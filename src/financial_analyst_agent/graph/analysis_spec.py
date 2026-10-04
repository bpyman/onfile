"""Analysis spec, patch application, validation, and task compilation.

Internal seams for the stateful analysis graph. Callers outside this package
should not depend on these helpers; the conversation seam owns the public API.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from financial_analyst_agent.contracts import ALLOWED_METRICS, unknown_metric_message
from financial_analyst_agent.domain.errors import CompanyNotFoundError
from financial_analyst_agent.services.filing_selector import FISCAL_WEEK_TOLERANCE


class NamedPeriodSpec(BaseModel):
    """A period the analyst named: "Q3 2024" (fiscal), "fiscal 2025", "calendar Q1 2026"."""

    model_config = ConfigDict(frozen=True)

    year: int
    quarter: int | None = Field(default=None, ge=1, le=4)
    calendar: bool = False

    def label(self) -> str:
        if self.calendar:
            return f"Calendar Q{self.quarter} {self.year}" if self.quarter else f"{self.year}"
        return f"Q{self.quarter} FY{self.year}" if self.quarter else f"Fiscal {self.year}"


class PeriodSelection(BaseModel):
    """Period window for an analysis.

    ``latest_quarter`` keeps one-shot behaviour. ``last_n_quarters`` re-runs
    metrics across a window; ``report_dates`` (newest first) are concrete bounds
    when known, otherwise execution discovers them from the facts adapter.
    ``company_report_dates`` holds another company's own quarter ends, keyed by
    its ``ResolvedCompany.key``, for companies whose fiscal calendar differs from the
    first company's (Walmart's April quarter beside Microsoft's March one).
    ``named`` periods are fiscal quarters or years the analyst named; each
    company's own filings say which quarter ends they cover (ADR 0007).
    """

    kind: Literal["latest_quarter", "last_n_quarters", "named"] = "latest_quarter"
    count: int | None = None
    report_dates: tuple[date, ...] = ()
    company_report_dates: tuple[tuple[str, tuple[date, ...]], ...] = ()
    named: tuple[NamedPeriodSpec, ...] = ()
    # The quarters the analyst asked for, when the filings hold fewer than that.
    asked: int | None = None

    @property
    def label(self) -> str:
        return ", ".join(period.label() for period in self.named)

    @model_validator(mode="after")
    def _check_window(self) -> PeriodSelection:
        if self.kind == "latest_quarter":
            return self
        if self.kind == "named":
            if not self.named:
                raise ValueError("named periods require at least one period")
            return self
        if self.count is None or self.count < 1:
            raise ValueError("last_n_quarters requires count >= 1")
        if self.report_dates and len(self.report_dates) != self.count:
            raise ValueError("report_dates length must match count")
        return self


class ResolvedCompany(BaseModel):
    """A company the analyst named, pinned to its SEC identity.

    ``cik`` is empty only for a name neither the snapshot nor SEC's ticker map
    resolves; its cells then say the company was not found.
    """

    cik: str
    name: str
    ticker: str
    # The analyst's own word for it ("Google"): what follow-ups match against.
    query: str

    @property
    def key(self) -> str:
        """What per-company state is keyed on: the CIK, or the name SEC does not know."""
        return self.cik or self.query.casefold()

    @property
    def handle(self) -> str:
        """What the providers are asked for: the CIK, or the name SEC does not know."""
        return self.cik or self.query


class RankedRequest(BaseModel):
    """A ranking asked for, before its members are read: the top ``limit`` of ``industry``."""

    model_config = ConfigDict(frozen=True)

    industry: str
    limit: int

    @model_validator(mode="before")
    @classmethod
    def _read_stored_pair(cls, value: Any) -> Any:
        # A clarification held before rankings had a type stores ("banks", 5).
        if isinstance(value, (list, tuple)) and len(value) == 2:
            return {"industry": value[0], "limit": value[1]}
        return value


class RankedSet(BaseModel):
    industry: str
    limit: int
    members: tuple[ResolvedCompany, ...] = ()


class AnalysisSpec(BaseModel):
    """Resolved quantitative statement of the analyst's current question."""

    companies: tuple[ResolvedCompany, ...] = ()
    constituents: RankedSet | None = None
    metrics: tuple[str, ...] = ()
    periods: PeriodSelection = Field(default_factory=PeriodSelection)
    operations: tuple[str, ...] = ()
    presentation: Literal["table"] = "table"
    # Companies a swap ("what about AMD?") or a new question replaced, so "which
    # one is more profitable?" and "compare them" reach the ones just looked at.
    earlier_companies: tuple[str, ...] = ()
    # Every company this thread has looked at, first named first ("compare with
    # the first one").
    seen_companies: tuple[str, ...] = ()
    # The metric "sort by …" ordered the rows by; None orders by the first metric.
    order_by: str | None = None
    # The snapshot date a market-data-only analysis reads (market cap, price).
    as_of: date | None = None


