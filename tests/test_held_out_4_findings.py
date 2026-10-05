"""The shared defects the fourth held-out set found, pinned on the recorded runtime.

Each case is run as the planner comparison runs it, with the rules planner, and
must pass on every field it is labelled with (docs/evaluation/held-out-4-findings.md).
"""

from __future__ import annotations

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
    ],
)
def test_a_fixed_held_out_case_passes_with_the_rules_planner(
    case_id: str, runtime: Runtime
) -> None:
    (result,) = run_planner([_case(case_id)], runtime.completer, runs=1, runtime=runtime)

    assert not result.error
    assert result.checks == {name: True for name in result.checks}
