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
from financial_analyst_agent.planner_cascade import unsure_reason
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
