"""Local FastMCP HTTP server. Same tools the turn uses in-process."""

from typing import Annotated

from fastmcp import FastMCP
from pydantic import Strict

from financial_analyst_agent.contracts import (
    ALLOWED_METRICS,
    MARKET_FORMULAS,
    REPORTED_METRICS,
    SNAPSHOT_METRICS,
    Runtime,
    TableRow,
    unknown_metric_message,
)
from financial_analyst_agent.domain.errors import UnknownIndustryError
from financial_analyst_agent.graph.analysis_spec import MAX_RANKED_COMPANIES
from financial_analyst_agent.numeral_lock import numeral_lock_extras, numeral_lock_message
from financial_analyst_agent.runtime import build_runtime
from financial_analyst_agent.turn import metric_rows

mcp = FastMCP("financial-analyst")

# The same bounds the window's turns keep: one question's length, one ranking's size.
MAX_TEXT_CHARS = 2000
MAX_ISSUERS = MAX_RANKED_COMPANIES
# The longest catalog slug is far shorter; an unknown metric is named back, so bound it.
MAX_METRIC_CHARS = 64


def _bounded(name: str, text: str, limit: int = MAX_TEXT_CHARS) -> str:
    if not text.strip() or len(text) > limit:
        raise ValueError(f"{name} must be 1 to {limit} characters")
    return text


def _catalog_metric(metric: str) -> str:
    _bounded("metric", metric, MAX_METRIC_CHARS)
    if metric not in ALLOWED_METRICS:
        raise ValueError(unknown_metric_message(metric))
    return metric


def _metric_rows(runtime: Runtime, issuers: list[str], metric: str) -> list[TableRow]:
    if (metric in SNAPSHOT_METRICS or metric in MARKET_FORMULAS) and runtime.ranking is None:
        raise RuntimeError("ranking adapter is not configured")
    return metric_rows(runtime, issuers, metric)


@mcp.tool()
def get_financials(company: str, metric: str) -> dict[str, object]:
    """Return the latest standalone quarterly fact for a company and metric.

    Takes every metric ``compare_metrics`` takes; a formula or snapshot metric
    (``gross_margin``, ``market_cap``) answers as that tool's row for the company.
    """
    _bounded("company", company)
    _catalog_metric(metric)
    runtime = build_runtime()
    if metric not in REPORTED_METRICS:
        [row] = _metric_rows(runtime, [company], metric)
        payload = row.model_dump(mode="json")
    else:
        payload = runtime.facts.get_financials(company, metric).model_dump(mode="json")
    if not isinstance(payload, dict):
        raise TypeError("get_financials must serialize to an object")
    # "recorded" or "live": a server without SEC_USER_AGENT answers from the recording.
    return {**payload, "runtime": runtime.kind.value}


@mcp.tool()
def compare_metrics(issuers: list[str], metric: str) -> dict[str, object]:
    """Compare a reported metric or allowed formula across issuers."""
    _catalog_metric(metric)
    if not issuers or len(issuers) > MAX_ISSUERS:
        raise ValueError(f"issuers must name 1 to {MAX_ISSUERS} companies")
    for issuer in issuers:
        _bounded("issuer", issuer)
    runtime = build_runtime()
    rows = _metric_rows(runtime, issuers, metric)
    return {"rows": [row.model_dump(mode="json") for row in rows], "runtime": runtime.kind.value}


@mcp.tool()
def rank_companies(
    industry: str, limit: Annotated[int, Strict()] = 10
) -> dict[str, object]:
    """Rank US operating companies in an industry from the dated universe snapshot."""
    _bounded("industry", industry)
    # True is an int to Python; a count it is not.
    if isinstance(limit, bool) or not isinstance(limit, int):
        raise ValueError(f"limit must be a whole number from 1 to {MAX_RANKED_COMPANIES}")
    if not 1 <= limit <= MAX_RANKED_COMPANIES:
        raise ValueError(f"limit must be 1 to {MAX_RANKED_COMPANIES}")
    runtime = build_runtime()
    if runtime.ranking is None:
        raise RuntimeError("ranking adapter is not configured")
    try:
        table = runtime.ranking.rank_companies(industry, limit)
    except UnknownIndustryError as exc:
        raise ValueError(str(exc)) from exc
    return {
        "runtime": runtime.kind.value,
        "as_of": table.as_of,
        "source": table.source,
        "sector": table.sector,
        "rows": [
            {
                "rank": index,
                "company_name": company.name,
                "ticker": company.ticker,
                "cik": company.cik,
                "market_cap": str(company.market_cap),
            }
            for index, company in enumerate(table.companies, start=1)
        ],
    }


@mcp.tool()
def explain_topic(topic: str) -> dict[str, object]:
    """Write a labeled model-analysis essay, withheld if it quotes numbers the topic lacks."""
    _bounded("topic", topic)
    runtime = build_runtime()
    if runtime.essay is None:
        raise RuntimeError("essay completer is not configured")
    essay = runtime.essay.complete_essay(topic)
    extras = numeral_lock_extras(essay, topic)
    if extras:
        return {"essay": None, "message": numeral_lock_message(", ".join(extras))}
    return {"essay": essay}


@mcp.tool()
def search_news(query: str) -> dict[str, object]:
    """Search current-event news for the user query. Title and URL are required."""
    _bounded("query", query)
    runtime = build_runtime()
    if runtime.news is None:
        raise RuntimeError("news adapter is not configured")
    hits = runtime.news.search_news(query)
    return {"hits": [hit.model_dump(mode="json") for hit in hits]}


if __name__ == "__main__":
    mcp.run(transport="http", host="127.0.0.1", port=8000)
