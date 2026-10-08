"""OpenAI structured-output planner. Default suite uses a fake parse client."""

from types import SimpleNamespace
from typing import Any

import pytest
from pydantic import ValidationError

from financial_analyst_agent.config import Settings
from financial_analyst_agent.contracts import Intent, WorkflowPlan
from financial_analyst_agent.planner import OpenAIStructuredCompleter, Plan
from financial_analyst_agent.planner_cascade import CascadeCompleter
from financial_analyst_agent.runtime import DemoCompleter, live_runtime, recorded_runtime
from financial_analyst_agent.turn import run_turn
from test_run_turn_lookup import GOOGLE_LATEST_QUARTER_NET_INCOME_QUERY

_MODEL = "gpt-5.6-terra"
_CLOSED_INTENTS = {intent.value for intent in Intent}


class _FakeParseClient:
    def __init__(self, parsed: object) -> None:
        self.calls: list[dict[str, Any]] = []
        self.chat = SimpleNamespace(completions=SimpleNamespace(parse=self.parse))
        self._parsed = parsed

    def parse(self, **kwargs: Any) -> object:
        self.calls.append(kwargs)
        message = SimpleNamespace(parsed=self._parsed, refusal=None)
        return SimpleNamespace(choices=[SimpleNamespace(message=message, finish_reason="stop")])


def test_openai_completer_emits_closed_intent_from_structured_output() -> None:
    parsed = Plan(intent=Intent.LOOKUP, company="Google", metric="net_income")
    client = _FakeParseClient(parsed)
    completer = OpenAIStructuredCompleter(client, _MODEL)

    plan = completer.complete(GOOGLE_LATEST_QUARTER_NET_INCOME_QUERY)

    # The model's response schema becomes the plan both planners return.
    assert isinstance(plan, WorkflowPlan)
    assert plan.intent is Intent.LOOKUP
    assert plan.intent.value in _CLOSED_INTENTS
    assert plan.company == "Google"
    assert plan.metric == "net_income"
    assert client.calls[0]["model"] == _MODEL
    assert client.calls[0]["response_format"] is Plan
    contents = [item["content"] for item in client.calls[0]["messages"]]
    assert GOOGLE_LATEST_QUARTER_NET_INCOME_QUERY in contents


def test_openai_completer_schema_only_allows_closed_intents() -> None:
    schema = Plan.model_json_schema()
    variants = schema["properties"]["action"]["anyOf"]
    names = {
        schema["$defs"][variant["$ref"].rsplit("/", maxsplit=1)[-1]]["properties"][
            "intent"
        ]["const"]
        for variant in variants
    }
    assert names == _CLOSED_INTENTS


@pytest.mark.parametrize(
    ("payload", "missing_parameter"),
    [
        ({"intent": "lookup", "metric": "net_income"}, "company"),
        ({"intent": "lookup", "company": "Google"}, "metric"),
        (
            {"intent": "compare", "companies": ["Microsoft"], "metric": "net_margin"},
            "companies",
        ),
        ({"intent": "compare", "companies": ["Microsoft", "Google"]}, "metric"),
        ({"intent": "rank", "industry": None, "limit": 10}, "industry"),
        ({"intent": "rank", "industry": "   ", "limit": 10}, "industry"),
        ({"intent": "rank", "industry": "healthcare", "limit": 0}, "limit"),
        ({"intent": "rank_and_lookup", "metric": "net_income", "limit": 10}, "industry"),
        ({"intent": "rank_and_lookup", "industry": "healthcare", "limit": 10}, "metric"),
        (
            {
                "intent": "rank_and_lookup",
                "industry": "healthcare",
                "metric": "net_income",
                "limit": 0,
            },
            "limit",
        ),
        ({"intent": "explain"}, "topic"),
    ],
    ids=[
        "lookup-company",
        "lookup-metric",
        "compare-companies",
        "compare-metric",
        "rank-industry",
        "rank-blank-industry",
        "rank-limit",
        "rank-and-lookup-industry",
        "rank-and-lookup-metric",
        "rank-and-lookup-limit",
        "explain-topic",
    ],
)
def test_plan_rejects_incomplete_intent_parameters(
    payload: dict[str, object], missing_parameter: str
) -> None:
    with pytest.raises(ValidationError, match=missing_parameter):
        Plan.model_validate(payload)


def test_live_runtime_without_openai_key_plans_with_the_rules_planner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # The rules planner serves the public demo; a live run without a key uses it
    # too rather than failing every turn.
    monkeypatch.setenv("APP_MODE", "live")
    monkeypatch.setenv("OPENAI_API_KEY", "")
    monkeypatch.setenv("TAVILY_API_KEY", "")
    monkeypatch.setenv("SEC_USER_AGENT", "FinancialAnalystAgent (dev@example.com)")
    runtime = live_runtime(Settings())
    assert isinstance(runtime.completer, DemoCompleter)


def test_live_runtime_plans_with_the_cascade_when_openai_is_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("OPENAI_MODEL", _MODEL)
    monkeypatch.setenv("SEC_USER_AGENT", "FinancialAnalystAgent (dev@example.com)")
    runtime = live_runtime(Settings())
    assert isinstance(runtime.completer, CascadeCompleter)
    # The rules planner plans first; the LLM planner is asked only where it is unsure.
    assert isinstance(runtime.completer._rules, DemoCompleter)
    assert isinstance(runtime.completer._llm, OpenAIStructuredCompleter)


def test_recorded_runtime_still_uses_injected_fake_completer() -> None:
    runtime = recorded_runtime()
    assert isinstance(runtime.completer, DemoCompleter)
    result = run_turn(GOOGLE_LATEST_QUARTER_NET_INCOME_QUERY, runtime)
    assert result.intent is Intent.LOOKUP


def test_a_plan_the_sdk_leaves_unparsed_is_read_against_the_schema_asked_for() -> None:
    from financial_analyst_agent.graph.analysis_spec import AnalysisSpec, SpecPatch

    first = OpenAIStructuredCompleter(
        _FakeParseClient({"intent": "lookup", "company": "Google", "metric": "net_income"}),
        _MODEL,
    ).complete(GOOGLE_LATEST_QUARTER_NET_INCOME_QUERY)
    assert first == WorkflowPlan(intent=Intent.LOOKUP, company="Google", metric="net_income")

    follow_up = OpenAIStructuredCompleter(
        _FakeParseClient({"intent": "spec_patch", "mode": "extend", "add_companies": ["Apple"]}),
        _MODEL,
    ).complete("add Apple", current_spec=AnalysisSpec())
    assert follow_up == SpecPatch(mode="extend", add_companies=("Apple",))
