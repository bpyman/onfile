"""The cascade keeps the rules plan unless the rules planner shows it was unsure."""

from typing import Any

import pytest

from financial_analyst_agent.contracts import Intent, WorkflowPlan
from financial_analyst_agent.domain.errors import PlannerError
from financial_analyst_agent.graph.analysis_spec import AnalysisSpec, SpecPatch
from financial_analyst_agent.planner_cascade import CascadeCompleter, unsure_reason
from financial_analyst_agent.planner_evaluation import (
    CaseRun,
    PlannerCase,
    mcnemar_p,
    paired,
    wilson_interval,
)


def _knows(industry: str) -> bool:
    return industry in ("Technology", "banks")


@pytest.mark.parametrize(
    ("plan", "follow_up", "reason"),
    [
        (WorkflowPlan(intent=Intent.LOOKUP, company="MSFT", metric="revenue"), False, None),
        (WorkflowPlan(intent=Intent.LOOKUP, company="NVDA", metric="overview"), False, None),
        (
            WorkflowPlan(intent=Intent.RANK_AND_LOOKUP, industry="Technology", metric="revenue"),
            False,
            None,
        ),
        (WorkflowPlan(intent=Intent.EXPLAIN, topic="AI in banking"), False, None),
        (
            WorkflowPlan(
                intent=Intent.COMPARE,
                companies=("NVDA", "AMD", "Apple"),
                metric="revenue",
                notes=("Showing Apple for “apples”.",),
            ),
            False,
            "notes",
        ),
        (WorkflowPlan(intent=Intent.LOOKUP, company="MSFT", metric="churn"), False, "metric"),
        (WorkflowPlan(intent=Intent.LOOKUP, company="MSFT", metric="unknown"), False, "metric"),
        (WorkflowPlan(intent=Intent.LOOKUP, metric="revenue"), False, "company"),
        (
            WorkflowPlan(intent=Intent.RANK_AND_LOOKUP, industry="10", metric="revenue"),
            False,
            "industry",
        ),
        (WorkflowPlan(intent=Intent.RANK, industry="market cap"), False, "industry"),
        # "make it the last eight quarters": the shared reading of the words edits the spec.
        (WorkflowPlan(intent=Intent.LOOKUP, metric="unknown"), True, None),
        (SpecPatch(mode="extend", add_companies=("AAPL",)), True, None),
        (SpecPatch(add_companies=("AAPL",)), True, "edit"),
        (SpecPatch(set_periods=None, add_operations=("year_over_year",)), True, None),
    ],
)
def test_unsure_reason(plan: WorkflowPlan | SpecPatch, follow_up: bool, reason: str | None) -> None:
    assert unsure_reason(plan, _knows, follow_up=follow_up) == reason


class _Planner:
    def __init__(self, plan: WorkflowPlan | SpecPatch | None = None) -> None:
        self.plan = plan
        self.asked: list[tuple[str, Any]] = []
        self.index = "rules index"

    def complete(self, query: str, current_spec: Any = None) -> WorkflowPlan | SpecPatch:
        self.asked.append((query, current_spec))
        if self.plan is None:
            raise PlannerError("The planner could not read that question.")
        return self.plan


def test_a_sure_rules_plan_never_reaches_the_llm() -> None:
    sure = WorkflowPlan(intent=Intent.LOOKUP, company="MSFT", metric="revenue")
    llm = _Planner(WorkflowPlan(intent=Intent.LOOKUP, company="AAPL", metric="revenue"))
    cascade = CascadeCompleter(_Planner(sure), llm, _knows)

    assert cascade.complete("Microsoft revenue") == sure
    assert cascade.last_reason is None
    assert llm.asked == []


def test_an_unsure_rules_plan_is_planned_by_the_llm_with_the_same_spec() -> None:
    unsure = WorkflowPlan(intent=Intent.LOOKUP, company="MSFT", metric="profit")
    planned = WorkflowPlan(intent=Intent.LOOKUP, company="MSFT", metric="net_income")
    llm = _Planner(planned)
    spec = AnalysisSpec(metrics=("revenue",))
    cascade = CascadeCompleter(_Planner(unsure), llm, _knows)

    assert cascade.complete("Microsoft profit", current_spec=spec) == planned
    assert cascade.last_reason == "metric"
    assert llm.asked == [("Microsoft profit", spec)]


def test_when_the_llm_fails_the_rules_plan_stands() -> None:
    unsure = WorkflowPlan(intent=Intent.LOOKUP, company="MSFT", metric="profit")
    cascade = CascadeCompleter(_Planner(unsure), _Planner(None), _knows)

    assert cascade.complete("Microsoft profit") == unsure


def test_the_cascade_lends_the_rules_planners_index() -> None:
    cascade = CascadeCompleter(_Planner(), _Planner(), _knows)

    assert cascade.index == "rules index"


def test_mcnemar_p_is_the_exact_two_sided_binomial() -> None:
    assert mcnemar_p(0, 0) == 1.0
    assert mcnemar_p(5, 0) == pytest.approx(2 / 32)
    # 10 against 2: 2 * (C(12,0) + C(12,1) + C(12,2)) / 2^12.
    assert mcnemar_p(10, 2) == pytest.approx(2 * 79 / 4096)
    assert mcnemar_p(3, 3) == 1.0


def test_wilson_interval_stays_inside_zero_and_one() -> None:
    low, high = wilson_interval(66, 66)
    assert high == 1.0 and 0.94 < low < 0.95
    low, high = wilson_interval(60, 66)
    assert 0.81 < low < 0.82 and 0.95 < high < 0.96


def _run(case_id: str, run: int, passed: bool) -> CaseRun:
    return CaseRun(case_id, run, {"outcome": passed}, None, 0.0)


def test_paired_counts_each_case_once_by_its_majority_of_runs() -> None:
    cases = [
        PlannerCase(f"c{i}", "held_out", "periods", ("q",), {"outcome": "answer"}) for i in range(4)
    ]
    first = [_run(f"c{i}", run, i != 3) for i in range(4) for run in range(3)]
    # c0 passes 2 of 3 runs, so it counts as passed; c1 and c2 fail.
    second = [
        _run(f"c{i}", run, (i == 0 and run < 2) or i == 3) for i in range(4) for run in range(3)
    ]

    held_out = paired(cases, first, second)["held_out"]

    assert (held_out["both"], held_out["only_first"], held_out["only_second"]) == (1, 2, 1)
    assert held_out["neither"] == 0
    assert held_out["p_value"] == pytest.approx(mcnemar_p(2, 1))


def test_a_plan_the_model_writes_invalid_falls_back_to_the_rules_plan() -> None:
    from types import SimpleNamespace

    import pydantic

    from financial_analyst_agent.planner import OpenAIStructuredCompleter, Plan

    try:
        # A comparison of one company: the plan's own rules refuse it.
        Plan.model_validate({"intent": "compare", "companies": ["Apple"], "metric": "revenue"})
    except pydantic.ValidationError as exc:
        invalid = exc

    def parse(**_kwargs: Any) -> Any:
        raise invalid

    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(parse=parse)))
    llm = OpenAIStructuredCompleter(client, "gpt-test")
    with pytest.raises(PlannerError):
        llm.complete("compare apple")

    unsure = WorkflowPlan(intent=Intent.COMPARE, companies=("Apple",), metric="profit")
    assert CascadeCompleter(_Planner(unsure), llm, _knows).complete("compare apple") == unsure
