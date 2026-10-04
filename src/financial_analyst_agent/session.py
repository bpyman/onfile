"""Visitor session identity, quotas, and snapshot freeze copy."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from threading import Lock

from financial_analyst_agent.domain.errors import SessionQuotaError
from financial_analyst_agent.guide import format_date
from financial_analyst_agent.presentation import try_parse_datetime
from financial_analyst_agent.thread_store import ThreadState, ThreadStore


def new_thread_id() -> str:
    return str(uuid.uuid4())


class SessionBudget:
    """Per-thread caps for public demo spend."""

    def __init__(self, *, max_turns: int, max_live_sec_requests: int) -> None:
        self.max_turns = max_turns
        self.max_live_sec_requests = max_live_sec_requests
        self.turns = 0
        self.live_sec_requests = 0
        self._lock = Lock()

    @classmethod
    def from_counts(
        cls,
        *,
        turns: int,
        live_sec_requests: int,
        max_turns: int,
        max_live_sec_requests: int,
    ) -> SessionBudget:
        budget = cls(max_turns=max_turns, max_live_sec_requests=max_live_sec_requests)
        budget.turns = turns
        budget.live_sec_requests = live_sec_requests
        return budget

    def consume_turn(self) -> None:
        with self._lock:
            if self.turns >= self.max_turns:
                raise SessionQuotaError(
                    "This thread has reached its turn limit. Start over to continue."
                )
            self.turns += 1

    def consume_live_sec(self) -> None:
        with self._lock:
            if self.live_sec_requests >= self.max_live_sec_requests:
                # The thread's allowance never refills, so waiting would not help.
                raise SessionQuotaError(
                    "This thread has reached its live SEC request limit. "
                    "Start over to keep asking, or switch to the recorded runtime."
                )
            self.live_sec_requests += 1


def snapshot_status(
    as_of: str,
    *,
    now: datetime | None = None,
    stale_after_days: int = 30,
    recorded: bool = False,
) -> tuple[str, bool]:
    """Human freeze date plus whether the ranking snapshot is older than the threshold.

    The recorded runtime ranks a fixture frozen with its captured filings, so its age
    is by design: it is labelled as recorded and never flagged stale.
    """
    prefix = "Recorded universe snapshot as of" if recorded else "Universe snapshot as of"
    parsed = try_parse_datetime(as_of)
    clock = now or datetime.now(UTC)
    if parsed is None:
        return (f"{prefix} {as_of}", False)
    aware = parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)
    stale = not recorded and clock - aware >= timedelta(days=stale_after_days)
    # A freeze is refreshed at most daily, so the status bar gives the day only.
    banner = f"{prefix} {format_date(aware.astimezone(UTC).date())}"
    if stale:
        banner = f"{banner} — freeze is older than {stale_after_days} days"
    return banner, stale


def persist_session_budget(store: ThreadStore, thread_id: str, budget: SessionBudget) -> None:
    """Write turn and live-SEC counts to the thread so quotas survive reloads.

    The thread was just used, so its expiry clock restarts: a failed turn that
    ran past the thread's remaining time must not get it deleted.
    """
    saved = store.load(thread_id)
    if saved is None:
        store.save(
            ThreadState(
                thread_id=thread_id,
                turn_count=budget.turns,
                live_sec_requests=budget.live_sec_requests,
            )
        )
        return
    store.save(
        saved.model_copy(
            update={
                "turn_count": max(saved.turn_count, budget.turns),
                "live_sec_requests": max(saved.live_sec_requests, budget.live_sec_requests),
                "updated_at": datetime.now(UTC),
            }
        )
    )
