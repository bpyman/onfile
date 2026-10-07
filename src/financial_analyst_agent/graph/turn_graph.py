"""The analysis graph: one conversation turn as fixed, typed steps (ADR 0005).

    START → interpret ─┬─ structured ──→ resolve ─┬─ compiled ────→ structured_analysis → END
                       │                          ├─ one question → clarify (interrupt)
                       │                          └─ refused ─────→ END
                       ├─ explain / current_events / exploratory_research / filing_change → END
                       └─ answered (guide reply, or companies the recording lacks) → END

    clarify ─┬─ answered ────→ resolve      (the held analysis, with the choice filled in)
             ├─ asked again ─→ clarify      (a period noted, or an option out of range)
             └─ set aside ───→ interpret    (a new question; the held one is discarded)

``interpret`` is the only step where the model chooses: it proposes a request
(a spec patch, an essay, or a filing comparison) from a closed set and never
picks nodes. The model writes an essay or a filing summary later, inside a
step ``interpret`` chose, and that text never routes the turn. ``resolve``
decides identity, catalog membership, and periods deterministically, and
either refuses, asks one question, or compiles tasks.
Figures come only from the deterministic workflows (``structured_analysis``);
the essay nodes are held to the numeral lock. Edges are fixed; routing reads
typed state.

An ambiguous metric or extend/replace scope pauses the graph with
``interrupt``; ``ThreadCheckpointer`` keeps the paused run in the thread
record, and the analyst's next message resumes it with ``Command(resume=...)``,
in ``clarify``, which decides whether it answers the held question.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime as GraphRuntime
from langgraph.types import Command, interrupt

from financial_analyst_agent.contracts import Intent, RendererKind, TurnResult, WorkflowPlan
from financial_analyst_agent.evidence_store import with_banner
from financial_analyst_agent.filing_change import bind_filing_change, run_filing_change
from financial_analyst_agent.graph.analysis_spec import AnalysisSpec, SpecPatch
from financial_analyst_agent.graph.checkpointer import GraphCheckpoint, ThreadCheckpointer
from financial_analyst_agent.graph.clarify import (
    ask_again,
    clarification_reply,
    pending_from_clarify,
    resumed_request,
)
from financial_analyst_agent.graph.spec_turn import (
    is_filing_change_proposal,
    is_qualitative_proposal,
    is_structured_proposal,
    plan_to_spec_patch,
    resolve_request,
)
from financial_analyst_agent.graph.state import (
    AnalysisRun,
    AnalystRequest,
    Clarification,
    FilingChangeRequest,
    PendingClarification,
    QualitativeRequest,
    StructuredRequest,
    TurnDeps,
    fresh_run,
)
from financial_analyst_agent.graph.structured import build_structured_analysis
from financial_analyst_agent.guide import (
    guide_reply,
    not_recorded_banner,
    not_recorded_reply,
    resets_analysis,
    unrecorded_companies,
)
from financial_analyst_agent.issuer_index import CompanyNames
from financial_analyst_agent.observability import call_provider, log_event
from financial_analyst_agent.request_wording import (
    asks_for_explanation,
    planner_window,
    read_window,
)
from financial_analyst_agent.services.metric_catalog import resolve_metric_phrase
from financial_analyst_agent.turn import (
    current_events_answer,
    explain_answer,
    exploratory_research_answer,
)

Node = Literal[
    "interpret",
    "resolve",
    "clarify",
    "structured_analysis",
    "explain",
    "current_events",
    "exploratory_research",
    "filing_change",
]
_QUALITATIVE_NODES: dict[Intent, Node] = {
    Intent.EXPLAIN: "explain",
    Intent.NEWS_AND_EXPLAIN: "current_events",
    Intent.EXPLORATORY_RESEARCH: "exploratory_research",
}
_PEER_COUNT = 3


def _answered(result: TurnResult, spec: AnalysisSpec | None) -> dict[str, Any]:
    """A finished answer, standing for ``spec``, which the thread keeps."""
    return {"result": result, "analysis_spec": spec, "thread_spec": spec}


def with_peers(proposal: WorkflowPlan | SpecPatch, ranking: Any) -> WorkflowPlan | SpecPatch:
    """Add the largest companies in the named company's industry ("… to its peers")."""
    if not isinstance(proposal, WorkflowPlan) or not proposal.peers or not proposal.companies:
        return proposal
    lookup = getattr(ranking, "lookup_member", None)
    peers = getattr(ranking, "peers", None)
    if not callable(lookup) or not callable(peers):
        return proposal
    try:
        member = lookup(proposal.companies[0])
    except Exception:
        return proposal
    found = peers(member.cik, limit=_PEER_COUNT)
    companies = (*proposal.companies, *(peer.ticker for peer in found))
    return proposal.model_copy(update={"companies": companies})


