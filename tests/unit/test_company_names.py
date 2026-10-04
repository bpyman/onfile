"""Company names: one reading for the planner and for spec resolution.

A name resolves the same way wherever it is read: in the question, or in a
company field a planner filled in ("Goldman Sachs", "Merck & Co.", "$TMO").
A name that is also an everyday word ("Target", "Block", "Gap") is a company
only where the question uses it as one. A name several companies share
("Lincoln") is asked about, not guessed.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest

from financial_analyst_agent.contracts import RendererKind, Runtime, WorkflowPlan
from financial_analyst_agent.conversation import run_conversation_turn
from financial_analyst_agent.domain.errors import AmbiguousCompanyError
from financial_analyst_agent.issuer_index import _everyday_words, _ordinary
from financial_analyst_agent.ranking import SnapshotRanking
from financial_analyst_agent.rules_planner import DemoCompleter, issuer_index
from financial_analyst_agent.thread_store import LocalThreadStore
from financial_analyst_agent.universe import load_universe_snapshot


def _ranking() -> SnapshotRanking:
    return SnapshotRanking.from_path(None, issuer_index())


def _found(question: str) -> list[str]:
    return [mention.query for mention in issuer_index().find(question)]


@pytest.mark.parametrize(
    ("company", "ticker"),
    [
        ("Goldman Sachs", "GS"),
        ("The Goldman Sachs Group", "GS"),
        ("Home Depot", "HD"),
        ("Lilly", "LLY"),
        ("Eli Lilly & Company", "LLY"),
        ("BofA", "BAC"),
        ("Johnson and Johnson", "JNJ"),
        ("Merck and Co", "MRK"),
        ("Danaher's", "DHR"),
        ("Oracle's", "ORCL"),
        ("$TMO", "TMO"),
        ("DHR.", "DHR"),
        ("Procter & Gamble", "PG"),
        ("Facebook", "META"),
        ("Coca-Cola", "KO"),
        ("JP Morgan", "JPM"),
        ("NVIDIA Corp.", "NVDA"),
        ("Broadcom Inc.'s", "AVGO"),
        ("Cisco Systems'", "CSCO"),
        ("Take-Two", "TTWO"),
        ("Target", "TGT"),
        ("Block", "XYZ"),
    ],
)
def test_a_company_field_resolves_as_the_planner_reads_it(company: str, ticker: str) -> None:
    assert _ranking().lookup_member(company).ticker == ticker


def test_a_ranking_without_an_index_builds_one_from_its_snapshot() -> None:
    ranking = SnapshotRanking(load_universe_snapshot(None))

    assert ranking.lookup_member("Goldman Sachs").ticker == "GS"


def test_a_shared_name_offers_the_largest_members() -> None:
    with pytest.raises(AmbiguousCompanyError) as raised:
        _ranking().lookup_member("Lincoln")

    tickers = [match["ticker"] for match in raised.value.details["matches"]]
    assert tickers[:2] == ["LECO", "LNC"]
    assert len(tickers) <= 4


@pytest.mark.parametrize(
    ("question", "companies"),
    [
        ("What is Target's revenue?", ["TGT"]),
        ("target revenue last quarter", ["TGT"]),
        ("compare target and walmart revenue", ["TGT", "WMT"]),
        ("Walmart, Target and Costco revenue", ["WMT", "TGT", "COST"]),
        ("how did target do last quarter", ["TGT"]),
        ("revenue for target last quarter", ["TGT"]),
        ("Is Target growing faster than Walmart?", ["TGT", "WMT"]),
        ("what about block?", ["XYZ"]),
        ("Gap revenue", ["GAP"]),
        ("match group revenue", ["MTCH"]),
        ("TARGET REVENUE", ["TGT"]),
        ("Target", ["TGT"]),
    ],
)
def test_an_everyday_word_used_as_a_company_is_one(question: str, companies: list[str]) -> None:
    assert _found(question) == companies


@pytest.mark.parametrize(
    ("question", "companies"),
    [
        ("Nvidia's target margin", ["NVDA"]),
        ("Nvidia target margin", ["NVDA"]),
        ("What is the target margin for Nvidia?", ["NVDA"]),
        ("Is Nvidia hitting its target?", ["NVDA"]),
        ("price target for Nvidia", ["NVDA"]),
        ("a target of 30% for Apple", ["Apple"]),
        ("what's the gap between Apple and Microsoft revenue", ["Apple", "Microsoft"]),
        ("show me apple revenue here", ["Apple"]),
        ("take a look at Apple revenue", ["Apple"]),
        ("Ask the oracle: what's Gilead's net margin?", ["GILD"]),
        ("Any intel on AMD's R&D spending?", ["AMD"]),
    ],
)
def test_an_everyday_word_used_as_a_word_is_not_a_company(
    question: str, companies: list[str]
) -> None:
    assert _found(question) == companies


def _one_word_names(*, everyday: bool) -> list[tuple[str, str]]:
    index = issuer_index()
    return sorted(
        (phrase, ticker)
        for phrase, ticker in index.phrases.items()
        if " " not in phrase
        and phrase.isalpha()
        and _ordinary(phrase)
        and (phrase in _everyday_words()) == everyday
        and ticker != "NVDA"
    )


@pytest.mark.parametrize(("word", "ticker"), _one_word_names(everyday=True))
def test_every_everyday_word_name_reads_both_ways(word: str, ticker: str) -> None:
    assert ticker in _found(f"What was {word.title()}'s revenue last quarter?")
    assert ticker in _found(f"compare {word} and Nvidia revenue")
    assert ticker not in _found(f"Nvidia's {word} margin")
    assert ticker not in _found(f"What is the {word} for Nvidia?")


@pytest.mark.parametrize(("word", "ticker"), _one_word_names(everyday=False))
def test_every_capitalised_name_is_a_company_unless_plainly_a_word(word: str, ticker: str) -> None:
    assert ticker in _found(f"{word} revenue last quarter")
    assert ticker in _found(f"is {word} profitable")
    assert ticker not in _found(f"Ask the {word}: what's Nvidia's revenue?")


class _Facts:
    def __init__(self) -> None:
        self.companies: list[str] = []

    def list_quarterly_report_dates(self, company: str, *, limit: int) -> tuple[date, ...]:
        return (date(2026, 6, 30), date(2026, 3, 31))[:limit]

    def get_financials(
        self, company: str, metric: str, *, report_date: date | None = None
    ) -> SimpleNamespace:
        self.companies.append(company)
        return SimpleNamespace(
            company_name="Lincoln National Corporation",
            ticker="LNC",
            cik="0000059558",
            metric=metric,
            value=Decimal("4542000000"),
            currency="USD",
            start_date=date(2026, 4, 1),
            end_date=date(2026, 6, 30),
            filed_date=date(2026, 8, 1),
            form="10-Q",
            accession_number="0000059558-26-000001",
            taxonomy="us-gaap",
            concept="Revenues",
            source_url="https://www.sec.gov/example.htm",
            source="sec_xbrl",
        )


@pytest.mark.parametrize("answer", ["2", "LNC", "Lincoln National", "the national one"])
def test_a_shared_name_asks_which_company_then_answers(tmp_path: Path, answer: str) -> None:
    facts = _Facts()
    runtime = Runtime(
        completer=DemoCompleter(issuer_index()),
        facts=facts,  # type: ignore[arg-type]
        ranking=_ranking(),
    )
    store = LocalThreadStore(tmp_path)

    asked = run_conversation_turn("t1", "Lincoln revenue", runtime, store=store).result

    assert asked.renderer is RendererKind.CLARIFY
    assert asked.clarify_kind == "ambiguous_company"
    assert asked.clarify_subject == "Lincoln"
    assert asked.candidates[:2] == ("LECO", "LNC")
    assert asked.candidate_labels[1] == "Lincoln National Corporation (LNC)"
    assert facts.companies == []

    answered = run_conversation_turn("t1", answer, runtime, store=store).result

    assert answered.renderer is not RendererKind.CLARIFY
    assert [row.ticker for row in answered.table_rows] == ["LNC"]
    # The chosen company is asked for by its CIK: Lincoln National's.
    assert {company for company in facts.companies} == {"0000059558"}


class _ModelPlan:
    """A model planner that names companies in full, as people do."""

    def __init__(self, *companies: str) -> None:
        self.companies = companies

    def complete(self, query: str, current_spec: object = None) -> WorkflowPlan:
        from financial_analyst_agent.contracts import Intent

        return WorkflowPlan(
            intent=Intent.COMPARE if len(self.companies) > 1 else Intent.LOOKUP,
            company=self.companies[0],
            companies=list(self.companies),
            metric="net_income",
            industry=None,
            topic=None,
        )


def test_facts_are_fetched_for_the_company_the_analysis_resolved(tmp_path: Path) -> None:
    from dataclasses import replace

    from financial_analyst_agent.runtime import recorded_runtime

    runtime = replace(recorded_runtime(), completer=_ModelPlan("Goldman Sachs", "JPMorgan"))
    result = run_conversation_turn(
        "t1", "Goldman Sachs vs JPMorgan net income", runtime, store=LocalThreadStore(tmp_path)
    ).result

    assert [(row.ticker, row.value is not None) for row in result.table_rows] == [
        ("GS", True),
        ("JPM", True),
    ]


@pytest.mark.parametrize(
    ("company", "ticker"), [("TEAM", "TEAM"), ("COKE", "COKE"), ("$coke", "COKE")]
)
def test_a_typed_ticker_is_that_listing_even_where_it_is_a_name(company: str, ticker: str) -> None:
    # "team" is Team Inc and "coke" is Coca-Cola, but TEAM is Atlassian's ticker.
    assert _ranking().lookup_member(company).ticker == ticker


@pytest.mark.parametrize(
    ("question", "companies"),
    [
        ("$TEAM revenue", ["TEAM"]),
        ("Novartis AG revenue", ["NVS"]),
        ("UBS Group AG revenue", ["UBS"]),
        ("The Progressive Corporation revenue", ["PGR"]),
        ("Pony AI Inc. American Depositary Shares revenue", ["PONY"]),
    ],
)
def test_listing_names_read_as_their_company(question: str, companies: list[str]) -> None:
    assert _found(question) == companies


@pytest.mark.parametrize(
    ("question", "companies"),
    [
        ("NVDA, AMD and INTC revenue", ["NVDA", "AMD", "INTC"]),
        ("NVDA vs INTC", ["NVDA", "INTC"]),
        ("MA vs AAPL", ["MA", "Apple"]),
        ("AAPL vs ON", ["Apple", "ON"]),
        ("COMPARE NVDA AND INTC REVENUE", ["NVDA", "INTC"]),
        # Capitals as tone still read words as words.
        ("WHAT IS NVIDIA NET MARGIN NOW?", ["NVDA"]),
        ("Is Apple ON track?", ["Apple"]),
    ],
)
def test_a_list_of_tickers_keeps_every_ticker(question: str, companies: list[str]) -> None:
    assert _found(question) == companies


@pytest.mark.parametrize(
    ("question", "companies"),
    [
        ("TEAM revenue", ["TEAM"]),
        ("COKE revenue", ["COKE"]),
        ("Compare TEAM and MSFT revenue", ["TEAM", "Microsoft"]),
        # Typed as a name, it is the name's company.
        ("Team revenue", ["TISI"]),
        ("Coke revenue", ["KO"]),
        # Shouted, capitals say nothing: the name reading stands.
        ("HOW IS TEAM DOING", ["TISI"]),
    ],
)
def test_a_ticker_typed_in_a_question_is_that_listing(question: str, companies: list[str]) -> None:
    assert _found(question) == companies


@pytest.mark.parametrize(
    ("turns", "tickers"),
    [
        (("Microsoft revenue", "add Lincoln", "1"), ["MSFT", "LECO"]),
        (("Microsoft revenue", "add Lincoln", "Lincoln National"), ["MSFT", "LNC"]),
        (("Microsoft revenue", "what about Lincoln?", "2"), ["LNC"]),
    ],
)
def test_a_follow_ups_shared_name_is_asked_once(
    tmp_path: Path, turns: tuple[str, ...], tickers: list[str]
) -> None:
    runtime = Runtime(
        completer=DemoCompleter(issuer_index()),
        facts=_Facts(),  # type: ignore[arg-type]
        ranking=_ranking(),
    )
    store = LocalThreadStore(tmp_path)
    for message in turns:
        turn = run_conversation_turn("t1", message, runtime, store=store)

    assert turn.result.renderer is not RendererKind.CLARIFY
    assert turn.analysis_spec is not None
    assert [company.ticker for company in turn.analysis_spec.companies] == tickers
