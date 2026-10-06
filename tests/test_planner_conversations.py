"""Planner red team: conversations replayed on the recorded runtime.

Each test is a thread from the red-team transcripts. The common thread: the
answer is about what was asked, and anything not answered is said.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from conversation_replay import ask, column_of, last_result, replay, tickers_of

if TYPE_CHECKING:
    from financial_analyst_agent.presentation import Presentation


@pytest.fixture
def runtime():  # type: ignore[no-untyped-def]
    from financial_analyst_agent.runtime import recorded_runtime

    return recorded_runtime()


def _metrics(answer: Presentation) -> set[str]:
    if answer.fact_card is not None:
        return {answer.fact_card.metric_header}
    assert answer.table is not None, answer.message
    return set(answer.table.headers)


def _text(answer: Presentation) -> str:
    rows = [" ".join(row) for row in answer.table.rows] if answer.table else []
    return " ".join([answer.message or "", *answer.banners, *rows])


PHARMA = {"LLY", "JNJ", "ABBV", "MRK", "PFE", "AMGN", "GILD"}


# H4, H5, H8: no junk rows, no "unknown"


@pytest.mark.parametrize(
    "question", ["gross margin", "What is the EBITDA?", "what was the revenue?", "What's the P/E?"]
)
def test_no_company_asks_for_one(runtime, question: str) -> None:  # type: ignore[no-untyped-def]
    (answer,) = ask(runtime, question)
    assert answer.table is None and answer.fact_card is None
    assert answer.message is not None
    assert "unknown" not in answer.message and "“the”" not in answer.message
    assert "company" in answer.message


def test_a_determiner_is_never_a_company(runtime) -> None:  # type: ignore[no-untyped-def]
    answers, chips, _ = replay(runtime, "what was the revenue?", "add Apple")
    assert tickers_of(answers[1]) == ["AAPL"]
    assert "the" not in chips


def test_naming_the_company_completes_the_question(runtime) -> None:  # type: ignore[no-untyped-def]
    answers = ask(runtime, "net margin", "for Apple")
    assert answers[1].fact_card is not None
    assert answers[1].fact_card.metric_header == "Net margin"


def test_which_is_biggest_ranks_the_companies_on_screen(runtime) -> None:  # type: ignore[no-untyped-def]
    answers = ask(runtime, "Compare Tesla, Apple and Nvidia revenue", "which is biggest?")
    assert answers[1].table is not None, answers[1].message
    assert set(tickers_of(answers[1])) - {""} == {"TSLA", "AAPL", "NVDA"}
    assert "unknown" not in _text(answers[1])


def test_an_unknown_industry_is_never_called_unknown(runtime) -> None:  # type: ignore[no-untyped-def]
    (answer,) = ask(runtime, "top 5 by revenue")
    assert "unknown" not in _text(answer)


# H6: qualitative turns keep the analysis


def test_a_news_question_keeps_the_analysis(runtime) -> None:  # type: ignore[no-untyped-def]
    answers = ask(runtime, "Apple revenue", "latest news on Apple", "add Merck")
    assert set(tickers_of(answers[2])) == {"AAPL", "MRK"}


# M1


def test_a_company_with_a_rank_word_is_looked_up(runtime) -> None:  # type: ignore[no-untyped-def]
    (answer,) = ask(runtime, "Apple top line")
    assert answer.fact_card is not None, answer.message
    assert answer.fact_card.metric_header == "Revenue"


# M2: clarification answers


@pytest.mark.parametrize(
    ("question", "answer", "wanted"),
    [
        ("Apple margin", "all of them", {"Gross margin", "Operating margin", "Net margin"}),
        ("Apple margin", "all three", {"Gross margin", "Operating margin", "Net margin"}),
        ("Apple margin", "all", {"Gross margin", "Operating margin", "Net margin"}),
        ("Apple income", "both", {"Net income", "Operating income"}),
        ("Apple profit", "net income and operating income", {"Net income", "Operating income"}),
        ("Apple margin", "gross and net", {"Gross margin", "Net margin"}),
        ("Apple margin", "the net one please", {"Net margin"}),
        ("Apple profit", "gross margin", {"Gross margin"}),
        ("Apple margin", "EPS", {"Diluted EPS"}),
    ],
)
def test_clarification_answers(runtime, question: str, answer: str, wanted: set[str]) -> None:  # type: ignore[no-untyped-def]
    answers = ask(runtime, question, answer)
    assert wanted <= _metrics(answers[1])
    assert tickers_of(answers[1]) == ["AAPL"]
    assert not any("set aside" in banner for banner in answers[1].banners)


def test_a_period_answer_keeps_the_question_open(runtime) -> None:  # type: ignore[no-untyped-def]
    answers, _, pending = replay(runtime, "Apple margin", "last 4 quarters")
    assert answers[1].candidates
    assert pending
    answers, chips, _ = replay(runtime, "Apple margin", "last 4 quarters", "net")
    assert "Last 4 quarters" in chips and "Net margin" in chips


def test_a_number_out_of_range_asks_again(runtime) -> None:  # type: ignore[no-untyped-def]
    answers, _, pending = replay(runtime, "Apple margin", "4")
    assert pending
    assert answers[1].candidates
    assert any("1 to 3" in banner for banner in answers[1].banners)


# M3


def test_margins_compares_all_three(runtime) -> None:  # type: ignore[no-untyped-def]
    (answer,) = ask(runtime, "Compare the margins of Apple and Microsoft")
    assert {"Gross margin", "Operating margin", "Net margin"} <= _metrics(answer)


# M4: unknown words are named, not swapped for an overview


@pytest.mark.parametrize(
    ("question", "word"),
    [
        ("Apple happiness index", "happiness index"),
        ("Nvidia guidance", "guidance"),
        ("Apple costs", "costs"),
    ],
)
def test_an_unknown_word_is_named(runtime, question: str, word: str) -> None:  # type: ignore[no-untyped-def]
    (answer,) = ask(runtime, question)
    assert answer.table is None and answer.fact_card is None
    assert answer.message is not None and f"“{word}”" in answer.message


@pytest.mark.parametrize(
    ("question", "metric"),
    [
        ("Apple turnover", "Revenue"),
        ("Apple depreciation", "Depreciation and amortization"),
        ("Apple's PE", "P/E ratio"),
        ("How much did Apple earn?", "Net income"),
        ("How much does Apple spend on research?", "Research and development"),
    ],
)
def test_everyday_wording_finds_the_metric(runtime, question: str, metric: str) -> None:  # type: ignore[no-untyped-def]
    (answer,) = ask(runtime, question)
    assert answer.fact_card is not None, answer.message
    # A trailing-year figure says so after its name ("P/E ratio (trailing year)").
    assert answer.fact_card.metric_header.removesuffix(" (trailing year)") == metric


def test_how_much_money_did_apple_make_asks_which(runtime) -> None:  # type: ignore[no-untyped-def]
    (answer,) = ask(runtime, "How much money did Apple make last quarter?")
    assert set(answer.candidates) == {"Revenue", "Net income"}


def test_worth_is_market_cap(runtime) -> None:  # type: ignore[no-untyped-def]
    (answer,) = ask(runtime, "What's Apple worth?")
    assert "Market cap" in _metrics(answer)


def test_the_overview_still_answers_how_is(runtime) -> None:  # type: ignore[no-untyped-def]
    for question in ("How is Apple doing?", "Apple", "Tell me about Nvidia"):
        (answer,) = ask(runtime, question)
        assert answer.table is not None, (question, answer.message)
        assert "Net margin" in answer.table.headers


# M5: what was not answered is said


def test_an_unknown_name_in_a_list_is_said(runtime) -> None:  # type: ignore[no-untyped-def]
    (answer,) = ask(runtime, "Compare Apple and Foobar revenue")
    assert any("Foobar" in banner for banner in answer.banners)


def test_a_second_question_is_said(runtime) -> None:  # type: ignore[no-untyped-def]
    (answer,) = ask(runtime, "Compare Apple and Microsoft revenue and rank the top 5 banks")
    assert any("rank the top 5 banks" in banner for banner in answer.banners)


def test_a_company_beside_a_ranking_is_said(runtime) -> None:  # type: ignore[no-untyped-def]
    (answer,) = ask(runtime, "Top 5 banks and Apple revenue")
    assert any("Apple" in banner for banner in answer.banners)


# M7, M8: pronouns and "them"


def test_compare_them_after_two_lookups(runtime) -> None:  # type: ignore[no-untyped-def]
    answers = ask(runtime, "Apple revenue", "Microsoft revenue", "compare them")
    assert set(tickers_of(answers[2])) == {"AAPL", "MSFT"}


def test_compare_with_the_first_one(runtime) -> None:  # type: ignore[no-untyped-def]
    answers = ask(
        runtime, "Apple revenue", "what about Microsoft?", "Nvidia", "compare with the first one"
    )
    assert set(tickers_of(answers[3])) == {"NVDA", "AAPL"}


def test_what_was_it_last_quarter(runtime) -> None:  # type: ignore[no-untyped-def]
    answers = ask(runtime, "Microsoft revenue last 4 quarters", "what was it last quarter?")
    assert answers[1].fact_card is not None, answers[1].message
    assert answers[1].fact_card.ticker == "MSFT"


def test_what_was_it_a_year_ago(runtime) -> None:  # type: ignore[no-untyped-def]
    answers = ask(runtime, "Microsoft revenue", "what was it a year ago?")
    assert answers[1].headline is not None and "Year over year" in answers[1].headline


# M9: ranking follow-ups


def test_add_a_company_to_a_ranking(runtime) -> None:  # type: ignore[no-untyped-def]
    answers = ask(runtime, "top 5 banks", "add Apple")
    assert "AAPL" in tickers_of(answers[1])
    assert "JPM" in tickers_of(answers[1])


def test_remove_a_company_from_a_ranking(runtime) -> None:  # type: ignore[no-untyped-def]
    answers = ask(runtime, "top 5 banks", "remove JPMorgan")
    assert "JPM" not in tickers_of(answers[1])
    assert "BAC" in tickers_of(answers[1])


def test_sort_by_reranks_a_ranking(runtime) -> None:  # type: ignore[no-untyped-def]
    answers = ask(runtime, "top 5 pharma companies by revenue", "sort by net income")
    assert any("Ordered by net income" in banner for banner in answers[1].banners)


def test_what_about_another_industry(runtime) -> None:  # type: ignore[no-untyped-def]
    answers = ask(runtime, "top 5 banks", "what about pharma?")
    assert set(tickers_of(answers[1])) <= PHARMA


# M10–M12: periods


@pytest.mark.parametrize(
    ("question", "chip"),
    [
        ("Apple revenue 2024", "Fiscal 2024"),
        ("Apple revenue september quarter 2025", "Calendar Q3 2025"),
    ],
)
def test_periods_are_read(runtime, question: str, chip: str) -> None:  # type: ignore[no-untyped-def]
    _, chips, _ = replay(runtime, question)
    assert chip in chips


def test_last_n_years_asks_for_their_quarters(runtime) -> None:  # type: ignore[no-untyped-def]
    (answer,) = ask(runtime, "Apple revenue in the last 3 years")
    assert any("of the 12 quarters" in banner for banner in answer.banners)


def test_quarter_over_quarter_shows_sequential_change(runtime) -> None:  # type: ignore[no-untyped-def]
    (answer,) = ask(runtime, "Apple revenue quarter over quarter")
    assert answer.table is not None, answer.message
    assert "QoQ change" in answer.table.headers


@pytest.mark.parametrize("count", [2, 4, 6])
def test_quarter_over_quarter_keeps_the_window_asked_for(runtime, count: int) -> None:  # type: ignore[no-untyped-def]
    # Each quarter shown has its change on the quarter before, the oldest's too.
    result = replay(runtime, f"Apple revenue over the last {count} quarters quarter over quarter")
    (answer,) = result.answers
    assert answer.table is not None, answer.message
    changes = column_of(answer, "QoQ change")
    assert len(changes) == count
    assert all(change not in ("", "—") for change in changes), changes
    assert f"Last {count} quarters" in result.chips


_FISCAL_2025 = ["2025-09-27", "2025-06-28", "2025-03-29", "2024-12-28"]


def _levels_and_changes(result, comparison: str) -> tuple[list[str], list[str]]:  # type: ignore[no-untyped-def]
    levels = [str(row.end_date) for row in result.table_rows if row.comparison is None]
    changes = [str(row.end_date) for row in result.table_rows if row.comparison == comparison]
    return levels, changes


@pytest.mark.parametrize(
    ("question", "comparison"),
    [
        ("Apple R&D for fiscal 2025 year over year", "year_over_year"),
        ("Apple R&D for fiscal 2025 quarter over quarter", "sequential"),
    ],
)
def test_a_named_year_shows_its_quarters_each_with_its_change(  # type: ignore[no-untyped-def]
    runtime, question: str, comparison: str
) -> None:
    # Fiscal 2025's four quarters, each with its change; no fiscal 2024 quarter as a
    # row, though it is the base of a change.
    levels, changes = _levels_and_changes(last_result(runtime, question), comparison)
    assert levels == _FISCAL_2025
    assert sorted(changes, reverse=True) == _FISCAL_2025


@pytest.mark.parametrize(
    ("answer", "comparison"),
    [("the quarter before", "sequential"), ("year over year", "year_over_year")],
)
def test_a_named_quarter_keeps_the_change_chosen_for_it(  # type: ignore[no-untyped-def]
    runtime, answer: str, comparison: str
) -> None:
    # "Compared with what?" answered: Q2 FY2025 alone, with that change.
    result = last_result(runtime, "How much did Apple's revenue change in Q2 2025?", answer)
    assert _levels_and_changes(result, comparison) == (["2025-03-29"], ["2025-03-29"])


def test_next_quarter_is_not_forecast(runtime) -> None:  # type: ignore[no-untyped-def]
    (answer,) = ask(runtime, "Apple revenue next quarter")
    assert answer.table is None and answer.fact_card is None
    assert answer.message is not None and "forecast" in answer.message


def test_an_unread_period_is_said(runtime) -> None:  # type: ignore[no-untyped-def]
    (answer,) = ask(runtime, "Apple revenue for the quarter ended April 2026")
    assert any("couldn't read" in banner for banner in answer.banners)


def test_last_four_quarters_year_over_year_has_four_changes(runtime) -> None:  # type: ignore[no-untyped-def]
    (answer,) = ask(runtime, "Apple revenue last 4 quarters yoy")
    changes = column_of(answer, "YoY change")
    # Four quarters, each with its change: not eight rows, half of them blank.
    assert len(changes) == 4
    assert all(changes)


def test_a_future_quarter_is_not_reported_yet(runtime) -> None:  # type: ignore[no-untyped-def]
    (answer,) = ask(runtime, "Apple revenue Q4 2026")
    assert answer.message is not None and "not been reported yet" in answer.message


# M13: segments


def test_a_segment_is_said_not_covered(runtime) -> None:  # type: ignore[no-untyped-def]
    (answer,) = ask(runtime, "Apple iPhone revenue")
    assert any("segment" in banner for banner in answer.banners)


def test_a_kpi_alone_is_refused(runtime) -> None:  # type: ignore[no-untyped-def]
    (answer,) = ask(runtime, "Apple revenue per employee")
    assert any("per employee" in banner for banner in answer.banners)


# M14: edits that empty the analysis


def test_dropping_the_only_metric_says_so(runtime) -> None:  # type: ignore[no-untyped-def]
    answers, chips, _ = replay(runtime, "Apple revenue", "drop revenue")
    assert answers[1].message is not None
    assert "Analysis has" not in answers[1].message
    assert "metric" in answers[1].message
    assert "Revenue" in chips


def test_removing_the_only_company_says_so(runtime) -> None:  # type: ignore[no-untyped-def]
    answers, chips, _ = replay(runtime, "Apple revenue", "remove Apple")
    assert answers[1].message is not None and "only company" in answers[1].message
    assert "AAPL" in chips


def test_remove_one_metric_and_add_another(runtime) -> None:  # type: ignore[no-untyped-def]
    answers = ask(runtime, "Apple revenue", "remove revenue add net income")
    assert answers[1].fact_card is not None, answers[1].message
    assert answers[1].fact_card.metric_header == "Net income"


# Lows


def test_since_a_year_says_the_cap(runtime) -> None:  # type: ignore[no-untyped-def]
    (answer,) = ask(runtime, "Apple revenue since 2015")
    assert any("since 2015" in banner for banner in answer.banners)


def test_last_100_quarters_says_what_was_asked(runtime) -> None:  # type: ignore[no-untyped-def]
    (answer,) = ask(runtime, "Apple revenue last 100 quarters")
    assert any("100" in banner for banner in answer.banners)


def test_latest_drops_the_year_over_year_chip(runtime) -> None:  # type: ignore[no-untyped-def]
    _, chips, _ = replay(runtime, "Apple revenue", "show year-over-year", "latest")
    assert "Year over year" not in chips


@pytest.mark.parametrize("message", ["start over", "help", "hi", "banana"])
def test_no_set_aside_note_on_a_reset_help_or_refusal(runtime, message: str) -> None:  # type: ignore[no-untyped-def]
    answers = ask(runtime, "Apple margin", message)
    assert not any("set aside" in banner for banner in answers[1].banners)


def test_the_set_aside_note_shows_once(runtime) -> None:  # type: ignore[no-untyped-def]
    answers = ask(runtime, "Apple margin", "Microsoft revenue", "add Apple")
    assert any("set aside" in banner for banner in answers[1].banners)
    assert not any("set aside" in banner for banner in answers[2].banners)


def test_markdown_is_read_as_text(runtime) -> None:  # type: ignore[no-untyped-def]
    (answer,) = ask(runtime, "**Apple** _revenue_")
    assert answer.fact_card is not None, answer.message
    assert answer.fact_card.metric_header == "Revenue"


# UX


@pytest.mark.parametrize(
    "question",
    ["Best stock to buy?", "What stocks should I buy?", "Which stock to buy now", "stock tips"],
)
def test_stock_picks_are_declined(runtime, question: str) -> None:  # type: ignore[no-untyped-def]
    (answer,) = ask(runtime, question)
    assert answer.message is not None and "investment advice" in answer.message
    assert answer.suggestions


@pytest.mark.parametrize(
    "question",
    [
        "¿Cuáles fueron los ingresos de Apple el último trimestre?",
        "苹果公司的收入是多少",
        "Wie hoch war der Umsatz von Microsoft?",
    ],
)
def test_questions_are_read_in_english(runtime, question: str) -> None:  # type: ignore[no-untyped-def]
    (answer,) = ask(runtime, question)
    assert answer.message is not None and "English" in answer.message


@pytest.mark.parametrize("question", ["top 5 SPACs", "top 5 ETFs", "biggest BDCs"])
def test_non_operating_rankings_are_explained(runtime, question: str) -> None:  # type: ignore[no-untyped-def]
    (answer,) = ask(runtime, question)
    assert answer.message is not None and "operating companies" in answer.message


def test_a_theme_is_not_an_industry(runtime) -> None:  # type: ignore[no-untyped-def]
    (answer,) = ask(runtime, "top 5 AI companies")
    assert answer.message is not None and "semiconductors" in answer.message


def test_an_etf_ticker_is_explained(runtime) -> None:  # type: ignore[no-untyped-def]
    (answer,) = ask(runtime, "QQQ revenue")
    assert answer.message is not None and "fund" in answer.message


# Presentation


def test_a_singular_industry_chip_reads_as_plural(runtime) -> None:  # type: ignore[no-untyped-def]
    _, chips, _ = replay(runtime, "Which bank has the highest net margin?")
    assert any(chip.startswith("Top 10 banks") for chip in chips), chips


def test_market_data_chips_say_as_of(runtime) -> None:  # type: ignore[no-untyped-def]
    _, chips, _ = replay(runtime, "Apple market cap")
    assert "Latest quarter" not in chips
    assert any(chip.startswith("As of ") for chip in chips), chips


def test_a_single_company_table_has_no_cik_or_currency(runtime) -> None:  # type: ignore[no-untyped-def]
    for question in ("Apple interest coverage", "Apple market cap"):
        (answer,) = ask(runtime, question)
        if answer.table is not None:
            assert "Cik" not in answer.table.headers and "CIK" not in answer.table.headers
            assert "Currency" not in answer.table.headers


def test_the_correction_banner_comes_first(runtime) -> None:  # type: ignore[no-untyped-def]
    (answer,) = ask(runtime, "Microsft vs Nvdia revenue")
    assert answer.banners[0].startswith("Showing ")


def test_an_unknown_metric_refusal_is_short(runtime) -> None:  # type: ignore[no-untyped-def]
    (answer,) = ask(runtime, "Apple happiness index")
    assert answer.message is not None
    assert "Supported metrics" not in answer.message
    assert len(answer.message) < 220


def test_a_named_period_chart_caption_does_not_say_latest(runtime) -> None:  # type: ignore[no-untyped-def]
    (answer,) = ask(runtime, "Apple and Microsoft revenue Q2 2026")
    if answer.chart is not None:
        assert "Latest" not in answer.chart.caption


def test_spy_overview_is_one_message(runtime) -> None:  # type: ignore[no-untyped-def]
    (answer,) = ask(runtime, "How is SPY doing?")
    assert answer.table is None
    assert answer.message is not None and "SPY" in answer.message


def test_remove_both_says_it_would_empty_the_analysis(runtime) -> None:  # type: ignore[no-untyped-def]
    answers, chips, _ = replay(runtime, "Apple and Microsoft revenue", "remove both")
    assert answers[1].message is not None and "only company" in answers[1].message
    assert "AAPL" in chips and "MSFT" in chips


def test_an_unknown_word_keeps_its_spelling(runtime) -> None:  # type: ignore[no-untyped-def]
    (answer,) = ask(runtime, "Who is Apple's CEO?")
    assert answer.message is not None and "“CEO”" in answer.message


@pytest.mark.parametrize("question", ["top five banks", "top 5 shell companies"])
def test_a_ranking_word_is_not_an_unrecorded_company(runtime, question: str) -> None:  # type: ignore[no-untyped-def]
    (answer,) = ask(runtime, question)
    assert answer.message is None or "recorded demo" not in answer.message


def test_biggest_expense_asks_which_expense(runtime) -> None:  # type: ignore[no-untyped-def]
    (answer,) = ask(runtime, "What is Apple's biggest expense?")
    assert set(answer.candidates) == {"Cost of revenue", "Operating expenses"}


def test_removing_year_over_year_keeps_the_quarters_on_screen(runtime) -> None:  # type: ignore[no-untyped-def]
    # The year-over-year chip's × sends this. "year over year" in it is not a
    # request for two years of quarters.
    answers, chips, _ = replay(
        runtime, "Apple revenue growth last 4 quarters", "remove year over year"
    )
    assert chips == ("AAPL", "Revenue", "Last 4 quarters")
    assert answers[1].table is not None
    assert "YoY change" not in answers[1].table.headers
    assert len(answers[1].table.rows) == 4


def test_the_period_chip_s_remove_returns_to_the_latest_quarter(runtime) -> None:  # type: ignore[no-untyped-def]
    answers, chips, _ = replay(runtime, "Apple revenue last 4 quarters", "latest quarter")
    assert chips == ("AAPL", "Revenue", "Latest quarter")
    assert answers[1].fact_card is not None
