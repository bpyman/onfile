"""Derived quarters, per-share figures and named periods (ADR 0007)."""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from financial_analyst_agent.contracts import Intent, RendererKind, TableRow, TurnResult
from financial_analyst_agent.domain.enums import Metric
from financial_analyst_agent.domain.errors import (
    PerShareNotDerivableError,
    UnsupportedQuarterlyFactError,
)
from financial_analyst_agent.domain.models import FactRecord, Filing
from financial_analyst_agent.graph.analysis_spec import (
    AnalysisSpec,
    NamedPeriodSpec,
    PeriodSelection,
    ResolvedCompany,
)
from financial_analyst_agent.graph.spec_turn import compile_tasks
from financial_analyst_agent.period_selection import read
from financial_analyst_agent.presentation import format_metric_value, present_turn
from financial_analyst_agent.request_wording import change_asked
from financial_analyst_agent.services.fact_selector import (
    FOURTH_QUARTER_LABEL,
    YEAR_TO_DATE_LABEL,
    FactOwner,
    derive_quarter,
)
from financial_analyst_agent.services.filing_selector import list_quarterly_report_dates
from financial_analyst_agent.services.fiscal_periods import (
    FiscalLabel,
    calendar_quarter,
    dates_for,
    periods_from_filings,
)
from financial_analyst_agent.services.metric_catalog import resolve_metric_phrase

FY_START = date(2024, 9, 29)
Q1_END = date(2024, 12, 28)
Q2_END = date(2025, 3, 29)
Q3_END = date(2025, 6, 28)
FY_END = date(2025, 9, 27)


def _fact(
    concept: str,
    start: date,
    end: date,
    value: str,
    accession: str,
    form: str = "10-Q",
    unit: str = "USD",
) -> FactRecord:
    return FactRecord(
        accession_number=accession,
        start_date=start,
        end_date=end,
        form=form,
        unit=unit,
        value=Decimal(value),
        concept=concept,
        taxonomy="us-gaap",
        filed_date=end.replace(day=1) if end.month == 12 else date(end.year, end.month + 1, 1),
    )


def _filing(form: str, accession: str, report_date: date) -> Filing:
    return Filing(
        form=form,
        accession_number=accession,
        filed_date=report_date,
        report_date=report_date,
    )


def _derive(facts: list[FactRecord], filing: Filing, metric: Metric, unit: str = "USD"):  # type: ignore[no-untyped-def]
    return derive_quarter(
        facts,
        filing,
        metric,
        FactOwner(company_name="Apple Inc.", ticker="AAPL", cik="0000320193", currency=unit),
        "https://www.sec.gov/primary.htm",
        lambda accession: f"https://www.sec.gov/{accession}.htm",
    )


REVENUE = "RevenueFromContractWithCustomerExcludingAssessedTax"
CASH = "NetCashProvidedByUsedInOperatingActivities"


def test_fourth_quarter_is_the_year_minus_nine_months() -> None:
    facts = [
        _fact(REVENUE, FY_START, Q3_END, "313695", "q3", "10-Q"),
        _fact(REVENUE, date(2025, 3, 30), Q3_END, "94036", "q3", "10-Q"),
        _fact(REVENUE, FY_START, FY_END, "416161", "k", "10-K"),
    ]

    fact = _derive(facts, _filing("10-K", "k", FY_END), Metric.REVENUE)

    assert fact.value == Decimal("102466")
    assert (fact.start_date, fact.end_date) == (date(2025, 6, 29), FY_END)
    assert fact.directly_reported is False
    assert fact.derivation is not None
    assert fact.derivation.label == FOURTH_QUARTER_LABEL
    assert [part.accession_number for part in fact.derivation.parts] == ["k", "q3"]
    assert fact.derivation.parts[1].source_url == "https://www.sec.gov/q3.htm"


def test_a_derived_quarter_carries_its_owner_and_its_longer_filing_s_provenance() -> None:
    facts = [
        _fact(REVENUE, FY_START, Q3_END, "313695", "q3", "10-Q"),
        _fact(REVENUE, FY_START, FY_END, "416161", "k", "10-K"),
    ]
    annual = facts[1]

    fact = _derive(facts, _filing("10-K", "k", FY_END), Metric.REVENUE)

    # Every field but the amount, its start, the flag and the derivation is the
    # owner's or the 10-K's, as a directly reported fact's would be.
    assert fact.model_dump(
        exclude={"value", "start_date", "directly_reported", "derivation", "year_earlier"}
    ) == {
        "company_name": "Apple Inc.",
        "ticker": "AAPL",
        "cik": "0000320193",
        "metric": Metric.REVENUE,
        "currency": "USD",
        "end_date": annual.end_date,
        "filed_date": annual.filed_date,
        "form": annual.form,
        "accession_number": annual.accession_number,
        "taxonomy": annual.taxonomy,
        "concept": annual.concept,
        "source_url": "https://www.sec.gov/primary.htm",
        "source": "sec_xbrl",
        "newer_filing_end": None,
        "year_only_quarter_end": None,
        "diluted_shares": None,
        "split_adjustment": None,
    }


