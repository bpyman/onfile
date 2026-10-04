"""Evidence addressed by identifier so thread checkpoints stay small.

Fetched facts, news hits, and turn results live here. Thread state holds only
references. Reuse across turns is the caller's responsibility to label.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import uuid
from datetime import date
from pathlib import Path
from typing import Any, Literal, Protocol
from urllib.parse import quote, unquote

from pydantic import BaseModel, Field

from financial_analyst_agent.contracts import (
    QUALITATIVE_INTENTS,
    FactsPort,
    NewsHit,
    TurnResult,
)
from financial_analyst_agent.domain.models import FinancialFact
from financial_analyst_agent.services.fiscal_periods import FiscalPeriod

EvidenceKind = Literal["fact", "news", "result"]

class EvidenceRecord(BaseModel):
    evidence_id: str
    kind: EvidenceKind
    payload: dict[str, Any] = Field(default_factory=dict)


def fact_evidence_id(
    company: str, metric: str, report_date: date | None = None
) -> str:
    """Stable id so the same cell reuses across turns without refetching."""
    period = report_date.isoformat() if report_date is not None else "latest"
    raw = f"fact|{company.casefold()}|{metric}|{period}"
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]
    return f"fact-{digest}"


def news_evidence_id(url: str) -> str:
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:24]
    return f"news-{digest}"


def _fact_to_payload(fact: Any) -> dict[str, Any]:
    # Validated on the way in, so a cache hit reads back as the same FinancialFact.
    return FinancialFact.model_validate(fact, from_attributes=True).model_dump(mode="json")


def _payload_to_fact(payload: dict[str, Any]) -> FinancialFact:
    # A cache hit is the same FinancialFact the facts port returned (ADR 0003).
    return FinancialFact.model_validate(payload)


class EvidenceStore(Protocol):
    def has(self, evidence_id: str) -> bool: ...

    def put_fact(
        self,
        company: str,
        metric: str,
        fact: Any,
        *,
        report_date: date | None = None,
    ) -> str: ...

    def get_fact(self, evidence_id: str) -> Any: ...

    def put_news(self, hit: NewsHit) -> str: ...

    def get_news(self, evidence_id: str) -> NewsHit: ...

    def put_result(self, result: TurnResult) -> str: ...

    def get_result(self, evidence_id: str) -> TurnResult: ...

    def known_ids(self) -> frozenset[str]: ...


class _RecordStore:
    """Typed evidence methods over a subclass's raw ``_write`` / ``_read``."""

    def _write(self, record: EvidenceRecord) -> None:
        raise NotImplementedError

    def _read(self, evidence_id: str) -> EvidenceRecord:
        """Return the record or raise ``KeyError``."""
        raise NotImplementedError

    def _put(self, evidence_id: str, kind: EvidenceKind, payload: dict[str, Any]) -> str:
        self._write(EvidenceRecord(evidence_id=evidence_id, kind=kind, payload=payload))
        return evidence_id

    def _payload(self, evidence_id: str, kind: EvidenceKind) -> dict[str, Any]:
        record = self._read(evidence_id)
        if record.kind != kind:
            raise KeyError(evidence_id)
        return record.payload

    def put_fact(
        self,
        company: str,
        metric: str,
        fact: Any,
        *,
        report_date: date | None = None,
    ) -> str:
        evidence_id = fact_evidence_id(company, metric, report_date)
        return self._put(evidence_id, "fact", _fact_to_payload(fact))

    def get_fact(self, evidence_id: str) -> Any:
        return _payload_to_fact(self._payload(evidence_id, "fact"))

    def put_news(self, hit: NewsHit) -> str:
        return self._put(news_evidence_id(hit.url), "news", hit.model_dump(mode="json"))

    def get_news(self, evidence_id: str) -> NewsHit:
        return NewsHit.model_validate(self._payload(evidence_id, "news"))

    def put_result(self, result: TurnResult) -> str:
        evidence_id = f"result-{uuid.uuid4().hex[:16]}"
        return self._put(evidence_id, "result", result.model_dump(mode="json"))

    def get_result(self, evidence_id: str) -> TurnResult:
        return TurnResult.model_validate(self._payload(evidence_id, "result"))


class InMemoryEvidenceStore(_RecordStore):
    """Process-local evidence for ephemeral conversation threads."""

    def __init__(self) -> None:
        self._records: dict[str, EvidenceRecord] = {}

    def has(self, evidence_id: str) -> bool:
        return evidence_id in self._records

    def known_ids(self) -> frozenset[str]:
        return frozenset(self._records)

    def _write(self, record: EvidenceRecord) -> None:
        self._records[record.evidence_id] = record

    def _read(self, evidence_id: str) -> EvidenceRecord:
        return self._records[evidence_id]


