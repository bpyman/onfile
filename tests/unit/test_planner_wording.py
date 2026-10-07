"""Wording the planners misread on the development cases: rankings, swaps and filings."""

from __future__ import annotations

import pytest

from financial_analyst_agent.contracts import Intent
from financial_analyst_agent.graph.analysis_spec import (
    NamedPeriodSpec,
    PeriodSelection,
    SpecPatch,
    apply_patch,
    resolve_spec,
)
from financial_analyst_agent.ranking import SnapshotRanking
from financial_analyst_agent.request_wording import (
    bind_metrics_from_message,
    bind_order_from_message,
    bind_periods_from_message,
    refine_patch_from_message,
)
from financial_analyst_agent.rules_planner import DemoCompleter, issuer_index
from financial_analyst_agent.runtime import FIXTURE_UNIVERSE_SNAPSHOT_PATH


@pytest.mark.parametrize(
    ("question", "industry", "limit"),
    [
        ("Which three chipmakers are worth the most?", "chipmakers", 3),
        ("Rank the two largest banks by market value", "banks", 2),
        ("Which five banks are the largest by market cap?", "banks", 5),
        ("What are the 3 most valuable banks?", "banks", 3),
        ("the most valuable healthcare companies", "healthcare", 10),
    ],
)
def test_a_ranking_reads_its_group_and_count(question: str, industry: str, limit: int) -> None:
    plan = DemoCompleter(issuer_index()).complete(question)

    assert plan.intent in (Intent.RANK, Intent.RANK_AND_LOOKUP)
    assert (plan.industry, plan.limit) == (industry, limit)


@pytest.mark.parametrize(
    ("question", "industry", "metric"),
    [
        ("chipmakers by free cash flow, lowest first", "chipmakers", "free_cash_flow"),
        ("big pharma by revenue", "big pharma", "revenue"),
        ("big banks by revenue", "big banks", "revenue"),
        ("Semiconductor companies by net margin", "semiconductor", "net_margin"),
    ],
)
def test_a_group_by_a_metric_is_a_ranking_without_top(
    question: str, industry: str, metric: str
) -> None:
    plan = DemoCompleter(issuer_index()).complete(question)

    assert plan.intent is Intent.RANK_AND_LOOKUP
    assert (plan.industry, plan.limit, plan.metric) == (industry, 10, metric)
    assert plan.order_by_metric is True


@pytest.mark.parametrize(
    "question", ["revenue by segment", "Apple revenue by quarter", "net income by year"]
)
def test_a_metric_by_something_is_not_a_ranking(question: str) -> None:
    plan = DemoCompleter(issuer_index()).complete(question)

    assert plan.intent is Intent.LOOKUP


@pytest.mark.parametrize(
    ("message", "ascending"),
    [
        ("top 5 banks by revenue, lowest first", True),
        ("chipmakers by free cash flow, smallest first", True),
        ("top 5 banks by revenue ascending", True),
        ("top 5 banks by revenue in ascending order", True),
        ("top 5 banks by revenue from the lowest", True),
        ("top 5 banks by revenue, largest first", False),
        ("top 5 banks by revenue, highest first", False),
        ("top 5 banks by revenue descending", False),
        ("top 5 banks by revenue", None),
        ("Apple revenue in the first quarter", None),
    ],
)
def test_the_order_direction_is_read_from_the_words(message: str, ascending: bool | None) -> None:
    patch = bind_order_from_message(SpecPatch(mode="replace"), message)

    added = "lowest_first" in patch.add_operations
    removed = "lowest_first" in patch.remove_operations
    assert (added, removed) == {True: (True, False), False: (False, True), None: (False, False)}[
        ascending
    ]


def test_naming_another_order_starts_again_from_the_largest() -> None:
    patch = bind_order_from_message(
        SpecPatch(mode="extend", set_order_by="revenue", add_operations=("order_by_metric",)),
        "sort by revenue",
    )

    assert patch.remove_operations == ("lowest_first",)
    assert patch.add_operations == ("order_by_metric",)


