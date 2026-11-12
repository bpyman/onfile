"""Structured-analysis subgraph: compiled tasks in, one answer and its resolved spec out.

    run_tasks → merge → add_history → annotate → explain

``run_tasks`` is the only step that fans out to providers for the asked cells
(a bounded thread pool under the turn's SEC deadline); ``merge`` combines the
cells deterministically (period-aligned rows, Decimal changes); ``add_history``
reads the overview trend and a lone fact's prior quarter; ``annotate`` adds the
notes and names the analysis the thread keeps; ``explain`` adds Management's
explanation to a why question's figures (ADR 0017). The subgraph sees only the
compiled analysis, never the conversation.
"""

from __future__ import annotations

from typing import Any, TypedDict

from langgraph.graph import END, START, StateGraph
from langgraph.runtime import Runtime as GraphRuntime

from financial_analyst_agent.contracts import TurnResult
from financial_analyst_agent.evidence_store import with_banner
from financial_analyst_agent.graph.analysis_spec import AnalysisSpec
from financial_analyst_agent.graph.spec_turn import (
    add_explanation,
    add_history,
    annotate_analysis,
    dispatch_compiled_tasks,
    merge_analysis,
)
from financial_analyst_agent.graph.state import CompiledAnalysis, TurnDeps
from financial_analyst_agent.guide import not_recorded_banner


class StructuredInput(TypedDict):
    compiled: CompiledAnalysis | None


class StructuredOutput(TypedDict):
    result: TurnResult | None
    analysis_spec: AnalysisSpec | None
    thread_spec: AnalysisSpec | None


class StructuredAnalysis(StructuredInput, StructuredOutput):
    task_results: list[TurnResult]


def _compiled(state: StructuredInput) -> CompiledAnalysis:
    compiled = state["compiled"]
    if compiled is None:
        raise ValueError("structured analysis runs only on a compiled analysis")
    return compiled


def _answer(state: StructuredAnalysis) -> TurnResult:
    result = state["result"]
    if result is None:
        raise ValueError("structured analysis has no merged answer yet")
    return result


def _run_tasks(
    state: StructuredAnalysis, runtime: GraphRuntime[TurnDeps]
) -> dict[str, list[TurnResult]]:
    deps = runtime.context
    results = dispatch_compiled_tasks(
        _compiled(state).tasks,
        deps.runtime,
        on_progress=deps.on_progress,
        max_workers=deps.max_workers,
    )
    return {"task_results": results}


def _merge(state: StructuredAnalysis) -> dict[str, TurnResult]:
    return {"result": merge_analysis(_compiled(state), state["task_results"])}


def _add_history(
    state: StructuredAnalysis, runtime: GraphRuntime[TurnDeps]
) -> dict[str, TurnResult]:
    deps = runtime.context
    merged = add_history(
        _compiled(state), _answer(state), deps.runtime, max_workers=deps.max_workers
    )
    return {"result": merged}


def _annotate(state: StructuredAnalysis, runtime: GraphRuntime[TurnDeps]) -> dict[str, Any]:
    compiled = _compiled(state)
    result, spec = annotate_analysis(compiled, _answer(state), runtime.context.runtime)
    if compiled.unrecorded:
        result = with_banner(result, not_recorded_banner(list(compiled.unrecorded)))
    return {"result": result, "analysis_spec": spec, "thread_spec": spec}


def _explain(state: StructuredAnalysis, runtime: GraphRuntime[TurnDeps]) -> dict[str, Any]:
    deps = runtime.context
    result = add_explanation(
        _compiled(state), _answer(state), deps.runtime, max_workers=deps.max_workers
    )
    return {"result": result}


def build_structured_analysis() -> Any:
    builder = StateGraph(
        StructuredAnalysis,
        context_schema=TurnDeps,
        input_schema=StructuredInput,
        output_schema=StructuredOutput,
    )
    builder.add_node("run_tasks", _run_tasks)
    builder.add_node("merge", _merge)
    builder.add_node("add_history", _add_history)
    builder.add_node("annotate", _annotate)
    builder.add_node("explain", _explain)
    builder.add_edge(START, "run_tasks")
    builder.add_edge("run_tasks", "merge")
    builder.add_edge("merge", "add_history")
    builder.add_edge("add_history", "annotate")
    builder.add_edge("annotate", "explain")
    builder.add_edge("explain", END)
    return builder.compile(name="structured_analysis")
