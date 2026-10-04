"""Resolve a structured request into compiled tasks, run them, and merge the answer.

The analysis graph's structured steps call into here: ``resolve_request``
(patch → resolve → date the periods against filings → validate → compile),
``dispatch_compiled_tasks`` (the bounded, deadline-aware provider fan-out), and
the deterministic merge of the task results: change rows, ordering, history and
notes. The analyst's wording is read by ``request_wording``; the notes' text is
``answer_notes``.
"""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from concurrent.futures import TimeoutError as FuturesTimeout
from contextvars import copy_context
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from functools import partial
from typing import Any

from financial_analyst_agent.answer_notes import (
    already_present_notes,
    annual_filer_note,
    capped_ranking_notes,
    period_notes,
    short_ranking_notes,
)
from financial_analyst_agent.contracts import (
    ALLOWED_METRICS,
    DEFAULT_RANK_LIMIT,
    LOOKUP_FAILED,
    MISSING_FACT,
    NOT_OPERATING_COMPANY,
    QUALITATIVE_INTENTS,
    SNAPSHOT_METRICS,
    SOURCE_UNAVAILABLE,
    STRUCTURED_INTENTS,
    TRAILING_YEAR_FORMULAS,
    ComparisonBase,
    ComponentProvenance,
    Intent,
    Refusal,
    RendererKind,
    Runtime,
    TableRow,
    ToolTrace,
    TurnResult,
    WorkflowPlan,
    refusal_from_error,
    split_between,
    unknown_metric_message,
)
from financial_analyst_agent.domain.errors import (
    SOURCE_FAILURES,
    AmbiguousCompanyError,
    CompanyNotFoundError,
    FinancialAnalystError,
    ProviderError,
    ProviderRefusal,
    SessionQuotaError,
    UnknownIndustryError,
)
from financial_analyst_agent.graph.analysis_spec import (
    MAX_QUARTERS_ASKED,
    AnalysisSpec,
    CompiledTask,
    NamedPeriodSpec,
    PeriodSelection,
    RankedRequest,
    ResolvedCompany,
    SpecDraft,
    SpecPatch,
    SpecRejection,
    apply_patch,
    compile_tasks,
    emptied_by,
    resolve_spec,
    validate_spec,
)
from financial_analyst_agent.graph.state import CompiledAnalysis, StructuredRequest
from financial_analyst_agent.guide import in_sentence, short_name
from financial_analyst_agent.providers.sec.client import sec_turn_seconds_left
from financial_analyst_agent.providers.sec.company_resolver import resolve_company
from financial_analyst_agent.request_wording import (
    COMPARISON_CANDIDATES,
    COMPARISON_LABELS,
    FORECAST,
    INVALID_QUARTER,
    OVERVIEW_METRICS,
    bind_metrics_from_message,
    comparison_asked,
    refine_patch_from_message,
    unique_metrics_from_phrase,
)
from financial_analyst_agent.services.filing_selector import FISCAL_WEEK_TOLERANCE
from financial_analyst_agent.services.fiscal_periods import (
    adjacent_quarters,
    calendar_quarter,
    dates_for,
    one_year_earlier,
)
from financial_analyst_agent.turn import (
    compare_task,
    lookup_task,
    rank_and_lookup_task,
    rank_task,
    reason_for_code,
)

# Bound concurrent provider fan-out so a wide window cannot flood SEC/EDGAR.
DEFAULT_TASK_MAX_WORKERS = 8

ProgressCallback = Callable[[int, int], None]


def plan_to_spec_patch(plan: WorkflowPlan) -> SpecPatch:
    """Lift a one-shot closed plan into a replace-mode spec patch."""
    patch = _lifted_plan(plan)
    window = plan.recent_quarters
    if window is not None and window >= 1 and plan.intent is not Intent.RANK:
        # The model's reading of a window: used only where the wording's own
        # reading finds none (see planner_window).
        selection = PeriodSelection(kind="last_n_quarters", count=min(window, MAX_QUARTERS_ASKED))
        patch = patch.model_copy(update={"set_periods": selection})
    return patch


def _lifted_plan(plan: WorkflowPlan) -> SpecPatch:
    """The plan's companies, metric and ranking as a replace patch."""
    intent = plan.intent
    metrics = (plan.metric,) if plan.metric else ()
    if intent is Intent.LOOKUP:
        # A question naming no company names none: "the" or "unknown" is not one.
        company = plan.company if plan.company and plan.company != "unknown" else None
        return SpecPatch(
            mode="replace", add_companies=(company,) if company else (), add_metrics=metrics
        )
    if intent is Intent.COMPARE:
        return SpecPatch(
            mode="replace",
            add_companies=plan.companies,
            add_metrics=metrics,
            add_operations=(
                ("across_companies", "order_by_metric")
                if plan.order_by_metric
                else ("across_companies",)
            ),
        )
    if intent not in (Intent.RANK, Intent.RANK_AND_LOOKUP):
        raise ValueError(f"cannot lift intent to spec patch: {intent!r}")
    ranked = RankedRequest(industry=plan.industry or "", limit=plan.limit or DEFAULT_RANK_LIMIT)
    if intent is Intent.RANK:
        return SpecPatch(mode="replace", ranked_request=ranked)
    return SpecPatch(
        mode="replace",
        ranked_request=ranked,
        add_metrics=metrics,
        add_operations=("rank", "order_by_metric") if plan.order_by_metric else ("rank",),
    )


def _listed_dates(listing: Any, company: str, count: int) -> tuple[date, ...]:
    return tuple(listing(company, limit=count))


