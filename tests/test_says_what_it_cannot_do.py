"""When the app cannot do what was asked, it says so instead of answering a different question.

Each test is a question a tester asked the public demo, replayed on the recorded
runtime, with the answer it should have got: rankings by a metric, unsupported
metrics and periods, missing companies, misspelled names and group names,
undo, advice, and changes with no base.
"""

from __future__ import annotations

import pytest

from conversation_replay import ask, column_of, replay, tickers_of


# Imported per test, as in test_tester_conversations.
@pytest.fixture
def runtime():  # type: ignore[no-untyped-def]
    from financial_analyst_agent.runtime import recorded_runtime

    return recorded_runtime()


PHARMA = {"LLY", "JNJ", "ABBV", "MRK", "PFE", "AMGN", "GILD"}
TECH = {"AAPL", "MSFT", "NVDA", "AVGO", "MU", "INTC", "ORCL", "AMD", "CSCO", "PLTR", "AMAT"}


# Rankings


@pytest.mark.parametrize(
    "question",
    ["Rank pharma by operating margin", "Rank pharma companies by operating margin"],
)
def test_rank_an_industry_by_a_metric(runtime, question: str) -> None:  # type: ignore[no-untyped-def]
    (answer,) = ask(runtime, question)
    assert answer.table is not None, answer.message
    assert "Rank" in answer.table.headers
    assert set(tickers_of(answer)) <= PHARMA


def test_rank_after_a_comparison_starts_a_new_ranking(runtime) -> None:  # type: ignore[no-untyped-def]
    answers = ask(runtime, "Compare Apple and Microsoft revenue", "Rank pharma by operating margin")
    assert answers[1].table is not None and "Rank" in answers[1].table.headers
    assert set(tickers_of(answers[1])) <= PHARMA


def test_which_company_has_the_highest_metric_is_a_ranking(runtime) -> None:  # type: ignore[no-untyped-def]
    (answer,) = ask(runtime, "Which tech company has the highest net margin?")
    assert answer.table is not None and "Rank" in answer.table.headers
    assert set(tickers_of(answer)) <= TECH
    margins = [float(cell.split("%")[0]) for cell in column_of(answer, "Net margin") if "%" in cell]
    assert margins == sorted(margins, reverse=True)


def test_smallest_says_rankings_start_from_the_largest(runtime) -> None:  # type: ignore[no-untyped-def]
    (answer,) = ask(runtime, "Smallest healthcare companies")
    assert answer.table is None
    assert answer.message is not None
    assert answer.message.startswith("Rankings start from the largest companies")
    assert list(answer.suggestions) == ["Top 5 healthcare companies by revenue"]


def test_a_ranking_names_the_period_it_shows(runtime) -> None:  # type: ignore[no-untyped-def]
    chips = replay(runtime, "Top 10 semiconductor companies by gross margin in Q1 2026").chips
    assert "Q1 FY2026" not in chips
    assert "Latest quarter" in chips


def test_the_order_chip_reads_as_words(runtime) -> None:  # type: ignore[no-untyped-def]
    chips = replay(runtime, "Top 5 banks by net income").chips
    assert "Order By Metric" not in chips


# Metrics the app cannot look up


@pytest.mark.parametrize(
    ("question", "named"),
    [
        ("Apple ROA", "return on assets"),
        ("Apple total assets", "total assets"),
        ("Apple total debt", "debt"),
        ("Apple headcount", "headcount"),
        # A word inside an unknown measure that would be ambiguous alone ("equity")
        # does not make it a question: the measure is named (ADR 0004).
        ("What's Apple's debt-to-equity ratio?", "debt-to-equity"),
        ("Apple D/E", "debt-to-equity"),
        ("Apple equity multiplier", "equity multiplier"),
        ("Apple dividend yield", "dividend yield"),
    ],
)
def test_an_unsupported_metric_is_named_not_swapped(runtime, question: str, named: str) -> None:  # type: ignore[no-untyped-def]
    (answer,) = ask(runtime, question)
    assert answer.table is None and answer.fact_card is None
    assert answer.message is not None
    assert answer.message.startswith(f"I can't look up {named}")
    assert "Apple" in " ".join(answer.suggestions)


def test_an_unsupported_metric_after_another_answer_does_not_repeat_it(runtime) -> None:  # type: ignore[no-untyped-def]
    answers = ask(runtime, "Apple capex", "Apple buybacks")
    assert answers[1].fact_card is None and answers[1].table is None
    assert answers[1].message is not None
    assert answers[1].message.startswith("I can't look up share buybacks")


# Periods


@pytest.mark.parametrize(
    "question",
    ["Apple revenue last year", "Apple annual revenue"],
)
def test_a_year_shows_the_last_four_quarters(runtime, question: str) -> None:  # type: ignore[no-untyped-def]
    (answer,) = ask(runtime, question)
    assert answer.table is not None and len(answer.table.rows) == 4
    assert any("rather than summed" in banner for banner in answer.banners)


def test_a_half_year_shows_its_two_quarters(runtime) -> None:  # type: ignore[no-untyped-def]
    (answer,) = ask(runtime, "Microsoft revenue H1 FY2026")
    assert len(column_of(answer, "Revenue")) == 2


def test_since_a_year_shows_every_quarter_available(runtime) -> None:  # type: ignore[no-untyped-def]
    (answer,) = ask(runtime, "Apple revenue since 2025")
    assert answer.table is not None
    assert len(answer.table.rows) >= 5


def test_year_to_date_says_it_is_not_supported(runtime) -> None:  # type: ignore[no-untyped-def]
    (answer,) = ask(runtime, "Apple revenue year to date")
    assert any("Year-to-date" in banner for banner in answer.banners)


