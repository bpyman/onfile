"""Exploratory research lane: labelled, cited, fenced from structured facts.

Asserts the conversation and parent-graph seams. Does not assert LangGraph
node names, channels, or internals.
"""

from __future__ import annotations

from types import SimpleNamespace

from financial_analyst_agent.contracts import WorkflowPlan
from helpers import FakeFacts

FIXTURE_RESEARCH_QUERY = (
    "What themes are emerging in coverage of Hormuz closures and energy markets?"
)


class _SilentCompleter:
    def complete(self, query: str, current_spec: object = None) -> SimpleNamespace:
        raise AssertionError("workflow graph entry must not re-plan")


class _ExploratoryCompleter:
    def complete(self, query: str, current_spec: object = None) -> WorkflowPlan:
        from financial_analyst_agent.contracts import Intent

        return WorkflowPlan(intent=Intent.EXPLORATORY_RESEARCH, topic=query)


class _GroundedResearchEssay:
    def complete_essay(self, query: str, tool_json: str = "") -> str:
        if "$1.2B" not in tool_json:
            raise AssertionError("research essay must receive news evidence JSON")
        return (
            "Recent coverage highlights delayed crude loadings around Hormuz, "
            "including ExxonMobil's cited $1.2B of delayed loadings [1]."
        )


class _InventedDollarEssay:
    def complete_essay(self, query: str, tool_json: str = "") -> str:
        return "Coverage invents a $99.9B energy windfall with no source."


class _ExplodingFacts(FakeFacts):
    def get_financials(self, company: str, metric: str, **_kwargs: object) -> object:
        raise AssertionError("exploratory research must not look up financials")


class _ExplodingRanking:
    def rank_companies(self, industry: str, limit: int) -> object:
        raise AssertionError("exploratory research must not rank companies")

    def lookup_member(self, company: str) -> object:
        raise AssertionError("exploratory research must not look up members")

    def snapshot_as_of(self) -> str:
        raise AssertionError("exploratory research must not read the snapshot")

    def snapshot_source(self) -> str:
        raise AssertionError("exploratory research must not read the snapshot")


class _FixtureNews:
    def search_news(self, query: str) -> list:
        from financial_analyst_agent.contracts import NewsHit

        return [
            NewsHit(
                title="Hormuz closures slow crude loadings",
                url="https://example.test/hormuz-exxon",
                snippet=(
                    "ExxonMobil cited $1.2B of delayed loadings after the "
                    "strait closures."
                ),
                score=0.91,
                published="2026-08-18",
            )
        ]


class _EmptyNews:
    def search_news(self, query: str) -> list:
        return []


class _ExplodingEssay:
    def complete_essay(self, query: str, tool_json: str = "") -> str:
        raise AssertionError("empty news hits must not fall back to a memory essay")


def _runtime(
    *,
    completer: object | None = None,
    essay: object | None = None,
    news: object | None = None,
) -> object:
    from financial_analyst_agent.contracts import Runtime

    return Runtime(
        completer=completer or _SilentCompleter(),  # type: ignore[arg-type]
        facts=_ExplodingFacts(),  # type: ignore[arg-type]
        ranking=_ExplodingRanking(),  # type: ignore[arg-type]
        essay=essay,  # type: ignore[arg-type]
        news=news,  # type: ignore[arg-type]
    )


def test_exploratory_research_returns_labelled_cited_research() -> None:
    from financial_analyst_agent.contracts import (
        EXPLORATORY_RESEARCH_BANNER,
        Intent,
        RendererKind,
    )
    from financial_analyst_agent.turn import exploratory_research_answer

    result = exploratory_research_answer(
        FIXTURE_RESEARCH_QUERY,
        _runtime(essay=_GroundedResearchEssay(), news=_FixtureNews()),  # type: ignore[arg-type]
    )

    assert result.intent == Intent.EXPLORATORY_RESEARCH
    assert result.renderer == RendererKind.ESSAY
    assert EXPLORATORY_RESEARCH_BANNER in result.banners
    assert "model-analysis" not in result.banners
    assert result.citations
    assert result.citations[0].url == "https://example.test/hormuz-exxon"
    assert result.table_rows == []
    assert result.numeral_lock_extras == []
    assert result.essay is not None
    assert "$1.2B" in result.essay
    assert result.tool_traces[0].tool == "search_news"
    assert result.tool_traces[0].args["topic"] == "news"


def test_exploratory_research_refuses_invented_numerals() -> None:
    from financial_analyst_agent.contracts import (
        EXPLORATORY_RESEARCH_BANNER,
        Intent,
        RendererKind,
    )
    from financial_analyst_agent.turn import exploratory_research_answer

    result = exploratory_research_answer(
        FIXTURE_RESEARCH_QUERY,
        _runtime(essay=_InventedDollarEssay(), news=_FixtureNews()),  # type: ignore[arg-type]
    )

    assert result.intent == Intent.EXPLORATORY_RESEARCH
    assert result.renderer == RendererKind.REFUSE
    assert result.essay is None
    assert result.table_rows == []
    assert EXPLORATORY_RESEARCH_BANNER not in result.banners
    assert any("99.9" in extra for extra in result.numeral_lock_extras)
    assert result.message is not None
    assert "99.9" in result.message


def test_exploratory_research_refuses_empty_hits_without_essay() -> None:
    from financial_analyst_agent.contracts import Intent, RendererKind
    from financial_analyst_agent.turn import exploratory_research_answer

    result = exploratory_research_answer(
        FIXTURE_RESEARCH_QUERY,
        _runtime(essay=_ExplodingEssay(), news=_EmptyNews()),  # type: ignore[arg-type]
    )

    assert result.intent == Intent.EXPLORATORY_RESEARCH
    assert result.renderer == RendererKind.REFUSE
    assert result.essay is None
    assert result.table_rows == []
    assert result.citations == []


def test_conversation_routes_non_analysis_question_to_exploratory_lane() -> None:
    from financial_analyst_agent.contracts import (
        EXPLORATORY_RESEARCH_BANNER,
        Intent,
        RendererKind,
    )
    from financial_analyst_agent.conversation import run_conversation_turn
    from financial_analyst_agent.thread_store import EphemeralThreadStore

    store = EphemeralThreadStore()
    turn = run_conversation_turn(
        "t-research",
        FIXTURE_RESEARCH_QUERY,
        _runtime(
            completer=_ExploratoryCompleter(),
            essay=_GroundedResearchEssay(),
            news=_FixtureNews(),
        ),  # type: ignore[arg-type]
        store=store,
    )

    assert turn.result.intent == Intent.EXPLORATORY_RESEARCH
    assert turn.result.renderer == RendererKind.ESSAY
    assert EXPLORATORY_RESEARCH_BANNER in turn.result.banners
    assert turn.result.citations
    assert turn.result.table_rows == []
    assert turn.analysis_spec is None
    assert turn.result.intent == Intent.EXPLORATORY_RESEARCH
