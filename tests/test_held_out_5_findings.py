"""The shared defects the fifth held-out set found, pinned on the recorded runtime.

Each case is run as the planner comparison runs it and must pass on every field
it is labelled with (docs/evaluation/held-out-5-findings.md): with the rules
planner, and with a stand-in for the LLM planner proposing what the run's
observation shows it proposed, so no test calls OpenAI.
"""

from __future__ import annotations

import uuid
from dataclasses import replace
from datetime import date
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from financial_analyst_agent.contracts import Intent, Runtime, WorkflowPlan
from financial_analyst_agent.conversation import run_conversation_turn
from financial_analyst_agent.domain.errors import PlannerError
from financial_analyst_agent.planner_cascade import CascadeCompleter, unsure_reason
from financial_analyst_agent.planner_evaluation import PlannerCase, load_cases, run_planner
from financial_analyst_agent.rules_planner import DemoCompleter, issuer_index
from financial_analyst_agent.runtime import recorded_runtime
from financial_analyst_agent.thread_store import EphemeralThreadStore
from financial_analyst_agent.turn import run_turn
from helpers import FakeFacts

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
# comparison's observation: Goldman's net interest income over five quarters,
# and a company beside each everyday word used as the word.
_LLM_PLANS = {
    "h5_gr_gs_both": WorkflowPlan(
        intent=Intent.LOOKUP, company="Goldman", metric="net_interest_income", recent_quarters=5
    ),
    "h5_ow_intel_word": WorkflowPlan(
        intent=Intent.COMPARE, companies=("Palantir", "Intel"), metric="operating_income"
    ),
    "h5_ow_micron_measure": WorkflowPlan(
        intent=Intent.COMPARE, companies=("Broadcom", "Micron"), metric="gross_margin"
    ),
    "h5_ow_apple_idiom": WorkflowPlan(
        intent=Intent.COMPARE, companies=("AbbVie", "Apple"), metric="revenue"
    ),
    "h5_ow_oracle_word": WorkflowPlan(
        intent=Intent.COMPARE, companies=("Cisco", "Oracle"), metric="cash"
    ),
    "h5_mw_iphone": WorkflowPlan(intent=Intent.LOOKUP, company="Apple", metric="revenue"),
    # Revenue, which the question implies but does not name: refused on one run.
    "h5_gr_fast_avgo": WorkflowPlan(intent=Intent.LOOKUP, company="Broadcom", metric="revenue"),
    "h5_rk_drugs_gm": WorkflowPlan(
        intent=Intent.RANK_AND_LOOKUP,
        industry="drugmakers",
        metric="gross_margin",
        limit=3,
        order_by_metric=True,
        recent_quarters=4,
    ),
    # A general explanation, though the question names a company and its figure.
    "h5_co_buyback": WorkflowPlan(
        intent=Intent.EXPLAIN, topic="How does Apple's buyback affect its EPS?"
    ),
    "h5_co_volatile": WorkflowPlan(
        intent=Intent.EXPLAIN, topic="Why is Goldman's revenue so volatile?"
    ),
    # News, on one run of three, though the question asks about a change.
    "h5_cl_drop": WorkflowPlan(
        intent=Intent.NEWS_AND_EXPLAIN, topic="Why did NVIDIA's revenue drop?"
    ),
    "h5_cl_fall": WorkflowPlan(
        intent=Intent.NEWS_AND_EXPLAIN, topic="What caused Pfizer's earnings to fall?"
    ),
    # A ranking with no group, refused as an unknown industry.
    "h5_rk_worth": WorkflowPlan(intent=Intent.RANK),
}


