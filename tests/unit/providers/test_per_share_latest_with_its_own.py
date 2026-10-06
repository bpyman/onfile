"""A per-share figure with no period: the latest quarter that has its own (ADR 0007).

Per-share figures are never derived, so a fiscal fourth quarter has none of its
own. Asked with no period, the answer steps back to the latest quarter whose
filing reports one, and says which quarter it stepped past. A named fourth
quarter still says it is reported only for the year.
"""

from datetime import date
from decimal import Decimal

import pytest

from financial_analyst_agent.domain.errors import PerShareNotDerivableError

CISCO_FOURTH_QUARTER_END = date(2026, 7, 25)
CISCO_THIRD_QUARTER_END = date(2026, 4, 25)


@pytest.fixture
def facts():  # type: ignore[no-untyped-def]
    from financial_analyst_agent.runtime import recorded_runtime

    return recorded_runtime().facts


def test_eps_with_no_period_is_the_latest_quarter_with_its_own(facts) -> None:  # type: ignore[no-untyped-def]
    # Cisco's latest report is its 10-K for the year to Jul 25, 2026, whose
    # fourth quarter reports EPS only inside the year's figure.
    fact = facts.get_financials("CSCO", "eps_diluted")

    assert fact.end_date == CISCO_THIRD_QUARTER_END
    assert fact.value == Decimal("0.85")
    assert fact.year_only_quarter_end == CISCO_FOURTH_QUARTER_END
    assert fact.newer_filing_end is None


def test_a_named_fourth_quarter_still_says_it_is_reported_for_the_year(facts) -> None:  # type: ignore[no-untyped-def]
    with pytest.raises(PerShareNotDerivableError):
        facts.get_financials("CSCO", "eps_diluted", report_date=CISCO_FOURTH_QUARTER_END)


def test_a_latest_quarter_with_its_own_eps_is_unchanged(facts) -> None:  # type: ignore[no-untyped-def]
    fact = facts.get_financials("AAPL", "eps_diluted")

    assert fact.end_date == date(2026, 6, 27)
    assert fact.year_only_quarter_end is None
