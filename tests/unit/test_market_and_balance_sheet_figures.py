"""EBITDA, return on equity, P/E and share price (ADR 0008)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from typing import Any

from financial_analyst_agent.contracts import Intent, TurnResult
from financial_analyst_agent.domain.enums import Metric
from financial_analyst_agent.domain.errors import UnsupportedQuarterlyFactError
from financial_analyst_agent.domain.models import FinancialFact
from financial_analyst_agent.presentation import (
    format_metric_value,
    long_quarter_banner,
    present_turn,
)
from financial_analyst_agent.turn import compare_metrics, market_formula_rows, snapshot_compare_rows
from helpers import FakeFacts

_QUARTER = (date(2026, 3, 29), date(2026, 6, 27))
_YEAR = (date(2025, 6, 29), date(2026, 6, 27))
_EARLIER_YEAR = (date(2025, 3, 30), date(2026, 3, 28))
_AT_END = (date(2026, 6, 27), date(2026, 6, 27))


def _fact(metric: str, value: str, period: tuple[date, date]) -> FinancialFact:
    return FinancialFact(
        company_name="Apple Inc.",
        ticker="AAPL",
        cik="0000320193",
        metric=Metric(metric),
        value=Decimal(value),
        currency="USD",
        start_date=period[0],
        end_date=period[1],
        filed_date=date(2026, 8, 1),
        form="10-Q",
        accession_number="0000320193-26-000070",
        taxonomy="us-gaap",
        concept="Concept",
        source_url="https://www.sec.gov/aapl",
    )


class _Facts(FakeFacts):
    def __init__(self, facts: dict[str, FinancialFact], dated: dict[str, FinancialFact]) -> None:
        self.facts = facts
        self.dated = dated

    def get_financials(
        self, company: str, metric: str, *, report_date: date | None = None
    ) -> FinancialFact:
        return (self.dated if report_date is not None else self.facts)[metric]


class _Ranking:
    def __init__(self, price: Decimal | None = Decimal("341.07")) -> None:
        self.member = SimpleNamespace(
            cik="0000320193",
            name="Apple Inc.",
            ticker="AAPL",
            market_cap=Decimal("5000000000000"),
            price=price,
        )

    def lookup_member(self, query: str) -> Any:
        return self.member

    def snapshot_as_of(self) -> str:
        return "2026-09-27T10:54:00+00:00"

    def snapshot_source(self) -> str:
        return "fmp_universe_snapshot"


def test_ebitda_adds_depreciation_and_amortization_to_operating_income() -> None:
    facts = _Facts(
        {
            "operating_income": _fact("operating_income", "35700000000", _QUARTER),
            "depreciation_amortization": _fact("depreciation_amortization", "3320000000", _QUARTER),
        },
        {},
    )
    (row,) = compare_metrics(facts, ["Apple"], "ebitda")
    assert row.value == Decimal("39020000000")
    assert format_metric_value("ebitda", row.value) == "$39.02 B"


def test_return_on_equity_divides_the_trailing_year_by_equity_at_its_end() -> None:
    facts = _Facts(
        {
            "net_income_ttm": _fact("net_income_ttm", "128930000000", _YEAR),
            "shareholders_equity": _fact("shareholders_equity", "107520000000", _AT_END),
        },
        {},
    )
    (row,) = compare_metrics(facts, ["Apple"], "return_on_equity")
    assert (row.start_date, row.end_date) == _YEAR
    assert format_metric_value("return_on_equity", row.value) == "119.9%"
    # A trailing year is not a long quarter.
    assert long_quarter_banner([row]) == ""


def test_return_on_equity_needs_equity_at_the_year_s_end() -> None:
    facts = _Facts(
        {
            "net_income_ttm": _fact("net_income_ttm", "128930000000", _YEAR),
            "shareholders_equity": _fact(
                "shareholders_equity", "107520000000", (date(2026, 3, 28), date(2026, 3, 28))
            ),
        },
        {},
    )
    (row,) = compare_metrics(facts, ["Apple"], "return_on_equity")
    assert row.value is None and row.reason == "period_mismatch"


def test_pe_is_the_snapshot_market_cap_over_trailing_net_income() -> None:
    facts = _Facts({"net_income_ttm": _fact("net_income_ttm", "128930000000", _YEAR)}, {})
    (row,) = market_formula_rows(facts, _Ranking(), ["Apple"], "pe_ratio")
    assert format_metric_value("pe_ratio", row.value) == "38.8x"
    market_cap, earnings = row.components
    assert (market_cap.metric, market_cap.end_date) == ("market_cap", date(2026, 9, 27))
    assert earnings.metric == "net_income_ttm"


def test_pe_is_not_meaningful_on_a_loss() -> None:
    facts = _Facts({"net_income_ttm": _fact("net_income_ttm", "-5000000000", _YEAR)}, {})
    (row,) = market_formula_rows(facts, _Ranking(), ["Apple"], "pe_ratio")
    assert row.value is None and row.reason == "not_meaningful"


def test_pe_for_a_past_period_is_not_today_s_price_over_old_earnings() -> None:
    latest = _fact("net_income_ttm", "128930000000", _YEAR)
    earlier = _fact("net_income_ttm", "120000000000", _EARLIER_YEAR)
    facts = _Facts({"net_income_ttm": latest}, {"net_income_ttm": earlier})
    (row,) = market_formula_rows(
        facts, _Ranking(), ["Apple"], "pe_ratio", report_date=_EARLIER_YEAR[1]
    )
    assert row.value is None and row.reason == "latest_period_only"
    assert row.end_date == _EARLIER_YEAR[1]


def test_share_price_comes_from_the_snapshot() -> None:
    (row,) = snapshot_compare_rows(_Ranking(), ["Apple"], "price")
    assert format_metric_value("price", row.value) == "$341.07"
    (missing,) = snapshot_compare_rows(_Ranking(price=None), ["Apple"], "price")
    assert missing.value is None and missing.reason == "missing_fact"


def test_a_balance_sheet_amount_shows_its_date_not_a_period() -> None:
    facts = _Facts({"cash": _fact("cash", "39544000000", _AT_END)}, {})
    (row,) = compare_metrics(facts, ["Apple"], "cash")
    answer = present_turn(
        TurnResult(intent=Intent.LOOKUP, tool_traces=[], renderer="table", table_rows=[row])
    )
    assert answer.fact_card is not None
    assert answer.fact_card.period_label == "Balance sheet · At Jun 27, 2026"


def test_a_derived_gross_profit_names_each_part_by_its_own_metric() -> None:
    from financial_analyst_agent.services.fiscal_periods import gross_profit_from_components
    from financial_analyst_agent.turn import _table_row_from_fact

    gross = gross_profit_from_components(
        _fact("revenue", "70530000000", _QUARTER), _fact("cost_of_revenue", "61520000000", _QUARTER)
    )

    row = _table_row_from_fact(gross)

    assert [part.metric for part in row.derived_from] == ["revenue", "cost_of_revenue"]


def test_a_sum_s_parts_are_named_by_their_own_metric_only_when_asked() -> None:
    from financial_analyst_agent.services.fiscal_periods import (
        revenue_from_components,
        sum_of_components,
    )

    interest = _fact("net_interest_income", "14000000000", _QUARTER)
    fees = _fact("noninterest_income", "11000000000", _QUARTER)
    halves = [
        _fact("depreciation_amortization", "2000000000", _QUARTER),
        _fact("depreciation_amortization", "1320000000", _QUARTER),
    ]
    gross = _fact("gross_profit", "9010000000", _QUARTER)
    cost = _fact("cost_of_revenue", "61520000000", _QUARTER)

    named = sum_of_components(Metric.REVENUE, [interest, fees], name_parts=True)
    unnamed = sum_of_components(Metric.DEPRECIATION_AMORTIZATION, halves)
    rebuilt = revenue_from_components(_fact("revenue", "70530", _QUARTER), gross, cost)

    assert named.derivation is not None and unnamed.derivation is not None
    assert rebuilt.derivation is not None
    assert [part.metric for part in named.derivation.parts] == [
        "net_interest_income",
        "noninterest_income",
    ]
    assert [part.metric for part in unnamed.derivation.parts] == [None, None]
    assert [part.metric for part in rebuilt.derivation.parts] == ["gross_profit", "cost_of_revenue"]
    # Each part keeps the fact's own provenance and any derivation of its own.
    assert named.derivation.parts[0].model_dump(exclude={"metric"}) == {
        "value": "14000000000",
        "start_date": _QUARTER[0],
        "end_date": _QUARTER[1],
        "form": "10-Q",
        "accession_number": "0000320193-26-000070",
        "taxonomy": "us-gaap",
        "concept": "Concept",
        "filed_date": date(2026, 8, 1),
        "source_url": "https://www.sec.gov/aapl",
        "derivation": None,
        "split_adjustment": None,
    }


class _FactsMissing(_Facts):
    """A facts port whose filings lack some metrics as standalone quarters."""

    def __init__(self, facts: dict[str, FinancialFact], missing: set[str]) -> None:
        super().__init__(facts, {})
        self.missing = missing

    def get_financials(
        self, company: str, metric: str, *, report_date: date | None = None
    ) -> FinancialFact:
        if metric in self.missing:
            raise UnsupportedQuarterlyFactError(
                "No directly reported standalone-quarter fact exists for metric",
                details={"metric": metric, "reason": "no_standalone_quarter"},
            )
        return super().get_financials(company, metric, report_date=report_date)


def test_a_formula_missing_a_component_names_it() -> None:
    # probe-round-3-gaps ticket 11: AMD's filings report depreciation only for the
    # fiscal year, so no quarter has EBITDA; the row says which part is missing.
    facts = _FactsMissing(
        {"operating_income": _fact("operating_income", "1990000000", _QUARTER)},
        {"depreciation_amortization"},
    )
    (row,) = compare_metrics(facts, ["Apple"], "ebitda")
    assert row.value is None and row.reason == "missing_fact"
    assert row.missing_components == ["depreciation_amortization"]


def test_a_formula_missing_every_component_names_each() -> None:
    # Merck's filings report no operating income line, and amortization only for the year.
    facts = _FactsMissing({}, {"operating_income", "depreciation_amortization"})
    (row,) = compare_metrics(facts, ["Merck"], "ebitda")
    assert row.reason == "missing_fact"
    assert row.missing_components == ["operating_income", "depreciation_amortization"]


def test_a_plain_metric_the_filings_lack_names_no_component() -> None:
    facts = _FactsMissing({}, {"revenue"})
    (row,) = compare_metrics(facts, ["Apple"], "revenue")
    assert row.reason == "missing_fact" and row.missing_components == []
