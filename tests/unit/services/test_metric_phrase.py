import pytest

from financial_analyst_agent.contracts import ALLOWED_METRICS
from financial_analyst_agent.domain.errors import UnknownMetricError
from financial_analyst_agent.services.metric_catalog import (
    parse_metric,
    resolve_metric_phrase,
    resolve_metric_phrases,
    without_trailing_year_words,
)


def test_profit_is_ambiguous_among_profit_concepts() -> None:
    resolved = resolve_metric_phrase("What was Google's profit?")
    assert resolved.kind == "ambiguous"
    assert resolved.candidates == ("gross_profit", "operating_income", "net_income")


def test_profit_margin_is_net_margin() -> None:
    resolved = resolve_metric_phrase("What was Google's profit margin?")
    assert resolved.kind == "unique"
    assert resolved.metric == "net_margin"


def test_gross_and_operating_profit_margin_name_their_margins() -> None:
    assert resolve_metric_phrase("Google gross profit margin").metric == "gross_margin"
    assert resolve_metric_phrase("Google operating profit margin").metric == "operating_margin"


def test_margin_alone_is_ambiguous_among_margins() -> None:
    resolved = resolve_metric_phrase("What was Google's margin?")
    assert resolved.kind == "ambiguous"
    assert resolved.candidates == ("gross_margin", "operating_margin", "net_margin")


def test_gross_profit_is_unique_catalog_name() -> None:
    resolved = resolve_metric_phrase(
        "What was Google's gross profit based on their latest quarterly report?"
    )
    assert resolved.kind == "unique"
    assert resolved.metric == "gross_profit"


def test_net_income_is_unique_catalog_name() -> None:
    resolved = resolve_metric_phrase(
        "What was Google's net income based on their latest quarterly report?"
    )
    assert resolved.kind == "unique"
    assert resolved.metric == "net_income"


def test_net_margin_is_unique_catalog_name() -> None:
    resolved = resolve_metric_phrase("Shopify net margin")
    assert resolved.kind == "unique"
    assert resolved.metric == "net_margin"


def test_revenue_is_unique_catalog_name() -> None:
    resolved = resolve_metric_phrase("What was Google's revenue?")
    assert resolved.kind == "unique"
    assert resolved.metric == "revenue"


def test_income_is_ambiguous_not_net_income() -> None:
    resolved = resolve_metric_phrase("What was Google's income?")
    assert resolved.kind == "ambiguous"
    assert resolved.candidates == ("net_income", "operating_income")


def test_reported_income_is_ambiguous() -> None:
    resolved = resolve_metric_phrase(
        "What are the top 10 healthcare companies and the reported income for each?"
    )
    assert resolved.kind == "ambiguous"
    assert resolved.candidates == ("net_income", "operating_income")


def test_operating_profit_is_unique_operating_income() -> None:
    resolved = resolve_metric_phrase("What was Google's operating profit?")
    assert resolved.kind == "unique"
    assert resolved.metric == "operating_income"


def test_operating_alone_is_unknown() -> None:
    resolved = resolve_metric_phrase(
        "What was Google's operating based on their latest quarterly report?"
    )
    assert resolved.kind == "unknown"


def test_earnings_alias_is_unique_net_income() -> None:
    resolved = resolve_metric_phrase("What was Google's earnings?")
    assert resolved.kind == "unique"
    assert resolved.metric == "net_income"


def test_sales_alias_is_unique_revenue() -> None:
    resolved = resolve_metric_phrase("What was Google's sales?")
    assert resolved.kind == "unique"
    assert resolved.metric == "revenue"


def test_cost_of_sales_is_unique_cost_of_revenue() -> None:
    resolved = resolve_metric_phrase("What was Google's cost of sales?")
    assert resolved.kind == "unique"
    assert resolved.metric == "cost_of_revenue"


def test_ebit_alias_is_unique_operating_income() -> None:
    resolved = resolve_metric_phrase("What was Google's EBIT?")
    assert resolved.kind == "unique"
    assert resolved.metric == "operating_income"


def test_ebitda_is_a_catalog_formula() -> None:
    resolved = resolve_metric_phrase("What was Google's EBITDA?")
    assert (resolved.kind, resolved.metric) == ("unique", "ebitda")


def test_several_distinct_catalog_metrics_resolve_in_order() -> None:
    phrases = resolve_metric_phrases("Compare Google revenue and net income")
    assert [p.kind for p in phrases] == ["unique", "unique"]
    assert [p.metric for p in phrases] == ["revenue", "net_income"]


def test_colliding_phrase_beside_unique_stays_ambiguous() -> None:
    phrases = resolve_metric_phrases("Compare Google revenue and profit")
    assert len(phrases) == 2
    assert phrases[0].kind == "unique"
    assert phrases[0].metric == "revenue"
    assert phrases[1].kind == "ambiguous"
    assert phrases[1].candidates == ("gross_profit", "operating_income", "net_income")


