"""Analysis spec: patch application, validation, and task compilation.

Internal seams in the graph package. Asserts pure outcomes without executing
providers. Does not assert LangGraph node names or checkpoint payloads.
"""

from __future__ import annotations


def test_apply_patch_replace_builds_draft_from_empty() -> None:
    from financial_analyst_agent.graph.analysis_spec import (
        SpecPatch,
        apply_patch,
    )

    patch = SpecPatch(
        mode="replace",
        add_companies=("Google",),
        add_metrics=("net_income",),
    )
    draft = apply_patch(None, patch)

    assert draft.company_queries == ("Google",)
    assert draft.metrics == ("net_income",)
    assert draft.periods.kind == "latest_quarter"
    assert draft.operations == ()
    assert draft.presentation == "table"
    assert draft.ranked_request is None


def test_apply_patch_keeps_lowest_first_across_edits_of_a_ranking() -> None:
    from financial_analyst_agent.graph.analysis_spec import (
        AnalysisSpec,
        RankedRequest,
        RankedSet,
        SpecPatch,
        apply_patch,
    )

    ranked = SpecPatch(
        mode="replace",
        ranked_request=RankedRequest(industry="banks", limit=5),
        add_metrics=("revenue",),
        add_operations=("rank", "order_by_metric", "lowest_first"),
    )
    assert "lowest_first" in apply_patch(None, ranked).operations

    current = AnalysisSpec(
        constituents=RankedSet(industry="banks", limit=5),
        metrics=("revenue",),
        operations=("rank", "order_by_metric", "lowest_first"),
    )
    # A follow-up that says nothing about the order keeps it.
    kept = apply_patch(current, SpecPatch(mode="extend", add_metrics=("net_income",)))
    assert "lowest_first" in kept.operations
    # "largest first" turns it back.
    back = apply_patch(current, SpecPatch(mode="extend", remove_operations=("lowest_first",)))
    assert "lowest_first" not in back.operations
    # "add Apple" turns the ranking into those companies, still from the lowest.
    added = apply_patch(current, SpecPatch(mode="extend", add_companies=("Apple",)))
    assert "lowest_first" in added.operations and "rank" not in added.operations


def test_apply_patch_extend_adds_and_removes_companies() -> None:
    from financial_analyst_agent.graph.analysis_spec import (
        AnalysisSpec,
        PeriodSelection,
        ResolvedCompany,
        SpecPatch,
        apply_patch,
    )

    current = AnalysisSpec(
        companies=(
            ResolvedCompany(
                cik="0001652044",
                name="Alphabet Inc.",
                ticker="GOOG",
                query="Google",
            ),
        ),
        metrics=("net_income",),
        periods=PeriodSelection(kind="latest_quarter"),
        operations=(),
        presentation="table",
    )
    patch = SpecPatch(
        mode="extend",
        add_companies=("Apple",),
        remove_companies=("Google",),
    )
    draft = apply_patch(current, patch)

    assert draft.company_queries == ("Apple",)
    assert draft.metrics == ("net_income",)


def test_apply_patch_extend_adds_company_keeps_metrics() -> None:
    from financial_analyst_agent.graph.analysis_spec import (
        AnalysisSpec,
        PeriodSelection,
        ResolvedCompany,
        SpecPatch,
        apply_patch,
    )

    current = AnalysisSpec(
        companies=(
            ResolvedCompany(
                cik="0001652044",
                name="Alphabet Inc.",
                ticker="GOOG",
                query="Google",
            ),
        ),
        metrics=("net_income",),
        periods=PeriodSelection(kind="latest_quarter"),
    )
    draft = apply_patch(
        current,
        SpecPatch(mode="extend", add_companies=("Nvidia",)),
    )
    assert draft.company_queries == ("Google", "Nvidia")
    assert draft.metrics == ("net_income",)


def test_apply_patch_replace_discards_prior_companies() -> None:
    from financial_analyst_agent.graph.analysis_spec import (
        AnalysisSpec,
        PeriodSelection,
        ResolvedCompany,
        SpecPatch,
        apply_patch,
    )

    current = AnalysisSpec(
        companies=(
            ResolvedCompany(
                cik="0001652044",
                name="Alphabet Inc.",
                ticker="GOOG",
                query="Google",
            ),
        ),
        metrics=("net_income",),
        periods=PeriodSelection(kind="latest_quarter"),
    )
    draft = apply_patch(
        current,
        SpecPatch(
            mode="replace",
            add_companies=("Microsoft",),
            add_metrics=("revenue",),
        ),
    )
    assert draft.company_queries == ("Microsoft",)
    assert draft.metrics == ("revenue",)


