"""Display records the answer card draws: change chips, cell evidence, headlines."""

from datetime import date
from decimal import Decimal

import pytest

from financial_analyst_agent.contracts import (
    ComponentProvenance,
    Intent,
    RendererKind,
    TableRow,
    TurnResult,
)
from financial_analyst_agent.graph.analysis_spec import (
    AnalysisSpec,
    PeriodSelection,
    RankedSet,
    ResolvedCompany,
)
from financial_analyst_agent.presentation import present_turn, spec_chip_edits

MSFT = {"company_name": "Microsoft Corporation", "ticker": "MSFT", "cik": "0000789019"}
AAPL = {"company_name": "Apple Inc.", "ticker": "AAPL", "cik": "0000320193"}


def _part(value: str, start: date, end: date, *, metric: str = "revenue") -> ComponentProvenance:
    return ComponentProvenance(
        metric=metric,
        value=Decimal(value),
        start_date=start,
        end_date=end,
        form="10-Q",
        accession_number="0000789019-26-000001",
        taxonomy="us-gaap",
        concept="Revenues",
        source_url="https://www.sec.gov/a.htm",
        source="sec_xbrl",
    )


def _fact(
    value: str = "1177",
    *,
    metric: str = "revenue",
    year_earlier: str | None = "1000",
    concept: str = "Revenues",
    end: date = date(2026, 3, 31),
    **extra: object,
) -> TableRow:
    start = date(end.year, end.month - 2, 1)
    return TableRow(
        **MSFT,
        metric=metric,
        value=Decimal(value),
        start_date=start,
        end_date=end,
        form="10-Q",
        accession_number="0000789019-26-000001",
        taxonomy="us-gaap",
        concept=concept,
        source_url="https://www.sec.gov/a.htm",
        year_earlier=(
            _part(
                year_earlier,
                date(end.year - 1, start.month, 1),
                date(end.year - 1, end.month, end.day),
                metric=metric,
            )
            if year_earlier is not None
            else None
        ),
        **extra,  # type: ignore[arg-type]
    )


def _lookup(row: TableRow, prior: list[TableRow] | None = None) -> TurnResult:
    return TurnResult(
        intent=Intent.LOOKUP,
        renderer=RendererKind.TABLE,
        tool_traces=[],
        table_rows=[row],
        prior_quarter_rows=prior or [],
    )


def test_fact_card_change_chips_read_the_comparative_and_the_prior_quarter() -> None:
    prior = _fact("1084", year_earlier=None, end=date(2025, 12, 31))
    card = present_turn(_lookup(_fact(), [prior])).fact_card
    assert card is not None
    assert [chip.label for chip in card.changes] == ["▲17.7% YoY", "▲8.6% QoQ"]
    assert [chip.direction for chip in card.changes] == ["up", "up"]
    assert "Jan 1, 2025 – Mar 31, 2025" in card.changes[0].title


def test_fact_card_change_chip_falls_and_skips_what_is_not_meaningful() -> None:
    # A fall reads down; a base at or below zero has no percent change.
    falling = present_turn(_lookup(_fact("900"))).fact_card
    assert falling is not None
    assert [chip.label for chip in falling.changes] == ["▼10.0% YoY"]
    assert falling.changes[0].direction == "down"
    from_loss = present_turn(_lookup(_fact("50", year_earlier="-20"))).fact_card
    assert from_loss is not None and from_loss.changes == ()
    bare = present_turn(_lookup(_fact(year_earlier=None))).fact_card
    assert bare is not None and bare.changes == ()


def test_with_no_comparative_the_year_over_year_chip_reads_the_quarter_as_first_filed() -> None:
    # A balance sheet's comparative is the fiscal year-end, so the year-earlier
    # quarter comes from its own filing (ADR 0009), and the chip says so.
    first_filed = _fact("1000", year_earlier=None, end=date(2025, 3, 31))
    result = _lookup(_fact(year_earlier=None)).model_copy(
        update={"year_earlier_rows": [first_filed]}
    )
    card = present_turn(result).fact_card
    assert card is not None
    assert [chip.label for chip in card.changes] == ["▲17.7% YoY"]
    assert "as first filed in 10-Q" in card.changes[0].title
    assert "reports no year-earlier figure" in card.changes[0].title


def test_a_comparative_comes_before_the_quarter_as_first_filed() -> None:
    first_filed = _fact("1100", year_earlier=None, end=date(2025, 3, 31))
    result = _lookup(_fact()).model_copy(update={"year_earlier_rows": [first_filed]})
    card = present_turn(result).fact_card
    assert card is not None
    assert [chip.label for chip in card.changes] == ["▲17.7% YoY"]
    assert "reports it" in card.changes[0].title


