"""Concurrency, failure isolation, and period-change edge cases found in review."""

from __future__ import annotations

import threading
import time
from datetime import date
from decimal import Decimal
from types import SimpleNamespace

import pytest

from financial_analyst_agent.contracts import LOOKUP_FAILED, RendererKind, TableRow
from financial_analyst_agent.domain.errors import DataIntegrityError, ProviderError
from financial_analyst_agent.evidence_store import EvidenceCachedFacts, InMemoryEvidenceStore
from financial_analyst_agent.graph.analysis_spec import CompiledTask
from financial_analyst_agent.graph.spec_turn import (
    TASK_FAILURE_MESSAGE,
    _task_failure_result,
    across_period_change_rows,
)
from financial_analyst_agent.providers.sec.client import _RateLimiter
from financial_analyst_agent.services.metric_catalog import resolve_metric_phrase


def _level(end: date, value: str) -> TableRow:
    return TableRow(
        company_name="Apple Inc.",
        ticker="AAPL",
        cik="0000320193",
        metric="revenue",
        value=Decimal(value),
        start_date=date(end.year, max(end.month - 2, 1), 1),
        end_date=end,
        form="10-Q",
        accession_number="0000320193-00-000000",
        concept="Revenues",
        source_url="https://www.sec.gov/",
    )


def test_metric_named_twice_resolves_to_one_metric() -> None:
    resolved = resolve_metric_phrase("Compare Apple's revenue and Microsoft's revenue")

    assert resolved.kind == "unique"
    assert resolved.metric == "revenue"
    assert resolved.metrics == ("revenue",)


def test_yoy_matches_a_52_53_week_fiscal_calendar() -> None:
    # Apple's June quarter ended Jun 27, 2026 and Jun 28, 2025: not the same date.
    rows = [_level(date(2026, 6, 27), "100"), _level(date(2025, 6, 28), "90")]

    yoy = [row for row in across_period_change_rows(rows) if row.comparison == "year_over_year"]

    assert len(yoy) == 1
    assert yoy[0].value == Decimal("10")


def test_sequential_change_skips_a_missing_quarter() -> None:
    # Q2 is missing: Q3 against Q1 is a two-quarter change, not a sequential one.
    rows = [
        _level(date(2025, 12, 31), "400"),
        _level(date(2025, 9, 30), "300"),
        _level(date(2025, 3, 31), "100"),
    ]

    sequential = [
        row for row in across_period_change_rows(rows) if row.comparison == "sequential"
    ]

    assert [(row.start_date, row.end_date) for row in sequential] == [
        (date(2025, 7, 1), date(2025, 12, 31))
    ]


def test_provider_failure_is_not_reported_as_a_missing_fact() -> None:
    task = CompiledTask(kind="lookup", issuers=("Apple",), metric="revenue")

    outage = _task_failure_result(task, ProviderError("SEC server error"))
    bug = _task_failure_result(task, ValueError("boom"))

    assert outage.table_rows[0].reason == "source_unavailable"
    assert bug.table_rows[0].reason == LOOKUP_FAILED


@pytest.mark.parametrize(
    "failure",
    [OSError(28, "No space left on device"), DataIntegrityError("identity mismatch")],
    ids=["disk", "integrity"],
)
def test_a_source_failure_that_is_not_a_provider_error_is_still_unavailable(
    failure: Exception,
) -> None:
    task = CompiledTask(kind="compare", issuers=("Apple", "Microsoft"), metric="revenue")

    result = _task_failure_result(task, failure)

    assert [row.reason for row in result.table_rows] == ["source_unavailable"] * 2


def test_tasks_still_running_when_the_turn_runs_out_answer_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from financial_analyst_agent.graph import analysis_spec, spec_turn
    from financial_analyst_agent.providers.sec.client import sec_turn_budget

    release = threading.Event()

    def fake_execute(task: object, runtime: object, *, query: str = "") -> object:
        if getattr(task, "metric", "") == "revenue":
            release.wait(5)
        return SimpleNamespace(renderer=RendererKind.TABLE, table_rows=[])

    monkeypatch.setattr(spec_turn, "execute_compiled_task", fake_execute)
    monkeypatch.setattr(spec_turn, "_TASK_GRACE_SECONDS", 0.1)
    task = analysis_spec.CompiledTask
    tasks = (
        task(kind="lookup", issuers=("Apple",), metric="revenue"),
        task(kind="lookup", issuers=("Apple",), metric="net_income"),
    )

    started = time.monotonic()
    try:
        with sec_turn_budget(0.1):
            results = spec_turn.dispatch_compiled_tasks(
                tasks, SimpleNamespace(), max_workers=2  # type: ignore[arg-type]
            )
    finally:
        release.set()

    assert time.monotonic() - started < 2
    assert results[0].table_rows[0].reason == "source_unavailable"
    assert results[1].table_rows == []