def test_apply_patch_ignores_model_typed_companies_when_ranked_request_set() -> None:
    from financial_analyst_agent.graph.analysis_spec import (
        RankedRequest,
        SpecPatch,
        apply_patch,
    )

    draft = apply_patch(
        None,
        SpecPatch(
            mode="replace",
            add_companies=("FakeCo", "OtherCo"),
            add_metrics=("net_income",),
            ranked_request=RankedRequest(industry="healthcare", limit=10),
        ),
    )
    assert draft.company_queries == ()
    assert draft.ranked_request == RankedRequest(industry="healthcare", limit=10)
    assert draft.metrics == ("net_income",)


def test_validate_spec_rejects_unknown_metric_before_providers() -> None:
    from financial_analyst_agent.graph.analysis_spec import (
        AnalysisSpec,
        PeriodSelection,
        ResolvedCompany,
        SpecRejection,
        validate_spec,
    )

    spec = AnalysisSpec(
        companies=(
            ResolvedCompany(
                cik="0001652044",
                name="Alphabet Inc.",
                ticker="GOOG",
                query="Google",
            ),
        ),
        metrics=("not_a_real_metric",),
        periods=PeriodSelection(kind="latest_quarter"),
    )
    outcome = validate_spec(spec)
    assert isinstance(outcome, SpecRejection)
    assert outcome.code == "invalid_metric"
    assert outcome.details["term"] == "not_a_real_metric"


def test_metric_rejection_names_the_term_and_the_allowed_metrics() -> None:
    from financial_analyst_agent.contracts import ALLOWED_METRICS, unknown_metric_message
    from financial_analyst_agent.graph.analysis_spec import metric_rejection

    assert metric_rejection(("revenue", "net_income")) is None

    rejection = metric_rejection(("revenue", "not_a_real_metric", "another_bad_one"))

    assert rejection is not None
    assert rejection.code == "invalid_metric"
    assert rejection.message == unknown_metric_message("not_a_real_metric")
    assert rejection.details == {"term": "not_a_real_metric", "allowed": list(ALLOWED_METRICS)}


def test_apply_patch_extend_edits_keep_order_and_add_each_item_once() -> None:
    from financial_analyst_agent.graph.analysis_spec import (
        AnalysisSpec,
        ResolvedCompany,
        SpecPatch,
        apply_patch,
    )

    current = AnalysisSpec(
        companies=(
            ResolvedCompany(cik="0000789019", name="Microsoft Corp", ticker="MSFT", query="MSFT"),
            ResolvedCompany(cik="0001652044", name="Alphabet Inc.", ticker="GOOG", query="Google"),
        ),
        metrics=("revenue", "net_income"),
        operations=("across_companies", "order_by_metric"),
    )
    patch = SpecPatch(
        mode="extend",
        add_companies=("Apple", "Google", "Apple"),
        remove_companies=("Microsoft",),
        add_metrics=("net_income", "eps_diluted", "eps_diluted"),
        remove_metrics=("revenue",),
        add_operations=("lowest_first", "order_by_metric"),
        remove_operations=("across_companies",),
    )

    draft = apply_patch(current, patch)

    # Kept items first in their order; added ones follow, each once, none twice.
    assert draft.company_queries == ("Google", "Apple")
    assert draft.metrics == ("net_income", "eps_diluted")
    assert draft.operations == ("order_by_metric", "lowest_first")


def test_validate_spec_rejects_empty_analysis() -> None:
    from financial_analyst_agent.graph.analysis_spec import (
        AnalysisSpec,
        PeriodSelection,
        SpecRejection,
        validate_spec,
    )

    outcome = validate_spec(
        AnalysisSpec(
            companies=(),
            metrics=("net_income",),
            periods=PeriodSelection(kind="latest_quarter"),
        )
    )
    assert isinstance(outcome, SpecRejection)
    assert outcome.code == "empty_spec"


