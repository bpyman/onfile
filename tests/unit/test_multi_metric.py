"""Conversation seam: multi-metric composition (ticket 09).

Asserts several metrics in one analysis at the public conversation entry.
Does not assert graph internals. Uses a real temporary store.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

from financial_analyst_agent.contracts import WorkflowPlan
from financial_analyst_agent.domain.errors import UnsupportedQuarterlyFactError
from financial_analyst_agent.runtime import FIXTURE_UNIVERSE_SNAPSHOT_PATH
from helpers import FakeFacts, named_by_cik

# Resolved companies are asked for by CIK; these fakes answer by name.
_NAMED = named_by_cik('Microsoft', 'Google')


class _MultiMetricFacts(FakeFacts):
    """Reported + formula components; one cell can be missing without sinking others."""

    def __init__(self, *, missing: set[tuple[str, str]] | None = None) -> None:
        self.missing = missing or set()
        self.calls: list[tuple[str, str]] = []

    def get_financials(

        self, company: str, metric: str, *, report_date: date | None = None

    ) -> SimpleNamespace:
        company = _NAMED(company)
        self.calls.append((company, metric))
        if (company, metric) in self.missing:
            raise UnsupportedQuarterlyFactError(f"no standalone quarter for {company} {metric}")
        values = {
            ("Microsoft", "revenue"): Decimal("400"),
            ("Microsoft", "operating_income"): Decimal("100"),
            ("Microsoft", "net_income"): Decimal("80"),
            ("Microsoft", "research_and_development"): Decimal("40"),
            ("Google", "revenue"): Decimal("200"),
            ("Google", "operating_income"): Decimal("50"),
            ("Google", "net_income"): Decimal("40"),
            ("Google", "research_and_development"): Decimal("20"),
        }
        value = values[(company, metric)]
        return SimpleNamespace(
            company_name=company,
            ticker="MSFT" if company == "Microsoft" else "GOOG",
            cik="0000789019" if company == "Microsoft" else "0001652044",
            metric=metric,
            value=value,
            currency="USD",
            start_date=date(2026, 1, 1),
            end_date=date(2026, 3, 31),
            filed_date=date(2026, 4, 29),
            form="10-Q",
            accession_number="acc",
            taxonomy="us-gaap",
            concept=metric,
            source_url="https://www.sec.gov/example.htm",
            source="sec_xbrl",
        )


class _CompareCompleter:
    def complete(self, query: str, current_spec: object = None) -> WorkflowPlan:
        from financial_analyst_agent.contracts import Intent

        return WorkflowPlan(
            intent=Intent.COMPARE,
            company=None,
            companies=["Microsoft", "Google"],
            metric="revenue",
            industry=None,
            topic=None,
        )


def _runtime(*, completer: object, facts: object | None = None):
    from financial_analyst_agent.contracts import Runtime
    from financial_analyst_agent.ranking import SnapshotRanking

    return Runtime(
        completer=completer,  # type: ignore[arg-type]
        facts=(facts or _MultiMetricFacts()),  # type: ignore[arg-type]
        ranking=SnapshotRanking.from_path(FIXTURE_UNIVERSE_SNAPSHOT_PATH),
    )


def test_multi_company_multi_metric_one_analysis(tmp_path: Path) -> None:
    from financial_analyst_agent.contracts import Intent, RendererKind
    from financial_analyst_agent.conversation import run_conversation_turn
    from financial_analyst_agent.thread_store import LocalThreadStore

    facts = _MultiMetricFacts()
    store = LocalThreadStore(tmp_path)
    message = "compare Microsoft and Google on revenue and operating margin"
    turn = run_conversation_turn(
        "t1",
        message,
        _runtime(completer=_CompareCompleter(), facts=facts),
        store=store,
    )

    assert turn.result.intent is Intent.COMPARE
    assert turn.result.renderer is RendererKind.TABLE
    assert turn.analysis_spec is not None
    assert turn.analysis_spec.metrics == ("revenue", "operating_margin")
    assert [c.query for c in turn.analysis_spec.companies] == ["Microsoft", "Google"]

    cells = {(row.ticker, row.metric): row for row in turn.result.table_rows}
    assert set(cells) == {
        ("MSFT", "revenue"),
        ("GOOG", "revenue"),
        ("MSFT", "operating_margin"),
        ("GOOG", "operating_margin"),
    }
    assert cells[("MSFT", "revenue")].value == Decimal("400")
    assert cells[("MSFT", "revenue")].components
    assert cells[("MSFT", "revenue")].components[0].accession_number == "acc"
    assert cells[("MSFT", "operating_margin")].value == Decimal("100") / Decimal("400")
    assert cells[("MSFT", "operating_margin")].components
    assert cells[("GOOG", "operating_margin")].value == Decimal("50") / Decimal("200")
    assert len(turn.result.tool_traces) == 2


def test_add_and_remove_metric_keeps_companies(tmp_path: Path) -> None:
    from financial_analyst_agent.conversation import run_conversation_turn
    from financial_analyst_agent.graph.analysis_spec import SpecPatch
    from financial_analyst_agent.thread_store import LocalThreadStore

    facts = _MultiMetricFacts()
    store = LocalThreadStore(tmp_path)
    run_conversation_turn(
        "t1",
        "compare Microsoft and Google on revenue and operating margin",
        _runtime(completer=_CompareCompleter(), facts=facts),
        store=store,
    )

    class _AddRd:
        def complete(self, query: str, current_spec: object = None) -> SpecPatch:
            return SpecPatch(mode="extend", add_metrics=("rd_to_sales",))

    turn = run_conversation_turn(
        "t1",
        "now add R&D intensity",
        _runtime(completer=_AddRd(), facts=facts),
        store=store,
    )
    assert turn.analysis_spec is not None
    assert [c.query for c in turn.analysis_spec.companies] == ["Microsoft", "Google"]
    assert turn.analysis_spec.metrics == ("revenue", "operating_margin", "rd_to_sales")
    metrics_present = {row.metric for row in turn.result.table_rows}
    assert metrics_present == {"revenue", "operating_margin", "rd_to_sales"}

    class _RemoveRevenue:
        def complete(self, query: str, current_spec: object = None) -> SpecPatch:
            return SpecPatch(mode="extend", remove_metrics=("revenue",))

    turn = run_conversation_turn(
        "t1",
        "drop revenue",
        _runtime(completer=_RemoveRevenue(), facts=facts),
        store=store,
    )
    assert turn.analysis_spec is not None
    assert [c.query for c in turn.analysis_spec.companies] == ["Microsoft", "Google"]
    assert turn.analysis_spec.metrics == ("operating_margin", "rd_to_sales")
    assert {row.metric for row in turn.result.table_rows} == {
        "operating_margin",
        "rd_to_sales",
    }


def test_missing_cell_states_reason_without_sinking_table(tmp_path: Path) -> None:
    from financial_analyst_agent.contracts import MISSING_FACT, RendererKind
    from financial_analyst_agent.conversation import run_conversation_turn
    from financial_analyst_agent.thread_store import LocalThreadStore

    facts = _MultiMetricFacts(missing={("Google", "operating_income")})
    store = LocalThreadStore(tmp_path)
    turn = run_conversation_turn(
        "t1",
        "compare Microsoft and Google on revenue and operating margin",
        _runtime(completer=_CompareCompleter(), facts=facts),
        store=store,
    )

    assert turn.result.renderer is RendererKind.TABLE
    by_company_metric = {
        (row.company_name, row.metric): row for row in turn.result.table_rows
    }
    assert by_company_metric[("Microsoft", "revenue")].value == Decimal("400")
    assert by_company_metric[("Google", "revenue")].value == Decimal("200")
    assert by_company_metric[("Microsoft", "operating_margin")].value is not None
    missing = by_company_metric[("Google", "operating_margin")]
    assert missing.value is None
    assert missing.reason == MISSING_FACT


def test_unsupported_combination_refuses_explicitly(tmp_path: Path) -> None:
    from financial_analyst_agent.contracts import RendererKind
    from financial_analyst_agent.conversation import run_conversation_turn
    from financial_analyst_agent.graph.analysis_spec import SpecPatch
    from financial_analyst_agent.thread_store import LocalThreadStore

    class _AcrossPeriodsLatest:
        def complete(self, query: str, current_spec: object = None) -> SpecPatch:
            return SpecPatch(
                mode="replace",
                add_companies=("Google",),
                add_metrics=("net_income",),
                add_operations=("across_periods",),
            )

    store = LocalThreadStore(tmp_path)
    turn = run_conversation_turn(
        "t1",
        "show Google net income across periods",
        _runtime(completer=_AcrossPeriodsLatest(), facts=_MultiMetricFacts()),
        store=store,
    )
    assert turn.result.renderer is RendererKind.REFUSE
    assert turn.result.tool_traces == []
    assert turn.analysis_spec is None
    assert turn.result.message is not None
    assert "across_periods" in turn.result.message
