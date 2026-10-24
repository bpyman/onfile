"""Management's explanation: the MD&A paragraphs that explain a figure's move, chosen by code."""

import json
import os
import subprocess
import sys
from functools import cache
from pathlib import Path

import pytest

from financial_analyst_agent.explanation import (
    explained_metrics,
    is_about_another_metric,
    management_explanation,
    mentions_metric,
)
from financial_analyst_agent.filing_change import (
    extract_section,
    filing_anchor_url,
    section_paragraphs,
)
from financial_analyst_agent.providers.sec.urls import build_filing_document_url

RECORDINGS = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "financial_analyst_agent"
    / "data"
    / "sec_fixture_recordings.json"
)


@cache
def _documents() -> dict[str, str]:
    documents: dict[str, str] = json.loads(RECORDINGS.read_text(encoding="utf-8"))[
        "filing_documents"
    ]
    return documents


def _recorded(document: str) -> tuple[str, str]:
    """A recorded filing's HTML and its EDGAR URL, by primary document name."""
    key = next(key for key in sorted(_documents()) if key.endswith(f":{document}"))
    cik, accession, name = key.split(":")
    return _documents()[key], build_filing_document_url(cik, accession, name)


def _first(document: str, metric: str, basis: str | None = None) -> str:
    html, url = _recorded(document)
    explanation = management_explanation(html, metric, basis, url)  # type: ignore[arg-type]
    assert explanation.paragraphs, explanation.reason
    return explanation.paragraphs[0].text


def _mda(*paragraphs: str) -> str:
    body = "".join(f"<p>{paragraph}</p>" for paragraph in paragraphs)
    return (
        "<html><body><div>Item 2. Management's Discussion and Analysis of Financial "
        f"Condition and Results of Operations</div>{body}"
        "<div>Item 3. Quantitative and Qualitative Disclosures About Market Risk</div>"
        "<p>Not meaningful.</p></body></html>"
    )


URL = "https://www.sec.gov/Archives/edgar/data/1/000000000126000001/x-20260630.htm"


def test_apple_gross_margin_starts_with_the_product_mix() -> None:
    assert "different mix of products" in _first("aapl-20260627.htm", "gross_margin")


def test_micron_gross_margin_starts_with_dram_and_nand_margins() -> None:
    first = _first("mu-20260528.htm", "gross_margin")
    assert "improvements in margins for both DRAM and NAND" in first


def test_pfizer_revenue_starts_with_total_revenues() -> None:
    assert "Total revenues increased" in _first("pfe-20260628.htm", "revenue")


def test_amd_gross_margin_puts_no_operating_income_paragraph_first() -> None:
    first = _first("amd-20260627.htm", "gross_margin")
    assert not is_about_another_metric(first, "gross_margin")
    # Pinned: the quarter's gross margin, and its cause (the absent MI308 charges, the mix).
    assert first.startswith("Gross margin for the three months ended June 27, 2026 was 54%")


def test_the_basis_asked_picks_the_comparison_that_matches_it() -> None:
    sequential = _first("mu-20260528.htm", "gross_margin", "sequential")
    year_over_year = _first("mu-20260528.htm", "gross_margin", "year_over_year")
    assert "from 74% for the second quarter of 2026" in sequential
    assert "from 38% for the third quarter of 2025" in year_over_year


def test_each_paragraph_is_verbatim_with_its_cause_and_link() -> None:
    html, url = _recorded("aapl-20260627.htm")
    explanation = management_explanation(html, "gross_margin", None, url)
    paragraphs = section_paragraphs(extract_section(html, "mda"))
    assert 1 <= len(explanation.paragraphs) <= 3
    assert explanation.reason is None
    for chosen in explanation.paragraphs:
        assert chosen.text in paragraphs
        assert chosen.url == filing_anchor_url(url, chosen.text)
        assert chosen.cause is not None
        start, end = chosen.cause
        assert chosen.text[start:end].startswith("primarily due to")
    scores = [chosen.score for chosen in explanation.paragraphs]
    assert scores == sorted(scores, reverse=True)


def test_a_document_with_no_mda_says_so() -> None:
    html = "<html><body><div>Item 1. Financial Statements</div><p>Tables.</p></body></html>"
    explanation = management_explanation(html, "revenue", None, URL)
    assert explanation.paragraphs == ()
    assert explanation.reason == "mda_not_found"


