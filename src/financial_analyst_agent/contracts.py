"""Stable application contracts: ports, Runtime, result models, enums, metric constants.

Workflow implementations live in ``turn``; a graph package can import this module
without loading those workflows.
"""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import TYPE_CHECKING, Any, Literal, Protocol, Self

from pydantic import BaseModel, Field, field_validator, model_validator

from financial_analyst_agent.domain.models import FinancialFact
from financial_analyst_agent.domain.serialization import DecimalStr
from financial_analyst_agent.services.metric_catalog import METRIC_DISPLAY

if TYPE_CHECKING:
    from financial_analyst_agent.ranking import RankTable
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


def snapshot_banner(as_of: str) -> str:
    """Raw banner naming the ranking snapshot; presentation reformats the timestamp."""
    return f"{SNAPSHOT_BANNER_PREFIX}{as_of}"


def unknown_metric_message(term: str) -> str:
    # presentation._UNKNOWN_METRIC parses this wording back out; keep the two in step.
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


class Completer(Protocol):
    def complete(self, query: str, current_spec: Any | None = None) -> Any: ...


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


class RankingPort(Protocol):
    def rank_companies(self, industry: str, limit: int) -> "RankTable": ...

    def lookup_member(self, company: str) -> "UniverseCompany": ...

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
    )
