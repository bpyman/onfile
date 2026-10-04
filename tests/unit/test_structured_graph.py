"""Each compiled task kind runs through its own deterministic workflow.

``execute_compiled_task`` is how the structured-analysis subgraph runs one cell:
a closed map from task kind to workflow, with no model and no nested graph.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from financial_analyst_agent.domain.enums import DataSourceKind, Metric
from financial_analyst_agent.domain.models import FinancialFact
from financial_analyst_agent.graph.analysis_spec import CompiledTask
from financial_analyst_agent.ranking import SnapshotRanking
from financial_analyst_agent.runtime import FIXTURE_UNIVERSE_SNAPSHOT_PATH


class _LookupFacts:
    def get_financials(
        self, company: str, metric: str, *, report_date: date | None = None
    ) -> FinancialFact:
        assert company == "Google"
        assert metric == "net_income"
        return FinancialFact(
            company_name="Alphabet Inc.",
            ticker="GOOG",
            cik="0001652044",
            metric=Metric.NET_INCOME,
            value=Decimal("62578000000"),
            currency="USD",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 3, 31),
            filed_date=date(2026, 3, 31),
            form="10-Q",
            accession_number="0001652044-26-000048",
            taxonomy="us-gaap",
            concept="NetIncomeLoss",
            source_url="https://www.sec.gov/example.htm",
            source=DataSourceKind.SEC_XBRL,
        )


class _CompareFacts:
    def get_financials(
        self, company: str, metric: str, *, report_date: date | None = None
    ) -> FinancialFact:
        values = {
            ("Microsoft", "operating_income"): Decimal("100"),
            ("Microsoft", "revenue"): Decimal("400"),
            ("Google", "operating_income"): Decimal("50"),
            ("Google", "revenue"): Decimal("200"),
        }
        value = values[(company, metric)]
        return FinancialFact(
            company_name=company,
            ticker="MSFT" if company == "Microsoft" else "GOOG",
            cik="0000789019" if company == "Microsoft" else "0001652044",
            metric=Metric(metric),
            value=value,
            currency="USD",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 3, 31),
            filed_date=date(2026, 3, 31),
            form="10-Q",
            accession_number="acc",
            taxonomy="us-gaap",
            concept=metric,
            source_url="https://www.sec.gov/example.htm",
            source=DataSourceKind.SEC_XBRL,
        )


class _SilentCompleter:
    def complete(self, query: str, current_spec: object = None) -> SimpleNamespace:
        raise AssertionError("a compiled task must not re-plan")


def _runtime(*, facts: object, ranking: object | None = None) -> object:
    from financial_analyst_agent.contracts import Runtime

    return Runtime(
        completer=_SilentCompleter(),
        facts=facts,  # type: ignore[arg-type]
        ranking=ranking,  # type: ignore[arg-type]
    )


def test_compiled_task_lookup_returns_table() -> None:
    from financial_analyst_agent.contracts import Intent, RendererKind, TurnResult
    from financial_analyst_agent.graph.spec_turn import execute_compiled_task

    task = CompiledTask(kind="lookup", issuers=("Google",), metric="net_income")
    result = execute_compiled_task(task, _runtime(facts=_LookupFacts()))  # type: ignore[arg-type]

    assert type(result).__name__ == TurnResult.__name__
    assert result.intent == Intent.LOOKUP
    assert result.renderer == RendererKind.TABLE
    assert result.table_rows[0].value == Decimal("62578000000")
    assert result.tool_traces[0].tool == "get_financials"


def test_compiled_task_compare_returns_table() -> None:
    from financial_analyst_agent.contracts import Intent, RendererKind
    from financial_analyst_agent.graph.spec_turn import execute_compiled_task

    task = CompiledTask(
        kind="compare", issuers=("Microsoft", "Google"), metric="operating_margin"
    )
    result = execute_compiled_task(task, _runtime(facts=_CompareFacts()))  # type: ignore[arg-type]

    assert result.intent == Intent.COMPARE
    assert result.renderer == RendererKind.TABLE
    assert len(result.table_rows) == 2
    assert result.tool_traces[0].tool == "compare_metrics"


def test_compiled_task_rank_returns_table() -> None:
    from financial_analyst_agent.contracts import Intent, RendererKind
    from financial_analyst_agent.graph.spec_turn import execute_compiled_task

    ranking = SnapshotRanking.from_path(FIXTURE_UNIVERSE_SNAPSHOT_PATH)
    task = CompiledTask(kind="rank", industry="healthcare", limit=3)
    result = execute_compiled_task(
        task,
        _runtime(facts=_LookupFacts(), ranking=ranking),  # type: ignore[arg-type]
    )

    assert result.intent == Intent.RANK
    assert result.renderer == RendererKind.TABLE
    assert len(result.table_rows) == 3
    assert result.tool_traces[0].tool == "rank_companies"


def test_compiled_task_rank_and_lookup_returns_table() -> None:
    from financial_analyst_agent.contracts import Intent, RendererKind
    from financial_analyst_agent.graph.spec_turn import execute_compiled_task

    ranking = SnapshotRanking.from_path(FIXTURE_UNIVERSE_SNAPSHOT_PATH)
    task = CompiledTask(kind="rank_and_lookup", industry="healthcare", limit=2, metric="market_cap")
    result = execute_compiled_task(
        task,
        _runtime(facts=_LookupFacts(), ranking=ranking),  # type: ignore[arg-type]
    )

    assert result.intent == Intent.RANK_AND_LOOKUP
    assert result.renderer == RendererKind.TABLE
    assert len(result.table_rows) == 2
    assert result.tool_traces[0].tool == "rank_companies"
