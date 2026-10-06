"""Application seam: run_turn(query, runtime) → TurnResult.

Contracts (ports, Runtime, result models, enums, metric constants) live in
``contracts``; this module keeps the workflow implementations the analysis
graph calls: one function per compiled task kind (``lookup_task``,
``compare_task``, ``rank_task``, ``rank_and_lookup_task``) and one per
qualitative workflow (``explain_answer``, ``current_events_answer``,
``exploratory_research_answer``).

``run_turn`` is a compatibility wrapper over an ephemeral conversation thread.
New multi-turn behaviour is asserted at ``run_conversation_turn``.
"""

import json
import re
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

from financial_analyst_agent.contracts import (
    AMBIGUOUS_CONCEPT,
    COMPANY_NOT_FOUND,
    DEFAULT_RANK_LIMIT,
    DIFFERENCE_FORMULAS,
    EXPLORATORY_RESEARCH_BANNER,
    EXTREME_MARGIN,
    FORMULA_COMPONENTS,
    INSTANT_METRICS,
    LATEST_PERIOD_ONLY,
    MARGIN_FORMULAS,
    MARKET_FORMULAS,
    MISSING_FACT,
    MODEL_ANALYSIS_BANNER,
    NEGATIVE_EQUITY,
    NEGATIVE_REVENUE,
    NEWS_SUMMARY_BANNER,
    NO_DIVIDEND_THIS_QUARTER,
    NOT_IN_SNAPSHOT,
    NOT_MEANINGFUL,
    NOT_OPERATING_COMPANY,
    NOT_REPORTED_FOR_QUARTER,
    PERIOD_MISMATCH,
    PRETAX_LOSS,
    SEARCH_NEWS_MAX_RESULTS,
    SEARCH_NEWS_TIME_RANGE,
    SEARCH_NEWS_TOPIC,
    SNAPSHOT_METRICS,
    SOURCE_UNAVAILABLE,
    SUM_FORMULAS,
    ZERO_DENOMINATOR,
    ComponentProvenance,
    FactsPort,
    Intent,
    NewsHit,
    RankingPort,
    RendererKind,
    Runtime,
    RuntimeKind,
    TableRow,
    ToolTrace,
    TurnResult,
    refusal_from_error,
)
from financial_analyst_agent.domain.errors import (
    SOURCE_FAILURES,
    AmbiguousCompanyError,
    AmbiguousFactError,
    CompanyNotFoundError,
    IneligibleIssuerError,
    NoDividendThisQuarterError,
    PerShareNotDerivableError,
    ProviderError,
    UnknownIndustryError,
    UnsupportedQuarterlyFactError,
    visitor_message,
)
from financial_analyst_agent.domain.models import DerivationPart, FinancialFact
from financial_analyst_agent.fan_out import map_in_order
from financial_analyst_agent.graph.analysis_spec import CompiledTask
from financial_analyst_agent.observability import call_provider
from financial_analyst_agent.services.filing_selector import FISCAL_WEEK_TOLERANCE
from financial_analyst_agent.universe import UniverseCompany

_LOOKUP_FAILURES = (
    AmbiguousFactError,
    UnsupportedQuarterlyFactError,
    AmbiguousCompanyError,
    CompanyNotFoundError,
)
# What one company in a comparison or ranking may fail with and still leave
# the other companies their own rows.
_COMPANY_FAILURES = (*_LOOKUP_FAILURES, *SOURCE_FAILURES)
ESSAY_UNAVAILABLE_MESSAGE = "The written answer could not be produced just now. Please try again."
_NUMERIC_TOKEN = re.compile(
    # A number never ends in its list comma ("29, then"), and a one-letter unit
    # must end the word ("5B", not the "t" of "then").
    r"\$?\d(?:[\d,]*\d)?(?:\.\d+)?(?:\s*(?:[KMBTkmbt]\b|[Bb]illion|[Mm]illion|[Tt]rillion))?"
)
_CITE_MARKER = re.compile(r"\[([1-9]\d*)\]")
# Grounding keys whose digits identify a document rather than state a figure.
_IDENTIFIER_KEYS = frozenset({"url", "cik", "document", "primary_document", "anchor"})
_MONTH = (
    r"(?:Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|June?|July?|Aug(?:ust)?"
    r"|Sep(?:t(?:ember)?)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)"
)
# What may follow a date and makes it an amount instead: "March 12%", "2050 million".
_AMOUNT_AFTER = (
    r"(?!\s*(?:%|percent\b|[KMBTkmbt]\b|thousand\b|million\b|billion\b|trillion\b"
    r"|dollars?\b|shares\b)|[.,]?\d)"
)
# Dates are when, not how much: "March 31, 2026", "2026-03-31" or "in fiscal 2026" in
# an essay is not a figure, and a grounding date's "31" or "03" must not unlock "31%"
# elsewhere. A bare four-digit number is a year only beside a word that dates it;
# "hire 2000 engineers" stays a figure.
_DATE_TEXT = re.compile(
    rf"\b\d{{4}}-\d{{2}}-\d{{2}}(?:T[\d:.+-]+Z?)?\b"
    rf"|\b{_MONTH}\.?\s+\d{{1,2}}(?:st|nd|rd|th)?(?:,?\s+(?:19|20)\d{{2}})?\b{_AMOUNT_AFTER}"
    rf"|\b{_MONTH}\.?\s+(?:19|20)\d{{2}}\b{_AMOUNT_AFTER}"
    r"|\b(?:in|during|since|by|until|through|from|fiscal(?:\s+year)?|calendar(?:\s+year)?"
    r"|FY|Q[1-4]|H[12]|early|mid|late|end\s+of)\s*'?(?:19|20)\d{2}\b"
    rf"{_AMOUNT_AFTER}",
    re.IGNORECASE,
)
_YEAR = re.compile(r"\b(?:19|20)\d{2}\b")