def _names_a_company(proposal: WorkflowPlan | SpecPatch) -> bool:
    """Whether a figures proposal names a company or ranks a group ("unknown" names none)."""
    if isinstance(proposal, SpecPatch):
        return bool(proposal.add_companies) or proposal.ranked_request is not None
    if proposal.intent in (Intent.RANK, Intent.RANK_AND_LOOKUP):
        return True
    company = proposal.company if proposal.company and proposal.company != "unknown" else None
    return bool(company or proposal.companies)


def _figure_asked(message: str, deps: TurnDeps) -> WorkflowPlan | None:
    """The lookup a figures question asks for, when a planner read it as an explanation.

    It names a catalog metric. With a recorded company named, it is that company's
    figure, however it is worded: "Why is Goldman's revenue so volatile?" (README,
    the why row; the why note comes from the words). With none, it asks which
    company only where none of the explanation wording is there: "What's the EPS?"
    (README, general question). "What is EPS?", "How might AI change banking?" and
    "How might AI change Goldman Sachs's business?" stay explanations: the first
    asks what the measure is, the others name no catalog metric.
    """
    resolved = resolve_metric_phrase(message)
    if resolved.kind == "unknown":
        return None
    index = names_index(deps.runtime)
    mentions = index.find(message) if index is not None else []
    companies = tuple(dict.fromkeys(mention.query for mention in mentions))
    if len(companies) == 1:
        return WorkflowPlan(intent=Intent.LOOKUP, company=companies[0], metric=resolved.metric)
    if companies:
        return WorkflowPlan(intent=Intent.COMPARE, companies=companies, metric=resolved.metric)
    if asks_for_explanation(message):
        return None
    return WorkflowPlan(intent=Intent.LOOKUP, metric=resolved.metric)


def request_from_proposal(
    proposal: WorkflowPlan | SpecPatch, message: str, deps: TurnDeps
) -> AnalystRequest:
    """Type the planner's proposal: one of the closed request kinds, or an error."""
    if isinstance(proposal, WorkflowPlan) and is_filing_change_proposal(proposal):
        return bind_filing_change(proposal, message)
    if isinstance(proposal, WorkflowPlan) and proposal.intent is Intent.EXPLAIN:
        proposal = _figure_asked(message, deps) or proposal
    if (
        is_structured_proposal(proposal)
        and not _names_a_company(proposal)
        and asks_for_explanation(message)
    ):
        # "Explain how a share buyback affects EPS": a general question that names
        # a metric, whichever planner read it as a figure with no company.
        return QualitativeRequest(intent=Intent.EXPLAIN, topic=message)
    if isinstance(proposal, WorkflowPlan) and is_qualitative_proposal(proposal):
        topic = proposal.topic
        # Validated: the intent is one of the qualitative three.
        return QualitativeRequest.model_validate(
            {"intent": proposal.intent, "topic": topic if topic and topic.strip() else message}
        )
    if is_structured_proposal(proposal):
        # A planner's window stands only where the words ask about time.
        window = read_window(message)
        patch = planner_window(
            proposal if isinstance(proposal, SpecPatch) else plan_to_spec_patch(proposal),
            message,
            window=window,
        )
        intent = None if isinstance(proposal, SpecPatch) else proposal.intent
        notes = () if isinstance(proposal, SpecPatch) else proposal.notes
        runtime = deps.runtime
        unrecorded = (
            []
            if patch.ranked_request is not None
            else unrecorded_companies(
                message,
                names_index(runtime),
                getattr(runtime.completer, "outside_index", None),
            )
        )
        return StructuredRequest(
            patch=patch,
            wording=message,
            question=message,
            window=window,
            intent=intent,
            notes=notes,
            unrecorded=tuple(unrecorded),
        )
    # The three request kinds cover every closed intent.
    raise ValueError(f"unsupported planner proposal: {proposal!r}")


