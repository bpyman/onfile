"""Contracts must load without pulling in workflow implementations."""

from __future__ import annotations

import sys


def test_contracts_import_without_loading_turn_workflows() -> None:
    dependents = (
        "financial_analyst_agent.turn",
        "financial_analyst_agent.conversation",
        "financial_analyst_agent.guide",
        "financial_analyst_agent.thread_store",
        "financial_analyst_agent.evidence_store",
        "financial_analyst_agent.contracts",
        "financial_analyst_agent.graph",
        "financial_analyst_agent.planner",
    )

    def loaded() -> list[str]:
        return [
            name
            for name in sys.modules
            if name in dependents or any(name.startswith(f"{dep}.") for dep in dependents)
        ]

    # Put the original modules back afterwards: later tests hold their classes,
    # and a second copy of Intent would never compare equal to the first.
    removed = {name: sys.modules.pop(name) for name in loaded()}
    try:
        import financial_analyst_agent.contracts as contracts

        assert "financial_analyst_agent.turn" not in sys.modules
        assert contracts.Intent.LOOKUP == "lookup"
        assert contracts.RendererKind.TABLE == "table"
        assert "revenue" in contracts.ALLOWED_METRICS
        assert contracts.Runtime is not None
        assert contracts.TurnResult is not None
        assert contracts.NewsHit is not None
        assert contracts.FactsPort is not None
    finally:
        for name in loaded():
            del sys.modules[name]
        sys.modules.update(removed)


def test_turn_exports_its_workflows_and_contracts_owns_the_types() -> None:
    # Contract types are imported from contracts; turn exports only its own functions.
    from financial_analyst_agent import turn

    assert set(turn.__all__) == {
        "compare_metrics",
        "compare_task",
        "current_events_answer",
        "explain_answer",
        "exploratory_research_answer",
        "lookup_task",
        "market_formula_rows",
        "metric_rows",
        "rank_and_lookup_task",
        "rank_task",
        "run_turn",
        "snapshot_compare_rows",
    }
    assert callable(turn.run_turn)
    assert callable(turn.compare_metrics)
    assert callable(turn.snapshot_compare_rows)
