from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from financial_analyst_agent.contracts import Intent, RendererKind, Runtime, WorkflowPlan
from financial_analyst_agent.runtime import recorded_runtime
from financial_analyst_agent.turn import run_turn
from helpers import FakeFacts
from test_run_turn_lookup import (
    UNKNOWN_METRIC_QUERY,
    _ExplodingFacts,
    _UnknownMetricCompleter,
)

PROFIT_QUERY = "What was Google's profit?"
INCOME_QUERY = "What was Google's income?"
PROFIT_MARGIN_QUERY = "What was Google's profit margin?"


class _GuessNetIncomeCompleter:
    def complete(self, query: str, current_spec: object = None) -> WorkflowPlan:
        return WorkflowPlan(intent=Intent.LOOKUP, company="Google", metric="net_income")


def test_run_turn_clarifies_profit_even_when_planner_guesses_net_income() -> None:
    result = run_turn(
        PROFIT_QUERY,
        Runtime(completer=_GuessNetIncomeCompleter(), facts=_ExplodingFacts()),
    )

    assert result.intent is Intent.LOOKUP
    assert result.renderer is RendererKind.CLARIFY
    assert result.tool_traces == []
    assert result.table_rows == []
    assert result.candidates == ("gross_profit", "operating_income", "net_income")


def test_run_turn_clarifies_income_even_when_planner_guesses_net_income() -> None:
    result = run_turn(
        INCOME_QUERY,
        Runtime(completer=_GuessNetIncomeCompleter(), facts=_ExplodingFacts()),
    )

    assert result.renderer is RendererKind.CLARIFY
    assert result.candidates == ("net_income", "operating_income")
    assert result.tool_traces == []


def test_run_turn_clarifies_profit_margin() -> None:
    result = run_turn(
        PROFIT_MARGIN_QUERY,
        Runtime(completer=_GuessNetIncomeCompleter(), facts=_ExplodingFacts()),
    )

    assert result.renderer is RendererKind.CLARIFY
    assert result.candidates == ("gross_margin", "operating_margin", "net_margin")


def test_recorded_runtime_clarifies_profit() -> None:
    result = run_turn(PROFIT_QUERY, recorded_runtime())
    assert result.renderer is RendererKind.CLARIFY
    assert result.tool_traces == []
    assert result.candidates == ("gross_profit", "operating_income", "net_income")


def test_unknown_metric_still_refuses_with_full_catalog() -> None:
    result = run_turn(
        UNKNOWN_METRIC_QUERY,
        Runtime(completer=_UnknownMetricCompleter(), facts=_ExplodingFacts()),
    )
    assert result.renderer is RendererKind.REFUSE
    assert result.candidates == ()
    assert result.message is not None
    assert result.message.startswith("I can't look up return on assets yet.")


def test_unique_phrase_overrides_planner_metric() -> None:
    fetched: list[str] = []

    class _Facts(FakeFacts):
        def get_financials(
            self, company: str, metric: str, *, report_date: date | None = None
        ) -> SimpleNamespace:
            fetched.append(metric)
            return SimpleNamespace(
                company_name="Alphabet Inc.",
                ticker="GOOG",
                cik="0001652044",
                metric=metric,
                value=Decimal("1"),
                currency="USD",
                start_date=date(2026, 1, 1),
                end_date=date(2026, 3, 31),
                filed_date=date(2026, 3, 31),
                form="10-Q",
                accession_number="0001652044-26-000048",
                taxonomy="us-gaap",
                concept="OperatingIncomeLoss",
                source_url="https://example.com",
            )

    result = run_turn(
        "What was Google's operating profit?",
        Runtime(completer=_GuessNetIncomeCompleter(), facts=_Facts()),
    )
    assert result.renderer is RendererKind.TABLE
    assert fetched == ["operating_income"]


def test_unknown_phrase_refuses_even_when_planner_guesses_net_income() -> None:
    result = run_turn(
        UNKNOWN_METRIC_QUERY,
        Runtime(completer=_GuessNetIncomeCompleter(), facts=_ExplodingFacts()),
    )
    assert result.renderer is RendererKind.REFUSE
    assert result.tool_traces == []
    assert result.message is not None
    assert result.message.startswith("I can't look up return on assets yet.")