__all__ = [
    "compare_metrics",
    "compare_task",
    "current_events_answer",
    "explain_answer",
    "exploratory_research_answer",
    "lookup_task",
    "market_formula_rows",
    "rank_and_lookup_task",
    "rank_task",
    "run_turn",
    "snapshot_compare_rows",
]


def _strip_valid_citation_markers(essay: str, hit_count: int) -> str:
    def replace(match: re.Match[str]) -> str:
        raw = match.group(1)
        index = int(raw)
        if raw == str(index) and 1 <= index <= hit_count:
            return ""
        return match.group(0)

    return _CITE_MARKER.sub(replace, essay)


def _is_identifier_key(key: str) -> bool:
    key = key.casefold()
    return key in _IDENTIFIER_KEYS or key.endswith("_url") or "accession" in key


def _grounding_text(tool_json: str) -> str:
    """The grounding's readable values, without the digits of links and identifiers.

    "0000950170-25-061046" and an article's URL are not figures an essay can
    quote: "25%" must not pass because an accession number holds "-25-".
    """
    try:
        payload = json.loads(tool_json)
    except ValueError:
        return tool_json
    parts: list[str] = []

    def walk(value: Any) -> None:
        if isinstance(value, dict):
            for key, item in value.items():
                if not _is_identifier_key(str(key)):
                    walk(item)
        elif isinstance(value, list):
            for item in value:
                walk(item)
        elif value is not None:
            parts.append(str(value))

    walk(payload)
    return "\n".join(parts)


def _figures(text: str) -> list[str]:
    """Numeric tokens outside dates."""
    return _NUMERIC_TOKEN.findall(_DATE_TEXT.sub(" ", text))


_UNIT_SCALE = {
    "k": Decimal(1_000),
    "thousand": Decimal(1_000),
    "m": Decimal(1_000_000),
    "million": Decimal(1_000_000),
    "b": Decimal(1_000_000_000),
    "billion": Decimal(1_000_000_000),
    "t": Decimal(1_000_000_000_000),
    "trillion": Decimal(1_000_000_000_000),
}
_FIGURE_PARTS = re.compile(r"\$?(?P<number>\d[\d,]*(?:\.(?P<decimals>\d+))?)\s*(?P<unit>[A-Za-z]*)")
_PERCENT_AFTER = re.compile(r"\s*(?:%|percent\b|per cent\b)", re.IGNORECASE)
# A figure shown to fewer significant digits than this ("$2 billion", "3%") is
# too coarse to tie to one grounded value, so only an exact match lets it pass.
_MIN_SIGNIFICANT_DIGITS = 2


def _grounded_amounts(grounding: str) -> list[Decimal]:
    """Every number in the grounding, as an amount (sign dropped, as an essay's has none)."""
    amounts = []
    for token in _figures(grounding):
        try:
            amounts.append(abs(Decimal(token.lstrip("$").split()[0].replace(",", ""))))
        except ArithmeticError:
            continue
    return amounts


def _rounds_from_grounding(token: str, percent: bool, amounts: list[Decimal]) -> bool:
    """Whether ``token`` is a grounded amount written as the window or a reader would.

    "$22.97 B", "$22.97 billion" and "about $23 billion" round from 22974000000 at
    the precision they show; "30.9%" rounds from the ratio 0.3088. A digit changed
    at that precision ("$22.98 B", "31.9%") rounds from nothing grounded.
    """
    parts = _FIGURE_PARTS.fullmatch(token.strip())
    if parts is None:
        return False
    shown = Decimal(parts.group("number").replace(",", ""))
    decimals = len(parts.group("decimals") or "")
    if len(shown.as_tuple().digits) < _MIN_SIGNIFICANT_DIGITS or shown == 0:
        return False
    unit = parts.group("unit").casefold()
    if unit and unit not in _UNIT_SCALE:
        return False
    scale = _UNIT_SCALE.get(unit, Decimal(1)) / (Decimal(100) if percent else Decimal(1))
    step = Decimal(1).scaleb(-decimals)
    for amount in amounts:
        try:
            if (amount / scale).quantize(step, rounding=ROUND_HALF_UP) == shown:
                return True
        except InvalidOperation:
            continue
    return False


def _numeral_lock_extras(essay: str, tool_json: str, *, hit_count: int = 0) -> list[str]:
    scanned = _DATE_TEXT.sub(" ", _strip_valid_citation_markers(essay, hit_count))
    grounding = _grounding_text(tool_json)
    # A source's dates do not unlock their day or month, but their years may be quoted.
    years = {
        year for date in _DATE_TEXT.findall(grounding) for year in _YEAR.findall(date)
    }
    allowed = set(_figures(grounding)) | years
    amounts = _grounded_amounts(grounding)
    extras = []
    for match in _NUMERIC_TOKEN.finditer(scanned):
        token = match.group(0)
        if token in allowed:
            continue
        percent = _PERCENT_AFTER.match(scanned, match.end()) is not None
        if not _rounds_from_grounding(token, percent, amounts):
            extras.append(token)
    return list(dict.fromkeys(extras))


def _numeral_lock_message(invented: str) -> str:
    return (
        "The written answer was withheld because it quoted numbers its sources "
        f"do not contain: {invented}."
    )


