from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest

from financial_analyst_agent.contracts import (
    ComponentProvenance,
    DisclosureChange,
    Intent,
    NewsHit,
    RendererKind,
    TableRow,
    ToolTrace,
    TurnResult,
)
from financial_analyst_agent.presentation import (
    format_chart_amount,
    format_datetime_utc,
    format_field_name,
    format_metric_value,
    format_percent,
    format_reason,
    format_usd,
    metric_groups,
    present_turn,
    try_parse_datetime,
)
from financial_analyst_agent.prose import format_date


def test_format_usd_billions_half_up() -> None:
    assert format_usd(Decimal("112193000000")) == "$112.19 B"


def test_format_usd_compact_tie_rounds_half_up() -> None:
    assert format_usd(Decimal("1005000")) == "$1.01 M"
    assert format_usd(Decimal("112195000000")) == "$112.20 B"


def test_format_usd_alphabet_net_income() -> None:
    assert format_usd(Decimal("62578000000")) == "$62.58 B"


def test_format_usd_exact_hundreds_of_billions() -> None:
    assert format_usd(Decimal("800000000000")) == "$800.00 B"


def test_format_usd_under_one_million_uses_thousands() -> None:
    # One scale for every amount: "$500.00 K" beside "$1.00 M", not "$500,000".
    assert format_usd(Decimal("500000")) == "$500.00 K"
    assert format_usd(Decimal("950")) == "$950"


def test_format_usd_one_million_uses_suffix() -> None:
    assert format_usd(Decimal("1000000")) == "$1.00 M"


def test_format_usd_one_trillion() -> None:
    assert format_usd(Decimal("1000000000000")) == "$1.00 T"


def test_format_usd_zero() -> None:
    assert format_usd(Decimal("0")) == "$0"


def test_format_usd_negative() -> None:
    assert format_usd(Decimal("-1500000000")) == "-$1.50 B"


def test_format_date_has_no_leading_zero() -> None:
    assert format_date(date(2026, 1, 1)) == "Jan 1, 2026"
    assert format_date(date(2020, 6, 30)) == "Jun 30, 2020"


def test_format_datetime_utc_drops_seconds() -> None:
    stamp = datetime(2026, 8, 17, 16, 0, 0, tzinfo=UTC)
    assert format_datetime_utc(stamp) == "Aug 17, 2026, 4:00 PM UTC"


def test_format_datetime_utc_converts_offset_and_drops_microseconds() -> None:
    stamp = datetime.fromisoformat("2026-08-18T05:10:30.074615-04:00")
    assert format_datetime_utc(stamp) == "Aug 18, 2026, 9:10 AM UTC"


def test_format_percent_one_decimal_half_up() -> None:
    ratio = Decimal("38398000000") / Decimal("82886000000")
    assert format_percent(ratio) == "46.3%"


def test_format_percent_tie_rounds_half_up() -> None:
    assert format_percent(Decimal("0.46350")) == "46.4%"


def test_format_metric_value_formats_interest_coverage_as_multiple() -> None:
    assert format_metric_value("interest_coverage", Decimal("12.46")) == "12.5x"
    assert format_metric_value("rd_to_sales", Decimal("0.123")) == "12.3%"


def test_format_field_name_is_human_readable() -> None:
    assert format_field_name("company_name") == "Company"
    assert format_field_name("cik") == "CIK"
    assert format_field_name("net_income") == "Net income"
    assert format_field_name("rank") == "Rank"


def test_format_reason_domain_first() -> None:
    assert format_reason("missing_fact") == "Missing fact"
    assert format_reason("period_mismatch") == "Period mismatch"
    assert format_reason("ambiguous_concept") == "Ambiguous concept"
    assert format_reason("zero_denominator") == "Not meaningful (zero base)"
    assert format_reason("not_reported_for_quarter") == "Reported for the year only"


def test_format_metric_value_blank_when_missing() -> None:
    assert format_metric_value("net_income", None) == ""


def test_format_metric_value_margin_is_percent() -> None:
    ratio = Decimal("39696000000") / Decimal("109896000000")
    assert format_metric_value("operating_margin", ratio) == "36.1%"


def test_format_chart_amount_matches_table_compact_units() -> None:
    assert format_chart_amount("revenue", 82_886_000_000) == "$82.89 B"
    assert format_chart_amount("net_margin", "0.245") == "24.5%"
    assert format_chart_amount("interest_coverage", "12.3") == "12.3x"
    assert format_chart_amount("revenue", float("nan")) == ""


def test_format_metric_value_reported_is_usd() -> None:
    assert format_metric_value("net_income", Decimal("62578000000")) == "$62.58 B"


def test_format_metric_value_market_cap_is_usd() -> None:
    assert format_metric_value("market_cap", Decimal("800000000000")) == "$800.00 B"


def test_try_parse_datetime_iso() -> None:
    parsed = try_parse_datetime("2026-08-17T16:00:00+00:00")
    assert parsed is not None
    assert format_datetime_utc(parsed) == "Aug 17, 2026, 4:00 PM UTC"


def test_try_parse_datetime_unparseable_is_none() -> None:
    assert try_parse_datetime("yesterday morning") is None


def _lookup_result() -> TurnResult:
    return TurnResult(
        intent=Intent.LOOKUP,
        renderer=RendererKind.TABLE,
        tool_traces=[
            ToolTrace(
                tool="get_financials",
                args={"company": "Google", "metric": "net_income"},
                provenance={
                    "form": "10-Q",
                    "accession_number": "0001652044-26-000048",
                    "taxonomy": "us-gaap",
                    "concept": "NetIncomeLoss",
                    "source_url": "https://www.sec.gov/Archives/edgar/data/1652044/000165204426000048/goog-20260331.htm",
                    "start_date": "2026-01-01",
                    "end_date": "2026-03-31",
                    "source": "sec_xbrl",
                },
            )
        ],
        table_rows=[
            TableRow(
                company_name="Alphabet Inc.",
                ticker="GOOG",
                cik="0001652044",
                metric="net_income",
                value=Decimal("62578000000"),
                currency="USD",
                start_date=date(2026, 1, 1),
                end_date=date(2026, 3, 31),
                form="10-Q",
                accession_number="0001652044-26-000048",
                taxonomy="us-gaap",
                concept="NetIncomeLoss",
                source_url="https://www.sec.gov/Archives/edgar/data/1652044/000165204426000048/goog-20260331.htm",
            )
        ],
    )


def test_present_lookup_uses_fact_card_not_table() -> None:
    presented = present_turn(_lookup_result())
    assert presented.intent == "lookup"
    assert presented.table is None
    card = presented.fact_card
    assert card is not None
    assert card.company_name == "Alphabet Inc."
    assert card.ticker == "GOOG"
    assert card.metric_header == "Net income"
    assert card.amount == "$62.58 B"
    assert card.period_label == "Standalone quarter · Jan 1, 2026 – Mar 31, 2026"
    assert card.form == "10-Q"
    assert card.accession_number == "0001652044-26-000048"
    assert card.concept == "NetIncomeLoss"
    assert card.source_url.endswith("goog-20260331.htm")
    trace = presented.traces[0]
    assert dict(trace.inputs) == {
        "Company": "Google",
        "Metric": "Net income",
    }
    assert dict(trace.outputs) == {
        "Form": "10-Q",
        "Accession number": "0001652044-26-000048",
        "Taxonomy": "us-gaap",
        "Concept": "NetIncomeLoss",
        "Start date": "Jan 1, 2026",
        "End date": "Mar 31, 2026",
        "Source": "SEC EDGAR",
        "Source URL": (
            "[www.sec.gov/…/goog-20260331.htm]"
            "(https://www.sec.gov/Archives/edgar/data/1652044/000165204426000048/goog-20260331.htm)"
        ),
    }
    assert "`0001652044-26-000048`" not in dict(trace.outputs)["Accession number"]
    assert all("(" not in label and "_" not in label for label, _ in trace.inputs)
    assert all("(" not in label and "_" not in label for label, _ in trace.outputs)
    assert trace.header == (
        "Looked up Google · Net income in SEC filings "
        "(Jan 1, 2026 – Mar 31, 2026)"
    )


