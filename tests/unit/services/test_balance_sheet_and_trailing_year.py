"""Balance-sheet amounts and trailing years (ADR 0008)."""

from datetime import date
from decimal import Decimal

import pytest

from financial_analyst_agent.domain.enums import Metric
from financial_analyst_agent.domain.errors import UnsupportedQuarterlyFactError
from financial_analyst_agent.services.fact_selector import (
    FactOwner,
    derive_trailing_year,
    select_instant_fact,
)
from helpers import make_fact, make_filing

COMPANY = {"company_name": "Apple Inc.", "ticker": "AAPL", "cik": "0000320193"}
OWNER = FactOwner(**COMPANY)
URL = "https://www.sec.gov/Archives/edgar/data/320193/q3.htm"
QUARTER = make_filing()  # 10-Q for the quarter ended 28 Sep 2024
# A fiscal third quarter: its 10-Q reports nine months to date.
FISCAL_Q3 = make_filing(report_date=date(2024, 6, 29))
FY_ACCESSION = "0000320193-23-000106"


def _url(accession: str) -> str:
    return f"https://www.sec.gov/{accession}"


def test_a_balance_sheet_amount_is_the_filing_s_instant_at_its_report_date() -> None:
    facts = [
        make_fact(
            concept="CashAndCashEquivalentsAtCarryingValue",
            start_date=None,
            value=Decimal("25000000000"),
        ),
        # The prior year-end balance the same 10-Q repeats is not this quarter's.
        make_fact(
            concept="CashAndCashEquivalentsAtCarryingValue",
            start_date=None,
            end_date=date(2023, 9, 30),
            value=Decimal("29965000000"),
        ),
    ]
    fact = select_instant_fact(facts, QUARTER, Metric.CASH, OWNER, source_url=URL)
    assert fact.value == Decimal("25000000000")
    assert fact.start_date == fact.end_date == date(2024, 9, 28)
    assert fact.directly_reported is True


def test_a_duration_fact_is_not_a_balance_sheet_amount() -> None:
    facts = [make_fact(concept="StockholdersEquity")]
    with pytest.raises(UnsupportedQuarterlyFactError):
        select_instant_fact(
            facts, QUARTER, Metric.SHAREHOLDERS_EQUITY, OWNER, source_url=URL
        )


def _trailing_facts(*, proxy: bool = False) -> list:
    facts = [
        # Fiscal 2023 from the 10-K.
        make_fact(
            accession_number=FY_ACCESSION,
            form="10-K",
            start_date=date(2022, 9, 25),
            end_date=date(2023, 9, 30),
            value=Decimal("97000000000"),
            filed_date=date(2023, 11, 3),
        ),
        # This 10-Q's nine months, and the same nine months a year earlier.
        make_fact(
            start_date=date(2023, 10, 1), end_date=date(2024, 6, 29), value=Decimal("80000000000")
        ),
        make_fact(
            start_date=date(2022, 9, 25), end_date=date(2023, 7, 1), value=Decimal("75000000000")
        ),
    ]
    if proxy:
        # A proxy statement tags net income for the year too; it is not the 10-K.
        facts.append(
            make_fact(
                accession_number="0000320193-24-000010",
                form="DEF 14A",
                start_date=date(2022, 9, 25),
                end_date=date(2023, 9, 30),
                value=Decimal("1"),
                filed_date=date(2024, 1, 10),
            )
        )
    return facts


def test_the_trailing_year_after_a_10q_adds_the_year_to_date_to_the_last_10k() -> None:
    fact = derive_trailing_year(
        _trailing_facts(proxy=True),
        FISCAL_Q3,
        Metric.NET_INCOME_TTM,
        OWNER,
        source_url=URL,
        source_url_for_accession=_url,
    )
    assert fact.value == Decimal("102000000000")
    assert (fact.start_date, fact.end_date) == (date(2023, 7, 2), date(2024, 6, 29))
    assert fact.directly_reported is False
    assert fact.derivation is not None
    assert fact.derivation.method == "trailing_twelve_months"
    assert [part.form for part in fact.derivation.parts] == ["10-K", "10-Q", "10-Q"]


def test_the_trailing_year_carries_its_owner_and_the_10q_s_provenance() -> None:
    facts = _trailing_facts()
    year_to_date = facts[1]

    fact = derive_trailing_year(
        facts,
        FISCAL_Q3,
        Metric.NET_INCOME_TTM,
        OWNER,
        source_url=URL,
        source_url_for_accession=_url,
    )

    # The 10-Q that reports this year to date is the trailing year's filing; the
    # owner's name, ticker, CIK and currency are read as for a reported fact.
    assert fact.model_dump(
        exclude={"value", "start_date", "directly_reported", "derivation", "year_earlier"}
    ) == {
        **COMPANY,
        "metric": Metric.NET_INCOME_TTM,
        "currency": "USD",
        "end_date": year_to_date.end_date,
        "filed_date": year_to_date.filed_date,
        "form": year_to_date.form,
        "accession_number": year_to_date.accession_number,
        "taxonomy": year_to_date.taxonomy,
        "concept": year_to_date.concept,
        "source_url": URL,
        "source": "sec_xbrl",
        "newer_filing_end": None,
        "year_only_quarter_end": None,
        "diluted_shares": None,
        "split_adjustment": None,
    }
    assert [part.metric for part in (fact.derivation.parts if fact.derivation else [])] == [
        "net_income",
        "net_income",
        "net_income",
    ]


def test_the_trailing_year_after_a_10k_is_the_fiscal_year() -> None:
    annual = make_filing(
        form="10-K",
        accession_number=FY_ACCESSION,
        report_date=date(2023, 9, 30),
        filed_date=date(2023, 11, 3),
    )
    fact = derive_trailing_year(
        _trailing_facts(),
        annual,
        Metric.NET_INCOME_TTM,
        OWNER,
        source_url=URL,
        source_url_for_accession=_url,
    )
    assert fact.value == Decimal("97000000000")
    assert fact.directly_reported is True


def test_no_trailing_year_without_the_10k() -> None:
    facts = [fact for fact in _trailing_facts(proxy=True) if fact.form != "10-K"]
    with pytest.raises(UnsupportedQuarterlyFactError):
        derive_trailing_year(
            facts,
            FISCAL_Q3,
            Metric.NET_INCOME_TTM,
            OWNER,
            source_url=URL,
            source_url_for_accession=_url,
        )
