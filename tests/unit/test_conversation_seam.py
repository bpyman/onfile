"""Conversation seam: thread id + message + runtime → typed conversation turn.

Asserts persistence at the public seam against a real temporary store.
Does not assert checkpointer payloads or LangGraph internals.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from financial_analyst_agent.contracts import WorkflowPlan
from financial_analyst_agent.runtime import FIXTURE_EXPLAIN_ESSAY


class _LookupFacts:
    def get_financials(
        self, company: str, metric: str, *, report_date: date | None = None
    ) -> SimpleNamespace:
        assert company == "Google"
        assert metric == "net_income"
        return SimpleNamespace(
            company_name="Alphabet Inc.",
            ticker="GOOG",
            cik="0001652044",
            metric="net_income",
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


class _LookupCompleter:
    def complete(self, query: str, current_spec: object = None) -> WorkflowPlan:
        from financial_analyst_agent.contracts import Intent

        return WorkflowPlan(
            intent=Intent.LOOKUP,
            company="Google",
            metric="net_income",
            industry=None,
            topic=None,
        )


class _ExplainCompleter:
    def complete(self, query: str, current_spec: object = None) -> WorkflowPlan:
        from financial_analyst_agent.contracts import Intent

        return WorkflowPlan(
            intent=Intent.EXPLAIN,
            company=None,
            metric=None,
            industry=None,
            topic="AI disruption in healthcare",
        )


class _NumberFreeEssay:
    def complete_essay(self, query: str, tool_json: str = "") -> str:
        return FIXTURE_EXPLAIN_ESSAY


def _runtime(
    *, completer: object, facts: object | None = None, essay: object | None = None
) -> object:
    from financial_analyst_agent.contracts import Runtime

    return Runtime(
        completer=completer,  # type: ignore[arg-type]
        facts=(facts or _LookupFacts()),  # type: ignore[arg-type]
        essay=essay,  # type: ignore[arg-type]
    )


def test_conversation_seam_returns_typed_turn(tmp_path: Path) -> None:
    from financial_analyst_agent.contracts import Intent, RendererKind, TurnResult
    from financial_analyst_agent.conversation import ConversationTurn, run_conversation_turn
    from financial_analyst_agent.thread_store import LocalThreadStore

    store = LocalThreadStore(tmp_path)
    message = "What was Google's net income based on their latest quarterly report?"
    turn = run_conversation_turn(
        "thread-a",
        message,
        _runtime(completer=_LookupCompleter()),  # type: ignore[arg-type]
        store=store,
    )

    assert isinstance(turn, ConversationTurn)
    assert turn.thread_id == "thread-a"
    assert isinstance(turn.result, TurnResult)
    assert turn.result.intent is Intent.LOOKUP
    assert turn.result.renderer is RendererKind.TABLE
    assert turn.result.table_rows[0].ticker == "GOOG"
    assert [m.content for m in turn.messages] == [message]
    assert turn.results == (turn.result,)
    assert turn.last_result == turn.result


def test_same_thread_sees_prior_turn_different_thread_starts_clean(tmp_path: Path) -> None:
    from financial_analyst_agent.contracts import Intent
    from financial_analyst_agent.conversation import run_conversation_turn
    from financial_analyst_agent.thread_store import LocalThreadStore

    store = LocalThreadStore(tmp_path)
    first = "What was Google's net income based on their latest quarterly report?"
    second = "How can AI disrupt healthcare?"

    turn1 = run_conversation_turn(
        "thread-a",
        first,
        _runtime(completer=_LookupCompleter()),  # type: ignore[arg-type]
        store=store,
    )
    assert turn1.result.intent is Intent.LOOKUP

    turn2 = run_conversation_turn(
        "thread-a",
        second,
        _runtime(completer=_ExplainCompleter(), essay=_NumberFreeEssay()),  # type: ignore[arg-type]
        store=store,
    )
    assert [m.content for m in turn2.messages] == [first, second]
    assert turn2.results == (turn1.result, turn2.result)
    assert turn2.result.intent is Intent.EXPLAIN

    other = run_conversation_turn(
        "thread-b",
        second,
        _runtime(completer=_ExplainCompleter(), essay=_NumberFreeEssay()),  # type: ignore[arg-type]
        store=store,
    )
    assert [m.content for m in other.messages] == [second]
    assert other.thread_id == "thread-b"


def test_thread_state_survives_process_restart(tmp_path: Path) -> None:
    from financial_analyst_agent.conversation import run_conversation_turn
    from financial_analyst_agent.thread_store import LocalThreadStore

    message = "What was Google's net income based on their latest quarterly report?"
    store1 = LocalThreadStore(tmp_path)
    run_conversation_turn(
        "thread-a",
        message,
        _runtime(completer=_LookupCompleter()),  # type: ignore[arg-type]
        store=store1,
    )

    # New store instance over the same durable root (new process).
    store2 = LocalThreadStore(tmp_path)
    follow_up = "How can AI disrupt healthcare?"
    turn = run_conversation_turn(
        "thread-a",
        follow_up,
        _runtime(completer=_ExplainCompleter(), essay=_NumberFreeEssay()),  # type: ignore[arg-type]
        store=store2,
    )
    assert [m.content for m in turn.messages] == [message, follow_up]
    assert turn.last_result.intent.value == "explain"


def test_run_state_is_not_persisted_between_turns(tmp_path: Path) -> None:
    from financial_analyst_agent.conversation import run_conversation_turn
    from financial_analyst_agent.thread_store import LocalThreadStore, ThreadState

    store = LocalThreadStore(tmp_path)
    run_conversation_turn(
        "thread-a",
        "What was Google's net income based on their latest quarterly report?",
        _runtime(completer=_LookupCompleter()),  # type: ignore[arg-type]
        store=store,
    )
    state = store.load("thread-a")
    assert isinstance(state, ThreadState)
    dumped = state.model_dump()
    assert {
        "thread_id",
        "messages",
        "evidence_refs",
        "last_result_ref",
        "analysis_spec",
        "checkpoint",
    } <= set(dumped)
    assert set(dumped) <= {
        "thread_id",
        "runtime",
        "messages",
        "evidence_refs",
        "last_result_ref",
        "analysis_spec",
        "checkpoint",
        "updated_at",
        "turn_count",
        "live_sec_requests",
    }
    # A finished turn leaves no paused graph run behind.
    assert dumped["checkpoint"] is None
    assert state.pending_clarification is None
    assert len(state.evidence_refs) >= 1
    assert state.last_result_ref is not None
    assert store.resolve_last_result(state) is not None
    assert "plan" not in dumped
    # Only the runtime's name is thread state; its providers are not.
    assert dumped["runtime"] == "recorded"
    assert "compiled_tasks" not in dumped
    assert "proposed_patch" not in dumped


def test_clearing_a_thread_forgets_prior_turns(tmp_path: Path) -> None:
    from financial_analyst_agent.conversation import run_conversation_turn
    from financial_analyst_agent.thread_store import LocalThreadStore

    message = "What was Google's net income based on their latest quarterly report?"
    store = LocalThreadStore(tmp_path)
    run_conversation_turn(
        "thread-a",
        message,
        _runtime(completer=_LookupCompleter()),  # type: ignore[arg-type]
        store=store,
    )
    prior = store.load("thread-a")
    assert prior is not None
    assert prior.messages
    assert store.resolve_last_result(prior) is not None

    store.clear("thread-a")

    assert store.load("thread-a") is None
    restarted = LocalThreadStore(tmp_path)
    assert restarted.load("thread-a") is None
    turn = run_conversation_turn(
        "thread-a",
        "How can AI disrupt healthcare?",
        _runtime(completer=_ExplainCompleter(), essay=_NumberFreeEssay()),  # type: ignore[arg-type]
        store=restarted,
    )
    assert [m.content for m in turn.messages] == ["How can AI disrupt healthcare?"]
    assert turn.last_result.intent.value == "explain"


def test_run_turn_is_ephemeral_thread_wrapper() -> None:
    from financial_analyst_agent.contracts import Intent, RendererKind, TurnResult
    from financial_analyst_agent.turn import run_turn

    result = run_turn(
        "What was Google's net income based on their latest quarterly report?",
        _runtime(completer=_LookupCompleter()),  # type: ignore[arg-type]
    )
    assert isinstance(result, TurnResult)
    assert result.intent is Intent.LOOKUP
    assert result.renderer is RendererKind.TABLE
    assert result.table_rows[0].value == Decimal("62578000000")
