"""Stable application contracts: ports, Runtime, result models, enums, metric constants.

Workflow implementations live in ``turn``; a graph package can import this module
without loading those workflows.
"""

from collections.abc import Collection
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Literal, Protocol, Self

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from financial_analyst_agent.domain.models import FinancialFact
from financial_analyst_agent.domain.serialization import DecimalStr
from financial_analyst_agent.services.metric_catalog import METRIC_DISPLAY

if TYPE_CHECKING:
    from financial_analyst_agent.graph.analysis_spec import SpecPatch
    from financial_analyst_agent.ranking import RankTable
    from financial_analyst_agent.services.fiscal_periods import FiscalPeriod
    from financial_analyst_agent.universe import UniverseCompany


class Intent(StrEnum):
    LOOKUP = "lookup"
    COMPARE = "compare"
    RANK = "rank"
    RANK_AND_LOOKUP = "rank_and_lookup"
    EXPLAIN = "explain"
    NEWS_AND_EXPLAIN = "news_and_explain"
    EXPLORATORY_RESEARCH = "exploratory_research"
    FILING_CHANGE = "filing_change"


class RendererKind(StrEnum):
    TABLE = "table"
    ESSAY = "essay"
    REFUSE = "refuse"
    CLARIFY = "clarify"


QUALITATIVE_INTENTS: tuple[Intent, ...] = (
    Intent.EXPLAIN,
    Intent.NEWS_AND_EXPLAIN,
    Intent.EXPLORATORY_RESEARCH,
)
STRUCTURED_INTENTS: tuple[Intent, ...] = (
    Intent.LOOKUP,
    Intent.COMPARE,
    Intent.RANK,
    Intent.RANK_AND_LOOKUP,
)


REPORTED_METRICS: tuple[str, ...] = (
    "revenue",
    "cost_of_revenue",
    "gross_profit",
    "operating_expenses",
    "operating_income",
    "net_income",
    "research_and_development",
    "selling_general_and_administrative",
    "interest_expense",
    "income_tax_expense",
    "pretax_income",
    "eps_diluted",
    "eps_basic",
    "operating_cash_flow",
    "capital_expenditure",
    "depreciation_amortization",
    "dividends_paid",
    "dividends_per_share",
    "cash",
    "shareholders_equity",
    # A bank's; other companies report none (missing_fact).
    "net_interest_income",
    "noninterest_income",
    # One amount over the four quarters to a report date (ADR 0008).
    "net_income_ttm",
)
FORMULA_METRICS: tuple[str, ...] = (
    "gross_margin",
    "operating_margin",
    "net_margin",
    "rd_to_sales",
    "sga_ratio",
    "effective_tax_rate",
    "interest_coverage",
    "free_cash_flow",
    "ebitda",
    "return_on_equity",
    "pe_ratio",
)
SNAPSHOT_METRICS: tuple[str, ...] = ("market_cap", "price")
ALLOWED_METRICS: tuple[str, ...] = REPORTED_METRICS + FORMULA_METRICS + SNAPSHOT_METRICS
# A metric's kind of value is its catalog entry's (services.metric_catalog).
PERCENT_FORMULAS: tuple[str, ...] = tuple(
    metric for metric in FORMULA_METRICS if METRIC_DISPLAY[metric].value_kind == "percent"
)
# Formulas whose denominator is revenue.
MARGIN_FORMULAS: tuple[str, ...] = (
    "gross_margin",
    "operating_margin",
    "net_margin",
    "rd_to_sales",
    "sga_ratio",
)
FORMULA_COMPONENTS: dict[str, tuple[str, str]] = {
    "gross_margin": ("gross_profit", "revenue"),
    "operating_margin": ("operating_income", "revenue"),
    "net_margin": ("net_income", "revenue"),
    "rd_to_sales": ("research_and_development", "revenue"),
    "sga_ratio": ("selling_general_and_administrative", "revenue"),
    "effective_tax_rate": ("income_tax_expense", "pretax_income"),
    "interest_coverage": ("operating_income", "interest_expense"),
    "free_cash_flow": ("operating_cash_flow", "capital_expenditure"),
    "ebitda": ("operating_income", "depreciation_amortization"),
    "return_on_equity": ("net_income_ttm", "shareholders_equity"),
    "pe_ratio": ("market_cap", "net_income_ttm"),
}
# Formulas that subtract their second component instead of dividing by it.
DIFFERENCE_FORMULAS: tuple[str, ...] = ("free_cash_flow",)
# Formulas that add their components.
SUM_FORMULAS: tuple[str, ...] = ("ebitda",)
# Formulas whose value is a multiple ("12.4x"), not a percent or an amount.
MULTIPLE_FORMULAS: tuple[str, ...] = tuple(
    metric for metric in FORMULA_METRICS if METRIC_DISPLAY[metric].value_kind == "multiple"
)
# Formulas over the trailing year rather than one quarter (ADR 0008).
TRAILING_YEAR_FORMULAS: tuple[str, ...] = ("return_on_equity", "pe_ratio")
# Every figure over a trailing year, the amount itself and the formulas over it.
TRAILING_YEAR_FIGURES: tuple[str, ...] = ("net_income_ttm", *TRAILING_YEAR_FORMULAS)
# Formulas with a snapshot component: computed for the latest period only,
# since the snapshot holds today's market cap, not a past one (ADR 0008).
MARKET_FORMULAS: tuple[str, ...] = ("pe_ratio",)
# Balance-sheet amounts: one value at the quarter's end date (ADR 0008).
INSTANT_METRICS: tuple[str, ...] = ("cash", "shareholders_equity")
PER_SHARE_METRICS: tuple[str, ...] = tuple(
    metric for metric in ALLOWED_METRICS if METRIC_DISPLAY[metric].value_kind == "per_share"
)

