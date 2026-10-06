"""Explain with numeral lock through run_turn."""

from datetime import date
from types import SimpleNamespace

import pytest

from financial_analyst_agent.contracts import (
    MODEL_ANALYSIS_BANNER,
    EssayCompleter,
    Intent,
    RendererKind,
    Runtime,
    WorkflowPlan,
)
from financial_analyst_agent.domain.errors import ProviderError, ProviderRefusal
from financial_analyst_agent.runtime import FIXTURE_EXPLAIN_ESSAY, recorded_runtime
from financial_analyst_agent.turn import ESSAY_UNAVAILABLE_MESSAGE, run_turn
from helpers import FakeFacts

AI_HEALTHCARE_QUERY = "How can AI disrupt healthcare?"
AI_MINING_QUERY = "How can AI disrupt mining?"


class _ExplainCompleter:
    def complete(self, query: str, current_spec: object = None) -> WorkflowPlan:
        if query != AI_HEALTHCARE_QUERY:
            raise AssertionError(f"unexpected query: {query!r}")
        return WorkflowPlan(intent=Intent.EXPLAIN, topic=query)


class _NumberFreeEssay:
    def complete_essay(self, query: str, tool_json: str = "") -> str:
        if query != AI_HEALTHCARE_QUERY:
            raise AssertionError(f"unexpected essay query: {query!r}")
        return FIXTURE_EXPLAIN_ESSAY


class _ExplodingFacts(FakeFacts):
    def get_financials(
        self, company: str, metric: str, *, report_date: date | None = None
    ) -> SimpleNamespace:
        raise AssertionError("explain must not look up financials")


class _ExplodingRanking:
    def rank_companies(self, industry: str, limit: int) -> SimpleNamespace:
        raise AssertionError("explain must not rank companies")


def _explain_runtime(essay: EssayCompleter) -> Runtime:
    return Runtime(
        completer=_ExplainCompleter(),
        facts=_ExplodingFacts(),
        ranking=_ExplodingRanking(),
        essay=essay,
    )


class _InventedDollarEssay:
    def complete_essay(self, query: str, tool_json: str = "") -> str:
        return "AI imaging will create a $29.8B market without citing a filing."


@pytest.mark.parametrize(
    ("failure", "shown"),
    [
        (ProviderRefusal("Written answers are off"), "Written answers are off"),
        (ProviderError("OpenAI 502 Bad Gateway"), ESSAY_UNAVAILABLE_MESSAGE),
    ],
)
def test_explain_applies_the_visitor_error_rule(
    failure: ProviderError, shown: str
) -> None:
    class _RefusingEssay:
        def complete_essay(self, query: str, tool_json: str = "") -> str:
            raise failure

    result = run_turn(AI_HEALTHCARE_QUERY, _explain_runtime(_RefusingEssay()))

    assert result.renderer is RendererKind.REFUSE
    assert result.message == shown


def test_run_turn_explain_returns_model_analysis_essay_without_retrieval() -> None:
    result = run_turn(AI_HEALTHCARE_QUERY, _explain_runtime(_NumberFreeEssay()))

    assert result.intent is Intent.EXPLAIN
    assert result.renderer is RendererKind.ESSAY
    assert MODEL_ANALYSIS_BANNER in result.banners
    assert result.essay == FIXTURE_EXPLAIN_ESSAY
    assert result.table_rows == []
    assert result.numeral_lock_extras == []
    tools = [trace.tool for trace in result.tool_traces]
    assert "search_news" not in tools
    assert "get_financials" not in tools
    assert "rank_companies" not in tools


def test_run_turn_explain_fails_numeral_lock_on_novel_dollars() -> None:
    result = run_turn(AI_HEALTHCARE_QUERY, _explain_runtime(_InventedDollarEssay()))

    assert result.intent is Intent.EXPLAIN
    assert result.renderer is RendererKind.REFUSE
    assert result.essay is None
    assert MODEL_ANALYSIS_BANNER not in result.banners
    assert result.numeral_lock_extras
    assert any("29.8" in extra for extra in result.numeral_lock_extras)
    assert result.message is not None
    assert "29.8" in result.message


def test_recorded_runtime_explain_uses_injected_essay_completer() -> None:
    result = run_turn(AI_HEALTHCARE_QUERY, recorded_runtime())

    assert result.intent is Intent.EXPLAIN
    assert result.renderer is RendererKind.ESSAY
    assert MODEL_ANALYSIS_BANNER in result.banners
    assert result.essay is not None
    assert result.essay.strip()
    assert result.numeral_lock_extras == []
    tools = [trace.tool for trace in result.tool_traces]
    assert "search_news" not in tools


def test_recorded_runtime_refuses_explain_without_matching_recording() -> None:
    result = run_turn(AI_MINING_QUERY, recorded_runtime())

    assert result.intent is Intent.EXPLAIN
    assert result.renderer is RendererKind.REFUSE
    assert result.essay is None
    assert result.message is not None
    assert "recorded" in result.message.casefold()


BUYBACK_QUERY = "Explain how a share buyback affects EPS"


class _FigureProposer:
    """A planner that reads a general question as a figure with no company."""

    def complete(self, query: str, current_spec: object = None) -> WorkflowPlan:
        return WorkflowPlan(intent=Intent.LOOKUP, metric="eps_diluted")


class _BuybackEssay:
    def complete_essay(self, query: str, tool_json: str = "") -> str:
        if query != BUYBACK_QUERY:
            raise AssertionError(f"unexpected essay query: {query!r}")
        return "A buyback retires shares, so the same net income is spread over fewer of them."


def _proposed_figure_runtime() -> Runtime:
    return Runtime(
        completer=_FigureProposer(),
        facts=_ExplodingFacts(),
        ranking=_ExplodingRanking(),
        essay=_BuybackEssay(),
    )


def test_a_general_question_naming_a_metric_explains_whatever_the_planner_proposed() -> None:
    result = run_turn(BUYBACK_QUERY, _proposed_figure_runtime())

    assert result.intent is Intent.EXPLAIN
    assert result.renderer is RendererKind.ESSAY
    assert MODEL_ANALYSIS_BANNER in result.banners
    assert result.table_rows == []


def test_a_figure_with_no_company_asks_which_company_not_an_explanation() -> None:
    result = run_turn("What's the EPS?", _proposed_figure_runtime())

    assert result.intent is Intent.LOOKUP
    assert result.renderer is RendererKind.REFUSE
    assert result.message is not None
    assert result.message.startswith("I couldn't tell which company you mean.")