def test_a_fourth_quarter_s_year_earlier_is_each_filing_s_own_comparative() -> None:
    prior_start = date(2023, 10, 1)
    facts = [
        _fact(REVENUE, FY_START, Q3_END, "313695", "q3", "10-Q"),
        _fact(REVENUE, prior_start, date(2024, 6, 29), "296105", "q3", "10-Q"),
        _fact(REVENUE, FY_START, FY_END, "416161", "k", "10-K"),
        _fact(REVENUE, prior_start, date(2024, 9, 28), "391035", "k", "10-K"),
        # The year-earlier nine months as first filed, before the newer 10-Q restated them.
        _fact(REVENUE, prior_start, date(2024, 6, 29), "290000", "q3-2024", "10-Q"),
    ]

    fact = _derive(facts, _filing("10-K", "k", FY_END), Metric.REVENUE)

    assert fact.year_earlier is not None
    assert fact.year_earlier.value == Decimal("94930")
    assert fact.year_earlier.start_date == date(2024, 6, 30)
    assert fact.year_earlier.derivation is not None
    assert [part.accession_number for part in fact.year_earlier.derivation.parts] == ["k", "q3"]


def test_a_fourth_quarter_subtracts_the_nine_months_as_then_reported() -> None:
    # 3M, 2023: a 10-Q filed after the 10-K recast the nine months for a spin-off.
    start, nine, year = date(2023, 1, 1), date(2023, 9, 30), date(2023, 12, 31)
    original = _fact(REVENUE, start, nine, "24668", "q3", "10-Q")
    recast = _fact(REVENUE, start, nine, "18608", "q3-2024", "10-Q").model_copy(
        update={"filed_date": date(2024, 10, 22)}
    )
    annual = _fact(REVENUE, start, year, "32681", "k", "10-K").model_copy(
        update={"filed_date": date(2024, 2, 7)}
    )

    fact = _derive([original, recast, annual], _filing("10-K", "k", year), Metric.REVENUE)

    assert fact.value == Decimal("8013")
    assert fact.derivation is not None
    assert fact.derivation.parts[1].accession_number == "q3"


def test_a_quarter_is_not_derived_from_a_part_filed_after_its_total() -> None:
    start, nine, year = date(2023, 1, 1), date(2023, 9, 30), date(2023, 12, 31)
    recast_only = _fact(REVENUE, start, nine, "18608", "q3-2024", "10-Q").model_copy(
        update={"filed_date": date(2024, 10, 22)}
    )
    annual = _fact(REVENUE, start, year, "32681", "k", "10-K").model_copy(
        update={"filed_date": date(2024, 2, 7)}
    )

    with pytest.raises(UnsupportedQuarterlyFactError):
        _derive([recast_only, annual], _filing("10-K", "k", year), Metric.REVENUE)


def test_a_standalone_fourth_quarter_in_the_10k_is_used_as_reported() -> None:
    facts = [
        _fact(REVENUE, FY_START, FY_END, "416161", "k", "10-K"),
        _fact(REVENUE, date(2025, 6, 29), FY_END, "102466", "k", "10-K"),
    ]

    fact = _derive(facts, _filing("10-K", "k", FY_END), Metric.REVENUE)

    assert fact.value == Decimal("102466")
    assert fact.directly_reported is True
    assert fact.derivation is None


def test_cash_flow_quarter_is_year_to_date_minus_the_previous_quarter() -> None:
    facts = [
        _fact(CASH, FY_START, Q1_END, "29935", "q1"),
        _fact(CASH, FY_START, Q2_END, "53887", "q2"),
    ]

    fact = _derive(facts, _filing("10-Q", "q2", Q2_END), Metric.OPERATING_CASH_FLOW)

    assert fact.value == Decimal("23952")
    assert fact.start_date == date(2024, 12, 29)
    assert fact.derivation is not None and fact.derivation.label == YEAR_TO_DATE_LABEL


