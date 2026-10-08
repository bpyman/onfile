"""A TableRow knows which company it belongs to and what to call it in a sentence."""

from __future__ import annotations

from financial_analyst_agent.contracts import (
    COMPANY_NOT_FOUND,
    NO_DIVIDEND_THIS_QUARTER,
    NOT_REPORTED_FOR_QUARTER,
    Intent,
    TableRow,
    refuse_unknown_metric,
)
from financial_analyst_agent.domain.errors import (
    CompanyNotFoundError,
    NoDividendThisQuarterError,
    PerShareNotDerivableError,
    UnknownMetricError,
)


def _row(company_name: str, cik: str) -> TableRow:
    return TableRow(company_name=company_name, ticker="", cik=cik, metric="revenue")


def test_a_row_is_keyed_by_its_cik_or_by_the_name_sec_does_not_know() -> None:
    assert _row("Microsoft Corporation", "0000789019").company_key == "0000789019"
    assert _row("Acme Widgets", "").company_key == "Acme Widgets"


def test_a_row_s_short_name_drops_the_legal_suffix_or_keeps_the_whole_name() -> None:
    assert _row("Microsoft Corporation", "0000789019").short == "Microsoft"
    assert _row("The Goldman Sachs Group, Inc.", "0000886982").short == "Goldman Sachs"
    assert _row("Acme Widgets", "").short == "Acme Widgets"


def test_the_window_s_reason_codes_are_the_error_classes_codes() -> None:
    # Cells carry the reason constant; refusals carry the error class's code. The
    # window labels both by one key, so the two spellings must agree.
    assert CompanyNotFoundError.code == COMPANY_NOT_FOUND
    assert PerShareNotDerivableError.code == NOT_REPORTED_FOR_QUARTER
    assert NoDividendThisQuarterError.code == NO_DIVIDEND_THIS_QUARTER
    assert refuse_unknown_metric(Intent.LOOKUP, "costs").refusal is not None
    assert refuse_unknown_metric(Intent.LOOKUP, "costs").refusal.code == UnknownMetricError.code