def test_present_lookup_formula_uses_percent_and_component_provenance() -> None:
    result = TurnResult(
        intent=Intent.LOOKUP,
        renderer=RendererKind.TABLE,
        tool_traces=[],
        table_rows=[
            TableRow(
                company_name="Shopify Inc.",
                ticker="SHOP",
                cik="0001594805",
                metric="net_margin",
                value=Decimal("0.1"),
                start_date=date(2026, 1, 1),
                end_date=date(2026, 3, 31),
                components=[
                    ComponentProvenance(
                        metric="net_income",
                        value=Decimal("100"),
                        start_date=date(2026, 1, 1),
                        end_date=date(2026, 3, 31),
                        form="10-Q",
                        accession_number="0001594805-26-000012",
                        taxonomy="us-gaap",
                        concept="NetIncomeLoss",
                        source_url="https://www.sec.gov/Archives/edgar/data/1594805/shop.htm",
                        source="sec_xbrl",
                    ),
                    ComponentProvenance(
                        metric="revenue",
                        value=Decimal("1000"),
                        start_date=date(2026, 1, 1),
                        end_date=date(2026, 3, 31),
                        form="10-Q",
                        accession_number="0001594805-26-000012",
                        taxonomy="us-gaap",
                        concept="RevenueFromContractWithCustomerExcludingAssessedTax",
                        source_url="https://www.sec.gov/Archives/edgar/data/1594805/shop.htm",
                        source="sec_xbrl",
                    ),
                ],
            )
        ],
    )
    presented = present_turn(result)
    assert presented.table is None
    card = presented.fact_card
    assert card is not None
    assert card.metric_header == "Net margin"
    assert card.amount == "10.0%"
    # A calculated card names its inputs; each one's concept and form are in the evidence.
    assert card.period_label.startswith("Calculated · ")
    assert card.form == ""
    assert card.accession_number == "0001594805-26-000012"
    assert card.concept == "Net income ÷ revenue"
    assert card.source_url.endswith("shop.htm")
    evidence = presented.evidence
    assert len(evidence) == 3
    derived, net_income, revenue = evidence
    assert derived.concept == (
        "NetIncomeLoss / RevenueFromContractWithCustomerExcludingAssessedTax"
    )
    assert derived.accession_number == "0001594805-26-000012"
    assert derived.form == "10-Q"
    assert "component" in derived.selection_rule.lower()
    assert net_income.concept == "NetIncomeLoss"
    assert net_income.raw_amount == "100"
    assert net_income.accession_number == "0001594805-26-000012"
    assert net_income.source_url.endswith("shop.htm")
    assert revenue.concept == "RevenueFromContractWithCustomerExcludingAssessedTax"
    assert revenue.raw_amount == "1000"


def test_evidence_inspector_uses_row_specific_selection_rules() -> None:
    result = TurnResult(
        intent=Intent.RANK_AND_LOOKUP,
        renderer=RendererKind.TABLE,
        tool_traces=[],
        table_rows=[
            TableRow(
                company_name="Eli Lilly and Company",
                ticker="LLY",
                cik="0000059478",
                metric="market_cap",
                value=Decimal("800000000000"),
                currency="USD",
            ),
            TableRow(
                company_name="Microsoft Corporation",
                ticker="MSFT",
                cik="0000789019",
                metric="revenue",
                value=Decimal("70000000000"),
                start_date=date(2025, 1, 1),
                end_date=date(2025, 3, 31),
                form="10-Q",
                accession_number="0001193125-25-000099",
                concept="RevenueFromContractWithCustomerExcludingAssessedTax",
                source_url="https://www.sec.gov/Archives/edgar/data/789019/old.htm",
            ),
        ],
    )
    presented = present_turn(result)
    market_cap, quarter = presented.evidence
    assert "snapshot" in market_cap.selection_rule.lower()
    assert "Latest standalone quarterly 10-Q" not in market_cap.selection_rule
    assert "Latest standalone quarterly 10-Q" not in quarter.selection_rule
    assert "10-Q" in quarter.selection_rule
    assert "stated period" in quarter.selection_rule


def test_compare_row_with_its_one_fact_as_component_reads_as_standalone() -> None:
    # compare_metrics carries a plain metric's fact as a single component; that is
    # a reported quarter, not a calculation.
    fact = ComponentProvenance(
        metric="revenue",
        value=Decimal("94036000000"),
        start_date=date(2026, 3, 29),
        end_date=date(2026, 6, 27),
        form="10-Q",
        accession_number="0000320193-26-000020",
        taxonomy="us-gaap",
        concept="RevenueFromContractWithCustomerExcludingAssessedTax",
        source_url="https://www.sec.gov/Archives/edgar/data/320193/000032019326000020/",
        source="sec_companyfacts",
    )
    ratio = fact.model_copy(update={"metric": "net_income", "value": Decimal("23434000000")})
    row = TableRow(
        company_name="Apple Inc.",
        ticker="AAPL",
        cik="0000320193",
        metric="revenue",
        value=fact.value,
        currency="USD",
        start_date=fact.start_date,
        end_date=fact.end_date,
        components=[fact],
    )
    margin = row.model_copy(
        update={"metric": "net_margin", "value": Decimal("0.25"), "components": [ratio, fact]}
    )
    result = TurnResult(
        intent=Intent.COMPARE,
        renderer=RendererKind.TABLE,
        tool_traces=[],
        table_rows=[row, margin],
    )
    rules = {item.label: item.selection_rule for item in present_turn(result).evidence}
    revenue_rule = next(rule for label, rule in rules.items() if "· Revenue ·" in label)
    margin_rule = next(rule for label, rule in rules.items() if "Net margin" in label)
    assert revenue_rule.startswith("Standalone 10-Q fact for the stated period")
    assert "component facts" in margin_rule


def test_present_rank_omits_empty_fact_columns_and_formats_market_cap() -> None:
    result = TurnResult(
        intent=Intent.RANK,
        renderer=RendererKind.TABLE,
        banners=["Universe snapshot as of 2026-08-17T16:00:00+00:00"],
        tool_traces=[
            ToolTrace(
                tool="rank_companies",
                args={"industry": "healthcare", "limit": 10},
                provenance={"snapshot_as_of": "2026-08-17T16:00:00+00:00"},
            )
        ],
        table_rows=[
            TableRow(
                company_name="Eli Lilly and Company",
                ticker="LLY",
                cik="0000059478",
                metric="market_cap",
                rank=1,
                value=Decimal("800000000000"),
                currency="USD",
            )
        ],
    )
    presented = present_turn(result)
    assert presented.fact_card is None
    table = presented.table
    assert table is not None
    assert "rank" in table.keys
    assert "form" not in table.keys
    assert "reason" not in table.keys
    assert table.keys[0] == "rank"
    assert table.headers == (
        "Rank",
        "Company",
        "Ticker",
        "Market cap",
    )
    assert "cik" not in table.keys
    assert "metric" not in table.keys
    assert "accession_number" not in table.keys
    assert all("(" not in header and "_" not in header for header in table.headers)
    rank_index = table.keys.index("rank")
    value_index = table.keys.index("value")
    assert table.rows[0][rank_index] == "1"
    assert table.rows[0][value_index] == "$800.00 B"
    assert presented.banners == ("Universe snapshot as of Aug 17, 2026, 4:00 PM UTC",)