def explain_answer(topic: str, runtime: Runtime, *, grounding_json: str = "") -> TurnResult:
    """A model-analysis essay on ``topic``, held to the numeral lock.

    ``grounding_json`` is the deterministic rows of the thread's last answer, if any:
    the only figures the essay may quote.
    """
    if runtime.essay is None:
        raise RuntimeError("explain intent requires an essay completer")
    essay_completer = runtime.essay
    traces = [ToolTrace(tool="explain_topic", args={"topic": topic})]
    try:
        essay = call_provider(
            "llm",
            lambda: essay_completer.complete_essay(topic, grounding_json),
        )
    except ProviderError as exc:
        traces[0] = traces[0].model_copy(
            update={"provenance": {"error": {"code": exc.code, "message": str(exc)}}}
        )
        return TurnResult(
            intent=Intent.EXPLAIN,
            tool_traces=traces,
            renderer=RendererKind.REFUSE,
            message=visitor_message(exc, ESSAY_UNAVAILABLE_MESSAGE),
            refusal=refusal_from_error(exc),
        )
    lock_json = grounding_json or json.dumps(
        [trace.model_dump(mode="json") for trace in traces]
    )
    extras = _numeral_lock_extras(essay, lock_json)
    if extras:
        invented = ", ".join(extras)
        return TurnResult(
            intent=Intent.EXPLAIN,
            tool_traces=traces,
            renderer=RendererKind.REFUSE,
            numeral_lock_extras=extras,
            message=_numeral_lock_message(invented),
        )
    return TurnResult(
        intent=Intent.EXPLAIN,
        tool_traces=traces,
        renderer=RendererKind.ESSAY,
        banners=[
            MODEL_ANALYSIS_BANNER,
            *(
                [REPLAYED_ESSAY_BANNER]
                if runtime.kind is RuntimeKind.LIVE and not runtime.live_essays
                else []
            ),
        ],
        essay=essay,
    )


def _usable_news_hits(hits: list[NewsHit]) -> list[NewsHit]:
    usable = [hit for hit in hits if hit.title.strip() and hit.url.strip()]
    return usable[:SEARCH_NEWS_MAX_RESULTS]


def _search_news_args(query: str) -> dict[str, Any]:
    return {
        "query": query,
        "topic": SEARCH_NEWS_TOPIC,
        "max_results": SEARCH_NEWS_MAX_RESULTS,
        "time_range": SEARCH_NEWS_TIME_RANGE,
    }


def _hits_json(hits: list[NewsHit]) -> str:
    return json.dumps([hit.model_dump(mode="json") for hit in hits])


NO_NEWS_MESSAGE = (
    "I found no news articles for this, and I only answer news questions from articles I "
    "can cite."
)


REPLAYED_NEWS_BANNER = (
    "Replayed: this server has no live news search, so these are the recorded demo's articles."
)
REPLAYED_ESSAY_BANNER = (
    "Replayed: this server has no OpenAI key, so this is the recorded demo's written answer."
)


def _replays_news(runtime: Runtime) -> bool:
    return runtime.kind is RuntimeKind.RECORDED or not runtime.live_news


def _replay_banners(runtime: Runtime) -> list[str]:
    """On the live runtime, label an answer replayed from the recorded demo (story 36)."""
    if runtime.kind is RuntimeKind.RECORDED:
        return []
    banners = [] if runtime.live_news else [REPLAYED_NEWS_BANNER]
    return banners + ([] if runtime.live_essays else [REPLAYED_ESSAY_BANNER])


def _no_news_message(runtime: Runtime) -> str:
    if not _replays_news(runtime):
        return NO_NEWS_MESSAGE
    from financial_analyst_agent.news import FIXTURE_NEWS_QUERY

    if runtime.kind is RuntimeKind.RECORDED:
        return (
            f"{NO_NEWS_MESSAGE} The recorded demo only replays captured news for "
            f"“{FIXTURE_NEWS_QUERY}”."
        )
    # No search ran: saying "I found no news" would claim one did.
    return (
        "News search is off on this server, and I only answer news questions from "
        f"articles I can cite. It can replay the captured news for “{FIXTURE_NEWS_QUERY}”."
    )


def _news_grounded_essay_turn(
    query: str, runtime: Runtime, *, intent: Intent, banners: list[str] | None = None
) -> TurnResult:
    if runtime.news is None:
        raise RuntimeError(f"{intent.value} intent requires a news adapter")
    if runtime.essay is None:
        raise RuntimeError(f"{intent.value} intent requires an essay completer")
    news = runtime.news
    essay_completer = runtime.essay
    search_args = _search_news_args(query)
    try:
        hits = _usable_news_hits(call_provider("news", lambda: news.search_news(query)))
    except ProviderError as exc:
        return TurnResult(
            intent=intent,
            tool_traces=[
                ToolTrace(
                    tool="search_news",
                    args=search_args,
                    provenance={
                        "error": {"code": exc.code, "message": str(exc)},
                    },
                )
            ],
            renderer=RendererKind.REFUSE,
            message=(
                "News search is unavailable right now, and I only answer news questions "
                "from articles I can cite."
            ),
            refusal=refusal_from_error(exc),
        )
    traces = [
        ToolTrace(
            tool="search_news",
            args=search_args,
            provenance={"hits": [hit.model_dump(mode="json") for hit in hits]},
        )
    ]
    if not hits:
        return TurnResult(
            intent=intent,
            tool_traces=traces,
            renderer=RendererKind.REFUSE,
            message=_no_news_message(runtime),
        )
    tool_json = _hits_json(hits)
    essay = call_provider(
        "llm", lambda: essay_completer.complete_essay(query, tool_json)
    )
    extras = _numeral_lock_extras(essay, tool_json, hit_count=len(hits))
    if extras:
        invented = ", ".join(extras)
        return TurnResult(
            intent=intent,
            tool_traces=traces,
            renderer=RendererKind.REFUSE,
            citations=hits,
            numeral_lock_extras=extras,
            message=_numeral_lock_message(invented),
        )
    return TurnResult(
        intent=intent,
        tool_traces=traces,
        renderer=RendererKind.ESSAY,
        citations=hits,
        banners=[*(banners or []), *_replay_banners(runtime)],
        essay=essay,
    )