@pytest.mark.parametrize(
    "case_id",
    [
        # Naming both bases shows both changes, with the bases leading the question.
        "h5_gr_gs_both",
        # An everyday-word name used as the word names no company (ticket 02).
        "h5_ow_intel_word",
        "h5_ow_micron_measure",
        "h5_ow_micron_unit",
        "h5_ow_apple_idiom",
        "h5_ow_oracle_word",
        # A segment one company reports names it (ticket 03).
        "h5_mw_iphone",
        # A ranking reads whatever comes first: a count (ticket 04).
        "h5_rk_banks_ni",
        # A ranking records the latest quarter it shows (ticket 05).
        "h5_rk_drugs_gm",
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


@pytest.mark.parametrize(
    ("question", "companies", "metric", "kept"),
    [
        ("Intel and Palantir operating income", ("Intel", "Palantir"), "operating_income",
         {"INTC", "PLTR"}),
        ("Micron and Broadcom gross margin, to the micron", ("Micron", "Broadcom"),
         "gross_margin", {"MU", "AVGO"}),
    ],
)
def test_a_company_named_beside_the_word_stays(
    question: str, companies: tuple[str, ...], metric: str, kept: set[str], runtime: Runtime
) -> None:
    """Only a company the question names through the word alone is dropped."""
    for planner in (runtime.completer, _ProposedPlan(
        WorkflowPlan(intent=Intent.COMPARE, companies=companies, metric=metric)
    )):
        turn = run_conversation_turn(
            f"held-out-5-{uuid.uuid4()}",
            question,
            replace(runtime, completer=planner),
            store=EphemeralThreadStore(),
        )

        assert {row.ticker for row in turn.result.table_rows} == kept


_NO_COMPANY = WorkflowPlan(intent=Intent.LOOKUP, metric="revenue")


@pytest.mark.parametrize(
    ("question", "ticker"),
    [
        ("iPhone sales", "AAPL"),
        ("iPad revenue", "AAPL"),
        ("Mac sales", "AAPL"),
        ("Azure revenue", "MSFT"),
        ("Xbox revenue", "MSFT"),
        ("YouTube revenue", "GOOG"),
    ],
)
def test_a_segment_names_its_company_whichever_planner(
    question: str, ticker: str, runtime: Runtime
) -> None:
    """With no company named, the segment names it: the company-wide figure, with
    the note that filings report totals, not segments (README, a segment)."""
    for planner in (runtime.completer, _ProposedPlan(_NO_COMPANY)):
        turn = run_conversation_turn(
            f"held-out-5-{uuid.uuid4()}",
            question,
            replace(runtime, completer=planner),
            store=EphemeralThreadStore(),
        )

        assert {row.ticker for row in turn.result.table_rows} == {ticker}
        assert {row.metric for row in turn.result.table_rows} == {"revenue"}
        assert any("not segments" in banner for banner in turn.result.banners)


def test_the_cascade_keeps_the_rules_plan_for_a_segment(runtime: Runtime) -> None:
    plan = runtime.completer.complete("iPhone sales")

    assert unsure_reason(plan, lambda industry: True) is None


def test_a_company_named_beside_a_segment_stays(runtime: Runtime) -> None:
    """"Microsoft iPhone sales" names Microsoft: the segment names no one else."""
    turn = run_conversation_turn(
        f"held-out-5-{uuid.uuid4()}",
        "Microsoft iPhone sales",
        runtime,
        store=EphemeralThreadStore(),
    )

    assert {row.ticker for row in turn.result.table_rows} == {"MSFT"}


class _CompanyWideRevenue(FakeFacts):
    """Revenue for whichever company is asked, as its company-wide figure."""

    def __init__(self) -> None:
        self.asked: list[str] = []

    def get_financials(
        self, company: str, metric: str, *, report_date: date | None = None
    ) -> SimpleNamespace:
        self.asked.append(company)
        return SimpleNamespace(
            company_name=company,
            ticker=company[:4].upper(),
            cik="0000000001",
            metric=metric,
            value=Decimal("1000000000"),
            currency="USD",
            start_date=date(2026, 4, 1),
            end_date=date(2026, 6, 30),
            filed_date=date(2026, 7, 30),
            form="10-Q",
            accession_number="0000000001-26-000001",
            taxonomy="us-gaap",
            concept="Revenues",
            source_url="https://www.sec.gov/Archives/edgar/data/1/fake.htm",
            source="sec_xbrl",
        )


@pytest.mark.parametrize(
    ("question", "company"),
    [
        ("AWS revenue", "Amazon"),
        ("Instagram revenue", "Meta"),
        ("WhatsApp sales", "Meta"),
    ],
)
def test_a_segment_of_an_unrecorded_company_names_it(question: str, company: str) -> None:
    """Amazon and Meta are not in the recording: fake facts stand in."""
    for planner in (DemoCompleter(issuer_index()), _ProposedPlan(_NO_COMPANY)):
        facts = _CompanyWideRevenue()

        result = run_turn(question, Runtime(completer=planner, facts=facts))

        assert facts.asked == [company]
        assert any("not segments" in banner for banner in result.banners)


def test_a_ranking_after_a_leading_window_keeps_the_rules_plan(runtime: Runtime) -> None:
    plan = runtime.completer.complete(_case("h5_rk_drugs_gm").turns[0])

    assert unsure_reason(plan, lambda industry: True) is None


@pytest.mark.parametrize(
    "question",
    [
        "Over the past year, the top 3 drugmakers by gross margin",
        "This quarter, the top 3 drugmakers by gross margin",
        "the 3 biggest drugmakers by gross margin",
        "3 drugmakers by gross margin",
    ],
)
def test_a_ranking_reads_whatever_comes_first(question: str, runtime: Runtime) -> None:
    """A leading count or window: the top three drugmakers, each its latest quarter."""
    turn = run_conversation_turn(
        f"held-out-5-{uuid.uuid4()}", question, runtime, store=EphemeralThreadStore()
    )

    rows = turn.result.table_rows
    assert [row.ticker for row in rows] == ["LLY", "ABBV", "JNJ"]
    assert {row.metric for row in rows} == {"gross_margin"}
    assert [row.rank for row in rows] == [1, 2, 3]


def test_a_ranking_over_a_window_shows_the_latest_quarter_with_its_note(
    runtime: Runtime,
) -> None:
    turn = run_conversation_turn(
        f"held-out-5-{uuid.uuid4()}",
        "Over the past year, the top 3 drugmakers by gross margin",
        runtime,
        store=EphemeralThreadStore(),
    )

    assert len(turn.result.table_rows) == 3
    assert any("latest quarter" in banner for banner in turn.result.banners)


@pytest.mark.parametrize(
    ("question", "group"),
    [
        ("5 banks by net income", "banks"),
        ("Last quarter, chipmakers by revenue", "chipmakers"),
        ("Over the last 4 quarters, 5 banks by revenue", "banks"),
    ],
)
def test_the_cascade_keeps_the_rules_ranking(question: str, group: str, runtime: Runtime) -> None:
    plan = runtime.completer.complete(question)

    assert plan.intent is Intent.RANK_AND_LOOKUP
    assert plan.industry == group
    assert unsure_reason(plan, lambda industry: True) is None


def test_a_count_of_quarters_leading_by_a_metric_ranks_no_group(runtime: Runtime) -> None:
    """ "the 5 quarters by revenue" counts quarters, not a group to rank."""
    plan = runtime.completer.complete("the 5 quarters by revenue")

    assert plan.intent is not Intent.RANK_AND_LOOKUP


@pytest.mark.parametrize(
    "question",
    [
        "Over the past year, the top 3 drugmakers by gross margin",
        "top 3 drugmakers by gross margin over the last 4 quarters",
        "top 3 drugmakers by gross margin in fiscal 2025",
    ],
)
def test_a_ranking_records_the_latest_quarter_with_the_window_note(
    question: str, runtime: Runtime
) -> None:
    """The window asked for is said in the note, not kept as the analysis's period:
    no "four latest quarters" banner for a ranking that shows one."""
    turn = run_conversation_turn(
        f"held-out-5-{uuid.uuid4()}", question, runtime, store=EphemeralThreadStore()
    )

    assert turn.analysis_spec is not None
    assert turn.analysis_spec.periods.kind == "latest_quarter"
    assert any("latest quarter" in banner for banner in turn.result.banners)
    assert not any("four latest quarters" in banner for banner in turn.result.banners)


def test_a_ranking_with_no_window_has_no_window_note(runtime: Runtime) -> None:
    turn = run_conversation_turn(
        f"held-out-5-{uuid.uuid4()}",
        "top 3 drugmakers by gross margin",
        runtime,
        store=EphemeralThreadStore(),
    )

    assert not any("Ranked lists" in banner for banner in turn.result.banners)


def test_adding_a_company_to_a_windowed_ranking_keeps_the_latest_quarter(
    runtime: Runtime,
) -> None:
    store = EphemeralThreadStore()
    thread = f"held-out-5-{uuid.uuid4()}"
    run_conversation_turn(
        thread, "Over the past year, the top 3 drugmakers by gross margin", runtime, store=store
    )

    turn = run_conversation_turn(thread, "add Pfizer", runtime, store=store)

    assert turn.analysis_spec is not None
    assert turn.analysis_spec.periods.kind == "latest_quarter"
    assert len({row.end_date for row in turn.result.table_rows if row.ticker == "LLY"}) == 1


def test_a_growth_ranking_records_the_latest_quarter_and_shows_its_change(
    runtime: Runtime,
) -> None:
    """Each bank's latest quarter beside its change on the year before (ADR 0009)."""
    turn = run_conversation_turn(
        f"held-out-5-{uuid.uuid4()}",
        "top 5 banks by revenue growth",
        runtime,
        store=EphemeralThreadStore(),
    )

    assert turn.analysis_spec is not None
    assert turn.analysis_spec.periods.kind == "latest_quarter"
    rows = turn.result.table_rows
    assert [row.ticker for row in rows if row.comparison == "year_over_year"] == [
        "JPM",
        "BAC",
        "WFC",
    ]
    assert len({row.end_date for row in rows}) == 1


def test_adding_a_company_to_a_growth_ranking_shows_growth_over_its_window(
    runtime: Runtime,
) -> None:
    store = EphemeralThreadStore()
    thread = f"held-out-5-{uuid.uuid4()}"
    run_conversation_turn(thread, "top 5 banks by revenue growth", runtime, store=store)

    turn = run_conversation_turn(thread, "add Apple", runtime, store=store)

    assert turn.analysis_spec is not None
    assert turn.analysis_spec.periods.kind == "last_n_quarters"
    assert "year_over_year" in turn.analysis_spec.operations
    assert {row.ticker for row in turn.result.table_rows} == {"AAPL", "JPM", "BAC", "WFC"}


class _Refuses:
    """The LLM planner's place on the runs that refused: it plans nothing."""

    def complete(self, query: str, current_spec: Any = None) -> WorkflowPlan:
        raise PlannerError("the LLM planner refused")


def test_growth_with_no_metric_keeps_the_rules_plan_under_the_cascade(runtime: Runtime) -> None:
    """"How fast is Broadcom growing?" is revenue growth (README): the rules planner
    proposes revenue, so a refusing LLM planner is never asked."""
    cascade = CascadeCompleter(runtime.completer, _Refuses(), lambda industry: True)

    (result,) = run_planner([_case("h5_gr_fast_avgo")], cascade, runs=1, runtime=runtime)

    assert cascade.last_reason is None
    assert not result.error
    assert result.checks == {name: True for name in result.checks}


@pytest.mark.parametrize(
    "question", ["How fast is Broadcom growing?", "Is Apple growing?", "How has Nvidia grown?"]
)
def test_the_rules_planner_proposes_revenue_for_growth_with_no_metric(
    question: str, runtime: Runtime
) -> None:
    plan = runtime.completer.complete(question)

    assert plan.metric == "revenue"
    assert unsure_reason(plan, lambda industry: True) is None


def _turn(question: str, planner: Any, runtime: Runtime) -> Any:
    return run_conversation_turn(
        f"held-out-5-{uuid.uuid4()}",
        question,
        replace(runtime, completer=planner),
        store=EphemeralThreadStore(),
    )


@pytest.mark.parametrize(
    ("question", "ticker", "metric"),
    [
        ("Why is Goldman's revenue so volatile?", "GS", "revenue"),
        ("Why is Apple's gross margin so high?", "AAPL", "gross_margin"),
        ("How does Apple's buyback affect its EPS?", "AAPL", "eps_diluted"),
    ],
)
def test_a_named_companys_question_is_its_figure_whichever_planner(
    question: str, ticker: str, metric: str, runtime: Runtime
) -> None:
    """A named company and a catalog metric are that company's figure (README, the
    why row), even when a planner reads the question as a general explanation."""
    for planner in (runtime.completer, _ProposedPlan(WorkflowPlan(intent=Intent.EXPLAIN))):
        turn = _turn(question, planner, runtime)

        assert {row.ticker for row in turn.result.table_rows} == {ticker}
        assert {row.metric for row in turn.result.table_rows} == {metric}


def test_a_named_companys_why_has_the_why_note_whichever_planner(runtime: Runtime) -> None:
    for planner in (runtime.completer, _ProposedPlan(WorkflowPlan(intent=Intent.EXPLAIN))):
        turn = _turn("Why is Goldman's revenue so volatile?", planner, runtime)

        assert any("not why" in banner for banner in turn.result.banners)


def test_a_named_companys_how_has_no_why_note(runtime: Runtime) -> None:
    turn = _turn(
        "How does Apple's buyback affect its EPS?",
        _ProposedPlan(WorkflowPlan(intent=Intent.EXPLAIN)),
        runtime,
    )

    assert not any("not why" in banner for banner in turn.result.banners)


@pytest.mark.parametrize(
    "question",
    ["How might AI change Goldman Sachs's business?", "Explain how a share buyback affects EPS"],
)
def test_a_question_naming_no_company_figure_stays_an_explanation(
    question: str, runtime: Runtime
) -> None:
    turn = _turn(question, _ProposedPlan(WorkflowPlan(intent=Intent.EXPLAIN)), runtime)

    assert turn.result.intent is Intent.EXPLAIN
    assert not turn.result.table_rows


_NEWS = WorkflowPlan(intent=Intent.NEWS_AND_EXPLAIN)


@pytest.mark.parametrize(
    "question",
    [
        "Why did NVIDIA's revenue drop?",
        "What caused Pfizer's earnings to fall?",
        "What drove the change in Oracle's free cash flow?",
    ],
)
def test_a_change_with_no_base_asks_against_what_whichever_planner(
    question: str, runtime: Runtime
) -> None:
    """A change that names no base is asked about (README, a change with no base),
    even when a planner reads the question as news."""
    for planner in (runtime.completer, _ProposedPlan(_NEWS)):
        turn = _turn(question, planner, runtime)

        assert turn.result.clarify_kind == "ambiguous_comparison"


def test_a_change_with_no_base_and_no_company_asks_which_company_whichever_planner(
    runtime: Runtime,
) -> None:
    rules = _turn("Why did revenue drop?", runtime.completer, runtime)
    news = _turn("Why did revenue drop?", _ProposedPlan(_NEWS), runtime)

    assert news.result.intent is rules.result.intent is Intent.LOOKUP
    assert news.result.message == rules.result.message


@pytest.mark.parametrize(
    "question",
    [
        "What's the news on why NVIDIA's revenue dropped?",
        "Headlines on why Pfizer's earnings fell",
    ],
)
def test_a_change_asked_as_news_by_name_stays_news(question: str, runtime: Runtime) -> None:
    turn = _turn(question, _ProposedPlan(_NEWS), runtime)

    assert turn.result.intent is Intent.NEWS_AND_EXPLAIN
