"""A year-over-year change reads both levels from the newer filing (comparative first)."""

from datetime import date
from decimal import Decimal

from financial_analyst_agent.contracts import Intent, RendererKind, TableRow, TurnResult
from financial_analyst_agent.graph.spec_turn import across_period_change_rows
from financial_analyst_agent.presentation import change_percent, present_turn
from financial_analyst_agent.turn import _table_row_from_fact
from sec_fixtures import fixture_lookup


def _rows(ticker: str, metric: str, *ends: date) -> list[TableRow]:
    lookup = fixture_lookup(ticker)
    return [
        _table_row_from_fact(lookup.get_financials(ticker, metric, report_date=end))
        for end in ends
    ]


def _yoy(rows: list[TableRow], end: date, *, sequential: bool = True) -> TableRow:
    (change,) = [
        row
        for row in across_period_change_rows(rows, sequential=sequential)
        if row.comparison == "year_over_year" and row.end_date == end
    ]
    return change


def _present(rows: list[TableRow], *, sequential: bool = True) -> list[str]:
    changes = across_period_change_rows(rows, sequential=sequential)
    result = TurnResult(
        intent=Intent.LOOKUP,
        tool_traces=[],
        renderer=RendererKind.TABLE,
        table_rows=[*rows, *changes],
    )
    return list(present_turn(result).banners)


def test_eps_across_nvidia_s_split_compares_with_the_restated_comparative() -> None:
    # $0.76 against $5.98 first filed read -87.3%; the same 10-Q reports the
    # year-earlier quarter as $0.60 after the ten-for-one split.
    rows = _rows("NVDA", "eps_diluted", date(2025, 4, 27), date(2024, 4, 28))

    change = _yoy(rows, date(2025, 4, 27))

    assert change_percent(change) == Decimal("26.7")
    prior, current = change.components
    assert prior.value == Decimal("0.6")
    assert prior.accession_number == current.accession_number == "0001045810-25-000116"


def test_a_split_inside_the_window_is_said_and_drops_the_quarter_over_quarter_change() -> None:
    # Chipotle's fixture reports no split ratio, so its levels stay as first filed
    # (NVIDIA's are put on the later basis: test_split_adjusted_per_share).
    ends = (date(2024, 6, 30), date(2024, 3, 31))
    rows = _rows("CMG", "eps_diluted", *ends)

    changes = across_period_change_rows(rows)
    banners = _present(rows)

    assert not [row for row in changes if row.comparison == "sequential"]
    assert any("share split" in banner and "Mar 31, 2024" in banner for banner in banners)


def test_chipotle_s_eps_grows_on_the_restated_year_earlier_figure() -> None:
    rows = _rows("CMG", "eps_diluted", date(2025, 3, 31), date(2024, 3, 31))

    assert change_percent(_yoy(rows, date(2025, 3, 31))) == Decimal("7.7")


def test_a_restated_year_earlier_revenue_is_the_base_and_the_note_says_so() -> None:
    # Bank of America's 10-Q restates the year-earlier quarter's revenue from
    # $26.46 B to $27.44 B: +15.0%, not the +19.3% against the figure first filed.
    rows = _rows("BAC", "revenue", date(2026, 6, 30), date(2025, 6, 30))

    assert change_percent(_yoy(rows, date(2026, 6, 30))) == Decimal("15.0")
    assert any("restated" in banner and "Jun 30, 2025" in banner for banner in _present(rows))


def test_year_over_year_alone_needs_no_year_earlier_row_in_the_window() -> None:
    rows = _rows("BAC", "revenue", date(2026, 6, 30))

    change = _yoy(rows, date(2026, 6, 30), sequential=False)

    assert change.components[0].value == Decimal("27443000000")
    # Without year over year asked for, the window's own rows decide.
    assert not across_period_change_rows(rows)


def test_without_a_comparative_the_year_earlier_row_is_the_base() -> None:
    rows = _rows("BAC", "revenue", date(2026, 6, 30), date(2025, 6, 30))
    current = rows[0].model_copy(update={"year_earlier": None})

    change = _yoy([current, rows[1]], date(2026, 6, 30))

    assert change.components[0].value == Decimal("26463000000")