def test_fact_card_margin_changes_in_points() -> None:
    row = _fact("0.3", metric="net_margin", year_earlier="0.25", components=[])
    card = present_turn(_lookup(row)).fact_card
    assert card is not None
    assert [chip.label for chip in card.changes] == ["▲5.0 pts YoY"]


def test_fact_card_names_its_kind_and_shortens_a_long_concept() -> None:
    long = (
        "IncomeLossFromContinuingOperationsBeforeIncomeTaxes"
        "ExtraordinaryItemsNoncontrollingInterest"
    )
    card = present_turn(_lookup(_fact(concept=long))).fact_card
    assert card is not None
    assert card.kind_label == "Quarterly fact"
    assert card.concept == long
    assert card.concept_short.endswith("…")
    assert len(card.concept_short) <= 30
    assert long.startswith(card.concept_short[:-1])
    plain = present_turn(_lookup(_fact())).fact_card
    assert plain is not None and plain.concept_short == "Revenues"


def test_calculated_fact_card_says_calculated() -> None:
    row = TableRow(
        **MSFT,
        metric="net_margin",
        value=Decimal("0.36"),
        start_date=date(2026, 1, 1),
        end_date=date(2026, 3, 31),
        components=[
            _part("25", date(2026, 1, 1), date(2026, 3, 31), metric="net_income"),
            _part("70", date(2026, 1, 1), date(2026, 3, 31), metric="revenue"),
        ],
    )
    card = present_turn(_lookup(row)).fact_card
    assert card is not None
    assert card.kind_label == "Calculated"


def _series(company: dict[str, str], values: list[str]) -> list[TableRow]:
    ends = [date(2025, 9, 30), date(2025, 12, 31), date(2026, 3, 31)]
    return [
        TableRow(
            **company,
            metric="revenue",
            value=Decimal(value),
            start_date=date(end.year, end.month - 2, 1),
            end_date=end,
            form="10-Q",
            accession_number=f"{company['cik']}-{index}",
            concept="Revenues",
            source_url="https://www.sec.gov/a.htm",
        )
        for index, (end, value) in enumerate(zip(ends, values, strict=True))
    ]


def test_table_cells_and_chart_points_carry_their_evidence_index() -> None:
    rows = [*_series(MSFT, ["70", "80", "90"]), *_series(AAPL, ["95", "140", "100"])]
    result = TurnResult(
        intent=Intent.COMPARE, renderer=RendererKind.TABLE, tool_traces=[], table_rows=rows
    )
    presented = present_turn(result)
    table = presented.table
    assert table is not None
    value = table.keys.index("value:revenue")
    for row_text, row_evidence in zip(table.rows, table.evidence, strict=True):
        index = row_evidence[value]
        assert index is not None
        item = presented.evidence[index]
        assert item.amount == row_text[value]
        assert item.company_name in row_text
    # The inspector lists sources in the table's reading order.
    cells = [row[value] for row in table.evidence]
    assert cells == sorted(cells)
    chart = presented.chart
    assert chart is not None and chart.kind == "line"
    assert chart.series_labels == ("MSFT", "AAPL")
    latest = chart.evidence[-1]["Apple Inc."]
    assert presented.evidence[latest].amount == chart.amounts[-1]["Apple Inc."]


def test_table_raw_cells_keep_exact_amounts() -> None:
    rows = _series(MSFT, ["77673000000.5", "80", "90"])
    table = present_turn(
        TurnResult(
            intent=Intent.LOOKUP, renderer=RendererKind.TABLE, tool_traces=[], table_rows=rows
        )
    ).table
    assert table is not None
    value = next(i for i, key in enumerate(table.keys) if key.startswith("value"))
    assert "77673000000.5" in [row[value] for row in table.raw]
    end = table.keys.index("end_date")
    assert table.raw[-1][end] == "2025-09-30"


def test_bars_carry_their_evidence_and_derived_mark() -> None:
    rows = [
        TableRow(
            **company,
            metric="research_and_development",
            value=Decimal(value),
            start_date=date(2026, 1, 1),
            end_date=date(2026, 3, 31),
            rank=rank,
            form="10-Q",
            accession_number=f"{company['cik']}-1",
            source_url="https://www.sec.gov/a.htm",
            derivation=derivation,
        )
        for rank, (company, value, derivation) in enumerate(
            ((AAPL, "8042000000", None), (MSFT, "8197000000", "Fiscal year minus nine months")),
            start=1,
        )
    ]
    presented = present_turn(
        TurnResult(
            intent=Intent.RANK_AND_LOOKUP,
            renderer=RendererKind.TABLE,
            tool_traces=[],
            table_rows=rows,
        )
    )
    chart = presented.chart
    assert chart is not None
    assert [record["Derived"] for record in chart.records] == [False, True]
    for record in chart.records:
        item = presented.evidence[int(str(record["Evidence"]))]
        assert item.ticker in str(record["Company"])


