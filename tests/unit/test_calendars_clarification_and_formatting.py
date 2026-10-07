"""Fiscal calendars per company, clarification answers, chart buckets, and number formatting."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from financial_analyst_agent.answer_notes import CALENDARS_DIFFER_BANNER, period_notes
from financial_analyst_agent.api import _Throttle
from financial_analyst_agent.contracts import Intent, RendererKind, TableRow, TurnResult
from financial_analyst_agent.graph.analysis_spec import (
    AnalysisSpec,
    PeriodSelection,
    ResolvedCompany,
    SpecPatch,
    compile_tasks,
)
from financial_analyst_agent.graph.clarify import clarification_reply
from financial_analyst_agent.graph.spec_turn import materialize_period_dates
from financial_analyst_agent.presentation import format_usd, present_turn
from financial_analyst_agent.request_wording import read_window
from financial_analyst_agent.thread_store import PendingClarification
from helpers import FakeFacts

_MSFT = (date(2026, 3, 31), date(2025, 12, 31), date(2025, 9, 30))
_AAPL = (date(2026, 6, 27), date(2026, 3, 28), date(2025, 12, 27))
_NVDA = (date(2026, 7, 26), date(2026, 4, 26), date(2025, 10, 26))


def _company(query: str) -> ResolvedCompany:
    return ResolvedCompany(cik=query, name=query, ticker=query.upper(), query=query)


def _pending() -> PendingClarification:
    return PendingClarification(
        kind="ambiguous_metric",
        candidates=("net_income", "operating_income"),
        patch=SpecPatch(),
    )


def test_a_new_question_naming_a_candidate_is_not_an_answer() -> None:
    reply = clarification_reply(_pending(), "net income")
    assert reply is not None and reply.chosen == ("net_income",)
    assert clarification_reply(_pending(), "What was Microsoft's net income?") is None
    assert clarification_reply(_pending(), "compare Apple and Microsoft net income") is None


class _Listing(FakeFacts):
    def __init__(self) -> None:
        self.listed: list[str] = []

    def list_quarterly_report_dates(self, company: str, *, limit: int) -> tuple[date, ...]:
        self.listed.append(company)
        if company == "Missing":
            raise LookupError("no such company")
        return {"Microsoft": _MSFT, "Apple": _AAPL, "Nvidia": _NVDA}[company][:limit]


class _Runtime:
    def __init__(self) -> None:
        self.facts = _Listing()


def _window(*queries: str) -> AnalysisSpec:
    return AnalysisSpec(
        companies=tuple(_company(query) for query in queries),
        metrics=("revenue",),
        periods=PeriodSelection(kind="last_n_quarters", count=3),
    )


def test_each_fiscal_calendar_asks_for_its_own_quarters() -> None:
    runtime = _Runtime()

    spec = materialize_period_dates(_window("Microsoft", "Apple", "Nvidia"), runtime)  # type: ignore[arg-type]
    tasks = compile_tasks(spec)

    # Apple's quarters sit on Microsoft's calendar grid, so they share its dates;
    # Nvidia's April/July/October quarters are asked for on their own dates.
    asked = {(task.issuers, task.report_date) for task in tasks}
    assert asked == {
        *((("Microsoft", "Apple"), day) for day in _MSFT),
        *((("Nvidia",), day) for day in _NVDA),
    }
    message = "revenue"
    assert CALENDARS_DIFFER_BANNER in period_notes(
        message, spec, window=read_window(message)
    )


# Quarter ends back to 2023: a "since 2024" window keeps those on or after 1 January 2024.
_AAPL_SINCE = (
    date(2026, 6, 27),
    date(2026, 3, 28),
    date(2025, 12, 27),
    date(2025, 9, 27),
    date(2025, 6, 28),
    date(2025, 3, 29),
    date(2024, 12, 28),
    date(2024, 9, 28),
    date(2024, 6, 29),
    date(2024, 3, 30),
    date(2023, 12, 30),
    date(2023, 9, 30),
)
# Walmart's year ends in January: its quarter ended 31 January 2024 is since 2024.
_WMT_SINCE = (
    date(2026, 4, 30),
    date(2026, 1, 31),
    date(2025, 10, 31),
    date(2025, 7, 31),
    date(2025, 4, 30),
    date(2025, 1, 31),
    date(2024, 10, 31),
    date(2024, 7, 31),
    date(2024, 4, 30),
    date(2024, 1, 31),
    date(2023, 10, 31),
)


class _LongListing(FakeFacts):
    def __init__(self) -> None:
        self.limits: list[int] = []

    def list_quarterly_report_dates(self, company: str, *, limit: int) -> tuple[date, ...]:
        self.limits.append(limit)
        return {"Apple": _AAPL_SINCE, "Walmart": _WMT_SINCE}[company][:limit]


def _since(year: int, *queries: str) -> AnalysisSpec:
    return AnalysisSpec(
        companies=tuple(_company(query) for query in queries),
        metrics=("revenue",),
        periods=PeriodSelection(kind="last_n_quarters", count=40, since_year=year),
    )


def test_a_since_window_is_every_quarter_ended_on_or_after_that_january() -> None:
    runtime = _Runtime()
    runtime.facts = _LongListing()

    spec = materialize_period_dates(_since(2024, "Apple"), runtime)  # type: ignore[arg-type]

    # The cap is the listing's limit; the window is the quarters since 1 January 2024.
    assert runtime.facts.limits == [40]
    assert spec.periods.report_dates == _AAPL_SINCE[:10]
    assert (spec.periods.count, spec.periods.since_year) == (10, 2024)
    assert spec.periods.asked is None


def test_each_company_keeps_its_own_quarters_since_that_january() -> None:
    runtime = _Runtime()
    runtime.facts = _LongListing()

    spec = materialize_period_dates(_since(2024, "Apple", "Walmart"), runtime)  # type: ignore[arg-type]

    own = dict(spec.periods.company_report_dates)
    assert own["Walmart"] == _WMT_SINCE[:10]
    assert own["Walmart"][-1] == date(2024, 1, 31)


def test_a_since_window_with_no_quarter_yet_shows_the_latest() -> None:
    runtime = _Runtime()
    runtime.facts = _LongListing()

    spec = materialize_period_dates(_since(2027, "Apple"), runtime)  # type: ignore[arg-type]

    assert spec.periods.report_dates == _AAPL_SINCE[:1]


def test_adding_a_company_lists_only_that_company() -> None:
    runtime = _Runtime()
    spec = materialize_period_dates(_window("Microsoft"), runtime)  # type: ignore[arg-type]
    grown = spec.model_copy(
        update={"companies": (*spec.companies, _company("Nvidia"), _company("Missing"))}
    )

    spec = materialize_period_dates(grown, runtime)  # type: ignore[arg-type]

    assert runtime.facts.listed == ["Microsoft", "Nvidia", "Missing"]
    # Keyed by the company's CIK (here its query stands in for one).
    assert dict(spec.periods.company_report_dates)["Nvidia"] == _NVDA
    # A company that cannot be listed falls back to the shared window.
    groups = {task.issuers for task in compile_tasks(spec)}
    assert groups == {("Microsoft", "Missing"), ("Nvidia",)}


def test_one_calendar_compiles_as_before() -> None:
    spec = materialize_period_dates(_window("Microsoft", "Apple"), _Runtime())  # type: ignore[arg-type]

    assert [task.report_date for task in compile_tasks(spec)] == list(_MSFT)
    message = "revenue"
    assert CALENDARS_DIFFER_BANNER not in period_notes(
        message, spec, window=read_window(message)
    )


def _row(name: str, end: date, value: str) -> TableRow:
    return TableRow(
        company_name=name,
        ticker=name[:4].upper(),
        cik=name,
        metric="revenue",
        value=Decimal(value),
        start_date=end - timedelta(days=90),
        end_date=end,
        form="10-Q",
        accession_number=f"{name}-{end}",
        concept="Revenues",
        source_url="https://www.sec.gov/",
    )


def test_trend_chart_puts_a_fiscal_week_apart_in_one_quarter() -> None:
    rows = [
        _row("Microsoft", date(2026, 3, 31), "82"),
        _row("Microsoft", date(2025, 12, 31), "81"),
        _row("Apple", date(2026, 3, 28), "111"),
        _row("Apple", date(2025, 12, 27), "143"),
    ]
    result = TurnResult(
        intent=Intent.COMPARE, renderer=RendererKind.TABLE, table_rows=rows, tool_traces=[]
    )

    chart = present_turn(result).chart

    assert chart is not None
    assert [record["Period"] for record in chart.records] == ["2025-12-31", "2026-03-31"]
    assert all({"Microsoft", "Apple"} <= set(record) for record in chart.records)


def test_usd_rounding_that_reaches_the_next_unit_uses_it() -> None:
    assert format_usd(Decimal("999996000")) == "$1.00 B"
    assert format_usd(Decimal("999999999999")) == "$1.00 T"
    assert format_usd(Decimal("999994")) == "$999.99 K"
    assert format_usd(Decimal("-2500000000")) == "-$2.50 B"


def test_purge_throttle_allows_one_scan_per_interval() -> None:
    throttle = _Throttle(60)
    start = datetime(2026, 9, 27, tzinfo=UTC)

    assert throttle.due(start)
    assert not throttle.due(start + timedelta(seconds=30))
    assert throttle.due(start + timedelta(seconds=61))
