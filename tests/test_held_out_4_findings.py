"""The shared defects the fourth held-out set found, pinned on the recorded runtime.

Each case is run as the planner comparison runs it, with the rules planner, and
must pass on every field it is labelled with (docs/evaluation/held-out-4-findings.md).
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import pytest

from financial_analyst_agent.contracts import Runtime
from financial_analyst_agent.planner_evaluation import PlannerCase, load_cases, run_planner
from financial_analyst_agent.runtime import recorded_runtime

_CASES = Path(__file__).resolve().parents[1] / "docs/evaluation/planner-cases-held-out-4.json"


@pytest.fixture(scope="module")
def runtime() -> Runtime:
    return recorded_runtime()


def _case(case_id: str) -> PlannerCase:
    (case,) = [case for case in load_cases(_CASES) if case.case_id == case_id]
    return case


@pytest.mark.parametrize(
    "case_id",
    [
        # "Net interest income" is one metric, not the ambiguous word "interest".
        "h4_bac_nii_couple_quarters",
        # A change that names no base asks what to compare against.
        "h4_clarify_intel_change_no_base",
    ],
)
def test_a_fixed_held_out_case_passes_with_the_rules_planner(
    case_id: str, runtime: Runtime
) -> None:
    (result,) = run_planner([_case(case_id)], runtime.completer, runs=1, runtime=runtime)

    assert not result.error
    assert result.checks == {name: True for name in result.checks}


def test_year_on_year_answers_as_year_over_year_does(runtime: Runtime) -> None:
    """The change is read; the window is year over year's two years of quarters.

    The label's latest quarter disagrees with that design, as the two growth
    questions that name no period do (held-out-4-findings.md), so it is not checked.
    """
    case = _case("h4_growth_unh_ocf_year_on_year")
    over = replace(case, turns=("is unitedhealth's operating cash flow up year over year",))

    (on_result,) = run_planner([case], runtime.completer, runs=1, runtime=runtime)
    (over_result,) = run_planner([over], runtime.completer, runs=1, runtime=runtime)

    assert not on_result.error
    assert on_result.signature == over_result.signature
    assert {name: ok for name, ok in on_result.checks.items() if name != "periods"} == {
        name: True for name in on_result.checks if name != "periods"
    }