def test_a_window_longer_than_the_data_says_so(runtime) -> None:  # type: ignore[no-untyped-def]
    (answer,) = ask(runtime, "Apple revenue last 12 quarters")
    assert answer.table is not None
    shown = len(answer.table.rows)
    assert shown < 12
    assert any(f"only {shown} of the 12 quarters asked for" in banner for banner in answer.banners)


# Companies


def test_a_company_the_demo_lacks_is_named_and_the_rest_answered(runtime) -> None:  # type: ignore[no-untyped-def]
    (answer,) = ask(runtime, "Q2 2026 revenue for Apple, Amazon, Meta, Tesla")
    assert set(tickers_of(answer)) == {"AAPL", "TSLA"}
    assert any(
        "Amazon.com" in banner and "Meta Platforms" in banner and "recorded demo" in banner
        for banner in answer.banners
    )


def test_every_misspelled_name_is_corrected(runtime) -> None:  # type: ignore[no-untyped-def]
    (answer,) = ask(runtime, "Microsfot vs Aple net income")
    assert set(tickers_of(answer)) == {"MSFT", "AAPL"}


def test_magnificent_seven_expands_to_its_companies(runtime) -> None:  # type: ignore[no-untyped-def]
    (answer,) = ask(runtime, "Magnificent 7 revenue")
    assert {"AAPL", "MSFT", "NVDA", "TSLA"} <= set(tickers_of(answer))
    assert any("Amazon.com" in banner for banner in answer.banners)


def test_faang_expands_to_its_companies(runtime) -> None:  # type: ignore[no-untyped-def]
    (answer,) = ask(runtime, "FAANG net income")
    assert {"AAPL"} <= set(tickers_of(answer))


def test_an_unknown_company_leaves_no_unknown_chip(runtime) -> None:  # type: ignore[no-untyped-def]
    chips = replay(runtime, "OpenAI revenue").chips
    assert "unknown" not in chips


# Growth


def test_a_change_shows_its_percentage(runtime) -> None:  # type: ignore[no-untyped-def]
    (answer,) = ask(runtime, "Apple revenue year over year")
    table = answer.table
    assert table is not None
    yoy = [value for value in column_of(answer, "YoY change") if value]
    assert yoy and all("%" in value for value in yoy)


def test_which_grew_faster_leads_with_the_answer(runtime) -> None:  # type: ignore[no-untyped-def]
    (answer,) = ask(runtime, "Which grew faster, Apple or Microsoft?")
    assert answer.headline is not None
    assert answer.headline.startswith("Year over year, Microsoft's revenue grew")
    assert "Apple's grew" in answer.headline


def test_quarter_lengths_are_not_misreported(runtime) -> None:  # type: ignore[no-untyped-def]
    (answer,) = ask(runtime, "Which grew faster, Apple or Microsoft?")
    assert not any("65 weeks" in banner for banner in answer.banners)


def test_a_change_from_a_derived_quarter_is_marked(runtime) -> None:  # type: ignore[no-untyped-def]
    (answer,) = ask(runtime, "Apple revenue sequential growth")
    changes = column_of(answer, "QoQ change")
    ends = column_of(answer, "Quarter ended")
    # Dec 2025 against Apple's derived fiscal Q4 to Sep 2025.
    assert "†" in changes[ends.index("Dec 27, 2025")]


# Follow-up words


def test_sort_by_orders_the_table(runtime) -> None:  # type: ignore[no-untyped-def]
    answers = ask(runtime, "Compare Microsoft, Apple and Nvidia revenue", "sort by revenue")
    assert column_of(answers[1], "Ticker") == ["AAPL", "NVDA", "MSFT"]


def test_start_over_clears_the_analysis(runtime) -> None:  # type: ignore[no-untyped-def]
    answers = ask(runtime, "Compare Apple and Microsoft revenue", "start over")
    assert answers[1].message is not None and answers[1].message_tone == "info"
    assert replay(runtime, "Compare Apple and Microsoft revenue", "start over").chips == ()


def test_undo_explains_itself(runtime) -> None:  # type: ignore[no-untyped-def]
    answers = ask(runtime, "Apple revenue", "undo")
    assert answers[1].message is not None and answers[1].message_tone == "info"
    assert "metric" not in answers[1].message


def test_a_clarification_can_be_answered_by_number(runtime) -> None:  # type: ignore[no-untyped-def]
    answers = ask(runtime, "Apple margin", "2")
    assert answers[1].fact_card is not None
    assert answers[1].fact_card.metric_header == "Operating margin"


# Questions close to a supported flow


def test_is_it_a_buy_gets_the_advice_reply(runtime) -> None:  # type: ignore[no-untyped-def]
    (answer,) = ask(runtime, "Is Nvidia a buy?")
    assert answer.message is not None
    assert answer.message.startswith("I don't give investment advice")


def test_why_did_it_drop_asks_against_what_then_shows_the_change(runtime) -> None:  # type: ignore[no-untyped-def]
    asked, answer = ask(runtime, "Why did Apple's revenue drop last quarter?", "the quarter before")
    # A drop names no base: the quarter before, or the same quarter a year earlier?
    assert asked.clarify_prompt == "Compared with what?"
    assert answer.table is not None
    assert any(change.startswith("-") for change in column_of(answer, "QoQ change"))


def test_summarize_risk_factors_compares_the_filings(runtime) -> None:  # type: ignore[no-untyped-def]
    (answer,) = ask(runtime, "Summarize Microsoft's risk factors")
    assert answer.intent == "filing_change", answer.message


def test_compare_to_peers_adds_peers(runtime) -> None:  # type: ignore[no-untyped-def]
    (answer,) = ask(runtime, "Compare Nvidia to its peers")
    tickers = set(tickers_of(answer))
    assert "NVDA" in tickers and len(tickers) >= 3