def test_amounts_with_different_start_dates_are_never_subtracted() -> None:
    facts = [
        _fact(CASH, date(2024, 10, 1), Q1_END, "29935", "q1"),
        _fact(CASH, FY_START, Q2_END, "53887", "q2"),
    ]

    with pytest.raises(UnsupportedQuarterlyFactError):
        _derive(facts, _filing("10-Q", "q2", Q2_END), Metric.OPERATING_CASH_FLOW)


def test_fourth_quarter_eps_is_never_derived() -> None:
    concept = "EarningsPerShareDiluted"
    facts = [
        _fact(concept, FY_START, Q3_END, "5.62", "q3", unit="USD/shares"),
        _fact(concept, FY_START, FY_END, "7.46", "k", "10-K", unit="USD/shares"),
    ]

    with pytest.raises(PerShareNotDerivableError):
        _derive(facts, _filing("10-K", "k", FY_END), Metric.EPS_DILUTED, "USD/shares")


def test_windows_list_the_10k_year_end_as_a_quarter() -> None:
    filings = [
        _filing("10-Q", "q3", Q3_END),
        _filing("10-K", "k", FY_END),
        _filing("10-K/A", "ka", date(2025, 9, 28)),
        _filing("10-Q", "q2", Q2_END),
    ]

    assert list_quarterly_report_dates(filings, limit=3) == [date(2025, 9, 28), Q3_END, Q2_END]


def test_metric_phrases_name_eps_and_cash_flow() -> None:
    def metric(question: str) -> str | None:
        return resolve_metric_phrase(question).metric

    assert metric("Apple EPS") == "eps_diluted"
    assert metric("earnings per share for Apple") == "eps_diluted"
    assert metric("basic EPS") == "eps_basic"
    assert metric("Microsoft free cash flow") == "free_cash_flow"
    assert metric("capex at Amazon") == "capital_expenditure"
    assert metric("cash from operations") == "operating_cash_flow"
    assert resolve_metric_phrase("Apple cash flow").kind == "ambiguous"


def test_per_share_amounts_show_cents_or_the_fractions_filed() -> None:
    assert format_metric_value("eps_diluted", Decimal("2.02")) == "$2.02"
    # A fraction of a cent the filing reports is kept, as a $0.2475 dividend is.
    assert format_metric_value("eps_diluted", Decimal("-0.155")) == "-$0.155"
    assert format_metric_value("free_cash_flow", Decimal("19640000000")) == "$19.64 B"


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("Apple revenue Q3 2024", [NamedPeriodSpec(year=2024, quarter=3)]),
        ("Nvidia margin in Q3 FY25", [NamedPeriodSpec(year=2025, quarter=3)]),
        ("revenue 2024 Q1", [NamedPeriodSpec(year=2024, quarter=1)]),
        ("third quarter of fiscal 2024", [NamedPeriodSpec(year=2024, quarter=3)]),
        ("Nvidia net income fiscal 2025", [NamedPeriodSpec(year=2025)]),
        ("FY24 revenue", [NamedPeriodSpec(year=2024)]),
        (
            "Walmart revenue calendar Q1 2026",
            [NamedPeriodSpec(year=2026, quarter=1, calendar=True)],
        ),
        ("Apple revenue in 2023", [NamedPeriodSpec(year=2023)]),
        (
            "Q3 2024 vs Q3 2023",
            [NamedPeriodSpec(year=2024, quarter=3), NamedPeriodSpec(year=2023, quarter=3)],
        ),
        ("Visa net margin 2Q 2026", [NamedPeriodSpec(year=2026, quarter=2)]),
        ("4QFY24 EPS", [NamedPeriodSpec(year=2024, quarter=4)]),
        ("revenue for the last 4 quarters", []),
        ("top 5 banks", []),
    ],
)
def test_named_periods_are_read_from_the_question(
    question: str, expected: list[NamedPeriodSpec]
) -> None:
    assert list(read(question).named) == expected


def test_a_named_quarter_year_over_year_reads_its_own_comparative() -> None:
    from financial_analyst_agent.graph.analysis_spec import SpecPatch

    message = "Apple revenue Q4 2025 yoy"
    patch = read(message).bind(SpecPatch(mode="replace"), change_asked(message))

    # Q4 2025 alone, its change from the comparative its own filing reports (ADR 0009):
    # the year-earlier quarter is not a second named period.
    assert patch.set_periods is not None
    assert patch.set_periods.named == (NamedPeriodSpec(year=2025, quarter=4),)
    assert patch.set_periods.company_base_dates is None
    assert {"across_periods", "year_over_year"} <= set(patch.add_operations)