def test_ranking_and_comparison_get_a_headline() -> None:
    rows = [
        TableRow(
            **company,
            metric="research_and_development",
            value=Decimal(value),
            start_date=date(2026, 1, 1),
            end_date=date(2026, 3, 31),
            rank=rank,
        )
        for rank, (company, value) in enumerate(
            ((AAPL, "8042000000"), (MSFT, "9197000000")), start=1
        )
    ]
    ranked = present_turn(
        TurnResult(
            intent=Intent.RANK_AND_LOOKUP,
            renderer=RendererKind.TABLE,
            tool_traces=[],
            table_rows=rows,
        )
    )
    assert ranked.headline == (
        "Of these 2 companies, Microsoft reported the most research and development, "
        "$9.20 B, and Apple the least, $8.04 B, in the quarter ended Mar 31, 2026."
    )
    compared = present_turn(
        TurnResult(
            intent=Intent.COMPARE,
            renderer=RendererKind.TABLE,
            tool_traces=[],
            table_rows=[row.model_copy(update={"rank": None}) for row in rows],
        )
    )
    assert compared.headline == (
        "Microsoft's research and development was $9.20 B, ahead of Apple's $8.04 B, "
        "in the quarter ended Mar 31, 2026."
    )


def test_spec_chip_edits_say_the_follow_up_each_chip_sends() -> None:
    spec = AnalysisSpec(
        companies=(
            ResolvedCompany(cik="", name="Microsoft Corporation", ticker="MSFT", query="Microsoft"),
            ResolvedCompany(cik="", name="Apple Inc.", ticker="AAPL", query="Apple"),
        ),
        constituents=None,
        metrics=("revenue", "net_income"),
        periods=PeriodSelection(kind="last_n_quarters", count=4),
        operations=("year_over_year",),
    )
    edits = spec_chip_edits(spec)
    assert [(edit.label, edit.remove) for edit in edits] == [
        ("MSFT", "remove Microsoft"),
        ("AAPL", "remove Apple"),
        ("Revenue", "drop revenue"),
        ("Net income", "drop net income"),
        ("Last 4 quarters", "latest quarter"),
        ("Year over year", "remove year over year"),
    ]
    alone = AnalysisSpec(
        companies=(
            ResolvedCompany(cik="", name="Microsoft Corporation", ticker="MSFT", query="msft"),
        ),
        constituents=None,
        metrics=("revenue",),
        periods=PeriodSelection(kind="latest_quarter"),
        operations=(),
    )
    # The last company or metric has no ×: removing it would leave nothing to
    # show, and the chip says so on hover. The latest quarter has nothing to undo.
    edits = spec_chip_edits(alone)
    assert all(edit.remove is None for edit in edits)
    assert [edit.keep for edit in edits] == [
        "The only company here. Name another to look at instead, or start over.",
        "The only metric here. Name another to show instead, or start over.",
        None,
    ]


def test_a_ranking_chip_keeps_its_period_and_says_why_it_has_no_remove() -> None:
    spec = AnalysisSpec(
        companies=(),
        constituents=RankedSet(limit=5, industry="banks"),
        metrics=("net_income",),
        periods=PeriodSelection(kind="last_n_quarters", count=4),
        operations=(),
    )
    edits = spec_chip_edits(spec)
    assert [(edit.label, edit.remove) for edit in edits] == [
        ("Top 5 banks", None),
        ("Net income", None),
        # A ranking shows each company's latest quarter, whatever was asked.
        ("Latest quarter", None),
    ]
    assert edits[0].keep is not None and "ranking" in edits[0].keep


def test_quick_actions_offer_follow_ups_the_planner_reads() -> None:
    from financial_analyst_agent.presentation import chip_quick_actions

    spec = AnalysisSpec(
        companies=(
            ResolvedCompany(cik="", name="Microsoft Corporation", ticker="MSFT", query="Microsoft"),
        ),
        constituents=None,
        metrics=("revenue",),
        periods=PeriodSelection(kind="latest_quarter"),
        operations=(),
    )
    actions = chip_quick_actions(spec)
    assert [action.message for action in actions["company"]][:2] == ["add Apple", "add Alphabet"]
    assert "add revenue" not in [action.message for action in actions["metric"]]
    assert [action.message for action in actions["period"]] == [
        "make that the last four quarters",
        "show year-over-year",
    ]