class LocalEvidenceStore(_RecordStore):
    """JSON files under a directory, one record per evidence id."""

    def __init__(self, root: Path) -> None:
        self._root = root
        self._root.mkdir(parents=True, exist_ok=True)

    def _path(self, evidence_id: str) -> Path:
        return self._root / f"{quote(evidence_id, safe='')}.json"

    def has(self, evidence_id: str) -> bool:
        return self._path(evidence_id).is_file()

    def known_ids(self) -> frozenset[str]:
        # The filename is the quoted id (temp files end in .tmp), so listing reads no files.
        return frozenset(unquote(path.stem) for path in self._root.glob("*.json"))

    def _write(self, record: EvidenceRecord) -> None:
        """Write the whole record or nothing: a reader never sees a torn file."""
        path = self._path(record.evidence_id)
        temp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
        try:
            temp.write_text(record.model_dump_json(), encoding="utf-8")
            os.replace(temp, path)
        except BaseException:
            temp.unlink(missing_ok=True)
            raise

    def _read(self, evidence_id: str) -> EvidenceRecord:
        path = self._path(evidence_id)
        if not path.is_file():
            raise KeyError(evidence_id)
        return EvidenceRecord.model_validate_json(path.read_text(encoding="utf-8"))


class EvidenceCachedFacts:
    """FactsPort wrapper: retain fetched facts and serve them by identifier.

    Ids present before this turn are thread evidence (label reuse). Ids written
    during this turn are run-state cache (no cross-turn label).
    """

    def __init__(
        self,
        inner: FactsPort,
        store: EvidenceStore,
        *,
        prior_ids: frozenset[str],
    ) -> None:
        self._inner = inner
        self._store = store
        self._prior_ids = prior_ids
        self._lock = threading.Lock()
        self.reused_ids: set[str] = set()

    def get_financials(
        self,
        company: str,
        metric: str,
        *,
        report_date: date | None = None,
    ) -> Any:
        evidence_id = fact_evidence_id(company, metric, report_date)
        with self._lock:
            cached = self._store.has(evidence_id)
            if cached:
                if evidence_id in self._prior_ids:
                    self.reused_ids.add(evidence_id)
                return self._store.get_fact(evidence_id)
        fetched = self._inner.get_financials(company, metric, report_date=report_date)
        # The port returns a FinancialFact (ADR 0003), fresh or cached alike.
        fact = FinancialFact.model_validate(fetched, from_attributes=True)
        with self._lock:
            if not self._store.has(evidence_id):
                self._store.put_fact(company, metric, fact, report_date=report_date)
            elif evidence_id in self._prior_ids:
                self.reused_ids.add(evidence_id)
                return self._store.get_fact(evidence_id)
        return fact

    def list_quarterly_report_dates(self, company: str, *, limit: int) -> tuple[date, ...]:
        return self._inner.list_quarterly_report_dates(company, limit=limit)

    def files_quarterly(self, company: str) -> tuple[bool, str]:
        return self._inner.files_quarterly(company)

    def fiscal_periods(self, company: str) -> tuple[FiscalPeriod, ...]:
        return self._inner.fiscal_periods(company)

    def display_name(self, cik: str, fallback: str) -> str:
        return self._inner.display_name(cik, fallback)


def with_banner(result: TurnResult, banner: str) -> TurnResult:
    """Append ``banner`` once."""
    if banner in result.banners:
        return result
    return result.model_copy(update={"banners": [*result.banners, banner]})


def label_reused_evidence(result: TurnResult, *, reused: bool) -> TurnResult:
    return result.model_copy(update={"reused_evidence": True}) if reused else result


def retain_result_evidence(store: EvidenceStore, result: TurnResult) -> str:
    """Persist news hits (by url) and the turn result; return the result id."""
    for hit in result.citations:
        store.put_news(hit)
    return store.put_result(result)


def grounding_json_from_result(result: TurnResult | None) -> str:
    """Deterministic analysis payload for a later qualitative numeral lock.

    News and model-analysis essays are not analysis numbers; passing them as
    essay tool JSON makes a later explain treat them as the news set.
    """
    if result is None:
        return ""
    if result.intent in QUALITATIVE_INTENTS:
        return ""
    if not result.table_rows:
        return ""
    return json.dumps(
        [row.model_dump(mode="json") for row in result.table_rows],
        default=str,
    )
