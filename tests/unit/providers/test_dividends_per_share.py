"""Dividends per share: paid before declared, and a quarter with none declared said so."""

from datetime import date
from decimal import Decimal
from typing import Any

import pytest

from financial_analyst_agent.domain.errors import PerShareNotDerivableError
from financial_analyst_agent.services.metric_catalog import get_concept_candidates, parse_metric
from sec_fixtures import fixture_lookup


def test_the_dividend_paid_comes_before_the_one_declared() -> None:
    candidates = get_concept_candidates(parse_metric("dividends_per_share"))
    concepts = [concept for _, concept in candidates]

    assert concepts.index("CommonStockDividendsPerShareCashPaid") < concepts.index(
        "CommonStockDividendsPerShareDeclared"
    )


def test_a_quarter_after_the_year_s_dividend_was_declared_is_not_zero() -> None:
    # Walmart declares the year's dividend in its first quarter; the second
    # quarter's declared $0.00 is not a dividend cut.
    lookup = fixture_lookup("WMT")

    with pytest.raises(PerShareNotDerivableError):
        lookup.get_financials("WMT", "dividends_per_share", report_date=date(2026, 7, 31))
    first = lookup.get_financials("WMT", "dividends_per_share", report_date=date(2026, 4, 30))
    assert first.value == Decimal("0.99")


def test_a_quarter_with_no_dividend_says_so_without_guessing_why() -> None:
    from financial_analyst_agent.domain.errors import NoDividendThisQuarterError
    from financial_analyst_agent.presentation import format_reason
    from financial_analyst_agent.turn import reason_for

    lookup = fixture_lookup("WMT")
    with pytest.raises(NoDividendThisQuarterError) as raised:
        lookup.get_financials("WMT", "dividends_per_share", report_date=date(2026, 7, 31))

    # The filing reads the same for a year's dividend declared at once and for
    # a suspension, so neither "reported for the year" nor "declared earlier".
    assert format_reason(reason_for(raised.value)) == "No dividend declared this quarter"
    assert "declared earlier in the fiscal year" in str(raised.value)


def _window(*cells: tuple[str, date], beside: list[Any] | None = None) -> tuple[str, ...]:
    """The banners on a table of each company's dividend per share for its quarters."""
    from financial_analyst_agent.contracts import Intent, RendererKind, TurnResult
    from financial_analyst_agent.presentation import present_turn
    from financial_analyst_agent.turn import compare_metrics

    lookup = fixture_lookup(*{ticker for ticker, _ in cells})
    rows = [
        row
        for ticker, end in cells
        for row in compare_metrics(lookup, [ticker], "dividends_per_share", report_date=end)
    ]
    # An empty cell carries only the query; the turn names it from the resolved
    # company (spec_turn._fill_identity), as here.
    named = {row.ticker: row for row in rows if row.cik}
    rows = [
        row
        if row.cik
        else row.model_copy(
            update={
                "company_name": named[row.company_name].company_name,
                "ticker": row.company_name,
                "cik": named[row.company_name].cik,
            }
        )
        for row in rows
    ]
    result = TurnResult(
        intent=Intent.LOOKUP,
        tool_traces=[],
        renderer=RendererKind.TABLE,
        table_rows=[*rows, *(beside or [])],
    )
    return present_turn(result).banners


def test_a_dividend_declared_before_a_quarter_with_none_may_cover_the_year() -> None:
    banners = _window(("WMT", date(2026, 4, 30)), ("WMT", date(2026, 7, 31)))

    (note,) = [banner for banner in banners if "whole year" in banner]
    assert note.startswith("Walmart's $0.99 dividend per share for the quarter ended Apr 30, 2026")
    assert "none was declared in the quarter after" in note
    # One company: nothing to set it beside.
    assert "other companies" not in note


def test_beside_another_company_s_quarters_the_year_s_dividend_is_not_one_quarter_s() -> None:
    from financial_analyst_agent.contracts import TableRow

    apple = [
        TableRow(
            company_name="Apple Inc.",
            ticker="AAPL",
            cik="0000320193",
            metric="dividends_per_share",
            value=Decimal("0.26"),
            start_date=start,
            end_date=end,
        )
        for start, end in (
            (date(2025, 12, 28), date(2026, 3, 28)),
            (date(2026, 3, 29), date(2026, 6, 27)),
        )
    ]
    banners = _window(("WMT", date(2026, 4, 30)), ("WMT", date(2026, 7, 31)), beside=apple)

    (note,) = [banner for banner in banners if "whole year" in banner]
    assert "up to four quarters' worth, not one" in note


def test_a_lone_declared_quarter_says_nothing_it_cannot_see() -> None:
    # Without the quarter after it, the window shows no pattern.
    assert not [b for b in _window(("WMT", date(2026, 4, 30))) if "whole year" in b]
