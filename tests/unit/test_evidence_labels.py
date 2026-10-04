"""Evidence and cards say what a figure is: derived, calculated, a change, a trailing year."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from financial_analyst_agent.contracts import (
    ComponentProvenance,
    Intent,
    RendererKind,
    TableRow,
    TurnResult,
)
from financial_analyst_agent.presentation import (
    derived_banner,
    format_per_share,
    format_usd,
    growth_headline,
    present_turn,
)
from financial_analyst_agent.services.fact_selector import (
    FOURTH_QUARTER_LABEL,
    TRAILING_YEAR_LABEL,
)

_Q4 = (date(2025, 10, 1), date(2025, 12, 31))
_Q4_BEFORE = (date(2024, 10, 1), date(2024, 12, 31))
_YEAR = (date(2025, 7, 1), date(2026, 6, 30))


def _provenance(
    metric: str,
    value: str,
    period: tuple[date, date],
    *,
    form: str = "10-Q",
    accession: str = "0000059478-26-000001",
    derivation: str | None = None,
    derived_from: list[ComponentProvenance] | None = None,
) -> ComponentProvenance:
    return ComponentProvenance(
        metric=metric,
        value=Decimal(value),
        start_date=period[0],
        end_date=period[1],
        form=form,
        accession_number=accession,
        taxonomy="us-gaap",
        concept="Revenues",
        source_url=f"https://www.sec.gov/{accession}.htm",
        source="sec_xbrl",
        derivation=derivation,
        derived_from=derived_from or [],
    )


def _row(metric: str, value: str | None, period: tuple[date, date], **fields: object) -> TableRow:
    values: dict[str, object] = {
        "company_name": "Eli Lilly and Company",
        "ticker": "LLY",
        "cik": "0000059478",
        "metric": metric,
        "value": Decimal(value) if value is not None else None,
        "start_date": period[0],
        "end_date": period[1],
    }
    return TableRow.model_validate({**values, **fields})


def _present(  # type: ignore[no-untyped-def]
    *rows: TableRow,
    intent: Intent = Intent.COMPARE,
    banners: list[str] | None = None,
    snapshot_as_of: str | None = None,
):
    return present_turn(
        TurnResult(
            intent=intent,
            tool_traces=[],
            renderer=RendererKind.TABLE,
            table_rows=list(rows),
            banners=banners or [],
            snapshot_as_of=snapshot_as_of,
        )
    )


def test_a_derived_fourth_quarter_in_a_comparison_says_it_is_derived() -> None:
    fourth = _provenance(
        "revenue", "19290000000", _Q4, form="10-K", derivation=FOURTH_QUARTER_LABEL
    )
    row = _row("revenue", "19290000000", _Q4, components=[fourth], form="10-K")

    (item, *_parts) = _present(row, _row("revenue", "1", _Q4, ticker="PFE")).evidence

    assert item.selection_rule.startswith("Derived quarter")
    assert "no year-to-date derivation" not in item.selection_rule


def test_a_change_names_both_quarters_and_both_filings() -> None:
    current = _provenance("revenue", "19290000000", _Q4, accession="0000059478-26-000010")
    prior = _provenance("revenue", "13530000000", _Q4_BEFORE, accession="0000059478-25-000010")
    change = _row(
        "revenue",
        "5760000000",
        (_Q4_BEFORE[0], _Q4[1]),
        components=[prior, current],
        comparison="year_over_year",
    )
    level = _row(
        "revenue",
        "19290000000",
        _Q4,
        components=[current],
        accession_number=current.accession_number,
        form="10-Q",
    )

    items = {item.label: item for item in _present(level, change).evidence}
    (item,) = [item for label, item in items.items() if "change" in label]

    assert item.period_label == "Oct 1, 2025 – Dec 31, 2025 vs Oct 1, 2024 – Dec 31, 2024"
    assert item.accession_number == "0000059478-26-000010"
    assert item.concept == "Revenues"
    assert "0000059478-25-000010" in item.selection_rule
    assert "0000059478-26-000010" in item.selection_rule


def test_a_p_e_card_is_calculated_over_a_trailing_year() -> None:
    market_cap = ComponentProvenance(
        metric="market_cap",
        value=Decimal("1090000000000"),
        start_date=date(2026, 9, 27),
        end_date=date(2026, 9, 27),
        form="",
        accession_number="",
        taxonomy="",
        concept="",
        source_url="",
        source="fmp_universe_snapshot",
    )
    year = _provenance("net_income", "66970000000", (date(2025, 1, 1), date(2025, 12, 31)))
    to_date = _provenance("net_income", "35770000000", (date(2026, 1, 1), date(2026, 6, 30)))
    before = _provenance("net_income", "16970000000", (date(2025, 1, 1), date(2025, 6, 30)))
    earnings = _provenance(
        "net_income_ttm",
        "85770000000",
        _YEAR,
        derivation=TRAILING_YEAR_LABEL,
        derived_from=[year, to_date, before],
    )
    row = _row("pe_ratio", "12.7", _YEAR, components=[market_cap, earnings])

    presented = _present(row, intent=Intent.LOOKUP)

    card = presented.fact_card
    assert card is not None
    assert card.period_label.startswith("Calculated † · Trailing year · Jul 1, 2025")
    assert card.form == ""
    assert card.concept == "Market cap (Sep 27, 2026) ÷ trailing-year net income"
    parts = [item.label for item in presented.evidence if item.amount in ("$66.97 B", "$35.77 B")]
    assert parts == [
        "Eli Lilly and Company · Net income · Jan 1, 2025 – Dec 31, 2025",
        "Eli Lilly and Company · Net income · Jan 1, 2026 – Jun 30, 2026",
    ]
    assert "Both" not in derived_banner([row])


def test_a_share_price_beside_a_trailing_year_is_dated_by_the_snapshot() -> None:
    price = _row("price", "505.48", _YEAR).model_copy(update={"start_date": None, "end_date": None})
    pe = _row("pe_ratio", "12.7", _YEAR)

    table = _present(
        price,
        pe,
        intent=Intent.LOOKUP,
        snapshot_as_of="2026-09-27T10:54:00+00:00",
    ).table

    assert table is not None
    assert "Quarter ended" not in table.headers
    assert "P/E ratio (trailing year)" in table.headers
    assert "$505.48 on Sep 27, 2026" in table.rows[0]


def test_headline_names_a_metric_in_its_own_case_and_says_unchanged() -> None:
    def change(ticker: str, value: str) -> TableRow:
        base = _provenance("eps_diluted", "0.32", _Q4_BEFORE)
        return _row(
            "eps_diluted",
            value,
            _Q4,
            components=[base],
            comparison="year_over_year",
            ticker=ticker,
        )

    headline = growth_headline([change("CMG", "0")])

    assert headline is not None
    assert "diluted EPS" in headline and "was unchanged" in headline


def test_amounts_use_one_scale_and_per_share_keeps_its_precision() -> None:
    assert format_usd(Decimal("500000")) == "$500.00 K"
    assert format_usd(Decimal("999996")) == "$1.00 M"
    assert format_usd(Decimal("950")) == "$950"
    assert format_per_share(Decimal("0.2475")) == "$0.2475"
    assert format_per_share(Decimal("1.5")) == "$1.50"
