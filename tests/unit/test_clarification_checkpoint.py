"""A clarification is the analysis graph paused on ``interrupt`` (ADR 0005).

The paused run is kept in the thread record by the thread's checkpointer, the
next message resumes it with ``Command(resume=...)``, and an unrelated question
sets it aside. These tests drive the conversation seam and then look at the
graph's own state through the same checkpointer the seam used.
"""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from financial_analyst_agent.contracts import WorkflowPlan
from financial_analyst_agent.runtime import FIXTURE_EXPLAIN_ESSAY, FIXTURE_UNIVERSE_SNAPSHOT_PATH
from helpers import named_by_cik

# Resolved companies are asked for by CIK; these fakes answer by name.
_NAMED = named_by_cik('Google')

PROFIT = ("gross_profit", "operating_income", "net_income")


class _Facts:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def list_quarterly_report_dates(self, company: str, *, limit: int) -> tuple[date, ...]:
        company = _NAMED(company)
        return (date(2026, 3, 31), date(2025, 12, 31), date(2025, 9, 30))[:limit]

    def get_financials(
        self, company: str, metric: str, *, report_date: date | None = None
    ) -> SimpleNamespace:
        company = _NAMED(company)
        self.calls.append((company, metric))
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


class _Planner:
    """Plans a Google lookup for a profit question, an essay for anything else."""

    def __init__(self) -> None:
        self.asked: list[str] = []

    def complete(self, query: str, current_spec: object = None) -> WorkflowPlan:
        from financial_analyst_agent.contracts import Intent

        self.asked.append(query)
        if "profit" in query.casefold():
            return WorkflowPlan(intent=Intent.LOOKUP, company="Google", metric="net_income")
        return WorkflowPlan(intent=Intent.EXPLAIN, topic=query)


class _Essay:
    def complete_essay(self, query: str, tool_json: str = "") -> str:
        return FIXTURE_EXPLAIN_ESSAY


def _runtime(planner: _Planner, facts: _Facts) -> Any:
    from financial_analyst_agent.contracts import Runtime
    from financial_analyst_agent.ranking import SnapshotRanking

    return Runtime(
        completer=planner,
        facts=facts,  # type: ignore[arg-type]
        ranking=SnapshotRanking.from_path(FIXTURE_UNIVERSE_SNAPSHOT_PATH),
        essay=_Essay(),
    )


def _turn(store: Any, message: str, planner: _Planner, facts: _Facts) -> Any:
    from financial_analyst_agent.conversation import run_conversation_turn

    return run_conversation_turn("t1", message, _runtime(planner, facts), store=store)


def _graph_state(store: Any) -> Any:
    """The analysis graph's state for thread t1, read through its saved checkpoint."""
    from financial_analyst_agent.graph.checkpointer import ThreadCheckpointer
    from financial_analyst_agent.graph.turn_graph import TURN_GRAPH

    record = store.load("t1")
    assert record is not None
    graph = TURN_GRAPH.copy(update={"checkpointer": ThreadCheckpointer("t1", record.checkpoint)})
    return graph.get_state({"configurable": {"thread_id": "t1"}})


def test_an_ambiguous_metric_pauses_the_graph_on_an_interrupt(tmp_path: Path) -> None:
    from financial_analyst_agent.contracts import RendererKind
    from financial_analyst_agent.graph.state import Clarification
    from financial_analyst_agent.thread_store import LocalThreadStore

    store = LocalThreadStore(tmp_path)
    facts = _Facts()

    turn = _turn(store, "What was Google's profit?", _Planner(), facts)

    assert turn.result.renderer is RendererKind.CLARIFY
    assert turn.result.candidates == PROFIT
    assert facts.calls == []
    snapshot = _graph_state(store)
    assert snapshot.next == ("clarify",)
    (paused,) = snapshot.interrupts
    assert isinstance(paused.value, Clarification)
    assert paused.value.pending.candidates == PROFIT
    assert paused.value.pending.patch.add_companies == ("Google",)
    record = store.load("t1")
    assert record is not None
    assert record.pending_clarification == paused.value.pending


def test_the_answer_resumes_the_held_analysis_without_planning_again(tmp_path: Path) -> None:
    from financial_analyst_agent.contracts import RendererKind
    from financial_analyst_agent.thread_store import LocalThreadStore

    store = LocalThreadStore(tmp_path)
    planner = _Planner()
    facts = _Facts()
    _turn(store, "What was Google's profit?", planner, facts)

    turn = _turn(store, "net income", planner, facts)

    # Resumed in the clarify step: the planner never saw the answer.
    assert planner.asked == ["What was Google's profit?"]
    assert turn.result.renderer is RendererKind.TABLE
    # The company came from the held patch; the answer named only the metric.
    assert set(facts.calls) == {("Google", "net_income")}
    record = store.load("t1")
    assert record is not None
    assert record.checkpoint is None
    assert record.pending_clarification is None
    assert record.analysis_spec is not None
    assert record.analysis_spec.metrics == ("net_income",)
    assert _graph_state(store).next == ()