def test_a_named_quarter_quarter_over_quarter_reads_the_quarter_before() -> None:
    from financial_analyst_agent.graph.analysis_spec import SpecPatch

    message = "Apple revenue Q4 2025 quarter over quarter"
    patch = read(message).bind(SpecPatch(mode="replace"), change_asked(message))

    assert patch.set_periods is not None
    assert patch.set_periods.named == (NamedPeriodSpec(year=2025, quarter=4),)
    # The quarter before is read as the change's base once each company's dates are listed.
    assert patch.set_periods.company_base_dates == ()
    assert "across_periods" in patch.add_operations
    assert "year_over_year" not in patch.add_operations


def test_fiscal_and_calendar_quarters_come_from_each_filing() -> None:
    filings = [
        _filing("10-Q", "q3", Q3_END),
        _filing("10-K", "k", FY_END),
        _filing("10-Q", "q2", Q2_END),
    ]
    labels = {
        "q3": FiscalLabel(2025, "Q3"),
        "q2": FiscalLabel(2025, "Q2"),
        "k": FiscalLabel(2025, "FY"),
    }
    periods = periods_from_filings(filings, labels)

    assert dates_for(periods, 2025, 3, calendar=False) == (Q3_END,)
    assert dates_for(periods, 2025, 4, calendar=False) == (FY_END,)
    assert dates_for(periods, 2025, None, calendar=False) == (FY_END, Q3_END, Q2_END)
    assert calendar_quarter(date(2025, 10, 26)) == (2025, 3)
    assert dates_for(periods, 2025, 2, calendar=True) == (Q3_END,)


def test_a_named_quarter_asks_each_company_for_its_own_quarter_end() -> None:
    apple = ResolvedCompany(cik="1", name="Apple Inc.", ticker="AAPL", query="AAPL")
    microsoft = ResolvedCompany(cik="2", name="Microsoft", ticker="MSFT", query="MSFT")
    spec = AnalysisSpec(
        companies=(apple, microsoft),
        metrics=("revenue",),
        periods=PeriodSelection(
            kind="named",
            named=(NamedPeriodSpec(year=2024, quarter=3),),
            report_dates=(date(2024, 6, 29),),
            count=1,
            company_report_dates=(
                ("1", (date(2024, 6, 29),)),
                ("2", (date(2024, 3, 31),)),
            ),
        ),
        operations=("across_companies",),
    )

    tasks = compile_tasks(spec)

    assert {(task.issuers, task.report_date) for task in tasks} == {
        # Each company is asked for by its CIK.
        (("1",), date(2024, 6, 29)),
        (("2",), date(2024, 3, 31)),
    }


def test_derived_values_are_marked_and_explained() -> None:
    row = TableRow(
        company_name="Apple Inc.",
        ticker="AAPL",
        cik="0000320193",
        metric="revenue",
        value=Decimal("102466000000"),
        start_date=date(2025, 6, 29),
        end_date=FY_END,
        derivation=FOURTH_QUARTER_LABEL,
    )
    other = row.model_copy(update={"derivation": None, "end_date": Q3_END})
    result = TurnResult(
        intent=Intent.LOOKUP,
        renderer=RendererKind.TABLE,
        table_rows=[row, other],
        tool_traces=[],
    )

    presented = present_turn(result)

    assert presented.table is not None
    values = [r[presented.table.keys.index("value:revenue")] for r in presented.table.rows]
    assert values == ["$102.47 B †", "$102.47 B"]
    assert any("10-K's full year minus the 10-Q's nine months" in b for b in presented.banners)


def test_trailing_twelve_months_shows_the_four_quarters_behind_it() -> None:
    from financial_analyst_agent.graph.analysis_spec import SpecPatch

    for question in (
        "Apple TTM revenue",
        "revenue over the trailing twelve months",
        # After the metric, "last twelve months" is a span of quarters, not LTM.
        "pfizer net income over the last twelve months",
    ):
        patch = read(question).bind(SpecPatch(mode="replace"), change_asked(question))
        assert patch.set_periods == PeriodSelection(kind="last_n_quarters", count=4)


def test_trailing_twelve_months_before_net_income_is_one_figure_not_a_window() -> None:
    from financial_analyst_agent.graph.analysis_spec import SpecPatch

    for question in (
        "Apple TTM net income",
        "trailing twelve month net income for Apple",
        "pfizer's last twelve months net income",
        "Apple last 12 months net income",
    ):
        window = read(question).reading
        assert not window.trailing_year
        assert not window.counted_window
        patch = read(question).bind(SpecPatch(mode="replace"), change_asked(question))
        assert patch.set_periods is None