def names_index(runtime: Any) -> CompanyNames | None:
    """The issuer index that reads company names on this runtime, whichever planner plans.

    Spec resolution reads names with the ranking's index (ADR 0010); the guide,
    the not-recorded note and a clarification's answer read them the same way,
    so an LLM-planned turn, whose planner holds no index, reads names alike.
    """
    index: CompanyNames | None = getattr(runtime.ranking, "index", None)
    if index is None:
        index = getattr(runtime.completer, "index", None)
    return index


def _interpret(state: AnalysisRun, runtime: GraphRuntime[TurnDeps]) -> dict[str, Any]:
    """A guide reply, or the model's proposal typed as a closed request."""
    deps = runtime.context
    providers = deps.runtime
    message = state["message"]
    index = names_index(providers)
    guide = guide_reply(message, deps.active_spec, index)
    if guide is not None:
        return {
            "request": None,
            **_answered(guide, None if resets_analysis(message) else deps.active_spec),
        }
    completer = providers.completer
    proposal = call_provider(
        "planner", lambda: completer.complete(message, current_spec=deps.active_spec)
    )
    request = request_from_proposal(with_peers(proposal, providers.ranking), message, deps)
    if isinstance(request, StructuredRequest) and request.patch.ranked_request is None:
        # A ranking names an industry: "top five banks" names no company to miss.
        not_recorded = not_recorded_reply(
            message, index, getattr(providers.completer, "outside_index", None)
        )
        if not_recorded is not None:
            return {"request": None, **_answered(not_recorded, deps.active_spec)}
    return {"request": request, "result": None}


def _route_request(state: AnalysisRun) -> str:
    request = state["request"]
    if state["result"] is not None or request is None:
        return END
    if isinstance(request, StructuredRequest):
        return "resolve"
    if isinstance(request, FilingChangeRequest):
        return "filing_change"
    return _QUALITATIVE_NODES[request.intent]


def _structured(state: AnalysisRun) -> StructuredRequest:
    request = state["request"]
    if not isinstance(request, StructuredRequest):
        raise ValueError(f"resolve runs on a structured request, not {request!r}")
    return request


def _resolve(state: AnalysisRun, runtime: GraphRuntime[TurnDeps]) -> dict[str, Any]:
    """Patch → resolve → validate → compile; or one question; or a refusal.

    No facts are fetched: resolution reads only filing lists, to date the periods.
    """
    deps = runtime.context
    request = _structured(state)
    resolution = resolve_request(request, deps.active_spec, deps.runtime)
    if resolution.compiled is not None:
        return {"patch": resolution.patch, "compiled": resolution.compiled}
    result = resolution.result
    if result is None:
        raise ValueError("resolution produced neither an answer nor compiled tasks")
    if request.unrecorded:
        result = with_banner(result, not_recorded_banner(list(request.unrecorded)))
    pending = pending_from_clarify(result, resolution.patch, request.question)
    if pending is not None:
        return {
            "patch": resolution.patch,
            "clarification": Clarification(pending=pending, result=result),
        }
    spec = resolution.analysis_spec
    return {
        "patch": resolution.patch,
        "result": result,
        "analysis_spec": spec,
        "thread_spec": spec if spec is not None else deps.active_spec,
    }


def _route_resolution(state: AnalysisRun) -> str:
    if state["clarification"] is not None:
        return "clarify"
    if state["compiled"] is not None:
        return "structured_analysis"
    return END