def test_present_compare_formats_percent_and_keeps_reason() -> None:
    result = TurnResult(
        intent=Intent.COMPARE,
        renderer=RendererKind.TABLE,
        tool_traces=[
            ToolTrace(
                tool="compare_metrics",
                args={
                    "issuers": ["Microsoft", "Google"],
                    "metric": "operating_margin",
                },
            )
        ],
        table_rows=[
            TableRow(
                company_name="Microsoft Corporation",
                ticker="MSFT",
                cik="0000789019",
                metric="operating_margin",
                reason="missing_fact",
            ),
            TableRow(
                company_name="Alphabet Inc.",
                ticker="GOOG",
                cik="0001652044",
                metric="operating_margin",
                value=Decimal("39696000000") / Decimal("109896000000"),
                currency="USD",
                start_date=date(2026, 1, 1),
                end_date=date(2026, 3, 31),
            ),
        ],
    )
    presented = present_turn(result)
    table = presented.table
    assert table is not None
    # One metric across companies reads as one row per company; a failed cell
    # shows its reason in the value column, with provenance in the evidence.
    value_index = table.keys.index("value:operating_margin")
    assert table.rows[0][value_index] == "Missing fact"
    assert table.rows[1][value_index] == "36.1%"
    assert table.headers[value_index] == "Operating margin"
    assert table.headers[-1] == "Quarter ended"
    assert "metric" not in table.keys
    assert "Value" not in table.headers
    assert presented.traces[0].header == (
        "Compared Operating margin · Microsoft, Google in SEC filings"
    )


def test_present_news_keeps_unparseable_published() -> None:
    result = TurnResult(
        intent=Intent.NEWS_AND_EXPLAIN,
        renderer=RendererKind.ESSAY,
        essay="Supply chain remains tight.",
        citations=[
            NewsHit(
                title="Hit",
                url="https://example.com/n",
                published="yesterday morning",
            )
        ],
        tool_traces=[ToolTrace(tool="search_news", args={"query": "NVIDIA"})],
    )
    presented = present_turn(result)
    assert presented.citations[0].index == 1
    assert presented.citations[0].published == "yesterday morning"
    assert presented.essay == "Supply chain remains tight."
    assert presented.table is None
    assert presented.fact_card is None


def test_present_news_formats_date_only_published() -> None:
    result = TurnResult(
        intent=Intent.NEWS_AND_EXPLAIN,
        renderer=RendererKind.ESSAY,
        essay="Supply chain remains tight.",
        citations=[
            NewsHit(
                title="Hit",
                url="https://example.com/n",
                published="2026-01-01",
            )
        ],
        tool_traces=[ToolTrace(tool="search_news", args={"query": "NVIDIA"})],
    )
    presented = present_turn(result)
    assert presented.citations[0].index == 1
    assert presented.citations[0].published == "Jan 1, 2026"


def test_present_trace_formats_nested_news_hits_as_readable_lines() -> None:
    result = TurnResult(
        intent=Intent.NEWS_AND_EXPLAIN,
        renderer=RendererKind.ESSAY,
        essay="Supply chain remains tight.",
        tool_traces=[
            ToolTrace(
                tool="search_news",
                args={"query": "NVIDIA"},
                provenance={
                    "hits": [
                        {
                            "title": "First hit",
                            "url": "https://example.com/first",
                            "snippet": "Lead times after $12.3B of demand.",
                            "score": 0.91,
                            "published": "2026-01-01",
                        },
                        {
                            "title": "Second hit",
                            "url": "https://example.com/second",
                            "snippet": "# Go to frontpage\n**The Register**",
                            "published": "yesterday morning",
                        },
                    ]
                },
            )
        ],
    )

    hits = dict(present_turn(result).traces[0].outputs)["Hits"]

    assert hits == (
        "- **[1]** [First hit](https://example.com/first)\n"
        "  - Score: `0.91`\n"
        "  - Published: Jan 1, 2026\n"
        "  - Snippet: Lead times after \\$12.3B of demand.\n"
        "\n"
        "- **[2]** [Second hit](https://example.com/second)\n"
        "  - Published: yesterday morning\n"
        "  - Snippet: \\# Go to frontpage \\*\\*The Register\\*\\*"
    )
    assert "\\# Go to frontpage" in hits
    assert "\\*\\*The Register\\*\\*" in hits


def test_present_trace_keeps_extra_news_hit_fields() -> None:
    result = TurnResult(
        intent=Intent.NEWS_AND_EXPLAIN,
        renderer=RendererKind.ESSAY,
        essay="Supply chain remains tight.",
        tool_traces=[
            ToolTrace(
                tool="search_news",
                args={"query": "NVIDIA"},
                provenance={
                    "hits": [
                        {
                            "title": "First hit",
                            "url": "https://example.com/first",
                            "snippet": "Lead times.",
                            "score": 0.91,
                            "published": "2026-01-01",
                            "source": "The Register",
                            "raw_content": "Go to frontpage. Logo, The Register",
                        }
                    ]
                },
            )
        ],
    )

    hits = dict(present_turn(result).traces[0].outputs)["Hits"]

    assert hits == (
        "- **[1]** [First hit](https://example.com/first)\n"
        "  - Score: `0.91`\n"
        "  - Published: Jan 1, 2026\n"
        "  - Source: The Register\n"
        "  - Snippet: Lead times."
    )
    assert "raw_content" not in hits.casefold()
    assert "Go to frontpage" not in hits


def test_present_formula_trace_lists_each_component_as_provenance_rows() -> None:
    result = TurnResult(
        intent=Intent.LOOKUP,
        renderer=RendererKind.TABLE,
        tool_traces=[
            ToolTrace(
                tool="compare_metrics",
                args={"issuers": ["Shopify"], "metric": "net_margin"},
                provenance={
                    "components": [
                        {
                            "cik": "0001594805",
                            "metric": "net_income",
                            "value": "100000000",
                            "form": "10-Q",
                            "taxonomy": "us-gaap",
                            "source": "sec_xbrl",
                            "accession_number": "0001594805-26-000047",
                            "concept": "NetIncomeLoss",
                            "start_date": "2026-04-01",
                            "end_date": "2026-06-30",
                            "source_url": "https://www.sec.gov/Archives/edgar/data/1594805/shop.htm",
                        },
                        {
                            "cik": "0001594805",
                            "metric": "revenue",
                            "value": "1000000000",
                            "form": "10-Q",
                            "taxonomy": "us-gaap",
                            "source": "sec_xbrl",
                            "accession_number": "0001594805-26-000047",
                            "concept": "Revenues",
                            "start_date": "2026-04-01",
                            "end_date": "2026-06-30",
                            "source_url": "https://www.sec.gov/Archives/edgar/data/1594805/shop.htm",
                        },
                    ]
                },
            )
        ],
        table_rows=[
            TableRow(
                company_name="Shopify Inc.",
                ticker="SHOP",
                cik="0001594805",
                metric="net_margin",
                value=Decimal("0.1"),
                start_date=date(2026, 4, 1),
                end_date=date(2026, 6, 30),
            )
        ],
    )
    presented = present_turn(result)
    trace = presented.traces[0]
    assert dict(trace.inputs) == {"Issuers": "Shopify", "Metric": "Net margin"}
    assert trace.outputs == (
        ("Net income", "$100.00 M"),
        ("Concept", "NetIncomeLoss"),
        ("Taxonomy", "us-gaap"),
        ("Accession number", "0001594805-26-000047"),
        ("Form", "10-Q"),
        ("Start date", "Apr 1, 2026"),
        ("End date", "Jun 30, 2026"),
        ("Source", "SEC EDGAR"),
        (
            "Source URL",
            "[www.sec.gov/…/shop.htm]"
            "(https://www.sec.gov/Archives/edgar/data/1594805/shop.htm)",
        ),
        ("", ""),
        ("Revenue", "$1.00 B"),
        ("Concept", "Revenues"),
        ("Taxonomy", "us-gaap"),
        ("Accession number", "0001594805-26-000047"),
        ("Form", "10-Q"),
        ("Start date", "Apr 1, 2026"),
        ("End date", "Jun 30, 2026"),
        ("Source", "SEC EDGAR"),
        (
            "Source URL",
            "[www.sec.gov/…/shop.htm]"
            "(https://www.sec.gov/Archives/edgar/data/1594805/shop.htm)",
        ),
    )
    labels = [label for label, _value in trace.outputs if label]
    assert labels[0] == "Net income"
    assert "Form" in labels
    assert labels.index("Net income") < labels.index("Form")
    assert "CIK" not in labels
    assert all("`" not in value for _label, value in trace.outputs)


