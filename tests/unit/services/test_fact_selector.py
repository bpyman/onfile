"""Fact selector tests."""

from datetime import date, timedelta
from decimal import Decimal

import pytest

from financial_analyst_agent.domain.enums import Metric
from financial_analyst_agent.domain.errors import (
    AmbiguousFactError,
    FilingNotFoundError,
    UnsupportedQuarterlyFactError,
)
from financial_analyst_agent.services.fact_selector import (
    FactOwner,
    is_standalone_quarter,
    select_quarterly_fact,
    select_quarterly_fact_with_filing_fallback,
)
from helpers import make_fact, make_filing

FILING = make_filing()
SOURCE_URL = "https://www.sec.gov/Archives/edgar/data/320193/aapl.htm"
COMPANY = {
    "company_name": "Apple Inc.",
    "ticker": "AAPL",
    "cik": "0000320193",
}
OWNER = FactOwner(**COMPANY)
REPORT_END = date(2024, 9, 28)


def _select(facts: list, filing=FILING) -> object:
    selected = select_quarterly_fact(
        facts,
        filing,
        Metric.NET_INCOME,
        OWNER,
        source_url=SOURCE_URL,
    )
    assert len(selected) == 1
    return selected[0]


def test_selects_standalone_quarterly_fact() -> None:
    result = _select([make_fact(value=Decimal("23636000000"))])
    assert result.value == Decimal("23636000000")
    assert result.directly_reported is True
    assert result.source.value == "sec_xbrl"
    assert result.metric == Metric.NET_INCOME
    assert result.concept == "NetIncomeLoss"


def test_rejects_ytd_fact_same_accession() -> None:
    facts = [
        make_fact(
            start_date=date(2023, 10, 1),
            end_date=REPORT_END,
            value=Decimal("50000000000"),
        ),
    ]
    with pytest.raises(UnsupportedQuarterlyFactError):
        _select(facts)


def test_rejects_comparative_prior_year_same_accession() -> None:
    facts = [
        make_fact(
            start_date=date(2023, 7, 2),
            end_date=date(2023, 9, 30),
            value=Decimal("22956000000"),
        ),
    ]
    with pytest.raises(UnsupportedQuarterlyFactError):
        _select(facts)


def test_rejects_wrong_accession() -> None:
    facts = [
        make_fact(
            accession_number="0000320193-24-000050",
            value=Decimal("100"),
        ),
    ]
    with pytest.raises(UnsupportedQuarterlyFactError):
        _select(facts)


def test_rejects_wrong_unit() -> None:
    facts = [make_fact(unit="EUR", value=Decimal("100"))]
    with pytest.raises(UnsupportedQuarterlyFactError):
        _select(facts)


def test_rejects_instant_fact_without_duration() -> None:
    facts = [make_fact(start_date=None, value=Decimal("100"))]
    with pytest.raises(UnsupportedQuarterlyFactError):
        _select(facts)


def test_selects_current_quarter_among_mixed_facts() -> None:
    facts = [
        make_fact(
            start_date=date(2023, 10, 1),
            end_date=REPORT_END,
            value=Decimal("50000000000"),
        ),
        make_fact(
            start_date=date(2023, 7, 2),
            end_date=date(2023, 9, 30),
            value=Decimal("22956000000"),
        ),
        make_fact(
            start_date=date(2024, 6, 30),
            end_date=REPORT_END,
            value=Decimal("23636000000"),
        ),
    ]
    result = _select(facts)
    assert result.value == Decimal("23636000000")


def test_ambiguous_when_multiple_same_filed_date() -> None:
    facts = [
        make_fact(value=Decimal("100")),
        make_fact(value=Decimal("200")),
    ]
    with pytest.raises(AmbiguousFactError):
        _select(facts)


def test_identical_duplicate_facts_are_not_ambiguous() -> None:
    facts = [make_fact(value=Decimal("100")), make_fact(value=Decimal("100"))]

    assert _select(facts).value == Decimal("100")


