"""The planner comparison: its cases, scoring, metering and budget, without calling OpenAI."""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from typing import Any

import pytest

from financial_analyst_agent.conversation import run_conversation_turn
from financial_analyst_agent.planner import OpenAIStructuredCompleter, Plan
from financial_analyst_agent.planner_evaluation import (
    BudgetExceeded,
    CaseRun,
    MeteredCompleter,
    MeteredOpenAIClient,
    Observation,
    PlannerCase,
    Prices,
    Usage,
    estimate,
    load_cases,
    observe,
    run_planner,
    score,
    summarize,
)
from financial_analyst_agent.runtime import recorded_runtime
from financial_analyst_agent.thread_store import EphemeralThreadStore


def _seen(**overrides: Any) -> Observation:
    fields: dict[str, Any] = {
        "outcome": "answer",
        "intent": "lookup",
        "tickers": frozenset({"MSFT"}),
        "metrics": frozenset({"revenue"}),
        "periods": ("last_n_quarters", 4),
        "operations": frozenset({"across_periods"}),
    }
    fields.update(overrides)
    return Observation(**fields)


def _ask(*messages: str) -> Observation:
    runtime = recorded_runtime()
    store = EphemeralThreadStore()
    thread_id = str(uuid.uuid4())
    turn = None
    for message in messages:
        turn = run_conversation_turn(thread_id, message, runtime, store=store)
    assert turn is not None
    return observe(turn)


def test_the_committed_cases_load_with_unique_ids_and_known_fields() -> None:
    cases = load_cases()

    assert sum(case.split == "scorecard" for case in cases) == 28
    assert sum(case.split == "dev" for case in cases) == 50 + 72 + 69
    assert sum(case.split == "held_out" for case in cases) == 66
    assert all(case.turns and case.expect for case in cases)


def test_a_case_passes_only_on_the_fields_it_labels() -> None:
    seen = _seen()

    assert score({"tickers": ["MSFT"], "metrics": ["revenue"]}, seen) == {
        "tickers": True,
        "metrics": True,
    }
    assert score({"tickers": ["MSFT", "AAPL"]}, seen) == {"tickers": False}
    assert score({"tickers_include": ["MSFT"]}, _seen(tickers=frozenset({"MSFT", "AAPL"}))) == {
        "tickers_include": True
    }
    assert score({"periods": {"kind": "last_n_quarters", "count": 8}}, seen) == {"periods": False}
    assert score({"periods": {"kind": "last_n_quarters"}}, seen) == {"periods": True}
    assert score({"operations_include": ["year_over_year"]}, seen) == {"operations_include": False}


def test_missing_recorded_data_still_counts_as_a_planned_answer() -> None:
    # The plan was right; the recorded filings lack the fact.
    assert score({"outcome": "answer"}, _seen(outcome="no_data")) == {"outcome": True}
    assert score({"outcome": "refuse"}, _seen(outcome="no_data")) == {"outcome": False}


def test_a_turn_that_raised_fails_every_labelled_field() -> None:
    assert score({"outcome": "answer", "intent": "lookup"}, None) == {
        "outcome": False,
        "intent": False,
    }


def test_observing_a_recorded_turn_reads_its_window_and_growth() -> None:
    window = _ask("Microsoft revenue over the last four quarters")
    assert window.outcome == "answer"
    assert window.tickers == {"MSFT"}
    assert window.metrics == {"revenue"}
    assert window.periods == ("last_n_quarters", 4)

    growth = _ask("Compare Nvidia and AMD revenue growth")
    assert "year_over_year" in growth.operations


def test_a_fact_missing_from_the_recorded_filings_is_no_data() -> None:
    assert _ask("what did Goldman Sachs spend on R&D in its latest quarter").outcome == "no_data"
    # A window of quarters the filings lack says why too, not only a single quarter.
    assert _ask("Goldman Sachs R&D over the last three quarters").outcome == "no_data"


class _FakeCompletions:
    """Returns one plan per call and reports token usage, as the OpenAI SDK does."""

    def __init__(self, plan: Plan) -> None:
        self.plan = plan
        self.calls = 0

    def parse(self, **_: Any) -> Any:
        self.calls += 1
        message = SimpleNamespace(parsed=self.plan, refusal=None)
        usage = SimpleNamespace(
            prompt_tokens=900,
            completion_tokens=50,
            completion_tokens_details=SimpleNamespace(reasoning_tokens=20),
        )
        return SimpleNamespace(choices=[SimpleNamespace(message=message)], usage=usage)