def test_the_two_largest_counts_a_group() -> None:
    plan = DemoCompleter(issuer_index()).complete("Compare the two largest banks")

    assert (plan.industry, plan.limit) == ("banks", 2)


@pytest.mark.parametrize(
    "question",
    [
        "Show me how Microsoft's newest 10-Q differs from the one before",
        "Microsoft's latest 10-K compared to the prior one",
    ],
)
def test_a_filing_comparison_in_other_words(question: str) -> None:
    assert DemoCompleter(issuer_index()).complete(question).intent is Intent.FILING_CHANGE


@pytest.mark.parametrize(
    "question",
    [
        "an apples-to-apples comparison of Microsoft and Nvidia",
        "Apples to apples: Merck vs Pfizer net margin",
        "comparing apples to apples, how do Merck and Pfizer stack up on net income?",
        "Merck and Pfizer net margin, apples with apples",
        "Merck vs Pfizer net margin, apples for apples",
        "Merck vs Pfizer revenue is apples and oranges",
        "the building blocks of Microsoft and Oracle revenue",
    ],
)
def test_a_word_inside_an_idiom_is_not_a_misspelt_name(question: str) -> None:
    """A hyphened phrase or an idiom owns its words: "apples" is not Apple."""
    found = issuer_index().correct(question)

    assert found == []


@pytest.mark.parametrize(
    "question",
    [
        "Apples to apples: Merck vs Pfizer net margin",
        "Merck vs Pfizer net margin, apples and oranges",
    ],
)
def test_an_idiom_beside_real_companies_names_only_them(question: str) -> None:
    plan = DemoCompleter(issuer_index()).complete(question)

    assert plan.intent is Intent.COMPARE
    assert plan.companies == ("MRK", "PFE")
    assert plan.notes == ()


def _spec(*companies: str, metrics: tuple[str, ...] = ("net_income",)):
    ranking = SnapshotRanking.from_path(FIXTURE_UNIVERSE_SNAPSHOT_PATH)
    patch = SpecPatch(mode="replace", add_companies=companies, add_metrics=metrics)
    return resolve_spec(apply_patch(None, patch), ranking=ranking), ranking.index


@pytest.mark.parametrize("message", ["swap Merck for AbbVie", "replace Merck with AbbVie"])
def test_swap_x_for_y_replaces_x(message: str) -> None:
    spec, index = _spec("PFE", "MRK")
    patch = refine_patch_from_message(SpecPatch(mode="replace"), message, spec, index=index)

    assert (patch.add_companies, patch.remove_companies) == (("AbbVie",), ("Merck",))


@pytest.mark.parametrize(
    "message",
    [
        "switch the metric to free cash flow",
        "change it to free cash flow",
        "show free cash flow instead",
    ],
)
def test_switching_the_metric_replaces_it(message: str) -> None:
    spec, index = _spec("AMGN")
    patch = refine_patch_from_message(
        SpecPatch(mode="extend", add_metrics=("free_cash_flow",)), message, spec, index=index
    )

    assert (patch.add_metrics, patch.remove_metrics) == (("free_cash_flow",), ("net_income",))


def test_adding_a_metric_never_removes_one() -> None:
    spec, index = _spec("MSFT", "AAPL", metrics=("revenue",))
    proposed = SpecPatch(
        mode="extend", add_metrics=("operating_margin",), remove_metrics=("revenue",)
    )
    patch = refine_patch_from_message(proposed, "now add operating margin", spec, index=index)

    assert (patch.add_metrics, patch.remove_metrics) == (("operating_margin",), ())


def test_metric_wording_records_which_metric_orders_the_answer() -> None:
    proposed = SpecPatch(mode="extend", add_operations=("order_by_metric",))

    patch, refusal = bind_metrics_from_message(proposed, "sort by net income")

    assert refusal is None
    assert patch.set_order_by == "net_income"