class SpecPatch(BaseModel):
    """Model-proposed edit. Deterministic code applies and resolves it.

    ``mode`` is ``None`` when extend-versus-replace scope is ambiguous: the
    conversation seam clarifies rather than guessing (ticket 14).
    """

    mode: Literal["extend", "replace"] | None = None
    add_companies: tuple[str, ...] = ()
    remove_companies: tuple[str, ...] = ()
    add_metrics: tuple[str, ...] = ()
    remove_metrics: tuple[str, ...] = ()
    set_periods: PeriodSelection | None = None
    add_operations: tuple[str, ...] = ()
    remove_operations: tuple[str, ...] = ()
    set_presentation: Literal["table"] | None = None
    ranked_request: RankedRequest | None = None
    set_order_by: str | None = None


class SpecDraft(BaseModel):
    """Unresolved patch outcome: company queries and metric slugs."""

    company_queries: tuple[str, ...] = ()
    metrics: tuple[str, ...] = ()
    periods: PeriodSelection = Field(default_factory=PeriodSelection)
    operations: tuple[str, ...] = ()
    presentation: Literal["table"] = "table"
    ranked_request: RankedRequest | None = None
    earlier_companies: tuple[str, ...] = ()
    seen_companies: tuple[str, ...] = ()
    order_by: str | None = None


# A ranking lists at most this many companies: each one with a filed metric
# is a lookup, and "top 1000" once took eight minutes of SEC requests.
MAX_RANKED_COMPANIES = 25
# "Last N quarters" reads at most ten years: more than any filing history here.
MAX_QUARTERS_ASKED = 40
# Companies a thread remembers having looked at.
_MAX_SEEN_COMPANIES = 12

SUPPORTED_OPERATIONS: frozenset[str] = frozenset(
    {"across_companies", "across_periods", "rank", "order_by_metric", "year_over_year"}
)


class SpecRejection(BaseModel):
    code: Literal["invalid_metric", "empty_spec", "unsupported_combination"]
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class CompiledTask(BaseModel):
    kind: Literal["lookup", "compare", "rank", "rank_and_lookup"]
    # The companies' ``ResolvedCompany.handle``: their CIKs, or a name SEC does not know.
    issuers: tuple[str, ...] = ()
    metric: str | None = None
    industry: str | None = None
    limit: int | None = None
    report_date: date | None = None


def _company_matches_token(company: ResolvedCompany, token: str) -> bool:
    needle = token.casefold()
    if needle in {
        company.query.casefold(),
        company.name.casefold(),
        company.ticker.casefold(),
        company.cik.casefold(),
    }:
        return True
    # "remove JPMorgan" names "JPMorgan Chase & Co." by the start of its name.
    words = " ".join(re.findall(r"[a-z0-9&]+", needle))
    name = " ".join(re.findall(r"[a-z0-9&]+", company.name.casefold()))
    return bool(words) and re.match(rf"{re.escape(words)}\b", name) is not None


def _seen(*groups: tuple[str, ...]) -> tuple[str, ...]:
    seen = tuple(dict.fromkeys(company for group in groups for company in group))
    return seen[:_MAX_SEEN_COMPANIES]


