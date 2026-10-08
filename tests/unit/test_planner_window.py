"""A model planner's window: used only where the wording asks about time but names no count."""

from __future__ import annotations

import pytest

from financial_analyst_agent.contracts import Intent, WorkflowPlan
from financial_analyst_agent.graph.analysis_spec import PeriodSelection, SpecPatch
from financial_analyst_agent.graph.spec_turn import plan_to_spec_patch
from financial_analyst_agent.period_selection import read
from financial_analyst_agent.planner import Plan
from financial_analyst_agent.request_wording import bind_periods_from_message


def _lookup(recent_quarters: int | None) -> WorkflowPlan:
    return Plan.model_validate(
        {
            "action": {
                "intent": Intent.LOOKUP,
                "company": "Nvidia",
                "metric": "net_income",
                "recent_quarters": recent_quarters,
            }
        }
    ).workflow_plan()


def _window(count: int) -> PeriodSelection:
    return PeriodSelection(kind="last_n_quarters", count=count)


def _proposed(message: str, recent_quarters: int | None) -> SpecPatch:
    plan = _lookup(recent_quarters)
    return read(message).propose(plan_to_spec_patch(plan), model_quarters=plan.recent_quarters)


def test_a_plans_window_becomes_the_patchs_window_beside_a_period_word() -> None:
    message = "How has Nvidia's net income trended lately?"

    assert _proposed(message, 6).set_periods == _window(6)
    assert _proposed(message, None).set_periods is None
    assert plan_to_spec_patch(_lookup(6)).set_periods is None


def test_a_plans_window_is_capped() -> None:
    assert _proposed("Nvidia net income history", 100).set_periods == _window(40)


def test_a_rank_proposes_no_window() -> None:
    message = "top 3 chipmakers by revenue over time"
    patch = SpecPatch(mode="replace", add_metrics=("revenue",))

    assert read(message).propose(patch, model_quarters=None).set_periods is None


def test_the_wordings_window_overrules_the_models() -> None:
    message = "Nvidia net income over the past six quarters"
    patch = _proposed(message, 4)

    assert bind_periods_from_message(patch, message).set_periods == _window(6)


@pytest.mark.parametrize(
    "message",
    [
        "Nvidia net income over the last handful of quarters",
        "How has Nvidia's net income trended lately?",
    ],
)
def test_the_models_window_stands_where_the_words_ask_about_time(message: str) -> None:
    patch = _proposed(message, 5)

    assert bind_periods_from_message(patch, message).set_periods == _window(5)


def test_a_window_the_words_never_asked_for_is_dropped() -> None:
    patch = _proposed("What was Nvidia's net income?", 4)

    assert patch.set_periods is None


def test_a_follow_up_patch_is_held_to_the_same_rule() -> None:
    proposed = SpecPatch(mode="extend", add_companies=("AMD",), set_periods=_window(4))

    assert read("what about AMD?").propose(proposed).set_periods is None


def test_proposing_never_binds_the_words() -> None:
    # The held patch keeps the planner's count; the window the words name is
    # bound when the request is resolved, so a clarification's reply can rebind.
    message = "Apple revenue last 6 quarters"
    patch = _proposed(message, 4)

    assert patch.set_periods == _window(4)
