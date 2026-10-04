"""Regressions for the PRD/ADR review findings, run on the recorded runtime."""

from __future__ import annotations

import pytest

from financial_analyst_agent.contracts import Intent, RendererKind, Runtime
from financial_analyst_agent.runtime import recorded_runtime
from financial_analyst_agent.turn import run_turn
from helpers import FakeFacts


@pytest.fixture(scope="module")
def runtime() -> Runtime:
    return recorded_runtime()


def test_a_rejected_comparison_is_labelled_a_comparison(runtime: Runtime) -> None:
    # Story 32: a refusal names the analysis asked for, not a default lookup.
    result = run_turn("compare Apple and Microsoft revenue in Q3 FY2040", runtime)

    assert result.renderer is RendererKind.REFUSE
    assert result.intent is Intent.COMPARE


def test_a_cached_fact_reads_back_as_the_same_financial_fact() -> None:
    # ADR 0003: the facts port returns FinancialFact, cache hit or not.
    from datetime import date
    from decimal import Decimal

    from financial_analyst_agent.domain.enums import Metric
    from financial_analyst_agent.domain.models import FinancialFact
    from financial_analyst_agent.evidence_store import EvidenceCachedFacts, InMemoryEvidenceStore

    fact = FinancialFact(
        company_name="Microsoft Corporation",
        ticker="MSFT",
        cik="0000789019",
        metric=Metric.REVENUE,
        value=Decimal("70066000000"),
        currency="USD",
        start_date=date(2026, 1, 1),
        end_date=date(2026, 3, 31),
        filed_date=date(2026, 4, 29),
        form="10-Q",
        accession_number="0000950170-26-000123",
        taxonomy="us-gaap",
        concept="Revenues",
        source_url="https://www.sec.gov/example.htm",
    )

    class _Facts(FakeFacts):
        def get_financials(
            self, company: str, metric: str, *, report_date: date | None = None
        ) -> FinancialFact:
            return fact

    cached = EvidenceCachedFacts(_Facts(), InMemoryEvidenceStore(), prior_ids=frozenset())
    fresh = cached.get_financials("MSFT", "revenue")
    again = cached.get_financials("MSFT", "revenue")

    assert isinstance(again, FinancialFact)
    assert again == fresh == fact


@pytest.mark.parametrize(
    ("cik", "title", "operating"),
    [
        ("0009999999", "MICROSOFT CORP", True),
        ("0009999999", "ACME CAPITAL TRUST II 7.875% NOTES", False),
        # Only preferreds listed, but an operating utility that files 10-Qs.
        ("0000092103", "SOUTHERN CALIFORNIA EDISON Co", True),
        # Ares Capital, a BDC on the ineligible CIK list.
        ("0001287750", "ARES CAPITAL CORP", False),
    ],
)
def test_a_name_outside_the_freeze_is_judged_by_its_sec_identity(
    cik: str, title: str, operating: bool
) -> None:
    # ADR 0002: listing-title tokens and the CIK list; lookups ignore ticker suffixes.
    from financial_analyst_agent.universe import sec_identity_is_operating

    assert sec_identity_is_operating(cik, title) is operating


@pytest.mark.parametrize(
    ("cik", "title", "listed", "operating"),
    [
        # A member: the snapshot judged it, whatever SEC's title says.
        ("0009999999", "ACME CAPITAL TRUST II 7.875% NOTES", {"0009999999"}, True),
        # A non-member is judged by its SEC title.
        ("0009999999", "ACME CAPITAL TRUST II 7.875% NOTES", set(), False),
        ("0009999999", "MICROSOFT CORP", set(), True),
        # The ineligible list wins over membership (AGENTS.md).
        ("0001287750", "ARES CAPITAL CORP", {"0001287750"}, False),
    ],
)
def test_one_operating_company_rule(
    cik: str, title: str, listed: set[str], operating: bool
) -> None:
    from financial_analyst_agent.domain.errors import IneligibleIssuerError
    from financial_analyst_agent.universe import require_operating

    if operating:
        require_operating(cik, title, listed)
        return
    with pytest.raises(IneligibleIssuerError, match="is not an operating company") as raised:
        require_operating(cik, title, listed)
    assert raised.value.details == {"cik": cik}


