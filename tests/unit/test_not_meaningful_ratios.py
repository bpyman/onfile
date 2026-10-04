"""Ratios over a negative denominator are not meaningful, and say why."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from financial_analyst_agent.contracts import Intent, RendererKind, TableRow, TurnResult
from financial_analyst_agent.domain.enums import Metric
from financial_analyst_agent.domain.models import FinancialFact
from financial_analyst_agent.graph.spec_turn import _order_by_metric
from financial_analyst_agent.presentation import format_reason, present_turn
from financial_analyst_agent.turn import compare_metrics
from helpers import FakeFacts

_QUARTER = (date(2026, 4, 1), date(2026, 6, 30))
_YEAR = (date(2025, 7, 1), date(2026, 6, 30))
_AT_END = (date(2026, 6, 30), date(2026, 6, 30))


class _Facts(FakeFacts):
    def __init__(self, facts: dict[str, FinancialFact]) -> None:
        self.facts = facts

    def get_financials(
        self, company: str, metric: str, *, report_date: date | None = None
    ) -> FinancialFact:
        return self.facts[metric]


def _fact(metric: str, value: str, period: tuple[date, date]) -> FinancialFact:
    return FinancialFact(
        company_name="McDonald's Corporation",
        ticker="MCD",
        cik="0000063908",
        metric=Metric(metric),
        value=Decimal(value),
        currency="USD",
        start_date=period[0],
        end_date=period[1],
        filed_date=date(2026, 8, 1),
        form="10-Q",
        accession_number="0000063908-26-000070",
        taxonomy="us-gaap",
        concept="Concept",
        source_url="https://www.sec.gov/mcd",
    )


def _row(metric: str, numerator: tuple[str, str], denominator: tuple[str, str]) -> TableRow:
    period = _YEAR if metric == "return_on_equity" else _QUARTER
    at = _AT_END if denominator[0] == "shareholders_equity" else period
    facts = _Facts(
        {
            numerator[0]: _fact(numerator[0], numerator[1], period),
            denominator[0]: _fact(denominator[0], denominator[1], at),
        }
    )
    (row,) = compare_metrics(facts, ["McDonald's"], metric)
    return row


@pytest.mark.parametrize(
    ("metric", "numerator", "denominator", "label"),
    [
        # McDonald's equity is negative: -858.9% is not a return.
        (
            "return_on_equity",
            ("net_income_ttm", "8200000000"),
            ("shareholders_equity", "-3800000000"),
            "Not meaningful (negative equity)",
        ),
        (
            "net_margin",
            ("net_income", "-12000000"),
            ("revenue", "-250000"),
            "Not meaningful (negative revenue)",
        ),
        (
            "effective_tax_rate",
            ("income_tax_expense", "4000000"),
            ("pretax_income", "-90000000"),
            "Not meaningful (pretax loss)",
        ),
        # Aurora's -13,500% operating margin on a sliver of revenue.
        (
            "operating_margin",
            ("operating_income", "-270000000"),
            ("revenue", "2000000"),
            "Not meaningful (beyond ±1,000%)",
        ),
    ],
)
def test_a_ratio_over_a_bad_denominator_is_not_meaningful(
    metric: str, numerator: tuple[str, str], denominator: tuple[str, str], label: str
) -> None:
    row = _row(metric, numerator, denominator)

    assert row.value is None
    assert row.reason is not None and format_reason(row.reason) == label
    # The inputs stay as evidence.
    assert [component.metric for component in row.components] == [numerator[0], denominator[0]]


def test_a_ratio_over_a_sound_denominator_is_computed() -> None:
    row = _row("net_margin", ("net_income", "-12000000"), ("revenue", "250000000"))

    assert row.value == Decimal("-0.048")


def test_a_not_meaningful_ratio_never_ranks_first() -> None:
    def ranked(cik: str, rank: int, value: str | None, reason: str | None = None) -> TableRow:
        return TableRow(
            company_name=cik,
            ticker=cik,
            cik=cik,
            metric="return_on_equity",
            rank=rank,
            value=Decimal(value) if value is not None else None,
            reason=reason,
            end_date=date(2026, 6, 27),
        )

    result = TurnResult(
        intent=Intent.RANK_AND_LOOKUP,
        tool_traces=[],
        renderer=RendererKind.TABLE,
        table_rows=[
            ranked("MCD", 1, None, "negative_equity"),
            ranked("AAPL", 2, "1.2"),
            ranked("MSFT", 3, "0.35"),
        ],
    )

    ordered = _order_by_metric(result, "return_on_equity")

    assert [row.ticker for row in ordered.table_rows] == ["AAPL", "MSFT", "MCD"]
    table = present_turn(ordered).table
    assert table is not None
    assert "Not meaningful (negative equity)" in table.rows[-1]
