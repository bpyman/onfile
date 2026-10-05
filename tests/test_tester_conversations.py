"""Conversations testers had with the public demo, replayed on the recorded runtime.

Each test is one conversation with the answer it should have got: periods and
companies named mid-conversation, companies the demo did not record, named and
derived quarters, change rows, and rankings shorter than asked.
"""

from __future__ import annotations

import pytest

from conversation_replay import ask, last_result, tickers_of


# Imported per test, and kept out of tests/unit: tests/unit/test_contracts_import
# reloads the conversation modules but not the planner, so a recorded runtime used
# after it carries enum members the reloaded seam does not recognise.
@pytest.fixture
def runtime():  # type: ignore[no-untyped-def]
    from financial_analyst_agent.runtime import recorded_runtime

    return recorded_runtime()


def test_a_period_question_naming_another_company_answers_that_company(runtime) -> None:  # type: ignore[no-untyped-def]
    answers = ask(
        runtime,
        "Apple revenue last 4 quarters",
        "Microsoft TTM net income",
        "calendar Q2 2026 revenue for Oracle",
    )
    assert set(tickers_of(answers[0])) == {"AAPL"}
    assert set(tickers_of(answers[1])) == {"MSFT"}
    assert set(tickers_of(answers[2])) == {"ORCL"}


def test_a_company_named_after_a_ranking_replaces_the_ranking(runtime) -> None:  # type: ignore[no-untyped-def]
    answers = ask(
        runtime,
        "Rank the top 5 banks by net income",
        "JPMorgan diluted EPS last 4 quarters",
    )
    assert answers[0].table is not None and "Rank" in answers[0].table.headers
    assert set(tickers_of(answers[1])) == {"JPM"}
    assert answers[1].table is not None and "Rank" not in answers[1].table.headers
    assert len(answers[1].table.rows) == 4


def test_a_period_on_its_own_still_edits_the_current_analysis(runtime) -> None:  # type: ignore[no-untyped-def]
    answers = ask(runtime, "Apple revenue", "last 4 quarters")
    assert set(tickers_of(answers[1])) == {"AAPL"}
    assert answers[1].table is not None and len(answers[1].table.rows) == 4


@pytest.mark.parametrize(
    ("question", "name"),
    [
        ("Costco revenue", "Costco Wholesale"),
        ("COST revenue", "Costco Wholesale"),
    ],
)
def test_a_company_the_demo_did_not_record_is_named_not_swapped(
    runtime, question: str, name: str
) -> None:  # type: ignore[no-untyped-def]
    answers = ask(runtime, "Tesla vs GM revenue", question)
    reply = answers[1]
    assert reply.table is None and reply.fact_card is None
    assert reply.message is not None
    assert reply.message.startswith(f"{name} isn't in the recorded demo")
    assert reply.message_tone == "info"


def test_a_recorded_company_is_not_mistaken_for_a_missing_one(runtime) -> None:  # type: ignore[no-untyped-def]
    answers = ask(runtime, "Apple revenue", "what about AMD?")
    assert set(tickers_of(answers[1])) == {"AMD"}


def test_no_company_named_says_so_instead_of_unknown(runtime) -> None:  # type: ignore[no-untyped-def]
    answers = ask(runtime, "revenue please")
    assert answers[0].message is not None
    assert "unknown" not in answers[0].message
    assert answers[0].message.startswith("I couldn't tell which company you mean")


# Codex review of master (GPT-6-Astra), reproduced on the recorded runtime.


def test_an_insurers_gross_margin_is_not_revenue_minus_product_costs(runtime) -> None:  # type: ignore[no-untyped-def]
    # UnitedHealth tags $13.4 B of product costs as cost of goods and reports its
    # $75 B of medical costs separately; revenue minus the first is not gross profit.
    (row,) = last_result(runtime, "UnitedHealth gross margin").table_rows
    assert row.value is None
    apple = last_result(runtime, "Apple gross margin").table_rows[0]
    assert apple.value is not None