def materialize_period_dates(spec: AnalysisSpec, runtime: Runtime) -> AnalysisSpec:
    """Fill last_n_quarters report dates from the facts port.

    The first company's quarter ends become ``report_dates``; every other named
    company gets its own, so a company on a different fiscal calendar is asked
    for its quarters rather than the first company's. Dates already on the spec
    are kept, so a follow-up that adds a company lists only that company.
    """
    if spec.periods.kind == "named":
        return _materialize_named_periods(spec, runtime)
    if spec.periods.kind != "last_n_quarters":
        return spec
    listing = getattr(runtime.facts, "list_quarterly_report_dates", None)
    if listing is None:
        return spec
    first = spec.companies[0] if spec.companies else None
    if first is None and spec.constituents is not None and spec.constituents.members:
        first = spec.constituents.members[0]
    if first is None:
        return spec
    periods = spec.periods
    listed_first = False
    if not periods.report_dates:
        dates = _listed_dates(listing, first.handle, periods.count or 1)
        if not dates:
            return spec
        asked = periods.count if periods.count and len(dates) < periods.count else None
        periods = periods.model_copy(
            update={"count": len(dates), "report_dates": dates, "asked": asked}
        )
        listed_first = True
    known = dict(periods.company_report_dates)
    if listed_first and spec.companies:
        known[first.key] = periods.report_dates
    for company in spec.companies:
        key = company.key
        if key in known:
            continue
        try:
            dates = _listed_dates(listing, company.handle, periods.count or 1)
        except SessionQuotaError:
            raise
        except Exception:
            # This company's cells report their own failure; it must not refuse
            # the whole window for the companies that do resolve.
            continue
        if dates:
            known[key] = dates
    periods = periods.model_copy(update={"company_report_dates": tuple(known.items())})
    if periods == spec.periods:
        return spec
    return spec.model_copy(update={"periods": periods})


def _named_dates(periods: Any, named: tuple[NamedPeriodSpec, ...]) -> tuple[date, ...]:
    matched = {
        day
        for spec in named
        for day in dates_for(tuple(periods), spec.year, spec.quarter, calendar=spec.calendar)
    }
    return tuple(sorted(matched, reverse=True))


def _materialize_named_periods(spec: AnalysisSpec, runtime: Runtime) -> AnalysisSpec:
    """Each company's own quarter ends for the named periods (ADR 0007).

    "Q3 FY2024" is Apple's quarter ended June 29 and Microsoft's ended March 31;
    each company's filings say which is which. A company without a filing for
    the period gets no cells, and the turn says so.
    """
    lister = getattr(runtime.facts, "fiscal_periods", None)
    if lister is None:
        return spec
    periods = spec.periods
    known = dict(periods.company_report_dates)
    for company in spec.companies:
        key = company.key
        if key in known:
            continue
        try:
            listed = lister(company.handle)
        except SessionQuotaError:
            raise
        except Exception:
            # This company's cells report their own failure.
            continue
        known[key] = _named_dates(listed, periods.named)
    first = next(
        (known[company.key] for company in spec.companies if known.get(company.key)),
        (),
    )
    longest = max((len(dates) for dates in known.values()), default=0)
    updated = periods.model_copy(
        update={
            "report_dates": first,
            "count": longest or None,
            "company_report_dates": tuple(known.items()),
        }
    )
    if updated == periods:
        return spec
    return spec.model_copy(update={"periods": updated})


def drop_annual_filers(spec: AnalysisSpec, runtime: Runtime) -> tuple[AnalysisSpec, list[str]]:
    """Leave out named companies that file annual 20-F/40-F reports instead of 10-Qs.

    A foreign private issuer such as Novo Nordisk has no quarterly facts, so
    every cell would read "Missing fact"; the turn says why instead.
    """
    checker = getattr(runtime.facts, "files_quarterly", None)
    if checker is None or not spec.companies:
        return spec, []
    kept: list[Any] = []
    dropped: list[str] = []
    for company in spec.companies:
        try:
            quarterly, name = checker(company.handle)
        except SessionQuotaError:
            raise
        except Exception:
            # Resolution problems surface through the company's own cells.
            kept.append(company)
            continue
        if quarterly:
            kept.append(company)
        else:
            dropped.append(short_name(company.name if company.cik else name) or company.query)
    if not dropped:
        return spec, []
    return spec.model_copy(update={"companies": tuple(kept)}), dropped


def sec_identity(runtime: Runtime) -> Callable[[str], ResolvedCompany | None] | None:
    """Pin a name the snapshot leaves out to its SEC company, from SEC's ticker map.

    The facts lookup resolves names the same way, so a cell finds the company the
    spec names. A name SEC does not know, or knows as several companies, stays a
    name: its cells say so. Without a filings port (a test runtime), nothing.
    """
    filings = runtime.filings
    if filings is None:
        return None

    def identify(query: str) -> ResolvedCompany | None:
        try:
            company = resolve_company(query, filings.get_company_tickers())
        except (CompanyNotFoundError, AmbiguousCompanyError, *SOURCE_FAILURES):
            return None
        ticker = company.tickers[0] if company.tickers else ""
        return ResolvedCompany(cik=company.cik, name=company.name, ticker=ticker, query=query)

    return identify


def is_filing_change_proposal(proposal: WorkflowPlan | SpecPatch) -> bool:
    return isinstance(proposal, WorkflowPlan) and proposal.intent is Intent.FILING_CHANGE


def is_qualitative_proposal(proposal: WorkflowPlan | SpecPatch) -> bool:
    return isinstance(proposal, WorkflowPlan) and proposal.intent in QUALITATIVE_INTENTS


def is_structured_proposal(proposal: WorkflowPlan | SpecPatch) -> bool:
    return isinstance(proposal, SpecPatch) or proposal.intent in STRUCTURED_INTENTS


def _draft_intent(draft: SpecDraft) -> Intent:
    """The closed intent a draft's shape asks for, when no planned intent came with it."""
    if draft.ranked_request is not None:
        return Intent.RANK_AND_LOOKUP if draft.metrics else Intent.RANK
    return Intent.COMPARE if len(draft.company_queries) > 1 else Intent.LOOKUP


