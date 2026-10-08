"""One choice of row builder for a metric, shared by the turn and the MCP server."""

from financial_analyst_agent.runtime import recorded_runtime
from financial_analyst_agent.turn import (
    compare_metrics,
    market_formula_rows,
    metric_rows,
    snapshot_compare_rows,
)


def test_metric_rows_serves_each_kind_of_metric_with_its_own_builder() -> None:
    runtime = recorded_runtime()
    assert runtime.ranking is not None
    issuers = ["MSFT", "AAPL"]

    assert metric_rows(runtime, issuers, "market_cap") == snapshot_compare_rows(
        runtime.ranking, issuers, "market_cap"
    )
    assert metric_rows(runtime, issuers, "pe_ratio") == market_formula_rows(
        runtime.facts, runtime.ranking, issuers, "pe_ratio"
    )
    assert metric_rows(runtime, issuers, "revenue") == compare_metrics(
        runtime.facts, issuers, "revenue"
    )


def test_the_mcp_server_compares_through_the_same_dispatch() -> None:
    from financial_analyst_agent import mcp_server

    compared = getattr(mcp_server.compare_metrics, "fn", mcp_server.compare_metrics)
    runtime = recorded_runtime()
    rows = [row.model_dump(mode="json") for row in metric_rows(runtime, ["MSFT"], "gross_margin")]

    assert compared(["MSFT"], "gross_margin")["rows"] == rows