def test_prefers_latest_filed_date_on_restatement() -> None:
    facts = [
        make_fact(filed_date=date(2024, 11, 1), value=Decimal("23636000000")),
        make_fact(filed_date=date(2024, 12, 15), value=Decimal("23650000000")),
    ]
    result = _select(facts)
    assert result.value == Decimal("23650000000")


def test_10_q_filing_rejects_only_10_q_a_facts_on_incompatible_accession() -> None:
    facts = [
        make_fact(
            form="10-Q/A",
            accession_number="0000320193-24-000082",
            value=Decimal("100"),
        ),
    ]
    with pytest.raises(UnsupportedQuarterlyFactError):
        _select(facts)


def test_10_q_filing_rejects_same_accession_10_q_a_form() -> None:
    facts = [
        make_fact(
            form="10-Q/A",
            accession_number=FILING.accession_number,
            value=Decimal("100"),
        ),
    ]
    with pytest.raises(UnsupportedQuarterlyFactError):
        _select(facts)


def test_10_q_a_filing_requires_10_q_a_form_on_fact() -> None:
    amendment_filing = make_filing(
        form="10-Q/A",
        accession_number="0000320193-24-000082",
    )
    facts = [
        make_fact(
            form="10-Q",
            accession_number="0000320193-24-000082",
            value=Decimal("100"),
        ),
        make_fact(
            form="10-Q/A",
            accession_number="0000320193-24-000082",
            value=Decimal("200"),
        ),
    ]
    result = select_quarterly_fact(
        facts,
        amendment_filing,
        Metric.NET_INCOME,
        OWNER,
        source_url=SOURCE_URL,
    )
    assert len(result) == 1
    assert result[0].value == Decimal("200")
    assert result[0].form == "10-Q/A"


def test_matching_concepts_return_highest_priority() -> None:
    shared_value = Decimal("23636000000")
    facts = [
        make_fact(concept="NetIncomeLoss", value=shared_value),
        make_fact(concept="ProfitLoss", value=shared_value),
    ]
    result = _select(facts)
    assert result.concept == "NetIncomeLoss"
    assert result.value == shared_value


def test_conflicting_concepts_keep_highest_priority() -> None:
    facts = [
        make_fact(concept="NetIncomeLoss", value=Decimal("23636000000")),
        make_fact(concept="ProfitLoss", value=Decimal("999")),
    ]
    result = _select(facts)
    assert result.concept == "NetIncomeLoss"
    assert result.value == Decimal("23636000000")


def test_falls_back_to_next_concept_when_priority_concept_is_absent() -> None:
    facts = [make_fact(concept="ProfitLoss", value=Decimal("18000000000"))]
    result = _select(facts)
    assert result.concept == "ProfitLoss"
    assert result.value == Decimal("18000000000")


def test_operating_expenses_rejects_total_costs_concept() -> None:
    facts = [make_fact(concept="CostsAndExpenses", value=Decimal("500"))]

    with pytest.raises(UnsupportedQuarterlyFactError):
        select_quarterly_fact(
            facts,
            FILING,
            Metric.OPERATING_EXPENSES,
            OWNER,
            source_url=SOURCE_URL,
        )


def test_duration_70_days_accepted() -> None:
    start = REPORT_END - timedelta(days=70)
    result = _select([make_fact(start_date=start, end_date=REPORT_END, value=Decimal("1"))])
    assert result.value == Decimal("1")


def test_duration_110_days_accepted() -> None:
    start = REPORT_END - timedelta(days=110)
    result = _select([make_fact(start_date=start, end_date=REPORT_END, value=Decimal("2"))])
    assert result.value == Decimal("2")


def test_duration_69_days_rejected() -> None:
    start = REPORT_END - timedelta(days=69)
    with pytest.raises(UnsupportedQuarterlyFactError):
        _select([make_fact(start_date=start, end_date=REPORT_END, value=Decimal("3"))])


def test_duration_111_days_rejected() -> None:
    start = REPORT_END - timedelta(days=111)
    with pytest.raises(UnsupportedQuarterlyFactError):
        _select([make_fact(start_date=start, end_date=REPORT_END, value=Decimal("4"))])