def _rejection_result(rejection: SpecRejection, intent: Intent) -> TurnResult:
    return TurnResult(
        intent=intent,
        tool_traces=[],
        renderer=RendererKind.REFUSE,
        message=rejection.message,
        refusal=Refusal(code=rejection.code, details=rejection.details),
    )


# One deterministic workflow per compiled task kind: the closed set a task can run.
TASK_WORKFLOWS: dict[str, Callable[[CompiledTask, Runtime], TurnResult]] = {
    "lookup": lookup_task,
    "compare": compare_task,
    "rank": rank_task,
    "rank_and_lookup": rank_and_lookup_task,
}


def execute_compiled_task(task: CompiledTask, runtime: Runtime) -> TurnResult:
    """Run one compiled cell through the workflow for its kind."""
    return TASK_WORKFLOWS[task.kind](task, runtime)


TASK_FAILURE_MESSAGE = "This part of the analysis could not be completed. Please try again."
SOURCE_UNAVAILABLE_MESSAGE = (
    "SEC EDGAR could not be reached just now, so this could not be answered. "
    "Please try again in a few minutes."
)
# How long the tasks may run past the turn's SEC budget: parsing what was read.
_TASK_GRACE_SECONDS = 15.0


def _missing_cell(
    company: str, metric: str, report_date: date | None, reason: str = MISSING_FACT
) -> TableRow:
    return TableRow(
        company_name=company,
        ticker="",
        cik="",
        metric=metric,
        end_date=report_date,
        reason=reason,
    )


def _task_failure_result(task: CompiledTask, exc: BaseException) -> TurnResult:
    """Isolate an unexpected cell failure as a typed partial or refuse.

    Neither a source failure (an EDGAR outage, retries exhausted, a full disk)
    nor a fault of ours is evidence that the filing lacks the fact, so each
    gets its own reason. The raw exception text never reaches the visitor.
    """
    reason = SOURCE_UNAVAILABLE if isinstance(exc, SOURCE_FAILURES) else LOOKUP_FAILED
    if task.kind in ("lookup", "compare") and task.issuers and task.metric:
        companies = task.issuers[:1] if task.kind == "lookup" else task.issuers
        return TurnResult(
            intent=Intent(task.kind),
            tool_traces=[],
            renderer=RendererKind.TABLE,
            table_rows=[
                _missing_cell(company, task.metric, task.report_date, reason)
                for company in companies
            ],
        )
    return TurnResult(
        intent=Intent.LOOKUP,
        tool_traces=[],
        renderer=RendererKind.REFUSE,
        message=TASK_FAILURE_MESSAGE,
    )


def dispatch_compiled_tasks(
    tasks: tuple[CompiledTask, ...],
    runtime: Runtime,
    *,
    on_progress: ProgressCallback | None = None,
    max_workers: int = DEFAULT_TASK_MAX_WORKERS,
) -> list[TurnResult]:
    """Run independent compiled tasks concurrently; preserve task order in results.

    Worker count is capped so a wide company × metric × period fan-out cannot
    open unbounded provider connections. Completion order does not affect merge
    order: results are always returned in ``tasks`` order.
    """
    total = len(tasks)
    if total == 0:
        return []
    if total == 1 or max_workers <= 1:
        results: list[TurnResult] = []
        for index, task in enumerate(tasks):
            try:
                results.append(execute_compiled_task(task, runtime))
            except SessionQuotaError:
                raise
            except Exception as exc:
                results.append(_task_failure_result(task, exc))
            if on_progress is not None:
                on_progress(index + 1, total)
        return results

    workers = min(max_workers, total)
    ordered: list[TurnResult | None] = [None] * total
    done = 0
    pool = ThreadPoolExecutor(max_workers=workers)
    try:
        futures = {
            pool.submit(
                copy_context().run,
                partial(execute_compiled_task, task, runtime),
            ): index
            for index, task in enumerate(tasks)
        }
        left = sec_turn_seconds_left()
        timeout = None if left == float("inf") else max(0.0, left) + _TASK_GRACE_SECONDS
        try:
            for future in as_completed(futures, timeout=timeout):
                index = futures[future]
                try:
                    ordered[index] = future.result()
                except SessionQuotaError:
                    raise
                except Exception as exc:
                    ordered[index] = _task_failure_result(tasks[index], exc)
                done += 1
                if on_progress is not None:
                    on_progress(done, total)
        except FuturesTimeout:
            # The turn's time is up: what is still running answers as unavailable.
            late = ProviderError("The turn's time for SEC requests is spent")
            for index, result in enumerate(ordered):
                if result is None:
                    ordered[index] = _task_failure_result(tasks[index], late)
            pool.shutdown(wait=False, cancel_futures=True)
            return [result for result in ordered if result is not None]
    except BaseException:
        # A quota stop (or any escape) must not wait for the queued tasks to run.
        pool.shutdown(wait=False, cancel_futures=True)
        raise
    pool.shutdown(wait=True)
    assert all(result is not None for result in ordered)
    return [result for result in ordered if result is not None]


def _lookup_refuse_as_partial(task: CompiledTask, result: TurnResult) -> list[TableRow]:
    """Convert a whole-lookup refuse into a cell so multi-metric tables stay partial."""
    if result.renderer is not RendererKind.REFUSE:
        return list(result.table_rows)
    if task.kind != "lookup" or not task.issuers or not task.metric:
        return list(result.table_rows)
    # The refusal's error says why, as it does in a comparison (ADR 0002): a fund in
    # a window of quarters, or an unknown company, reads alike in every cell.
    codes = [
        trace.provenance["error"].get("code")
        for trace in result.tool_traces
        if isinstance(trace.provenance.get("error"), dict)
    ]
    reason = next(
        (reason_for_code(code) for code in codes if reason_for_code(code) != MISSING_FACT),
        MISSING_FACT,
    )
    return [_missing_cell(task.issuers[0], task.metric, task.report_date, reason)]