def current_events_answer(query: str, runtime: Runtime) -> TurnResult:
    """A cited news summary via the constrained news wrapper, held to the numeral lock."""
    return _news_grounded_essay_turn(
        query, runtime, intent=Intent.NEWS_AND_EXPLAIN, banners=[NEWS_SUMMARY_BANNER]
    )


def exploratory_research_answer(query: str, runtime: Runtime) -> TurnResult:
    """Cited research draft via the constrained news wrapper; never structured rows."""
    return _news_grounded_essay_turn(
        query,
        runtime,
        intent=Intent.EXPLORATORY_RESEARCH,
        banners=[EXPLORATORY_RESEARCH_BANNER],
    )


def _part_provenance(part: DerivationPart, parent: str, source: str) -> ComponentProvenance:
    """A reported fact behind a derived amount, with the facts it came from in turn."""
    nested = part.derivation
    own = part.metric or parent
    return ComponentProvenance(
        metric=own,
        value=part.value,
        start_date=part.start_date,
        end_date=part.end_date,
        form=part.form,
        accession_number=part.accession_number,
        taxonomy=part.taxonomy,
        concept=part.concept,
        source_url=part.source_url,
        source=source,
        derivation=nested.label if nested is not None else None,
        derived_from=(
            [_part_provenance(inner, own, source) for inner in nested.parts] if nested else []
        ),
        split_adjustment=part.split_adjustment,
    )


def _derivation_fields(fact: FinancialFact) -> dict[str, Any]:
    """A derived quarter's label and the reported facts it came from (ADR 0007)."""
    derivation = fact.derivation
    if derivation is None:
        return {}
    metric = fact.metric.value
    source = _fact_source_kind(fact)
    return {
        "derivation": derivation.label,
        "derived_from": [_part_provenance(part, metric, source) for part in derivation.parts],
    }


def _year_earlier(fact: FinancialFact, metric: str | None = None) -> ComponentProvenance | None:
    """The fact's year-earlier comparative, as its own filing reports it."""
    before = fact.year_earlier
    if before is None:
        return None
    return _part_provenance(before, metric or fact.metric.value, _fact_source_kind(fact))


def _table_row_from_fact(fact: FinancialFact) -> TableRow:
    return TableRow(
        company_name=fact.company_name,
        ticker=fact.ticker,
        cik=fact.cik,
        metric=fact.metric.value,
        value=fact.value,
        currency=fact.currency,
        start_date=fact.start_date,
        end_date=fact.end_date,
        form=fact.form,
        accession_number=fact.accession_number,
        taxonomy=fact.taxonomy,
        concept=fact.concept,
        source_url=fact.source_url,
        newer_filing_end=fact.newer_filing_end,
        year_earlier=_year_earlier(fact),
        diluted_shares=fact.diluted_shares,
        split_adjustment=fact.split_adjustment,
        **_derivation_fields(fact),
    )


def _fact_source_kind(fact: FinancialFact) -> str:
    return str(fact.source)


def _lookup_provenance(fact: FinancialFact) -> dict[str, Any]:
    derivation = fact.derivation
    extra: dict[str, Any] = {}
    if derivation is not None:
        extra["derivation"] = derivation.model_dump(mode="json")
    return extra | {
        "form": fact.form,
        "accession_number": fact.accession_number,
        "taxonomy": fact.taxonomy,
        "concept": fact.concept,
        "start_date": fact.start_date.isoformat(),
        "end_date": fact.end_date.isoformat(),
        "source": _fact_source_kind(fact),
        "source_url": fact.source_url,
    }


def _ranked_table(
    task: CompiledTask, runtime: Runtime, intent: Intent
) -> tuple[Any, ToolTrace] | TurnResult:
    """The task's ranked industry, or a refusal when the industry is unknown.

    A task compiled from a resolved spec carries the spec's ranking; only a
    task without one ranks the industry here.
    """
    if runtime.ranking is None:
        raise RuntimeError(f"{intent.value} intent requires a ranking adapter")
    industry = task.industry or ""
    limit = task.limit or DEFAULT_RANK_LIMIT
    try:
        table = task.ranked or runtime.ranking.rank_companies(industry, limit)
    except UnknownIndustryError as exc:
        return TurnResult(
            intent=intent,
            tool_traces=[],
            renderer=RendererKind.REFUSE,
            message=str(exc),
            refusal=refusal_from_error(exc),
        )
    trace = ToolTrace(
        tool="rank_companies",
        args={"industry": industry, "limit": limit},
        provenance={
            "snapshot_as_of": table.as_of,
            "source": table.source,
            "sector": table.sector,
        },
    )
    return table, trace


def rank_task(task: CompiledTask, runtime: Runtime) -> TurnResult:
    """The snapshot's largest members of an industry, by market cap."""
    ranked = _ranked_table(task, runtime, Intent.RANK)
    if isinstance(ranked, TurnResult):
        return ranked
    table, trace = ranked
    rows = [
        _snapshot_row(company, "market_cap", rank=index)
        for index, company in enumerate(table.companies, start=1)
    ]
    return TurnResult(
        intent=Intent.RANK,
        tool_traces=[trace],
        renderer=RendererKind.TABLE,
        table_rows=rows,
        snapshot_as_of=table.as_of,
    )