def _clarify(state: AnalysisRun, runtime: GraphRuntime[TurnDeps]) -> dict[str, Any]:
    """Pause on the held question; read the next message as its answer, or set it aside."""
    deps = runtime.context
    held = state["clarification"]
    if held is None:
        raise ValueError("clarify runs only with a held question")
    message = interrupt(held)
    if not isinstance(message, str):
        raise TypeError(f"a clarification resumes with the analyst's message, not {message!r}")
    reply = clarification_reply(held.pending, message, names_index(deps.runtime))
    update: dict[str, Any] = {"message": message, "patch": None, "set_aside": False}
    if reply is None:
        # ADR 0005: asking something unrelated discards the held analysis, explicitly.
        return {**update, "clarification": None, "request": None, "set_aside": True}
    if not reply.chosen:
        return {
            **update,
            "clarification": ask_again(held.pending, reply, message, deps.active_spec),
        }
    request = resumed_request(held.pending, reply.chosen, message, deps.active_spec)
    return {**update, "clarification": None, "request": request}


def _route_answer(state: AnalysisRun) -> Node:
    if state["clarification"] is not None:
        return "clarify"
    if state["request"] is None:
        return "interpret"
    return "resolve"


def _qualitative(state: AnalysisRun) -> QualitativeRequest:
    request = state["request"]
    if not isinstance(request, QualitativeRequest):
        raise ValueError(f"an essay workflow runs on a qualitative request, not {request!r}")
    return request


def _explain(state: AnalysisRun, runtime: GraphRuntime[TurnDeps]) -> dict[str, Any]:
    deps = runtime.context
    result = explain_answer(
        _qualitative(state).topic, deps.runtime, grounding_json=deps.grounding()
    )
    # An essay, answered or not, leaves the analysis as it was: "add Merck" still adds to it.
    return _answered(result, deps.active_spec)


def _current_events(state: AnalysisRun, runtime: GraphRuntime[TurnDeps]) -> dict[str, Any]:
    deps = runtime.context
    return _answered(current_events_answer(state["message"], deps.runtime), deps.active_spec)


def _exploratory_research(
    state: AnalysisRun, runtime: GraphRuntime[TurnDeps]
) -> dict[str, Any]:
    deps = runtime.context
    result = exploratory_research_answer(state["message"], deps.runtime)
    return _answered(result, deps.active_spec)


def _filing_change(state: AnalysisRun, runtime: GraphRuntime[TurnDeps]) -> dict[str, Any]:
    deps = runtime.context
    request = state["request"]
    if not isinstance(request, FilingChangeRequest):
        raise ValueError(f"filing comparison runs on a filing request, not {request!r}")
    result = run_filing_change(request, deps.runtime)
    return _answered(result, deps.active_spec)


def build_turn_graph() -> Any:
    """The parent graph, compiled without a checkpointer: each turn supplies its thread's."""
    builder = StateGraph(AnalysisRun, context_schema=TurnDeps)
    builder.add_node("interpret", _interpret)
    builder.add_node("resolve", _resolve)
    builder.add_node("clarify", _clarify)
    builder.add_node("structured_analysis", build_structured_analysis())
    builder.add_node("explain", _explain)
    builder.add_node("current_events", _current_events)
    builder.add_node("exploratory_research", _exploratory_research)
    builder.add_node("filing_change", _filing_change)
    builder.add_edge(START, "interpret")
    builder.add_conditional_edges(
        "interpret",
        _route_request,
        ["resolve", "explain", "current_events", "exploratory_research", "filing_change", END],
    )
    builder.add_conditional_edges(
        "resolve", _route_resolution, ["clarify", "structured_analysis", END]
    )
    builder.add_conditional_edges("clarify", _route_answer, ["resolve", "clarify", "interpret"])
    for workflow in (
        "structured_analysis",
        "explain",
        "current_events",
        "exploratory_research",
        "filing_change",
    ):
        builder.add_edge(workflow, END)
    return builder.compile(name="analysis")


TURN_GRAPH = build_turn_graph()


@dataclass(frozen=True)
class AnalysisOutcome:
    """One turn's answer, and what the thread keeps from it."""

    result: TurnResult
    # The analysis this turn answered, and the one the thread keeps.
    analysis_spec: AnalysisSpec | None
    thread_spec: AnalysisSpec | None
    # The patch as resolution applied it, when the turn was structured.
    patch: SpecPatch | None
    # An open clarification was set aside to answer this message.
    set_aside: bool
    # The paused run, while a clarification is open; None once the turn finished.
    checkpoint: GraphCheckpoint | None