def _subtracted_level_provenance(row: TableRow) -> ComponentProvenance:
    """The level a change row subtracts, with the facts it came from.

    A margin level keeps its formula inputs and a derived quarter its source
    facts, so the change's evidence shows every filing behind both levels.
    """
    assert row.value is not None
    assert row.start_date is not None
    assert row.end_date is not None
    return ComponentProvenance(
        metric=row.metric,
        value=row.value,
        start_date=row.start_date,
        end_date=row.end_date,
        form=row.form or "",
        accession_number=row.accession_number or "",
        taxonomy=row.taxonomy or "",
        concept=row.concept or row.metric,
        source_url=row.source_url or "",
        source="sec_xbrl",
        derivation=row.derivation,
        derived_from=list(row.components) or list(row.derived_from),
    )


def _change_row(
    current: TableRow, prior: ComponentProvenance, *, comparison: ComparisonBase
) -> TableRow:
    assert current.value is not None
    return TableRow(
        company_name=current.company_name,
        ticker=current.ticker,
        cik=current.cik,
        metric=current.metric,
        value=Decimal(str(current.value)) - Decimal(str(prior.value)),
        currency=current.currency,
        start_date=prior.start_date,
        end_date=current.end_date,
        components=[prior, _subtracted_level_provenance(current)],
        comparison=comparison,
    )


def _year_earlier_level(
    row: TableRow, ordered: list[TableRow], *, comparatives_only: bool
) -> ComponentProvenance | None:
    """The level a year-over-year change starts from.

    The comparative the row's own filing reports comes first: it is on the same
    basis after a restatement (Bank of America's revenue) or a share split
    (NVIDIA's diluted EPS of $0.60, first filed as $5.98). The year-earlier row
    as first filed serves only when the filing reports no comparative, and only
    when it is in the window unless the analyst asked for year over year alone.
    """
    prior = _yoy_prior(row, ordered)
    if row.year_earlier is not None and (prior is not None or comparatives_only):
        return row.year_earlier
    if prior is None or split_between(row, prior):
        return None
    return _subtracted_level_provenance(prior)


def _yoy_prior(row: TableRow, ordered: list[TableRow]) -> TableRow | None:
    """The row a year earlier, allowing for 52/53-week fiscal calendars."""
    assert row.end_date is not None
    target = one_year_earlier(row.end_date)
    best: TableRow | None = None
    for candidate in ordered:
        if candidate is row or candidate.end_date is None:
            continue
        distance = abs(candidate.end_date - target)
        if distance > FISCAL_WEEK_TOLERANCE:
            continue
        if best is None or distance < abs((best.end_date or date.min) - target):
            best = candidate
    return best


def across_period_change_rows(
    levels: list[TableRow], *, sequential: bool = True
) -> list[TableRow]:
    """Sequential and year-over-year change from period-aligned level cells.

    ``sequential`` is off when the analyst asked for year-over-year change only.
    """
    by_key: dict[tuple[str, str], list[TableRow]] = {}
    for row in levels:
        if row.value is None or row.end_date is None or row.comparison is not None:
            continue
        by_key.setdefault((row.cik or row.company_name, row.metric), []).append(row)

    changes: list[TableRow] = []
    for group in by_key.values():
        ordered = sorted(group, key=lambda r: r.end_date or date.min, reverse=True)
        for newer, older in zip(ordered, ordered[1:], strict=False):
            assert newer.end_date is not None and older.end_date is not None
            # A missing quarter in the window must not turn into a two-quarter
            # change labelled "sequential"; per-share figures across a split
            # count different shares.
            if (
                sequential
                and adjacent_quarters(newer.end_date, older.end_date)
                and not split_between(newer, older)
            ):
                changes.append(
                    _change_row(
                        newer, _subtracted_level_provenance(older), comparison="sequential"
                    )
                )
        for row in ordered:
            prior = _year_earlier_level(row, ordered, comparatives_only=not sequential)
            if prior is not None:
                changes.append(_change_row(row, prior, comparison="year_over_year"))
    return changes


def merge_task_results(
    tasks: tuple[CompiledTask, ...],
    results: list[TurnResult],
    *,
    across_periods: bool = False,
    sequential: bool = True,
) -> TurnResult:
    """Assemble independent cell results into one analysis table."""
    if len(results) == 1 and not across_periods:
        return results[0]

    rows: list[TableRow] = []
    traces: list[ToolTrace] = []
    banners: list[str] = []
    snapshot_as_of = None
    for task, result in zip(tasks, results, strict=True):
        if result.renderer is RendererKind.REFUSE and not result.table_rows:
            rows.extend(_lookup_refuse_as_partial(task, result))
            # The trace says why the cell is empty, as a single lookup's refusal does.
            traces.extend(result.tool_traces)
            continue
        rows.extend(result.table_rows)
        traces.extend(result.tool_traces)
        for banner in result.banners:
            if banner not in banners:
                banners.append(banner)
        snapshot_as_of = snapshot_as_of or result.snapshot_as_of

    if not rows and any(r.renderer is RendererKind.REFUSE for r in results):
        # Every task refused with no cells — surface the first refuse.
        for result in results:
            if result.renderer is RendererKind.REFUSE:
                return result

    if across_periods:
        rows = list(rows) + across_period_change_rows(rows, sequential=sequential)

    intent = results[0].intent
    if any(task.kind == "compare" for task in tasks):
        intent = Intent.COMPARE
    elif any(task.kind == "rank_and_lookup" for task in tasks):
        intent = Intent.RANK_AND_LOOKUP
    elif any(task.kind == "rank" for task in tasks):
        intent = Intent.RANK

    return TurnResult(
        intent=intent,
        tool_traces=traces,
        renderer=RendererKind.TABLE,
        table_rows=rows,
        banners=banners,
        snapshot_as_of=snapshot_as_of,
    )