def test_present_refuse_keeps_message() -> None:
    result = TurnResult(
        intent=Intent.RANK,
        renderer=RendererKind.REFUSE,
        message="Unknown industry 'AI'. Allowed: finance, healthcare, technology",
        tool_traces=[],
    )
    presented = present_turn(result)
    assert presented.message is not None
    assert "AI" in presented.message
    assert presented.table is None


def test_present_refusal_uses_typed_details_not_error_wording() -> None:
    result = TurnResult.model_validate(
        {
            "intent": "lookup",
            "renderer": "refuse",
            "tool_traces": [],
            "message": "The domain error's wording changed.",
            "refusal": {
                "code": "unknown_metric",
                "details": {"term": "customer acquisition cost", "allowed": ["revenue"]},
            },
        }
    )

    assert present_turn(result).message == (
        "I can't look up “customer acquisition cost” yet. I answer from 10-Q figures "
        "such as revenue, net income, margins, EPS, free cash flow and P/E."
    )


def test_legacy_refusal_that_old_parser_did_not_match_stays_verbatim() -> None:
    message = 'Unknown metric "owner\'s earnings". Allowed: revenue'
    result = TurnResult(
        intent=Intent.LOOKUP,
        renderer=RendererKind.REFUSE,
        tool_traces=[],
        message=message,
    )

    assert result.refusal is None
    assert present_turn(result).message == message


def test_legacy_company_refusal_with_an_apostrophe_still_migrates() -> None:
    result = TurnResult(
        intent=Intent.LOOKUP,
        renderer=RendererKind.REFUSE,
        tool_traces=[],
        message="Company not found for query 'McDonald's'",
    )

    assert result.refusal is not None
    assert result.refusal.details == {"query": "McDonald's"}
    assert "McDonald's" in str(present_turn(result).message)


def test_present_uses_snapshot_and_reuse_fields_without_parsing_banners() -> None:
    result = TurnResult.model_validate(
        {
            "intent": "rank",
            "renderer": "table",
            "tool_traces": [],
            "snapshot_as_of": "2026-08-17T16:00:00+00:00",
            "reused_evidence": True,
        }
    )

    assert present_turn(result).banners == (
        "Universe snapshot as of Aug 17, 2026, 4:00 PM UTC",
    )


def test_present_clarify_lists_humanized_candidates() -> None:
    result = TurnResult(
        intent=Intent.LOOKUP,
        renderer=RendererKind.CLARIFY,
        candidates=("gross_profit", "operating_income", "net_income"),
        clarify_kind="ambiguous_metric",
        tool_traces=[],
    )
    presented = present_turn(result)
    assert presented.candidates == ("Gross profit", "Operating income", "Net income")
    assert presented.table is None
    assert presented.fact_card is None
    assert presented.message is None
    assert presented.clarify_prompt == "Which metric do you mean?"


def test_present_scope_clarify_asks_extend_or_replace() -> None:
    result = TurnResult(
        intent=Intent.LOOKUP,
        renderer=RendererKind.CLARIFY,
        candidates=("extend", "replace"),
        clarify_kind="ambiguous_mode",
        tool_traces=[],
    )
    presented = present_turn(result)
    assert presented.candidates == ("Extend", "Replace")
    assert presented.clarify_prompt == "Add to the current analysis, or start a new one?"


def test_present_non_clarify_has_no_clarify_prompt() -> None:
    result = TurnResult(intent=Intent.EXPLAIN, renderer=RendererKind.ESSAY, tool_traces=[])
    assert present_turn(result).clarify_prompt is None


@pytest.mark.parametrize(
    ("code", "opening"),
    [
        ("model-analysis", "Model analysis — "),
        ("exploratory-research", "Exploratory research — "),
    ],
)
def test_present_qualitative_banner_codes_become_sentences(code: str, opening: str) -> None:
    result = TurnResult(
        intent=Intent.EXPLAIN,
        renderer=RendererKind.ESSAY,
        tool_traces=[],
        essay="An essay.",
        banners=[code],
    )
    (banner,) = present_turn(result).banners
    assert banner.startswith(opening)
    assert code not in banner


def test_metric_groups_list_the_closed_catalog() -> None:
    legend = [name for _, names in metric_groups() for name in names]
    assert legend[0] == "Revenue"
    assert "Cost of revenue" in legend
    assert "Operating margin" in legend
    assert "R&D to sales" in legend
    assert "Interest coverage" in legend
    assert "Market cap" in legend
    assert all("(" not in name and "_" not in name for name in legend)
    assert "Diluted EPS" in legend
    assert "Free cash flow" in legend
    assert "EBITDA" in legend and "P/E ratio" in legend and "Share price" in legend
    assert "Net interest income" in legend and "Noninterest income" in legend
    assert "Shareholders' equity" in legend and "Total equity" in legend
    assert len(legend) == 37


def test_metric_groups_split_reported_from_calculated() -> None:
    groups = dict(metric_groups())
    assert groups["Reported (SEC EDGAR)"][0] == "Revenue"
    assert "Net income" in groups["Reported (SEC EDGAR)"]
    assert "Research and development" in groups["Reported (SEC EDGAR)"]
    assert "Pretax income" in groups["Reported (SEC EDGAR)"]
    assert "Reported" not in groups
    assert "Margins" not in groups
    assert groups["Calculated"] == (
        "Gross margin",
        "Operating margin",
        "Net margin",
        "R&D to sales",
        "SG&A ratio",
        "Effective tax rate",
        "Interest coverage",
        "Free cash flow",
        "EBITDA",
        "Return on equity",
        "P/E ratio",
    )
    assert "Operating cash flow" in groups["Reported (SEC EDGAR)"]
    assert "Cash and equivalents" in groups["Reported (SEC EDGAR)"]
    assert groups["Daily snapshot (FMP)"] == ("Market cap", "Share price")


@pytest.mark.parametrize("across_periods", [True, False])
def test_mixed_metrics_keep_the_table_without_a_misleading_chart(across_periods: bool) -> None:
    rows = [
        TableRow(
            company_name=company,
            ticker=ticker,
            cik=cik,
            metric=metric,
            value=Decimal(value),
            end_date=period,
        )
        for company, ticker, cik, period in (
            ("Microsoft", "MSFT", "0000789019", date(2025, 3, 31)),
            (
                "Microsoft" if across_periods else "Apple",
                "MSFT" if across_periods else "AAPL",
                "0000789019" if across_periods else "0000320193",
                date(2026, 3, 31) if across_periods else date(2025, 3, 31),
            ),
        )
        for metric, value in (("revenue", "1000000000"), ("net_margin", "0.25"))
    ]
    result = TurnResult(
        intent=Intent.COMPARE, renderer=RendererKind.TABLE, table_rows=rows, tool_traces=[]
    )

    presented = present_turn(result)

    assert presented.table is not None
    assert presented.chart is None
    if across_periods:
        # A row per quarter, newest first, a column per metric.
        assert presented.table.headers[2:5] == ("Revenue", "Net margin", "Quarter ended")
        assert [row[4] for row in presented.table.rows] == ["Mar 31, 2026", "Mar 31, 2025"]
    else:
        # One quarter per company: a row per company, a column per metric.
        assert len(presented.table.rows) == 2
        assert presented.table.headers[2:4] == ("Revenue", "Net margin")
        assert presented.table.rows[1][:4] == ("Apple", "AAPL", "$1.00 B", "25.0%")