def test_an_unrelated_question_sets_the_held_analysis_aside(tmp_path: Path) -> None:
    from financial_analyst_agent.contracts import Intent, RendererKind
    from financial_analyst_agent.conversation import DISCARDED_CLARIFICATION_BANNER
    from financial_analyst_agent.thread_store import LocalThreadStore

    store = LocalThreadStore(tmp_path)
    planner = _Planner()
    facts = _Facts()
    _turn(store, "What was Google's profit?", planner, facts)

    turn = _turn(store, "How can AI disrupt healthcare?", planner, facts)

    assert planner.asked == ["What was Google's profit?", "How can AI disrupt healthcare?"]
    assert turn.result.intent is Intent.EXPLAIN
    assert turn.result.renderer is RendererKind.ESSAY
    assert DISCARDED_CLARIFICATION_BANNER in turn.result.banners
    assert facts.calls == []
    record = store.load("t1")
    assert record is not None
    assert record.checkpoint is None
    # Answering the old question now is a new question, not a resume.
    again = _turn(store, "net income", planner, facts)
    assert again.result.renderer is not RendererKind.TABLE
    assert planner.asked[-1] == "net income"


def test_a_reloaded_store_resumes_from_the_thread_record(tmp_path: Path) -> None:
    from financial_analyst_agent.contracts import RendererKind
    from financial_analyst_agent.thread_store import LocalThreadStore

    _turn(LocalThreadStore(tmp_path), "What was Google's profit?", _Planner(), _Facts())
    saved = json.loads((tmp_path / "t1.json").read_text(encoding="utf-8"))
    assert saved["checkpoint"]["saved"][0]["writes"]

    # A new store over the same directory, as after a restart: nothing in memory.
    planner = _Planner()
    facts = _Facts()
    turn = _turn(LocalThreadStore(tmp_path), "the third one", planner, facts)

    assert planner.asked == []
    assert turn.result.renderer is RendererKind.TABLE
    assert set(facts.calls) == {("Google", "net_income")}


def test_an_answer_out_of_range_asks_again_and_the_next_one_resumes(tmp_path: Path) -> None:
    from financial_analyst_agent.contracts import RendererKind
    from financial_analyst_agent.thread_store import LocalThreadStore

    store = LocalThreadStore(tmp_path)
    planner = _Planner()
    facts = _Facts()
    _turn(store, "What was Google's profit?", planner, facts)

    asked_again = _turn(store, "4", planner, facts)

    assert asked_again.result.renderer is RendererKind.CLARIFY
    assert asked_again.result.banners == [
        "There are 3 options: pick 1 to 3, or type the metric's name."
    ]
    assert _graph_state(store).next == ("clarify",)

    turn = _turn(store, "net", planner, facts)

    assert planner.asked == ["What was Google's profit?"]
    assert turn.result.renderer is RendererKind.TABLE
    assert set(facts.calls) == {("Google", "net_income")}


def test_a_clarification_saved_before_checkpoints_still_resumes(tmp_path: Path) -> None:
    from financial_analyst_agent.contracts import RendererKind
    from financial_analyst_agent.thread_store import LocalThreadStore

    legacy = {
        "thread_id": "t1",
        "runtime": "recorded",
        "messages": [{"role": "analyst", "content": "What was Google's profit?"}],
        "pending_clarification": {
            "kind": "ambiguous_metric",
            "candidates": list(PROFIT),
            "patch": {"mode": "replace", "add_companies": ["Google"], "add_metrics": ["unknown"]},
            "intent": "lookup",
            "question": "What was Google's profit?",
        },
        "turn_count": 1,
    }
    (tmp_path / "t1.json").write_text(json.dumps(legacy), encoding="utf-8")
    store = LocalThreadStore(tmp_path)
    record = store.load("t1")
    assert record is not None
    assert record.pending_clarification is not None
    planner = _Planner()
    facts = _Facts()

    turn = _turn(store, "net income", planner, facts)

    assert planner.asked == []
    assert turn.result.renderer is RendererKind.TABLE
    assert set(facts.calls) == {("Google", "net_income")}
    saved = json.loads((tmp_path / "t1.json").read_text(encoding="utf-8"))
    assert "pending_clarification" not in saved
    assert saved["checkpoint"] is None


