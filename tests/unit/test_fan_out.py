"""A turn fetches its companies at once, keeping their order (ADR 0005)."""

import threading
import time
from dataclasses import replace
from datetime import date
from typing import Any

import pytest

from financial_analyst_agent.domain.errors import SessionQuotaError
from financial_analyst_agent.fan_out import map_in_order
from financial_analyst_agent.providers.sec.client import sec_turn_budget, sec_turn_seconds_left
from financial_analyst_agent.turn import run_turn
from test_run_turn_rank import HEALTHCARE_TOP_10, _snapshot_rank_runtime
from test_run_turn_rank_and_lookup import HEALTHCARE_INCOME_QUERY


def test_results_keep_the_order_of_their_items_not_of_finishing() -> None:
    def slower_first(item: int) -> int:
        time.sleep(0.01 * (5 - item))
        return item * 10

    assert map_in_order(slower_first, [0, 1, 2, 3, 4]) == [0, 10, 20, 30, 40]


def test_calls_run_at_once() -> None:
    # Three calls that each wait for the other two: run one at a time, they never meet.
    meeting = threading.Barrier(3, timeout=5)

    assert map_in_order(lambda item: meeting.wait() is not None, [0, 1, 2]) == [True] * 3


def test_each_call_shares_the_turns_sec_deadline() -> None:
    with sec_turn_budget(30):
        left = map_in_order(lambda _item: sec_turn_seconds_left(), [0, 1, 2])

    assert all(0 < seconds <= 30 for seconds in left)


def test_a_spent_session_budget_stops_the_fan_out() -> None:
    started: list[int] = []

    def call(item: int) -> int:
        started.append(item)
        if item == 0:
            raise SessionQuotaError("This thread has reached its live SEC request limit.")
        time.sleep(0.05)
        return item

    with pytest.raises(SessionQuotaError):
        map_in_order(call, list(range(20)), max_workers=2)
    # Calls not yet started when the error surfaced never run.
    assert len(started) < 20


class _OverlapCountingFacts:
    """The recorded facts, counting how many companies are fetched at the same time."""

    def __init__(self, facts: Any) -> None:
        self._facts = facts
        self._lock = threading.Lock()
        self._now = 0
        self.most = 0

    def get_financials(self, company: str, metric: str, *, report_date: date | None = None) -> Any:
        with self._lock:
            self._now += 1
            self.most = max(self.most, self._now)
        try:
            time.sleep(0.05)
            return self._facts.get_financials(company, metric, report_date=report_date)
        finally:
            with self._lock:
                self._now -= 1

    def __getattr__(self, name: str) -> Any:
        return getattr(self._facts, name)


def test_a_ranked_lookup_fetches_its_members_at_once_in_rank_order() -> None:
    runtime = _snapshot_rank_runtime()
    facts = _OverlapCountingFacts(runtime.facts)

    result = run_turn(HEALTHCARE_INCOME_QUERY, replace(runtime, facts=facts))

    assert facts.most > 1
    assert [row.cik for row in result.table_rows] == [
        cik for _name, _ticker, cik, _cap in HEALTHCARE_TOP_10
    ]
    assert [trace.args.get("company") for trace in result.tool_traces[1:]] == [
        cik for _name, _ticker, cik, _cap in HEALTHCARE_TOP_10
    ]
