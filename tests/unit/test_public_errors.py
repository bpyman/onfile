"""One policy decides which domain-error wording a visitor may read."""

from __future__ import annotations

import pytest

from financial_analyst_agent.domain import errors
from financial_analyst_agent.domain.errors import (
    AmbiguousCompanyError,
    CompanyNotFoundError,
    FinancialAnalystError,
    ProviderError,
    ProviderRefusal,
    RuntimeMismatchError,
    SessionQuotaError,
)


@pytest.mark.parametrize(
    "error_type",
    [
        ProviderRefusal,
        CompanyNotFoundError,
        AmbiguousCompanyError,
        SessionQuotaError,
        RuntimeMismatchError,
    ],
)
def test_only_errors_written_for_visitors_are_marked_public(
    error_type: type[FinancialAnalystError],
) -> None:
    assert getattr(error_type, "public", False) is True
    assert getattr(ProviderError, "public", False) is False


@pytest.mark.parametrize(
    "error",
    [
        ProviderRefusal("Provider refusal for the visitor"),
        CompanyNotFoundError("Company miss for the visitor"),
        AmbiguousCompanyError("Shared name for the visitor"),
        SessionQuotaError("Quota limit for the visitor"),
        RuntimeMismatchError("Runtime mismatch for the visitor"),
    ],
)
def test_visitor_message_uses_the_flag_and_the_callers_fallback(
    error: FinancialAnalystError,
) -> None:
    visitor_message = getattr(errors, "visitor_message", None)

    assert visitor_message is not None
    assert visitor_message(error, "Generic") == str(error)
    assert visitor_message(ProviderError("OpenAI 502 Bad Gateway"), "Generic") == "Generic"
    assert visitor_message(OSError("disk path"), "Generic") == "Generic"


@pytest.mark.parametrize(
    ("failure", "shown"),
    [
        (CompanyNotFoundError("No company called Acme"), "No company called Acme"),
        (ProviderRefusal("Recorded filings unavailable"), "Recorded filings unavailable"),
        (
            ProviderError("SEC payload path"),
            "SEC EDGAR could not be reached just now, so this could not be answered. "
            "Please try again in a few minutes.",
        ),
    ],
)
def test_request_resolution_applies_the_visitor_rule(
    monkeypatch: pytest.MonkeyPatch,
    failure: FinancialAnalystError,
    shown: str,
) -> None:
    from financial_analyst_agent.contracts import Intent
    from financial_analyst_agent.graph import spec_turn
    from financial_analyst_agent.graph.analysis_spec import SpecPatch
    from financial_analyst_agent.graph.state import StructuredRequest
    from financial_analyst_agent.runtime import recorded_runtime

    def fail(*_args: object, **_kwargs: object) -> None:
        raise failure

    monkeypatch.setattr(spec_turn, "materialize_period_dates", fail)
    request = StructuredRequest(
        patch=SpecPatch(
            mode="replace",
            add_companies=("Microsoft",),
            add_metrics=("revenue",),
        ),
        wording="Microsoft revenue over the last four quarters",
        question="Microsoft revenue over the last four quarters",
        intent=Intent.LOOKUP,
    )

    resolution = spec_turn.resolve_request(request, None, recorded_runtime())

    assert resolution.result is not None
    assert resolution.result.message == shown
