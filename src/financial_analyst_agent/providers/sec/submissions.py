"""Parse SEC submissions JSON into Filing models."""

import re
from datetime import date
from typing import Any

from financial_analyst_agent.domain.enums import PERIODIC_FORMS
from financial_analyst_agent.domain.errors import ProviderError
from financial_analyst_agent.domain.models import Filing
from financial_analyst_agent.providers.sec.identity import require_matching_payload_cik

# An SEC accession number: "0000320193-26-000013".
ACCESSION_PATTERN = re.compile(r"\d{10}-\d{2}-\d{6}")
_DOMESTIC_PERIODIC_FORMS = frozenset({"10-K", "10-KT", "10-Q", "10-QT"})
_FOREIGN_ANNUAL_FORMS = frozenset({"20-F", "40-F"})
# Only foreign private issuers furnish 6-Ks or register on a 20-F/40-F.
_FOREIGN_ONLY_FORMS = frozenset({"6-K", "20FR12B", "20FR12G", "40FR12B", "40FR12G"})


def require_matching_submissions_cik(payload: dict[str, Any], cik: str) -> dict[str, Any]:
    """Validate that a submissions payload reports the requested issuer CIK."""
    require_matching_payload_cik(
        payload,
        cik,
        message="submissions response identity does not match the requested CIK",
    )
    return payload


