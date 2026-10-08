"""A per-share level filed before a stock split is shown on the basis after it (ADR 0009)."""

from datetime import date
from decimal import Decimal

from financial_analyst_agent.contracts import Intent, RendererKind, TableRow, TurnResult
from financial_analyst_agent.domain.enums import Metric
from financial_analyst_agent.domain.models import (
    DerivationPart,
    FactRecord,
    FinancialFact,
    SplitAdjustment,
)
from financial_analyst_agent.graph.spec_turn import across_period_change_rows
from financial_analyst_agent.presentation import (
    format_metric_value,
    present_turn,
    split_adjusted_banners,
)
from financial_analyst_agent.services.stock_splits import on_latest_basis, reported_splits
from financial_analyst_agent.turn import _table_row_from_fact
from sec_fixtures import fixture_lookup

_EPS = "EarningsPerShareDiluted"
_RATIO = "StockholdersEquityNoteStockSplitConversionRatio1"


def _rows(ticker: str, metric: str, *ends: date) -> list[TableRow]:
    lookup = fixture_lookup(ticker)
    return [
        _table_row_from_fact(lookup.get_financials(ticker, metric, report_date=end)) for end in ends
    ]


def _present(rows: list[TableRow]) -> tuple[list[str], list[TableRow]]:
    changes = across_period_change_rows(rows)
    result = TurnResult(
        intent=Intent.LOOKUP,
        tool_traces=[],
        renderer=RendererKind.TABLE,
        table_rows=[*rows, *changes],
    )
    presentation = present_turn(result)
    return list(presentation.banners), changes


def test_nvidia_s_eps_before_the_split_is_on_the_later_basis() -> None:
    (row,) = _rows("NVDA", "eps_diluted", date(2024, 4, 28))

    # $5.98 over 10, the quotient: NVIDIA restates it as $0.60, within rounding.
    assert row.value == Decimal("0.598")
    assert format_metric_value("eps_diluted", row.value) == "$0.598"
    # The evidence keeps the May 2024 10-Q that first reported $5.98.
    assert row.accession_number == "0001045810-24-000124"
    assert row.split_adjustment is not None
    assert row.split_adjustment.label == (
        "$5.98 as first filed, ÷ 10 for the ten-for-one split of June 2024"
    )


def test_a_quarter_after_the_split_is_as_filed() -> None:
    (row,) = _rows("NVDA", "eps_diluted", date(2024, 7, 28))

    assert row.value == Decimal("0.67")
    assert row.split_adjustment is None


def test_an_adjusted_split_has_no_note_and_a_quarter_over_quarter_change() -> None:
    rows = _rows("NVDA", "eps_diluted", date(2024, 7, 28), date(2024, 4, 28))

    banners, changes = _present(rows)

    assert not any("share split" in banner for banner in banners)
    assert any(
        "Apr 28, 2024" in banner and "ten-for-one split of June 2024" in banner
        for banner in banners
    )
    (sequential,) = [row for row in changes if row.comparison == "sequential"]
    assert sequential.value == Decimal("0.072")


def test_the_inspector_shows_the_figure_as_first_filed_and_the_ratio() -> None:
    rows = _rows("NVDA", "eps_diluted", date(2024, 4, 28))
    result = TurnResult(
        intent=Intent.LOOKUP, tool_traces=[], renderer=RendererKind.TABLE, table_rows=rows
    )

    rules = [item.selection_rule for item in present_turn(result).evidence]

    assert any("$5.98 as first filed, ÷ 10 for the ten-for-one split" in rule for rule in rules)


def test_dividends_per_share_are_adjusted_too() -> None:
    (row,) = _rows("NVDA", "dividends_per_share", date(2024, 4, 28))

    assert row.value == Decimal("0.004")


def test_weighted_diluted_shares_are_on_the_same_basis() -> None:
    # So no split shows between two quarters' share counts.
    lookup = fixture_lookup("NVDA")
    shares = lookup.get_financials("NVDA", "eps_diluted", report_date=date(2024, 4, 28))

    after = lookup.get_financials("NVDA", "eps_diluted", report_date=date(2024, 7, 28))
    assert shares.diluted_shares is not None and after.diluted_shares is not None
    assert abs(shares.diluted_shares / after.diluted_shares - 1) < Decimal("0.1")