def test_an_ineligible_issuer_is_a_typed_miss_in_a_comparison() -> None:
    # ADR 0002: the row that failed the rule says so; the other row stays.
    from financial_analyst_agent.contracts import NOT_OPERATING_COMPANY
    from financial_analyst_agent.domain.errors import IneligibleIssuerError
    from financial_analyst_agent.turn import compare_metrics

    class _Facts(FakeFacts):
        def get_financials(self, company: str, metric: str, **_: object) -> object:
            raise IneligibleIssuerError("ARES CAPITAL CORP is not an operating company")

    [row] = compare_metrics(_Facts(), ["ARCC"], "revenue")  # type: ignore[arg-type]

    assert row.reason == NOT_OPERATING_COMPANY
    assert row.value is None


def _keyless_live_runtime() -> Runtime:
    """The live runtime's news and writing ports when the server has no keys."""
    from dataclasses import replace

    from financial_analyst_agent.contracts import RuntimeKind
    from financial_analyst_agent.news import RecordedNewsSearch
    from financial_analyst_agent.runtime import RecordedEssayCompleter

    return replace(
        recorded_runtime(),
        news=RecordedNewsSearch(),
        essay=RecordedEssayCompleter(live=True),
        kind=RuntimeKind.LIVE,
        live_news=False,
        live_essays=False,
    )


def test_a_replayed_news_answer_on_the_live_runtime_says_it_is_replayed() -> None:
    # Story 36: do not pretend a cassette is live.
    from financial_analyst_agent.news import FIXTURE_NEWS_QUERY
    from financial_analyst_agent.turn import (
        REPLAYED_ESSAY_BANNER,
        REPLAYED_NEWS_BANNER,
        current_events_answer,
    )

    result = current_events_answer(FIXTURE_NEWS_QUERY, _keyless_live_runtime())

    assert result.renderer is RendererKind.ESSAY
    assert REPLAYED_NEWS_BANNER in result.banners
    assert REPLAYED_ESSAY_BANNER in result.banners


def test_news_off_does_not_claim_a_search_found_nothing() -> None:
    from financial_analyst_agent.turn import NO_NEWS_MESSAGE, current_events_answer

    result = current_events_answer("What is new with Eli Lilly?", _keyless_live_runtime())

    assert result.renderer is RendererKind.REFUSE
    assert result.message is not None
    assert NO_NEWS_MESSAGE not in result.message
    assert "News search is off on this server" in result.message


@pytest.mark.parametrize("question", ["What was Apple's income?", "What was Apple's profit?"])
def test_an_ambiguous_metric_word_clarifies_on_the_rules_planner(
    runtime: Runtime, question: str
) -> None:
    # ADR 0004: "income" and "profit" are ambiguous; the planner no longer maps
    # "income" to net income with a phrase table of its own.
    from financial_analyst_agent.rules_planner import _metric_from_query

    assert _metric_from_query(question.casefold()) == "unknown"
    result = run_turn(question, runtime)
    assert result.renderer is RendererKind.CLARIFY
    assert "net_income" in result.candidates


def test_a_snapshot_member_listed_ineligible_later_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # AGENTS.md: a fund's CIK goes on the list; lookup refuses it before the
    # snapshot is rebuilt, as ranking does.
    from financial_analyst_agent import universe
    from financial_analyst_agent.domain.errors import IneligibleIssuerError
    from financial_analyst_agent.runtime import recorded_runtime

    monkeypatch.setattr(universe, "INELIGIBLE_ISSUER_CIKS", frozenset({"0000320193"}))

    with pytest.raises(IneligibleIssuerError):
        recorded_runtime().facts.get_financials("AAPL", "revenue")


@pytest.mark.parametrize(
    ("candidates", "prompt"),
    [
        (["extend", "replace"], "Add to the current analysis"),
        (["net_income", "operating_income"], "metric"),
    ],
)
def test_a_clarification_saved_before_its_kind_was_recorded_asks_the_same(
    candidates: list[str], prompt: str
) -> None:
    # A thread saved by an earlier release has no clarify_kind on its result.
    from financial_analyst_agent.contracts import TurnResult
    from financial_analyst_agent.presentation import present_turn

    saved = {
        "intent": "lookup",
        "tool_traces": [],
        "renderer": "clarify",
        "candidates": candidates,
    }
    shown = present_turn(TurnResult.model_validate(saved))

    assert shown.clarify_prompt is not None
    assert prompt.casefold() in shown.clarify_prompt.casefold()