OLDER_END = date(2024, 6, 29)
OLDER_START = date(2024, 3, 31)
OLDER_ACCESSION = "0000320193-24-000060"


def _source_url(filing: object) -> str:
    return SOURCE_URL


def test_filing_fallback_named_report_date_returns_that_quarter() -> None:
    older_filing = make_filing(
        accession_number=OLDER_ACCESSION,
        report_date=OLDER_END,
        filed_date=date(2024, 8, 1),
        primary_document="aapl-20240629.htm",
    )
    newer_filing = FILING
    facts = [
        make_fact(
            accession_number=OLDER_ACCESSION,
            start_date=OLDER_START,
            end_date=OLDER_END,
            filed_date=date(2024, 8, 1),
            value=Decimal("21448000000"),
        ),
        make_fact(value=Decimal("23636000000")),
    ]

    selected = select_quarterly_fact_with_filing_fallback(
        facts,
        [older_filing, newer_filing],
        Metric.NET_INCOME,
        OWNER,
        source_url_for_filing=_source_url,
        report_date=OLDER_END,
    )

    assert len(selected) == 1
    assert selected[0].value == Decimal("21448000000")
    assert selected[0].end_date == OLDER_END
    assert selected[0].accession_number == OLDER_ACCESSION


def test_filing_fallback_named_report_date_missing_does_not_use_latest() -> None:
    facts = [make_fact(value=Decimal("23636000000"))]

    with pytest.raises(FilingNotFoundError):
        select_quarterly_fact_with_filing_fallback(
            facts,
            [FILING],
            Metric.NET_INCOME,
            OWNER,
            source_url_for_filing=_source_url,
            report_date=OLDER_END,
        )


def test_filing_fallback_latest_unchanged_when_report_date_omitted() -> None:
    older_filing = make_filing(
        accession_number=OLDER_ACCESSION,
        report_date=OLDER_END,
        filed_date=date(2024, 8, 1),
    )
    facts = [
        make_fact(
            accession_number=OLDER_ACCESSION,
            start_date=OLDER_START,
            end_date=OLDER_END,
            filed_date=date(2024, 8, 1),
            value=Decimal("21448000000"),
        ),
        make_fact(value=Decimal("23636000000")),
    ]

    selected = select_quarterly_fact_with_filing_fallback(
        facts,
        [older_filing, FILING],
        Metric.NET_INCOME,
        OWNER,
        source_url_for_filing=_source_url,
    )

    assert selected[0].value == Decimal("23636000000")
    assert selected[0].end_date == REPORT_END


def test_filing_fallback_named_period_still_raises_ambiguous() -> None:
    older_filing = make_filing(
        accession_number=OLDER_ACCESSION,
        report_date=OLDER_END,
        filed_date=date(2024, 8, 1),
    )
    facts = [
        make_fact(
            accession_number=OLDER_ACCESSION,
            start_date=OLDER_START,
            end_date=OLDER_END,
            filed_date=date(2024, 8, 1),
            value=Decimal("100"),
        ),
        make_fact(
            accession_number=OLDER_ACCESSION,
            start_date=OLDER_START,
            end_date=OLDER_END,
            filed_date=date(2024, 8, 1),
            value=Decimal("200"),
        ),
    ]

    with pytest.raises(AmbiguousFactError):
        select_quarterly_fact_with_filing_fallback(
            facts,
            [older_filing, FILING],
            Metric.NET_INCOME,
            OWNER,
            source_url_for_filing=_source_url,
            report_date=OLDER_END,
        )


def test_a_standalone_quarter_runs_seventy_to_one_hundred_ten_days_inclusive() -> None:
    assert is_standalone_quarter(REPORT_END - timedelta(days=70), REPORT_END)
    assert is_standalone_quarter(REPORT_END - timedelta(days=110), REPORT_END)
    assert not is_standalone_quarter(REPORT_END - timedelta(days=69), REPORT_END)
    assert not is_standalone_quarter(REPORT_END - timedelta(days=111), REPORT_END)
    # An instant has no start, so it is not a quarter.
    assert not is_standalone_quarter(None, REPORT_END)
