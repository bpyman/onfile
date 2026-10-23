"""The note naming what an answer does not act on, whichever planner read the question."""

from dataclasses import replace

from conversation_replay import ask
from financial_analyst_agent.answer_notes import unapplied_notes
from financial_analyst_agent.contracts import Intent, WorkflowPlan
from financial_analyst_agent.graph.analysis_spec import AnalysisSpec, RankedSet, ResolvedCompany
from financial_analyst_agent.runtime import recorded_runtime

_YUM_CHINA = ResolvedCompany(
    cik="1673358", name="Yum China Holdings, Inc.", ticker="YUMC", query="Yum China"
)
_APPLE = ResolvedCompany(cik="320193", name="Apple Inc.", ticker="AAPL", query="Apple")


def test_a_place_in_a_company_name_is_not_a_region() -> None:
    spec = AnalysisSpec(companies=(_YUM_CHINA,), metrics=("revenue",))
    assert unapplied_notes("Yum China revenue", spec) == []
    assert unapplied_notes("Yum China revenue in Japan", spec) == [
        "Filings' structured data reports company-wide totals, not regions such as "
        "“Japan”, so this shows the company-wide figure."
    ]


def test_a_place_that_is_only_a_word_of_the_name_is_still_a_place() -> None:
    ibm = ResolvedCompany(
        cik="51143", name="International Business Machines Corporation", ticker="IBM", query="IBM"
    )
    spec = AnalysisSpec(companies=(ibm,), metrics=("revenue",))
    assert unapplied_notes("IBM international revenue", spec) == [
        "Filings' structured data reports company-wide totals, not regions such as "
        "“international”, so this shows the company-wide figure."
    ]
    assert unapplied_notes("International Business Machines revenue", spec) == []


def test_a_condition_on_named_companies_is_left_to_the_analyst() -> None:
    # "Did Apple grow more than 5%?" is answered by the growth itself; only a
    # ranking would have to screen.
    spec = AnalysisSpec(companies=(_APPLE,), metrics=("revenue",), operations=("year_over_year",))
    assert unapplied_notes("Did Apple's revenue grow more than 5%?", spec) == []


def test_a_plain_ranking_names_its_conditions_and_nothing_about_metrics() -> None:
    # Market cap alone: no measure was left out, no figure divided, no why to answer.
    spec = AnalysisSpec(constituents=RankedSet(industry="Technology", limit=5))
    assert unapplied_notes("why are the top 5 profitable tech companies in China?", spec) == [
        "I can't screen companies by a condition yet, so “profitable” and “China” are not "
        "applied: the list is the largest companies by market cap."
    ]


class _ModelPlanner:
    """What the LLM planner proposed for a screen: the plan has no place for its conditions."""

    def complete(self, query: str, current_spec: object = None) -> WorkflowPlan:
        return WorkflowPlan(
            intent=Intent.RANK_AND_LOOKUP, industry="Technology", limit=10, metric="revenue"
        )


def test_a_model_planned_screen_names_its_conditions_too() -> None:
    runtime = replace(recorded_runtime(), completer=_ModelPlanner())
    (answer,) = ask(
        runtime, "Which tech companies grew revenue more than 20% while staying profitable?"
    )
    assert answer.table is not None
    assert answer.banners[0] == (
        "I can't screen companies by a condition yet, so “more than 20%” and “profitable” "
        "are not applied: the list is the largest companies by market cap."
    )
