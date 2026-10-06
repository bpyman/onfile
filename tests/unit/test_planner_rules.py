"""The rules planner reads everyday questions; the window guides and suggests."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

import pytest

from financial_analyst_agent.answer_notes import capped_ranking_notes
from financial_analyst_agent.contracts import Intent, RendererKind, TableRow, TurnResult
from financial_analyst_agent.conversation import run_conversation_turn, start_thread
from financial_analyst_agent.domain.errors import UnknownIndustryError
from financial_analyst_agent.filing_change import _read_filings, _year_apart_quarterlies
from financial_analyst_agent.graph.analysis_spec import (
    AnalysisSpec,
    PeriodSelection,
    RankedSet,
    ResolvedCompany,
    SpecPatch,
    apply_patch,
    resolve_spec,
)
from financial_analyst_agent.graph.spec_turn import _order_by_metric, plan_to_spec_patch
from financial_analyst_agent.guide import guide_reply, short_name, suggest_follow_ups
from financial_analyst_agent.issuer_index import IssuerIndex
from financial_analyst_agent.presentation import present_turn
from financial_analyst_agent.ranking import SnapshotRanking
from financial_analyst_agent.request_wording import (
    OVERVIEW_METRICS,
    bind_metrics_from_message,
    bind_periods_from_message,
    refine_patch_from_message,
)
from financial_analyst_agent.rules_planner import DemoCompleter, issuer_index
from financial_analyst_agent.runtime import RuntimeKind, recorded_runtime
from financial_analyst_agent.thread_store import EphemeralThreadStore
from financial_analyst_agent.universe import (
    SnapshotGroups,
    load_universe_snapshot,
    resolve_industry_group,
)


def _live() -> DemoCompleter:
    return DemoCompleter(issuer_index())


def test_live_index_names_companies_by_name_ticker_and_first_word() -> None:
    index = issuer_index()

    def found(question: str) -> list[str]:
        return [mention.query for mention in index.find(question)]

    assert found("What was Costco's revenue?") == ["COST"]
    assert found("coca-cola vs pepsico net income") == ["KO", "PEP"]
    assert found("Compare $NFLX and DIS") == ["NFLX", "DIS"]
    assert found("Home Depot versus Lowes") == ["HD", "LOW"]
    # Generic first words and lowercase words are not companies.
    assert found("what are the top 5 general companies") == []
    assert found("I want AI revenue") == []


def test_misspelt_company_is_corrected_and_said() -> None:
    plan = _live().complete("microsft revenue")

    assert plan.company == "Microsoft"
    assert plan.notes == ("Showing Microsoft for “microsft”.",)


@pytest.mark.parametrize(
    "question",
    [
        "how does inflation affect revenue",
        "every company's margins",
        "being profitable",
        "what do the figures say",
        "trade policy risk",
    ],
)
def test_ordinary_english_is_not_a_misspelt_company(question: str) -> None:
    assert issuer_index().correct(question) == []


def test_misspelt_names_still_correct_beside_common_words() -> None:
    corrected = issuer_index().correct("how does inflation affect nvida revenue")

    assert [mention.query for mention in corrected] == ["NVDA"]


def test_a_ticker_that_is_also_an_alias_is_one_company() -> None:
    plan = DemoCompleter().complete("AAPL")

    assert plan.intent is Intent.LOOKUP


def test_which_is_bigger_compares_market_cap_and_revenue() -> None:
    plan = DemoCompleter().complete("Which is bigger, Apple or Microsoft?")
    patch = SpecPatch(mode="replace", add_companies=tuple(plan.companies), add_metrics=("unknown",))

    bound, refusal = bind_metrics_from_message(patch, "Which is bigger, Apple or Microsoft?")

    assert plan.intent is Intent.COMPARE
    assert refusal is None
    assert bound.add_metrics == ("market_cap", "revenue")


@pytest.mark.parametrize(
    "question",
    [
        "Nvidia",
        "How is Nvidia doing?",
        "Tell me about Nvidia",
        "Give me the rundown on how Nvidia is performing",
        "How is Nvidia performing?",
        "How has Nvidia been performing?",
        "the rundown on Nvidia",
        "a quick read on Nvidia",
        "a quick look at Nvidia",
        "Nvidia's performance",
        "Nvidia's performance over the last 4 quarters",
    ],
)
def test_a_company_on_its_own_gets_an_overview(question: str) -> None:
    patch = SpecPatch(mode="replace", add_companies=("NVDA",), add_metrics=("unknown",))

    bound, refusal = bind_metrics_from_message(patch, question)

    assert refusal is None
    assert bound.add_metrics == OVERVIEW_METRICS


@pytest.mark.parametrize("guessed", ["unknown", "stock performance"])
def test_a_measure_the_catalog_lacks_is_not_an_overview(guessed: str) -> None:
    # "Performance" is an overview word, but "stock performance" is a measure the
    # catalog lacks by name: refused, whichever planner proposed the metric.
    patch = SpecPatch(mode="replace", add_companies=("AAPL",), add_metrics=(guessed,))

    _bound, refusal = bind_metrics_from_message(patch, "Apple's stock performance")

    assert refusal is not None and refusal.renderer is RendererKind.REFUSE
    assert "'stock performance'" in (refusal.message or "")


def test_the_rules_planner_reads_overview_words_as_no_metric() -> None:
    # "rundown" and "performing" are not the word the catalog lacks: the plan
    # names no metric, and the shared reading gives the overview.
    planner = _live()

    for question in (
        "Give me the rundown on how Wells Fargo is performing",
        "How has Wells Fargo been performing?",
        "a quick read on Wells Fargo",
    ):
        plan = planner.complete(question)
        assert plan.intent is Intent.LOOKUP, question
        assert plan.metric == "unknown", question
        patch, refusal = bind_metrics_from_message(
            plan_to_spec_patch(plan), question, intent=plan.intent
        )
        assert refusal is None, question
        assert patch.add_metrics == OVERVIEW_METRICS, question


def test_growth_wording_asks_for_year_over_year() -> None:
    patch = bind_periods_from_message(
        SpecPatch(mode="replace"), "How has Tesla's revenue changed over the last year?"
    )

    assert patch.set_periods is not None and patch.set_periods.count == 5
    assert "across_periods" in patch.add_operations
    # Growth means year over year unless the analyst says sequential (ADR 0010).
    assert "year_over_year" in patch.add_operations


def test_rankings_read_industries_and_limits() -> None:
    plan = DemoCompleter().complete("top 5 semiconductor companies by revenue")
    banks = DemoCompleter().complete("biggest banks")

    assert (plan.intent, plan.industry, plan.limit, plan.metric) == (
        Intent.RANK_AND_LOOKUP,
        "semiconductor",
        5,
        "revenue",
    )
    assert (banks.intent, banks.industry) == (Intent.RANK, "banks")


def test_industry_words_name_industries_inside_a_sector() -> None:
    groups = SnapshotGroups.of(load_universe_snapshot())

    semis = resolve_industry_group("semiconductor", groups)
    software = resolve_industry_group("software companies", groups)
    regional = resolve_industry_group("regional banks", groups)
    tech = resolve_industry_group("tech", groups)

    assert semis is not None and semis.industries == {"Semiconductors"}
    assert software is not None and software.label == "Software"
    assert regional is not None and regional.industries == {"Banks - Regional"}
    assert tech is not None and tech.sector == "Technology"
    assert resolve_industry_group("spaceships", groups) is None


def test_a_ranking_by_a_metric_is_ordered_by_it() -> None:
    by = _live().complete("top 5 healthcare companies by revenue")
    their = _live().complete("biggest banks and their net income")
    cap = _live().complete("top 5 banks by market cap")

    assert by.order_by_metric is True
    assert their.order_by_metric is False
    assert cap.order_by_metric is False
    assert plan_to_spec_patch(by).add_operations == ("rank", "order_by_metric")
    assert plan_to_spec_patch(their).add_operations == ("rank",)


def test_ordering_by_a_metric_reranks_the_members() -> None:
    def row(rank: int, ticker: str, value: str | None, end: date) -> TableRow:
        return TableRow(
            company_name=ticker,
            ticker=ticker,
            cik=f"000000000{rank}",
            metric="revenue",
            rank=rank,
            value=Decimal(value) if value is not None else None,
            end_date=end,
        )

    june = date(2026, 6, 30)
    result = TurnResult(
        intent=Intent.RANK_AND_LOOKUP,
        renderer=RendererKind.TABLE,
        tool_traces=[],
        table_rows=[
            row(1, "LLY", "22", june),
            row(2, "JNJ", "25", june),
            row(3, "XYZ", None, june),
            row(4, "UNH", "112", june),
        ],
    )

    ordered = _order_by_metric(result, "revenue")
    presented = present_turn(ordered)

    assert [(r.rank, r.ticker) for r in ordered.table_rows] == [
        (1, "UNH"),
        (2, "JNJ"),
        (3, "LLY"),
        (4, "XYZ"),
    ]
    assert ordered.ordered_by == "revenue"
    assert any(banner.startswith("Ordered by revenue.") for banner in presented.banners)
    assert presented.chart is not None
    assert presented.chart.caption.startswith("Ordered by revenue among the largest by market cap")


def test_a_ranking_lists_at_most_25_companies() -> None:
    ranking = SnapshotRanking(load_universe_snapshot())
    patch = SpecPatch(mode="replace", ranked_request=("tech", 1000))

    spec = resolve_spec(apply_patch(None, patch), ranking=ranking)

    assert spec.constituents is not None
    assert len(spec.constituents.members) == spec.constituents.limit == 25
    assert capped_ranking_notes(patch) == [
        "A ranking lists at most 25 companies, so this shows the top 25 rather than 1000."
    ]
    assert capped_ranking_notes(SpecPatch(mode="replace", ranked_request=("tech", 5))) == []


def test_gics_sector_names_and_common_industry_words_resolve() -> None:
    groups = SnapshotGroups.of(load_universe_snapshot())

    staples = resolve_industry_group("consumer staples", groups)
    payments = resolve_industry_group("payments companies", groups)
    hotels = resolve_industry_group("hotels", groups)
    oil = resolve_industry_group("oil & gas", groups)
    healthcare = resolve_industry_group("healthcare", groups)

    assert staples is not None and staples.sector == "Consumer Defensive"
    assert payments is not None and payments.industries == {"Financial - Credit Services"}
    assert hotels is not None and "Travel Lodging" in hotels.industries
    assert oil is not None and len(oil.industries) > 1
    assert all(name.startswith("Oil & Gas") for name in oil.industries)
    assert healthcare is not None and healthcare.sector == "Healthcare"
    for word in ("software", "telecom", "restaurants"):
        assert resolve_industry_group(word, groups) is not None, word


def test_oil_and_gas_is_one_industry_in_a_ranking() -> None:
    plan = _live().complete("top 5 oil and gas companies by revenue")
    both = _live().complete("biggest banks and their net income")

    assert plan.industry == "oil & gas"
    assert both.industry == "banks"


def test_unknown_industry_names_the_snapshot_sectors() -> None:
    snapshot = load_universe_snapshot()
    with pytest.raises(UnknownIndustryError) as raised:
        SnapshotRanking(snapshot).rank_companies("spaceships", 5)
    result = TurnResult(
        intent=Intent.RANK,
        renderer=RendererKind.REFUSE,
        message=str(raised.value),
        tool_traces=[],
    )

    message = present_turn(result).message or ""

    assert "“spaceships”" in message
    assert "Healthcare" in message and "Technology" in message
    assert "finance" not in message


def _spec(*queries: str, metrics: tuple[str, ...] = ("revenue",)) -> AnalysisSpec:
    return AnalysisSpec(
        companies=tuple(
            ResolvedCompany(cik="", name=query, ticker=query, query=query) for query in queries
        ),
        metrics=metrics,
    )


def test_short_follow_ups_lean_on_the_current_analysis() -> None:
    planner = DemoCompleter()
    spec = _spec("MSFT")

    add_metric = planner.complete("and net margin", current_spec=spec)
    # The planner proposes the metric; the shared edit reading puts it in
    # revenue's place, for either planner (request_wording).
    swap_metric = refine_patch_from_message(
        planner.complete("what about net income?", current_spec=spec),
        "what about net income?",
        spec,
        index=planner.index,
    )
    swap_company = planner.complete("what about Apple?", current_spec=spec)
    add_company = planner.complete("and Nvidia", current_spec=spec)

    assert add_metric == SpecPatch(mode="extend", add_metrics=("net_margin",))
    assert (swap_metric.mode, swap_metric.add_metrics, swap_metric.remove_metrics) == (
        "extend",
        ("net_income",),
        ("revenue",),
    )
    assert swap_company == SpecPatch(
        mode="extend", remove_companies=("MSFT",), add_companies=("Apple",)
    )
    assert add_company == SpecPatch(mode="extend", add_companies=("NVDA",))


def test_which_one_after_a_swap_compares_the_two_companies() -> None:
    swapped = resolve_spec(
        apply_patch(
            _spec("NVDA"),
            SpecPatch(mode="extend", remove_companies=("NVDA",), add_companies=("AMD",)),
        )
    )
    planner = DemoCompleter()

    which = planner.complete("which one is more profitable", current_spec=swapped)
    only = planner.complete("is it profitable", current_spec=swapped)
    kept = resolve_spec(apply_patch(swapped, SpecPatch(mode="extend", add_metrics=("capex",))))

    assert swapped.earlier_companies == ("NVDA",)
    assert which == SpecPatch(
        mode="extend", add_companies=("NVDA",), add_metrics=("net_income", "net_margin")
    )
    assert only.add_companies == ()
    assert kept.earlier_companies == ("NVDA",)


def test_compare_without_a_metric_is_an_overview() -> None:
    planner = _live()

    for question in ("Compare Nvidia and AMD", "how does Nvidia stack up against AMD?"):
        plan = planner.complete(question)
        patch, refusal = bind_metrics_from_message(
            plan_to_spec_patch(plan), question, intent=plan.intent
        )
        assert refusal is None, question
        assert patch.add_metrics == OVERVIEW_METRICS, question
    unknown = planner.complete("compare apple and microsoft roa")
    _patch, refusal = bind_metrics_from_message(
        plan_to_spec_patch(unknown), "compare apple and microsoft roa", intent=unknown.intent
    )
    assert refusal is not None and refusal.renderer is RendererKind.REFUSE


def test_top_n_narrows_a_ranking_and_a_new_ranking_is_not_an_edit() -> None:
    planner = DemoCompleter()
    ranked = AnalysisSpec(
        constituents=RankedSet(industry="banks", limit=10, members=()), metrics=("revenue",)
    )

    narrowed = planner.complete("only the top 3", current_spec=ranked)
    fresh = planner.complete("largest pharma companies by net income", current_spec=ranked)

    assert narrowed == SpecPatch(mode="extend", ranked_request=("banks", 3))
    assert fresh.intent is Intent.RANK_AND_LOOKUP and fresh.industry == "pharma"


def test_filing_change_without_accessions_is_recognized_for_any_company() -> None:
    plan = DemoCompleter().complete("What changed in Apple's latest 10-Q?")

    assert plan.intent is Intent.FILING_CHANGE
    assert plan.company == "Apple"
    assert plan.section == "mda and risk_factors"


def test_year_apart_pair_prefers_the_same_quarter() -> None:
    recent = {
        "accessionNumber": ["n", "k", "p", "y"],
        "form": ["10-Q", "10-K", "10-Q", "10-Q"],
        "reportDate": ["2026-03-31", "2025-06-30", "2025-12-31", "2025-03-31"],
        "primaryDocument": ["n.htm", "k.htm", "p.htm", "y.htm"],
    }

    assert _year_apart_quarterlies(_read_filings(recent)) == ("y", "n")


def test_guide_replies_answer_help_greetings_advice_and_why() -> None:
    index = IssuerIndex.build([], [("apple", "Apple")])
    spec = _spec("Tesla")

    hello = guide_reply("hi!", None)
    advice = guide_reply("Is Apple a good buy?", None, index)
    why = guide_reply("why?", spec)

    assert hello is not None and hello.guide and hello.suggestions
    assert advice is not None and "investment advice" in (advice.message or "")
    assert advice.suggestions[0] == "How is Apple doing?"
    assert why is not None and why.suggestions == ["What changed in Tesla's latest 10-Q?"]
    assert guide_reply("What was Apple's revenue?", None, index) is None
    assert present_turn(hello).message_tone == "info"
    assert present_turn(hello).intent_label == "Guide"


def test_suggestions_offer_a_window_a_peer_and_a_metric() -> None:
    ranking = SnapshotRanking.from_path()
    nvidia = ResolvedCompany(
        cik="0001045810", name="NVIDIA Corporation", ticker="NVDA", query="NVDA"
    )
    spec = AnalysisSpec(companies=(nvidia,), metrics=("revenue",))
    result = TurnResult(intent=Intent.LOOKUP, renderer=RendererKind.TABLE, tool_traces=[])

    ideas = suggest_follow_ups(result, spec, ranking)

    assert ideas[0] == "show year-over-year"
    assert ideas[1].startswith("add ") and ideas[1] != "add NVIDIA"
    assert ideas[2] == "add net margin"
    ranked = AnalysisSpec(
        constituents=RankedSet(industry="banks", limit=10, members=()), metrics=()
    )
    assert suggest_follow_ups(result, ranked, ranking) == ["show their revenue", "only the top 5"]


def test_short_names_drop_legal_suffixes() -> None:
    assert short_name("NVIDIA Corporation") == "NVIDIA"
    assert short_name("Eli Lilly and Company") == "Eli Lilly"
    assert short_name("JPMorgan Chase & Co.") == "JPMorgan Chase"
    assert short_name("The Goldman Sachs Group, Inc.") == "Goldman Sachs"
    assert short_name("Wells Fargo & Company") == "Wells Fargo"


def test_several_metrics_for_one_quarter_read_across_one_row() -> None:
    rows = [
        TableRow(
            company_name="Apple Inc.",
            ticker="AAPL",
            cik="0000320193",
            metric=metric,
            value=Decimal(value),
            start_date=date(2026, 3, 29),
            end_date=date(2026, 6, 27),
        )
        for metric, value in (("revenue", "109420000000"), ("net_margin", "0.272"))
    ]
    result = TurnResult(
        intent=Intent.LOOKUP, renderer=RendererKind.TABLE, table_rows=rows, tool_traces=[]
    )

    table = present_turn(result).table

    assert table is not None
    assert table.keys == ("company_name", "ticker", "value:revenue", "value:net_margin", "end_date")
    assert table.rows == (("Apple Inc.", "AAPL", "$109.42 B", "27.2%", "Jun 27, 2026"),)


def test_a_window_of_several_metrics_reads_one_row_per_quarter_and_change() -> None:
    def row(metric: str, end: date, value: str, comparison: str | None = None) -> TableRow:
        return TableRow(
            company_name="Apple Inc.",
            ticker="AAPL",
            cik="0000320193",
            metric=metric,
            value=Decimal(value),
            end_date=end,
            comparison=comparison,  # type: ignore[arg-type]
        )

    new, old = date(2026, 6, 27), date(2025, 6, 28)
    rows = [
        row("revenue", new, "110"),
        row("net_margin", new, "0.27"),
        row("revenue", old, "100"),
        row("net_margin", old, "0.25"),
        row("revenue", new, "10", "year_over_year"),
        row("net_margin", new, "0.02", "year_over_year"),
    ]
    result = TurnResult(
        intent=Intent.LOOKUP, renderer=RendererKind.TABLE, table_rows=rows, tool_traces=[]
    )

    table = present_turn(result).table

    assert table is not None
    # One row per quarter, each change in a column beside its level.
    assert len(table.rows) == 2
    assert table.headers[4:6] == ("Revenue, YoY", "Net margin, YoY")
    assert table.rows[0][4:6] == ("+$10", "+2.0 pts")
    assert table.rows[1][4:6] == ("", "")


@pytest.mark.parametrize(
    ("wording", "count"),
    [
        ("last 0 quarters", 1),
        ("last 000 quarters", 1),
        ("last 12 quarters", 12),
        ("last 99999999999999999999 quarters", 40),
    ],
)
def test_quarter_window_is_kept_between_one_and_ten_years(wording: str, count: int) -> None:
    patch = bind_periods_from_message(SpecPatch(mode="replace"), f"Apple revenue {wording}")

    assert patch.set_periods == PeriodSelection(kind="last_n_quarters", count=count)


@pytest.mark.parametrize(("asked", "count"), [(0, 1), (-3, 1), (4, 4), (10_000, 40)])
def test_llm_quarter_window_is_clamped(asked: int, count: int) -> None:
    from financial_analyst_agent.planner import _SpecPatchAction

    action = _SpecPatchAction(
        intent="spec_patch", period_kind="last_n_quarters", period_count=asked
    )

    periods = action.to_spec_patch().set_periods
    assert periods is not None
    assert (periods.kind, periods.count) == ("last_n_quarters", count)


@pytest.mark.parametrize(
    ("question", "companies"),
    [
        ("BRK.B revenue", ["BRK-B"]),
        ("BRK-B revenue", ["BRK-B"]),
        ("BF.B net income", ["BF-B"]),
        ("T-Mobile revenue", ["TMUS"]),
        ("U.S. Bancorp net income", ["USB"]),
        ("us bancorp net income", ["USB"]),
        ("O'Reilly revenue", ["ORLY"]),
        ("johnson controls revenue", ["JCI"]),
        ("general electric revenue", ["GE"]),
        ("southern company revenue", ["SO"]),
        ("Bank of New York revenue", ["BNY"]),
        ("Apple NET income", ["Apple"]),
        ("MSFT NET MARGIN", ["Microsoft"]),
        ("IT spending at Apple", ["Apple"]),
        ("Cloudflare vs NET", ["NET"]),
        ("P/E of S&P companies", []),
    ],
)
def test_share_classes_short_names_and_metric_words(question: str, companies: list[str]) -> None:
    assert [mention.query for mention in issuer_index().find(question)] == companies


def test_follow_ups_that_set_a_company_beside_the_current_one() -> None:
    planner = DemoCompleter()
    spec = _spec("AAPL")

    assert planner.complete("and msft revenue", current_spec=spec) == SpecPatch(
        mode="extend", add_companies=("Microsoft",)
    )
    assert planner.complete("and msft net income", current_spec=spec) == SpecPatch(
        mode="extend", add_companies=("Microsoft",), add_metrics=("net_income",)
    )
    for question in ("compare it to Google", "vs Google", "how does it compare to Google?"):
        assert planner.complete(question, current_spec=spec) == SpecPatch(
            mode="extend", add_companies=("Google",)
        )
    # A fresh comparison is still a new question.
    assert not isinstance(planner.complete("Nvidia vs AMD", current_spec=spec), SpecPatch)


def test_compare_them_uses_the_companies_already_named() -> None:
    swapped = resolve_spec(
        apply_patch(
            _spec("NVDA"),
            SpecPatch(mode="extend", remove_companies=("NVDA",), add_companies=("AMD",)),
        )
    )
    planner = DemoCompleter()

    assert planner.complete("compare them", current_spec=swapped) == SpecPatch(
        mode="extend", add_companies=("NVDA",)
    )
    assert planner.complete("Compare the two.", current_spec=_spec("NVDA", "AMD")) == SpecPatch(
        mode="extend"
    )


def test_count_words_and_rev_are_read() -> None:
    planner = _live()

    five = planner.complete("top five banks by revenue")
    three = planner.complete("the three biggest semiconductor companies")

    assert (five.industry, five.limit, five.metric) == ("banks", 5, "revenue")
    assert (three.industry, three.limit) == ("semiconductor", 3)
    assert planner.complete("Five Below revenue").company == "FIVE"
    assert planner.complete("Apple rev").metric == "revenue"


def test_a_cik_names_its_company() -> None:
    index = issuer_index()

    assert [m.query for m in index.find("CIK 320193 revenue")] == ["AAPL"]
    assert [m.query for m in index.find("0000789019 net income")] == ["MSFT"]
    assert index.find("revenue of 12345 companies") == []


def test_periods_filings_cannot_answer_are_said() -> None:
    def ask(question: str) -> Any:
        store = EphemeralThreadStore()
        start_thread("t", RuntimeKind.RECORDED, store=store)
        turn = run_conversation_turn("t", question, recorded_runtime(), store=store)
        return present_turn(turn.result)

    month = ask("Apple revenue last month")
    future = ask("Apple revenue for fiscal 2031")

    assert any("not months or weeks" in banner for banner in month.banners)
    assert "not been reported yet" in (future.message or "")


def test_a_list_of_companies_is_bounded_like_a_ranking() -> None:
    from financial_analyst_agent.graph.analysis_spec import validate_spec

    tickers = [f"T{index}" for index in range(26)]

    rejection = validate_spec(_spec(*tickers))

    assert rejection is not None and "at most 25" in rejection.message
    assert validate_spec(_spec(*tickers[:25])) is None


def test_a_reit_is_named_without_its_reit() -> None:
    assert [m.query for m in issuer_index().find("Apple Hospitality revenue")] == ["APLE"]


@pytest.mark.parametrize(
    ("question", "companies"),
    [
        # Georgia Power's own listing, not Power REIT or its parent Southern Co.
        ("Georgia Power revenue", ["GPJA"]),
        ("Power REIT revenue", ["PW"]),
        ("Target revenue", ["TGT"]),
        ("TSMC revenue", ["TSM"]),
        ("SPY revenue", ["SPY"]),
    ],
)
def test_everyday_words_funds_and_nicknames(question: str, companies: list[str]) -> None:
    assert [mention.query for mention in issuer_index().find(question)] == companies


@pytest.mark.parametrize(
    ("question", "companies"),
    [
        ("Ares Capital net income", ["ARCC"]),
        ("Ares Management revenue", ["ARES"]),
        ("Blackstone Secured Lending revenue", ["BXSL"]),
        ("Blackstone revenue", ["BX"]),
    ],
)
def test_a_fund_is_named_without_taking_its_operating_namesake(
    question: str, companies: list[str]
) -> None:
    assert [mention.query for mention in issuer_index().find(question)] == companies


@pytest.mark.parametrize(
    ("question", "companies"),
    [
        # Filers outside the snapshot are named whole, ahead of their words.
        ("Southern California Edison revenue", ["SCE-PM"]),
        ("Consumers Energy net income", ["CMS-PB"]),
        ("Entergy Texas revenue", ["ETI-P"]),
        # The parents and everyday questions are unchanged.
        ("Edison International revenue", ["EIX"]),
        ("Entergy revenue", ["ETR"]),
        ("Southern Company revenue", ["SO"]),
        ("Apple vs Microsoft net income", ["Apple", "Microsoft"]),
    ],
)
def test_a_filer_outside_the_snapshot_is_named_by_its_full_name(
    question: str, companies: list[str]
) -> None:
    assert [mention.query for mention in issuer_index().find(question)] == companies


def test_a_filer_name_never_takes_a_company_word_or_a_metric() -> None:
    from financial_analyst_agent.issuer_index import IssuerIndex

    reserved = frozenset({"revenue", "cash", "flow"})
    index = IssuerIndex.build(
        [],
        [("apple", "Apple")],
        filers=[
            ("ART", "APPLE REVENUE TRUST"),
            ("CFC", "Cash Flow Corp"),
            ("ACM", "Acme"),
            ("XAP", "Apple Inc /DE/"),
            ("CBK", "CONSUMERS BANCORP INC /OH/"),
        ],
        reserved=reserved,
    )

    # A metric word, a one-word name, or a phrase a company holds: not indexed.
    assert index.phrases == {"apple": "Apple", "consumers bancorp": "CBK"}


def test_the_rules_planner_returns_a_frozen_workflow_plan() -> None:
    import pytest
    from pydantic import ValidationError

    from financial_analyst_agent.contracts import Intent, WorkflowPlan

    plan = DemoCompleter().complete("Apple and Microsoft revenue")

    assert isinstance(plan, WorkflowPlan)
    assert (plan.intent, plan.companies, plan.metric) == (
        Intent.COMPARE,
        ("Apple", "Microsoft"),
        "revenue",
    )
    with pytest.raises(ValidationError):
        plan.metric = "net_income"  # type: ignore[misc]
