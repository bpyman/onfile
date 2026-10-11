"""OpenAI-backed essay completion for the live runtime."""

from types import SimpleNamespace
from typing import Any

import openai
import pytest

from financial_analyst_agent.config import Settings
from financial_analyst_agent.essay import OpenAIEssayCompleter
from financial_analyst_agent.runtime import live_runtime

_MODEL = "gpt-5.6-terra"
_MINING_QUERY = "How can AI disrupt mining?"
_MINING_ESSAY = "AI can improve ore sorting and predictive maintenance in mining."
_NEWS_QUERY = "What is going on with NVIDIA's supply chain?"
_NEWS_TOOL_JSON = (
    '[{"title":"NVIDIA flags packaging constraints",'
    '"url":"https://example.test/nvidia","snippet":"CoWoS lead times remain extended."}]'
)


class _FakeOpenAIClient:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self.responses = SimpleNamespace(create=self.create)

    def create(self, **kwargs: Any) -> object:
        self.calls.append(kwargs)
        return SimpleNamespace(output_text=_MINING_ESSAY)


def test_live_runtime_generates_explain_essay_with_openai(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _FakeOpenAIClient()
    monkeypatch.setattr(openai, "OpenAI", lambda **_kwargs: client)
    runtime = live_runtime(
        Settings(
            openai_api_key="sk-test",
            openai_model=_MODEL,
            sec_user_agent="FinancialAnalystAgent (dev@example.com)",
            tavily_api_key="tvly-test",
        )
    )

    assert runtime.essay is not None
    essay = runtime.essay.complete_essay(_MINING_QUERY)

    assert essay == _MINING_ESSAY
    assert len(client.calls) == 1
    # Essays run on their own model, not the planner's (docs/evaluation/essay-evaluation.md).
    assert client.calls[0]["model"] == "gpt-6.1-sol"
    assert _MINING_QUERY in client.calls[0]["input"]


def test_openai_news_essay_receives_query_and_tool_json() -> None:
    client = _FakeOpenAIClient()
    completer = OpenAIEssayCompleter(client, _MODEL)

    completer.complete_essay(_NEWS_QUERY, _NEWS_TOOL_JSON)

    prompt = client.calls[0]["input"]
    assert _NEWS_QUERY in prompt
    assert _NEWS_TOOL_JSON in prompt
    instructions = client.calls[0]["instructions"].casefold()
    assert "news coverage from the past week" in instructions
    assert "build the answer only from it" in instructions
    assert "[2][4]" in client.calls[0]["instructions"]
    assert "the figure check" in instructions


def test_openai_explain_with_analysis_json_does_not_use_news_instructions() -> None:
    client = _FakeOpenAIClient()
    completer = OpenAIEssayCompleter(client, _MODEL)
    analysis_json = (
        '[{"company_name":"Apple Inc.","metric":"revenue","value":"100"}]'
    )

    completer.complete_essay("How could AI change bank underwriting?", analysis_json)

    instructions = client.calls[0]["instructions"].casefold()
    assert "news coverage" not in instructions
    assert "call it the table" in instructions
    assert "bank underwriting" in client.calls[0]["input"].casefold()
    assert "News tool JSON" not in client.calls[0]["input"]
    assert "do not include numeric tokens" not in instructions
    assert "analysis json" in client.calls[0]["input"].casefold() or (
        "100" in client.calls[0]["input"]
    )
