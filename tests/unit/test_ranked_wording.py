"""A ranking's group is read by one grammar, whichever planner proposed the ranking (ADR 0010)."""

from __future__ import annotations

from pathlib import Path

import pytest

import financial_analyst_agent.graph as graph_package
from financial_analyst_agent.contracts import Intent
from financial_analyst_agent.ranked_wording import prepared, ranked_group, ranking_group
from financial_analyst_agent.rules_planner import DemoCompleter, recorded_issuer_index
from financial_analyst_agent.universe import WHOLE_MARKET


def test_a_question_is_prepared_once_with_counts_as_digits_and_odd_counts_said() -> None:
    assert prepared("Top five banks by revenue") == ("Top 5 banks by revenue", [])
    assert prepared("top 0 banks") == (
        "top 10 banks",
        ["A ranking lists at least one company, so this shows the top 10."],
    )


@pytest.mark.parametrize(
    ("question", "group"),
    [
        ("Top five banks", "banks"),
        ("Over the past year, the top 3 drugmakers by gross margin", "drugmakers"),
        ("Which tech company has the highest net margin?", "tech"),
        ("chipmakers by free cash flow", "chipmakers"),
        ("top 10 companies in AI", "ai"),
        ("which companies are worth the most?", WHOLE_MARKET),
    ],
)
def test_the_group_a_rankings_words_name(question: str, group: str) -> None:
    assert ranked_group(question) == group


def test_the_group_the_graph_checks_is_the_group_the_rules_planner_plans() -> None:
    completer = DemoCompleter(recorded_issuer_index())
    for question in (
        "Over the past year, the top 3 drugmakers by gross margin",
        "Which tech company has the highest net margin?",
        "chipmakers by free cash flow",
        "top 10 companies in AI",
    ):
        plan = completer.complete(question)
        assert plan.intent in (Intent.RANK, Intent.RANK_AND_LOOKUP), question
        assert plan.industry == ranked_group(question), question


def test_a_ranking_with_no_company_named_is_of_the_group_its_words_name() -> None:
    # Prepared and lower-cased already, with any leading clause set aside.
    assert ranking_group("which bank has the most deposits") == "banks"
    assert ranking_group("top 5 semiconductor companies by revenue") == "semiconductor"
    assert ranking_group("the 3 largest ev makers") == "automakers"


def test_the_analysis_graph_reads_a_rankings_group_without_the_rules_planner() -> None:
    graph = Path(graph_package.__file__).parent
    importing = [
        path.name
        for path in graph.glob("*.py")
        if "rules_planner" in path.read_text(encoding="utf-8")
    ]
    assert importing == []
