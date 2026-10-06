"""OpenAI structured-output planner. Emits a closed intent or a spec patch."""

from typing import Annotated, Any, Literal

import openai
from pydantic import AfterValidator, BaseModel, model_validator

from financial_analyst_agent.config import Settings
from financial_analyst_agent.contracts import (
    ALLOWED_METRICS,
    DEFAULT_RANK_LIMIT,
    Intent,
    WorkflowPlan,
)
from financial_analyst_agent.domain.errors import PlannerError
from financial_analyst_agent.graph.analysis_spec import (
    MAX_QUARTERS_ASKED,
    AnalysisSpec,
    PeriodSelection,
    RankedRequest,
    SpecPatch,
)

_PLANNER_FAILED_MESSAGE = "LLM planner failed"
_OVERVIEW = "overview"
_SYSTEM_PROMPT = (
    "Map the user's question about US public companies' SEC filings to a Plan. "
    "Code fetches and computes every number; you only choose what to look up. "
    "intent must be one of lookup, compare, rank, rank_and_lookup, explain, "
    "news_and_explain, exploratory_research, filing_change. "
    "Use lookup for one named company's reported figures, whether the latest quarter, "
    "a window of quarters, a named fiscal quarter, or growth. "
    "Use compare for two or more named companies on a metric. "
    "Use rank for the top N companies of an industry by market cap, with no other metric. "
    "Use rank_and_lookup for the top N of an industry with a metric for each. "
    "Use explain for qualitative industry or AI-disruption questions with no retrieval, and "
    "for a general question about how a figure works that names no company (explain how a "
    "buyback affects EPS; why does operating margin matter). "
    "Use news_and_explain for a named company's current events (supply chain, what's going on). "
    "Use exploratory_research for themes or open research that no figures answer and that "
    "need cited news rather than financial rows. "
    "Use filing_change when the user asks what changed in a company's 10-Q or 10-K, its "
    "MD&A or its Risk Factors. Set company. Set older_accession and newer_accession only "
    "when the user names accession numbers; leave them empty for the latest filing, and "
    "code compares the latest with the one before. Set section to mda, risk_factors, or "
    "both, as asked; both when the user names neither. Set form to 10-K when they ask "
    "about the annual report or 10-K, otherwise 10-Q. Set summarize true only when they "
    "also ask for a summary. "
    'Name companies as the user wrote them ("Nvidia", "JPM"), never CIKs. '
    f"metric is one of: {', '.join(ALLOWED_METRICS)}. "
    f"Use {_OVERVIEW} when the user asks how a company is doing without naming a metric. "
    "When the user names a measure the list lacks, set metric to their own words; code "
    "refuses it by name. When the measure is ambiguous (profit, income, margin, earnings), "
    "set metric to the user's word; code asks which they mean. "
    "Give the first metric when several are named; code reads the rest from the question. "
    "Periods (last N quarters, Q3 FY2025, since 2024) and year-over-year growth are read "
    "from the question by code. When the question asks for a window of recent quarters or "
    "years, also set recent_quarters to its length in quarters (a year is 4); code reads "
    "the wording first and uses yours only when it cannot. Otherwise leave it null. "
    "Set order_by_metric true when the user wants companies ranked, sorted, or ordered by "
    "the metric (top 5 banks by net income; which has the highest margin), false when they "
    "only want the metric shown for each (top 5 banks and their net income). "
    "Set peers true, with the one company in companies, when the user compares a company "
    "with its peers or competitors. "
    "For explain and exploratory_research, set topic to the user question. "
    "Never calculate, select, or invent financial values."
)
_FOLLOW_UP_PROMPT = (
    "The analyst is continuing a conversation thread. The current analysis spec "
    "is provided. Map this follow-up to a FollowUpPlan. "
    "Use intent spec_patch when they are editing or replacing the quantitative "
    "analysis. mode=extend when they add/remove/swap companies or metrics, "
    "change the period window, or ask for year-over-year on the current analysis. "
    "mode=replace when they start an unrelated new analysis, including a "
    "complete lookup or compare question about different issuers. "
    "mode=null when extend versus replace is unclear. "
    "Company names as the user said them — never CIKs. "
    "Do not invent financial values. "
    "Use explain / news_and_explain / exploratory_research only for qualitative "
    "or current-event questions that are not a spec edit. "
    "Use filing_change for what changed in a company's 10-Q, MD&A or Risk Factors. "
    f"Allowed metrics: {', '.join(ALLOWED_METRICS)}. "
    "Operations: across_companies (several companies side by side), across_periods "
    "(a window of quarters), rank (the top N of an industry), order_by_metric (sort the "
    'companies by the metric: "sort by revenue", "which is biggest"), year_over_year '
    '(growth against the same quarter a year earlier: "show year-over-year"). '
    "Remove year_over_year when they ask for plain levels again. "
    "Periods in the follow-up's wording are also read by code."
)