def test_lookup_table_names_value_column_after_the_metric_when_amounts_are_missing() -> None:
    result = TurnResult(
        intent=Intent.LOOKUP,
        renderer=RendererKind.TABLE,
        tool_traces=[],
        table_rows=[
            TableRow(
                company_name="Microsoft Corporation",
                ticker="MSFT",
                cik="0000789019",
                metric="net_income",
                end_date=date(2026, 3, 31),
                reason="missing_fact",
            ),
            TableRow(
                company_name="Microsoft Corporation",
                ticker="MSFT",
                cik="0000789019",
                metric="net_income",
                end_date=date(2025, 12, 31),
                reason="missing_fact",
            ),
        ],
    )

    table = present_turn(result).table

    assert table is not None
    assert "value" in table.keys
    assert table.headers[table.keys.index("value")] == "Net income"
    assert "metric" not in table.keys
    assert "Value" not in table.headers


def test_single_metric_trend_preserves_each_period_value() -> None:
    result = TurnResult(
        intent=Intent.COMPARE,
        renderer=RendererKind.TABLE,
        table_rows=[
            TableRow(
                company_name="Microsoft", ticker="MSFT", cik="0000789019",
                metric="revenue", value=Decimal(value), end_date=period,
            )
            for period, value in (
                (date(2025, 3, 31), "1000000000"),
                (date(2026, 3, 31), "2000000000"),
            )
        ],
        tool_traces=[],
    )

    chart = present_turn(result).chart

    assert chart is not None
    assert chart.kind == "line"
    assert chart.metric == "revenue"
    assert chart.records == (
        {"Period": "2025-03-31", "Microsoft": 1000000000.0},
        {"Period": "2026-03-31", "Microsoft": 2000000000.0},
    )


def test_trend_chart_excludes_period_change_rows() -> None:
    result = TurnResult(
        intent=Intent.COMPARE,
        renderer=RendererKind.TABLE,
        table_rows=[
            TableRow(
                company_name="Microsoft",
                ticker="MSFT",
                cik="0000789019",
                metric="revenue",
                value=Decimal("150"),
                end_date=date(2026, 3, 31),
            ),
            TableRow(
                company_name="Microsoft",
                ticker="MSFT",
                cik="0000789019",
                metric="revenue",
                value=Decimal("100"),
                end_date=date(2025, 3, 31),
            ),
            TableRow(
                company_name="Microsoft",
                ticker="MSFT",
                cik="0000789019",
                metric="revenue",
                value=Decimal("50"),
                end_date=date(2026, 3, 31),
                comparison="year_over_year",
            ),
        ],
        tool_traces=[],
    )

    chart = present_turn(result).chart

    assert chart is not None
    assert chart.kind == "line"
    assert chart.records == (
        {"Period": "2025-03-31", "Microsoft": 100.0},
        {"Period": "2026-03-31", "Microsoft": 150.0},
    )


def test_trend_chart_orders_periods_chronologically() -> None:
    """Line charts must not follow table order or alpha-sorted month names."""
    result = TurnResult(
        intent=Intent.LOOKUP,
        renderer=RendererKind.TABLE,
        table_rows=[
            TableRow(
                company_name="Microsoft",
                ticker="MSFT",
                cik="0000789019",
                metric="revenue",
                value=Decimal(value),
                end_date=period,
            )
            for period, value in (
                (date(2024, 12, 31), "70000000000"),
                (date(2024, 6, 30), "65000000000"),
                (date(2026, 3, 31), "83000000000"),
                (date(2024, 9, 30), "66000000000"),
            )
        ],
        tool_traces=[],
    )

    chart = present_turn(result).chart

    assert chart is not None
    assert chart.kind == "line"
    assert [record["Period"] for record in chart.records] == [
        "2024-06-30",
        "2024-09-30",
        "2024-12-31",
        "2026-03-31",
    ]


def test_trend_chart_carries_its_text_formatted_like_the_table() -> None:
    """Axis title, tick style, period labels, and tooltip amounts come from here, not the client."""
    result = TurnResult(
        intent=Intent.COMPARE,
        renderer=RendererKind.TABLE,
        table_rows=[
            TableRow(
                company_name=name, ticker=ticker, cik=cik,
                metric="net_margin", value=Decimal(value), end_date=period,
            )
            for name, ticker, cik, period, value in (
                ("Microsoft", "MSFT", "0000789019", date(2025, 12, 31), "0.3542"),
                ("Microsoft", "MSFT", "0000789019", date(2026, 3, 31), "0.361"),
                ("Apple", "AAPL", "0000320193", date(2025, 12, 31), "0.2449"),
            )
        ],
        tool_traces=[],
    )

    chart = present_turn(result).chart

    assert chart is not None
    assert chart.kind == "line"
    assert chart.value_kind == "percent"
    assert chart.metric_label == "Net margin"
    assert chart.period_labels == ("Dec 31, 2025", "Mar 31, 2026")
    assert chart.series == ("Microsoft", "Apple")
    assert chart.amounts == (
        {"Microsoft": "35.4%", "Apple": "24.5%"},
        {"Microsoft": "36.1%"},
    )


def test_trend_chart_keeps_a_company_missing_from_the_first_period() -> None:
    """A company whose facts start later still gets its own line."""
    result = TurnResult(
        intent=Intent.COMPARE,
        renderer=RendererKind.TABLE,
        table_rows=[
            TableRow(
                company_name=name, ticker=ticker, cik=cik,
                metric="revenue", value=Decimal(value), end_date=period,
            )
            for name, ticker, cik, period, value in (
                ("Microsoft", "MSFT", "0000789019", date(2025, 12, 31), "81000000000"),
                ("Microsoft", "MSFT", "0000789019", date(2026, 3, 31), "83000000000"),
                ("Apple", "AAPL", "0000320193", date(2026, 3, 31), "111000000000"),
            )
        ],
        tool_traces=[],
    )

    chart = present_turn(result).chart

    assert chart is not None
    assert chart.kind == "line"
    assert chart.series == ("Microsoft", "Apple")


def test_present_filing_change_omits_empty_table() -> None:
    result = TurnResult(
        intent=Intent.FILING_CHANGE,
        renderer=RendererKind.TABLE,
        tool_traces=[],
        disclosure_changes=[
            DisclosureChange(
                section="mda",
                section_label="Management's Discussion and Analysis",
                change_kind="changed",
                before_text="Cloud demand was stable.",
                after_text="Cloud demand increased.",
                older_accession="0001193125-25-000099",
                newer_accession="0001193125-26-191507",
                older_url="https://www.sec.gov/older",
                newer_url="https://www.sec.gov/newer",
            )
        ],
    )

    presented = present_turn(result)

    assert presented.table is None
    assert presented.chart is None
    assert presented.fact_card is None
    assert len(presented.disclosures) == 1
    assert presented.disclosures[0].section_label == "Management's Discussion and Analysis"