# A ranked list's length when the question names none.
DEFAULT_RANK_LIMIT = 10
SNAPSHOT_BANNER_PREFIX = "Universe snapshot as of "


def unknown_metric_message(term: str) -> str:
    return f"Unknown metric {term!r}. Allowed: {', '.join(ALLOWED_METRICS)}"

PERIOD_MISMATCH = "period_mismatch"
MISSING_FACT = "missing_fact"
# A named company that fails the membership rule: a fund, BDC, note, preferred.
NOT_OPERATING_COMPANY = "not_operating_company"
# The source (EDGAR) failed for this cell; the fact may well exist.
SOURCE_UNAVAILABLE = "source_unavailable"
# The lookup itself failed (a fault of ours, not the filing's or EDGAR's).
LOOKUP_FAILED = "lookup_failed"
# A named company that neither the snapshot nor SEC's ticker list knows.
COMPANY_NOT_FOUND = "company_not_found"
# A company SEC knows that the market snapshot does not hold: no market cap or price.
NOT_IN_SNAPSHOT = "not_in_snapshot"
AMBIGUOUS_CONCEPT = "ambiguous_concept"
ZERO_DENOMINATOR = "zero_denominator"
# A per-share figure for a quarter the filings do not report on its own
# (fiscal Q4 EPS lives only in the annual total; ADR 0007).
NOT_REPORTED_FOR_QUARTER = "not_reported_for_quarter"
# A quarter with no dividend declared, after one earlier in the fiscal year.
NO_DIVIDEND_THIS_QUARTER = "no_dividend_this_quarter"
# A ratio that means nothing for these inputs: a P/E on a trailing-year loss.
NOT_MEANINGFUL = "not_meaningful"
# Ratios over a negative denominator, which would mislead: McDonald's
# negative equity gives a return of -859%, a tax on a pretax loss a negative rate.
NEGATIVE_EQUITY = "negative_equity"
NEGATIVE_REVENUE = "negative_revenue"
PRETAX_LOSS = "pretax_loss"
# A margin beyond 1,000% of revenue either way: a sliver of revenue, not a business's margin.
EXTREME_MARGIN = "extreme_margin"
# A snapshot-based figure asked for a past period (ADR 0008).
LATEST_PERIOD_ONLY = "latest_period_only"
MODEL_ANALYSIS_BANNER = "model-analysis"
EXPLORATORY_RESEARCH_BANNER = "exploratory-research"
NEWS_SUMMARY_BANNER = "news-summary"
SEARCH_NEWS_TOPIC = "news"
SEARCH_NEWS_MAX_RESULTS = 5
SEARCH_NEWS_TIME_RANGE = "week"