def test_an_mda_that_does_not_discuss_the_metric_says_so() -> None:
    html = _mda(
        "Revenue increased 5% compared to the same period last year, primarily due to "
        "higher volumes in every region."
    )
    explanation = management_explanation(html, "research_and_development", None, URL)
    assert explanation.paragraphs == ()
    assert explanation.reason == "not_discussed"


def test_naming_the_metric_without_a_change_or_cause_is_not_an_explanation() -> None:
    html = _mda("Gross margin is defined as revenue less cost of sales, divided by revenue.")
    explanation = management_explanation(html, "gross_margin", None, URL)
    assert explanation.reason == "not_discussed"


def test_the_change_must_be_said_of_the_metric() -> None:
    html = _mda(
        "Gross margin is a key measure we track. We sell in many regions. Customer demand "
        "increased in every region, driven by new products."
    )
    explanation = management_explanation(html, "gross_margin", None, URL)
    assert explanation.reason == "not_discussed"


def test_a_causal_clause_runs_past_an_abbreviation() -> None:
    html = _mda(
        "Gross margin increased in the quarter, primarily driven by the absence of charges "
        "related to the U.S. government export control. Revenue also rose."
    )
    chosen = management_explanation(html, "gross_margin", None, URL).paragraphs[0]
    assert chosen.cause is not None
    assert chosen.text[chosen.cause[0] : chosen.cause[1]] == (
        "primarily driven by the absence of charges related to the U.S. government export control"
    )


def test_a_metric_without_words_gets_no_explanation() -> None:
    html = _mda("Dividends per share increased to $0.26 due to the board's decision.")
    explanation = management_explanation(html, "dividends_per_share", None, URL)
    assert explanation.paragraphs == ()
    assert explanation.reason == "metric_not_covered"
    assert "dividends_per_share" not in explained_metrics()


def test_a_paragraph_mostly_about_another_metric_is_never_shown() -> None:
    about_operating_income = (
        "Operating income increased to $2.0 billion compared to the prior year period. The "
        "increase in operating income was primarily due to higher gross profit, partially "
        "offset by higher operating expenses. Operating income rose in every segment."
    )
    about_gross_margin = "Gross margin increased to 54% in the second quarter."
    html = _mda(about_operating_income, about_gross_margin)
    explanation = management_explanation(html, "gross_margin", None, URL)
    assert [chosen.text for chosen in explanation.paragraphs] == [about_gross_margin]
    assert is_about_another_metric(about_operating_income, "gross_margin")
    assert not is_about_another_metric(about_gross_margin, "gross_margin")
    # With nothing about gross margin, the MD&A does not discuss it: no fallback.
    alone = management_explanation(_mda(about_operating_income), "gross_margin", None, URL)
    assert alone.paragraphs == () and alone.reason == "not_discussed"


def test_on_a_tie_the_metric_named_first_is_the_subject() -> None:
    cash = (
        "Cash provided by operating activities increased in the first half compared to the "
        "first half of last year due to higher revenue."
    )
    assert is_about_another_metric(cash, "revenue")


def test_a_first_sentence_about_another_metric_makes_it_the_subject() -> None:
    summary = (
        "Total gross margin decreased by 2.0 percentage points. Revenue increased, primarily "
        "driven by higher revenue from products and revenue growth in services."
    )
    # Revenue is named most, but the paragraph opens on gross margin.
    assert is_about_another_metric(summary, "revenue")


def test_the_cost_of_a_line_of_revenue_is_gross_margin_wording() -> None:
    cost = "Cost of energy generation and storage revenue increased $556 million."
    assert mentions_metric(cost, "gross_margin")
    assert not mentions_metric(cost, "revenue")


def test_nvidia_revenue_puts_no_cash_flow_paragraph_first() -> None:
    first = _first("nvda-20260726.htm", "revenue")
    assert not is_about_another_metric(first, "revenue")


def test_sales_general_and_administrative_is_not_revenue() -> None:
    assert not mentions_metric("Sales, general and administrative expenses rose.", "revenue")
    assert mentions_metric(
        "Sales, general and administrative expenses rose.", "selling_general_and_administrative"
    )


