"""Conversation seam: concurrent cell dispatch and progress (ticket 12).

Asserts independent cells run concurrently with bounded workers, preserve
serial-equivalent values/order/provenance, isolate cell failures, and report
progress. Does not assert graph internals. Uses a real temporary store.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from datetime import date
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from financial_analyst_agent.domain.errors import UnsupportedQuarterlyFactError
from financial_analyst_agent.runtime import FIXTURE_UNIVERSE_SNAPSHOT_PATH
from helpers import ListedFilings, named_by_cik

# Resolved companies are asked for by CIK; these fakes answer by name.
_NAMED = named_by_cik('Microsoft')

Q1 = date(2025, 3, 31)
Q2 = date(2025, 6, 30)
Q3 = date(2025, 9, 30)
Q4 = date(2025, 12, 31)
FOUR_QUARTERS = (Q4, Q3, Q2, Q1)


class _SlowFacts(ListedFilings):
    """Facts that overlap in wall time so concurrency is observable."""

    def __init__(
        self,
        values: dict[tuple[str, str, date], Decimal],
        *,
        missing: set[tuple[str, str, date]] | None = None,
        hold_ms: float = 0.05,
    ) -> None:
        super().__init__({"Microsoft": FOUR_QUARTERS})
        self.values = values
        self.missing = missing or set()
        self.hold_ms = hold_ms
        self._lock = threading.Lock()
        self.in_flight = 0
        self.peak_in_flight = 0
        self.calls: list[tuple[str, str, date | None]] = []

    def list_quarterly_report_dates(self, company: str, *, limit: int) -> tuple[date, ...]:
        return super().list_quarterly_report_dates(_NAMED(company), limit=limit)

    def get_financials(
        self, company: str, metric: str, *, report_date: date | None = None
    ) -> SimpleNamespace:
        company = _NAMED(company)
        with self._lock:
            self.in_flight += 1
            self.peak_in_flight = max(self.peak_in_flight, self.in_flight)
            self.calls.append((company, metric, report_date))
        try:
            time.sleep(self.hold_ms)
            if report_date is None:
                report_date = FOUR_QUARTERS[0]
            if (company, metric, report_date) in self.missing:
                raise UnsupportedQuarterlyFactError(
                    f"no standalone quarter for {company} {metric} {report_date.isoformat()}"
                )
            value = self.values[(company, metric, report_date)]
            return SimpleNamespace(
                company_name=company,
                ticker="MSFT" if company == "Microsoft" else "GOOG",
                cik="0000789019" if company == "Microsoft" else "0001652044",
                metric=metric,
                value=value,
                currency="USD",
                start_date=date(report_date.year, report_date.month - 2, 1)
                if report_date.month > 2
                else date(report_date.year - 1, 10, 1),
                end_date=report_date,
                filed_date=report_date,
                form="10-Q",
                accession_number=f"acc-{report_date.isoformat()}",
                taxonomy="us-gaap",
                concept=metric,
                source_url="https://www.sec.gov/example.htm",
                source="sec_xbrl",
            )
        finally:
            with self._lock:
                self.in_flight -= 1


def _four_metric_values() -> dict[tuple[str, str, date], Decimal]:
    out: dict[tuple[str, str, date], Decimal] = {}
    for end, base in ((Q4, 400), (Q3, 300), (Q2, 200), (Q1, 100)):
        out[("Microsoft", "revenue", end)] = Decimal(base)
        out[("Microsoft", "net_income", end)] = Decimal(base) // 4
    return out


def _runtime(*, completer: object, facts: object):
    from financial_analyst_agent.contracts import Runtime
    from financial_analyst_agent.ranking import SnapshotRanking

    return Runtime(
        completer=completer,  # type: ignore[arg-type]
        facts=facts,  # type: ignore[arg-type]
        ranking=SnapshotRanking.from_path(FIXTURE_UNIVERSE_SNAPSHOT_PATH),
    )


def _wide_lookup_completer():
    from financial_analyst_agent.graph.analysis_spec import PeriodSelection, SpecPatch

    class _Wide:
        def complete(self, query: str, current_spec: object = None) -> SpecPatch:
            return SpecPatch(
                mode="replace",
                add_companies=("Microsoft",),
                add_metrics=("revenue", "net_income"),
                set_periods=PeriodSelection(
                    kind="last_n_quarters",
                    count=4,
                    report_dates=FOUR_QUARTERS,
                ),
            )

    return _Wide()


def test_wide_analysis_matches_serial_values_provenance_and_order(tmp_path: Path) -> None:
    """Concurrent dispatch must not change numbers, provenance, or row order."""
    from financial_analyst_agent.contracts import Intent, RendererKind
    from financial_analyst_agent.conversation import run_conversation_turn
    from financial_analyst_agent.thread_store import LocalThreadStore

    message = "Microsoft revenue and net income for the last four quarters"
    store = LocalThreadStore(tmp_path)

    serial_facts = _SlowFacts(_four_metric_values(), hold_ms=0.0)
    serial = run_conversation_turn(
        "serial",
        message,
        _runtime(completer=_wide_lookup_completer(), facts=serial_facts),
        store=store,
        max_workers=1,
    )

    concurrent_facts = _SlowFacts(_four_metric_values(), hold_ms=0.05)
    concurrent = run_conversation_turn(
        "concurrent",
        message,
        _runtime(completer=_wide_lookup_completer(), facts=concurrent_facts),
        store=store,
        max_workers=4,
    )

    assert concurrent_facts.peak_in_flight >= 2
    assert concurrent.result.intent is Intent.LOOKUP
    assert concurrent.result.renderer is RendererKind.TABLE
    assert len(concurrent.result.table_rows) == 8
    assert [
        (row.metric, row.end_date, row.value, row.accession_number)
        for row in concurrent.result.table_rows
    ] == [
        (row.metric, row.end_date, row.value, row.accession_number)
        for row in serial.result.table_rows
    ]
    # Hand-checked: period-outer fan-out (Q4 revenue, Q4 net_income, …).
    assert concurrent.result.table_rows[0].metric == "revenue"
    assert concurrent.result.table_rows[0].end_date == Q4
    assert concurrent.result.table_rows[0].value == Decimal("400")
    assert concurrent.result.table_rows[0].accession_number == "acc-2025-12-31"
    assert concurrent.result.table_rows[1].metric == "net_income"
    assert concurrent.result.table_rows[1].end_date == Q4
    assert concurrent.result.table_rows[1].value == Decimal("100")


def test_failed_cell_does_not_fail_turn_or_thread(tmp_path: Path) -> None:
    from financial_analyst_agent.contracts import MISSING_FACT, RendererKind
    from financial_analyst_agent.conversation import run_conversation_turn
    from financial_analyst_agent.thread_store import LocalThreadStore

    facts = _SlowFacts(
        _four_metric_values(),
        missing={("Microsoft", "revenue", Q2)},
        hold_ms=0.02,
    )
    store = LocalThreadStore(tmp_path)
    turn = run_conversation_turn(
        "t1",
        "Microsoft revenue and net income for the last four quarters",
        _runtime(completer=_wide_lookup_completer(), facts=facts),
        store=store,
        max_workers=4,
    )

    assert turn.result.renderer is RendererKind.TABLE
    by_key = {(row.metric, row.end_date): row for row in turn.result.table_rows}
    assert by_key[("revenue", Q4)].value == Decimal("400")
    assert by_key[("revenue", Q2)].value is None
    assert by_key[("revenue", Q2)].reason == MISSING_FACT
    assert by_key[("net_income", Q2)].value == Decimal("50")
    reloaded = store.load("t1")
    assert reloaded is not None


def test_session_quota_error_is_not_isolated_as_missing_fact(tmp_path: Path) -> None:
    from financial_analyst_agent.conversation import run_conversation_turn
    from financial_analyst_agent.domain.errors import SessionQuotaError
    from financial_analyst_agent.thread_store import LocalThreadStore

    class _QuotaFacts(_SlowFacts):
        def get_financials(self, company: str, metric: str, *, report_date: date | None = None):
            company = _NAMED(company)
            raise SessionQuotaError("This thread has reached its live SEC request limit.")

    store = LocalThreadStore(tmp_path)
    with pytest.raises(SessionQuotaError, match="live SEC"):
        run_conversation_turn(
            "t1",
            "Microsoft revenue and net income for the last four quarters",
            _runtime(completer=_wide_lookup_completer(), facts=_QuotaFacts(_four_metric_values())),
            store=store,
            max_workers=4,
        )
    assert store.load("t1") is None


def test_worker_provider_logs_include_thread_and_turn(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    from financial_analyst_agent.conversation import run_conversation_turn
    from financial_analyst_agent.observability import call_provider
    from financial_analyst_agent.thread_store import LocalThreadStore

    class _LoggedFacts(_SlowFacts):
        def get_financials(self, company: str, metric: str, *, report_date: date | None = None):
            company = _NAMED(company)
            return call_provider(
                "sec",
                lambda: _SlowFacts.get_financials(
                    self, company, metric, report_date=report_date
                ),
            )

    caplog.set_level(logging.INFO, logger="financial_analyst_agent")
    store = LocalThreadStore(tmp_path)
    run_conversation_turn(
        "t1",
        "Microsoft revenue and net income for the last four quarters",
        _runtime(
            completer=_wide_lookup_completer(),
            facts=_LoggedFacts(_four_metric_values(), hold_ms=0.01),
        ),
        store=store,
        max_workers=4,
    )
    sec_events = []
    for record in caplog.records:
        try:
            event = json.loads(record.message)
        except json.JSONDecodeError:
            continue
        if isinstance(event, dict) and event.get("provider") == "sec":
            sec_events.append(event)
    assert sec_events
    assert all(event.get("thread_id") == "t1" and event.get("turn") == 1 for event in sec_events)


def test_progress_reports_each_completed_cell(tmp_path: Path) -> None:
    from financial_analyst_agent.conversation import run_conversation_turn
    from financial_analyst_agent.thread_store import LocalThreadStore

    events: list[tuple[int, int]] = []
    store = LocalThreadStore(tmp_path)
    turn = run_conversation_turn(
        "t1",
        "Microsoft revenue and net income for the last four quarters",
        _runtime(
            completer=_wide_lookup_completer(),
            facts=_SlowFacts(_four_metric_values(), hold_ms=0.01),
        ),
        store=store,
        on_progress=lambda done, total: events.append((done, total)),
        max_workers=4,
    )

    assert len(turn.result.table_rows) == 8
    assert events[0][1] == 8
    assert [done for done, _total in events] == list(range(1, 9))
    assert events[-1] == (8, 8)


def test_concurrency_is_bounded(tmp_path: Path) -> None:
    from financial_analyst_agent.conversation import run_conversation_turn
    from financial_analyst_agent.thread_store import LocalThreadStore

    facts = _SlowFacts(_four_metric_values(), hold_ms=0.05)
    store = LocalThreadStore(tmp_path)
    run_conversation_turn(
        "t1",
        "Microsoft revenue and net income for the last four quarters",
        _runtime(completer=_wide_lookup_completer(), facts=facts),
        store=store,
        max_workers=2,
    )

    assert facts.peak_in_flight <= 2
    assert facts.peak_in_flight >= 2