def _component_metrics(metric: str) -> tuple[str, ...]:
    formula = FORMULA_COMPONENTS.get(metric)
    if formula is not None:
        return formula
    return (metric,)


def _provenance_from_fact(fact: FinancialFact, metric: str) -> ComponentProvenance:
    return ComponentProvenance(
        metric=metric,
        value=fact.value,
        start_date=fact.start_date,
        end_date=fact.end_date,
        form=fact.form,
        accession_number=fact.accession_number,
        taxonomy=fact.taxonomy,
        concept=fact.concept,
        source_url=fact.source_url,
        source=_fact_source_kind(fact),
        split_adjustment=fact.split_adjustment,
        **_derivation_fields(fact),
    )


def _formula_value(metric: str, facts: list[FinancialFact]) -> Any:
    components = FORMULA_COMPONENTS.get(metric)
    if components is None:
        return facts[0].value
    first, second = facts
    if metric in DIFFERENCE_FORMULAS:
        return first.value - second.value
    if metric in SUM_FORMULAS:
        return first.value + second.value
    return first.value / second.value


# A margin past this many times revenue says more about the revenue than the business.
_EXTREME_MARGIN = Decimal(10)
# Ratios that mean nothing when their denominator is negative, and why.
_NEGATIVE_DENOMINATOR = {
    **dict.fromkeys(MARGIN_FORMULAS, NEGATIVE_REVENUE),
    "return_on_equity": NEGATIVE_EQUITY,
    "effective_tax_rate": PRETAX_LOSS,
}


def _not_meaningful(metric: str, facts: list[FinancialFact]) -> str | None:
    """Why a ratio's value would mislead, or None when it is sound to show."""
    if (
        metric not in FORMULA_COMPONENTS
        or metric in DIFFERENCE_FORMULAS
        or metric in SUM_FORMULAS
    ):
        return None
    numerator, denominator = facts
    if denominator.value == 0:
        return ZERO_DENOMINATOR
    reason = _NEGATIVE_DENOMINATOR.get(metric)
    if reason is not None and denominator.value < 0:
        return reason
    if metric in MARGIN_FORMULAS and abs(numerator.value / denominator.value) > _EXTREME_MARGIN:
        return EXTREME_MARGIN
    return None


def _formula_year_earlier(
    metric: str, facts: list[FinancialFact], names: tuple[str, ...]
) -> ComponentProvenance | None:
    """The formula over each component's year-earlier comparative, when all have one."""
    if metric not in FORMULA_COMPONENTS:
        return _year_earlier(facts[0], metric)
    befores = [_year_earlier(fact, name) for fact, name in zip(facts, names, strict=True)]
    if any(before is None for before in befores):
        return None
    parts = [before for before in befores if before is not None]
    if len({part.end_date for part in parts}) != 1:
        return None
    first = parts[0]
    as_facts = [
        fact.model_copy(update={"value": part.value})
        for fact, part in zip(facts, parts, strict=True)
    ]
    if _not_meaningful(metric, as_facts) is not None:
        return None
    durations = [part for part in parts if part.metric not in INSTANT_METRICS] or parts
    return ComponentProvenance(
        metric=metric,
        value=_formula_value(metric, as_facts),
        start_date=durations[0].start_date,
        end_date=first.end_date,
        form=first.form,
        accession_number=first.accession_number,
        taxonomy="",
        concept="",
        source_url=first.source_url,
        source=first.source,
        derived_from=parts,
    )


def _metric_name(fact: FinancialFact) -> str:
    return fact.metric.value


def _aligned_period(facts: list[FinancialFact]) -> tuple[date, date] | None:
    """The period every component covers; a balance-sheet amount needs only its date.

    Return on equity divides a trailing year by the equity on its last day, so
    the row keeps the year and the equity must be at that year's end.
    """
    durations = [fact for fact in facts if _metric_name(fact) not in INSTANT_METRICS]
    periods = {(fact.start_date, fact.end_date) for fact in durations or facts}
    if len(periods) != 1:
        return None
    period = next(iter(periods))
    if any(fact.end_date != period[1] for fact in facts):
        return None
    return period


PERIODS_DIFFER_BANNER = (
    "These companies' latest quarters end on different dates, so the values cover "
    "different periods. Each row shows its own quarter."
)


def _same_fiscal_period(periods: set[tuple[date | None, date | None]]) -> bool:
    """True when every period is one fiscal quarter, allowing 52/53-week calendars.

    Apple's quarter ending March 28 and Microsoft's ending March 31 are the same
    quarter; bounds further apart than ``FISCAL_WEEK_TOLERANCE`` are not.
    """
    if len(periods) <= 1:
        return True
    starts = [start for start, _end in periods if start is not None]
    ends = [end for _start, end in periods if end is not None]
    if len(starts) != len(periods) or len(ends) != len(periods):
        return False
    return all(
        max(bounds) - min(bounds) <= FISCAL_WEEK_TOLERANCE for bounds in (starts, ends)
    )


# A failed cell's reason by the error's code, so one failure reads alike whichever
# workflow met it: a fund is "not an operating company" rather than a missing
# filing, a per-share figure for a quarter the filings report only for the year
# says so, and anything else is a missing fact.
_REASON_BY_CODE = {
    IneligibleIssuerError.code: NOT_OPERATING_COMPANY,
    CompanyNotFoundError.code: COMPANY_NOT_FOUND,
    AmbiguousFactError.code: AMBIGUOUS_CONCEPT,
    PerShareNotDerivableError.code: NOT_REPORTED_FOR_QUARTER,
    NoDividendThisQuarterError.code: NO_DIVIDEND_THIS_QUARTER,
}


