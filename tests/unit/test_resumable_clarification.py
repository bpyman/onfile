"""Conversation seam: resumable clarification (ticket 14).

An ambiguous metric holds a pending clarification on the thread — nothing
fetched. Answering resumes the planned analysis; an unrelated question
discards it. Unknown metrics still refuse. Ambiguous extend/replace scope
clarifies rather than guessing.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from financial_analyst_agent.contracts import WorkflowPlan
from financial_analyst_agent.runtime import FIXTURE_EXPLAIN_ESSAY, FIXTURE_UNIVERSE_SNAPSHOT_PATH
from helpers import FakeFacts, ListedFilings, named_by_cik

# Resolved companies are asked for by CIK; these fakes answer by name.
_NAMED = named_by_cik('Google', 'Apple')


class _SilentFacts(FakeFacts):
    def get_financials(self, company: str, metric: str, **kwargs: object) -> SimpleNamespace:
        company = _NAMED(company)
        raise AssertionError(f"provider must not run while clarifying: {company} {metric}")


class _LookupFacts(ListedFilings):
    """Google and Apple file the same five quarters; every fact is Alphabet's."""

    def __init__(self) -> None:
        quarters = (
            date(2026, 3, 31),
            date(2025, 12, 31),
            date(2025, 9, 30),
            date(2025, 6, 30),
            date(2025, 3, 31),
        )
        super().__init__({"Google": quarters, "Apple": quarters})
        self.calls: list[tuple[str, str]] = []

    def list_quarterly_report_dates(self, company: str, *, limit: int) -> tuple[date, ...]:
        return super().list_quarterly_report_dates(_NAMED(company), limit=limit)

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


class _GuessNetIncome:
    def complete(self, query: str, current_spec: object = None) -> WorkflowPlan:
        from financial_analyst_agent.contracts import Intent

        return WorkflowPlan(
            intent=Intent.LOOKUP,
            company="Google",
            metric="net_income",
            industry=None,
            topic=None,
        )