def _order_by_metric(result: TurnResult, metric: str) -> TurnResult:
    """Order a ranking's market-cap members by ``metric``, largest first.

    Membership stays the snapshot's top N by market cap: ranking a whole
    industry by a filed metric would mean a lookup per company in it.
    """
    latest: dict[str, TableRow] = {}
    for row in result.table_rows:
        if row.metric != metric or row.comparison is not None or not row.cik:
            continue
        shown = latest.get(row.cik)
        if shown is None or (row.end_date or date.min) > (shown.end_date or date.min):
            latest[row.cik] = row
    ranks = {row.cik: row.rank for row in result.table_rows if row.cik and row.rank is not None}
    if not latest or not ranks:
        return result

    def key(cik: str) -> tuple[bool, Decimal, int]:
        row = latest.get(cik)
        value = row.value if row is not None else None
        return (value is None, -(value or Decimal(0)), ranks[cik] or 0)

    order = {cik: index for index, cik in enumerate(sorted(ranks, key=key), start=1)}
    rows = sorted(
        (
            row.model_copy(update={"rank": order[row.cik]}) if row.cik in order else row
            for row in result.table_rows
        ),
        key=lambda row: (row.rank is None, row.rank or 0),
    )
    return result.model_copy(update={"table_rows": rows, "ordered_by": metric})


def _order_companies_by_metric(result: TurnResult, metric: str) -> TurnResult:
    """Order named companies by their latest ``metric``, largest first ("sort by revenue")."""
    latest: dict[str, TableRow] = {}
    for row in result.table_rows:
        if row.metric != metric or row.comparison is not None or row.value is None:
            continue
        key = row.cik or row.company_name
        shown = latest.get(key)
        if shown is None or (row.end_date or date.min) > (shown.end_date or date.min):
            latest[key] = row
    if not latest:
        return result
    first_seen = list(dict.fromkeys(row.cik or row.company_name for row in result.table_rows))

    def order(company: str) -> tuple[bool, Decimal, int]:
        row = latest.get(company)
        value = row.value if row is not None else None
        return (value is None, -(value or Decimal(0)), first_seen.index(company))

    ranking = {company: index for index, company in enumerate(sorted(first_seen, key=order))}
    rows = sorted(result.table_rows, key=lambda row: ranking[row.cik or row.company_name])
    return result.model_copy(update={"table_rows": rows})


def _fill_identity(result: TurnResult, spec: AnalysisSpec) -> TurnResult:
    """Give a failed cell the company's name and ticker, not the handle it was asked by.

    A cell that never reached a filing carries only what the providers were asked
    for (a CIK); the spec says which company that is, so show that one.
    """
    known = {
        company.handle.casefold(): company
        for company in spec.companies
        if company.cik and company.name
    }
    if not known or not any(not row.cik for row in result.table_rows):
        return result
    # The name the company's other cells already show, so one table names it once.
    shown = {row.cik: row.company_name for row in result.table_rows if row.cik}
    rows = [
        row.model_copy(
            update={
                "company_name": shown.get(match.cik, match.name),
                "ticker": match.ticker,
                "cik": match.cik,
            }
        )
        if not row.cik and (match := known.get(row.company_name.casefold())) is not None
        else row
        for row in result.table_rows
    ]
    return result.model_copy(update={"table_rows": rows})


@dataclass(frozen=True)
class Resolution:
    """What resolving a structured request decided, before anything is fetched.

    Either an answer that needs no fetch (a refusal, or a CLARIFY asking one
    question) with the analysis it stands for, or compiled work. ``patch`` is the
    patch as resolution applied it; a clarification holds it.
    """

    patch: SpecPatch
    result: TurnResult | None = None
    analysis_spec: AnalysisSpec | None = None
    compiled: CompiledAnalysis | None = None


def _with_company_choice(patch: SpecPatch, subject: str, ticker: str) -> SpecPatch:
    """The patch with the chosen company wherever the shared name stood."""
    named = subject.casefold()
    companies = tuple(
        ticker if company.casefold() == named else company for company in patch.add_companies
    )
    if ticker not in companies:
        companies = (*companies, ticker)
    return patch.model_copy(update={"add_companies": tuple(dict.fromkeys(companies))})


def _with_comparison(spec: AnalysisSpec, comparison: ComparisonBase) -> AnalysisSpec:
    """The analysis with its changes measured as the analyst chose."""
    operations = [op for op in spec.operations if op != "year_over_year"]
    if "across_periods" not in operations:
        operations.append("across_periods")
    if comparison == "year_over_year":
        operations.append("year_over_year")
    return spec.model_copy(update={"operations": tuple(operations)})


def company_clarification(intent: Intent, exc: AmbiguousCompanyError) -> TurnResult:
    """Ask which company a name means: "Coca-Cola" is KO, CCEP or COKE."""
    matches = exc.details.get("matches", ())
    return TurnResult(
        intent=intent,
        tool_traces=[],
        renderer=RendererKind.CLARIFY,
        candidates=tuple(str(match["ticker"]) for match in matches),
        candidate_labels=tuple(f"{match['title']} ({match['ticker']})" for match in matches),
        clarify_kind="ambiguous_company",
        clarify_subject=str(exc.details.get("query", "")),
    )