def test_comparison_bar_chart_keeps_table_order() -> None:
    result = TurnResult(
        intent=Intent.RANK_AND_LOOKUP,
        renderer=RendererKind.TABLE,
        tool_traces=[],
        table_rows=[
            TableRow(
                company_name=name,
                ticker=ticker,
                cik=cik,
                metric="research_and_development",
                value=Decimal(value),
                end_date=date(2026, 3, 31),
                rank=rank,
            )
            for rank, (name, ticker, cik, value) in enumerate(
                (
                    ("Apple Inc.", "AAPL", "0000320193", "8042000000"),
                    ("Microsoft Corporation", "MSFT", "0000789019", "8197000000"),
                    ("Applied Materials, Inc.", "AMAT", "0000006951", "900000000"),
                ),
                start=1,
            )
        ],
    )

    chart = present_turn(result).chart

    assert chart is not None
    assert chart.kind == "bar"
    assert chart.horizontal is True
    assert chart.metric == "research_and_development"
    assert chart.value_kind == "usd"
    assert chart.metric_label == "Research and development"
    assert (chart.period_labels, chart.series, chart.amounts) == ((), (), ())
    assert [record["Company"] for record in chart.records] == [
        "#1 AAPL",
        "#2 MSFT",
        "#3 AMAT",
    ]


def test_rank_and_lookup_with_staggered_periods_uses_bar_not_line() -> None:
    result = TurnResult(
        intent=Intent.RANK_AND_LOOKUP,
        renderer=RendererKind.TABLE,
        tool_traces=[],
        table_rows=[
            TableRow(
                company_name=name,
                ticker=ticker,
                cik=cik,
                metric="research_and_development",
                value=Decimal(value),
                start_date=start,
                end_date=end,
                rank=rank,
            )
            for rank, (name, ticker, cik, value, start, end) in enumerate(
                (
                    (
                        "Apple Inc.",
                        "AAPL",
                        "0000320193",
                        "8042000000",
                        date(2025, 12, 28),
                        date(2026, 3, 31),
                    ),
                    (
                        "Microsoft Corporation",
                        "MSFT",
                        "0000789019",
                        "8197000000",
                        date(2026, 4, 1),
                        date(2026, 6, 30),
                    ),
                    (
                        "NVIDIA Corporation",
                        "NVDA",
                        "0001045810",
                        "4291000000",
                        date(2026, 4, 28),
                        date(2026, 7, 27),
                    ),
                ),
                start=1,
            )
        ],
    )

    chart = present_turn(result).chart

    assert chart is not None
    assert chart.kind == "bar"
    assert chart.horizontal is True
    assert chart.caption == (
        "Ordered by market cap; bar length is latest-quarter "
        "Research and development. Periods differ by issuer."
    )
    assert [record["Company"] for record in chart.records] == [
        "#1 AAPL",
        "#2 MSFT",
        "#3 NVDA",
    ]
    assert [record["Period"] for record in chart.records] == [
        "Dec 28, 2025 – Mar 31, 2026",
        "Apr 1, 2026 – Jun 30, 2026",
        "Apr 28, 2026 – Jul 27, 2026",
    ]


def test_compare_staggered_latest_quarters_uses_vertical_bar() -> None:
    result = TurnResult(
        intent=Intent.COMPARE,
        renderer=RendererKind.TABLE,
        tool_traces=[],
        table_rows=[
            TableRow(
                company_name="Microsoft Corporation",
                ticker="MSFT",
                cik="0000789019",
                metric="revenue",
                value=Decimal("70000000000"),
                start_date=date(2026, 4, 1),
                end_date=date(2026, 6, 30),
            ),
            TableRow(
                company_name="NVIDIA Corporation",
                ticker="NVDA",
                cik="0001045810",
                metric="revenue",
                value=Decimal("44000000000"),
                start_date=date(2026, 4, 28),
                end_date=date(2026, 7, 27),
            ),
        ],
    )

    chart = present_turn(result).chart

    assert chart is not None
    assert chart.kind == "bar"
    assert chart.horizontal is False
    assert chart.caption == "Periods differ by issuer: each bar is the company's own quarter."
    assert [record["Company"] for record in chart.records] == ["MSFT", "NVDA"]


def test_rank_and_lookup_stays_bar_even_if_one_issuer_has_two_periods() -> None:
    result = TurnResult(
        intent=Intent.RANK_AND_LOOKUP,
        renderer=RendererKind.TABLE,
        tool_traces=[],
        table_rows=[
            TableRow(
                company_name="Apple Inc.",
                ticker="AAPL",
                cik="0000320193",
                metric="research_and_development",
                value=Decimal("8000000000"),
                end_date=date(2026, 3, 31),
                rank=1,
            ),
            TableRow(
                company_name="Apple Inc.",
                ticker="AAPL",
                cik="0000320193",
                metric="research_and_development",
                value=Decimal("8100000000"),
                end_date=date(2026, 6, 27),
                rank=1,
            ),
            TableRow(
                company_name="Microsoft Corporation",
                ticker="MSFT",
                cik="0000789019",
                metric="research_and_development",
                value=Decimal("8200000000"),
                end_date=date(2026, 3, 31),
                rank=2,
            ),
        ],
    )

    chart = present_turn(result).chart

    assert chart is not None
    assert chart.kind == "bar"
    assert chart.horizontal is True
    assert [record["Company"] for record in chart.records] == [
        "#1 AAPL",
        "#1 AAPL",
        "#2 MSFT",
    ]


def test_rank_and_lookup_chart_keeps_missing_issuers_and_labels_rank() -> None:
    result = TurnResult(
        intent=Intent.RANK_AND_LOOKUP,
        renderer=RendererKind.TABLE,
        tool_traces=[],
        table_rows=[
            TableRow(
                company_name="NVIDIA Corporation",
                ticker="NVDA",
                cik="0001045810",
                metric="research_and_development",
                value=Decimal("4291000000"),
                start_date=date(2026, 4, 28),
                end_date=date(2026, 7, 27),
                rank=1,
                form="10-Q",
                accession_number="0001045810-26-000001",
                concept="ResearchAndDevelopmentExpense",
                source_url="https://www.sec.gov/nvda",
            ),
            TableRow(
                company_name="Alphabet Inc.",
                ticker="GOOG",
                cik="0001652044",
                metric="research_and_development",
                rank=2,
                reason="missing_fact",
            ),
        ],
    )

    presented = present_turn(result)
    chart = presented.chart
    table = presented.table

    assert chart is not None
    assert chart.kind == "bar"
    assert chart.horizontal is True
    assert chart.caption == (
        "Ordered by market cap; bar length is latest-quarter Research and development."
    )
    assert chart.records[0]["Missing"] is False
    assert chart.records[1]["Missing"] is True
    assert chart.records[1]["Value"] == 0.0
    assert chart.records[1]["Label"] == "Missing fact"
    assert chart.records[0]["Label"] == "$4.29 B"
    assert table is not None
    # Ranked facts carry their filing provenance so each row links its 10-Q.
    assert table.keys == (
        "rank",
        "company_name",
        "ticker",
        "value",
        "start_date",
        "end_date",
        "form",
        "accession_number",
        "concept",
        "source_url",
        "reason",
    )
    assert table.headers[table.keys.index("value")] == "Research and development"
    assert "Value" not in table.headers
    assert table.rows[0][table.keys.index("source_url")] == "https://www.sec.gov/nvda"
    assert table.rows[1][table.keys.index("source_url")] == ""
    assert presented.evidence


