"""Fetch the largest companies' SEC data in the background, before anyone asks (ADR 0014).

A cold company costs a live turn its SEC downloads; a warm one is read from the
disk cache as a small digest. The warm-up walks the largest companies, largest
first, and fetches each one's first submissions page and facts digest when the
filing watch says it should. It keeps to its own share of the SEC request rate
and waits, before each of its requests, whenever visitors' requests are queued,
so a visitor never waits behind it. A failure is logged and the walk goes on
after a pause.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable, Sequence

from financial_analyst_agent.observability import log_event

_LOGGER = logging.getLogger(__name__)

# How often an idle warm-up looks again while visitors' requests are queued.
_IDLE_CHECK_SECONDS = 0.25
# How often a warm-up waiting for the filing watch looks again.
_READY_CHECK_SECONDS = 1.0
# The pause after a failure: SEC asking for quiet, or a company it would not serve.
_FAILURE_PAUSE_SECONDS = 30.0
# A company still not warm after warming (a cache that cannot keep its files) is not
# fetched again for this long, so a broken disk is not a download loop.
_NOT_KEPT_SECONDS = 6 * 3600.0


class FactsWarmer:
    """Warms ``ciks`` in order, when ``needs_warming(cik)`` says so.

    Warming a company makes each of ``requests`` in turn with its CIK: one a
    file (its first submissions page, its facts). ``idle()`` says whether SEC is
    free for background work, and is asked before every request; ``rate`` is
    the warm-up's requests a second.
    """

    def __init__(
        self,
        ciks: Sequence[str],
        *,
        requests: Sequence[Callable[[str], None]],
        needs_warming: Callable[[str], bool],
        idle: Callable[[], bool],
        rate: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._ciks = tuple(ciks)
        self._requests = tuple(requests)
        self._needs_warming = needs_warming
        self._idle = idle
        self._pause = len(self._requests) / rate
        self._clock = clock
        self._not_kept: dict[str, float] = {}

    def sweep(self, stop: threading.Event) -> int:
        """One walk over the companies; how many were warmed."""
        warmed = 0
        for cik in self._ciks:
            if stop.is_set():
                break
            if not self._needs_warming(cik):
                continue
            skipped_at = self._not_kept.get(cik)
            if skipped_at is not None and self._clock() - skipped_at < _NOT_KEPT_SECONDS:
                continue
            try:
                for request in self._requests:
                    # A visitor who queues between a company's requests is not behind the next.
                    while not self._idle():
                        if stop.wait(_IDLE_CHECK_SECONDS):
                            return warmed
                    request(cik)
            except Exception as exc:  # noqa: BLE001 - a visitor's turn fetches it instead
                log_event("sec_warm_failed", cik=cik, error=type(exc).__name__)
                if stop.wait(_FAILURE_PAUSE_SECONDS):
                    break
                continue
            warmed += 1
            if self._needs_warming(cik):
                # Fetched, but nothing lasting kept: leave it to visitors for a while.
                self._not_kept[cik] = self._clock()
                log_event("sec_warm_not_kept", cik=cik)
            if stop.wait(self._pause):
                break
        return warmed

    def run(self, stop: threading.Event, interval: float, ready: Callable[[], bool]) -> None:
        """Walk the companies every ``interval`` seconds until ``stop`` is set.

        A walk waits until ``ready()``: the filing watch's first poll, without
        which no company can be said to need warming.
        """
        while not stop.is_set():
            if not ready():
                stop.wait(_READY_CHECK_SECONDS)
                continue
            warmed = self.sweep(stop)
            if warmed:
                log_event("sec_warm_sweep", warmed=warmed, companies=len(self._ciks))
            stop.wait(interval)


_WARMER: FactsWarmer | None = None
_WARMER_LOCK = threading.Lock()


def ensure_facts_warmer(
    make: Callable[[], FactsWarmer], interval: float, ready: Callable[[], bool]
) -> FactsWarmer:
    """The process's warm-up, started on first use."""
    global _WARMER
    with _WARMER_LOCK:
        if _WARMER is None:
            warmer = make()
            threading.Thread(
                target=warmer.run,
                args=(threading.Event(), interval, ready),
                name="sec-warm",
                daemon=True,
            ).start()
            _WARMER = warmer
            _LOGGER.info("Warming the largest companies' SEC data in the background")
        return _WARMER
