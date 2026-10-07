"""The shared defects the fifth held-out set found, pinned on the recorded runtime.

Each case is run as the planner comparison runs it and must pass on every field
it is labelled with (docs/evaluation/held-out-5-findings.md): with the rules
planner, and with a stand-in for the LLM planner proposing what the run's
observation shows it proposed, so no test calls OpenAI.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Any

import pytest

from financial_analyst_agent.contracts import Intent, Runtime, WorkflowPlan
from financial_analyst_agent.conversation import run_conversation_turn
from financial_analyst_agent.planner_evaluation import PlannerCase, load_cases, run_planner
from financial_analyst_agent.runtime import recorded_runtime
from financial_analyst_agent.thread_store import EphemeralThreadStore

_CASES = Path(__file__).resolve().parents[1] / "docs/evaluation/planner-cases-held-out-5.json"


@pytest.fixture(scope="module")
def runtime() -> Runtime:
    return recorded_runtime()


def _case(case_id: str) -> PlannerCase:
    (case,) = [case for case in load_cases(_CASES) if case.case_id == case_id]
    return case


class _ProposedPlan:
    """The LLM planner's place: one plan, whatever the question."""

    def __init__(self, plan: WorkflowPlan) -> None:
        self.plan = plan

    def complete(self, query: str, current_spec: Any = None) -> WorkflowPlan:
        return self.plan


# What the LLM planner proposed on the run of 7 October 2026, read from the
# comparison's observation: Goldman's net interest income over five quarters.
_LLM_PLANS = {
    "h5_gr_gs_both": WorkflowPlan(
        intent=Intent.LOOKUP, company="Goldman", metric="net_interest_income", recent_quarters=5
    ),
}


@pytest.mark.parametrize(
    "case_id",
    [
        # Naming both bases shows both changes, with the bases leading the question.
        "h5_gr_gs_both",
    ],
)
def test_a_fixed_held_out_case_passes_with_the_rules_planner(
    case_id: str, runtime: Runtime
) -> None:
    (result,) = run_planner([_case(case_id)], runtime.completer, runs=1, runtime=runtime)

    assert not result.error
    assert result.checks == {name: True for name in result.checks}


@pytest.mark.parametrize("case_id", sorted(_LLM_PLANS))
def test_a_fixed_held_out_case_passes_with_what_the_llm_planner_proposed(
    case_id: str, runtime: Runtime
) -> None:
    planner = _ProposedPlan(_LLM_PLANS[case_id])

    (result,) = run_planner([_case(case_id)], planner, runs=1, runtime=runtime)

    assert not result.error
    assert result.checks == {name: True for name in result.checks}


@pytest.mark.parametrize(
    "question",
    [
        "Sequentially or versus last year, Goldman net interest income",
        "Goldman net interest income, sequentially or versus last year",
    ],
)
def test_naming_both_bases_shows_both_changes_on_every_quarter(
    question: str, runtime: Runtime
) -> None:
    """Each quarter shown has its year-over-year change from its own comparative
    (ADR 0009) and, but for the oldest, its change on the quarter before: not
    only where the year-earlier quarter happens to be on screen. The recording
    holds four Goldman quarters, so none is."""
    turn = run_conversation_turn(
        f"held-out-5-{uuid.uuid4()}", question, runtime, store=EphemeralThreadStore()
    )

    rows = turn.result.table_rows
    levels = sorted(row.end_date for row in rows if row.comparison is None and row.value)
    year_over_year = sorted(row.end_date for row in rows if row.comparison == "year_over_year")
    sequential = sorted(row.end_date for row in rows if row.comparison == "sequential")
    assert len(levels) == 4
    assert year_over_year == levels
    assert sequential == levels[1:]


def test_naming_both_bases_as_a_follow_up_keeps_the_quarters_on_screen(runtime: Runtime) -> None:
    """After six quarters, "sequentially or versus last year" shows those six,
    each with both changes; the oldest's sequential base is read, not shown."""
    thread = f"held-out-5-{uuid.uuid4()}"
    store = EphemeralThreadStore()
    run_conversation_turn(thread, "Apple revenue over the last 6 quarters", runtime, store=store)
    turn = run_conversation_turn(thread, "sequentially or versus last year", runtime, store=store)

    rows = turn.result.table_rows
    levels = sorted(row.end_date for row in rows if row.comparison is None and row.value)
    year_over_year = sorted(row.end_date for row in rows if row.comparison == "year_over_year")
    sequential = sorted(row.end_date for row in rows if row.comparison == "sequential")
    assert len(levels) == 6
    assert year_over_year == levels
    assert sequential == levels
