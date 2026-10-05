"""Which companies have filed a 10-Q or 10-K lately, read from SEC's latest-filings feed.

A company's cached SEC data stays fresh until it files again (ADR 0013). SEC
lists its latest filings as an Atom feed; asked for ``10-Q`` it lists 10-Qs and
10-Q/As, and for ``10-K`` 10-Ks and 10-K/As, newest first. The watch reads both
every few minutes, pages back until it overlaps its last poll, and remembers
when each company last filed. It also knows from when it has seen every
filing, so a file written before that is not vouched for.
"""

from __future__ import annotations

import logging
import re
import threading
import time
import xml.etree.ElementTree as ElementTree
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from financial_analyst_agent.observability import log_event

_LOGGER = logging.getLogger(__name__)

# The forms whose filing changes a company's quarterly figures; each asks for its amendments too.
WATCHED_FORMS = ("10-Q", "10-K")
PAGE_SIZE = 100
# Pages read in one poll before a gap is accepted (earnings season fills a page in an hour).
_MAX_PAGES = 5
# A file the watch vouches for stays fresh this long without a filing.
VOUCHED_SECONDS = 7 * 24 * 3600
# After a filing, SEC's structured data may lag it by hours: refresh often for a day.
AFTER_FILING_SECONDS = 15 * 60
AFTER_FILING_WINDOW_SECONDS = 24 * 3600
# What a file gets when the watch cannot vouch for it: the rule before the watch.
DEFAULT_SECONDS = 3600
# A watch that has not polled successfully for this many intervals vouches for nothing.
_MISSED_POLLS = 3

_ATOM = "{http://www.w3.org/2005/Atom}"
_CIK_IN_TITLE = re.compile(r"\((\d{10})\)")


@dataclass(frozen=True)
class Filing:
    """One feed entry: who filed which form, and when SEC accepted it (epoch seconds)."""

    cik: str
    form: str
    accepted: float


def parse_feed(text: str) -> list[Filing]:
    """The filings an Atom page lists; an entry without a CIK, form or time is skipped."""
    root = ElementTree.fromstring(text)
    filings = []
    for entry in root.iter(f"{_ATOM}entry"):
        title = entry.findtext(f"{_ATOM}title") or ""
        updated = entry.findtext(f"{_ATOM}updated") or ""
        category = entry.find(f"{_ATOM}category")
        cik = _CIK_IN_TITLE.search(title)
        form = category.get("term", "") if category is not None else ""
        try:
            accepted = datetime.fromisoformat(updated).timestamp()
        except ValueError:
            continue
        if cik is not None and form:
            filings.append(Filing(cik=cik.group(1), form=form, accepted=accepted))
    return filings


class FilingWatch:
    """When each company last filed a 10-Q or 10-K, and how long its cached files may last.

    ``fetch_page(form, start)`` returns one Atom page of the latest filings of
    ``form``. ``poll`` reads every watched form; ``lifetime`` is what the SEC
    cache asks of each company file.
    """

    def __init__(
        self,
        fetch_page: Callable[[str, int], str],
        *,
        interval: float,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._fetch_page = fetch_page
        self._interval = interval
        self._clock = clock
        self._lock = threading.Lock()
        self._last_filed: dict[str, float] = {}
        self._newest: dict[str, float] = {}
        self._covered_from: dict[str, float] = {}
        self._last_poll: float | None = None

    def poll(self) -> None:
        """Read the latest filings of every watched form; an SEC error is raised, not swallowed."""
        now = self._clock()
        read = {form: self._read(form) for form in WATCHED_FORMS}
        with self._lock:
            for form, (filings, overlapped) in read.items():
                for filing in filings:
                    known = self._last_filed.get(filing.cik)
                    if known is None or filing.accepted > known:
                        self._last_filed[filing.cik] = filing.accepted
                if filings:
                    self._newest[form] = max(
                        self._newest.get(form, 0.0), *(f.accepted for f in filings)
                    )
                if form not in self._covered_from or not overlapped:
                    # Before the oldest filing read, a filing may have gone unseen.
                    oldest = min((f.accepted for f in filings), default=now)
                    self._covered_from[form] = oldest
            self._last_poll = now

    def _read(self, form: str) -> tuple[list[Filing], bool]:
        """This form's filings since the last poll, and whether they reached back to it."""
        previous = self._newest.get(form)
        filings: list[Filing] = []
        for page in range(_MAX_PAGES):
            batch = parse_feed(self._fetch_page(form, page * PAGE_SIZE))
            filings.extend(batch)
            if len(batch) < PAGE_SIZE:
                # The feed has nothing older: it reaches back as far as SEC keeps it.
                return filings, True
            if previous is not None and min(f.accepted for f in batch) <= previous:
                return filings, True
        return filings, False

    def lifetime(self, cik: str, written: float) -> float:
        """How long a company file written at ``written`` stays fresh, in seconds from then."""
        now = self._clock()
        with self._lock:
            healthy = (
                self._last_poll is not None
                and now - self._last_poll <= _MISSED_POLLS * self._interval
                and len(self._covered_from) == len(WATCHED_FORMS)
            )
            covered_from = max(self._covered_from.values(), default=None)
            filed = self._last_filed.get(cik)
        if not healthy or covered_from is None or written < covered_from:
            return DEFAULT_SECONDS
        if filed is not None and filed > written:
            # Filed after the file was written: it is out of date.
            return 0.0
        if filed is not None and now - filed < AFTER_FILING_WINDOW_SECONDS:
            return AFTER_FILING_SECONDS
        return VOUCHED_SECONDS

    def run(self, stop: threading.Event) -> None:
        """Poll every interval until ``stop`` is set; a failed poll is logged and retried."""
        while not stop.is_set():
            try:
                self.poll()
            except Exception as exc:  # noqa: BLE001 - the cache falls back to the hour
                log_event("sec_filing_watch_failed", error=type(exc).__name__)
            stop.wait(self._interval)


_WATCH: FilingWatch | None = None
_WATCH_LOCK = threading.Lock()


def ensure_filing_watch(
    fetch_page: Callable[[str, int], str], interval: float
) -> FilingWatch | None:
    """The process's filing watch, started on first use; None when ``interval`` is 0."""
    global _WATCH
    if interval <= 0:
        return None
    with _WATCH_LOCK:
        if _WATCH is None:
            watch = FilingWatch(fetch_page, interval=interval)
            threading.Thread(
                target=watch.run,
                args=(threading.Event(),),
                name="sec-filing-watch",
                daemon=True,
            ).start()
            _WATCH = watch
            _LOGGER.info("Watching SEC's latest 10-Q and 10-K filings every %.0f s", interval)
        return _WATCH