def test_merge_uses_the_specs_ordering_metric_not_the_message() -> None:
    from financial_analyst_agent.graph.analysis_spec import AnalysisSpec
    from financial_analyst_agent.graph.spec_turn import _ordering_metric

    spec = AnalysisSpec(metrics=("revenue", "net_income"), order_by="net_income")

    assert _ordering_metric(spec) == "net_income"


def test_over_the_past_year_is_the_years_quarters_not_growth() -> None:
    message = "Compare JPMorgan and Bank of America net income over the past year"
    patch = bind_periods_from_message(SpecPatch(mode="replace"), message)

    assert patch.set_periods == PeriodSelection(kind="last_n_quarters", count=4)
    assert "year_over_year" not in patch.add_operations


@pytest.mark.parametrize(
    ("message", "count"),
    [
        ("How did AMD's EBITDA change over the past year?", 4),
        ("How has Tesla's revenue changed over the last year?", 4),
        ("How did AMD's EBITDA change in the last 12 months?", 4),
        ("How did AMD's EBITDA grow over the last 2 years?", 8),
        ("AMD EBITDA growth over the last 4 quarters", 4),
    ],
)
def test_a_change_over_a_named_window_is_year_over_year_over_that_window(
    message: str, count: int
) -> None:
    """README's growth row: "change over the past year" is 4 quarters, each year over year."""
    patch = bind_periods_from_message(SpecPatch(mode="replace"), message)

    assert patch.set_periods == PeriodSelection(kind="last_n_quarters", count=count)
    assert "across_periods" in patch.add_operations
    assert "year_over_year" in patch.add_operations


@pytest.mark.parametrize(
    ("message", "base"),
    [
        ("Apple revenue growth", "year_over_year"),
        ("How fast did Nvidia's revenue grow?", "year_over_year"),
        ("Microsoft net income trend", "year_over_year"),
        ("How has Tesla's revenue changed over the last year?", "year_over_year"),
        ("Apple revenue year over year", "year_over_year"),
        ("Is Apple's revenue up year on year?", "year_over_year"),
        ("Apple revenue year-on-year", "year_over_year"),
        ("Apple revenue y/y", "year_over_year"),
        ("Apple revenue sequential growth", "sequential"),
        ("Apple revenue vs last quarter", "sequential"),
        ("Apple revenue quarter-over-quarter", "sequential"),
        ("Why did Apple's revenue drop last quarter?", "unclear"),
        ("How has Microsoft revenue changed?", "unclear"),
        ("How much did Intel's revenue change?", "unclear"),
        ("How much has Intel's revenue changed?", "unclear"),
        ("Did Intel's revenue change?", "unclear"),
        ("How did Intel's net income move?", "unclear"),
        ("What drove the change in Apple's revenue?", "unclear"),
        ("What caused the drop in Intel's net income?", "unclear"),
        ("What is behind the increase in Nvidia's revenue?", "unclear"),
        # "what caused ... to fall", "what's behind the drop in ...", "what led to the
        # decline in ...": a change named with no base, like "why did ... drop".
        ("What caused Pfizer's earnings to fall?", "unclear"),
        ("What caused Apple's revenue to fall?", "unclear"),
        ("what has caused apple's revenue to rise", "unclear"),
        ("What made Nvidia's revenue jump?", "unclear"),
        ("What's behind the drop in Apple's revenue?", "unclear"),
        ("What led to the decline in Pfizer's revenue?", "unclear"),
        ("What's the reason for the drop in Intel's revenue?", "unclear"),
        ("What caused Apple's revenue to fall year over year?", "year_over_year"),
        ("What caused Apple's revenue to fall since 2023?", None),
        ("What drove the change in Apple's revenue year over year?", "year_over_year"),
        ("What drove the change in Apple's revenue since 2023?", None),
        ("How much did Intel's revenue change year over year?", "year_over_year"),
        ("How much did Intel's revenue change since last quarter?", "sequential"),
        ("How much did Intel's revenue change over the last year?", None),
        ("Over the past 10 quarters, how has Thermo Fisher's revenue moved?", None),
        ("How much did Intel's revenue change since 2023?", None),
        ("Apple revenue last quarter", None),
    ],
)
def test_what_a_change_is_measured_against(message: str, base: str | None) -> None:
    from financial_analyst_agent.request_wording import comparison_asked

    assert comparison_asked(message) == base