def test_non_operating_income_is_not_operating_income() -> None:
    assert not mentions_metric("Our non-operating income, net increased.", "operating_income")


def test_cost_of_sales_is_gross_margin_wording_not_revenue() -> None:
    assert mentions_metric("Cost of sales increased.", "gross_margin")
    assert not mentions_metric("Cost of sales increased.", "revenue")
    assert mentions_metric("Net sales increased.", "revenue")


def test_equal_scores_keep_the_filing_order() -> None:
    first = "Revenue increased 4% in the quarter, driven by higher volumes."
    second = "Revenue increased 3% in the quarter, driven by higher prices."
    explanation = management_explanation(_mda(first, second), "revenue", None, URL)
    assert [chosen.text for chosen in explanation.paragraphs] == [first, second]
    assert explanation.paragraphs[0].score == explanation.paragraphs[1].score


def test_the_company_wide_figure_ranks_above_a_segment_one() -> None:
    segment = "Services revenue increased 4% in the quarter, driven by higher volumes."
    total = "Total revenue increased 4% in the quarter, driven by higher volumes."
    explanation = management_explanation(_mda(segment, total), "revenue", None, URL)
    assert [chosen.text for chosen in explanation.paragraphs] == [total, segment]


def test_no_more_than_three_paragraphs() -> None:
    paragraphs = [f"Revenue increased {n}% in the quarter, driven by demand." for n in range(5)]
    explanation = management_explanation(_mda(*paragraphs), "revenue", None, URL)
    assert len(explanation.paragraphs) == 3


def test_every_ticket_metric_has_words() -> None:
    assert {
        "revenue",
        "gross_margin",
        "gross_profit",
        "operating_income",
        "operating_margin",
        "net_income",
        "research_and_development",
        "selling_general_and_administrative",
    } <= set(explained_metrics())


@pytest.mark.parametrize("metric", ["operating_cash_flow", "capital_expenditure", "free_cash_flow"])
def test_cash_flow_metrics_are_not_covered(metric: str) -> None:
    html = _mda(
        "Net cash provided by operating activities increased $1.2 billion in the quarter "
        "compared to the prior year quarter, primarily due to higher net income. Capital "
        "expenditures increased, driven by investment in new plants."
    )
    explanation = management_explanation(html, metric, "year_over_year", URL)
    assert explanation.paragraphs == ()
    assert explanation.reason == "metric_not_covered"
    assert metric not in explained_metrics()


YEAR_OVER_YEAR = (
    "Revenue for the third quarter of 2026 increased 12% compared to the third quarter of "
    "2025, primarily due to higher volumes in every region."
)
SEQUENTIAL = (
    "Revenue for the third quarter of 2026 increased 4% compared to the second quarter of "
    "2026, primarily due to higher prices."
)


def test_a_sequential_question_never_gets_a_year_over_year_only_paragraph() -> None:
    unnamed = "Revenue increased 12% in the quarter, primarily due to higher volumes."
    html = _mda(YEAR_OVER_YEAR, unnamed, SEQUENTIAL)
    explanation = management_explanation(html, "revenue", "sequential", URL)
    assert [chosen.text for chosen in explanation.paragraphs] == [SEQUENTIAL]


def test_the_sequential_half_of_a_sentence_giving_both_counts() -> None:
    both = (
        "Data Center revenue was up 117% from a year ago and up 18% sequentially, driven by "
        "demand for our Blackwell platform."
    )
    explanation = management_explanation(_mda(YEAR_OVER_YEAR, both), "revenue", "sequential", URL)
    assert [chosen.text for chosen in explanation.paragraphs] == [both]


def test_a_year_over_year_question_drops_a_sequential_only_paragraph() -> None:
    unnamed = "Revenue increased 12% in the quarter, primarily due to higher volumes."
    html = _mda(SEQUENTIAL, unnamed, YEAR_OVER_YEAR)
    explanation = management_explanation(html, "revenue", "year_over_year", URL)
    assert {chosen.text for chosen in explanation.paragraphs} == {YEAR_OVER_YEAR, unnamed}