# The kind of report a filing comparison compares.
FilingForm = Literal["10-Q", "10-K"]


class WorkflowPlan(BaseModel):
    """A planner's reading of a question: one closed workflow and what it takes.

    Both planners return one, or a ``SpecPatch`` for an edit to the analysis on
    screen, and the turn types it into a request. A field the workflow does not
    take keeps its default.
    """

    model_config = ConfigDict(frozen=True)

    intent: Intent
    company: str | None = None
    companies: tuple[str, ...] = ()
    # A catalog slug, "overview", or the analyst's own word for a measure the catalog lacks.
    metric: str | None = None
    industry: str | None = None
    limit: int = DEFAULT_RANK_LIMIT
    # "Top 5 banks by net income" orders by it; "and their net income" does not.
    order_by_metric: bool = False
    # The window a model read, in quarters; code's own reading of the words comes first.
    recent_quarters: int | None = None
    # One company against the largest in its industry; the conversation adds them.
    peers: bool = False
    # What an essay is about; the question itself when there is none.
    topic: str | None = None
    # Two filings to compare (empty: the latest against the one before), which
    # sections, and whether the model's summary was asked for as well.
    older_accession: str = ""
    newer_accession: str = ""
    section: str = "both"
    # The kind of report to compare; the question's own words come first (ADR 0010).
    form: FilingForm | None = None
    summarize: bool = False
    # Further companies named where the workflow takes one.
    other_companies: tuple[str, ...] = ()
    # Said before the answer: a corrected name, a company left out.
    notes: tuple[str, ...] = ()


class Completer(Protocol):
    def complete(
        self, query: str, current_spec: Any | None = None
    ) -> "WorkflowPlan | SpecPatch": ...


class EssayCompleter(Protocol):
    def complete_essay(self, query: str, tool_json: str = "") -> str: ...


class FactsPort(Protocol):
    def get_financials(
        self,
        company: str,
        metric: str,
        *,
        report_date: date | None = None,
    ) -> FinancialFact: ...

    def list_quarterly_report_dates(self, company: str, *, limit: int) -> tuple[date, ...]: ...

    def fiscal_periods(self, company: str) -> tuple["FiscalPeriod", ...]: ...

    def files_quarterly(self, company: str) -> tuple[bool, str]: ...

    def display_name(self, cik: str, fallback: str) -> str: ...


class RankingPort(Protocol):
    def rank_companies(self, industry: str, limit: int) -> "RankTable": ...

    def lookup_member(self, company: str) -> "UniverseCompany": ...

    def member_ciks(self) -> Collection[str]: ...

    def snapshot_as_of(self) -> str: ...

    def snapshot_source(self) -> str: ...


class NewsPort(Protocol):
    def search_news(self, query: str) -> list["NewsHit"]: ...


class RuntimeKind(StrEnum):
    """The two provider sets a turn can run on (see CONTEXT.md)."""

    RECORDED = "recorded"
    LIVE = "live"


class FilingsPort(Protocol):
    """Raw SEC filing access for accession-pinned filing comparison."""

    def get_company_tickers(self) -> dict[str, Any]: ...

    def get_submissions(self, cik: str) -> dict[str, Any]: ...

    def get_filing_document(self, cik: str, accession: str, document: str) -> str: ...


@dataclass(frozen=True)
class Runtime:
    """Provider set for a turn. ``kind`` says whether it is the recorded or live runtime.

    ``kind`` defaults to recorded: a runtime assembled from test doubles replays canned
    answers. Builders that reach live providers set ``RuntimeKind.LIVE``.
    """

    completer: Completer
    facts: FactsPort
    ranking: RankingPort | None = None
    news: NewsPort | None = None
    essay: EssayCompleter | None = None
    # The same SEC source the facts lookup wraps, for filing comparison.
    filings: FilingsPort | None = None
    kind: RuntimeKind = RuntimeKind.RECORDED
    # On the live runtime, whether news search and written answers reach Tavily and
    # OpenAI. Without them it replays the recorded demo's answers and says so (story 36).
    live_news: bool = True
    live_essays: bool = True


