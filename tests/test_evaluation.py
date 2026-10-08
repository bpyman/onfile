"""The evaluation suite produces a checked-in scorecard shape."""

from financial_analyst_agent.evaluation import run_suite


def test_fixture_scorecard_covers_required_categories() -> None:
    payload = run_suite()
    categories = {row["category"] for row in payload["cases"]}
    assert {
        "intent_routing",
        "ambiguity_refusal",
        "stateful_follow_up",
        "numeral_lock",
        "filing_change",
    } <= categories
    by_id = {row["id"]: row for row in payload["cases"]}
    assert by_id["lookup_msft_pretax"]["passed"]
    assert by_id["compare_tsla_gm"]["passed"]
    assert by_id["follow_up_add_apple"]["passed"]
    assert by_id["numeral_lock_invented_number"]["passed"]
    assert by_id["filing_change_mda"]["passed"]
    assert payload["case_count"] >= 30
    assert payload["pass_rate"] == 1.0
    assert "p50_ms" in payload
    assert payload["live_cost_usd"] is None


def test_a_wrong_expectation_fails_its_case() -> None:
    from financial_analyst_agent.contracts import Intent, RendererKind
    from financial_analyst_agent.evaluation import EvalCase, _check_result
    from financial_analyst_agent.runtime import recorded_runtime
    from financial_analyst_agent.turn import run_turn

    result = run_turn("Top 5 semiconductor companies by revenue", recorded_runtime())
    base = EvalCase("x", "rankings", "", Intent.RANK_AND_LOOKUP, RendererKind.TABLE)

    assert _check_result(base, result) == ""
    assert "order" in _check_result(
        EvalCase(**{**base.__dict__, "expect_order": ("AMD", "NVDA")}), result
    )
    assert "chart" in _check_result(EvalCase(**{**base.__dict__, "expect_chart": "Growth"}), result)
    assert (
        _check_result(EvalCase(**{**base.__dict__, "expect_tickers": ("NVDA", "ZZZ")}), result)
        == "missing tickers ['ZZZ']"
    )
    assert (
        _check_result(EvalCase(**{**base.__dict__, "expect_values": ("1", "2")}), result)
        == "missing values ['1', '2']"
    )
