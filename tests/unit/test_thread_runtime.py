"""A conversation thread is bound to one runtime (ADR 0006), enforced by the conversation seam.

Package imports stay inside functions: ``test_contracts_import`` drops the package from
``sys.modules``, so module-level enum imports would go stale in a full run.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING

import pytest

from financial_analyst_agent.contracts import WorkflowPlan

if TYPE_CHECKING:
    from financial_analyst_agent.contracts import Runtime
    from financial_analyst_agent.thread_store import LocalThreadStore

QUESTION = "What was Google's net income based on their latest quarterly report?"


class _Facts:
    def get_financials(
        self, company: str, metric: str, *, report_date: date | None = None
    ) -> SimpleNamespace:
        return SimpleNamespace(
            company_name="Alphabet Inc.",
            ticker="GOOG",
            cik="0001652044",
            metric=metric,
            value=Decimal("62578000000"),
            currency="USD",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 3, 31),
            filed_date=date(2026, 3, 31),
            form="10-Q",
            accession_number="0001652044-26-000048",
            taxonomy="us-gaap",
            concept="NetIncomeLoss",
            source_url="https://www.sec.gov/example.htm",
            source="sec_xbrl",
        )


class _Completer:
    def complete(self, query: str, current_spec: object = None) -> WorkflowPlan:
        from financial_analyst_agent.contracts import Intent

        return WorkflowPlan(
            intent=Intent.LOOKUP,
            company="Google",
            metric="net_income",
            industry=None,
            topic=None,
        )


def _runtime(kind: str) -> Runtime:
    from financial_analyst_agent.contracts import Runtime, RuntimeKind

    runtime = Runtime(completer=_Completer(), facts=_Facts())  # type: ignore[arg-type]
    return replace(runtime, kind=RuntimeKind(kind))


def _store(root: Path) -> LocalThreadStore:
    from financial_analyst_agent.thread_store import LocalThreadStore

    return LocalThreadStore(root)


def test_first_turn_binds_the_thread_to_its_runtime(tmp_path: Path) -> None:
    from financial_analyst_agent.conversation import run_conversation_turn

    store = _store(tmp_path)

    run_conversation_turn("t1", QUESTION, _runtime("recorded"), store=store)

    state = store.load("t1")
    assert state is not None
    assert state.runtime == "recorded"
    again = run_conversation_turn("t1", "add Apple", _runtime("recorded"), store=store)
    assert len(again.messages) == 2


def test_turn_on_the_other_runtime_is_refused_and_nothing_is_persisted(
    tmp_path: Path,
) -> None:
    from financial_analyst_agent.conversation import run_conversation_turn
    from financial_analyst_agent.domain.errors import RuntimeMismatchError

    store = _store(tmp_path)
    run_conversation_turn("t1", QUESTION, _runtime("recorded"), store=store)
    before = store.load("t1")
    evidence_before = store.evidence_for("t1").known_ids()

    with pytest.raises(RuntimeMismatchError) as caught:
        run_conversation_turn("t1", "add Apple", _runtime("live"), store=store)

    assert caught.value.details == {"thread": "recorded", "turn": "live"}
    assert _store(tmp_path).load("t1") == before
    assert store.evidence_for("t1").known_ids() == evidence_before


def test_started_thread_is_bound_before_its_first_turn(tmp_path: Path) -> None:
    from financial_analyst_agent.contracts import RuntimeKind
    from financial_analyst_agent.conversation import run_conversation_turn, start_thread
    from financial_analyst_agent.domain.errors import RuntimeMismatchError

    store = _store(tmp_path)

    started = start_thread("t1", RuntimeKind.LIVE, store=store)

    assert started.runtime == "live"
    assert started.turn_count == 0
    with pytest.raises(RuntimeMismatchError):
        run_conversation_turn("t1", QUESTION, _runtime("recorded"), store=store)
    assert store.load("t1") == started
    turn = run_conversation_turn("t1", QUESTION, _runtime("live"), store=store)
    assert [m.content for m in turn.messages] == [QUESTION]


def test_thread_saved_before_binding_binds_on_its_next_turn(tmp_path: Path) -> None:
    from financial_analyst_agent.conversation import run_conversation_turn
    from financial_analyst_agent.domain.errors import RuntimeMismatchError
    from financial_analyst_agent.thread_store import ThreadState

    store = _store(tmp_path)
    # A checkpoint written before binding existed has no "runtime" key at all.
    legacy = ThreadState(thread_id="t1", turn_count=1).model_dump_json(exclude={"runtime"})
    assert "runtime" not in legacy
    (tmp_path / "t1.json").write_text(legacy, encoding="utf-8")
    saved = store.load("t1")
    assert saved is not None
    assert saved.runtime is None

    run_conversation_turn("t1", QUESTION, _runtime("live"), store=store)

    rebound = store.load("t1")
    assert rebound is not None
    assert rebound.runtime == "live"
    with pytest.raises(RuntimeMismatchError):
        run_conversation_turn("t1", "add Apple", _runtime("recorded"), store=store)
