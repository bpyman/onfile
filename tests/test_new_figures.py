"""P/E, return on equity, EBITDA, share price, cash and dividends on the recorded demo,
and the round-4 open items that came with them (ADR 0008).

Values are the recorded 27 September 2026 filings and snapshot.
"""

from __future__ import annotations

import pytest

from conversation_replay import ask, column_of, replay


# Imported per test, as in test_tester_conversations.
@pytest.fixture
def runtime():  # type: ignore[no-untyped-def]
    from financial_analyst_agent.runtime import recorded_runtime

    return recorded_runtime()


def test_pe_is_market_cap_over_trailing_net_income(runtime) -> None:  # type: ignore[no-untyped-def]
    (answer,) = ask(runtime, "Apple P/E")
    assert answer.fact_card is not None
    assert answer.fact_card.amount == "38.9x"
    # Calculated over a trailing year, from the snapshot's market cap and a derived year.
    assert answer.fact_card.period_label == (
        "Calculated † · Trailing year · Jun 29, 2025 – Jun 27, 2026"
    )
    assert answer.fact_card.concept == "Market cap (Sep 27, 2026) ÷ trailing-year net income"
    assert answer.fact_card.form == ""
    assert any("trailing-year net income" in banner for banner in answer.banners)
    labels = [item.label for item in answer.evidence]
    assert "Apple Inc. · Market cap · At Sep 27, 2026" in labels


def test_p_slash_e_is_not_read_as_two_tickers(runtime) -> None:  # type: ignore[no-untyped-def]
    (answer,) = ask(runtime, "Compare Nvidia, AMD and Broadcom P/E")
    assert column_of(answer, "Ticker") == ["NVDA", "AMD", "AVGO"]
    assert column_of(answer, "P/E ratio (trailing year)") == ["28.3x †", "159.8x †", "43.9x †"]


def test_return_on_equity_over_a_window(runtime) -> None:  # type: ignore[no-untyped-def]
    (answer,) = ask(runtime, "JPMorgan return on equity last 4 quarters")
    assert column_of(answer, "Return on equity (trailing year)") == [
        "17.4% †",
        "16.2% †",
        "15.7%",
        "16.1% †",
    ]
    # A trailing year is not a 52-week quarter.
    assert not any("weeks" in banner for banner in answer.banners)


def test_ebitda_uses_depreciation_plus_amortization_when_no_da_line(runtime) -> None:  # type: ignore[no-untyped-def]
    (answer,) = ask(runtime, "Microsoft EBITDA")
    assert answer.fact_card is not None
    assert answer.fact_card.amount == "$51.90 B"
    assert any("depreciation plus amortization" in banner for banner in answer.banners)


def test_dividends_asks_which_and_per_share_answers(runtime) -> None:  # type: ignore[no-untyped-def]
    asked, chosen = ask(runtime, "Apple dividends", "per share")
    assert list(asked.candidates) == ["Dividends per share", "Dividends paid"]
    assert chosen.fact_card is not None
    assert (chosen.fact_card.metric_header, chosen.fact_card.amount) == (
        "Dividends per share",
        "$0.27",
    )


def test_share_price_comes_from_the_snapshot(runtime) -> None:  # type: ignore[no-untyped-def]
    (answer,) = ask(runtime, "Nvidia stock price")
    assert column_of(answer, "Share price") == ["$225.07"]
    assert answer.banners[0].startswith("Universe snapshot as of Sep 27, 2026")


def test_cash_is_a_balance_at_each_quarter_end(runtime) -> None:  # type: ignore[no-untyped-def]
    (answer,) = ask(runtime, "Apple cash last 4 quarters")
    assert column_of(answer, "Cash and equivalents") == [
        "$39.54 B",
        "$45.57 B",
        "$45.32 B",
        "$35.93 B",
    ]


