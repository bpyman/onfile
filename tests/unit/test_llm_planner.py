"""The LLM planner can ask for everything the pipeline answers.

Each test drives a conversation on the recorded runtime with the OpenAI planner
returning a fixed plan through a fake client: what the model would answer, and
what the window then shows. No network.
"""

from __future__ import annotations

import uuid
from dataclasses import replace
from types import SimpleNamespace
from typing import Any

import pytest
from openai.lib._pydantic import to_strict_json_schema

from financial_analyst_agent.conversation import ConversationTurn, run_conversation_turn
from financial_analyst_agent.graph.analysis_spec import SUPPORTED_OPERATIONS
from financial_analyst_agent.planner import (
    _FOLLOW_UP_PROMPT,
    _SYSTEM_PROMPT,
    FollowUpPlan,
    OpenAIStructuredCompleter,
    Plan,
)
from financial_analyst_agent.runtime import recorded_runtime
from financial_analyst_agent.thread_store import EphemeralThreadStore


class _ScriptedClient:
    """Answers each planner call with the next plan, as OpenAI's parse() would."""

    def __init__(self, *plans: dict[str, Any]) -> None:
        self._plans = list(plans)
        self.chat = SimpleNamespace(completions=SimpleNamespace(parse=self._parse))

    def _parse(self, *, response_format: type[Any], **_: Any) -> Any:
        parsed = response_format.model_validate(self._plans.pop(0))
        message = SimpleNamespace(parsed=parsed, refusal=None)
        return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def _converse(*turns: tuple[str, dict[str, Any]]) -> ConversationTurn:
    client = _ScriptedClient(*(plan for _, plan in turns))
    runtime = replace(recorded_runtime(), completer=OpenAIStructuredCompleter(client, "test-model"))
    store = EphemeralThreadStore()
    thread_id = str(uuid.uuid4())
    turn = None
    for message, _ in turns:
        turn = run_conversation_turn(thread_id, message, runtime, store=store)
    assert turn is not None
    return turn


def _tickers(turn: ConversationTurn) -> list[str]:
    return list(dict.fromkeys(row.ticker for row in turn.result.table_rows if row.ticker))


def test_the_latest_10q_needs_no_accession_numbers_and_reads_both_sections() -> None:
    turn = _converse(
        (
            "What changed in Microsoft's latest 10-Q?",
            {"intent": "filing_change", "company": "Microsoft"},
        )
    )

    sections = {change.section for change in turn.result.disclosure_changes}
    assert sections == {"mda", "risk_factors"}


def test_named_accessions_and_a_section_reach_the_filing_comparison() -> None:
    turn = _converse(
        (
            "What changed in Microsoft's MD&A between 0000950170-25-061046 and "
            "0001193125-26-191507?",
            {
                "intent": "filing_change",
                "company": "Microsoft",
                "older_accession": "0000950170-25-061046",
                "newer_accession": "0001193125-26-191507",
                "section": "mda",
            },
        )
    )

    assert turn.result.disclosure_changes
    assert {change.section for change in turn.result.disclosure_changes} == {"mda"}


def test_how_a_company_is_doing_is_an_overview() -> None:
    turn = _converse(
        ("How is Nvidia doing?", {"intent": "lookup", "company": "Nvidia", "metric": "overview"})
    )

    assert turn.analysis_spec is not None
    assert len(turn.analysis_spec.metrics) > 1
    assert _tickers(turn) == ["NVDA"]


def test_a_comparison_ranked_by_its_metric_is_ordered_by_it() -> None:
    turn = _converse(
        (
            "Rank Microsoft, Apple and Nvidia by revenue",
            {
                "intent": "compare",
                "companies": ["Microsoft", "Apple", "Nvidia"],
                "metric": "revenue",
                "order_by_metric": True,
            },
        )
    )

    assert turn.analysis_spec is not None
    assert "order_by_metric" in turn.analysis_spec.operations
    assert _tickers(turn) == ["AAPL", "NVDA", "MSFT"]


def test_a_company_against_its_peers_brings_the_peers() -> None:
    turn = _converse(
        (
            "Compare Nvidia to its peers on revenue",
            {"intent": "compare", "companies": ["Nvidia"], "metric": "revenue", "peers": True},
        )
    )

    tickers = _tickers(turn)
    assert tickers[0] == "NVDA"
    assert len(tickers) > 1


def test_a_ranking_by_a_metric_is_ordered_by_it() -> None:
    turn = _converse(
        (
            "Top 5 semiconductor companies by revenue",
            {
                "intent": "rank_and_lookup",
                "industry": "semiconductors",
                "metric": "revenue",
                "limit": 5,
                "order_by_metric": True,
            },
        )
    )

    assert turn.analysis_spec is not None
    assert "order_by_metric" in turn.analysis_spec.operations
    assert _tickers(turn)[0] == "NVDA"


@pytest.mark.parametrize(("operations", "shown"), [(["year_over_year"], True), ([], False)])
def test_a_follow_up_can_ask_for_year_over_year(operations: list[str], shown: bool) -> None:
    # Wording the code does not read as year over year, so only the model's field asks.
    turn = _converse(
        (
            "Microsoft revenue over the last four quarters",
            {"intent": "lookup", "company": "Microsoft", "metric": "revenue"},
        ),
        (
            "show me the other comparison",
            {"intent": "spec_patch", "mode": "extend", "add_operations": operations},
        ),
    )

    assert any(row.comparison == "year_over_year" for row in turn.result.table_rows) is shown


def test_a_follow_up_can_sort_by_a_metric() -> None:
    turn = _converse(
        (
            "Compare Microsoft, Apple and Nvidia revenue",
            {
                "intent": "compare",
                "companies": ["Microsoft", "Apple", "Nvidia"],
                "metric": "revenue",
            },
        ),
        (
            "sort by revenue",
            {"intent": "spec_patch", "mode": "extend", "add_operations": ["order_by_metric"]},
        ),
    )

    assert _tickers(turn) == ["AAPL", "NVDA", "MSFT"]


def test_a_follow_up_names_only_operations_the_spec_supports() -> None:
    with pytest.raises(ValueError):
        FollowUpPlan.model_validate(
            {"intent": "spec_patch", "mode": "extend", "add_operations": ["forecast"]}
        )


@pytest.mark.parametrize("schema", [Plan, FollowUpPlan])
def test_the_schemas_are_accepted_by_strict_structured_outputs(schema: type[Any]) -> None:
    to_strict_json_schema(schema)


def test_the_prompts_name_every_supported_operation_and_the_latest_filing() -> None:
    for operation in SUPPORTED_OPERATIONS:
        assert operation in _FOLLOW_UP_PROMPT
    assert "latest" in _SYSTEM_PROMPT
    assert "overview" in _SYSTEM_PROMPT


def test_the_follow_up_operations_are_the_spec_operations() -> None:
    from typing import get_args

    from financial_analyst_agent.planner import Operation

    assert set(get_args(Operation)) == SUPPORTED_OPERATIONS


def test_the_first_turn_prompt_names_the_overview_plan_value_code_reads() -> None:
    from financial_analyst_agent.request_wording import OVERVIEW_PLAN

    assert f"Use {OVERVIEW_PLAN} when" in _SYSTEM_PROMPT