def reason_for_code(code: str | None) -> str:
    """Why a cell is empty, from the code of the error that emptied it."""
    return _REASON_BY_CODE.get(code or "", MISSING_FACT)


def reason_for(exc: BaseException) -> str:
    """Why a cell is empty, from the error that emptied it."""
    if isinstance(exc, SOURCE_FAILURES):
        # EDGAR failed for this company; the filing may well report the fact.
        return SOURCE_UNAVAILABLE
    return reason_for_code(getattr(exc, "code", None))


def _compare_unresolved_row(
    issuer: str, metric: str, reason: str, report_date: date | None = None
) -> TableRow:
    # A dated cell keeps its quarter, so a window table shows it on that quarter's row.
    return TableRow(
        company_name=issuer,
        ticker="",
        cik="",
        metric=metric,
        reason=reason,
        end_date=report_date,
    )


def _compare_row(identity: FinancialFact, metric: str, **kwargs: Any) -> TableRow:
    return TableRow(
        company_name=identity.company_name,
        ticker=identity.ticker,
        cik=identity.cik,
        metric=metric,
        **kwargs,
    )


def compare_metrics(
    facts: FactsPort,
    issuers: list[str],
    metric: str,
    *,
    report_date: date | None = None,
) -> list[TableRow]:
    """Resolve issuers, fetch formula components, and period-align Decimal results.

    The issuers' facts are fetched at once; the rows are built in issuer order.
    """
    component_names = _component_metrics(metric)

    def fetch(issuer: str) -> list[FinancialFact] | Exception:
        try:
            return [
                facts.get_financials(issuer, component, report_date=report_date)
                for component in component_names
            ]
        except _COMPANY_FAILURES as exc:
            return exc

    rows: list[TableRow] = []
    seen_ciks: set[str] = set()
    for issuer, fetched in zip(issuers, map_in_order(fetch, issuers), strict=True):
        if isinstance(fetched, Exception):
            rows.append(
                _compare_unresolved_row(
                    issuer, metric, reason_for(fetched), report_date=report_date
                )
            )
            continue
        identity = fetched[0]
        if identity.cik in seen_ciks:
            continue
        seen_ciks.add(identity.cik)
        period = _aligned_period(fetched)
        components = [
            _provenance_from_fact(fact, component)
            for fact, component in zip(fetched, component_names, strict=True)
        ]
        if period is None:
            rows.append(
                _compare_row(
                    identity,
                    metric,
                    components=components,
                    reason=PERIOD_MISMATCH,
                )
            )
            continue
        period_start, period_end = period
        unusable = _not_meaningful(metric, fetched)
        if unusable is not None:
            rows.append(
                _compare_row(
                    identity,
                    metric,
                    start_date=period_start,
                    end_date=period_end,
                    components=components,
                    reason=unusable,
                )
            )
            continue
        rows.append(
            _compare_row(
                identity,
                metric,
                value=_formula_value(metric, fetched),
                start_date=period_start,
                end_date=period_end,
                components=components,
                year_earlier=_formula_year_earlier(metric, fetched, component_names),
                diluted_shares=identity.diluted_shares,
                # A one-fact row is that fact: a split-adjusted level says so.
                split_adjustment=identity.split_adjustment if len(fetched) == 1 else None,
                newer_filing_end=max(
                    (
                        pending
                        for fact in fetched
                        if (pending := fact.newer_filing_end)
                    ),
                    default=None,
                ),
            )
        )
    # Each row keeps its own issuer's period. When issuers' latest quarters end on
    # different dates the values stay visible, each with its own dates, and the
    # turn says the periods differ (see ``periods_differ``); no value is ever
    # computed across issuers.
    return rows


def _snapshot_date(as_of: str) -> date:
    return datetime.fromisoformat(as_of).date()


def market_formula_rows(
    facts: FactsPort,
    ranking: RankingPort,
    issuers: list[str],
    metric: str,
    *,
    report_date: date | None = None,
) -> list[TableRow]:
    """P/E: the snapshot's market cap over the trailing year's net income (ADR 0008).

    The snapshot holds one market cap, taken at its as_of date, so the ratio is
    given only for each company's latest trailing year; a past period gets
    ``LATEST_PERIOD_ONLY`` rather than today's price over old earnings.
    """
    snapshot_day = _snapshot_date(ranking.snapshot_as_of())
    source = ranking.snapshot_source()
    earnings_metric = FORMULA_COMPONENTS[metric][1]

    def fetch(issuer: str) -> tuple[FinancialFact, FinancialFact] | Exception:
        try:
            latest = facts.get_financials(issuer, earnings_metric)
            earnings = (
                latest
                if report_date is None
                else facts.get_financials(issuer, earnings_metric, report_date=report_date)
            )
        except (*_COMPANY_FAILURES, PerShareNotDerivableError) as exc:
            return exc
        return latest, earnings

    members = {issuer: _snapshot_member(ranking, issuer) for issuer in issuers}
    in_snapshot = [issuer for issuer, (member, _) in members.items() if member is not None]
    fetched_by_issuer = dict(zip(in_snapshot, map_in_order(fetch, in_snapshot), strict=True))
    rows: list[TableRow] = []
    seen_ciks: set[str] = set()
    for issuer in issuers:
        member, reason = members[issuer]
        if member is None:
            rows.append(_compare_unresolved_row(issuer, metric, reason, report_date=report_date))
            continue
        fetched = fetched_by_issuer[issuer]
        if isinstance(fetched, Exception):
            rows.append(
                _compare_unresolved_row(
                    issuer, metric, reason_for(fetched), report_date=report_date
                )
            )
            continue
        latest, earnings = fetched
        if member.cik in seen_ciks:
            continue
        seen_ciks.add(member.cik)
        market_cap = ComponentProvenance(
            metric="market_cap",
            value=member.market_cap,
            start_date=snapshot_day,
            end_date=snapshot_day,
            form="",
            accession_number="",
            taxonomy="",
            concept="",
            source_url="",
            source=source,
        )
        components = [market_cap, _provenance_from_fact(earnings, earnings_metric)]
        period = {"start_date": earnings.start_date, "end_date": earnings.end_date}
        if earnings.end_date != latest.end_date:
            rows.append(
                _compare_row(
                    earnings, metric, components=components, reason=LATEST_PERIOD_ONLY, **period
                )
            )
            continue
        if earnings.value <= 0:
            rows.append(
                _compare_row(
                    earnings, metric, components=components, reason=NOT_MEANINGFUL, **period
                )
            )
            continue
        rows.append(
            _compare_row(
                earnings,
                metric,
                value=member.market_cap / earnings.value,
                components=components,
                newer_filing_end=earnings.newer_filing_end,
                **period,
            )
        )
    return rows