class NewsHit(BaseModel):
    title: str
    url: str
    snippet: str = ""
    score: float | None = None
    published: str | None = None


class Refusal(BaseModel):
    """Stable reason for a refused turn, independent of its visitor-facing wording."""

    code: str
    details: dict[str, Any] = Field(default_factory=dict)


class ToolTrace(BaseModel):
    tool: str
    args: dict[str, Any]
    provenance: dict[str, Any] = Field(default_factory=dict)


class ComponentProvenance(BaseModel):
    metric: str
    value: DecimalStr
    start_date: date
    end_date: date
    form: str
    accession_number: str
    taxonomy: str
    concept: str
    source_url: str
    source: str
    # Set when the value is a derived quarter (ADR 0007), e.g. "Fiscal year minus nine months".
    derivation: str | None = None
    derived_from: list["ComponentProvenance"] = Field(default_factory=list)


# What a change is measured against (CONTEXT.md, Comparison base): the same
# quarter a year earlier, or the quarter before. One spelling for the analyst's
# choice, the analysis and the change rows it produces.
ComparisonBase = Literal["year_over_year", "sequential"]


class TableRow(BaseModel):
    company_name: str
    ticker: str
    cik: str
    metric: str
    rank: int | None = None
    value: DecimalStr | None = None
    currency: str | None = None
    start_date: date | None = None
    end_date: date | None = None
    form: str | None = None
    accession_number: str | None = None
    taxonomy: str | None = None
    concept: str | None = None
    source_url: str | None = None
    components: list[ComponentProvenance] = Field(default_factory=list)
    reason: str | None = None
    comparison: ComparisonBase | None = None
    # A derived quarter (ADR 0007): how it was computed, and the facts it came from.
    derivation: str | None = None
    derived_from: list[ComponentProvenance] = Field(default_factory=list)
    # A newer quarter is filed but not yet in SEC's structured data (see FinancialFact).
    newer_filing_end: date | None = None
    # A ranked company's snapshot market cap: the order a ranking is drawn in.
    market_cap: DecimalStr | None = None
    # The same figure a year earlier as this row's own filing reports it; a
    # year-over-year change reads it before the year-earlier row (CONTEXT.md).
    year_earlier: ComponentProvenance | None = None
    # Weighted diluted shares behind a per-share figure, so a split between two
    # quarters shows.
    diluted_shares: DecimalStr | None = None

    @field_validator("comparison", mode="before")
    @classmethod
    def _read_stored_comparison(cls, value: object) -> object:
        """Threads stored before the comparison base had one spelling say "yoy"."""
        return "year_over_year" if value == "yoy" else value


# Weighted diluted shares moving by half again or more between quarters is a split,
# not buybacks or issuance; so is a per-share figure restated by that much.
SPLIT_RATIO = Decimal("1.5")


def split_between(newer: TableRow, older: TableRow) -> bool:
    """Whether a share split falls between two per-share rows, by their share counts."""
    if newer.diluted_shares is None or older.diluted_shares is None:
        return False
    low, high = sorted((Decimal(str(newer.diluted_shares)), Decimal(str(older.diluted_shares))))
    return low > 0 and high / low >= SPLIT_RATIO


class DisclosureChange(BaseModel):
    """Deterministic paragraph-level change between two accession-pinned sections."""

    section: Literal["mda", "risk_factors"]
    section_label: str
    change_kind: Literal["added", "removed", "changed"]
    before_text: str = ""
    after_text: str = ""
    older_accession: str
    newer_accession: str
    older_url: str
    newer_url: str
    # The heading the paragraph sits under ("Liquidity and Capital Resources"), or "".
    subsection: str = ""
    selection_rule: str = (
        "Reviewed section extracted by Item heading; paragraph diff is deterministic."
    )


