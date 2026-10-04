"""A model planner's window: used only where the wording asks about time but names no count."""

from __future__ import annotations

import pytest

from financial_analyst_agent.contracts import Intent, WorkflowPlan
from financial_analyst_agent.graph.analysis_spec import PeriodSelection, SpecPatch
from financial_analyst_agent.graph.spec_turn import plan_to_spec_patch
from financial_analyst_agent.planner import Plan
from financial_analyst_agent.request_wording import bind_periods_from_message, planner_window


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


def test_a_plans_window_becomes_the_patchs_window() -> None:
    assert plan_to_spec_patch(_lookup(6)).set_periods == _window(6)
    assert plan_to_spec_patch(_lookup(None)).set_periods is None


def test_the_wordings_window_overrules_the_models() -> None:
    message = "Nvidia net income over the past six quarters"
    patch = planner_window(plan_to_spec_patch(_lookup(4)), message)

    assert bind_periods_from_message(patch, message).set_periods == _window(6)


@pytest.mark.parametrize(
    "message",
    [
        "Nvidia net income over the last handful of quarters",
        "How has Nvidia's net income trended lately?",
    ],
)
def test_the_models_window_stands_where_the_words_ask_about_time(message: str) -> None:
    patch = planner_window(plan_to_spec_patch(_lookup(5)), message)

    assert bind_periods_from_message(patch, message).set_periods == _window(5)


def test_a_window_the_words_never_asked_for_is_dropped() -> None:
    patch = planner_window(plan_to_spec_patch(_lookup(4)), "What was Nvidia's net income?")

    assert patch.set_periods is None


def test_a_follow_up_patch_is_held_to_the_same_rule() -> None:
    proposed = SpecPatch(mode="extend", add_companies=("AMD",), set_periods=_window(4))

    assert planner_window(proposed, "what about AMD?").set_periods is None