def periods_differ(rows: list[TableRow]) -> bool:
    """Whether the valued rows cover different fiscal quarters."""
    periods = {(row.start_date, row.end_date) for row in rows if row.value is not None}
    return not _same_fiscal_period(periods)


def _rank_and_lookup_row(
    company: UniverseCompany, index: int, metric: str, reason: str
) -> TableRow:
    return TableRow(
        company_name=company.name,
        ticker=company.ticker,
        cik=company.cik,
        metric=metric,
        rank=index,
        reason=reason,
        market_cap=company.market_cap,
    )


def _with_rank_identity(row: TableRow, company: UniverseCompany, index: int) -> TableRow:
    return row.model_copy(
        update={
            "company_name": company.name,
            "ticker": company.ticker,
            "cik": company.cik,
            "rank": index,
            "market_cap": company.market_cap,
        }
    )


def rank_and_lookup_task(task: CompiledTask, runtime: Runtime) -> TurnResult:
    """An industry's ranked members, each with one metric's latest quarter."""
    ranked = _ranked_table(task, runtime, Intent.RANK_AND_LOOKUP)
    if isinstance(ranked, TurnResult):
        return ranked
    table, trace = ranked
    metric = _task_metric(task)

    def member_row(ranked_member: tuple[int, Any]) -> tuple[TableRow, list[ToolTrace]]:
        index, company = ranked_member
        if metric in SNAPSHOT_METRICS:
            return _snapshot_row(company, metric, rank=index), []
        if metric in FORMULA_COMPONENTS:
            partial = _metrics_turn(Intent.RANK_AND_LOOKUP, [company.cik], metric, runtime)
            return _with_rank_identity(partial.table_rows[0], company, index), partial.tool_traces
        args = {"company": company.cik, "metric": metric}
        try:
            fact = runtime.facts.get_financials(company.cik, metric)
        except _COMPANY_FAILURES as exc:
            row = _rank_and_lookup_row(company, index, metric, reason_for(exc))
            return row, [ToolTrace(tool="get_financials", args=args)]
        return _with_rank_identity(_table_row_from_fact(fact), company, index), [
            ToolTrace(
                tool="get_financials",
                args=args,
                provenance=_lookup_provenance(fact),
            )
        ]

    # The members' facts are fetched at once; rows and traces keep rank order.
    built = map_in_order(member_row, list(enumerate(table.companies, start=1)))
    rows = [row for row, _ in built]
    traces = [trace]
    traces.extend(member_trace for _, member_traces in built for member_trace in member_traces)
    return TurnResult(
        intent=Intent.RANK_AND_LOOKUP,
        tool_traces=traces,
        renderer=RendererKind.TABLE,
        table_rows=rows,
        snapshot_as_of=table.as_of,
    )


def _compare_components_provenance(rows: list[TableRow]) -> dict[str, Any]:
    return {
        "components": [
            {"cik": row.cik, **component.model_dump(mode="json")}
            for row in rows
            for component in row.components
        ]
    }


def _metrics_turn(
    intent: Intent,
    issuers: list[str],
    metric: str,
    runtime: Runtime,
    *,
    report_date: date | None = None,
) -> TurnResult:
    if metric in SNAPSHOT_METRICS:
        return _snapshot_metrics_turn(intent, issuers, metric, runtime)
    if metric in MARKET_FORMULAS:
        if runtime.ranking is None:
            raise RuntimeError(f"{metric} requires a ranking adapter for market cap")
        rows = market_formula_rows(
            runtime.facts, runtime.ranking, issuers, metric, report_date=report_date
        )
    else:
        rows = compare_metrics(runtime.facts, issuers, metric, report_date=report_date)
    args: dict[str, Any] = {"issuers": issuers, "metric": metric}
    if report_date is not None:
        args["report_date"] = report_date.isoformat()
    return TurnResult(
        intent=intent,
        tool_traces=[
            ToolTrace(
                tool="compare_metrics",
                args=args,
                provenance=_compare_components_provenance(rows),
            )
        ],
        renderer=RendererKind.TABLE,
        table_rows=rows,
        banners=[PERIODS_DIFFER_BANNER] if periods_differ(rows) else [],
    )