# What a CLARIFY result asks: pick one metric, extend vs replace the analysis,
# which of the companies a name could mean, or what a change is measured against.
ClarifyKind = Literal[
    "ambiguous_metric", "ambiguous_mode", "ambiguous_company", "ambiguous_comparison"
]


class TurnResult(BaseModel):
    intent: Intent
    tool_traces: list[ToolTrace]
    renderer: RendererKind
    table_rows: list[TableRow] = Field(default_factory=list)
    banners: list[str] = Field(default_factory=list)
    numeral_lock_extras: list[str] = Field(default_factory=list)
    message: str | None = None
    essay: str | None = None
    citations: list[NewsHit] = Field(default_factory=list)
    candidates: tuple[str, ...] = ()
    clarify_kind: ClarifyKind | None = None
    # How each candidate is shown ("Coca-Cola Consolidated (COKE)"); empty when
    # the candidate's own name reads well.
    candidate_labels: tuple[str, ...] = ()
    # The words a clarification asks about: the company name that was ambiguous.
    clarify_subject: str | None = None
    disclosure_changes: list[DisclosureChange] = Field(default_factory=list)
    # Questions the window offers next, phrased so the planner reads them.
    suggestions: list[str] = Field(default_factory=list)
    # A guide reply (help, greetings, advice declined) rather than a refusal.
    guide: bool = False
    # A ranking whose market-cap members are ordered by this metric instead.
    ordered_by: str | None = None
    # A few quarters of revenue and net margin beside one company's overview.
    trend_rows: list[TableRow] = Field(default_factory=list)
    # The quarter before a lone fact, for its quarter-over-quarter change.
    prior_quarter_rows: list[TableRow] = Field(default_factory=list)
    # The same quarter a year earlier as first filed, for a lone fact whose own
    # filing reports no year-earlier figure (ADR 0009).
    year_earlier_rows: list[TableRow] = Field(default_factory=list)
    refusal: Refusal | None = None
    snapshot_as_of: str | None = None
    # Position of a migrated legacy snapshot banner among visible banners.
    snapshot_banner_index: int = 0
    reused_evidence: bool = False

    @model_validator(mode="before")
    @classmethod
    def _read_legacy_metadata(cls, value: object) -> object:
        """Lift metadata out of results saved before it had typed fields."""
        if not isinstance(value, dict):
            return value
        data = dict(value)
        banners = list(data.get("banners") or [])
        kept: list[str] = []
        for banner in banners:
            if (
                data.get("snapshot_as_of") is None
                and isinstance(banner, str)
                and banner.startswith(SNAPSHOT_BANNER_PREFIX)
            ):
                data["snapshot_as_of"] = banner[len(SNAPSHOT_BANNER_PREFIX) :]
                data.setdefault("snapshot_banner_index", len(kept))
            elif banner == "Reused thread evidence":
                data.setdefault("reused_evidence", True)
            else:
                kept.append(banner)
        data["banners"] = kept
        if data.get("refusal") is None and data.get("renderer") == RendererKind.REFUSE:
            refusal = _legacy_refusal(data.get("message"))
            if refusal is not None:
                data["refusal"] = refusal
        data["tool_traces"] = _migrate_legacy_trace_errors(data.get("tool_traces"))
        return data

    @model_validator(mode="after")
    def _infer_clarify_kind(self) -> Self:
        """A clarification saved before ``clarify_kind`` existed says its kind by its candidates."""
        if self.renderer is RendererKind.CLARIFY and self.clarify_kind is None and self.candidates:
            self.clarify_kind = (
                "ambiguous_mode" if self.candidates == ("extend", "replace") else "ambiguous_metric"
            )
        return self


def refuse_unknown_metric(intent: Intent, term: str) -> TurnResult:
    return TurnResult(
        intent=intent,
        tool_traces=[],
        renderer=RendererKind.REFUSE,
        message=unknown_metric_message(term),
        refusal=Refusal(
            code="unknown_metric",
            details={"term": term, "allowed": list(ALLOWED_METRICS)},
        ),
    )