def test_compile_tasks_lookup_without_executing() -> None:
    from financial_analyst_agent.graph.analysis_spec import (
        AnalysisSpec,
        CompiledTask,
        PeriodSelection,
        ResolvedCompany,
        compile_tasks,
    )

    spec = AnalysisSpec(
        companies=(
            ResolvedCompany(
                cik="0001652044",
                name="Alphabet Inc.",
                ticker="GOOG",
                query="Google",
            ),
        ),
        metrics=("net_income",),
        periods=PeriodSelection(kind="latest_quarter"),
    )
    tasks = compile_tasks(spec)
    assert tasks == (
        CompiledTask(
            kind="lookup",
            issuers=("0001652044",),
            metric="net_income",
        ),
    )


def test_compile_tasks_compare_for_two_companies() -> None:
    from financial_analyst_agent.graph.analysis_spec import (
        AnalysisSpec,
        CompiledTask,
        PeriodSelection,
        ResolvedCompany,
        compile_tasks,
    )

    spec = AnalysisSpec(
        companies=(
            ResolvedCompany(
                cik="0000789019",
                name="Microsoft",
                ticker="MSFT",
                query="Microsoft",
            ),
            ResolvedCompany(
                cik="0001652044",
                name="Alphabet Inc.",
                ticker="GOOG",
                query="Google",
            ),
        ),
        metrics=("operating_margin",),
        periods=PeriodSelection(kind="latest_quarter"),
        operations=("across_companies",),
    )
    tasks = compile_tasks(spec)
    assert tasks == (
        CompiledTask(
            kind="compare",
            issuers=("0000789019", "0001652044"),
            metric="operating_margin",
        ),
    )


def test_compile_tasks_one_independent_task_per_metric() -> None:
    from financial_analyst_agent.graph.analysis_spec import (
        AnalysisSpec,
        CompiledTask,
        PeriodSelection,
        ResolvedCompany,
        compile_tasks,
    )

    spec = AnalysisSpec(
        companies=(
            ResolvedCompany(
                cik="0000789019",
                name="Microsoft",
                ticker="MSFT",
                query="Microsoft",
            ),
            ResolvedCompany(
                cik="0001652044",
                name="Alphabet Inc.",
                ticker="GOOG",
                query="Google",
            ),
        ),
        metrics=("revenue", "operating_margin"),
        periods=PeriodSelection(kind="latest_quarter"),
        operations=("across_companies",),
    )
    tasks = compile_tasks(spec)
    assert tasks == (
        CompiledTask(
            kind="compare",
            issuers=("0000789019", "0001652044"),
            metric="revenue",
        ),
        CompiledTask(
            kind="compare",
            issuers=("0000789019", "0001652044"),
            metric="operating_margin",
        ),
    )


def test_compile_tasks_multi_metric_lookup_is_one_task_per_metric() -> None:
    from financial_analyst_agent.graph.analysis_spec import (
        AnalysisSpec,
        CompiledTask,
        PeriodSelection,
        ResolvedCompany,
        compile_tasks,
    )

    spec = AnalysisSpec(
        companies=(
            ResolvedCompany(
                cik="0001652044",
                name="Alphabet Inc.",
                ticker="GOOG",
                query="Google",
            ),
        ),
        metrics=("revenue", "net_income"),
        periods=PeriodSelection(kind="latest_quarter"),
    )
    tasks = compile_tasks(spec)
    assert tasks == (
        CompiledTask(kind="lookup", issuers=("0001652044",), metric="revenue"),
        CompiledTask(kind="lookup", issuers=("0001652044",), metric="net_income"),
    )


def test_validate_spec_refuses_across_periods_without_window() -> None:
    from financial_analyst_agent.graph.analysis_spec import (
        AnalysisSpec,
        PeriodSelection,
        ResolvedCompany,
        SpecRejection,
        validate_spec,
    )

    outcome = validate_spec(
        AnalysisSpec(
            companies=(
                ResolvedCompany(
                    cik="0001652044",
                    name="Alphabet Inc.",
                    ticker="GOOG",
                    query="Google",
                ),
            ),
            metrics=("net_income",),
            periods=PeriodSelection(kind="latest_quarter"),
            operations=("across_periods",),
        )
    )
    assert isinstance(outcome, SpecRejection)
    assert outcome.code == "unsupported_combination"
    assert "across_periods" in outcome.message


def test_validate_spec_allows_across_periods_with_window() -> None:
    from financial_analyst_agent.graph.analysis_spec import (
        AnalysisSpec,
        PeriodSelection,
        ResolvedCompany,
        validate_spec,
    )

    outcome = validate_spec(
        AnalysisSpec(
            companies=(
                ResolvedCompany(
                    cik="0001652044",
                    name="Alphabet Inc.",
                    ticker="GOOG",
                    query="Google",
                ),
            ),
            metrics=("net_income",),
            periods=PeriodSelection(kind="last_n_quarters", count=4),
            operations=("across_periods",),
        )
    )
    assert outcome is None