def test_resolve_metric_phrase_multi_unique_is_not_ambiguous() -> None:
    resolved = resolve_metric_phrase("Compare Google revenue and operating margin")
    assert resolved.kind == "unique"
    assert resolved.metrics == ("revenue", "operating_margin")
    assert resolved.candidates == ()


def test_roa_is_unknown() -> None:
    resolved = resolve_metric_phrase(
        "What was Google's ROA based on their latest quarterly report?"
    )
    assert resolved.kind == "unknown"


def test_costs_is_unknown() -> None:
    resolved = resolve_metric_phrase(
        "What was Google's costs based on their latest quarterly report?"
    )
    assert resolved.kind == "unknown"


def test_operating_margins_plural_is_unique_operating_margin() -> None:
    resolved = resolve_metric_phrase("Compare Microsoft and Google operating margins")
    assert resolved.kind == "unique"
    assert resolved.metric == "operating_margin"


def test_research_and_development_is_unique() -> None:
    resolved = resolve_metric_phrase("What was Google's research and development?")
    assert resolved.kind == "unique"
    assert resolved.metric == "research_and_development"


def test_rd_abbreviation_is_unique_research_and_development() -> None:
    resolved = resolve_metric_phrase("What was Google's R&D?")
    assert resolved.kind == "unique"
    assert resolved.metric == "research_and_development"


def test_rd_spend_is_unique_research_and_development() -> None:
    resolved = resolve_metric_phrase("Top 10 tech companies R&D spend")
    assert resolved.kind == "unique"
    assert resolved.metric == "research_and_development"


def test_sga_abbreviation_is_unique() -> None:
    resolved = resolve_metric_phrase("What was Google's SG&A?")
    assert resolved.kind == "unique"
    assert resolved.metric == "selling_general_and_administrative"


def test_interest_expense_is_unique() -> None:
    resolved = resolve_metric_phrase("What was Google's interest expense?")
    assert resolved.kind == "unique"
    assert resolved.metric == "interest_expense"


def test_interest_alone_is_ambiguous() -> None:
    resolved = resolve_metric_phrase("What was Google's interest?")
    assert resolved.kind == "ambiguous"
    assert resolved.candidates == ("interest_expense", "interest_coverage")


def test_income_tax_is_unique_tax_expense() -> None:
    resolved = resolve_metric_phrase("What was Google's income tax?")
    assert resolved.kind == "unique"
    assert resolved.metric == "income_tax_expense"


def test_tax_alone_is_ambiguous() -> None:
    resolved = resolve_metric_phrase("What was Google's tax?")
    assert resolved.kind == "ambiguous"
    assert resolved.candidates == ("income_tax_expense", "effective_tax_rate")


def test_pretax_income_is_unique() -> None:
    resolved = resolve_metric_phrase("What was Google's pretax income?")
    assert resolved.kind == "unique"
    assert resolved.metric == "pretax_income"


def test_rd_to_sales_is_unique() -> None:
    resolved = resolve_metric_phrase("What was Google's R&D to sales?")
    assert resolved.kind == "unique"
    assert resolved.metric == "rd_to_sales"


def test_effective_tax_rate_is_unique() -> None:
    resolved = resolve_metric_phrase("What was Google's effective tax rate?")
    assert resolved.kind == "unique"
    assert resolved.metric == "effective_tax_rate"


def test_net_interest_income_is_unique_not_ambiguous_interest() -> None:
    # Neither "net", "interest" nor "income" is read on its own (ADR 0004).
    resolved = resolve_metric_phrase("Bank of America's net interest income")
    assert resolved.kind == "unique"
    assert resolved.metric == "net_interest_income"
    assert "net_interest_income" in ALLOWED_METRICS


def test_nii_is_net_interest_income() -> None:
    # The standard abbreviation, read as EPS, FCF and ROE are.
    resolved = resolve_metric_phrase("What was JPMorgan's NII?")
    assert resolved.kind == "unique"
    assert resolved.metric == "net_interest_income"