def test_unexpected_rank_failure_hides_the_exception_text() -> None:
    task = CompiledTask(kind="rank", industry="technology", limit=5)

    result = _task_failure_result(task, RuntimeError("rank intent requires a ranking adapter"))

    assert result.renderer is RendererKind.REFUSE
    assert result.message == TASK_FAILURE_MESSAGE


def test_quota_stop_does_not_run_the_queued_tasks(monkeypatch: pytest.MonkeyPatch) -> None:
    # Imported here: another test drops package modules from sys.modules, so
    # module-level classes can go stale in a full run.
    from financial_analyst_agent.domain import errors
    from financial_analyst_agent.graph import analysis_spec, spec_turn

    started: list[str] = []
    lock = threading.Lock()

    def fake_execute(task: object, runtime: object, *, query: str = "") -> object:
        metric = getattr(task, "metric", "") or ""
        with lock:
            started.append(metric)
        if metric == "revenue":
            raise errors.SessionQuotaError("reached its live SEC request limit")
        time.sleep(0.05)
        return SimpleNamespace()

    monkeypatch.setattr(spec_turn, "execute_compiled_task", fake_execute)
    task = analysis_spec.CompiledTask
    tasks = (task(kind="lookup", issuers=("Apple",), metric="revenue"),) + tuple(
        task(kind="lookup", issuers=("Apple",), metric=f"m{i}") for i in range(40)
    )

    with pytest.raises(errors.SessionQuotaError):
        spec_turn.dispatch_compiled_tasks(tasks, SimpleNamespace(), max_workers=2)  # type: ignore[arg-type]

    assert len(started) < len(tasks)


def test_rate_limiter_spaces_concurrent_requests(monkeypatch: pytest.MonkeyPatch) -> None:
    # The limiter reserves slots 50 ms apart; the waits it asks for say so exactly,
    # where wall-clock stamps would read Windows' coarse clock and early wake-ups.
    from financial_analyst_agent.providers.sec import client

    waits: list[float] = []
    lock = threading.Lock()

    def record(seconds: float) -> None:
        with lock:
            waits.append(seconds)

    monkeypatch.setattr(client.time, "sleep", record)
    limiter = _RateLimiter(0.05)
    threads = [threading.Thread(target=limiter.acquire) for _ in range(5)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    # The first request goes at once; the other four wait for their slots.
    assert len(waits) == 4
    assert max(waits) == pytest.approx(0.2, abs=0.02)
    assert sorted(waits) == pytest.approx([0.05, 0.1, 0.15, 0.2], abs=0.02)


def test_dated_lookup_error_is_not_retried_as_latest_quarter() -> None:
    calls: list[date | None] = []

    class _Facts:
        def get_financials(
            self, company: str, metric: str, *, report_date: date | None = None
        ) -> object:
            calls.append(report_date)
            raise TypeError("unsupported operand type(s) for -: 'NoneType' and 'datetime.date'")

    cached = EvidenceCachedFacts(
        _Facts(), InMemoryEvidenceStore(), prior_ids=frozenset()
    )

    with pytest.raises(TypeError):
        cached.get_financials("Apple", "revenue", report_date=date(2025, 6, 28))

    assert calls == [date(2025, 6, 28)]


def test_evidence_cache_passes_the_snapshot_name_through() -> None:
    class _Named:
        def display_name(self, cik: str, fallback: str) -> str:
            return "Pfizer Inc." if cik == "0000078003" else fallback

    class _Bare:
        pass

    named = EvidenceCachedFacts(_Named(), InMemoryEvidenceStore(), prior_ids=frozenset())
    bare = EvidenceCachedFacts(_Bare(), InMemoryEvidenceStore(), prior_ids=frozenset())

    assert named.display_name("0000078003", "PFIZER INC") == "Pfizer Inc."
    assert bare.display_name("0000078003", "PFIZER INC") == "PFIZER INC"