def test_compile_tasks_fans_out_last_n_report_dates() -> None:
    from datetime import date

    from financial_analyst_agent.graph.analysis_spec import (
        AnalysisSpec,
        CompiledTask,
        PeriodSelection,
        ResolvedCompany,
        compile_tasks,
    )

    q2 = date(2025, 6, 30)
    q1 = date(2025, 3, 31)
    spec = AnalysisSpec(
        companies=(
            ResolvedCompany(
                cik="0000789019",
                name="Microsoft",
                ticker="MSFT",
                query="Microsoft",
            ),
        ),
        metrics=("revenue",),
        periods=PeriodSelection(
            kind="last_n_quarters",
            count=2,
            report_dates=(q2, q1),
        ),
    )
    tasks = compile_tasks(spec)
    assert tasks == (
        CompiledTask(
            kind="lookup",
            issuers=("0000789019",),
            metric="revenue",
            report_date=q2,
        ),
        CompiledTask(
            kind="lookup",
            issuers=("0000789019",),
            metric="revenue",
            report_date=q1,
        ),
    )


def test_compile_tasks_rank_and_lookup_from_constituents() -> None:
    from financial_analyst_agent.graph.analysis_spec import (
        AnalysisSpec,
        CompiledTask,
        PeriodSelection,
        RankedSet,
        ResolvedCompany,
        compile_tasks,
    )

    spec = AnalysisSpec(
        companies=(),
        constituents=RankedSet(
            industry="healthcare",
            limit=10,
            members=(
                ResolvedCompany(
                    cik="1",
                    name="A",
                    ticker="A",
                    query="A",
                ),
            ),
        ),
        metrics=("net_income",),
        periods=PeriodSelection(kind="latest_quarter"),
        operations=("rank",),
    )
    tasks = compile_tasks(spec)
    assert tasks == (
        CompiledTask(
            kind="rank_and_lookup",
            industry="healthcare",
            limit=10,
            metric="net_income",
        ),
    )


def test_compile_tasks_rank_without_metric() -> None:
    from financial_analyst_agent.graph.analysis_spec import (
        AnalysisSpec,
        CompiledTask,
        PeriodSelection,
        RankedSet,
        compile_tasks,
    )

    spec = AnalysisSpec(
        constituents=RankedSet(industry="technology", limit=5, members=()),
        metrics=(),
        periods=PeriodSelection(kind="latest_quarter"),
        operations=("rank",),
    )
    tasks = compile_tasks(spec)
    assert tasks == (
        CompiledTask(kind="rank", industry="technology", limit=5),
    )


def test_resolve_spec_fills_ranked_constituents_from_port_not_model_list() -> None:
    from types import SimpleNamespace

    from financial_analyst_agent.graph.analysis_spec import (
        RankedRequest,
        SpecDraft,
        resolve_spec,
    )

    class _Ranking:
        def rank_companies(self, industry: str, limit: int) -> SimpleNamespace:
            assert industry == "healthcare"
            assert limit == 2
            return SimpleNamespace(
                companies=(
                    SimpleNamespace(
                        cik="0000320193",
                        name="Real Co",
                        ticker="REAL",
                    ),
                )
            )

        def lookup_member(self, company: str) -> SimpleNamespace:
            raise AssertionError(f"must not resolve model-typed {company!r}")

    draft = SpecDraft(
        company_queries=("FakeCo",),
        metrics=("net_income",),
        ranked_request=RankedRequest(industry="healthcare", limit=2),
    )
    spec = resolve_spec(draft, ranking=_Ranking())
    assert spec.companies == ()
    assert spec.constituents is not None
    assert spec.constituents.industry == "healthcare"
    assert [m.ticker for m in spec.constituents.members] == ["REAL"]


def test_a_held_ranking_stored_as_a_pair_still_loads() -> None:
    # A clarification held before rankings had a type stored ("banks", 5).
    from financial_analyst_agent.graph.analysis_spec import RankedRequest, SpecPatch

    patch = SpecPatch.model_validate_json('{"mode": "replace", "ranked_request": ["banks", 5]}')

    assert patch.ranked_request == RankedRequest(industry="banks", limit=5)
