"""Wording the planners misread on the development cases: rankings, swaps and filings."""

from __future__ import annotations

import pytest

from financial_analyst_agent.contracts import Intent
from financial_analyst_agent.graph.analysis_spec import (
    PeriodSelection,
    SpecPatch,
    apply_patch,
    resolve_spec,
)
from financial_analyst_agent.ranking import SnapshotRanking
from financial_analyst_agent.request_wording import (
    bind_metrics_from_message,
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


def test_a_hyphened_phrase_is_not_a_misspelt_name() -> None:
    found = issuer_index().correct("an apples-to-apples comparison of Microsoft and Nvidia")

    assert found == []


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
    ("message", "count"),
    [
        # A window the follow-up names is the window.
        ("show that year over year for the last 3 quarters", 3),
        # A sequential change needs the quarter before the oldest one shown.
        ("show that quarter over quarter", 5),
    ],
)
def test_a_change_follow_up_that_needs_or_names_quarters_sets_them(
    message: str, count: int
) -> None:
    spec, index = _spec("AMGN", "GILD", metrics=("revenue",))
    spec = spec.model_copy(update={"periods": _window(4)})

    patch = refine_patch_from_message(SpecPatch(mode="extend"), message, spec, index=index)

    assert apply_patch(spec, patch).periods == _window(count)


def test_year_over_year_after_the_latest_quarter_shows_two_years() -> None:
    spec, index = _spec("AMGN", metrics=("revenue",))

    patch = refine_patch_from_message(
        SpecPatch(mode="extend"), "show that year over year", spec, index=index
    )

    assert apply_patch(spec, patch).periods == _window(8)
