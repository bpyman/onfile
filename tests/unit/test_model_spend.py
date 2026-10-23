"""The daily ceiling on OpenAI spend: what a request costs, and what stops at the ceiling."""

import json
from datetime import date
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from financial_analyst_agent.contracts import Intent, RendererKind, Runtime, WorkflowPlan
from financial_analyst_agent.domain.errors import PlannerError
from financial_analyst_agent.essay import OpenAIEssayCompleter
from financial_analyst_agent.model_spend import (
    SPEND_CAP_MESSAGE,
    DailySpendCap,
    SpendCapReached,
    request_cost,
)
from financial_analyst_agent.planner import OpenAIStructuredCompleter, Plan
from financial_analyst_agent.planner_cascade import CascadeCompleter
from financial_analyst_agent.turn import explain_answer, run_turn
from test_run_turn_news import NVIDIA_SUPPLY_QUERY, _ExplodingFacts, _FixtureNews, _NewsCompleter

_SOL = "gpt-6.1-sol"


def _essay_response(input_tokens: int = 1_000, output_tokens: int = 500) -> SimpleNamespace:
    """A Responses API reply: $2 and $10 a million tokens on sol, so 0.002 + 0.005."""
    usage = SimpleNamespace(input_tokens=input_tokens, output_tokens=output_tokens)
    return SimpleNamespace(output_text="An essay.", usage=usage)


class _Day:
    def __init__(self, day: date) -> None:
        self.day = day

    def __call__(self) -> date:
        return self.day


class _EssayClient:
    def __init__(self) -> None:
        self.calls = 0
        self.responses = SimpleNamespace(create=self.create)

    def create(self, **_kwargs: Any) -> SimpleNamespace:
        self.calls += 1
        return _essay_response()


def test_a_response_costs_its_tokens_at_the_models_price() -> None:
    assert request_cost(_SOL, _essay_response()) == Decimal("0.007")
    # Chat Completions name the same counts prompt and completion tokens.
    chat = SimpleNamespace(usage=SimpleNamespace(prompt_tokens=1_000, completion_tokens=500))
    assert request_cost("gpt-5.6-terra", chat) == Decimal("0.008")


def test_an_unpriced_model_is_charged_at_the_dearest_listed_price() -> None:
    assert request_cost("gpt-unlisted", _essay_response()) == Decimal("0.008")


def test_a_response_without_usage_costs_nothing() -> None:
    assert request_cost(_SOL, SimpleNamespace(output_text="An essay.")) == 0


def test_requests_stop_once_the_day_reaches_the_ceiling() -> None:
    cap = DailySpendCap(Decimal("0.01"))
    sent: list[int] = []

    def request() -> SimpleNamespace:
        sent.append(1)
        return _essay_response()

    cap.call(_SOL, request)
    cap.call(_SOL, request)  # 0.007 is under the ceiling, so this one goes out
    with pytest.raises(SpendCapReached) as raised:
        cap.call(_SOL, request)

    assert len(sent) == 2
    assert cap.spent_today == Decimal("0.014")
    assert str(raised.value) == SPEND_CAP_MESSAGE
    assert raised.value.public


def test_a_new_day_starts_from_nothing() -> None:
    today = _Day(date(2026, 10, 23))
    cap = DailySpendCap(Decimal("0.005"), today=today)
    cap.call(_SOL, _essay_response)
    with pytest.raises(SpendCapReached):
        cap.call(_SOL, _essay_response)

    today.day = date(2026, 10, 24)
    cap.call(_SOL, _essay_response)

    assert cap.spent_today == Decimal("0.007")


def test_a_ceiling_of_zero_counts_but_never_stops() -> None:
    cap = DailySpendCap(Decimal(0))
    for _ in range(3):
        cap.call(_SOL, _essay_response)
    assert cap.spent_today == Decimal("0.021")


def test_the_days_spend_survives_a_restart(tmp_path: Path) -> None:
    path = tmp_path / "spend" / "openai-spend.json"
    today = _Day(date(2026, 10, 23))
    DailySpendCap(Decimal("0.005"), path, today=today).call(_SOL, _essay_response)

    restarted = DailySpendCap(Decimal("0.005"), path, today=today)

    assert json.loads(path.read_text(encoding="utf-8")) == {
        "day": "2026-10-23",
        "spent_usd": "0.007",
    }
    with pytest.raises(SpendCapReached):
        restarted.call(_SOL, _essay_response)
    # Yesterday's file is yesterday's spend.
    today.day = date(2026, 10, 24)
    assert DailySpendCap(Decimal("0.005"), path, today=today).spent_today == 0


def test_an_unreadable_ledger_starts_the_day_from_nothing(tmp_path: Path) -> None:
    path = tmp_path / "openai-spend.json"
    path.write_text("not json", encoding="utf-8")
    assert DailySpendCap(Decimal(1), path).spent_today == 0


def _spent_cap() -> DailySpendCap:
    cap = DailySpendCap(Decimal("0.001"))
    cap.call(_SOL, _essay_response)
    return cap


def test_a_spent_budget_sends_no_essay_and_says_why() -> None:
    client = _EssayClient()
    essay = OpenAIEssayCompleter(client, _SOL, spend=_spent_cap())
    runtime = Runtime(completer=_NewsCompleter(), facts=_ExplodingFacts(), essay=essay)

    result = explain_answer("How can AI disrupt mining?", runtime)

    assert client.calls == 0
    assert result.renderer is RendererKind.REFUSE
    assert result.message == SPEND_CAP_MESSAGE


def test_a_spent_budget_on_a_news_question_says_why() -> None:
    client = _EssayClient()
    essay = OpenAIEssayCompleter(client, _SOL, spend=_spent_cap())
    runtime = Runtime(
        completer=_NewsCompleter(), facts=_ExplodingFacts(), news=_FixtureNews(), essay=essay
    )

    result = run_turn(NVIDIA_SUPPLY_QUERY, runtime)

    assert client.calls == 0
    assert result.intent is Intent.NEWS_AND_EXPLAIN
    assert result.renderer is RendererKind.REFUSE
    assert result.message == SPEND_CAP_MESSAGE


class _ParseClient:
    def __init__(self) -> None:
        self.calls = 0
        self.chat = SimpleNamespace(completions=SimpleNamespace(parse=self.parse))

    def parse(self, **_kwargs: Any) -> object:
        self.calls += 1
        parsed = Plan(intent=Intent.LOOKUP, company="Google", metric="net_income")
        message = SimpleNamespace(parsed=parsed, refusal=None)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


class _UnsureRules:
    """A rules plan with a correction note, which the cascade sends to the model."""

    def complete(self, query: str, current_spec: object = None) -> WorkflowPlan:
        return WorkflowPlan(
            intent=Intent.LOOKUP,
            company="NVDA",
            metric="revenue",
            notes=("Showing NVIDIA for “nvidai”.",),
        )


def test_a_spent_budget_leaves_the_planner_to_the_rules_plan() -> None:
    client = _ParseClient()
    llm = OpenAIStructuredCompleter(client, "gpt-5.6-terra", spend=_spent_cap())
    with pytest.raises(PlannerError):
        llm.complete("nvidai revenue")

    cascade = CascadeCompleter(_UnsureRules(), llm, lambda _industry: False)
    plan = cascade.complete("nvidai revenue")

    assert client.calls == 0
    assert cascade.last_reason is not None
    assert isinstance(plan, WorkflowPlan)
    assert plan.company == "NVDA"