def apply_patch(current: AnalysisSpec | None, patch: SpecPatch) -> SpecDraft:
    """Apply a proposed patch to the current spec (or empty) → unresolved draft."""
    if patch.mode is None and current is not None:
        raise ValueError("ambiguous patch mode must be clarified before apply_patch")
    current_queries = tuple(company.query for company in current.companies) if current else ()
    seen = _seen(current.seen_companies if current else (), current_queries)
    if patch.mode == "replace" or current is None:
        companies = list(patch.add_companies)
        metrics = list(patch.add_metrics)
        periods = patch.set_periods or PeriodSelection()
        operations = list(patch.add_operations)
        presentation = patch.set_presentation or "table"
        ranked = patch.ranked_request
        order_by = patch.set_order_by
        # "Apple revenue", then "Microsoft revenue": "compare them" means both.
        earlier: tuple[str, ...] = (
            current_queries
            if companies and not {query.casefold() for query in current_queries}
            & {query.casefold() for query in companies}
            else ()
        )
    elif current.constituents is not None and patch.ranked_request is None and (
        patch.add_companies or patch.remove_companies
    ):
        # "add Apple" to the top 5 banks: the ranking becomes those companies.
        members = [
            company
            for company in current.constituents.members
            if not any(_company_matches_token(company, token) for token in patch.remove_companies)
        ]
        companies = [company.query for company in members]
        companies.extend(token for token in patch.add_companies if token not in companies)
        metrics = [m for m in current.metrics if m not in patch.remove_metrics]
        metrics.extend(m for m in patch.add_metrics if m not in metrics)
        # A plain ranking shows market cap; the companies keep showing it.
        metrics = metrics or ["market_cap"]
        periods = patch.set_periods or current.periods
        dropped = ("rank", *patch.remove_operations)
        operations = [op for op in current.operations if op not in dropped]
        operations.extend(op for op in patch.add_operations if op not in operations)
        presentation = patch.set_presentation or current.presentation
        ranked = None
        order_by = patch.set_order_by or current.order_by
        earlier = ()
    else:
        kept = [
            company
            for company in current.companies
            if not any(
                _company_matches_token(company, token) for token in patch.remove_companies
            )
        ]
        companies = [company.query for company in kept]
        if not patch.add_companies and not patch.remove_companies:
            earlier = current.earlier_companies
        elif current.companies and not kept and patch.add_companies:
            earlier = tuple(company.query for company in current.companies)
        else:
            earlier = ()
        for token in patch.add_companies:
            if token not in companies:
                companies.append(token)
        metrics = list(current.metrics)
        for slug in patch.remove_metrics:
            metrics = [m for m in metrics if m != slug]
        for slug in patch.add_metrics:
            if slug not in metrics:
                metrics.append(slug)
        periods = patch.set_periods or current.periods
        operations = list(current.operations)
        for op in patch.remove_operations:
            operations = [o for o in operations if o != op]
        for op in patch.add_operations:
            if op not in operations:
                operations.append(op)
        presentation = patch.set_presentation or current.presentation
        if patch.ranked_request is not None:
            ranked = patch.ranked_request
        elif current.constituents is not None:
            ranked = RankedRequest(
                industry=current.constituents.industry, limit=current.constituents.limit
            )
        else:
            ranked = None
        order_by = patch.set_order_by or current.order_by

    if ranked is not None:
        # Ranked constituents come from the ranking port; ignore model-typed lists.
        companies = []

    return SpecDraft(
        company_queries=tuple(companies),
        metrics=tuple(metrics),
        periods=periods,
        operations=tuple(operations),
        presentation=presentation,
        ranked_request=ranked,
        earlier_companies=() if ranked is not None else earlier,
        seen_companies=_seen(seen, tuple(companies)),
        order_by=order_by if order_by in metrics else None,
    )


def emptied_by(
    current: AnalysisSpec | None, patch: SpecPatch
) -> Literal["companies", "metrics"] | None:
    """What an edit would leave the analysis without: "remove Apple" when Apple is all."""
    if current is None or patch.mode != "extend" or patch.ranked_request is not None:
        return None
    if current.constituents is None and current.companies and not patch.add_companies:
        kept = [
            company
            for company in current.companies
            if not any(_company_matches_token(company, token) for token in patch.remove_companies)
        ]
        if not kept:
            return "companies"
    # A ranking without its metrics is still a ranking, by market cap.
    if (
        current.constituents is None
        and current.metrics
        and not patch.add_metrics
        and set(current.metrics) <= set(patch.remove_metrics)
    ):
        return "metrics"
    return None