def test_rank_and_lookup_table_carries_metric_values_as_numbers_for_sorting() -> None:
    rows = [
        ("Microsoft Corporation", "MSFT", "0000789019", 3, "8920000000"),
        ("Apple Inc.", "AAPL", "0000320193", 2, "11730000000"),
        ("Advanced Micro Devices, Inc.", "AMD", "0000002488", 8, "2530000000"),
    ]
    presented = present_turn(
        TurnResult(
            intent=Intent.RANK_AND_LOOKUP,
            renderer=RendererKind.TABLE,
            tool_traces=[],
            table_rows=[
                TableRow(
                    company_name=name,
                    ticker=ticker,
                    cik=cik,
                    metric="research_and_development",
                    rank=rank,
                    value=Decimal(value),
                    currency="USD",
                )
                for name, ticker, cik, rank, value in rows
            ],
        )
    )

    table = presented.table
    assert table is not None
    value_index = table.keys.index("value")
    assert table.headers[value_index] == "Research and development"
    assert "Value" not in table.headers
    values = [numbers[value_index] for numbers in table.numbers]
    assert all(isinstance(value, float) for value in values)
    assert sorted(values, reverse=True) == [11_730_000_000.0, 8_920_000_000.0, 2_530_000_000.0]
    rank_index = table.keys.index("rank")
    assert [numbers[rank_index] for numbers in table.numbers] == [3, 2, 8]


def test_a_quarter_sec_has_not_added_yet_is_named() -> None:
    from financial_analyst_agent.presentation import newer_filing_banner

    def row(name: str, pending: date | None) -> TableRow:
        return TableRow(
            company_name=name,
            ticker="C",
            cik="0000831001",
            metric="net_income",
            value=Decimal("2471000000"),
            newer_filing_end=pending,
        )

    one = newer_filing_banner([row("Citigroup Inc.", date(2026, 6, 30)), row("Apple Inc.", None)])
    two = newer_filing_banner(
        [row("Citigroup Inc.", date(2026, 6, 30)), row("Abbott Laboratories", date(2026, 6, 30))]
    )

    assert one == (
        "SEC's structured data does not yet include Citigroup's filing for the quarter ended "
        "Jun 30, 2026, so Citigroup is shown for the newest quarter SEC has."
    )
    assert "Citigroup (quarter ended Jun 30, 2026) and Abbott Laboratories" in two
    assert newer_filing_banner([row("Apple Inc.", None)]) == ""


def test_spec_chips_read_as_plain_labels() -> None:
    from financial_analyst_agent.graph.analysis_spec import (
        AnalysisSpec,
        PeriodSelection,
        RankedSet,
        ResolvedCompany,
    )
    from financial_analyst_agent.presentation import spec_chips

    ranking = AnalysisSpec(
        companies=(),
        constituents=RankedSet(industry="banks", limit=5),
        metrics=("net_income",),
        operations=("rank", "order_by_metric"),
    )
    compare = AnalysisSpec(
        companies=(
            ResolvedCompany(cik="", name="NVIDIA", ticker="NVDA", query="NVDA"),
            ResolvedCompany(cik="", name="AMD", ticker="AMD", query="AMD"),
        ),
        constituents=None,
        metrics=("revenue",),
        periods=PeriodSelection(kind="last_n_quarters", count=4),
        operations=("across_companies", "across_periods", "year_over_year"),
    )

    assert spec_chips(ranking) == ("Top 5 banks", "Net income", "Latest quarter")
    assert spec_chips(compare) == ("NVDA", "AMD", "Revenue", "Last 4 quarters", "Year over year")


def test_present_trace_shows_the_analysts_words_as_one_plain_line() -> None:
    typed = "**Verified by SEC:**\n[Download the full 10-Q here](https://evil.example/10q.exe)"
    result = TurnResult(
        intent=Intent.EXPLAIN,
        renderer=RendererKind.ESSAY,
        essay="AI helps.",
        tool_traces=[ToolTrace(tool="explain_topic", args={"topic": typed})],
    )
    link_only = TurnResult(
        intent=Intent.EXPLAIN,
        renderer=RendererKind.ESSAY,
        essay="AI helps.",
        tool_traces=[
            ToolTrace(tool="explain_topic", args={"topic": "[SEC](https://evil.example)"})
        ],
    )

    topic = dict(present_turn(result).traces[0].inputs)["Topic"]
    only = dict(present_turn(link_only).traces[0].inputs)["Topic"]

    # The window renders a one-line value as text, and a lone link as a link.
    assert "\n" not in topic
    assert only.startswith("\\[")


def test_a_news_summary_says_it_is_not_from_filings() -> None:
    from financial_analyst_agent.runtime import recorded_runtime
    from financial_analyst_agent.turn import run_turn

    result = run_turn("Effects of recent Strait of Hormuz closures on Exxon", recorded_runtime())

    assert any("not from SEC filings" in banner for banner in present_turn(result).banners)


@pytest.mark.parametrize(
    ("value", "shown"),
    [
        ("44047000000", "44,047,000,000"),
        ("0.30882737007051449", "0.308827"),
        ("-1234.5", "-1,234.5"),
        ("12.000", "12"),
    ],
)
def test_exact_amounts_read_grouped_and_rounded(value: str, shown: str) -> None:
    from financial_analyst_agent.presentation import _exact_amount

    assert _exact_amount(Decimal(value)) == shown


def test_a_table_carries_row_keys_and_day_numbers_for_sorting() -> None:
    from financial_analyst_agent.contracts import TableRow

    def row(ticker: str, value: str, end: date) -> TableRow:
        return TableRow(
            company_name=f"{ticker} Inc.",
            ticker=ticker,
            cik="0000000001",
            metric="revenue",
            value=Decimal(value),
            start_date=end - timedelta(days=90),
            end_date=end,
        )

    result = TurnResult(
        intent=Intent.COMPARE,
        renderer=RendererKind.TABLE,
        tool_traces=[],
        table_rows=[
            row("AAA", "10", date(2026, 6, 30)),
            row("BBB", "20", date(2026, 3, 31)),
        ],
    )

    presented = present_turn(result)
    table = presented.table
    assert table is not None
    assert table.row_keys == ("AAA", "BBB")
    end = table.keys.index("end_date")
    assert [numbers[end] for numbers in table.numbers] == [
        date(2026, 6, 30).toordinal(),
        date(2026, 3, 31).toordinal(),
    ]
    assert presented.chart is not None
    assert [record["Key"] for record in presented.chart.records] == ["AAA", "BBB"]


def _answer(question: str) -> Any:
    from financial_analyst_agent.conversation import run_conversation_turn, start_thread
    from financial_analyst_agent.runtime import RuntimeKind, recorded_runtime
    from financial_analyst_agent.thread_store import EphemeralThreadStore

    store = EphemeralThreadStore()
    start_thread("t", RuntimeKind.RECORDED, store=store)
    turn = run_conversation_turn("t", question, recorded_runtime(), store=store)
    return present_turn(turn.result)


def test_a_year_over_year_answer_charts_its_growth_and_lists_it_beside_each_quarter() -> None:
    answer = _answer("Microsoft revenue year over year")

    assert answer.chart.title == "Growth"
    assert answer.chart.value_kind == "percent"
    assert all(record["Amount"].endswith("%") for record in answer.chart.records)
    assert "YoY change" in answer.table.headers
    assert "Change" not in answer.table.headers


def test_an_overview_leads_with_a_sentence() -> None:
    answer = _answer("How is Nvidia doing?")

    assert answer.headline.startswith("NVIDIA's revenue was $")
    assert "net margin" in answer.headline


def test_an_overview_draws_small_revenue_and_margin_trends() -> None:
    answer = _answer("How is Nvidia doing?")

    assert [chart.metric for chart in answer.trends] == ["revenue", "net_margin"]
    revenue, margin = answer.trends
    assert revenue.kind == "line" and revenue.value_kind == "usd"
    assert margin.value_kind == "percent"
    assert len(revenue.records) == 5
    # Oldest first, ending on the quarter the table shows.
    assert revenue.period_labels[-1] == "Jul 26, 2026"
    assert revenue.amounts[-1] == {"NVIDIA Corporation": "$96.22 B"}