def test_a_named_quarter_leaves_out_a_company_without_that_quarter(runtime) -> None:  # type: ignore[no-untyped-def]
    result = last_result(runtime, "Compare Microsoft and Apple revenue Q4 2026")
    assert {row.ticker for row in result.table_rows} == {"MSFT"}
    assert "No filing for Q4 FY2026 from Apple." in result.banners


def test_latest_after_a_named_quarter_asks_for_the_newest_quarter(runtime) -> None:  # type: ignore[no-untyped-def]
    (named,) = last_result(runtime, "Apple revenue Q3 2025").table_rows
    (latest,) = last_result(runtime, "Apple revenue Q3 2025", "latest revenue").table_rows
    assert latest.end_date is not None and named.end_date is not None
    assert latest.end_date > named.end_date


def test_a_trend_chart_keeps_a_missing_quarter_as_a_gap(runtime) -> None:  # type: ignore[no-untyped-def]
    from financial_analyst_agent.presentation import present_turn

    answer = present_turn(last_result(runtime, "Apple EPS last 6 quarters"))
    assert answer.chart is not None
    assert len(answer.chart.period_labels) == 6
    assert any(record["Apple Inc."] is None for record in answer.chart.records)


def test_a_derived_fiscal_q4_inside_gross_profit_keeps_its_filings(runtime) -> None:  # type: ignore[no-untyped-def]
    (row,) = last_result(runtime, "Google gross profit Q4 2025").table_rows
    forms = {inner.form for part in row.derived_from for inner in part.derived_from}
    assert forms == {"10-K", "10-Q"}
    assert all(part.derivation for part in row.derived_from)


def test_a_margin_change_row_keeps_both_formula_inputs(runtime) -> None:  # type: ignore[no-untyped-def]
    rows = last_result(runtime, "Apple operating margin year over year").table_rows
    change = next(row for row in rows if row.comparison == "year_over_year")
    for level in change.components:
        assert level.metric == "operating_margin"
        assert {part.metric for part in level.derived_from} == {"operating_income", "revenue"}


# Smaller findings from the same round of user testing.


def test_a_quarter_that_does_not_exist_is_refused(runtime) -> None:  # type: ignore[no-untyped-def]
    (answer,) = ask(runtime, "Microsoft revenue Q5 2025")
    assert answer.table is None and answer.fact_card is None
    assert answer.message == "There is no Q5: a fiscal year has four quarters, Q1 to Q4."


def test_which_one_is_more_profitable_adds_profit_to_the_comparison(runtime) -> None:  # type: ignore[no-untyped-def]
    answers = ask(runtime, "Compare Nvidia and AMD revenue", "which one is more profitable")
    assert answers[1].table is not None
    assert {"Net income", "Net margin"} <= set(answers[1].table.headers)
    assert set(tickers_of(answers[1])) == {"NVDA", "AMD"}


def test_chart_it_explains_when_charts_appear(runtime) -> None:  # type: ignore[no-untyped-def]
    answers = ask(runtime, "Apple revenue", "chart it")
    assert answers[1].message is not None
    assert answers[1].message.startswith("Charts appear on their own")
    assert answers[1].message_tone == "info"


def test_year_over_year_shows_a_yoy_change_for_each_quarter(runtime) -> None:  # type: ignore[no-untyped-def]
    answers = ask(runtime, "Apple revenue last 4 quarters", "show year-over-year")
    table = answers[1].table
    assert table is not None
    # The four quarters asked for stay on screen, each with its year-over-year
    # change beside it, read from the comparative its own 10-Q reports.
    changes = [row[table.headers.index("YoY change")] for row in table.rows]
    assert len(changes) == 4 and all(changes)
    assert "QoQ change" not in table.headers


def test_a_ranking_shorter_than_asked_says_so(runtime) -> None:  # type: ignore[no-untyped-def]
    (answer,) = ask(runtime, "Rank the top 5 banks by net income")
    assert answer.table is not None and len(answer.table.rows) == 3
    assert any("shorter than the 5 asked for" in banner for banner in answer.banners)


def test_a_margin_of_another_metric_offers_that_metric(runtime) -> None:  # type: ignore[no-untyped-def]
    (answer,) = ask(runtime, "Palantir free cash flow margin")
    assert answer.candidates[0] == "Free cash flow"