def resolve_spec(
    draft: SpecDraft,
    *,
    ranking: Any | None = None,
    identify: Callable[[str], ResolvedCompany | None] | None = None,
) -> AnalysisSpec:
    """Resolve company identity and ranked constituents. Metrics stay catalog slugs."""
    companies: list[ResolvedCompany] = []
    constituents: RankedSet | None = None

    if draft.ranked_request is not None:
        if ranking is None:
            raise RuntimeError("ranked analysis requires a ranking adapter")
        industry = draft.ranked_request.industry
        limit = min(draft.ranked_request.limit, MAX_RANKED_COMPANIES)
        table = ranking.rank_companies(industry, limit)
        members = tuple(
            ResolvedCompany(
                cik=member.cik,
                name=member.name,
                ticker=member.ticker,
                query=member.ticker,
            )
            for member in table.companies
        )
        constituents = RankedSet(industry=industry, limit=limit, members=members)
    else:
        seen: set[str] = set()
        for query in draft.company_queries:
            company = _resolve_company(query, ranking=ranking, identify=identify)
            if company.cik and company.cik in seen:
                # "add Apple" to an analysis that already has AAPL.
                continue
            seen.add(company.cik)
            companies.append(company)

    operations = list(draft.operations)
    if len(companies) >= 2 and "across_companies" not in operations:
        operations.append("across_companies")
    if constituents is not None and "rank" not in operations:
        operations.append("rank")
    if "year_over_year" in operations and "across_periods" not in operations:
        # A change is drawn from the quarters' rows; year over year without them,
        # as a model's follow-up may ask, would show no change at all.
        operations.append("across_periods")

    return AnalysisSpec(
        companies=tuple(companies),
        constituents=constituents,
        metrics=draft.metrics,
        periods=draft.periods,
        operations=tuple(operations),
        presentation=draft.presentation,
        earlier_companies=draft.earlier_companies,
        seen_companies=draft.seen_companies,
        order_by=draft.order_by,
    )


def _resolve_company(
    query: str,
    *,
    ranking: Any | None,
    identify: Callable[[str], ResolvedCompany | None] | None = None,
) -> ResolvedCompany:
    """The snapshot's company for ``query``, else SEC's (``identify``), else the bare name.

    An ambiguous snapshot name is raised: the analyst picks the company.
    """
    if ranking is not None:
        try:
            member = ranking.lookup_member(query)
            return ResolvedCompany(
                cik=member.cik,
                name=member.name,
                ticker=member.ticker,
                query=query,
            )
        except CompanyNotFoundError:
            pass
    if identify is not None:
        # A company the snapshot leaves out (Tesla on the recorded demo): SEC's.
        found = identify(query)
        if found is not None:
            return found
    return ResolvedCompany(cik="", name=query, ticker="", query=query)


def validate_spec(spec: AnalysisSpec) -> SpecRejection | None:
    """Validate a resolved spec against closed catalogs. No provider I/O."""
    for metric in spec.metrics:
        if metric not in ALLOWED_METRICS:
            return SpecRejection(
                code="invalid_metric",
                message=unknown_metric_message(metric),
            )
    for operation in spec.operations:
        if operation not in SUPPORTED_OPERATIONS:
            return SpecRejection(
                code="unsupported_combination",
                message=(
                    f"Unsupported operation {operation!r}. "
                    f"Allowed: {', '.join(sorted(SUPPORTED_OPERATIONS))}"
                ),
            )
        if operation == "across_periods" and (
            spec.periods.kind not in ("last_n_quarters", "named")
            or (spec.periods.kind == "last_n_quarters" and (spec.periods.count or 0) < 2)
        ):
            return SpecRejection(
                code="unsupported_combination",
                message=(
                    "Operation 'across_periods' requires a last_n_quarters "
                    "period window with count >= 2"
                ),
            )
    has_companies = bool(spec.companies)
    has_constituents = spec.constituents is not None
    if len(spec.companies) > MAX_RANKED_COMPANIES:
        # Each company is its own SEC lookup; a list is bounded as a ranking is.
        return SpecRejection(
            code="unsupported_combination",
            message=(
                f"That names {len(spec.companies)} companies; I compare at most "
                f"{MAX_RANKED_COMPANIES} at once. Try fewer, or ask for a ranking "
                "such as “top 10 banks by revenue”."
            ),
        )
    if not has_companies and not has_constituents:
        return SpecRejection(
            code="empty_spec",
            message="Analysis has no companies or ranked constituents",
            details={"missing": "companies"},
        )
    if has_constituents and not spec.metrics:
        return None
    if not spec.metrics and has_companies:
        return SpecRejection(
            code="empty_spec",
            message="Analysis has no metrics",
            details={"missing": "metrics"},
        )
    return None