@pytest.mark.parametrize(
    ("answer", "base"),
    [
        ("year_over_year", "year_over_year"),
        ("sequential", "sequential"),
        ("1", "year_over_year"),
        ("the quarter before", "sequential"),
        ("same quarter a year earlier", "year_over_year"),
        ("yoy", "year_over_year"),
        ("y/y", "year_over_year"),
        ("year on year", "year_over_year"),
        ("vs the previous quarter", "sequential"),
    ],
)
def test_an_answer_names_the_base_of_a_change(answer: str, base: str) -> None:
    from financial_analyst_agent.graph.clarify import clarification_reply
    from financial_analyst_agent.graph.state import PendingClarification
    from financial_analyst_agent.request_wording import COMPARISON_CANDIDATES

    pending = PendingClarification(
        kind="ambiguous_comparison",
        candidates=COMPARISON_CANDIDATES,
        patch=SpecPatch(mode="replace"),
    )
    reply = clarification_reply(pending, answer)

    assert reply is not None and reply.chosen == (base,)


@pytest.mark.parametrize(
    "message",
    [
        "remove year over year",
        "drop the year-over-year change",
        "no YoY",
        "remove year on year",
        "without year over year growth",
        "take out the year-over-year column",
    ],
)
def test_removing_year_over_year_takes_the_change_away_and_keeps_the_window(message: str) -> None:
    patch = bind_periods_from_message(SpecPatch(mode="extend"), message)

    assert patch.set_periods is None
    assert set(patch.remove_operations) == {"across_periods", "year_over_year"}
    assert not patch.add_operations


def test_year_over_year_on_its_own_still_asks_for_it() -> None:
    patch = bind_periods_from_message(SpecPatch(mode="extend"), "year over year")

    assert "year_over_year" in patch.add_operations
    assert not patch.remove_operations


@pytest.mark.parametrize(
    "spelling", ["year on year", "year-on-year", "YoY", "y/y", "Y/Y"]
)
def test_year_over_year_spelt_another_way_reads_the_same(spelling: str) -> None:
    def bound(wording: str) -> SpecPatch:
        message = f"is unitedhealth's operating cash flow up {wording}"
        return bind_periods_from_message(SpecPatch(mode="replace"), message)

    assert bound(spelling) == bound("year over year")
    assert "year_over_year" in bound(spelling).add_operations


@pytest.mark.parametrize(
    "wording",
    [
        "from a year earlier",
        "from a year ago",
        "from last year",
        "compared with the same quarter last year",
        "versus the same quarter a year earlier",
        "against the year-earlier quarter",
    ],
)
def test_a_year_earlier_reads_as_year_over_year(wording: str) -> None:
    def bound(base: str) -> SpecPatch:
        message = f"is unitedhealth's operating cash flow up {base}"
        return bind_periods_from_message(SpecPatch(mode="replace"), message)

    assert bound(wording) == bound("year over year")


def test_every_kind_of_clarification_is_one_entry_in_the_table() -> None:
    from typing import get_args

    from financial_analyst_agent.contracts import ClarifyKind
    from financial_analyst_agent.graph.clarify import CLARIFY_KINDS, clarify_prompt

    assert set(CLARIFY_KINDS) == set(get_args(ClarifyKind))
    asked = clarify_prompt("ambiguous_company", "Lincoln")
    assert asked == "Which company do you mean by “Lincoln”?"
    # A result saved before clarifications had kinds asked for a metric.
    assert clarify_prompt(None) == "Which metric do you mean?"


def test_asking_the_scope_question_again_names_its_own_answers() -> None:
    from financial_analyst_agent.graph.clarify import ClarifyReply, ask_again
    from financial_analyst_agent.graph.state import PendingClarification

    pending = PendingClarification(
        kind="ambiguous_mode", candidates=("extend", "replace"), patch=SpecPatch()
    )
    asked = ask_again(pending, ClarifyReply(out_of_range=True), "3", None)
    assert asked.result.banners == [
        "There are 2 options: pick 1 to 2, or type “extend” or “replace”."
    ]


