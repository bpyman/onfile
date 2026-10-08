"""A WorkflowPlan knows which company it names, if any."""

from __future__ import annotations

from financial_analyst_agent.contracts import Intent, WorkflowPlan


def test_a_plan_names_its_company_or_none_for_unknown_and_empty() -> None:
    assert WorkflowPlan(intent=Intent.LOOKUP, company="Apple").named_company == "Apple"
    # A planner that read no company writes "unknown"; an MCP call may leave it empty.
    assert WorkflowPlan(intent=Intent.LOOKUP, company="unknown").named_company is None
    assert WorkflowPlan(intent=Intent.LOOKUP, company="").named_company is None
    assert WorkflowPlan(intent=Intent.LOOKUP).named_company is None
