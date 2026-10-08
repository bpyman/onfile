"""Planner red team: words, names and periods the rules planner misread.

Each case is a question from the red-team transcripts; the planner, resolver
or period parser should read it the way the analyst meant it.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from financial_analyst_agent.answer_notes import segment_notes
from financial_analyst_agent.contracts import Intent, TableRow
from financial_analyst_agent.domain.errors import CompanyNotFoundError
from financial_analyst_agent.graph.analysis_spec import AnalysisSpec, NamedPeriodSpec, SpecPatch
from financial_analyst_agent.graph.spec_turn import plan_to_spec_patch
from financial_analyst_agent.period_selection import read
from financial_analyst_agent.presentation import overview_headline
from financial_analyst_agent.ranking import SnapshotRanking
from financial_analyst_agent.request_wording import change_asked
from financial_analyst_agent.rules_planner import DemoCompleter, issuer_index
from financial_analyst_agent.services.metric_catalog import resolve_metric_phrase


def _live() -> DemoCompleter:
    return DemoCompleter(issuer_index())


def _found(question: str) -> list[str]:
    return [mention.query for mention in issuer_index().find(question)]


# C1: words read as tickers


@pytest.mark.parametrize(
    ("question", "companies"),
    [
        ("WHAT IS NVIDIA NET MARGIN NOW?", ["NVDA"]),
        ("WHAT IS NVIDIA NET MARGIN FOR THE LAST 4 QUARTERS", ["NVDA"]),
        ("HOW IS MICROSOFT DOING SO FAR?", ["Microsoft"]),
        ("Apple SGA", ["Apple"]),
        ("Apple ARR and NI", ["Apple"]),
        ("Apple GP, AR and AP", ["Apple"]),
        ("Apple revenue in the UK", ["Apple"]),
        ("IMO Apple is doing well", ["Apple"]),
        ("What ARE Apple's margins", ["Apple"]),
    ],
)
def test_words_and_acronyms_are_not_tickers(question: str, companies: list[str]) -> None:
    assert _found(question) == companies


@pytest.mark.parametrize(
    ("question", "companies"),
    [
        ("CRM revenue", ["CRM"]),
        ("CRM REVENUE", ["CRM"]),
        ("NOW revenue", ["NOW"]),
        ("$NOW revenue", ["NOW"]),
        ("F revenue", ["F"]),
        ("$F net income", ["F"]),
        ("Compare $NOW and Apple", ["NOW", "Apple"]),
    ],
)
def test_real_ticker_questions_still_work(question: str, companies: list[str]) -> None:
    assert _found(question) == companies


def test_a_bare_ticker_beside_a_named_company_is_said() -> None:
    plan = _live().complete("Compare Apple and CRM revenue")

    assert plan.companies == ("Apple", "CRM")
    assert any("for “CRM”" in note for note in plan.notes)


# H1–H3: resolution


@pytest.mark.parametrize(
    "question", ["J.P. Morgan revenue", "JP Morgan Chase revenue", "J. P. Morgan net income"]
)
def test_jp_morgan_is_jpmorgan(question: str) -> None:
    assert _found(question) == ["JPM"]


@pytest.mark.parametrize(
    "question",
    ["Alphabet Inc Class C revenue", "Alphabet class A revenue", "Alphabet Series C net income"],
)
def test_a_share_class_letter_is_not_a_ticker(question: str) -> None:
    assert _found(question) == ["Google"]


@pytest.mark.parametrize("ticker", ["MAIN", "GAIN", "CHEV", "GOLDM"])
def test_a_ticker_outside_the_snapshot_never_prefix_matches_a_member(ticker: str) -> None:
    with pytest.raises(CompanyNotFoundError):
        SnapshotRanking.from_path().lookup_member(ticker)


def test_a_full_name_still_resolves() -> None:
    assert SnapshotRanking.from_path().lookup_member("Microsoft").ticker == "MSFT"


# H4, H5, H8: no junk companies or industries


@pytest.mark.parametrize(
    "question",
    ["What is the EBITDA?", "gross margin", "what was the revenue?", "what is the market cap?"],
)
def test_a_question_naming_no_company_names_none(question: str) -> None:
    patch = plan_to_spec_patch(DemoCompleter().complete(question))

    assert patch.add_companies == ()


@pytest.mark.parametrize(
    ("question", "industry"),
    [
        ("Where does Apple rank in tech by revenue?", "tech"),
        ("How does Apple rank among tech companies?", "tech"),
        ("top 5 in banking", "banking"),
        ("top 5 companies within healthcare", "healthcare"),
    ],
)
def test_prepositions_are_not_part_of_an_industry(question: str, industry: str) -> None:
    plan = DemoCompleter().complete(question)

    assert plan.industry == industry


# M1: one company and a rank word


@pytest.mark.parametrize(
    ("question", "metric"),
    [
        ("Apple top line", "revenue"),
        ("Apple top line growth", "revenue"),
        ("Apple revenue ranked", "revenue"),
        ("What is Apple's biggest expense?", None),
    ],
)
def test_one_company_with_a_rank_word_is_a_lookup(question: str, metric: str | None) -> None:
    plan = DemoCompleter().complete(question)

    assert plan.intent is Intent.LOOKUP
    assert plan.company == "Apple"
    if metric is not None:
        assert plan.metric == metric


def test_a_ranking_beside_a_company_says_the_company_was_not_answered() -> None:
    plan = DemoCompleter().complete("Top 5 banks and Apple revenue")

    assert plan.intent is Intent.RANK_AND_LOOKUP
    assert any("Apple" in note for note in plan.notes)


def test_rank_named_companies_orders_them() -> None:
    plan = DemoCompleter().complete("Rank Apple, Microsoft and Nvidia by revenue")

    assert plan.intent is Intent.COMPARE
    assert "order_by_metric" in plan_to_spec_patch(plan).add_operations


# M3, M4: metric phrasings


@pytest.mark.parametrize(
    ("question", "metrics"),
    [
        (
            "Compare the margins of Apple and Microsoft",
            ("gross_margin", "operating_margin", "net_margin"),
        ),
        ("Apple depreciation", ("depreciation_amortization",)),
        ("Apple's PE", ("pe_ratio",)),
        ("Apple PE ratio", ("pe_ratio",)),
        ("What's Apple worth?", ("market_cap",)),
        ("Apple valuation", ("market_cap",)),
        ("How much does Apple spend on research?", ("research_and_development",)),
        ("Apple research spending", ("research_and_development",)),
        ("Apple turnover", ("revenue",)),
        ("Apple top line", ("revenue",)),
        ("How much did Apple earn?", ("net_income",)),
    ],
)
def test_everyday_metric_wording(question: str, metrics: tuple[str, ...]) -> None:
    resolved = resolve_metric_phrase(question)

    assert resolved.kind == "unique"
    assert resolved.metrics == metrics


def test_money_made_asks_which_amount() -> None:
    resolved = resolve_metric_phrase("How much money did Apple make last quarter?")

    assert resolved.kind == "ambiguous"
    assert set(resolved.candidates) == {"revenue", "net_income"}


@pytest.mark.parametrize(
    ("question", "term"),
    [
        ("Apple happiness index", "happiness index"),
        ("Nvidia guidance", "guidance"),
        ("Apple costs", "costs"),
    ],
)
def test_a_short_question_names_its_unknown_word(question: str, term: str) -> None:
    plan = DemoCompleter().complete(question)

    assert plan.metric == term


# M6: typos


@pytest.mark.parametrize(
    ("question", "ticker"),
    [
        ("Nvidea net income", "NVDA"),
        ("Telsa revenue", "Tesla"),
        ("Appel revenue", "Apple"),
        ("Oracel revenue", "ORCL"),
        ("Microsfot revenue", "Microsoft"),
    ],
)
def test_one_edit_typos_are_corrected(question: str, ticker: str) -> None:
    corrected = issuer_index().correct(question)

    assert [mention.query for mention in corrected] == [ticker]


@pytest.mark.parametrize(
    "question",
    [
        "Apple sales growth",
        "show the prices",
        "costs and taxes",
        "which quarter grew",
        "total cash flows",
        "debts and loans",
        "share counts",
        "their income",
        "these banks",
        "assets under management",
        "leases and rents",
        "about Spain trade",
        "rates and yield",
    ],
)
def test_ordinary_words_are_not_typos(question: str) -> None:
    assert issuer_index().correct(question, ignore=frozenset({"apple"})) == []


# M10, M11: periods


def test_a_bare_year_is_that_fiscal_year() -> None:
    message = "Apple revenue 2024"
    patch = read(message).bind(SpecPatch(mode="replace"), change_asked(message))

    assert patch.set_periods is not None
    assert patch.set_periods.named == (NamedPeriodSpec(year=2024),)


def test_two_years_compare_both() -> None:
    message = "Apple revenue 2025 vs 2024"
    patch = read(message).bind(SpecPatch(mode="replace"), change_asked(message))

    assert patch.set_periods is not None
    assert patch.set_periods.named == (NamedPeriodSpec(year=2025), NamedPeriodSpec(year=2024))


@pytest.mark.parametrize(
    ("message", "count"),
    [
        ("Apple revenue in the last 3 years", 12),
        ("Apple revenue past 2 years", 8),
        ("Apple revenue over the last two years", 8),
    ],
)
def test_last_n_years_is_four_n_quarters(message: str, count: int) -> None:
    patch = read(message).bind(SpecPatch(mode="replace"), change_asked(message))

    assert patch.set_periods is not None
    assert patch.set_periods.kind == "last_n_quarters"
    assert patch.set_periods.count == count


@pytest.mark.parametrize(
    ("message", "period"),
    [
        (
            "Apple revenue september quarter 2025",
            NamedPeriodSpec(year=2025, quarter=3, calendar=True),
        ),
        (
            "Apple revenue December 2025 quarter",
            NamedPeriodSpec(year=2025, quarter=4, calendar=True),
        ),
        (
            "Apple revenue for the quarter ended June 2026",
            NamedPeriodSpec(year=2026, quarter=2, calendar=True),
        ),
    ],
)
def test_a_month_named_quarter_is_that_calendar_quarter(
    message: str, period: NamedPeriodSpec
) -> None:
    patch = read(message).bind(SpecPatch(mode="replace"), change_asked(message))

    assert patch.set_periods is not None
    assert patch.set_periods.named == (period,)


def test_quarter_over_quarter_is_a_sequential_window() -> None:
    message = "Apple revenue quarter over quarter"
    patch = read(message).bind(SpecPatch(mode="replace"), change_asked(message))

    assert patch.set_periods is not None and patch.set_periods.kind == "last_n_quarters"
    assert "across_periods" in patch.add_operations
    assert "year_over_year" not in patch.add_operations


def test_last_n_quarters_year_over_year_shows_the_n_quarters_asked() -> None:
    message = "Apple revenue last 4 quarters yoy"
    patch = read(message).bind(SpecPatch(mode="replace"), change_asked(message))

    # Each quarter's base is the comparative its own filing reports (ADR 0009).
    assert patch.set_periods is not None and patch.set_periods.count == 4
    assert "year_over_year" in patch.add_operations


@pytest.mark.parametrize(
    "wording",
    [
        "since 2024",
        "since the start of 2024",
        "since the beginning of 2024",
        "since early 2024",
    ],
)
def test_since_a_year_is_not_a_named_year(wording: str) -> None:
    from financial_analyst_agent.period_selection import read

    message = f"Apple revenue {wording}"
    patch = read(message).bind(SpecPatch(mode="replace"), change_asked(message))

    # Every quarter since that calendar year began, not the fiscal year it names.
    assert read(message).named == ()
    assert patch.set_periods is not None and patch.set_periods.kind == "last_n_quarters"


def test_latest_after_year_over_year_drops_the_change() -> None:
    message = "latest"
    patch = read(message).bind(SpecPatch(mode="extend"), change_asked(message))

    assert "year_over_year" in patch.remove_operations


# M15: nicknames


@pytest.mark.parametrize(
    ("question", "ticker"),
    [
        ("SpaceX revenue", "SPCX"),
        ("Space X net income", "SPCX"),
        ("Google revenue", "Google"),
        ("Facebook revenue", "META"),
        ("Walmart revenue", "WMT"),
        ("Exxon revenue", "XOM"),
        ("Chase net income", "JPM"),
        ("Mastercard revenue", "MA"),
        ("Coca-Cola revenue", "KO"),
        ("McDonalds revenue", "MCD"),
        ("Pepsi revenue", "PEP"),
        ("Berkshire revenue", "BRK-B"),
        ("Netflix revenue", "NFLX"),
        ("Salesforce revenue", "CRM"),
        ("Caterpillar revenue", "CAT"),
    ],
)
def test_everyday_company_names(question: str, ticker: str) -> None:
    assert _found(question) == [ticker]


# Lows


def test_two_classes_of_one_company_are_said_once() -> None:
    plan = _live().complete("GOOG vs GOOGL revenue")

    assert plan_to_spec_patch(plan).add_companies == ("Google",)
    assert any("GOOG" in note and "GOOGL" in note for note in plan.notes)


def test_the_other_share_class_finds_the_company() -> None:
    assert _found("BRK.A revenue") == ["BRK-B"]


@pytest.mark.parametrize(
    ("question", "limit", "noted"),
    [
        ("top 0 banks", 10, True),
        ("top -5 banks", 5, True),
        ("top 5.5 banks", 5, True),
        ("top 5 banks", 5, False),
    ],
)
def test_a_ranking_count_that_is_not_a_count(question: str, limit: int, noted: bool) -> None:
    plan = DemoCompleter().complete(question)

    assert plan.industry == "banks"
    assert plan.limit == limit
    assert bool(getattr(plan, "notes", ())) is noted


def test_which_bank_names_banks() -> None:
    plan = DemoCompleter().complete("which bank has the highest net margin?")

    assert plan.industry == "banks"


def test_markdown_does_not_hide_a_metric() -> None:
    plan = DemoCompleter().complete("**Apple** _revenue_ [click](http://evil.com)")

    assert plan.company == "Apple"
    assert plan.metric == "revenue"


def test_a_net_loss_reads_as_a_loss() -> None:
    def row(metric: str, value: str) -> TableRow:
        return TableRow(
            company_name="Space Exploration Technologies Corp.",
            ticker="SPCX",
            cik="0001181412",
            metric=metric,
            value=Decimal(value),
            end_date=date(2026, 6, 30),
        )

    headline = overview_headline([row("revenue", "7810000000"), row("net_income", "-541000000")])

    assert headline is not None
    assert "a net loss of $541.00 M" in headline
    assert "-$" not in headline


def test_a_fund_overview_is_one_refusal() -> None:
    from financial_analyst_agent.contracts import (
        NOT_OPERATING_COMPANY,
        Refusal,
        RendererKind,
        TurnResult,
    )
    from financial_analyst_agent.graph.spec_turn import _one_company_failure

    rows = [
        TableRow(company_name="SPY", ticker="", cik="", metric=metric, reason=NOT_OPERATING_COMPANY)
        for metric in ("revenue", "net_income", "gross_margin")
    ]
    merged = TurnResult(
        intent=Intent.LOOKUP,
        tool_traces=[],
        renderer=RendererKind.TABLE,
        table_rows=rows,
        message="SPY is not an operating company",
        refusal=Refusal(code="ineligible_issuer"),
    )

    result = _one_company_failure(merged, [merged])

    assert result.renderer is RendererKind.REFUSE
    assert result.message is not None and "not an operating company" in result.message


def test_initials_do_not_split_a_question() -> None:
    plan = _live().complete("J.P. Morgan revenue")

    assert plan.company == "JPM"
    assert plan.notes == ()


def test_a_segment_note_keeps_the_analysts_spelling() -> None:
    question = "Amazon Web Services revenue"
    plan = _live().complete(question)

    assert plan.metric == "revenue"
    # The note is the shared reading's, whichever planner planned.
    (note,) = segment_notes(question, AnalysisSpec(metrics=("revenue",)))
    assert "“Amazon Web Services”" in note