def resolve_request(
    request: StructuredRequest, current_spec: AnalysisSpec | None, runtime: Runtime
) -> Resolution:
    """Apply a structured request: patch → resolve → validate → compile.

    No facts are fetched. Resolution reads the companies' SEC filing lists only, to
    date a period window and to drop companies that file no 10-Qs.

    Only resolution decides identity (CIKs), catalog membership, and the period's
    report dates; the model's patch is never executed as given.
    """
    message = request.wording
    patch = request.patch
    intent = request.intent

    def answered(result: TurnResult, spec: AnalysisSpec | None) -> Resolution:
        return Resolution(patch=patch, result=result, analysis_spec=spec)

    invalid = INVALID_QUARTER.search(message)
    if invalid is not None:
        return answered(
            TurnResult(
                intent=intent or Intent.LOOKUP,
                tool_traces=[],
                renderer=RendererKind.REFUSE,
                message=(
                    f"There is no Q{invalid.group(1)}: a fiscal year has four quarters, "
                    "Q1 to Q4."
                ),
            ),
            current_spec,
        )
    forecast = FORECAST.search(message)
    if forecast is not None:
        return answered(_refusal(intent, forecast_message(forecast.group(0))), current_spec)
    patch = refine_patch_from_message(
        patch, message, current_spec, index=getattr(runtime.ranking, "index", None)
    )
    if request.company_choice is not None:
        # The held wording reads "Lincoln" again; the analyst already chose which.
        patch = _with_company_choice(patch, *request.company_choice)
    if patch.mode is None:
        if current_spec is None:
            patch = patch.model_copy(update={"mode": "replace"})
        else:
            return answered(
                TurnResult(
                    intent=intent or Intent.LOOKUP,
                    tool_traces=[],
                    renderer=RendererKind.CLARIFY,
                    candidates=("extend", "replace"),
                    clarify_kind="ambiguous_mode",
                ),
                current_spec,
            )
    patch, early = bind_metrics_from_message(patch, message, intent=intent)
    if early is not None:
        return answered(early, current_spec)
    emptied = emptied_by(current_spec, patch)
    if emptied is not None:
        return answered(_refusal(intent, EMPTIED_MESSAGES[emptied]), current_spec)

    draft = apply_patch(current_spec, patch)
    # A refusal names the analysis that was asked for, not a default lookup.
    asked = intent or _draft_intent(draft)
    # Drop model-supplied metrics that are not in the catalog when wording did not
    # resolve a unique phrase (plan slug may still be present on replace).
    if draft.metrics and any(m not in ALLOWED_METRICS for m in draft.metrics):
        bad = next(m for m in draft.metrics if m not in ALLOWED_METRICS)
        return answered(
            _rejection_result(
                SpecRejection(
                    code="invalid_metric",
                    message=unknown_metric_message(bad),
                    details={"term": bad, "allowed": list(ALLOWED_METRICS)},
                ),
                asked,
            ),
            None,
        )

    try:
        spec = resolve_spec(draft, ranking=runtime.ranking, identify=sec_identity(runtime))
    except UnknownIndustryError as exc:
        return answered(
            _refusal(asked, str(exc), refusal=refusal_from_error(exc)),
            None,
        )
    except AmbiguousCompanyError as exc:
        return answered(company_clarification(asked, exc), current_spec)
    if not spec.companies and spec.constituents is None and spec.metrics:
        # "what was the revenue?": naming the company next ("for Apple") completes it.
        held = current_spec if current_spec is not None else spec
        return answered(_refusal(asked, no_company_message(spec.metrics)), held)
    outcome = validate_spec(spec)
    if outcome is not None:
        return answered(_rejection_result(outcome, asked), None)
    if request.comparison is None and spec.constituents is None and (
        comparison_asked(message) == "unclear"
    ):
        # "Why did revenue drop?": against the quarter before, or a year before?
        return answered(
            TurnResult(
                intent=asked,
                tool_traces=[],
                renderer=RendererKind.CLARIFY,
                candidates=COMPARISON_CANDIDATES,
                candidate_labels=COMPARISON_LABELS,
                clarify_kind="ambiguous_comparison",
            ),
            current_spec,
        )
    if request.comparison is not None:
        spec = _with_comparison(spec, request.comparison)

    spec, annual_filers = drop_annual_filers(spec, runtime)
    if annual_filers and not spec.companies and spec.constituents is None:
        return answered(
            _rejection_result(
                SpecRejection(code="empty_spec", message=annual_filer_note(annual_filers)),
                asked,
            ),
            None,
        )

    try:
        spec = materialize_period_dates(spec, runtime)
    except (CompanyNotFoundError, *SOURCE_FAILURES) as exc:
        public = isinstance(exc, (CompanyNotFoundError, ProviderRefusal))
        return answered(
            _refusal(
                asked,
                str(exc) if public else SOURCE_UNAVAILABLE_MESSAGE,
                refusal=(
                    refusal_from_error(exc)
                    if isinstance(exc, FinancialAnalystError)
                    else None
                ),
            ),
            None,
        )
    if spec.periods.kind == "named" and spec.companies and not spec.periods.report_dates:
        future = all(
            period.year > date.today().year for period in spec.periods.named
        ) or _after_latest_filing(spec, runtime)
        return answered(
            _rejection_result(
                SpecRejection(
                    code="empty_spec",
                    message=(
                        f"No filings found for {spec.periods.label}: it has not been "
                        "reported yet."
                        if future
                        else f"No filings found for {spec.periods.label}. Periods are fiscal "
                        "years as each company names them; filings older than about "
                        "ten years may not be available."
                    ),
                ),
                asked,
            ),
            None,
        )
    if spec.periods.kind == "last_n_quarters" and not spec.periods.report_dates:
        return answered(
            _rejection_result(
                SpecRejection(
                    code="empty_spec",
                    message=(
                        "Could not determine quarterly report dates "
                        "for the requested window"
                    ),
                ),
                asked,
            ),
            None,
        )
    tasks = compile_tasks(spec)
    if not tasks:
        return answered(
            _rejection_result(
                SpecRejection(code="empty_spec", message="Analysis compiled to no tasks"),
                asked,
            ),
            None,
        )
    return Resolution(
        patch=patch,
        compiled=CompiledAnalysis(
            spec=spec,
            tasks=tasks,
            patch=patch,
            wording=message,
            prior_spec=current_spec,
            notes=request.notes,
            annual_filers=tuple(annual_filers),
            unrecorded=request.unrecorded,
        ),
    )


