"""Fiscal calendars per company, clarification answers, chart buckets, and number formatting."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from financial_analyst_agent.api import _Throttle
from financial_analyst_agent.contracts import Intent, RendererKind, TableRow, TurnResult
from financial_analyst_agent.graph.analysis_spec import (
    AnalysisSpec,
    PeriodSelection,
    ResolvedCompany,
    SpecPatch,
)
from financial_analyst_agent.graph.clarify import clarification_reply
from financial_analyst_agent.graph.spec_turn import compile_tasks
from financial_analyst_agent.period_selection import CALENDARS_DIFFER_BANNER, Periods, read
from financial_analyst_agent.presentation import format_usd, present_turn
from financial_analyst_agent.request_wording import change_asked
from financial_analyst_agent.services.fiscal_periods import FiscalPeriod
from financial_analyst_agent.thread_store import PendingClarification
from helpers import ListedFilings

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


def _facts() -> ListedFilings:
    return ListedFilings(
        {"Microsoft": _MSFT, "Apple": _AAPL, "Nvidia": _NVDA}, failing=("Missing",)
    )


def _window(*queries: str) -> AnalysisSpec:
    return AnalysisSpec(
        companies=tuple(_company(query) for query in queries),
        metrics=("revenue",),
        periods=PeriodSelection(kind="last_n_quarters", count=3),
    )


def _notes(message: str, spec: AnalysisSpec) -> list[str]:
    """The period notes in the order the answer shows them."""
    notes = Periods(spec).notes(read(message).reading, change_asked(message))
    return [*notes.read, *notes.shown]


def test_each_fiscal_calendar_asks_for_its_own_quarters() -> None:
    facts = _facts()

    spec = Periods(_window("Microsoft", "Apple", "Nvidia")).dated(facts).spec
    tasks = compile_tasks(spec)

    # Apple's quarters sit on Microsoft's calendar grid, so they share its dates;
    # Nvidia's April/July/October quarters are asked for on their own dates.
    asked = {(task.issuers, task.report_date) for task in tasks}
    assert asked == {
        *((("Microsoft", "Apple"), day) for day in _MSFT),
        *((("Nvidia",), day) for day in _NVDA),
    }
    message = "revenue"
    assert CALENDARS_DIFFER_BANNER in _notes(message, spec)


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


def _long_listing() -> ListedFilings:
    return ListedFilings({"Apple": _AAPL_SINCE, "Walmart": _WMT_SINCE})


def _since(year: int, *queries: str) -> AnalysisSpec:
    return AnalysisSpec(
        companies=tuple(_company(query) for query in queries),
        metrics=("revenue",),
        periods=PeriodSelection(kind="last_n_quarters", count=40, since_year=year),
    )


def test_a_since_window_is_every_quarter_ended_on_or_after_that_january() -> None:
    facts = _long_listing()

    spec = Periods(_since(2024, "Apple")).dated(facts).spec

    # The cap is the listing's limit; the window is the quarters since 1 January 2024.
    assert facts.listed == [("Apple", 40)]
    assert spec.periods.report_dates == _AAPL_SINCE[:10]
    assert (spec.periods.count, spec.periods.since_year) == (10, 2024)
    assert spec.periods.asked is None


def test_each_company_keeps_its_own_quarters_since_that_january() -> None:
    facts = _long_listing()

    spec = Periods(_since(2024, "Apple", "Walmart")).dated(facts).spec

    own = dict(spec.periods.company_report_dates)
    assert own["Walmart"] == _WMT_SINCE[:10]
    assert own["Walmart"][-1] == date(2024, 1, 31)


def test_a_since_window_with_no_quarter_yet_shows_the_latest() -> None:
    facts = _long_listing()

    spec = Periods(_since(2027, "Apple")).dated(facts).spec

    assert spec.periods.report_dates == _AAPL_SINCE[:1]


def _fiscal(end: date, year: int, quarter: int) -> FiscalPeriod:
    return FiscalPeriod(
        end=end, fiscal_year=year, quarter=quarter, form="10-K" if quarter == 4 else "10-Q"
    )


# Apple's fiscal 2025 opened with the quarter ended December 2024, Microsoft's
# with the quarter ended September 2024: each on its own calendar.
_AAPL_FISCAL = (
    _fiscal(date(2026, 6, 27), 2026, 3),
    _fiscal(date(2026, 3, 28), 2026, 2),
    _fiscal(date(2025, 12, 27), 2026, 1),
    _fiscal(date(2025, 9, 27), 2025, 4),
    _fiscal(date(2025, 6, 28), 2025, 3),
    _fiscal(date(2025, 3, 29), 2025, 2),
    _fiscal(date(2024, 12, 28), 2025, 1),
    _fiscal(date(2024, 9, 28), 2024, 4),
    _fiscal(date(2024, 6, 29), 2024, 3),
)
_MSFT_FISCAL = (
    _fiscal(date(2026, 6, 30), 2026, 4),
    _fiscal(date(2026, 3, 31), 2026, 3),
    _fiscal(date(2025, 12, 31), 2026, 2),
    _fiscal(date(2025, 9, 30), 2026, 1),
    _fiscal(date(2025, 6, 30), 2025, 4),
    _fiscal(date(2025, 3, 31), 2025, 3),
    _fiscal(date(2024, 12, 31), 2025, 2),
    _fiscal(date(2024, 9, 30), 2025, 1),
    _fiscal(date(2024, 6, 30), 2024, 4),
)
# Fifty quarters on Microsoft's calendar, newest first, back to Q3 of fiscal 2014.
_LONG_FISCAL = tuple(
    _fiscal(
        date(2026 - (index + 2) // 4, (6, 3, 12, 9)[index % 4], 30),
        2026 - index // 4,
        4 - index % 4,
    )
    for index in range(50)
)


def _fiscal_listing() -> ListedFilings:
    return ListedFilings(
        fiscal={"Apple": _AAPL_FISCAL, "Microsoft": _MSFT_FISCAL, "Long": _LONG_FISCAL}
    )


def _since_fiscal(year: int, *queries: str) -> AnalysisSpec:
    return AnalysisSpec(
        companies=tuple(_company(query) for query in queries),
        metrics=("revenue",),
        periods=PeriodSelection(
            kind="last_n_quarters", count=40, since_year=year, since_fiscal=True
        ),
    )


def test_since_a_fiscal_year_counts_from_each_companys_own_fiscal_year() -> None:
    facts = _fiscal_listing()

    spec = Periods(_since_fiscal(2025, "Apple", "Microsoft")).dated(facts).spec

    # Read where the fiscal periods are listed, as a named fiscal year is
    # (probe-round-3-gaps ticket 06): Apple's from December 2024, Microsoft's
    # from September 2024. No report dates were listed.
    assert spec.periods.report_dates == tuple(period.end for period in _AAPL_FISCAL[:7])
    own = dict(spec.periods.company_report_dates)
    assert own["Microsoft"] == tuple(period.end for period in _MSFT_FISCAL[:8])
    assert facts.listed == [("Apple", None), ("Microsoft", None)]
    # The filings hold every quarter of both spans: nothing more was asked for.
    assert (spec.periods.count, spec.periods.since_fiscal, spec.periods.asked) == (7, True, None)


def test_since_a_fiscal_year_the_filings_do_not_reach_carries_the_span_asked() -> None:
    facts = _fiscal_listing()

    spec = Periods(_since_fiscal(2015, "Apple")).dated(facts).spec

    # Q1 of fiscal 2015 to Q3 of fiscal 2026 is 47 quarters on Apple's own
    # labels; the filings hold nine, so the note can say how many are missing.
    assert spec.periods.report_dates == tuple(period.end for period in _AAPL_FISCAL)
    assert (spec.periods.count, spec.periods.asked) == (9, 47)


def test_since_a_fiscal_year_is_capped_at_the_window_cap() -> None:
    facts = _fiscal_listing()

    spec = Periods(_since_fiscal(2014, "Long")).dated(facts).spec

    # Fifty quarters since Q3 of fiscal 2014 would be held, but the window shows
    # the latest forty; the span asked is the fifty, from Q1 of that year: 52.
    assert spec.periods.report_dates == tuple(period.end for period in _LONG_FISCAL[:40])
    assert (spec.periods.count, spec.periods.asked) == (40, 52)


def test_since_a_fiscal_year_ahead_of_the_filings_shows_the_latest() -> None:
    facts = _fiscal_listing()

    spec = Periods(_since_fiscal(2027, "Apple")).dated(facts).spec

    assert spec.periods.report_dates == (date(2026, 6, 27),)
    assert spec.periods.asked is None


def test_adding_a_company_lists_only_that_company() -> None:
    facts = _facts()
    spec = Periods(_window("Microsoft")).dated(facts).spec
    grown = spec.model_copy(
        update={"companies": (*spec.companies, _company("Nvidia"), _company("Missing"))}
    )

    spec = Periods(grown).dated(facts).spec

    assert facts.listed == [("Microsoft", 3), ("Nvidia", 3), ("Missing", 3)]
    # Keyed by the company's CIK (here its query stands in for one).
    assert dict(spec.periods.company_report_dates)["Nvidia"] == _NVDA
    # A company that cannot be listed falls back to the shared window.
    groups = {task.issuers for task in compile_tasks(spec)}
    assert groups == {("Microsoft", "Missing"), ("Nvidia",)}


def test_one_calendar_compiles_as_before() -> None:
    spec = Periods(_window("Microsoft", "Apple")).dated(_facts()).spec

    assert [task.report_date for task in compile_tasks(spec)] == list(_MSFT)
    message = "revenue"
    assert CALENDARS_DIFFER_BANNER not in _notes(message, spec)


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


@pytest.mark.parametrize(
    ("answer", "chosen"),
    [
        ("the net one please", ("net_income",)),
        ("net", ("net_income",)),
        ("income", None),
        ("the one", None),
        ("gross", None),
    ],
)
def test_a_metric_answer_names_the_one_candidate_holding_its_words(
    answer: str, chosen: tuple[str, ...] | None
) -> None:
    reply = clarification_reply(_pending(), answer)
    assert (reply.chosen if reply is not None else None) == chosen


@pytest.mark.parametrize(
    ("answer", "chosen"),
    [
        ("the corporation one", ("LNC",)),
        ("holdings", ("LECO",)),
        # "national" is in two labels; "lincoln" is the name asked about.
        ("the national one", None),
        ("lincoln", None),
        ("the one", None),
    ],
)
def test_a_company_answer_names_the_one_offered_company_holding_its_words(
    answer: str, chosen: tuple[str, ...] | None
) -> None:
    pending = PendingClarification(
        kind="ambiguous_company",
        candidates=("LECO", "LNC", "LNN"),
        labels=(
            "Lincoln Electric Holdings, Inc. (LECO)",
            "Lincoln National Corporation (LNC)",
            "Lincoln National Bancorp (LNN)",
        ),
        subject="Lincoln",
        patch=SpecPatch(),
    )
    reply = clarification_reply(pending, answer)
    assert (reply.chosen if reply is not None else None) == chosen


def test_a_metric_answer_keeps_the_held_questions_window() -> None:
    from financial_analyst_agent.graph.clarify import resumed_request

    held = PendingClarification(
        kind="ambiguous_metric",
        candidates=("gross_margin", "net_margin"),
        patch=SpecPatch(mode="replace", add_companies=("Apple",)),
        question="Apple margin over the past few quarters",
    )
    resumed = resumed_request(held, ("gross_margin",), "gross margin", None)
    assert resumed.window == read(held.question).reading
    assert resumed.window.asked_quarters == 4 and resumed.window.interpretation_notes
    # A reply naming a window of its own is read, as the wording it resolves.
    own = resumed_request(held, ("gross_margin",), "gross margin last 6 quarters", None)
    assert own.window.asked_quarters == 6


@pytest.mark.parametrize(
    ("question", "direct", "note"),
    [
        ("Apple margin last year", "Apple gross margin last year", "The last year:"),
        ("Apple margin YTD", "Apple gross margin YTD", "Year-to-date"),
    ],
)
def test_a_metric_reply_keeps_the_held_questions_period_notes(
    question: str, direct: str, note: str
) -> None:
    """The held question's last-year and year-to-date notes survive a metric reply,
    as they show when the same question names the metric itself."""
    from financial_analyst_agent.conversation import run_conversation_turn, start_thread
    from financial_analyst_agent.runtime import RuntimeKind, recorded_runtime
    from financial_analyst_agent.thread_store import EphemeralThreadStore

    runtime, store = recorded_runtime(), EphemeralThreadStore()
    start_thread("held-window", RuntimeKind.RECORDED, store=store)
    asked = run_conversation_turn("held-window", question, runtime, store=store).result
    assert asked.renderer is RendererKind.CLARIFY
    answer = run_conversation_turn("held-window", "gross margin", runtime, store=store).result

    start_thread("asked-direct", RuntimeKind.RECORDED, store=store)
    named = run_conversation_turn("asked-direct", direct, runtime, store=store).result

    def notes(result: TurnResult) -> list[str]:
        return [banner for banner in result.banners if banner.startswith(note)]

    assert notes(answer) and notes(answer) == notes(named)


@pytest.mark.parametrize(
    ("question", "direct"),
    [
        # The growth note, the segment note, and the base still to be asked.
        ("Apple margin growth", "Apple gross margin growth"),
        ("iPhone margin", "iPhone gross margin"),
        ("Why did Apple margin fall", "Why did Apple gross margin fall"),
    ],
)
def test_a_metric_reply_answers_as_the_question_naming_the_metric(
    question: str, direct: str
) -> None:
    """A metric chosen on a clarification resumes the held question, not the reply's words."""
    from financial_analyst_agent.conversation import run_conversation_turn, start_thread
    from financial_analyst_agent.runtime import RuntimeKind, recorded_runtime
    from financial_analyst_agent.thread_store import EphemeralThreadStore

    runtime, store = recorded_runtime(), EphemeralThreadStore()
    start_thread("held", RuntimeKind.RECORDED, store=store)
    asked = run_conversation_turn("held", question, runtime, store=store).result
    assert asked.renderer is RendererKind.CLARIFY
    answer = run_conversation_turn("held", "gross margin", runtime, store=store).result

    start_thread("direct", RuntimeKind.RECORDED, store=store)
    named = run_conversation_turn("direct", direct, runtime, store=store).result

    assert answer.renderer is named.renderer
    assert answer.banners == named.banners
    assert answer.clarify_kind == named.clarify_kind