def _window(count: int) -> PeriodSelection:
    return PeriodSelection(kind="last_n_quarters", count=count)


@pytest.mark.parametrize(
    ("message", "shown"),
    [("show that year over year", 6), ("as growth", 4), ("yoy please", 2)],
)
def test_a_year_over_year_follow_up_keeps_the_window_on_screen(message: str, shown: int) -> None:
    spec, index = _spec("AMGN", "GILD", metrics=("revenue",))
    spec = spec.model_copy(update={"periods": _window(shown)})

    patch = refine_patch_from_message(SpecPatch(mode="extend"), message, spec, index=index)
    draft = apply_patch(spec, patch)

    assert draft.periods == _window(shown)
    assert "year_over_year" in draft.operations


@pytest.mark.parametrize(
    ("message", "periods"),
    [
        # A window the follow-up names is the window.
        ("show that year over year for the last 3 quarters", _window(3)),
        # A sequential change reads the quarter before the oldest one shown as
        # its base, and still shows the four on screen.
        (
            "show that quarter over quarter",
            PeriodSelection(kind="last_n_quarters", count=5, asked=4),
        ),
    ],
)
def test_a_change_follow_up_that_needs_or_names_quarters_sets_them(
    message: str, periods: PeriodSelection
) -> None:
    spec, index = _spec("AMGN", "GILD", metrics=("revenue",))
    spec = spec.model_copy(update={"periods": _window(4)})

    patch = refine_patch_from_message(SpecPatch(mode="extend"), message, spec, index=index)

    assert apply_patch(spec, patch).periods == periods


@pytest.mark.parametrize("message", ["show that year over year", "as growth", "yoy please"])
@pytest.mark.parametrize(
    "named",
    [
        (NamedPeriodSpec(year=2025),),
        (NamedPeriodSpec(year=2025, quarter=2),),
        (NamedPeriodSpec(year=2025, quarter=1), NamedPeriodSpec(year=2025, quarter=2)),
    ],
)
def test_a_year_over_year_follow_up_keeps_a_named_period(
    message: str, named: tuple[NamedPeriodSpec, ...]
) -> None:
    spec, index = _spec("AAPL", metrics=("revenue",))
    on_screen = PeriodSelection(kind="named", named=named)
    spec = spec.model_copy(update={"periods": on_screen})

    patch = refine_patch_from_message(SpecPatch(mode="extend"), message, spec, index=index)
    draft = apply_patch(spec, patch)

    assert draft.periods == on_screen
    assert "year_over_year" in draft.operations


def test_year_over_year_after_quarter_over_quarter_reads_no_base_quarter() -> None:
    spec, index = _spec("AAPL", metrics=("revenue",))
    named = (NamedPeriodSpec(year=2025),)
    spec = spec.model_copy(
        update={
            "periods": PeriodSelection(kind="named", named=named, company_base_dates=()),
            "operations": ("across_periods",),
        }
    )

    patch = refine_patch_from_message(
        SpecPatch(mode="extend"), "show that year over year", spec, index=index
    )

    assert apply_patch(spec, patch).periods == PeriodSelection(kind="named", named=named)


def test_year_over_year_after_the_latest_quarter_shows_two_years() -> None:
    spec, index = _spec("AMGN", metrics=("revenue",))

    patch = refine_patch_from_message(
        SpecPatch(mode="extend"), "show that year over year", spec, index=index
    )

    assert apply_patch(spec, patch).periods == _window(8)


