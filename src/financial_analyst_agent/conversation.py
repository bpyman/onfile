"""Conversation seam: thread identifier + analyst message + runtime → typed turn.

The turn itself is the analysis graph (``graph.turn_graph``). This seam owns
the thread around it: it loads the thread record, hands the graph its
per-turn context (providers wrapped with the thread's evidence cache, the
active analysis spec, the last answer's rows on demand), and saves what the
turn leaves: the message, the answer by evidence reference, the analysis the
thread keeps, and, while a clarification is open, the graph's paused run.

Pending clarification is the graph paused on ``interrupt``: an ambiguous
metric or ambiguous extend/replace scope holds the planned patch until the
analyst answers (``Command(resume=...)``) or asks something unrelated, which
discards it explicitly and is said on the answer.

A thread is bound to one runtime (ADR 0006): ``start_thread`` binds it up front,
otherwise its first turn does. A turn on the other runtime raises
``RuntimeMismatchError`` before anything is read from providers or persisted.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime

from pydantic import BaseModel

from financial_analyst_agent.contracts import (
    RendererKind,
    Runtime,
    RuntimeKind,
    TurnResult,
)
from financial_analyst_agent.domain.errors import RuntimeMismatchError
from financial_analyst_agent.evidence_store import (
    EvidenceCachedFacts,
    grounding_json_from_result,
    label_reused_evidence,
    retain_result_evidence,
    with_banner,
)
from financial_analyst_agent.graph.analysis_spec import AnalysisSpec, SpecPatch
from financial_analyst_agent.graph.spec_turn import DEFAULT_TASK_MAX_WORKERS
from financial_analyst_agent.graph.state import TurnDeps
from financial_analyst_agent.graph.turn_graph import run_analysis
from financial_analyst_agent.guide import suggest_follow_ups
from financial_analyst_agent.issuer_index import plain_text
from financial_analyst_agent.observability import (
    bind_log_context,
    reset_log_context,
    timed,
)
from financial_analyst_agent.thread_store import (
    ThreadMessage,
    ThreadState,
    ThreadStore,
)

DISCARDED_CLARIFICATION_BANNER = (
    "Answered your new question; the earlier one that needed a choice was set aside."
)


class ConversationTurn(BaseModel):
    thread_id: str
    result: TurnResult
    messages: tuple[ThreadMessage, ...] = ()
    analysis_spec: AnalysisSpec | None = None
    proposed_patch: SpecPatch | None = None


def _says_set_aside(result: TurnResult, previous: TurnResult | None) -> bool:
    """The set-aside note goes on an answer, once: not on a refusal, guide, question or repeat."""
    if result.renderer in (RendererKind.REFUSE, RendererKind.CLARIFY) or result.guide:
        return False
    return previous is None or DISCARDED_CLARIFICATION_BANNER not in previous.banners


def start_thread(thread_id: str, runtime: RuntimeKind, *, store: ThreadStore) -> ThreadState:
    """Create an empty conversation thread bound to ``runtime`` and persist it."""
    state = ThreadState(thread_id=thread_id, runtime=runtime)
    store.save(state)
    return state


def _check_runtime(prior: ThreadState, runtime: Runtime) -> None:
    if prior.runtime is not None and prior.runtime != runtime.kind:
        raise RuntimeMismatchError(
            f"This thread runs on the {prior.runtime.value} runtime and cannot take "
            f"a {runtime.kind.value} turn. Start over to switch runtime.",
            {"thread": prior.runtime.value, "turn": runtime.kind.value},
        )


def run_conversation_turn(
    thread_id: str,
    message: str,
    runtime: Runtime,
    *,
    store: ThreadStore,
    on_progress: Callable[[int, int], None] | None = None,
    max_workers: int | None = None,
) -> ConversationTurn:
    """Run one analyst message on a conversation thread and persist thread state.

    ``on_progress(done, total)`` is invoked as independent compiled cells finish.
    ``max_workers`` caps concurrent provider fan-out for structured analyses.
    Raises ``RuntimeMismatchError`` when the thread is bound to the other runtime;
    an unbound thread binds to ``runtime.kind``.
    """
    finish = timed("conversation_turn", thread_id=thread_id)
    typed = message
    # "**Apple** _revenue_" is read as the words, not the markdown around them.
    message = plain_text(message)
    prior = store.load(thread_id) or ThreadState(thread_id=thread_id)
    _check_runtime(prior, runtime)
    workers = DEFAULT_TASK_MAX_WORKERS if max_workers is None else max_workers
    context_token = bind_log_context(thread_id=thread_id, turn=prior.turn_count + 1)
    try:
        evidence = store.evidence_for(thread_id)
        prior_ids = evidence.known_ids()
        cached_facts = EvidenceCachedFacts(runtime.facts, evidence, prior_ids=prior_ids)
        deps = TurnDeps(
            runtime=replace(runtime, facts=cached_facts),
            active_spec=prior.analysis_spec,
            grounding=lambda: grounding_json_from_result(store.resolve_last_result(prior)),
            max_workers=workers,
            on_progress=on_progress,
        )
        outcome = run_analysis(
            thread_id,
            message,
            deps,
            checkpoint=prior.checkpoint,
            legacy=prior.legacy_pending_clarification,
        )

        result = outcome.result
        if outcome.set_aside and _says_set_aside(result, store.resolve_last_result(prior)):
            result = with_banner(result, DISCARDED_CLARIFICATION_BANNER)
        result = label_reused_evidence(result, reused=bool(cached_facts.reused_ids))
        if not result.suggestions and not result.guide:
            result = result.model_copy(
                update={
                    "suggestions": suggest_follow_ups(
                        result, outcome.analysis_spec, runtime.ranking
                    )
                }
            )

        result_ref = retain_result_evidence(evidence, result)
        new_fact_refs = tuple(
            sorted(
                eid
                for eid in evidence.known_ids() - prior_ids
                if eid.startswith("fact-")
            )
        )
        evidence_refs = tuple(
            dict.fromkeys((*prior.evidence_refs, *new_fact_refs, result_ref))
        )

        messages = (*prior.messages, ThreadMessage(role="analyst", content=typed))
        state = ThreadState(
            thread_id=thread_id,
            runtime=runtime.kind,
            messages=messages,
            evidence_refs=evidence_refs,
            last_result_ref=result_ref,
            analysis_spec=outcome.thread_spec,
            checkpoint=outcome.checkpoint,
            turn_count=prior.turn_count + 1,
            live_sec_requests=prior.live_sec_requests,
            updated_at=datetime.now(UTC),
        )
        store.save(state)
        finish(
            turn=state.turn_count,
            intent=result.intent.value,
            renderer=result.renderer.value,
        )
        return ConversationTurn(
            thread_id=thread_id,
            result=result,
            messages=messages,
            analysis_spec=outcome.analysis_spec,
            proposed_patch=outcome.patch,
        )
    finally:
        reset_log_context(context_token)
