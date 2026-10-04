"""Conversation seam: analysis spec patch follow-ups (ticket 08).

Asserts editable specs at the public conversation entry. Does not assert
graph internals. Uses a real temporary store.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from financial_analyst_agent.contracts import WorkflowPlan
from financial_analyst_agent.runtime import FIXTURE_UNIVERSE_SNAPSHOT_PATH


class _LookupFacts:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def get_financials(

        self, company: str, metric: str, *, report_date: date | None = None

    ) -> SimpleNamespace:
        self.calls.append((company, metric))
        values = {
            ("Google", "net_income"): Decimal("62578000000"),
            ("Apple", "net_income"): Decimal("11100000000"),
            ("Nvidia", "net_income"): Decimal("9000000000"),
        }
        value = values[(company, metric)]
        ticker = {"Google": "GOOG", "Apple": "AAPL", "Nvidia": "NVDA"}[company]
        cik = {
            "Google": "0001652044",
            "Apple": "0000320193",
            "Nvidia": "0001045810",
        }[company]
        return SimpleNamespace(
            company_name=company,
            ticker=ticker,
            cik=cik,
            metric=metric,
            value=value,
            currency="USD",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 3, 31),
            filed_date=date(2026, 3, 31),
            form="10-Q",
            accession_number="acc",
            taxonomy="us-gaap",
            concept="NetIncomeLoss",
            source_url="https://www.sec.gov/example.htm",
            source="sec_xbrl",
        )


class _SilentFacts:
    def get_financials(
        self, company: str, metric: str, *, report_date: date | None = None
    ) -> SimpleNamespace:
        raise AssertionError(f"provider must not run for invalid patch: {company} {metric}")


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
        from financial_analyst_agent.runtime import FIXTURE_EXPLAIN_ESSAY

        return FIXTURE_EXPLAIN_ESSAY


def _runtime(
    *,
    completer: object,
    facts: object | None = None,
    ranking: object | None = None,
    essay: object | None = None,
):
    from financial_analyst_agent.contracts import Runtime
    from financial_analyst_agent.ranking import SnapshotRanking

    return Runtime(
        completer=completer,  # type: ignore[arg-type]
        facts=(facts or _LookupFacts()),  # type: ignore[arg-type]
        ranking=ranking
        if ranking is not None
        else SnapshotRanking.from_path(FIXTURE_UNIVERSE_SNAPSHOT_PATH),
        essay=essay,  # type: ignore[arg-type]
    )


def test_first_message_produces_resolved_spec_and_lookup_answer(tmp_path: Path) -> None:
    from financial_analyst_agent.contracts import Intent, RendererKind
    from financial_analyst_agent.conversation import run_conversation_turn
    from financial_analyst_agent.thread_store import LocalThreadStore

    store = LocalThreadStore(tmp_path)
    message = "What was Google's net income based on their latest quarterly report?"
    turn = run_conversation_turn(
        "t1",
        message,
        _runtime(completer=_LookupCompleter()),
        store=store,
    )

    assert turn.result.intent is Intent.LOOKUP
    assert turn.result.renderer is RendererKind.TABLE
    assert turn.result.table_rows[0].ticker == "GOOG"
    assert turn.analysis_spec is not None
    assert [c.query for c in turn.analysis_spec.companies] == ["Google"]
    assert turn.analysis_spec.metrics == ("net_income",)
    assert turn.analysis_spec.periods.kind == "latest_quarter"
    assert turn.proposed_patch is not None
    assert turn.proposed_patch.mode == "replace"
    state = store.load("t1")
    assert state is not None
    assert state.analysis_spec is not None
    assert state.analysis_spec.metrics == ("net_income",)
    dumped = state.model_dump()
    assert "proposed_patch" not in dumped


def test_swap_add_remove_company_keeps_metrics(tmp_path: Path) -> None:
    from financial_analyst_agent.contracts import Intent
    from financial_analyst_agent.conversation import run_conversation_turn
    from financial_analyst_agent.graph.analysis_spec import SpecPatch
    from financial_analyst_agent.thread_store import LocalThreadStore

    store = LocalThreadStore(tmp_path)
    facts = _LookupFacts()
    runtime = _runtime(completer=_LookupCompleter(), facts=facts)
    run_conversation_turn(
        "t1",
        "What was Google's net income based on their latest quarterly report?",
        runtime,
        store=store,
    )

    class _Swap:
        def complete(self, query: str, current_spec: object = None) -> SpecPatch:
            return SpecPatch(
                mode="extend",
                remove_companies=("Google",),
                add_companies=("Apple",),
            )

    turn = run_conversation_turn(
        "t1",
        "use Apple instead of Google",
        _runtime(completer=_Swap(), facts=facts),
        store=store,
    )
    assert turn.result.intent is Intent.LOOKUP
    assert [c.query for c in turn.analysis_spec.companies] == ["Apple"]  # type: ignore[union-attr]
    assert turn.analysis_spec.metrics == ("net_income",)  # type: ignore[union-attr]
    assert facts.calls[-1] == ("Apple", "net_income")

    class _Add:
        def complete(self, query: str, current_spec: object = None) -> SpecPatch:
            return SpecPatch(mode="extend", add_companies=("Nvidia",))

    turn = run_conversation_turn(
        "t1",
        "add Nvidia",
        _runtime(completer=_Add(), facts=facts),
        store=store,
    )
    assert turn.result.intent.value == "compare"
    assert [c.query for c in turn.analysis_spec.companies] == ["Apple", "Nvidia"]  # type: ignore[union-attr]
    assert turn.analysis_spec.metrics == ("net_income",)  # type: ignore[union-attr]

    class _Remove:
        def complete(self, query: str, current_spec: object = None) -> SpecPatch:
            return SpecPatch(mode="extend", remove_companies=("Nvidia",))

    turn = run_conversation_turn(
        "t1",
        "drop Nvidia",
        _runtime(completer=_Remove(), facts=facts),
        store=store,
    )
    assert [c.query for c in turn.analysis_spec.companies] == ["Apple"]  # type: ignore[union-attr]
    assert turn.analysis_spec.metrics == ("net_income",)  # type: ignore[union-attr]


def test_unrelated_question_keeps_spec(tmp_path: Path) -> None:
    """An essay or news answer leaves the analysis on screen for the next edit."""
    from financial_analyst_agent.contracts import Intent
    from financial_analyst_agent.conversation import run_conversation_turn
    from financial_analyst_agent.thread_store import LocalThreadStore

    store = LocalThreadStore(tmp_path)
    run_conversation_turn(
        "t1",
        "What was Google's net income based on their latest quarterly report?",
        _runtime(completer=_LookupCompleter()),
        store=store,
    )
    turn = run_conversation_turn(
        "t1",
        "How can AI disrupt healthcare?",
        _runtime(completer=_ExplainCompleter(), essay=_NumberFreeEssay()),
        store=store,
    )
    assert turn.result.intent is Intent.EXPLAIN
    state = store.load("t1")
    assert state is not None
    assert state.analysis_spec is not None
    assert state.analysis_spec.metrics == ("net_income",)


def test_complete_does_not_retry_internal_typeerror(tmp_path: Path) -> None:
    from financial_analyst_agent.conversation import run_conversation_turn
    from financial_analyst_agent.thread_store import LocalThreadStore

    class _Boom:
        def __init__(self) -> None:
            self.calls = 0

        def complete(self, query: str, current_spec: object = None) -> object:
            self.calls += 1
            raise TypeError("structured parse failed")

    boom = _Boom()
    store = LocalThreadStore(tmp_path)
    try:
        run_conversation_turn("t1", "add Apple", _runtime(completer=boom), store=store)
    except TypeError:
        pass
    else:
        raise AssertionError("expected TypeError to propagate")
    assert boom.calls == 1


def test_invalid_patch_rejects_before_provider(tmp_path: Path) -> None:
    from financial_analyst_agent.contracts import RendererKind
    from financial_analyst_agent.conversation import run_conversation_turn
    from financial_analyst_agent.graph.analysis_spec import SpecPatch
    from financial_analyst_agent.thread_store import LocalThreadStore

    class _BadMetric:
        def complete(self, query: str, current_spec: object = None) -> SpecPatch:
            return SpecPatch(
                mode="replace",
                add_companies=("Google",),
                add_metrics=("not_a_real_metric",),
            )

    store = LocalThreadStore(tmp_path)
    turn = run_conversation_turn(
        "t1",
        "lookup not_a_real_metric for Google",
        _runtime(completer=_BadMetric(), facts=_SilentFacts()),
        store=store,
    )
    assert turn.result.renderer is RendererKind.REFUSE
    assert turn.result.tool_traces == []
    assert turn.analysis_spec is None


def test_ranked_request_uses_ranking_port_ignores_model_companies(tmp_path: Path) -> None:
    from financial_analyst_agent.contracts import Intent
    from financial_analyst_agent.conversation import run_conversation_turn
    from financial_analyst_agent.graph.analysis_spec import SpecPatch
    from financial_analyst_agent.thread_store import LocalThreadStore

    class _RankPatch:
        def complete(self, query: str, current_spec: object = None) -> SpecPatch:
            return SpecPatch(
                mode="replace",
                add_companies=("FakeCo", "InventedInc"),
                ranked_request=("healthcare", 3),
            )

    store = LocalThreadStore(tmp_path)
    turn = run_conversation_turn(
        "t1",
        "top 3 healthcare companies",
        _runtime(completer=_RankPatch(), facts=_SilentFacts()),
        store=store,
    )
    assert turn.result.intent is Intent.RANK
    assert turn.analysis_spec is not None
    assert turn.analysis_spec.companies == ()
    assert turn.analysis_spec.constituents is not None
    assert turn.analysis_spec.constituents.industry == "healthcare"
    assert len(turn.analysis_spec.constituents.members) == 3
    assert all(m.ticker != "FakeCo" for m in turn.analysis_spec.constituents.members)