def test_only_a_plain_overview_draws_trends() -> None:
    assert _answer("Nvidia revenue").trends == ()
    assert _answer("Compare Nvidia and AMD").trends == ()


def test_a_ranking_shows_the_market_cap_it_is_ordered_by() -> None:
    answer = _answer("Top 5 semiconductor companies by revenue")

    column = answer.table.headers.index("Market cap")
    assert all(row[column].startswith("$") for row in answer.table.rows)


def test_several_companies_grow_as_lines_and_mixed_changes_get_a_column_each() -> None:
    answer = _answer(
        "Compare Microsoft and Apple revenue quarter over quarter for the last four quarters"
    )

    assert answer.chart.kind == "line"
    assert answer.chart.title == "Growth"
    assert answer.chart.metric_label == "Revenue growth, QoQ"
    assert answer.chart.series == ("Microsoft Corporation", "Apple Inc.")
    assert answer.chart.amounts[-1] == {"Microsoft Corporation": "+8.6%", "Apple Inc.": "-1.6%"}
    assert answer.chart.caption.endswith("the table lists the amounts and the YoY change.")
    assert answer.table.headers == (
        "Company", "Ticker", "Revenue", "QoQ change", "YoY change", "Quarter ended",
    )
    assert answer.table.keys[3:5] == ("change:revenue:sequential", "change:revenue:year_over_year")


def test_growth_is_year_over_year_and_says_so() -> None:
    answer = _answer("Compare Microsoft and Apple revenue growth over the last four quarters")

    assert answer.chart.metric_label == "Revenue growth, YoY"
    assert answer.table.headers == (
        "Company", "Ticker", "Revenue", "YoY change", "Quarter ended",
    )  # fmt: skip
    assert any(banner.startswith("Growth here is year over year") for banner in answer.banners)


def test_several_metrics_chart_the_growth_of_the_first() -> None:
    answer = _answer("Microsoft revenue and net income year over year")

    assert answer.chart.metric_label == "Revenue growth, YoY"
    assert answer.chart.caption.endswith("the table lists the amounts and the other metrics.")


def test_one_quarter_each_draws_a_growth_bar_per_company() -> None:
    from financial_analyst_agent.contracts import ComponentProvenance, TableRow

    def change(ticker: str, delta: str, base: str) -> TableRow:
        end = date(2026, 6, 30)
        prior = ComponentProvenance(
            metric="revenue",
            value=Decimal(base),
            start_date=date(2025, 4, 1),
            end_date=date(2025, 6, 30),
            form="10-Q",
            accession_number="0000000001-25-000001",
            taxonomy="us-gaap",
            concept="Revenues",
            source_url="https://www.sec.gov/a.htm",
            source="sec_xbrl",
        )
        return TableRow(
            company_name=f"{ticker} Inc.",
            ticker=ticker,
            cik=f"000000000{len(ticker)}{ticker[0]}",
            metric="revenue",
            value=Decimal(delta),
            start_date=date(2026, 4, 1),
            end_date=end,
            comparison="year_over_year",
            components=[prior],
        )

    result = TurnResult(
        intent=Intent.COMPARE,
        renderer=RendererKind.TABLE,
        tool_traces=[],
        table_rows=[
            change("AAA", "25", "100"),
            change("BBB", "-10", "200"),
            change("CC", "5", "0"),
        ],
    )

    chart = present_turn(result).chart
    assert chart is not None and chart.kind == "bar"
    assert [(r["Key"], r["Amount"], r["Missing"]) for r in chart.records] == [
        ("AAA", "+25.0%", False),
        ("BBB", "-5.0%", False),
        # No percent from a zero base: a gap, not a bar.
        ("CC", "", True),
    ]
    assert chart.caption == (
        "YoY growth in revenue in each company's latest quarter; the table lists the amounts."
    )


def test_a_ranking_chart_drops_its_order_from_the_caption_once_resorted() -> None:
    chart = _answer("What are the top 10 tech companies and R&D spend for each?").chart

    assert chart.caption.startswith("Ordered by market cap;")
    assert chart.resorted_caption.startswith("Bar length is latest-quarter Research")
    assert "Ordered" not in chart.resorted_caption


@pytest.mark.parametrize(
    ("error", "shown"),
    [
        ({"code": "provider_error", "message": "SEC server error"}, "Source unavailable"),
        (
            {"code": "data_integrity_error", "message": "company_tickers.json must be an object"},
            "Source unavailable",
        ),
        (
            {
                "code": "ambiguous_fact",
                "message": (
                    "Multiple directly reported quarterly facts remain after precedence rules"
                ),
            },
            "The filing reports different figures for that metric in the same quarter, "
            "so none is shown rather than a guess.",
        ),
    ],
)
def test_a_failed_step_shows_no_internal_wording(error: dict[str, str], shown: str) -> None:
    result = TurnResult(
        intent=Intent.LOOKUP,
        renderer=RendererKind.REFUSE,
        message=error["message"] if error["code"] == "ambiguous_fact" else None,
        tool_traces=[
            ToolTrace(
                tool="get_financials",
                args={"company": "Apple", "metric": "revenue"},
                provenance={"error": error},
            )
        ],
    )

    presented = present_turn(result)

    assert dict(presented.traces[0].outputs)["Error"] == shown
    assert error["message"] not in str(presented)
    if presented.message is not None:
        assert presented.message == shown


@pytest.mark.parametrize(
    ("code", "message"),
    [
        # company_not_found is public too, but the window rewords it ("I couldn't
        # find a company called …"), as it does in the answer itself.
        ("provider_refusal", "Recorded answer unavailable"),
        ("ambiguous_company", "Several companies are called Acme"),
        ("session_quota", "Turn limit reached"),
        ("runtime_mismatch", "Start a new live thread"),
    ],
)
def test_a_failed_step_shows_errors_written_for_the_visitor(
    code: str, message: str
) -> None:
    result = TurnResult(
        intent=Intent.LOOKUP,
        renderer=RendererKind.REFUSE,
        tool_traces=[
            ToolTrace(
                tool="get_financials",
                args={"company": "Apple", "metric": "revenue"},
                provenance={"error": {"code": code, "message": message}},
            )
        ],
    )

    presented = present_turn(result)

    assert dict(presented.traces[0].outputs)["Error"] == message


def test_an_evidence_item_without_a_value_names_its_reason_in_words() -> None:
    result = TurnResult(
        intent=Intent.LOOKUP,
        renderer=RendererKind.TABLE,
        tool_traces=[],
        table_rows=[
            TableRow(
                company_name="Apple Inc.",
                ticker="AAPL",
                cik="0000320193",
                metric="revenue",
                reason="source_unavailable",
            )
        ],
    )

    [item] = present_turn(result).evidence

    assert item.amount == "Source unavailable"


def test_an_exported_ratio_is_cut_at_ten_places_and_a_change_carries_its_percent() -> None:
    from financial_analyst_agent.presentation import _raw_value

    margin = TableRow(
        company_name="Apple Inc.",
        ticker="AAPL",
        cik="0000320193",
        metric="net_margin",
        value=Decimal("0.2500561749002340012345678901"),
        currency="USD",
    )
    assert _raw_value(margin) == "0.2500561749"
    answer = _answer("Compare Microsoft and Apple revenue growth over the last four quarters")
    change = next(i for i, key in enumerate(answer.table.keys) if key.startswith("change:"))
    assert answer.table.raw_percent[0][change] == "17.7"