def require_submissions_structure(
    payload: dict[str, Any],
    *,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Validate the submissions container. Structure problems are availability failures."""
    error_details = details or {}
    if "filings" not in payload:
        raise ProviderError("submissions response missing filings", details=error_details)
    if not isinstance(payload["filings"], dict):
        raise ProviderError("submissions response filings must be an object", details=error_details)
    return payload


def validate_submissions_response(
    payload: dict[str, Any],
    cik: str,
    *,
    details: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Validated-retrieval boundary for submissions: identity first, then structure.

    Ordering matters. A response describing another issuer is an integrity violation
    even when its filing arrays are also malformed, so it must never be reported as
    issuer unavailability or converted into a partial item failure.
    """
    require_matching_submissions_cik(payload, cik)
    return require_submissions_structure(payload, details=details)


def files_quarterly_reports(payload: dict[str, Any]) -> bool:
    """False when the issuer's latest periodic report is a 20-F or 40-F.

    Foreign private issuers report annually on 20-F/40-F and furnish 6-Ks, so
    they have no 10-Q facts to rank on. Judging by the latest report keeps
    issuers that switched to 10-K/10-Q, and drops ones that switched away;
    amendments are ignored so a late 20-F/A cannot outrank a newer 10-Q.

    A newly listed foreign issuer has no annual report yet, so with no periodic
    report at all a 6-K or 20-F registration still marks it foreign. Otherwise
    it gets the benefit of the doubt: large banks' prospectus supplements can
    crowd their 10-Qs out of the recent list.
    """
    filings = payload.get("filings")
    recent = filings.get("recent") if isinstance(filings, dict) else None
    if not isinstance(recent, dict):
        return True
    forms = recent.get("form")
    dates = recent.get("filingDate")
    if not isinstance(forms, list) or not isinstance(dates, list):
        return True
    periodic = [
        (str(filed), form in _DOMESTIC_PERIODIC_FORMS)
        for form, filed in zip(forms, dates, strict=False)
        if form in _DOMESTIC_PERIODIC_FORMS or form in _FOREIGN_ANNUAL_FORMS
    ]
    if not periodic:
        return _FOREIGN_ONLY_FORMS.isdisjoint(forms)
    _filed, domestic = max(periodic)
    return domestic


# What a lookup reads of a submissions list: the periodic reports, the foreign
# forms that mark a 20-F filer, and the columns that describe a report.
_KEPT_FORMS = (
    PERIODIC_FORMS | _DOMESTIC_PERIODIC_FORMS | _FOREIGN_ANNUAL_FORMS | _FOREIGN_ONLY_FORMS
)
KEPT_COLUMNS = ("form", "accessionNumber", "filingDate", "reportDate", "primaryDocument")


def trim_submissions(payload: dict[str, Any]) -> dict[str, Any]:
    """Submissions with only the rows and columns ``parse_submissions`` and
    ``files_quarterly_reports`` read.

    A bank's list holds thousands of prospectus rows in two dozen columns, and
    a ranking keeps 25 lists for its whole turn. A list whose columns do not
    line up is returned as it is, for the parser to report.
    """
    filings = payload.get("filings")
    recent = filings.get("recent") if isinstance(filings, dict) else None
    forms = recent.get("form") if isinstance(recent, dict) else None
    if not isinstance(recent, dict) or not isinstance(forms, list):
        return payload
    columns = {name: recent.get(name) for name in KEPT_COLUMNS}
    if any(not isinstance(form, str) for form in forms) or any(
        not isinstance(values, list) or len(values) != len(forms) for values in columns.values()
    ):
        return payload
    keep = [index for index, form in enumerate(forms) if form in _KEPT_FORMS]
    trimmed = {
        name: [values[index] for index in keep]
        for name, values in columns.items()
        if isinstance(values, list)
    }
    return {"cik": payload.get("cik"), "filings": {"recent": trimmed}}


def require_recent_filings(payload: object) -> dict[str, Any]:
    """Return the ``filings.recent`` object of a submissions payload."""
    filings_section = payload.get("filings") if isinstance(payload, dict) else None
    if not isinstance(filings_section, dict):
        raise ProviderError("submissions payload missing filings object")

    recent = filings_section.get("recent")
    if not isinstance(recent, dict):
        raise ProviderError("submissions payload missing filings.recent object")
    return recent


def parse_submissions(payload: dict[str, Any]) -> list[Filing]:
    """Parse 10-Q and 10-K filings from a SEC submissions response."""
    recent = require_recent_filings(payload)

    forms = recent.get("form")
    if not isinstance(forms, list):
        raise ProviderError("submissions recent.form must be a list")

    expected_length = len(forms)
    accession_numbers = _require_recent_list(recent, "accessionNumber", expected_length)
    filing_dates = _require_recent_list(recent, "filingDate", expected_length)
    report_dates = _require_recent_list(recent, "reportDate", expected_length)
    primary_documents = _require_recent_list(recent, "primaryDocument", expected_length)

    filings: list[Filing] = []
    for index, raw_form in enumerate(forms):
        # Every provider-supplied field is type-checked before use, so malformed data
        # raises the sanitized provider boundary error instead of a built-in TypeError.
        form = _require_provider_string(raw_form, "form", index)
        if form not in PERIODIC_FORMS:
            continue
        accession_number = _require_provider_string(
            accession_numbers[index], "accessionNumber", index
        )
        if not ACCESSION_PATTERN.fullmatch(accession_number):
            continue
        filed_date = _parse_iso_date(filing_dates[index], "filingDate", index)
        report_date = _parse_iso_date(report_dates[index], "reportDate", index)
        primary_document = _require_optional_provider_string(
            primary_documents[index], "primaryDocument", index
        )
        filings.append(
            Filing(
                form=form,
                accession_number=accession_number,
                filed_date=filed_date,
                report_date=report_date,
                primary_document=primary_document,
            )
        )
    return filings


def _require_recent_list(
    recent: dict[str, Any],
    field_name: str,
    expected_length: int,
) -> list[Any]:
    values = recent.get(field_name)
    if not isinstance(values, list):
        raise ProviderError(f"submissions recent.{field_name} must be a list")
    if len(values) != expected_length:
        raise ProviderError(
            f"submissions recent.{field_name} length mismatch",
            details={"field": field_name, "expected": expected_length, "actual": len(values)},
        )
    return values


def _require_provider_string(value: object, field_name: str, index: int) -> str:
    """Require an exact string. ``bool`` and numbers are rejected, never coerced."""
    if not isinstance(value, str):
        raise ProviderError(
            f"submissions recent.{field_name} must be a string",
            details={"field": field_name, "index": index, "value_type": type(value).__name__},
        )
    return value


def _require_optional_provider_string(value: object, field_name: str, index: int) -> str | None:
    if value is None:
        return None
    return _require_provider_string(value, field_name, index)


def _parse_iso_date(value: object, field_name: str, index: int) -> date:
    text = _require_provider_string(value, field_name, index)
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        # Raw provider values never enter client-facing details.
        raise ProviderError(
            f"invalid ISO date for {field_name} at index {index}",
            details={"field": field_name, "index": index},
        ) from exc
