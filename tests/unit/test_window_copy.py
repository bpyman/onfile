"""What the window shows for change rows, refusals, periods, and the recorded demo."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from inspect import signature

import pytest

from financial_analyst_agent.answer_notes import (
    FISCAL_Q4_GAP_BANNER,
    YEAR_OF_QUARTERS_BANNER,
    period_notes,
)
from financial_analyst_agent.contracts import (
    ComponentProvenance,
    Intent,
    RendererKind,
    TableRow,
    ToolTrace,
    TurnResult,
)
from financial_analyst_agent.graph.analysis_spec import AnalysisSpec, PeriodSelection
from financial_analyst_agent.presentation import present_turn
from financial_analyst_agent.request_wording import read_window
from financial_analyst_agent.rules_planner import _companies_from_query
from financial_analyst_agent.runtime import DemoCompleter
from financial_analyst_agent.universe import (
    SnapshotGroups,
    allowed_industry_names,
    load_universe_snapshot,
)


def _level(end: date, value: str) -> TableRow:
    return TableRow(
        company_name="Microsoft Corporation",
        ticker="MSFT",
        cik="0000789019",
        metric="revenue",
        value=Decimal(value),
        start_date=date(end.year, end.month - 2, 1),
        end_date=end,
        form="10-Q",
        accession_number=f"acc-{end.isoformat()}",
        concept="Revenues",
        source_url="https://www.sec.gov/",
    )


def _component(row: TableRow) -> ComponentProvenance:
    assert row.value is not None and row.start_date and row.end_date
    return ComponentProvenance(
        metric=row.metric,
        value=row.value,
        start_date=row.start_date,
        end_date=row.end_date,
        form="10-Q",
        accession_number=row.accession_number or "",
        taxonomy="us-gaap",
        concept="Revenues",
        source_url="https://www.sec.gov/",
        source="sec_xbrl",
    )


def _refusal(message: str) -> str | None:
    return present_turn(
        TurnResult(
            intent=Intent.LOOKUP, renderer=RendererKind.REFUSE, message=message, tool_traces=[]
        )
    ).message


def test_change_rows_say_what_they_are_and_carry_a_sign() -> None:
    newer, older = _level(date(2026, 3, 31), "82"), _level(date(2025, 12, 31), "81")
    change = TableRow(
        company_name=newer.company_name,
        ticker=newer.ticker,
        cik=newer.cik,
        metric="revenue",
        value=Decimal("1"),
        start_date=older.start_date,
        end_date=newer.end_date,
        components=[_component(older), _component(newer)],
        comparison="sequential",
    )
    result = TurnResult(
        intent=Intent.LOOKUP,
        renderer=RendererKind.TABLE,
        table_rows=[newer, older, change],
        tool_traces=[],
    )

    presented = present_turn(result)

    assert presented.table is not None
    column = presented.table.keys.index("change:revenue")
    assert presented.table.headers[column] == "QoQ change"
    changes = [row[column] for row in presented.table.rows]
    assert changes[0].startswith("+$") and changes[1] == ""
    # The change's two components are the levels already listed: one entry each.
    labels = [item.label for item in presented.evidence]
    assert len(labels) == len(set(labels)) == 3
    # In the table's reading order: the newer quarter, its change, then the older.
    assert "quarter over quarter change" in labels[1]


def test_refusals_use_the_windows_words() -> None:
    no_metric = _refusal("Unknown metric 'unknown'. Allowed: revenue, net_income")
    assert no_metric is not None and "unknown" not in no_metric
    assert "net_income" not in (_refusal("Unknown metric 'ebitda'. Allowed: x") or "")
    assert "Name a company" in (_refusal("Analysis has no companies or ranked constituents") or "")
    assert "“microsft”" in (_refusal("Company not found for query 'microsft'") or "")
    assert _refusal("Something else entirely.") == "Something else entirely."


def test_trace_headers_name_the_company_not_its_cik() -> None:
    row = _level(date(2026, 3, 31), "82")
    result = TurnResult(
        intent=Intent.RANK_AND_LOOKUP,
        renderer=RendererKind.TABLE,
        table_rows=[row, _level(date(2025, 12, 31), "81")],
        tool_traces=[
            ToolTrace(tool="get_financials", args={"company": row.cik, "metric": "revenue"})
        ],
    )

    header = present_turn(result).traces[0].header

    # The short name the answer's notes use, not the legal name or the CIK.
    assert header.startswith("Looked up Microsoft · Revenue")
    assert row.cik not in header


def test_period_notes_flag_named_periods_and_fiscal_q4_gaps() -> None:
    spec = AnalysisSpec(
        periods=PeriodSelection(
            kind="last_n_quarters",
            count=3,
            report_dates=(date(2026, 3, 31), date(2025, 12, 31), date(2025, 9, 30)),
        )
    )
    gap = spec.model_copy(
        update={
            "periods": PeriodSelection(
                kind="last_n_quarters",
                count=2,
                report_dates=(date(2025, 9, 30), date(2025, 3, 31)),
            )
        }
    )

    message = "Microsoft revenue last 3 quarters"
    assert period_notes(message, spec, window=read_window(message)) == []
    message = "Microsoft revenue"
    assert FISCAL_Q4_GAP_BANNER in period_notes(
        message, gap, window=read_window(message)
    )
    message = "What was Microsoft revenue for the quarter ended April 2026?"
    named = period_notes(message, AnalysisSpec(), window=read_window(message))
    assert named and "April 2026" in named[0] and "latest quarter" in named[0]


def test_a_year_and_a_half_is_six_quarters_and_not_the_last_year() -> None:
    """"The last year and a half" is a counted window; the last-year banner is for four."""
    ends = (
        date(2026, 6, 30),
        date(2026, 3, 31),
        date(2025, 12, 31),
        date(2025, 9, 30),
        date(2025, 6, 30),
        date(2025, 3, 31),
    )
    six = AnalysisSpec(
        periods=PeriodSelection(kind="last_n_quarters", count=6, report_dates=ends)
    )
    four = AnalysisSpec(
        periods=PeriodSelection(kind="last_n_quarters", count=4, report_dates=ends[:4])
    )

    message = "Danaher net income the last year and a half"
    assert read_window(message).asked_quarters == 6
    assert period_notes(message, six, window=read_window(message)) == []
    message = "Danaher net income over the past year"
    assert period_notes(message, four, window=read_window(message)) == [YEAR_OF_QUARTERS_BANNER]


def test_request_wording_records_every_window_reading_used_by_notes() -> None:
    from financial_analyst_agent import request_wording

    read_window = getattr(request_wording, "read_window", None)

    assert read_window is not None
    approximate = read_window("Apple revenue over the past several months")
    assert approximate.asked_quarters == 2
    assert approximate.interpretation_notes
    assert read_window("Apple TTM revenue").trailing_year
    since = read_window("Apple revenue since 2000")
    # A "since" window names its year; how many quarters that is waits for the
    # companies' report dates, so the reading counts none.
    assert (since.since_year, since.asked_quarters) == (2000, None)
    assert not hasattr(since, "since_capped_from")
    assert (
        read_window("Apple revenue for the quarter ended April 2026").unread_named_period
        == "April 2026"
    )
    assert read_window("Apple revenue last month").sub_quarter


def test_compilation_carries_the_window_reading_and_notes_use_it() -> None:
    from financial_analyst_agent.graph.state import CompiledAnalysis
    from financial_analyst_agent.request_wording import read_window

    assert "window" in CompiledAnalysis.model_fields
    assert "window" in signature(period_notes).parameters
    reading = read_window("Apple revenue over the past several months")
    spec = AnalysisSpec(
        periods=PeriodSelection(
            kind="last_n_quarters",
            count=1,
            report_dates=(date(2026, 3, 31),),
        )
    )

    notes = period_notes("Apple revenue", spec, window=reading)

    assert any("Read “past several months” as the latest 2 quarters" in note for note in notes)
    assert "only 1 of the 2 quarters asked for" in notes[-1]


def test_recorded_planner_knows_every_recorded_company_in_the_order_named() -> None:
    plan = DemoCompleter().complete("Compare Eli Lilly and Merck net margins")

    assert plan.companies == ("LLY", "MRK")
    assert _companies_from_query("compare apple and microsoft") == ["Apple", "Microsoft"]
    assert _companies_from_query("an algorithm for amdocs") == []


def test_recorded_planner_sends_how_could_ai_questions_to_explain() -> None:
    plan = DemoCompleter().complete("How could AI change bank underwriting?")

    assert plan.intent.value == "explain"


def test_industry_names_are_not_repeated_in_another_case() -> None:
    names = allowed_industry_names(SnapshotGroups.of(load_universe_snapshot()))

    folded = [name.casefold() for name in names]
    assert len(folded) == len(set(folded))


def test_a_since_window_carries_its_year_to_the_spec_capped_at_forty() -> None:
    from financial_analyst_agent.graph.analysis_spec import MAX_QUARTERS_ASKED, SpecPatch
    from financial_analyst_agent.request_wording import bind_periods_from_message

    patch = bind_periods_from_message(SpecPatch(mode="replace"), "Apple revenue since 2000")

    periods = patch.set_periods
    assert periods is not None
    # The window is every filed quarter since 1 January 2000, at most 40 of them:
    # the cap is the listing's limit, and the quarters are chosen where the
    # company's report dates are known.
    assert (periods.kind, periods.since_year, periods.count) == (
        "last_n_quarters",
        2000,
        MAX_QUARTERS_ASKED,
    )
    assert periods.report_dates == ()


@pytest.mark.parametrize(
    "wording",
    [
        "since fiscal 2025",
        "since the start of fiscal 2025",
        "since FY2025",
        "since fiscal year 2025",
    ],
)
def test_since_a_fiscal_year_is_a_window_on_each_companys_own_fiscal_year(wording: str) -> None:
    from financial_analyst_agent.graph.analysis_spec import SpecPatch
    from financial_analyst_agent.request_wording import bind_periods_from_message

    message = f"Apple revenue {wording}"
    window = read_window(message)

    # The year is the company's fiscal year, and "fiscal 2025" is the window's
    # year rather than a named period left unread (probe-round-3-gaps ticket 06).
    assert (window.since_year, window.since_fiscal, window.asked_quarters) == (2025, True, None)
    assert window.unread_named_period is None
    periods = bind_periods_from_message(SpecPatch(mode="replace"), message).set_periods
    assert periods is not None
    assert (periods.kind, periods.since_year, periods.since_fiscal) == (
        "last_n_quarters",
        2025,
        True,
    )


def test_since_a_calendar_year_is_not_fiscal_and_its_spec_dumps_as_before() -> None:
    assert not read_window("Apple revenue since 2025").since_fiscal
    calendar = PeriodSelection(kind="last_n_quarters", count=40, since_year=2025)
    # A stored or compared spec of a calendar window does not change for the flag.
    assert "since_fiscal" not in calendar.model_dump(mode="json")
    fiscal = calendar.model_copy(update={"since_fiscal": True})
    assert fiscal.model_dump(mode="json")["since_fiscal"] is True
    assert PeriodSelection.model_validate(fiscal.model_dump(mode="json")).since_fiscal


def _since_spec(year: int, dates: tuple[date, ...]) -> AnalysisSpec:
    return AnalysisSpec(
        periods=PeriodSelection(
            kind="last_n_quarters", count=len(dates), since_year=year, report_dates=dates
        )
    )


_NINE_FROM_JUNE_2024 = (
    date(2026, 6, 27),
    date(2026, 3, 28),
    date(2025, 12, 27),
    date(2025, 9, 27),
    date(2025, 6, 28),
    date(2025, 3, 29),
    date(2024, 12, 28),
    date(2024, 9, 28),
    date(2024, 6, 29),
)


def test_a_since_window_note_counts_the_span_from_the_newest_filed_quarter() -> None:
    message = "Apple revenue since 2024"
    window = read_window(message)

    # Ten quarters ended between 1 January 2024 and 27 June 2026; the filings
    # hold nine of them, whatever today's date is.
    short = period_notes(message, _since_spec(2024, _NINE_FROM_JUNE_2024), window=window)
    assert "The filings here hold only 9 of the 10 quarters since 2024." in short
    assert not any("asked for" in note for note in short)

    whole = (*_NINE_FROM_JUNE_2024, date(2024, 3, 30))
    full = period_notes(message, _since_spec(2024, whole), window=window)
    assert not any("hold only" in note for note in full)


def test_a_since_window_over_the_cap_says_so_from_the_filed_quarters() -> None:
    message = "Apple revenue since 2015"
    notes = period_notes(
        message, _since_spec(2015, _NINE_FROM_JUNE_2024), window=read_window(message)
    )

    # Q1 2015 to Q2 2026 is 46 quarters; the window shows at most 40.
    assert (
        "Quarters since 2015 number 46; a window shows at most 40, so this asks for the "
        "latest 40." in notes
    )
    assert "The filings here hold only 9 of the 40 quarters since 2015." in notes


def test_a_since_fiscal_window_note_counts_the_span_on_the_companys_own_labels() -> None:
    message = "Apple revenue since fiscal 2015"
    # Q1 of fiscal 2015 to Q3 of fiscal 2026 is 47 quarters on Apple's labels, one
    # more than the calendar count; the listed spec carries the span as asked.
    spec = AnalysisSpec(
        periods=PeriodSelection(
            kind="last_n_quarters",
            count=9,
            since_year=2015,
            since_fiscal=True,
            report_dates=_NINE_FROM_JUNE_2024,
            asked=47,
        )
    )

    notes = period_notes(message, spec, window=read_window(message))

    assert (
        "Quarters since fiscal 2015 number 47; a window shows at most 40, so this asks for "
        "the latest 40." in notes
    )
    assert "The filings here hold only 9 of the 40 quarters since fiscal 2015." in notes
    assert not any("couldn't read" in note for note in notes)

    # Every quarter of fiscal 2025 and after is held: nothing to say.
    message = "Apple revenue since fiscal 2025"
    whole = AnalysisSpec(
        periods=PeriodSelection(
            kind="last_n_quarters",
            count=7,
            since_year=2025,
            since_fiscal=True,
            report_dates=_NINE_FROM_JUNE_2024[:7],
        )
    )
    assert period_notes(message, whole, window=read_window(message)) == []