# --- Fake facts -------------------------------------------------------------------


def _record(
    concept: str,
    value: str,
    end: date,
    filed: date,
    *,
    start: date | None = None,
    accession: str | None = None,
    unit: str = "USD/shares",
) -> FactRecord:
    return FactRecord(
        accession_number=accession or f"acc-{filed.isoformat()}",
        start_date=start,
        end_date=end,
        form="10-Q",
        unit=unit,
        value=Decimal(value),
        concept=concept,
        taxonomy="us-gaap",
        filed_date=filed,
    )


def _ratio(value: str, end: date, filed: date) -> FactRecord:
    return _record(_RATIO, value, end, filed, unit="pure")


def _fact(value: str, start: date, end: date, filed: date) -> FinancialFact:
    return FinancialFact(
        company_name="Example",
        ticker="EX",
        cik="0000000001",
        metric=Metric.EPS_DILUTED,
        value=Decimal(value),
        currency="USD/shares",
        start_date=start,
        end_date=end,
        filed_date=filed,
        form="10-Q",
        accession_number=f"acc-{filed.isoformat()}",
        taxonomy="us-gaap",
        concept=_EPS,
        source_url="https://www.sec.gov/example",
    )


_TWO_SPLITS = (
    _ratio("4", date(2021, 6, 3), date(2021, 8, 20)),
    _ratio("4", date(2021, 7, 19), date(2022, 3, 18)),
    _ratio("10", date(2024, 5, 31), date(2024, 8, 28)),
    _ratio("10", date(2024, 6, 30), date(2025, 5, 28)),
)


def test_reports_of_one_ratio_within_ninety_days_are_one_split() -> None:
    splits = reported_splits(list(_TWO_SPLITS))

    assert [(split.ratio, split.effective) for split in splits] == [
        (Decimal("4"), date(2021, 6, 3)),
        (Decimal("10"), date(2024, 5, 31)),
    ]


def test_a_quarter_before_both_splits_is_divided_by_forty() -> None:
    fact = _fact("8.00", date(2021, 2, 1), date(2021, 5, 2), date(2021, 5, 26))

    adjusted = on_latest_basis(fact, reported_splits(list(_TWO_SPLITS)), [])

    assert adjusted.value == Decimal("0.2")
    assert adjusted.split_adjustment is not None
    assert adjusted.split_adjustment.label == (
        "$8.00 as first filed, ÷ 40 for the four-for-one split of July 2021 "
        "and the ten-for-one split of June 2024"
    )


def test_a_reverse_split_multiplies() -> None:
    splits = reported_splits([_ratio("0.1", date(2024, 5, 31), date(2024, 8, 28))])
    fact = _fact("-0.12", date(2024, 1, 1), date(2024, 3, 31), date(2024, 5, 1))

    adjusted = on_latest_basis(fact, splits, [])

    assert adjusted.value == Decimal("-1.2")
    assert adjusted.split_adjustment is not None
    assert adjusted.split_adjustment.label == (
        "-$0.12 as first filed, × 10 for the one-for-ten reverse split of May 2024"
    )


def test_a_disagreeing_restated_figure_leaves_the_series_as_first_filed() -> None:
    splits = reported_splits(list(_TWO_SPLITS[2:]))
    start, end = date(2024, 1, 29), date(2024, 4, 28)
    fact = _fact("5.98", start, end, date(2024, 5, 29))
    records = [
        _record(_EPS, "5.98", end, date(2024, 5, 29), start=start),
        # A later 10-Q reports the quarter as $0.65, not $0.60: the ratio or date is misread.
        _record(_EPS, "0.65", end, date(2025, 5, 28), start=start),
    ]

    assert on_latest_basis(fact, splits, records) == fact