def test_a_lone_recorded_fact_carries_both_changes() -> None:
    from financial_analyst_agent.runtime import recorded_runtime
    from financial_analyst_agent.turn import run_turn

    result = run_turn("What was Microsoft's latest quarterly pretax income?", recorded_runtime())
    card = present_turn(result).fact_card
    assert card is not None
    assert [chip.label for chip in card.changes] == ["▲35.0% YoY", "▲12.0% QoQ"]


def test_an_overview_says_so() -> None:
    rows = _series(MSFT, ["70", "80", "90"])
    result = TurnResult(
        intent=Intent.LOOKUP,
        renderer=RendererKind.TABLE,
        tool_traces=[],
        table_rows=rows[-1:],
        trend_rows=rows,
    )
    assert present_turn(result).intent_label == "Overview"


def _change(company: dict[str, str], value: str, end: date, year_earlier: str) -> TableRow:
    start = date(end.year, end.month - 2, 1)
    before = _part(
        year_earlier, date(end.year - 1, start.month, 1), date(end.year - 1, end.month, end.day)
    )
    after = _part(str(Decimal(year_earlier) + Decimal(value)), start, end)
    return TableRow(
        **company,
        metric="revenue",
        value=Decimal(value),
        comparison="year_over_year",
        start_date=start,
        end_date=end,
        form="10-Q",
        accession_number=f"{company['cik']}-{end.isoformat()}",
        components=[before, after],
    )


def _compare(rows: list[TableRow]) -> TurnResult:
    return TurnResult(
        intent=Intent.COMPARE, renderer=RendererKind.TABLE, tool_traces=[], table_rows=rows
    )


def test_a_trend_line_keeps_a_missing_quarter_as_a_gap_with_an_empty_amount() -> None:
    rows = [*_series(MSFT, ["70", "80", "90"]), *_series(AAPL, ["95", "140", "100"])]
    rows[-1] = rows[-1].model_copy(update={"value": None, "reason": "missing_fact"})
    chart = present_turn(_compare(rows)).chart
    assert chart is not None and chart.kind == "line" and chart.title == "Trend"
    assert chart.records == (
        {"Period": "2025-09-30", "Microsoft Corporation": 70.0, "Apple Inc.": 95.0},
        {"Period": "2025-12-31", "Microsoft Corporation": 80.0, "Apple Inc.": 140.0},
        {"Period": "2026-03-31", "Microsoft Corporation": 90.0, "Apple Inc.": None},
    )
    assert chart.period_labels == ("Sep 30, 2025", "Dec 31, 2025", "Mar 31, 2026")
    assert chart.series == ("Microsoft Corporation", "Apple Inc.")
    assert chart.amounts == (
        {"Microsoft Corporation": "$70", "Apple Inc.": "$95"},
        {"Microsoft Corporation": "$80", "Apple Inc.": "$140"},
        {"Microsoft Corporation": "$90", "Apple Inc.": ""},
    )
    assert chart.metric_label == "Revenue" and chart.value_kind == "usd"


def test_a_growth_line_leaves_out_the_amount_of_a_change_with_no_percent() -> None:
    ends = [date(2025, 12, 31), date(2026, 3, 31)]
    rows = [
        *_series(MSFT, ["70", "80", "90"]),
        *_series(AAPL, ["95", "140", "100"]),
        _change(MSFT, "10", ends[0], "70"),
        _change(MSFT, "20", ends[1], "70"),
        _change(AAPL, "15", ends[0], "80"),
        # From a year-earlier loss, the change has no percent: a gap, not a point.
        _change(AAPL, "5", ends[1], "-10"),
    ]
    chart = present_turn(_compare(rows)).chart
    assert chart is not None and chart.kind == "line" and chart.title == "Growth"
    assert [record["Period"] for record in chart.records] == ["2025-12-31", "2026-03-31"]
    assert chart.records[0]["Microsoft Corporation"] == pytest.approx(0.143)
    assert chart.records[0]["Apple Inc."] == pytest.approx(0.188)
    assert chart.records[1]["Microsoft Corporation"] == pytest.approx(0.286)
    assert chart.records[1]["Apple Inc."] is None
    assert chart.period_labels == ("Dec 31, 2025", "Mar 31, 2026")
    assert chart.series == ("Microsoft Corporation", "Apple Inc.")
    assert chart.amounts == (
        {"Microsoft Corporation": "+14.3%", "Apple Inc.": "+18.8%"},
        {"Microsoft Corporation": "+28.6%"},
    )
    assert chart.series_labels == ("MSFT", "AAPL")
    assert chart.caption == (
        "YoY growth in revenue, quarter by quarter; the table lists the amounts."
    )
    assert chart.metric_label == "Revenue growth, YoY" and chart.value_kind == "percent"