def test_a_failed_turn_keeps_a_clarification_saved_before_checkpoints(tmp_path: Path) -> None:
    # The API saves the session budget after a failed or timed-out turn; that save
    # must not drop the old record's open question before a turn has resumed it.
    from financial_analyst_agent.session import SessionBudget, persist_session_budget
    from financial_analyst_agent.thread_store import LocalThreadStore

    legacy = {
        "thread_id": "t1",
        "runtime": "recorded",
        "messages": [{"role": "analyst", "content": "What was Google's profit?"}],
        "pending_clarification": {
            "kind": "ambiguous_metric",
            "candidates": list(PROFIT),
            "patch": {"mode": "replace", "add_companies": ["Google"], "add_metrics": ["unknown"]},
            "intent": "lookup",
            "question": "What was Google's profit?",
        },
        "turn_count": 1,
    }
    (tmp_path / "t1.json").write_text(json.dumps(legacy), encoding="utf-8")
    store = LocalThreadStore(tmp_path)

    persist_session_budget(store, "t1", SessionBudget(max_turns=50, max_live_sec_requests=50))

    record = store.load("t1")
    assert record is not None
    assert record.pending_clarification is not None
    assert record.pending_clarification.question == "What was Google's profit?"


def test_an_unreadable_checkpoint_is_dropped_rather_than_failing_the_thread(
    tmp_path: Path,
) -> None:
    from financial_analyst_agent.contracts import RendererKind
    from financial_analyst_agent.thread_store import LocalThreadStore

    store = LocalThreadStore(tmp_path)
    _turn(store, "What was Google's profit?", _Planner(), _Facts())
    path = tmp_path / "t1.json"
    saved = json.loads(path.read_text(encoding="utf-8"))
    for checkpoint in saved["checkpoint"]["saved"]:
        checkpoint["checkpoint"]["data"] = "bm90IG1zZ3BhY2s="  # "not msgpack"
        for write in checkpoint["writes"]:
            write["value"]["data"] = "bm90IG1zZ3BhY2s="
    path.write_text(json.dumps(saved), encoding="utf-8")
    record = store.load("t1")
    assert record is not None
    assert record.pending_clarification is None
    planner = _Planner()

    turn = _turn(store, "How can AI disrupt healthcare?", planner, _Facts())

    assert planner.asked == ["How can AI disrupt healthcare?"]
    assert turn.result.renderer is RendererKind.ESSAY
    after = store.load("t1")
    assert after is not None
    assert after.checkpoint is None


def test_the_checkpointer_serves_only_its_own_thread() -> None:
    from financial_analyst_agent.graph.checkpointer import ThreadCheckpointer

    with pytest.raises(ValueError, match="holds thread 't1'"):
        ThreadCheckpointer("t1").get_tuple({"configurable": {"thread_id": "t2"}})


def test_the_parent_graph_has_its_steps_and_fixed_edges() -> None:
    from financial_analyst_agent.graph.turn_graph import TURN_GRAPH

    drawn = TURN_GRAPH.get_graph()
    assert set(drawn.nodes) == {
        "__start__",
        "interpret",
        "resolve",
        "clarify",
        "structured_analysis",
        "explain",
        "current_events",
        "exploratory_research",
        "filing_change",
        "__end__",
    }
    edges = {(edge.source, edge.target) for edge in drawn.edges}
    assert edges == {
        ("__start__", "interpret"),
        ("interpret", "resolve"),
        ("interpret", "explain"),
        ("interpret", "current_events"),
        ("interpret", "exploratory_research"),
        ("interpret", "filing_change"),
        ("interpret", "__end__"),
        ("resolve", "clarify"),
        ("resolve", "structured_analysis"),
        ("resolve", "__end__"),
        ("clarify", "resolve"),
        ("clarify", "clarify"),
        ("clarify", "interpret"),
        ("structured_analysis", "__end__"),
        ("explain", "__end__"),
        ("current_events", "__end__"),
        ("exploratory_research", "__end__"),
        ("filing_change", "__end__"),
    }
    # Only the model-facing step and the answer-reading step decide where to go.
    assert {edge.source for edge in drawn.edges if edge.conditional} == {
        "interpret",
        "resolve",
        "clarify",
    }


def test_structured_analysis_is_a_subgraph_of_ordered_steps() -> None:
    from financial_analyst_agent.graph.turn_graph import TURN_GRAPH

    drawn = TURN_GRAPH.get_graph(xray=True)
    steps = ["run_tasks", "merge", "add_history", "annotate"]
    edges = {(edge.source, edge.target) for edge in drawn.edges}
    names = [f"structured_analysis:{step}" for step in steps]
    assert set(names) <= set(drawn.nodes)
    assert set(zip(names, names[1:], strict=False)) <= edges
    assert ("resolve", names[0]) in edges
    assert (names[-1], "__end__") in edges
