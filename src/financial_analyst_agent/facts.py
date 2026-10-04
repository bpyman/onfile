"""Offline SEC response replay through the production fact-selection path."""

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

from financial_analyst_agent.domain.errors import ProviderError, ProviderRefusal
from financial_analyst_agent.providers.sec.company_facts import validate_companyfacts_response
from financial_analyst_agent.providers.sec.submissions import validate_submissions_response
from financial_analyst_agent.providers.sec.tickers import require_usable_company_tickers

_RECORDING_PATH = Path(__file__).parent / "data" / "sec_fixture_recordings.json"


@lru_cache(maxsize=4)
def _load_recording(path: Path, _mtime_ns: int) -> dict[str, Any]:
    """Parse the cassette once per file version; every turn builds a new source.

    The parsed payload is shared and read-only.
    """
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ProviderError("Recorded SEC cassette must be a JSON object")
    return raw


class RecordedSECDataSource:
    """Read source-shaped SEC responses from the checked-in offline cassette."""

    def __init__(self, path: Path = _RECORDING_PATH) -> None:
        self._recording: dict[str, Any] = _load_recording(path, path.stat().st_mtime_ns)

    def close(self) -> None:
        return None

    def get_company_tickers(self) -> dict[str, Any]:
        return require_usable_company_tickers(self._recording.get("company_tickers"))

    def get_submissions(self, cik: str, *, with_history: bool = True) -> dict[str, Any]:
        # The cassette holds each filer's submissions as recorded; there are no pages to skip.
        payload = self._issuer_payload("submissions", cik)
        return validate_submissions_response(payload, cik, details={"cik": cik})

    def get_company_facts(self, cik: str) -> dict[str, Any]:
        payload = self._issuer_payload("company_facts", cik)
        return validate_companyfacts_response(payload, cik, details={"cik": cik})

    def get_filing_document(self, cik: str, accession: str, document: str) -> str:
        docs = self._recording.get("filing_documents")
        if not isinstance(docs, dict):
            raise ProviderError("Recorded SEC cassette missing filing_documents")
        payload = docs.get(f"{cik}:{accession}:{document}")
        if not isinstance(payload, str):
            raise ProviderRefusal(
                "No recorded filing document",
                details={"cik": cik, "accession": accession, "document": document},
            )
        return payload

    def _issuer_payload(self, section: str, cik: str) -> dict[str, Any]:
        payloads = self._recording.get(section)
        if not isinstance(payloads, dict):
            raise ProviderError(f"Recorded SEC cassette missing {section}")
        payload = payloads.get(cik)
        if not isinstance(payload, dict):
            raise ProviderError(
                "No recorded SEC response for issuer",
                details={"cik": cik, "status_code": 404},
            )
        return payload
