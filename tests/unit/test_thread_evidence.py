"""Conversation seam: thread evidence store (ticket 13).

Facts, news hits, and results are addressed by identifier and referenced from
thread state. Follow-ups reuse retained evidence (labelled); qualitative turns
receive the already-computed deterministic result. Asserts the public seam and
persisted thread shape — not graph internals.
"""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import quote

from financial_analyst_agent.contracts import WorkflowPlan
from financial_analyst_agent.runtime import FIXTURE_UNIVERSE_SNAPSHOT_PATH
from helpers import named_by_cik

# Resolved companies are asked for by CIK; these fakes answer by name.
_NAMED = named_by_cik('Microsoft', 'Google')


class _CountingFacts:
    """Records every provider call; returns stable quarterly facts."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str, date | None]] = []

    def get_financials(
        self,
        company: str,
        metric: str,
        *,
        report_date: date | None = None,
    ) -> SimpleNamespace:
        company = _NAMED(company)
        self.calls.append((company, metric, report_date))
        values = {
            ("Microsoft", "revenue"): Decimal("400"),
            ("Microsoft", "operating_income"): Decimal("100"),
            ("Microsoft", "net_income"): Decimal("80"),
            ("Microsoft", "research_and_development"): Decimal("40"),
            ("Google", "revenue"): Decimal("200"),
            ("Google", "operating_income"): Decimal("50"),
            ("Google", "net_income"): Decimal("40"),
            ("Google", "research_and_development"): Decimal("20"),
        }
        value = values[(company, metric)]
        return SimpleNamespace(
            company_name=company,
            ticker="MSFT" if company == "Microsoft" else "GOOG",
            cik="0000789019" if company == "Microsoft" else "0001652044",
            metric=metric,
            value=value,
            currency="USD",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 3, 31),
            filed_date=date(2026, 3, 31),
            form="10-Q",
            accession_number="acc",
            taxonomy="us-gaap",
            concept=metric,
            source_url="https://www.sec.gov/example.htm",
            source="sec_xbrl",
        )


class _CompareCompleter:
    def complete(self, query: str, current_spec: object = None) -> WorkflowPlan:
        from financial_analyst_agent.contracts import Intent

        return WorkflowPlan(
            intent=Intent.COMPARE,
            company=None,
            companies=["Microsoft", "Google"],
            metric="revenue",
            industry=None,
            topic=None,
        )


def _runtime(*, completer: object, facts: object | None = None, essay: object | None = None):
    from financial_analyst_agent.contracts import Runtime
    from financial_analyst_agent.ranking import SnapshotRanking

    return Runtime(
        completer=completer,  # type: ignore[arg-type]
        facts=(facts or _CountingFacts()),  # type: ignore[arg-type]
        ranking=SnapshotRanking.from_path(FIXTURE_UNIVERSE_SNAPSHOT_PATH),
        essay=essay,  # type: ignore[arg-type]
    )


def test_thread_state_references_evidence_by_id_not_inline_results(tmp_path: Path) -> None:
    from financial_analyst_agent.conversation import run_conversation_turn
    from financial_analyst_agent.thread_store import LocalThreadStore

    store = LocalThreadStore(tmp_path)
    turn = run_conversation_turn(
        "t1",
        "compare Microsoft and Google on revenue",
        _runtime(completer=_CompareCompleter()),
        store=store,
    )
    assert turn.result.table_rows
    state = store.load("t1")
    assert state is not None
    assert store.resolve_results(state) == (turn.result,)
    dumped = state.model_dump(mode="json")
    assert "evidence_refs" in dumped
    assert state.evidence_refs
    # Checkpoint stays small: no copied table rows / tool traces on thread state.
    assert "results" not in dumped or dumped.get("results") in (None, (), [])
    assert dumped.get("last_result") in (None, {})
    assert "table_rows" not in json.dumps(dumped)
    path = tmp_path / f"{quote('t1', safe='')}.json"
    raw = path.read_text(encoding="utf-8")
    assert "62578000000" not in raw
    assert '"value"' not in raw or "table_rows" not in raw


def test_follow_up_reuses_retained_evidence_and_labels_it(tmp_path: Path) -> None:
    from financial_analyst_agent.conversation import run_conversation_turn
    from financial_analyst_agent.graph.analysis_spec import SpecPatch
    from financial_analyst_agent.thread_store import LocalThreadStore

    facts = _CountingFacts()
    store = LocalThreadStore(tmp_path)
    run_conversation_turn(
        "t1",
        "compare Microsoft and Google on revenue and operating margin",
        _runtime(completer=_CompareCompleter(), facts=facts),
        store=store,
    )
    first_calls = list(facts.calls)
    assert first_calls

    class _AddRd:
        def complete(self, query: str, current_spec: object = None) -> SpecPatch:
            return SpecPatch(mode="extend", add_metrics=("rd_to_sales",))

    turn = run_conversation_turn(
        "t1",
        "now add R&D intensity",
        _runtime(completer=_AddRd(), facts=facts),
        store=store,
    )
    # Previously fetched cells are not refetched; only new components are.
    new_calls = facts.calls[len(first_calls) :]
    assert ("Microsoft", "revenue", None) not in new_calls
    assert ("Google", "revenue", None) not in new_calls
    assert ("Microsoft", "operating_income", None) not in new_calls
    assert any(metric == "research_and_development" for _, metric, _ in new_calls)

    assert any(
        "thread evidence" in banner.casefold() for banner in turn.result.banners
    )
    metrics_present = {row.metric for row in turn.result.table_rows}
    assert metrics_present == {"revenue", "operating_margin", "rd_to_sales"}


def test_qualitative_after_analysis_receives_deterministic_result(tmp_path: Path) -> None:
    from financial_analyst_agent.contracts import Intent, RendererKind
    from financial_analyst_agent.conversation import run_conversation_turn
    from financial_analyst_agent.thread_store import LocalThreadStore

    facts = _CountingFacts()
    store = LocalThreadStore(tmp_path)
    run_conversation_turn(
        "t1",
        "compare Microsoft and Google on revenue",
        _runtime(completer=_CompareCompleter(), facts=facts),
        store=store,
    )

    received: dict[str, str] = {}

    class _ExplainCompleter:
        def complete(self, query: str, current_spec: object = None) -> WorkflowPlan:
            return WorkflowPlan(
                intent=Intent.EXPLAIN,
                company=None,
                metric=None,
                industry=None,
                topic="what do these numbers imply",
            )

    class _GroundedEssay:
        def complete_essay(self, query: str, tool_json: str = "") -> str:
            received["tool_json"] = tool_json
            # Use a numeral that appears in the prior analysis table.
            return "Microsoft revenue was 400 while Google was 200."

    turn = run_conversation_turn(
        "t1",
        "what do these numbers imply",
        _runtime(completer=_ExplainCompleter(), facts=facts, essay=_GroundedEssay()),
        store=store,
    )
    assert turn.result.intent is Intent.EXPLAIN
    assert turn.result.renderer is RendererKind.ESSAY
    assert turn.result.numeral_lock_extras == []
    assert "400" in received["tool_json"]
    assert "200" in received["tool_json"]


def test_explain_after_news_does_not_reuse_prior_news_json(tmp_path: Path) -> None:
    from financial_analyst_agent.contracts import Intent, NewsHit, RendererKind, Runtime
    from financial_analyst_agent.conversation import run_conversation_turn
    from financial_analyst_agent.thread_store import LocalThreadStore

    store = LocalThreadStore(tmp_path)

    class _NewsCompleter:
        def complete(self, query: str, current_spec: object = None) -> WorkflowPlan:
            return WorkflowPlan(
                intent=Intent.NEWS_AND_EXPLAIN,
                topic=query,
            )

    class _NewsPort:
        def search_news(self, query: str) -> list[NewsHit]:
            return [
                NewsHit(
                    title="Lilly obesity pipeline",
                    url="https://example.test/lilly",
                    snippet="Zepbound sales cited $4.5B after the latest quarter.",
                    score=0.9,
                    published="2026-08-20",
                )
            ]

    class _NewsEssay:
        def complete_essay(self, query: str, tool_json: str = "") -> str:
            return "Lilly obesity coverage cites $4.5B of Zepbound sales [1]."

    news_runtime = Runtime(
        completer=_NewsCompleter(),  # type: ignore[arg-type]
        facts=SimpleNamespace(),  # type: ignore[arg-type]
        news=_NewsPort(),  # type: ignore[arg-type]
        essay=_NewsEssay(),  # type: ignore[arg-type]
        ranking=_runtime(completer=_CompareCompleter()).ranking,
    )
    run_conversation_turn(
        "t1",
        "What's going on with Eli Lilly's obesity drugs?",
        news_runtime,
        store=store,
    )

    received: dict[str, str] = {}

    class _ExplainCompleter:
        def complete(self, query: str, current_spec: object = None) -> WorkflowPlan:
            return WorkflowPlan(
                intent=Intent.EXPLAIN,
                topic=query,
            )

    class _ExplainEssay:
        def complete_essay(self, query: str, tool_json: str = "") -> str:
            received["query"] = query
            received["tool_json"] = tool_json
            return "Bank underwriting can use models to score credit files."

    explain_runtime = Runtime(
        completer=_ExplainCompleter(),  # type: ignore[arg-type]
        facts=SimpleNamespace(),  # type: ignore[arg-type]
        essay=_ExplainEssay(),  # type: ignore[arg-type]
        ranking=news_runtime.ranking,
    )
    turn = run_conversation_turn(
        "t1",
        "How could AI change bank underwriting?",
        explain_runtime,
        store=store,
    )
    assert turn.result.intent is Intent.EXPLAIN
    assert turn.result.renderer is RendererKind.ESSAY
    assert "obesity" not in received["tool_json"].casefold()
    assert "4.5B" not in received["tool_json"]
    assert "Lilly" not in received["tool_json"]
    assert received["tool_json"] == ""


def test_thread_checkpoint_stays_small_as_turns_accumulate(tmp_path: Path) -> None:
    from financial_analyst_agent.conversation import run_conversation_turn
    from financial_analyst_agent.graph.analysis_spec import SpecPatch
    from financial_analyst_agent.thread_store import LocalThreadStore

    facts = _CountingFacts()
    store = LocalThreadStore(tmp_path)
    run_conversation_turn(
        "t1",
        "compare Microsoft and Google on revenue",
        _runtime(completer=_CompareCompleter(), facts=facts),
        store=store,
    )

    class _AddNet:
        def complete(self, query: str, current_spec: object = None) -> SpecPatch:
            return SpecPatch(mode="extend", add_metrics=("net_income",))

    for _ in range(5):
        run_conversation_turn(
            "t1",
            "add net income",
            _runtime(completer=_AddNet(), facts=facts),
            store=store,
        )

    path = tmp_path / f"{quote('t1', safe='')}.json"
    checkpoint = path.read_text(encoding="utf-8")
    # Evidence bodies live elsewhere; checkpoint is references + messages + spec.
    assert len(checkpoint) < 8_000
    state = store.load("t1")
    assert state is not None
    assert len(state.messages) == 6
    result_refs = [ref for ref in state.evidence_refs if ref.startswith("result-")]
    assert len(result_refs) == 6
    assert any(ref.startswith("fact-") for ref in state.evidence_refs)


def test_one_company_by_another_name_reuses_its_evidence(tmp_path: Path) -> None:
    # "Google" and "GOOGL" resolve to Alphabet's CIK, and evidence is kept by CIK,
    # so asking again by ticker refetches nothing.
    from financial_analyst_agent.contracts import Intent
    from financial_analyst_agent.conversation import run_conversation_turn
    from financial_analyst_agent.thread_store import LocalThreadStore

    class _Lookup:
        def __init__(self, company: str) -> None:
            self.company = company

        def complete(self, query: str, current_spec: object = None) -> WorkflowPlan:
            return WorkflowPlan(intent=Intent.LOOKUP, company=self.company, metric="revenue")

    facts = _CountingFacts()
    store = LocalThreadStore(tmp_path)
    run_conversation_turn(
        "t1", "Google revenue", _runtime(completer=_Lookup("Google"), facts=facts), store=store
    )
    asked = len(facts.calls)
    assert asked

    run_conversation_turn(
        "t1", "GOOGL revenue", _runtime(completer=_Lookup("GOOGL"), facts=facts), store=store
    )

    assert len(facts.calls) == asked