def test_a_ranking_by_pe_says_what_it_leaves_out(runtime) -> None:  # type: ignore[no-untyped-def]
    (answer,) = ask(runtime, "Rank tech companies by P/E")
    assert column_of(answer, "Ticker")[:2] == ["AMD", "PLTR"]
    assert any(
        banner.startswith("Ordered by P/E ratio.") and "a higher P/E ratio" in banner
        for banner in answer.banners
    )


# Open items from round 4


def test_a_word_from_one_option_answers_the_clarify(runtime) -> None:  # type: ignore[no-untyped-def]
    answers = ask(runtime, "Apple revenue", "add Google margin", "net")
    assert column_of(answers[2], "Ticker") == ["AAPL", "GOOG"]
    assert answers[2].table is not None and "Net margin" in answers[2].table.headers


def test_a_clarified_question_about_another_company_starts_over(runtime) -> None:  # type: ignore[no-untyped-def]
    answers = ask(runtime, "Microsoft revenue", "Apple margin", "2")
    assert answers[2].fact_card is not None
    assert (answers[2].fact_card.ticker, answers[2].fact_card.metric_header) == (
        "AAPL",
        "Operating margin",
    )


def test_a_company_outside_the_snapshot_gets_its_ticker_chip(runtime) -> None:  # type: ignore[no-untyped-def]
    assert replay(runtime, "Tesla vs GM revenue").chips[:2] == ("TSLA", "GM")


def test_reusing_fetched_figures_is_not_announced(runtime) -> None:  # type: ignore[no-untyped-def]
    answers = ask(runtime, "Apple revenue", "add net margin")
    assert not any("fetched earlier" in banner for banner in answers[1].banners)


def test_cash_a_year_earlier_comes_from_that_quarter_s_own_filing(runtime) -> None:  # type: ignore[no-untyped-def]
    # Apple's 10-Q balance sheet compares with the fiscal year-end, so the June
    # 2025 cash ($36.27 B) is read as first filed in that summer's 10-Q (ADR 0009).
    (answer,) = ask(runtime, "Apple cash")
    assert answer.fact_card is not None
    year, quarter = answer.fact_card.changes
    assert year.label == "▲9.0% YoY"
    assert year.title.startswith("Against $36.27 B for At Jun 28, 2025, as first filed in 10-Q")
    assert quarter.label == "▼13.2% QoQ"


def test_a_comparative_still_comes_first_for_a_quarter_s_results(runtime) -> None:  # type: ignore[no-untyped-def]
    (answer,) = ask(runtime, "Apple revenue")
    assert answer.fact_card is not None
    year = answer.fact_card.changes[0]
    assert year.label == "▲16.4% YoY"
    assert year.title.endswith("as 10-Q 0000320193-26-000020 reports it")


def test_a_company_outside_the_snapshot_is_resolved_to_its_cik_before_any_lookup(runtime) -> None:  # type: ignore[no-untyped-def]
    # CONTEXT.md: resolved means CIKs. Tesla is not in the recorded snapshot, so
    # SEC's ticker map names it, before any of its facts are read.
    from financial_analyst_agent.graph.analysis_spec import SpecDraft, resolve_spec
    from financial_analyst_agent.graph.spec_turn import sec_identity

    draft = SpecDraft(company_queries=("Tesla", "Acme Widgets"), metrics=("revenue",))
    tesla, acme = resolve_spec(
        draft, ranking=runtime.ranking, identify=sec_identity(runtime)
    ).companies

    assert (tesla.cik, tesla.ticker, tesla.query) == ("0001318605", "TSLA", "Tesla")
    # A name SEC does not know stays a name; its cells say it was not found.
    assert (acme.cik, acme.handle) == ("", "Acme Widgets")


def test_a_market_figure_for_a_company_the_snapshot_lacks_says_so(runtime) -> None:  # type: ignore[no-untyped-def]
    (answer,) = ask(runtime, "Apple vs Tesla market cap")

    assert answer.table is not None
    assert answer.table.rows[1][:3] == ("Tesla, Inc.", "TSLA", "Not in the market snapshot")