def _snapshot_row(member: Any, metric: str, **kwargs: Any) -> TableRow:
    value = getattr(member, metric, None)
    return TableRow(
        company_name=member.name,
        ticker=member.ticker,
        cik=member.cik,
        metric=metric,
        value=value,
        currency="USD",
        reason=None if value is not None else MISSING_FACT,
        **kwargs,
    )


def is_cik(issuer: str) -> bool:
    """Whether a task names a company by CIK: one the spec resolved."""
    return len(issuer) == 10 and issuer.isdigit()


def _snapshot_member(ranking: RankingPort, issuer: str) -> tuple[Any | None, str]:
    """The snapshot's company for ``issuer``, or none and why the row has none.

    A company the spec resolved by CIK but the snapshot leaves out is not in the
    snapshot; a name neither knows is not found.
    """
    try:
        return ranking.lookup_member(issuer), ""
    except CompanyNotFoundError:
        return None, NOT_IN_SNAPSHOT if is_cik(issuer) else COMPANY_NOT_FOUND
    except AmbiguousCompanyError as exc:
        return None, reason_for(exc)


def snapshot_compare_rows(
    ranking: RankingPort, issuers: list[str], metric: str
) -> list[TableRow]:
    rows: list[TableRow] = []
    seen_ciks: set[str] = set()
    for issuer in issuers:
        member, reason = _snapshot_member(ranking, issuer)
        if member is None:
            rows.append(_compare_unresolved_row(issuer, metric, reason))
            continue
        if member.cik in seen_ciks:
            continue
        seen_ciks.add(member.cik)
        rows.append(_snapshot_row(member, metric))
    return rows


def _snapshot_metrics_turn(
    intent: Intent, issuers: list[str], metric: str, runtime: Runtime
) -> TurnResult:
    if runtime.ranking is None:
        raise RuntimeError(f"{intent.value} snapshot metric requires a ranking adapter")
    if intent is Intent.LOOKUP and len(issuers) == 1 and not is_cik(issuers[0]):
        # A name SEC does not know either: the lookup says so in words.
        try:
            member = runtime.ranking.lookup_member(issuers[0])
        except (CompanyNotFoundError, AmbiguousCompanyError) as exc:
            return TurnResult(
                intent=intent,
                tool_traces=[],
                renderer=RendererKind.REFUSE,
                message=str(exc),
                refusal=refusal_from_error(exc),
            )
        rows = [_snapshot_row(member, metric)]
    else:
        rows = snapshot_compare_rows(runtime.ranking, issuers, metric)
    as_of = runtime.ranking.snapshot_as_of()
    return TurnResult(
        intent=intent,
        tool_traces=[
            ToolTrace(
                tool="compare_metrics",
                args={"issuers": issuers, "metric": metric},
                provenance={
                    "snapshot_as_of": as_of,
                    "source": runtime.ranking.snapshot_source(),
                },
            )
        ],
        renderer=RendererKind.TABLE,
        table_rows=rows,
        snapshot_as_of=as_of,
    )


def _task_metric(task: CompiledTask) -> str:
    if task.metric is None:
        raise ValueError(f"a {task.kind} task names a metric")
    return task.metric


def compare_task(task: CompiledTask, runtime: Runtime) -> TurnResult:
    """One metric for several companies, at one report date or each one's latest."""
    return _metrics_turn(
        Intent.COMPARE,
        list(task.issuers),
        _task_metric(task),
        runtime,
        report_date=task.report_date,
    )


def lookup_task(task: CompiledTask, runtime: Runtime) -> TurnResult:
    """One company's metric, at one report date or its latest quarter."""
    company = task.issuers[0]
    metric = _task_metric(task)
    report_date = task.report_date
    if metric in FORMULA_COMPONENTS:
        return _metrics_turn(Intent.LOOKUP, [company], metric, runtime, report_date=report_date)
    if metric in SNAPSHOT_METRICS:
        return _snapshot_metrics_turn(Intent.LOOKUP, [company], metric, runtime)
    args: dict[str, Any] = {"company": company, "metric": metric}
    if report_date is not None:
        args["report_date"] = report_date.isoformat()
    try:
        fact = runtime.facts.get_financials(company, metric, report_date=report_date)
    except _LOOKUP_FAILURES as exc:
        provenance = (
            {}
            if isinstance(exc, PerShareNotDerivableError)
            else {
                "error": {
                    "code": exc.code,
                    "message": str(exc),
                    "details": exc.details,
                }
            }
        )
        return TurnResult(
            intent=Intent.LOOKUP,
            tool_traces=[
                ToolTrace(
                    tool="get_financials",
                    args=args,
                    provenance=provenance,
                )
            ],
            renderer=RendererKind.TABLE,
            table_rows=[
                TableRow(
                    company_name=company,
                    ticker="",
                    cik="",
                    metric=metric,
                    end_date=report_date,
                    reason=reason_for(exc),
                )
            ],
            message=str(exc),
            refusal=refusal_from_error(exc),
        )
    return TurnResult(
        intent=Intent.LOOKUP,
        tool_traces=[
            ToolTrace(
                tool="get_financials",
                args=args,
                provenance=_lookup_provenance(fact),
            )
        ],
        renderer=RendererKind.TABLE,
        table_rows=[_table_row_from_fact(fact)],
    )


def run_turn(query: str, runtime: Runtime) -> TurnResult:
    """Compatibility wrapper: one ephemeral conversation thread → TurnResult."""
    from financial_analyst_agent.conversation import run_conversation_turn
    from financial_analyst_agent.thread_store import EphemeralThreadStore

    return run_conversation_turn(
        "ephemeral",
        query,
        runtime,
        store=EphemeralThreadStore(),
    ).result