def _nonempty_text(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        raise ValueError("must not be blank")
    return normalized


def _positive_limit(value: int) -> int:
    if value < 1:
        raise ValueError("limit must be positive")
    return value


NonEmptyText = Annotated[str, AfterValidator(_nonempty_text)]
PositiveLimit = Annotated[int, AfterValidator(_positive_limit)]


class _LookupPlan(BaseModel):
    intent: Literal[Intent.LOOKUP]
    company: NonEmptyText
    # A catalog slug, "overview", or the user's own word for a measure the catalog lacks.
    metric: NonEmptyText
    # The window the question asks for, in quarters; code's reading of the words wins.
    recent_quarters: PositiveLimit | None = None


class _ComparePlan(BaseModel):
    intent: Literal[Intent.COMPARE]
    companies: list[NonEmptyText]
    metric: NonEmptyText
    order_by_metric: bool = False
    recent_quarters: PositiveLimit | None = None
    # One company against the largest in its industry; the conversation adds them.
    peers: bool = False

    @model_validator(mode="after")
    def _two_companies_or_peers(self) -> "_ComparePlan":
        if len(self.companies) < (1 if self.peers else 2):
            raise ValueError("companies must contain at least two issuers, or one with peers")
        return self


class _RankPlan(BaseModel):
    intent: Literal[Intent.RANK]
    industry: NonEmptyText
    limit: PositiveLimit = DEFAULT_RANK_LIMIT


class _RankAndLookupPlan(BaseModel):
    intent: Literal[Intent.RANK_AND_LOOKUP]
    industry: NonEmptyText
    metric: NonEmptyText
    limit: PositiveLimit = DEFAULT_RANK_LIMIT
    # "Top 5 banks by net income" orders by it; "and their net income" does not.
    order_by_metric: bool = False
    recent_quarters: PositiveLimit | None = None


class _ExplainPlan(BaseModel):
    intent: Literal[Intent.EXPLAIN]
    topic: NonEmptyText


class _NewsAndExplainPlan(BaseModel):
    intent: Literal[Intent.NEWS_AND_EXPLAIN]


class _ExploratoryResearchPlan(BaseModel):
    intent: Literal[Intent.EXPLORATORY_RESEARCH]
    topic: NonEmptyText


class _FilingChangePlan(BaseModel):
    intent: Literal[Intent.FILING_CHANGE]
    company: NonEmptyText
    # Empty for the latest filing against the one before it.
    older_accession: str = ""
    newer_accession: str = ""
    section: Literal["mda", "risk_factors", "both"] = "both"
    # The kind of report; code reads the question's own words first.
    form: Literal["10-Q", "10-K"] = "10-Q"
    summarize: bool = False


PlanAction = (
    _LookupPlan
    | _ComparePlan
    | _RankPlan
    | _RankAndLookupPlan
    | _ExplainPlan
    | _NewsAndExplainPlan
    | _ExploratoryResearchPlan
    | _FilingChangePlan
)


class _FlatActionModel(BaseModel):
    """Accept a bare action object as ``{"action": ...}``."""

    @model_validator(mode="before")
    @classmethod
    def _accept_flat_action(cls, value: Any) -> Any:
        if isinstance(value, dict) and "action" not in value and "intent" in value:
            return {"action": value}
        return value


class Plan(_FlatActionModel):
    action: PlanAction

    def workflow_plan(self) -> WorkflowPlan:
        """The model's answer as the plan both planners return.

        Each action's fields are ``WorkflowPlan`` fields; the rest keep their defaults.
        """
        return WorkflowPlan(**self.action.model_dump())


Operation = Literal[
    "across_companies", "across_periods", "rank", "order_by_metric", "year_over_year"
]


class _SpecPatchAction(BaseModel):
    intent: Literal["spec_patch"]
    mode: Literal["extend", "replace"] | None = None
    add_companies: tuple[str, ...] = ()
    remove_companies: tuple[str, ...] = ()
    add_metrics: tuple[str, ...] = ()
    remove_metrics: tuple[str, ...] = ()
    period_kind: Literal["latest_quarter", "last_n_quarters"] | None = None
    period_count: int | None = None
    add_operations: tuple[Operation, ...] = ()
    remove_operations: tuple[Operation, ...] = ()
    ranked_industry: str | None = None
    ranked_limit: PositiveLimit | None = None

    def to_spec_patch(self) -> SpecPatch:
        periods: PeriodSelection | None = None
        if self.period_kind == "last_n_quarters":
            periods = PeriodSelection(
                kind="last_n_quarters",
                count=min(
                    max(4 if self.period_count is None else self.period_count, 1),
                    MAX_QUARTERS_ASKED,
                ),
            )
        elif self.period_kind == "latest_quarter":
            periods = PeriodSelection()
        ranked: RankedRequest | None = None
        if self.ranked_industry:
            ranked = RankedRequest(
                industry=self.ranked_industry,
                limit=int(self.ranked_limit or DEFAULT_RANK_LIMIT),
            )
        return SpecPatch(
            mode=self.mode,
            add_companies=self.add_companies,
            remove_companies=self.remove_companies,
            add_metrics=self.add_metrics,
            remove_metrics=self.remove_metrics,
            set_periods=periods,
            add_operations=self.add_operations,
            remove_operations=self.remove_operations,
            ranked_request=ranked,
        )


FollowUpAction = (
    _SpecPatchAction
    | _ExplainPlan
    | _NewsAndExplainPlan
    | _ExploratoryResearchPlan
    | _FilingChangePlan
)


class FollowUpPlan(_FlatActionModel):
    action: FollowUpAction


def format_spec_for_planner(spec: AnalysisSpec) -> str:
    companies = (
        ", ".join(f"{company.name} ({company.ticker})" for company in spec.companies) or "(none)"
    )
    constituents = "(none)"
    if spec.constituents is not None:
        constituents = f"{spec.constituents.industry} top {spec.constituents.limit}"
    metrics = ", ".join(spec.metrics) or "(none)"
    period_label: str = spec.periods.kind
    if spec.periods.shown is not None:
        period_label = f"{spec.periods.kind} n={spec.periods.shown}"
    operations = ", ".join(spec.operations) or "(none)"
    return (
        f"Companies: {companies}\n"
        f"Ranked constituents: {constituents}\n"
        f"Metrics: {metrics}\n"
        f"Periods: {period_label}\n"
        f"Operations: {operations}"
    )


def openai_client_from_settings(settings: Settings) -> tuple[Any, str]:
    api_key = settings.require_openai_api_key()
    model = settings.require_openai_model()
    base_url = settings.openai_base_url.strip() or None
    return openai.OpenAI(api_key=api_key, base_url=base_url), model


class OpenAIStructuredCompleter:
    """Calls OpenAI parse() with Plan as the constrained response schema."""

    def __init__(self, client: Any, model: str) -> None:
        self._client = client
        self._model = model

    @classmethod
    def from_settings(cls, settings: Settings) -> "OpenAIStructuredCompleter":
        return cls(*openai_client_from_settings(settings))

    def complete(
        self, query: str, current_spec: AnalysisSpec | None = None
    ) -> WorkflowPlan | SpecPatch:
        if current_spec is None:
            system = _SYSTEM_PROMPT
            response_format: type[BaseModel] = Plan
        else:
            system = (
                f"{_FOLLOW_UP_PROMPT}\n\nCurrent analysis spec:\n"
                f"{format_spec_for_planner(current_spec)}"
            )
            response_format = FollowUpPlan
        try:
            completion = self._client.chat.completions.parse(
                model=self._model,
                messages=[
                    {"role": "system", "content": system},
                    {"role": "user", "content": query},
                ],
                response_format=response_format,
            )
        except openai.OpenAIError as exc:
            raise PlannerError(
                _PLANNER_FAILED_MESSAGE,
                details={"stage": "http", "error_class": type(exc).__name__},
            ) from exc
        except ValueError as exc:
            # The SDK validates the model's JSON against the plan's own rules (a
            # comparison of one company, a blank name) and raises pydantic's error.
            raise PlannerError(
                _PLANNER_FAILED_MESSAGE,
                details={"stage": "invalid_plan", "error_class": type(exc).__name__},
            ) from exc
        try:
            choice = completion.choices[0]
            message = choice.message
        except (AttributeError, IndexError, TypeError) as exc:
            raise PlannerError(
                _PLANNER_FAILED_MESSAGE,
                details={"stage": "malformed", "error_class": type(exc).__name__},
            ) from exc
        if getattr(message, "refusal", None):
            raise PlannerError(_PLANNER_FAILED_MESSAGE, details={"stage": "refusal"})
        parsed = getattr(message, "parsed", None)
        if parsed is None:
            raise PlannerError(_PLANNER_FAILED_MESSAGE, details={"stage": "missing_parsed"})
        if not isinstance(parsed, (Plan, FollowUpPlan)):
            schema = Plan if current_spec is None else FollowUpPlan
            parsed = schema.model_validate(parsed)
        if isinstance(parsed, FollowUpPlan):
            if isinstance(parsed.action, _SpecPatchAction):
                return parsed.action.to_spec_patch()
            return Plan(action=parsed.action).workflow_plan()
        return parsed.workflow_plan()