def test_a_sequential_question_with_only_year_over_year_causes_offers_them() -> None:
    explanation = management_explanation(_mda(YEAR_OVER_YEAR), "revenue", "sequential", URL)
    assert explanation.paragraphs == ()
    assert explanation.reason == "basis_not_discussed"
    assert [chosen.text for chosen in explanation.alternative] == [YEAR_OVER_YEAR]
    # With nothing for either basis, it is plainly not discussed.
    nothing = management_explanation(
        _mda("Research and development expenses increased, driven by higher headcount."),
        "revenue",
        "sequential",
        URL,
    )
    assert nothing.reason == "not_discussed" and nothing.alternative == ()


def test_a_cause_only_for_the_year_to_date_is_out() -> None:
    year_to_date = (
        "Total revenue for the first nine months of 2026 increased 203% as compared to the "
        "first nine months of 2025, primarily due to higher sales of DRAM."
    )
    quarter_flat = (
        "Revenue was flat in the third quarter of 2026 compared to the third quarter of "
        "2025. Revenue increased during the first nine months of 2026 primarily due to a "
        "different mix of services."
    )
    explanation = management_explanation(_mda(year_to_date, quarter_flat), "revenue", None, URL)
    assert explanation.reason == "not_discussed"


def test_a_year_to_date_cause_said_to_apply_to_the_quarter_counts() -> None:
    both = (
        "Revenue for the three months ended June 30, 2026 was $5.0 billion, and for the six "
        "months ended June 30, 2026 was $9.8 billion. The increase in both periods was "
        "primarily due to higher volumes."
    )
    three_and_six = (
        "Research and development expenses increased 14 percent and 21 percent for the "
        "three and six months ended June 30, 2026, respectively, driven by investment."
    )
    assert management_explanation(_mda(both), "revenue", None, URL).paragraphs
    rd = management_explanation(_mda(three_and_six), "research_and_development", None, URL)
    assert rd.paragraphs


@pytest.mark.parametrize(
    "block",
    [
        "Cost of products sold",
        "Gross margin increased to 54%.",
        "Higher gross margin on a richer mix of data center products and lower costs",
        "Increase in gross margin for the three months ended June 30, 2026",
    ],
)
def test_a_heading_or_a_block_without_a_verb_is_never_chosen(block: str) -> None:
    explanation = management_explanation(_mda(block), "gross_margin", None, URL)
    assert explanation.reason == "not_discussed"


def test_a_sentence_of_eight_words_with_a_verb_can_be_chosen() -> None:
    sentence = "Gross margin increased to 54% in the quarter."
    assert management_explanation(_mda(sentence), "gross_margin", None, URL).paragraphs


@pytest.mark.parametrize(
    "paragraph",
    [
        "Cash and cash equivalents increased $2.1 billion during the quarter, primarily due "
        "to net cash provided by operating activities and higher revenue.",
        "Net cash provided by financing activities increased in the quarter compared to the "
        "prior year quarter, primarily due to debt issued, partially offset by revenue "
        "declines in the quarter.",
        "Our liquidity remains strong: revenue increased in the quarter, driven by demand, "
        "and our liquidity is supported by our credit facility.",
    ],
)
def test_a_cash_balance_or_financing_paragraph_is_about_another_metric(paragraph: str) -> None:
    for metric in ("revenue", "net_income", "operating_income"):
        assert is_about_another_metric(paragraph, metric)
    assert management_explanation(_mda(paragraph), "revenue", None, URL).reason == "not_discussed"


_HASH_PROBE = """
import json, sys
from financial_analyst_agent.explanation import management_explanation
docs = json.load(open(sys.argv[1], encoding="utf-8"))["filing_documents"]
html = next(v for k, v in sorted(docs.items()) if k.endswith(":amd-20260627.htm"))
result = management_explanation(html, "gross_margin", "year_over_year", "u")
print(json.dumps([[p.text, p.score, p.cause] for p in result.paragraphs]))
"""


@pytest.mark.parametrize("seeds", [("0", "1")])
def test_the_result_does_not_depend_on_hash_ordering(seeds: tuple[str, str]) -> None:
    outputs = []
    for seed in seeds:
        env = {**os.environ, "PYTHONHASHSEED": seed}
        completed = subprocess.run(
            [sys.executable, "-c", _HASH_PROBE, str(RECORDINGS)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=env,
            check=True,
        )
        outputs.append(completed.stdout)
    assert outputs[0] == outputs[1]
    assert json.loads(outputs[0])