def refusal_from_error(exc: Any) -> Refusal:
    """Copy a domain error's stable public metadata at the workflow boundary."""
    return Refusal(code=str(exc.code), details=dict(exc.details))


def _legacy_refusal(message: object) -> dict[str, Any] | None:
    """Migrate refusal metadata from result records written before typed refusals."""
    if not isinstance(message, str):
        return None
    if message.startswith("Unknown metric ") and ". Allowed: " in message:
        named, allowed = message.removeprefix("Unknown metric ").split(". Allowed: ", 1)
        term = _legacy_single_quoted(named)
        if term is None:
            return None
        return {
            "code": "unknown_metric",
            "details": {
                "term": term,
                "allowed": [item for item in allowed.split(", ") if item],
            },
        }
    if message.startswith("Unknown industry ") and ". Allowed: " in message:
        named, allowed = message.removeprefix("Unknown industry ").split(". Allowed: ", 1)
        industry = _legacy_single_quoted(named, allow_inner_quote=True)
        if industry is None:
            return None
        return {
            "code": "unknown_industry",
            "details": {
                "industry": industry,
                "allowed": [item for item in allowed.split(", ") if item],
            },
        }
    prefix = "Company not found for query "
    if message.startswith(prefix):
        query = _legacy_single_quoted(
            message.removeprefix(prefix), allow_inner_quote=True
        )
        if query is None:
            return None
        return {
            "code": "company_not_found",
            "details": {"query": query},
        }
    legacy = {
        "No recorded filing document": ("provider_refusal", {"recorded_filing": True}),
        "Analysis has no companies or ranked constituents": (
            "empty_spec",
            {"missing": "companies"},
        ),
        "Analysis has no metrics": ("empty_spec", {"missing": "metrics"}),
        "No 10-Q or 10-Q/A filing found": ("filing_not_found", {}),
        "No dividend was declared in this quarter; one was declared earlier in the fiscal year": (
            "no_dividend_this_quarter",
            {},
        ),
        "Per-share figures for this quarter are reported only for a longer period": (
            "not_reported_for_quarter",
            {},
        ),
        "No reported or derivable quarter exists for metric": (
            "unsupported_quarterly_fact",
            {"reason": "not_reported_or_derivable"},
        ),
        "SEC's structured data does not yet include this quarter's filing": (
            "unsupported_quarterly_fact",
            {"reason": "pending_structured_data"},
        ),
        "Multiple directly reported quarterly facts remain after precedence rules": (
            "ambiguous_fact",
            {},
        ),
        "No directly reported standalone-quarter fact exists for metric": (
            "unsupported_quarterly_fact",
            {"reason": "no_standalone_quarter"},
        ),
    }
    found = legacy.get(message)
    if found is None:
        return None
    code, details = found
    return {"code": code, "details": details}


def _legacy_single_quoted(value: str, *, allow_inner_quote: bool = False) -> str | None:
    """What the old presentation regex accepted: one pair of single quotes."""
    if len(value) < 2 or not value.startswith("'") or not value.endswith("'"):
        return None
    inner = value[1:-1]
    return inner if allow_inner_quote or "'" not in inner else None


def _migrate_legacy_trace_errors(value: object) -> object:
    """Give stored trace errors the typed details their old message encoded."""
    if not isinstance(value, list):
        return value
    traces: list[object] = []
    for item in value:
        if not isinstance(item, dict):
            traces.append(item)
            continue
        trace = dict(item)
        provenance_value = trace.get("provenance")
        if not isinstance(provenance_value, dict):
            traces.append(trace)
            continue
        provenance = dict(provenance_value)
        error_value = provenance.get("error")
        if isinstance(error_value, dict) and not isinstance(error_value.get("details"), dict):
            error = dict(error_value)
            refusal = _legacy_refusal(error.get("message"))
            if refusal is not None and refusal["code"] == error.get("code"):
                error["details"] = refusal["details"]
                provenance["error"] = error
        trace["provenance"] = provenance
        traces.append(trace)
    return traces