def merge_analysis(compiled: CompiledAnalysis, results: list[TurnResult]) -> TurnResult:
    """One answer from the task results, in task order: deterministic, no fetch."""
    spec = compiled.spec
    merged = merge_task_results(
        compiled.tasks,
        results,
        across_periods="across_periods" in spec.operations,
        sequential="year_over_year" not in spec.operations,
    )
    if len(spec.companies) == 1 and spec.constituents is None:
        # "How is SPY doing?": one reason, said once, not a row for each metric.
        merged = _not_operating_once(merged, results, spec.companies[0])
    merged = _fill_identity(merged, spec)
    message = compiled.wording
    if "order_by_metric" in spec.operations and spec.constituents is not None and spec.metrics:
        merged = _order_by_metric(merged, _ordering_metric(spec, message))
    elif "order_by_metric" in spec.operations and spec.companies and spec.metrics:
        merged = _order_companies_by_metric(merged, _ordering_metric(spec, message))
    return merged


def add_history(
    compiled: CompiledAnalysis,
    merged: TurnResult,
    runtime: Runtime,
    *,
    max_workers: int = DEFAULT_TASK_MAX_WORKERS,
) -> TurnResult:
    """An overview's trend rows and a lone fact's earlier quarters, when the answer has them."""
    spec = compiled.spec
    trend = overview_trend(spec, runtime, max_workers=max_workers)
    if trend is not None:
        merged = merged.model_copy(
            update={
                "trend_rows": trend.table_rows,
                "tool_traces": [*merged.tool_traces, *trend.tool_traces],
            }
        )
    earlier = earlier_quarters(spec, merged, runtime)
    if earlier is not None:
        merged = merged.model_copy(
            update={
                "prior_quarter_rows": earlier.prior,
                "year_earlier_rows": earlier.year_earlier,
                "tool_traces": [*merged.tool_traces, *earlier.tool_traces],
            }
        )
    return merged


def annotate_analysis(
    compiled: CompiledAnalysis, merged: TurnResult, runtime: Runtime
) -> tuple[TurnResult, AnalysisSpec]:
    """The answer's notes, and the resolved analysis the thread keeps."""
    spec = compiled.spec
    patch = compiled.patch
    # Planner notes first: a corrected company name explains the whole answer.
    notes = [
        *([annual_filer_note(list(compiled.annual_filers))] if compiled.annual_filers else []),
        *already_present_notes(patch, compiled.prior_spec, spec),
        *period_notes(compiled.wording, spec),
        *short_ranking_notes(spec),
        *capped_ranking_notes(patch),
    ]
    banners = list(dict.fromkeys([*compiled.notes, *merged.banners, *notes]))
    snapshot_banner_index = merged.snapshot_banner_index
    if merged.snapshot_as_of is not None:
        before_snapshot = merged.banners[: merged.snapshot_banner_index]
        snapshot_banner_index = len(dict.fromkeys([*compiled.notes, *before_snapshot]))
    if banners != merged.banners or snapshot_banner_index != merged.snapshot_banner_index:
        merged = merged.model_copy(
            update={
                "banners": banners,
                "snapshot_banner_index": snapshot_banner_index,
            }
        )
    return merged, _with_market_date(spec, runtime)


EMPTIED_MESSAGES = {
    "companies": (
        "That would remove the only company in this analysis. Name another to look at "
        "instead, for example “what about Microsoft?”, or start over."
    ),
    "metrics": (
        "That would leave no metric to show. Name one to show instead, for example "
        "“just net income”, or start over."
    ),
}


def forecast_message(asked: str) -> str:
    return (
        f"Filings report quarters that have already happened, so I can't forecast "
        f"“{asked}”. Try “last 4 quarters” to see the trend so far."
    )


def no_company_message(metrics: tuple[str, ...]) -> str:
    from financial_analyst_agent.presentation import format_field_name

    label = in_sentence(format_field_name(metrics[0]))
    return (
        f"I couldn't tell which company you mean. Name one or its ticker, for example "
        f"“Apple {label}”, or rank an industry, such as “top 5 banks by {label}”."
    )


def _refusal(
    intent: Intent | None, message: str, *, refusal: Refusal | None = None
) -> TurnResult:
    return TurnResult(
        intent=intent or Intent.LOOKUP,
        tool_traces=[],
        renderer=RendererKind.REFUSE,
        message=message,
        refusal=refusal,
    )


def _not_operating_once(
    merged: TurnResult, results: list[TurnResult], company: ResolvedCompany
) -> TurnResult:
    """One refusal where every cell of one company failed for the same reason.

    "How is SPY doing?" is a fund, not five "Not an operating company" rows.
    """
    rows = merged.table_rows
    reasons = {row.reason for row in rows}
    if not rows or any(row.value is not None for row in rows) or len(reasons) != 1:
        return merged
    said = next(
        (
            result.message
            for result in results
            if result.renderer is RendererKind.REFUSE and result.message
        ),
        None,
    )
    if said is None and reasons == {NOT_OPERATING_COMPANY}:
        name = short_name(company.name) or company.query
        said = (
            f"{name} is not an operating company (it is a fund, business development "
            "company or similar listing), so its 10-Q figures are outside what this "
            "analyst covers."
        )
    if said is None:
        return merged
    return TurnResult(
        intent=merged.intent,
        tool_traces=merged.tool_traces,
        renderer=RendererKind.REFUSE,
        message=said,
        refusal=next(
            (result.refusal for result in results if result.refusal is not None),
            None,
        ),
    )


def _ordering_metric(spec: AnalysisSpec, message: str) -> str:
    """The metric to order by: named here, chosen by "sort by", else the first."""
    named = [metric for metric in unique_metrics_from_phrase(message) if metric in spec.metrics]
    if named:
        return named[0]
    if spec.order_by in spec.metrics:
        return str(spec.order_by)
    return spec.metrics[0]


def _with_market_date(spec: AnalysisSpec, runtime: Runtime) -> AnalysisSpec:
    """Date an analysis of snapshot figures only (market cap, price) by its snapshot."""
    market_only = all(metric in SNAPSHOT_METRICS for metric in spec.metrics)
    as_of = None
    if market_only and (spec.metrics or spec.constituents is not None):
        reader = getattr(runtime.ranking, "snapshot_as_of", None)
        try:
            as_of = date.fromisoformat(str(reader())[:10]) if callable(reader) else None
        except ValueError:
            as_of = None
    return spec if spec.as_of == as_of else spec.model_copy(update={"as_of": as_of})