@pytest.mark.parametrize(
    ("phrase", "metric"),
    [
        ("income from operations", "operating_income"),
        ("income taxes", "income_tax_expense"),
        ("income before taxes", "pretax_income"),
        ("income before income taxes", "pretax_income"),
        ("earnings before tax", "pretax_income"),
        ("pretax earnings", "pretax_income"),
        ("noninterest income", "noninterest_income"),
        ("non-interest income", "noninterest_income"),
        ("selling, general and administrative expenses", "selling_general_and_administrative"),
        ("SG&A expenses", "selling_general_and_administrative"),
        ("R&D expenses", "research_and_development"),
        ("research and development expense", "research_and_development"),
        ("interest expenses", "interest_expense"),
        ("total equity", "total_equity"),
        ("equity including noncontrolling interests", "total_equity"),
        ("times interest earned", "interest_coverage"),
        ("earnings before interest and taxes", "operating_income"),
        ("earnings before interest, taxes, depreciation and amortization", "ebitda"),
    ],
)
def test_a_longer_phrase_names_its_metric_not_its_ambiguous_word(phrase: str, metric: str) -> None:
    # The longest span that names one metric wins over "income", "tax",
    # "interest", "expenses", "equity" or "earned" inside it (ADR 0004).
    resolved = resolve_metric_phrase(f"What was the company's {phrase}?")
    assert resolved.kind == "unique"
    assert resolved.metric == metric
    assert metric in ALLOWED_METRICS


@pytest.mark.parametrize("word", ["income", "interest", "expenses", "equity", "tax"])
def test_the_ambiguous_word_alone_still_asks(word: str) -> None:
    assert resolve_metric_phrase(f"What was the company's {word}?").kind == "ambiguous"


def test_interest_coverage_is_unique() -> None:
    resolved = resolve_metric_phrase("What was Google's interest coverage?")
    assert resolved.kind == "unique"
    assert resolved.metric == "interest_coverage"


def test_market_cap_is_unique() -> None:
    resolved = resolve_metric_phrase("What was Google's market cap?")
    assert resolved.kind == "unique"
    assert resolved.metric == "market_cap"


def test_market_alone_is_unknown() -> None:
    resolved = resolve_metric_phrase("What was Google's market?")
    assert resolved.kind == "unknown"


@pytest.mark.parametrize("metric", ALLOWED_METRICS)
def test_catalog_slug_is_unique(metric: str) -> None:
    resolved = resolve_metric_phrase(f"What was Google's {metric}?")
    assert resolved.kind == "unique"
    assert resolved.metric == metric


def test_parse_metric_unknown_raises_unknown_metric_error() -> None:
    with pytest.raises(UnknownMetricError):
        parse_metric("roe")


@pytest.mark.parametrize(
    ("phrase", "metric"),
    [
        ("R&D as a percentage of revenue", "rd_to_sales"),
        ("SG&A as a percentage of sales", "sga_ratio"),
        ("research and development as a share of revenue", "rd_to_sales"),
        ("SG&A expenses as a percent of net sales", "sga_ratio"),
        ("R&D as % of revenue", "rd_to_sales"),
        ("gross profit as a percentage of revenue", "gross_margin"),
        ("operating income as a share of sales", "operating_margin"),
        ("net income as a percentage of total revenue", "net_margin"),
    ],
)
def test_a_figure_as_a_percentage_of_revenue_is_its_ratio(phrase: str, metric: str) -> None:
    resolved = resolve_metric_phrase(f"What was the company's {phrase}?")
    assert resolved.kind == "unique"
    assert resolved.metrics == (metric,)


def test_a_figure_without_a_ratio_shows_both_figures() -> None:
    # The catalog has no capex-to-sales ratio: the two figures, side by side.
    resolved = resolve_metric_phrase("What was the company's capex as a percentage of revenue?")
    assert resolved.metrics == ("capital_expenditure", "revenue")


@pytest.mark.parametrize(
    "phrase",
    [
        "TTM net income",
        "LTM net income",
        "trailing twelve month net income",
        "trailing twelve months net income",
        "trailing 12-month net income",
        "TTM earnings",
        "ttm net profit",
        "last twelve months net income",
        "last 12 months net income",
        "past twelve months net income",
    ],
)
def test_trailing_twelve_months_before_net_income_is_its_trailing_year(phrase: str) -> None:
    resolved = resolve_metric_phrase(f"What was Apple's {phrase}?")
    assert resolved.kind == "unique"
    assert resolved.metrics == ("net_income_ttm",)


def test_trailing_twelve_months_before_a_figure_without_a_trailing_year_keeps_the_figure() -> None:
    # Only net income has a trailing-year form; TTM revenue is a window of quarters.
    assert resolve_metric_phrase("Apple TTM revenue").metrics == ("revenue",)


def test_trailing_year_words_name_the_words_a_trailing_year_figure_takes() -> None:
    assert without_trailing_year_words("Apple TTM net income") == "Apple net income"
    assert without_trailing_year_words("Apple TTM revenue") == "Apple TTM revenue"
    assert (
        without_trailing_year_words("pfizer's last twelve months net income")
        == "pfizer's net income"
    )


def test_last_twelve_months_after_the_metric_is_a_window_not_the_trailing_year() -> None:
    # Spelled out before the metric, "last twelve months" is LTM; after it, a span.
    question = "pfizer net income over the last twelve months"
    assert resolve_metric_phrase(question).metrics == ("net_income",)
    assert without_trailing_year_words(question) == question