def _base_tasks(spec: AnalysisSpec) -> tuple[CompiledTask, ...]:
    if spec.constituents is not None:
        if not spec.metrics:
            return (
                CompiledTask(
                    kind="rank",
                    industry=spec.constituents.industry,
                    limit=spec.constituents.limit,
                ),
            )
        return tuple(
            CompiledTask(
                kind="rank_and_lookup",
                industry=spec.constituents.industry,
                limit=spec.constituents.limit,
                metric=metric,
            )
            for metric in spec.metrics
        )

    issuers = tuple(company.handle for company in spec.companies)
    if not issuers or not spec.metrics:
        return ()
    kind: Literal["lookup", "compare"] = "lookup" if len(issuers) == 1 else "compare"
    return tuple(
        CompiledTask(kind=kind, issuers=issuers, metric=metric) for metric in spec.metrics
    )


def _quarter_phase(day: date) -> int:
    """Month of the quarter grid a period end sits on (0, 1 or 2).

    A 52/53-week quarter ends up to a week either side of a month end, so a
    date in a month's first half counts as the previous month's end.
    """
    month = day.month if day.day >= 15 else day.month - 1
    return month % 3


def _same_grid(dates: tuple[date, ...], reference: tuple[date, ...]) -> bool:
    """Whether two quarter-end lists name the same quarters, give or take a week.

    Apple's March 28 and Microsoft's March 31 are one quarter. Costco's May 10
    and Walmart's April 30 sit in the same month of the quarter grid but are
    different quarters: asking Walmart for May 10 finds no filing.
    """
    if _quarter_phase(dates[0]) != _quarter_phase(reference[0]):
        return False
    return any(
        abs(own - shared) <= FISCAL_WEEK_TOLERANCE for own in dates for shared in reference
    )


def calendar_groups(spec: AnalysisSpec) -> list[tuple[tuple[str, ...], tuple[date, ...]]]:
    """Named companies grouped by the quarter ends their window uses, in spec order.

    A company with no dates of its own, or whose quarters end on the same
    calendar grid as the first company's (Apple's March 28 beside Microsoft's
    March 31), shares the window's ``report_dates`` so rows cover the same
    periods; a company on another grid (Nvidia's April quarter) keeps its own.
    """
    reference = spec.periods.report_dates
    own = dict(spec.periods.company_report_dates)
    named = spec.periods.kind == "named"
    groups: dict[tuple[date, ...], list[str]] = {}
    for company in spec.companies:
        dates = own.get(company.key, reference)
        if named:
            # "Q3 FY2024" is each company's own third quarter, wherever it ends.
            if not dates:
                continue
        elif not dates or not reference or _same_grid(dates, reference):
            dates = reference
        groups.setdefault(dates, []).append(company.handle)
    return [(tuple(issuers), dates) for dates, issuers in groups.items()]


def compile_tasks(spec: AnalysisSpec) -> tuple[CompiledTask, ...]:
    """Compile a resolved spec into typed tasks without executing providers.

    Each metric becomes an independent task so multi-metric analyses compose
    without a special-cased multi-metric workflow. A last_n_quarters window with
    concrete report_dates fans out one task per period.
    """
    base = _base_tasks(spec)
    if (
        spec.periods.kind not in ("last_n_quarters", "named")
        or not spec.periods.report_dates
        or not base
    ):
        return base
    # Rank workflows are snapshot-dated, not filing-period windows.
    expandable = tuple(
        task for task in base if task.kind in {"lookup", "compare"}
    )
    if not expandable:
        return base
    groups = calendar_groups(spec)
    # A named period leaves out a company with no filing for it; asking that
    # company for another company's date would answer with its own other quarter.
    named = spec.periods.kind == "named"
    if named or len(groups) > 1 or (groups and groups[0][1] != spec.periods.report_dates):
        # Each calendar asks for its own quarter ends; one shared date would
        # miss every quarter of a company whose fiscal quarters end elsewhere.
        longest = max(len(dates) for _, dates in groups)
        return tuple(
            CompiledTask(
                kind="compare" if len(spec.companies) > 1 else task.kind,
                issuers=issuers,
                metric=task.metric,
                report_date=dates[index],
            )
            for index in range(longest)
            for task in expandable
            for issuers, dates in groups
            if index < len(dates)
        )
    return tuple(
        task.model_copy(update={"report_date": report_date})
        for report_date in spec.periods.report_dates
        for task in expandable
    )