def _legacy_clarification(pending: PendingClarification) -> dict[str, Any]:
    """A held question saved before the graph held clarifications, as graph state."""
    asked = TurnResult(
        intent=pending.intent,
        tool_traces=[],
        renderer=RendererKind.CLARIFY,
        candidates=pending.candidates,
        clarify_kind=pending.kind,
    )
    held = Clarification(pending=pending, result=asked)
    return {**fresh_run(pending.question), "patch": pending.patch, "clarification": held}


def _restore(
    thread_id: str, checkpoint: GraphCheckpoint | None, config: RunnableConfig
) -> tuple[ThreadCheckpointer, bool]:
    """The thread's checkpointer, and whether its run is paused on a clarification.

    A checkpoint that cannot be read back, or is paused on anything but a
    clarification, is dropped: the turn starts fresh, as it would on a thread
    whose record could not be read, rather than failing every turn after.
    """
    if checkpoint is None:
        return ThreadCheckpointer(thread_id), False
    try:
        checkpointer = ThreadCheckpointer(thread_id, checkpoint)
        snapshot = TURN_GRAPH.copy(update={"checkpointer": checkpointer}).get_state(config)
        if not snapshot.next:
            return checkpointer, False
        held = snapshot.values.get("clarification")
        if _restored_whole(held):
            return checkpointer, True
        problem = "not paused on a whole clarification"
    except Exception as exc:  # a damaged record must not fail every later turn
        problem = type(exc).__name__
    log_event("thread_checkpoint_dropped", reason=problem)
    return ThreadCheckpointer(thread_id), False


def _restored_whole(held: Any) -> bool:
    """Whether a restored clarification came back as the models it was saved as.

    A field that no longer validates (a saved kind a later release renamed) is
    rebuilt with ``model_construct``, leaving plain dicts that fail every turn.
    """
    return (
        isinstance(held, Clarification)
        and isinstance(held.pending, PendingClarification)
        and isinstance(held.result, TurnResult)
    )


def run_analysis(
    thread_id: str,
    message: str,
    deps: TurnDeps,
    *,
    checkpoint: GraphCheckpoint | None,
    legacy: PendingClarification | None = None,
) -> AnalysisOutcome:
    """Run one turn of ``thread_id``: resume its open clarification, or start fresh.

    ``checkpoint`` is the thread's paused run, if any. ``legacy`` is a clarification
    a thread record saved before checkpoints existed; it is carried into the graph
    (as though ``resolve`` had just asked it) so the analyst's answer still resumes it.
    """
    config: RunnableConfig = {"configurable": {"thread_id": thread_id}}
    checkpointer, paused = _restore(thread_id, checkpoint, config)
    graph = TURN_GRAPH.copy(update={"checkpointer": checkpointer})
    if not paused and checkpoint is None and legacy is not None:
        graph.update_state(config, _legacy_clarification(legacy), as_node="resolve")
        paused = True
    run_input: Command[Any] | AnalysisRun = (
        Command(resume=message) if paused else fresh_run(message)
    )
    values: dict[str, Any] = graph.invoke(run_input, config, context=deps, durability="exit")
    interrupts = values.get("__interrupt__") or ()
    if interrupts:
        held = interrupts[0].value
        if not isinstance(held, Clarification):
            raise TypeError(f"the analysis graph paused on {held!r}, not a clarification")
        return AnalysisOutcome(
            result=held.result,
            analysis_spec=held.analysis_spec,
            thread_spec=deps.active_spec,
            patch=values["patch"],
            set_aside=values["set_aside"],
            checkpoint=checkpointer.record(),
        )
    result = values["result"]
    if not isinstance(result, TurnResult):
        raise RuntimeError("the analysis graph finished without an answer")
    return AnalysisOutcome(
        result=result,
        analysis_spec=values["analysis_spec"],
        thread_spec=values["thread_spec"],
        patch=values["patch"],
        set_aside=values["set_aside"],
        checkpoint=None,
    )