def _after_latest_filing(spec: AnalysisSpec, runtime: Runtime) -> bool:
    """Whether every named period ends after the first company's newest filed quarter."""
    lister = getattr(runtime.facts, "fiscal_periods", None)
    if lister is None or not spec.companies:
        return False
    try:
        listed = tuple(lister(spec.companies[0].handle))
    except SessionQuotaError:
        raise
    except Exception:
        return False
    if not listed:
        return False
    latest = max(listed, key=lambda period: period.end)
    for named in spec.periods.named:
        if named.calendar:
            last = calendar_quarter(latest.end)
        elif latest.fiscal_year is None or latest.quarter is None:
            return False
        else:
            last = (latest.fiscal_year, latest.quarter)
        if (named.year, named.quarter or 1) <= last:
            return False
    return True


# One company's overview carries a few quarters of these beside its table.
TREND_METRICS: tuple[str, ...] = ("revenue", "net_margin")
TREND_QUARTERS = 5


def overview_trend(
    spec: AnalysisSpec,
    runtime: Runtime,
    *,
    max_workers: int = DEFAULT_TASK_MAX_WORKERS,
) -> TurnResult | None:
    """The last few quarters of revenue and net margin for "How is Nvidia doing?".

    Only the overview of one company at its latest quarter gets them: the small
    trend charts above its table. The rows read the same filings the table does;
    a lookup that fails or runs out of the thread's allowance leaves the charts
    out and the answer as it was.
    """
    if (
        len(spec.companies) != 1
        or spec.constituents is not None
        or spec.operations
        or spec.periods.kind != "latest_quarter"
        or spec.metrics != OVERVIEW_METRICS
    ):
        return None
    window = spec.model_copy(
        update={
            "metrics": TREND_METRICS,
            "periods": PeriodSelection(kind="last_n_quarters", count=TREND_QUARTERS),
        }
    )
    try:
        window = materialize_period_dates(window, runtime)
        tasks = compile_tasks(window)
        results = dispatch_compiled_tasks(tasks, runtime, max_workers=max_workers)
    except (CompanyNotFoundError, SessionQuotaError, *SOURCE_FAILURES):
        return None
    if not tasks:
        return None
    merged = merge_task_results(tasks, results, across_periods=False)
    levels = [row for row in merged.table_rows if row.comparison is None and row.value is not None]
    return merged.model_copy(update={"table_rows": levels})


@dataclass(frozen=True)
class EarlierQuarters:
    """The quarters a lone fact's change chips are measured against."""

    prior: list[TableRow]
    year_earlier: list[TableRow]
    tool_traces: list[ToolTrace]


def earlier_quarters(
    spec: AnalysisSpec,
    result: TurnResult,
    runtime: Runtime,
) -> EarlierQuarters | None:
    """The quarter before a lone latest-quarter fact, and the quarter a year earlier.

    Only a fact card gets them: one company, one filed metric, its latest quarter.
    The quarter before is for the quarter-over-quarter chip. The year-over-year
    chip reads the comparative the fact's own filing reports; when there is none
    (a 10-Q's balance sheet compares with the fiscal year-end, not a year
    earlier), the quarter a year earlier as first filed is fetched instead
    (ADR 0009). Both come from the company's facts and filing list that the fact
    itself was read from, so neither costs another SEC download while those are
    cached. A lookup that fails leaves its chip out and the answer as it was.
    """
    rows = result.table_rows
    if (
        len(spec.companies) != 1
        or spec.constituents is not None
        or spec.operations
        or spec.periods.kind != "latest_quarter"
        or len(spec.metrics) != 1
        or spec.metrics[0] in (*SNAPSHOT_METRICS, *TRAILING_YEAR_FORMULAS)
        or len(rows) != 1
        or rows[0].value is None
        or rows[0].end_date is None
    ):
        return None
    current = rows[0]
    end = current.end_date
    assert end is not None
    year_target = one_year_earlier(end) if current.year_earlier is None else None

    def a_year_before(day: date) -> bool:
        return year_target is not None and abs(day - year_target) <= FISCAL_WEEK_TOLERANCE

    # Four quarters back reach a year earlier; the quarter before needs one.
    count = 5 if year_target is not None else 2
    window = spec.model_copy(
        update={"periods": PeriodSelection(kind="last_n_quarters", count=count)}
    )
    try:
        window = materialize_period_dates(window, runtime)
        dates = window.periods.report_dates[1:]
        wanted = [day for day in dates[:1] if adjacent_quarters(end, day)]
        wanted += [day for day in dates if a_year_before(day)][:1]
        if not wanted:
            return None
        key = spec.companies[0].key
        window = window.model_copy(
            update={
                "periods": window.periods.model_copy(
                    update={
                        "count": len(wanted),
                        "report_dates": tuple(wanted),
                        "company_report_dates": ((key, tuple(wanted)),),
                    }
                )
            }
        )
        tasks = compile_tasks(window)
        results = dispatch_compiled_tasks(tasks, runtime, max_workers=1)
    except (CompanyNotFoundError, SessionQuotaError, *SOURCE_FAILURES):
        return None
    if not tasks:
        return None
    merged = merge_task_results(tasks, results, across_periods=False)
    levels = [
        row
        for row in merged.table_rows
        if row.comparison is None
        and row.value is not None
        and row.end_date is not None
        and not split_between(current, row)
    ]
    prior = [row for row in levels if row.end_date and adjacent_quarters(end, row.end_date)]
    year = [row for row in levels if row.end_date and a_year_before(row.end_date)]
    if len(prior) != 1 and len(year) != 1:
        return None
    return EarlierQuarters(
        prior=prior if len(prior) == 1 else [],
        year_earlier=year if len(year) == 1 else [],
        tool_traces=merged.tool_traces,
    )