@pytest.mark.parametrize(
    ("code", "reason"),
    [
        ("ineligible_issuer", "not_operating_company"),
        ("company_not_found", "company_not_found"),
        # As a comparison's cell says it: the facts disagree, not that none exist.
        ("ambiguous_fact", "ambiguous_concept"),
        ("unsupported_quarterly_fact", "missing_fact"),
    ],
)
def test_a_refused_cell_in_a_window_keeps_its_reason(code: str, reason: str) -> None:
    # ADR 0002: a fund in a table of quarters is a typed miss, not a missing filing.
    from types import SimpleNamespace

    from financial_analyst_agent.contracts import RendererKind, Runtime
    from financial_analyst_agent.domain.errors import (
        AmbiguousFactError,
        CompanyNotFoundError,
        IneligibleIssuerError,
        UnsupportedQuarterlyFactError,
    )
    from financial_analyst_agent.graph.analysis_spec import CompiledTask
    from financial_analyst_agent.turn import lookup_task

    errors = {
        "ineligible_issuer": IneligibleIssuerError("ARCC is not an operating company"),
        "company_not_found": CompanyNotFoundError(
            "Company not found for query 'Acme'", details={"query": "Acme"}
        ),
        "ambiguous_fact": AmbiguousFactError("Several facts match"),
        "unsupported_quarterly_fact": UnsupportedQuarterlyFactError(
            "No quarterly fact", details={"reason": "not_reported_or_derivable"}
        ),
    }

    class _Facts(FakeFacts):
        def get_financials(self, *_: object, **__: object) -> object:
            raise errors[code]

    task = CompiledTask(kind="lookup", issuers=("ARCC",), metric="revenue")
    result = lookup_task(
        task,
        Runtime(completer=SimpleNamespace(), facts=_Facts()),  # type: ignore[arg-type]
    )

    assert result.renderer is RendererKind.TABLE
    [cell] = result.table_rows

    assert cell.reason == reason


def test_one_company_with_one_failed_reason_is_refused_from_typed_metadata() -> None:
    from financial_analyst_agent.contracts import (
        COMPANY_NOT_FOUND,
        Intent,
        Refusal,
        RendererKind,
        TableRow,
        TurnResult,
    )
    from financial_analyst_agent.graph.analysis_spec import (
        AnalysisSpec,
        CompiledTask,
        ResolvedCompany,
        SpecPatch,
    )
    from financial_analyst_agent.graph.spec_turn import merge_analysis
    from financial_analyst_agent.graph.state import CompiledAnalysis

    task = CompiledTask(kind="lookup", issuers=("Acme",), metric="revenue")
    compiled = CompiledAnalysis(
        spec=AnalysisSpec(
            companies=(
                ResolvedCompany(cik="", name="Acme", ticker="", query="Acme"),
            ),
            metrics=("revenue",),
        ),
        tasks=(task,),
        patch=SpecPatch(mode="replace"),
        wording="Acme revenue",
    )
    failed = TurnResult(
        intent=Intent.LOOKUP,
        renderer=RendererKind.TABLE,
        tool_traces=[],
        table_rows=[
            TableRow(
                company_name="Acme",
                ticker="",
                cik="",
                metric="revenue",
                reason=COMPANY_NOT_FOUND,
            )
        ],
        message="Company not found for query 'Acme'",
        refusal=Refusal(code="company_not_found", details={"query": "Acme"}),
    )

    result = merge_analysis(compiled, [failed])

    assert result.renderer is RendererKind.REFUSE
    assert result.message == failed.message
    assert result.refusal == failed.refusal


def test_a_ranking_by_an_ambiguous_metric_keeps_its_order_after_the_answer() -> None:
    # "highest income" asks which income, then ranks by the one chosen.
    import uuid

    from financial_analyst_agent.conversation import run_conversation_turn, start_thread
    from financial_analyst_agent.runtime import RuntimeKind, recorded_runtime
    from financial_analyst_agent.thread_store import EphemeralThreadStore

    store = EphemeralThreadStore()
    thread = uuid.uuid4().hex
    start_thread(thread, RuntimeKind.RECORDED, store=store)
    asked = run_conversation_turn(
        thread, "Which tech company has the highest income?", recorded_runtime(), store=store
    ).result
    answered = run_conversation_turn(thread, "net income", recorded_runtime(), store=store).result

    assert asked.renderer is RendererKind.CLARIFY
    assert asked.intent is Intent.RANK_AND_LOOKUP
    assert answered.ordered_by == "net_income"
    incomes = [row.value for row in answered.table_rows if row.value is not None]
    assert incomes == sorted(incomes, reverse=True)