def test_everyday_nicknames_name_the_company() -> None:
    from financial_analyst_agent.issuer_index import IssuerIndex
    from financial_analyst_agent.universe import UniverseCompany

    def company(ticker: str, name: str) -> UniverseCompany:
        return UniverseCompany(
            cik="0000000001", name=name, ticker=ticker, sector="x", exchange="NYSE", market_cap=1
        )

    index = IssuerIndex.build(
        [company("PEP", "PepsiCo, Inc."), company("KO", "The Coca-Cola Company")]
    )

    assert [m.query for m in index.find("Compare Coke and Pepsi EPS")] == ["KO", "PEP"]
    # A nickname for a company the snapshot lacks names nobody.
    assert index.find("Facebook revenue") == []


def test_live_index_knows_street_names_for_large_companies() -> None:
    from financial_analyst_agent.rules_planner import issuer_index

    index = issuer_index()

    assert [m.query for m in index.find("Citi vs Chase net income")] == ["C", "JPM"]
    assert [m.query for m in index.find("Schwab and Capital One revenue")] == ["SCHW", "COF"]


def test_revenue_reads_net_revenue_before_contract_revenue() -> None:
    from financial_analyst_agent.services.metric_catalog import get_concept_candidates

    concepts = [concept for _, concept in get_concept_candidates(Metric.REVENUE)]

    # A bank's contract revenue is its fees alone; its net revenue includes interest.
    assert concepts.index("RevenuesNetOfInterestExpense") < concepts.index(
        "RevenueFromContractWithCustomerExcludingAssessedTax"
    )
    assert "RegulatedAndUnregulatedOperatingRevenue" in concepts


def _periods(*rows: tuple[str, str, int, int]) -> tuple[object, ...]:
    from financial_analyst_agent.services.fiscal_periods import FiscalPeriod

    return tuple(
        FiscalPeriod(end=date.fromisoformat(end), fiscal_year=year, quarter=quarter, form=form)
        for end, form, quarter, year in rows
    )


def _years(periods: tuple[object, ...]) -> list[int | None]:
    from financial_analyst_agent.services.fiscal_periods import _sequenced

    return [period.fiscal_year for period in _sequenced(periods)]  # type: ignore[arg-type,attr-defined]


def test_a_first_quarter_repeating_the_closed_year_is_the_next_year() -> None:
    # Oracle: the 10-Q for the quarter ended August 31, 2026 declares fy 2026.
    oracle = _periods(
        ("2026-08-31", "10-Q", 1, 2026),
        ("2026-05-31", "10-K", 4, 2026),
        ("2026-02-28", "10-Q", 3, 2026),
        ("2025-05-31", "10-K", 4, 2025),
    )
    # NetApp: its first two quarters of fiscal 2026 both declare 2025.
    netapp = _periods(
        ("2026-01-23", "10-Q", 3, 2026),
        ("2025-10-24", "10-Q", 2, 2025),
        ("2025-07-25", "10-Q", 1, 2025),
        ("2025-04-25", "10-K", 4, 2025),
        ("2024-04-26", "10-K", 4, 2024),
    )

    assert _years(oracle) == [2027, 2026, 2026, 2025]
    assert _years(netapp) == [2026, 2026, 2026, 2025, 2024]


def test_a_mislabelled_year_end_is_not_carried_into_the_next_year() -> None:
    # Domino's 53-week year ended January 1, 2023 declares 2023; the next 10-K closes 2023.
    dominos = _periods(
        ("2023-12-31", "10-K", 4, 2023),
        ("2023-09-10", "10-Q", 3, 2023),
        ("2023-03-26", "10-Q", 1, 2023),
        ("2023-01-01", "10-K", 4, 2023),
        ("2022-01-02", "10-K", 4, 2022),
    )

    assert _years(dominos) == [2023, 2023, 2023, 2023, 2022]


def test_a_quarter_sec_has_not_labelled_yet_follows_the_one_before() -> None:
    from financial_analyst_agent.services.fiscal_periods import FiscalPeriod, _sequenced

    # Coca-Cola: the 10-Q for the quarter ended July 3, 2026 is listed, unlabelled.
    periods = (
        FiscalPeriod(end=date(2026, 7, 3), fiscal_year=None, quarter=None, form="10-Q"),
        FiscalPeriod(end=date(2026, 4, 3), fiscal_year=2026, quarter=1, form="10-Q"),
        FiscalPeriod(end=date(2025, 12, 31), fiscal_year=2025, quarter=4, form="10-K"),
    )

    newest = _sequenced(periods)[0]

    assert (newest.fiscal_year, newest.quarter) == (2026, 2)