class _UnknownMetricCompleter:
    def complete(self, query: str, current_spec: object = None) -> WorkflowPlan:
        from financial_analyst_agent.contracts import Intent

        return WorkflowPlan(
            intent=Intent.LOOKUP,
            company="Google",
            metric="debt",
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


def _runtime(*, completer: object, facts: object | None = None, essay: object | None = None):
    from financial_analyst_agent.contracts import Runtime
    from financial_analyst_agent.ranking import SnapshotRanking

    return Runtime(
        completer=completer,  # type: ignore[arg-type]
        facts=(facts or _LookupFacts()),  # type: ignore[arg-type]
        ranking=SnapshotRanking.from_path(FIXTURE_UNIVERSE_SNAPSHOT_PATH),
        essay=essay,  # type: ignore[arg-type]
    )


def test_ambiguous_metric_holds_pending_and_runs_no_tools(tmp_path: Path) -> None:
    from financial_analyst_agent.contracts import Intent, RendererKind
    from financial_analyst_agent.conversation import run_conversation_turn
    from financial_analyst_agent.thread_store import LocalThreadStore

    store = LocalThreadStore(tmp_path)
    turn = run_conversation_turn(
        "t1",
        "What was Google's profit?",
        _runtime(completer=_GuessNetIncome(), facts=_SilentFacts()),
        store=store,
    )

    assert turn.result.intent is Intent.LOOKUP
    assert turn.result.renderer is RendererKind.CLARIFY
    assert turn.result.tool_traces == []
    assert turn.result.candidates == ("gross_profit", "operating_income", "net_income")
    state = store.load("t1")
    assert state is not None
    assert state.pending_clarification is not None
    assert state.pending_clarification.kind == "ambiguous_metric"
    assert state.pending_clarification.candidates == (
        "gross_profit",
        "operating_income",
        "net_income",
    )
    assert state.analysis_spec is None


def test_answering_clarification_resumes_pending_analysis(tmp_path: Path) -> None:
    from financial_analyst_agent.contracts import Intent, RendererKind
    from financial_analyst_agent.conversation import run_conversation_turn
    from financial_analyst_agent.thread_store import LocalThreadStore

    store = LocalThreadStore(tmp_path)
    facts = _LookupFacts()
    run_conversation_turn(
        "t1",
        "What was Google's profit?",
        _runtime(completer=_GuessNetIncome(), facts=_SilentFacts()),
        store=store,
    )

    turn = run_conversation_turn(
        "t1",
        "net income",
        _runtime(completer=_GuessNetIncome(), facts=facts),
        store=store,
    )

    assert turn.result.renderer is RendererKind.TABLE
    assert turn.result.intent is Intent.LOOKUP
    # The lone fact also reads the quarter before it, for its change chip.
    assert set(facts.calls) == {("Google", "net_income")}
    assert turn.analysis_spec is not None
    assert turn.analysis_spec.metrics == ("net_income",)
    state = store.load("t1")
    assert state is not None
    assert state.pending_clarification is None
    assert state.analysis_spec is not None
    assert state.analysis_spec.metrics == ("net_income",)


def test_unknown_metric_still_refuses_without_pending(tmp_path: Path) -> None:
    from financial_analyst_agent.contracts import RendererKind
    from financial_analyst_agent.conversation import run_conversation_turn
    from financial_analyst_agent.thread_store import LocalThreadStore

    store = LocalThreadStore(tmp_path)
    turn = run_conversation_turn(
        "t1",
        "What was Google's total debt?",
        _runtime(completer=_UnknownMetricCompleter(), facts=_SilentFacts()),
        store=store,
    )

    assert turn.result.renderer is RendererKind.REFUSE
    assert turn.result.candidates == ()
    assert turn.result.message is not None
    assert turn.result.message.startswith("I can't look up debt yet.")
    state = store.load("t1")
    assert state is not None
    assert state.pending_clarification is None


def test_unrelated_question_discards_pending_clarification(tmp_path: Path) -> None:
    from financial_analyst_agent.contracts import Intent, RendererKind
    from financial_analyst_agent.conversation import (
        DISCARDED_CLARIFICATION_BANNER,
        run_conversation_turn,
    )
    from financial_analyst_agent.thread_store import LocalThreadStore

    store = LocalThreadStore(tmp_path)
    run_conversation_turn(
        "t1",
        "What was Google's profit?",
        _runtime(completer=_GuessNetIncome(), facts=_SilentFacts()),
        store=store,
    )

    turn = run_conversation_turn(
        "t1",
        "How can AI disrupt healthcare?",
        _runtime(
            completer=_ExplainCompleter(),
            facts=_SilentFacts(),
            essay=_NumberFreeEssay(),
        ),
        store=store,
    )

    assert turn.result.intent is Intent.EXPLAIN
    assert turn.result.renderer is RendererKind.ESSAY
    assert DISCARDED_CLARIFICATION_BANNER in turn.result.banners
    state = store.load("t1")
    assert state is not None
    assert state.pending_clarification is None


def test_ambiguous_mode_follow_up_clarifies_instead_of_guessing(tmp_path: Path) -> None:
    from financial_analyst_agent.contracts import RendererKind
    from financial_analyst_agent.conversation import run_conversation_turn
    from financial_analyst_agent.graph.analysis_spec import SpecPatch
    from financial_analyst_agent.thread_store import LocalThreadStore

    store = LocalThreadStore(tmp_path)
    facts = _LookupFacts()
    run_conversation_turn(
        "t1",
        "What was Google's net income based on their latest quarterly report?",
        _runtime(completer=_GuessNetIncome(), facts=facts),
        store=store,
    )
    # The lone fact also reads the quarter before it, for its change chip.
    assert set(facts.calls) == {("Google", "net_income")}

    class _AmbiguousMode:
        def complete(self, query: str, current_spec: object = None) -> SpecPatch:
            return SpecPatch(
                mode=None,
                add_operations=("across_periods",),
                set_periods=None,
            )

    turn = run_conversation_turn(
        "t1",
        "compare to last year",
        _runtime(completer=_AmbiguousMode(), facts=_SilentFacts()),
        store=store,
    )

    assert turn.result.renderer is RendererKind.CLARIFY
    assert turn.result.tool_traces == []
    assert turn.result.candidates == ("extend", "replace")
    assert turn.result.clarify_kind == "ambiguous_mode"
    state = store.load("t1")
    assert state is not None
    assert state.pending_clarification is not None
    assert state.pending_clarification.kind == "ambiguous_mode"
    # Prior resolved analysis remains until the mode is chosen.
    assert state.analysis_spec is not None
    assert state.analysis_spec.metrics == ("net_income",)


def test_answering_mode_clarification_resumes_with_chosen_mode(tmp_path: Path) -> None:
    from financial_analyst_agent.contracts import RendererKind
    from financial_analyst_agent.conversation import run_conversation_turn
    from financial_analyst_agent.graph.analysis_spec import PeriodSelection, SpecPatch
    from financial_analyst_agent.thread_store import LocalThreadStore

    store = LocalThreadStore(tmp_path)
    facts = _LookupFacts()
    run_conversation_turn(
        "t1",
        "What was Google's net income based on their latest quarterly report?",
        _runtime(completer=_GuessNetIncome(), facts=facts),
        store=store,
    )

    class _AmbiguousMode:
        def complete(self, query: str, current_spec: object = None) -> SpecPatch:
            return SpecPatch(
                mode=None,
                set_periods=PeriodSelection(kind="last_n_quarters", count=2),
                add_operations=("across_periods",),
            )

    run_conversation_turn(
        "t1",
        "compare to last year",
        _runtime(completer=_AmbiguousMode(), facts=_SilentFacts()),
        store=store,
    )

    turn = run_conversation_turn(
        "t1",
        "extend",
        _runtime(completer=_AmbiguousMode(), facts=facts),
        store=store,
    )

    assert turn.result.renderer is RendererKind.TABLE
    assert turn.analysis_spec is not None
    assert turn.analysis_spec.periods.kind == "last_n_quarters"
    assert turn.analysis_spec.periods.count == 2
    assert "across_periods" in turn.analysis_spec.operations
    assert [c.query for c in turn.analysis_spec.companies] == ["Google"]
    assert turn.analysis_spec.metrics == ("net_income",)
    state = store.load("t1")
    assert state is not None
    assert state.pending_clarification is None


def test_answering_replace_resumes_the_held_question(tmp_path: Path) -> None:
    from financial_analyst_agent.contracts import RendererKind
    from financial_analyst_agent.conversation import run_conversation_turn
    from financial_analyst_agent.graph.analysis_spec import SpecPatch
    from financial_analyst_agent.thread_store import LocalThreadStore

    store = LocalThreadStore(tmp_path)
    facts = _LookupFacts()
    run_conversation_turn(
        "t1",
        "What was Google's net income based on their latest quarterly report?",
        _runtime(completer=_GuessNetIncome(), facts=facts),
        store=store,
    )

    class _AmbiguousMode:
        def complete(self, query: str, current_spec: object = None) -> SpecPatch:
            return SpecPatch(mode=None, add_companies=("Apple",), add_metrics=("revenue",))

    held = run_conversation_turn(
        "t1",
        "Apple revenue",
        _runtime(completer=_AmbiguousMode(), facts=_SilentFacts()),
        store=store,
    )
    assert held.result.renderer is RendererKind.CLARIFY

    turn = run_conversation_turn(
        "t1",
        "replace",
        _runtime(completer=_AmbiguousMode(), facts=facts),
        store=store,
    )

    assert turn.result.renderer is RendererKind.TABLE, turn.result.message
    assert turn.analysis_spec is not None
    assert [c.query for c in turn.analysis_spec.companies] == ["Apple"]
    assert turn.analysis_spec.metrics == ("revenue",)
