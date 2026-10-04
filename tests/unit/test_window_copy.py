"""What the window shows for change rows, refusals, periods, and the recorded demo."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from financial_analyst_agent.answer_notes import FISCAL_Q4_GAP_BANNER, period_notes
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
from financial_analyst_agent.runtime import DemoCompleter, _companies_from_query
from financial_analyst_agent.universe import allowed_industry_names, load_universe_snapshot


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

    assert period_notes("Microsoft revenue last 3 quarters", spec) == []
    assert FISCAL_Q4_GAP_BANNER in period_notes("Microsoft revenue", gap)
    named = period_notes("What was Microsoft revenue in Q3 2024?", AnalysisSpec())
    assert named and "Q3 2024" in named[0] and "latest quarter" in named[0]
    assert period_notes("Microsoft revenue for fiscal 2025", AnalysisSpec())


def test_recorded_planner_knows_every_recorded_company_in_the_order_named() -> None:
    plan = DemoCompleter().complete("Compare Eli Lilly and Merck net margins")

    assert plan.companies == ("LLY", "MRK")
    assert _companies_from_query("compare apple and microsoft") == ["Apple", "Microsoft"]
    assert _companies_from_query("an algorithm for amdocs") == []


def test_recorded_planner_sends_how_could_ai_questions_to_explain() -> None:
    plan = DemoCompleter().complete("How could AI change bank underwriting?")

    assert plan.intent.value == "explain"


def test_industry_names_are_not_repeated_in_another_case() -> None:
    names = allowed_industry_names(load_universe_snapshot())

    folded = [name.casefold() for name in names]
    assert len(folded) == len(set(folded))