@pytest.mark.parametrize(
    "message", ["sequential instead", "quarter over quarter instead", "make it sequential"]
)
def test_a_sequential_follow_up_switches_the_change_and_keeps_the_window(message: str) -> None:
    # README's quarter-over-quarter row (probe-round-3-gaps ticket 05): after a
    # year-over-year view, the change switches and the quarters on screen stay.
    spec, index = _spec("AAPL", metrics=("revenue",))
    spec = spec.model_copy(
        update={"periods": _window(6), "operations": ("across_periods", "year_over_year")}
    )

    patch = refine_patch_from_message(SpecPatch(mode="extend"), message, spec, index=index)
    draft = apply_patch(spec, patch)

    # The quarter before the oldest one shown is read as its base, not shown.
    assert draft.periods == PeriodSelection(kind="last_n_quarters", count=7, asked=6)
    assert draft.operations == ("across_periods",)


def test_a_sequential_follow_up_keeps_a_named_period() -> None:
    spec, index = _spec("AAPL", metrics=("revenue",))
    named = (NamedPeriodSpec(year=2025),)
    spec = spec.model_copy(
        update={
            "periods": PeriodSelection(kind="named", named=named),
            "operations": ("across_periods", "year_over_year"),
        }
    )

    patch = refine_patch_from_message(
        SpecPatch(mode="extend"), "sequential instead", spec, index=index
    )
    draft = apply_patch(spec, patch)

    assert draft.periods == PeriodSelection(kind="named", named=named, company_base_dates=())
    assert draft.operations == ("across_periods",)


@pytest.mark.parametrize("message", ["year over year instead", "make it year over year"])
def test_year_over_year_instead_after_a_sequential_window_keeps_the_quarters(
    message: str,
) -> None:
    spec, index = _spec("AAPL", metrics=("revenue",))
    spec = spec.model_copy(
        update={
            "periods": PeriodSelection(kind="last_n_quarters", count=7, asked=6),
            "operations": ("across_periods",),
        }
    )

    patch = refine_patch_from_message(SpecPatch(mode="extend"), message, spec, index=index)
    draft = apply_patch(spec, patch)

    assert draft.periods.shown == 6
    assert "year_over_year" in draft.operations


@pytest.mark.parametrize(
    "message", ["drop Microsoft", "remove Microsoft", "without Microsoft", "take out Microsoft"]
)
def test_taking_a_company_away_removes_it(message: str) -> None:
    spec, index = _spec("AAPL", "MSFT", metrics=("revenue",))

    patch = refine_patch_from_message(SpecPatch(mode="extend"), message, spec, index=index)

    assert (patch.remove_companies, patch.add_companies, patch.add_metrics) == (("MSFT",), (), ())


@pytest.mark.parametrize(
    ("message", "explanation"),
    [
        # A general question: how something works, not a figure (README, general question).
        ("Explain how a share buyback affects EPS", True),
        ("explain EPS", True),
        ("Can you explain how revenue is recognized?", True),
        ("How does a buyback affect EPS?", True),
        ("How do buybacks impact diluted EPS?", True),
        ("How is EPS calculated?", True),
        ("How does depreciation work?", True),
        ("What is free cash flow and why does it matter?", True),
        ("Why does EPS matter?", True),
        ("Why is operating margin important?", True),
        ("What does diluted EPS mean?", True),
        # "What is X", X a measure with no article or possessive, asks what the measure is.
        ("What is EPS?", True),
        ("what is eps", True),
        ("What's EPS?", True),
        ("What are earnings per share?", True),
        ("What is free cash flow?", True),
        ("What is margin?", True),
        # A figure with no company asks which company; a change with no base asks its base.
        ("What's the EPS?", False),
        ("What is the EPS?", False),
        ("What is Apple's EPS?", False),
        ("What is Apple EPS?", False),
        ("What is its EPS?", False),
        ("What was the revenue last quarter?", False),
        ("revenue", False),
        ("Why did revenue drop?", False),
        ("How much did revenue change?", False),
        ("How is Apple doing?", False),
        ("How does Oracle's net income compare with Cisco's?", False),
        ("What changed in the latest 10-Q?", False),
    ],
)
def test_explanation_wording_is_told_from_a_figure(message: str, explanation: bool) -> None:
    from financial_analyst_agent.request_wording import asks_for_explanation

    assert asks_for_explanation(message) is explanation