def test_an_agreeing_restated_figure_adjusts() -> None:
    splits = reported_splits(list(_TWO_SPLITS[2:]))
    start, end = date(2024, 1, 29), date(2024, 4, 28)
    fact = _fact("5.98", start, end, date(2024, 5, 29))
    records = [
        _record(_EPS, "5.98", end, date(2024, 5, 29), start=start),
        _record(_EPS, "0.60", end, date(2025, 5, 28), start=start),
    ]

    assert on_latest_basis(fact, splits, records).value == Decimal("0.598")


def test_only_standalone_quarters_are_cross_checked_against_their_restatement() -> None:
    splits = reported_splits(list(_TWO_SPLITS[2:]))
    start, end = date(2024, 1, 29), date(2024, 4, 28)
    fact = _fact("5.98", start, end, date(2024, 5, 29))
    nine_months = date(2023, 7, 31)
    records = [
        _record(_EPS, "5.98", end, date(2024, 5, 29), start=start),
        _record(_EPS, "0.60", end, date(2025, 5, 28), start=start),
        # Nine months on two bases that do not agree: not one quarter (70 to 110
        # days, the band fact_selector owns), so the check never reads them.
        _record(_EPS, "12.00", end, date(2024, 5, 29), start=nine_months),
        _record(_EPS, "1.50", end, date(2025, 5, 28), start=nine_months),
    ]

    assert on_latest_basis(fact, splits, records).value == Decimal("0.598")


def test_the_comparative_in_the_same_filing_takes_the_same_divisor() -> None:
    splits = reported_splits(list(_TWO_SPLITS[2:]))
    fact = _fact("5.98", date(2024, 1, 29), date(2024, 4, 28), date(2024, 5, 29))
    before = DerivationPart(
        value=Decimal("0.82"),
        start_date=date(2023, 1, 30),
        end_date=date(2023, 4, 30),
        form="10-Q",
        accession_number=fact.accession_number,
        taxonomy="us-gaap",
        concept=_EPS,
        filed_date=fact.filed_date,
        source_url=fact.source_url,
    )

    adjusted = on_latest_basis(fact.model_copy(update={"year_earlier": before}), splits, [])

    assert adjusted.year_earlier is not None
    assert adjusted.year_earlier.value == Decimal("0.082")
    assert adjusted.year_earlier.split_adjustment is not None


def test_a_fact_filed_after_the_split_is_unchanged() -> None:
    splits = reported_splits(list(_TWO_SPLITS[2:]))
    fact = _fact("0.67", date(2024, 4, 29), date(2024, 7, 28), date(2024, 8, 28))

    assert on_latest_basis(fact, splits, []) == fact


def _adjusted_eps(end: date, value: str) -> TableRow:
    return TableRow(
        company_name="NVIDIA Corporation",
        ticker="NVDA",
        cik="0001045810",
        metric="eps_diluted",
        value=Decimal(value),
        start_date=date(end.year, max(end.month - 2, 1), 1),
        end_date=end,
        split_adjustment=SplitAdjustment(
            first_filed=Decimal("5.98"),
            divisor=Decimal("10"),
            splits="the ten-for-one split of June 2024",
        ),
    )


def test_the_split_note_reads_one_quarter_in_the_singular_and_several_in_the_plural() -> None:
    assert split_adjusted_banners([_adjusted_eps(date(2024, 4, 28), "0.598")]) == [
        "NVIDIA's diluted EPS for the quarter ended Apr 28, 2024 is shown after the "
        "ten-for-one split of June 2024, as the later filings restate it: the figure as "
        "first filed ÷ 10, by the ratio the company reports. The evidence gives the figure "
        "as first filed."
    ]
    assert split_adjusted_banners(
        [_adjusted_eps(date(2024, 4, 28), "0.598"), _adjusted_eps(date(2024, 1, 28), "0.488")]
    ) == [
        "NVIDIA's diluted EPS for the quarters ended Apr 28, 2024 and Jan 28, 2024 are shown "
        "after the ten-for-one split of June 2024, as the later filings restate them: the "
        "figure as first filed ÷ 10, by the ratio the company reports. The evidence gives "
        "the figure as first filed."
    ]