def _llm_planner(plan: Plan, usage: Usage) -> tuple[Any, _FakeCompletions]:
    completions = _FakeCompletions(plan)
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    planner = OpenAIStructuredCompleter(MeteredOpenAIClient(client, usage), "test-model")
    return MeteredCompleter(planner, usage), completions


_MSFT_PRETAX = PlannerCase(
    case_id="lookup_msft_pretax",
    split="scorecard",
    category="lookup",
    turns=("Microsoft pre-tax income",),
    expect={
        "outcome": "answer",
        "intent": "lookup",
        "tickers": ["MSFT"],
        "metrics": ["pretax_income"],
    },
)


def test_the_llm_path_runs_end_to_end_and_counts_its_tokens() -> None:
    usage = Usage()
    plan = Plan.model_validate(
        {"intent": "lookup", "company": "Microsoft", "metric": "pretax_income"}
    )
    completer, completions = _llm_planner(plan, usage)

    (result,) = run_planner([_MSFT_PRETAX], completer, runs=1)

    assert result.passed, result
    assert completions.calls == usage.calls == 1
    assert (usage.input_tokens, usage.output_tokens, usage.reasoning_tokens) == (900, 50, 20)
    summary = summarize([_MSFT_PRETAX], [result], usage, Prices(input=2.0, output=8.0))
    assert summary["cost_usd"] == pytest.approx((900 * 2.0 + 50 * 8.0) / 1_000_000)


def test_a_spent_budget_stops_the_run() -> None:
    usage = Usage()

    def spent() -> None:
        raise BudgetExceeded("spent")

    completer = MeteredCompleter(recorded_runtime().completer, usage, before_call=spent)

    results = run_planner([_MSFT_PRETAX, _MSFT_PRETAX], completer, runs=2)

    assert [result.error for result in results] == ["budget reached"]
    summary = summarize([_MSFT_PRETAX], results, usage, None)
    assert summary["splits"] == {} and summary["stopped_in_run"] == 0


def test_a_run_cut_short_by_the_budget_is_left_out_and_said_so() -> None:
    usage = Usage()
    calls = 0

    def spend() -> None:
        nonlocal calls
        calls += 1
        if calls > 1:
            raise BudgetExceeded("spent")

    completer = MeteredCompleter(recorded_runtime().completer, usage, before_call=spend)

    # One planner call a run: the first run completes, the second stops at once.
    results = run_planner([_MSFT_PRETAX], completer, runs=2)
    summary = summarize([_MSFT_PRETAX], results, usage, None)

    # Run 1 completed; run 2 stopped on its first case and is not averaged in.
    assert summary["runs"] == 1
    assert summary["stopped_in_run"] == 1
    assert summary["splits"]["all"]["accuracy_by_run"] == [1.0]
    assert all(failure["error"] != "budget reached" for failure in summary["failures"])


def test_agreement_counts_cases_whose_runs_all_saw_the_same() -> None:
    cases = [
        _MSFT_PRETAX,
        PlannerCase("other", "held_out", "lookup", ("q",), {"outcome": "answer"}),
    ]
    same = _seen().signature()
    results = [
        CaseRun("lookup_msft_pretax", 0, {"outcome": True}, same, 1.0),
        CaseRun("lookup_msft_pretax", 1, {"outcome": True}, same, 1.0),
        CaseRun("other", 0, {"outcome": True}, same, 1.0),
        CaseRun("other", 1, {"outcome": False}, _seen(outcome="refuse").signature(), 1.0),
    ]

    summary = summarize(cases, results, Usage(), None)

    assert summary["splits"]["all"]["agreement"] == 0.5
    assert summary["splits"]["all"]["accuracy_by_run"] == [1.0, 0.5]
    assert summary["cost_usd"] is None


def test_an_estimate_counts_every_turn_and_prices_only_when_asked() -> None:
    cases = load_cases()
    turns = sum(len(case.turns) for case in cases)

    unpriced = estimate(cases, 3, None)
    priced = estimate(cases, 3, Prices(input=1.0, output=1.0))

    assert unpriced["planner_calls"] == priced["planner_calls"] == turns * 3
    assert unpriced["cost_usd"] is None
    assert priced["cost_usd"] == pytest.approx(
        (priced["input_tokens"] + priced["output_tokens"]) / 1_000_000
    )
