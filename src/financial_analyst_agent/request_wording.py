"""The analyst's words, read: metrics, named periods, windows, comparison bases, edits.

One grammar for whichever planner proposed the analysis (ADR 0010): what a
question names, what period it asks about, what a change is measured against,
and how a follow-up edits the analysis on screen. Nothing here fetches.
"""

from __future__ import annotations

import re
from typing import Any, Literal

from financial_analyst_agent.contracts import (
    ALLOWED_METRICS,
    ComparisonBase,
    Intent,
    RendererKind,
    TurnResult,
    refuse_unknown_metric,
)
from financial_analyst_agent.graph.analysis_spec import (
    MAX_QUARTERS_ASKED,
    AnalysisSpec,
    PeriodSelection,
    SpecPatch,
)
from financial_analyst_agent.guide import short_name
from financial_analyst_agent.issuer_index import CompanyNames, word_uses
from financial_analyst_agent.period_selection import LATEST, YEAR_BASE, WindowReading, Words, read
from financial_analyst_agent.services.metric_catalog import (
    metric_phrases,
    resolve_metric_phrase,
    segment_companies,
)

_ADD_EDIT = re.compile(
    r"^\s*(?:now\s+)?(?:also\s+)?(?:add|include)\s+(.+?)\s*$",
    re.IGNORECASE,
)


# Words around the companies of an edit: "include Oracle too", "add Lilly as well".
_EDIT_FILLER = re.compile(
    r"\b(?:too|as well|also|please|pls|as a peer|in there"
    r"|to (?:the|this) (?:table|list|comparison|chart|analysis))\b",
    re.IGNORECASE,
)


# "Oracle too", "and Bank of America as well?": the companies join the analysis.
_ALSO_EDIT = re.compile(
    r"^\s*(?:and\s+|plus\s+)?(?:also\s+)?(?P<span>.+?)\s+(?:too|as well)\s*[?.!]*\s*$"
    r"|^\s*(?:and|plus|also)\s+(?P<lead>.+?)\s*[?.!]*\s*$",
    re.IGNORECASE,
)


# "what about net income", "just revenue", "net income instead", "by revenue": what
# the follow-up names takes the place of what is on screen instead of joining it.
# One reading for both planners' edits (ADR 0010, ADR 0011).
_SWAP_CUE = re.compile(
    r"^\s*(?:what about|how about|and what about|same for|now|ok|okay)\b"
    r"|\binstead\b|^\s*(?:just|only)\b|^\s*by\b",
    re.IGNORECASE,
)
# "what about their net income" asks about the companies on screen: it adds.
_POSSESSIVE = re.compile(r"\b(?:their|its)\b", re.IGNORECASE)
# "what about Goldman?", "how about AMD", "same for Oracle": the named companies
# take the place of the ones on screen; the metrics and window stay.
_INSTEAD_EDIT = re.compile(
    r"^\s*(?:and\s+|ok(?:ay)?,?\s+|now\s+)?(?:(?:what|how)\s+about|same\s+(?:thing\s+)?(?:for|with))"
    r"\s+(?P<span>.+?)\s*[?.!]*\s*$",
    re.IGNORECASE,
)


# "drop", "remove", "take out": the words that take something off the screen.
_TAKE_AWAY = r"drop|remove|take\s+out"
_DROP_EDIT = re.compile(
    rf"^\s*(?:{_TAKE_AWAY}|without)\s+(.+?)\s*$",
    re.IGNORECASE,
)
# "year over year", "year-on-year", "YoY", "y/y": one comparison, however spelt.
YEAR_OVER_YEAR = r"year[\s-]*o(?:ver|n)[\s-]*year|yoy|y/y"
# "a year earlier", "the same quarter last year", "the year-earlier quarter": the
# base of a year-over-year change, named without the words.
YEAR_EARLIER = (
    r"(?:a|one) year (?:ago|earlier|before)"
    r"|the same (?:quarter|period) (?:last year|a year (?:ago|earlier|before)"
    r"|(?:of )?the (?:prior|previous) year)"
    r"|the year[\s-]+(?:earlier|ago) (?:quarter|period)"
)
# "remove year over year": the change goes, the quarters on screen stay. Read
# before the year-over-year wording, which would otherwise ask for it.
_DROP_COMPARISON = re.compile(
    rf"^\s*(?:{_TAKE_AWAY}|without|no|hide)\s+(?:the\s+)?"
    rf"(?:{YEAR_OVER_YEAR})(?:\s+(?:change|changes|growth|comparison|column))?"
    r"\s*[.!]?\s*$",
    re.IGNORECASE,
)


_SWAP_EDIT = re.compile(
    r"^\s*(?:use|swap)\s+(.+?)\s+instead of\s+(.+?)\s*$",
    re.IGNORECASE,
)


# "swap Merck for AbbVie", "replace revenue with net income": out, then in.
_SWAP_FOR_EDIT = re.compile(
    r"^\s*(?:swap|replace|switch|exchange|trade)\s+(?:out\s+)?(?P<out>.+?)\s+(?:for|with)\s+"
    r"(?P<in>.+?)\s*[.?!]*\s*$",
    re.IGNORECASE,
)


# "switch the metric to free cash flow", "show net margin instead": what takes
# the place of what is on screen.
_SWITCH_TO_EDIT = re.compile(
    r"^\s*(?:now\s+)?(?:switch|change|swap|turn)\s+(?:(?:the|that|this|it)\s+)?"
    r"(?:(?:metric|measure|figure|number|company|companies)\s+)?(?:to|into|over to)\s+"
    r"(?P<span>.+?)\s*[.?!]*\s*$"
    r"|^\s*(?:now\s+)?(?:show|use|make it|do|give me)\s+(?P<instead>.+?)\s+instead\s*[.?!]*\s*$",
    re.IGNORECASE,
)


_DROP_AND_ADD_EDIT = re.compile(
    rf"^\s*(?:{_TAKE_AWAY})\s+(.+?)\s*,?\s+(?:and\s+)?(?:add|include|show)\s+(.+?)\s*$",
    re.IGNORECASE,
)


YOY = re.compile(
    rf"\b(?:{YEAR_OVER_YEAR}|{YEAR_EARLIER}|show yoy|compare to last year"
    # "over the past year" alone is the year's quarters; "grew over the past year" is growth.
    r"|(?:from|since|vs\.?|versus) (?:a year ago|last year)"
    r"|grow(?:th|n|ing)?|grew|how (?:has|have|did) .+ change[d]?|trend(?:ing)?"
    r"|why did .+ (?:drop|fall|decline|rise|jump|increase|decrease|go (?:up|down)))\b",
    re.IGNORECASE,
)


_STANDALONE_LOOKUP = re.compile(
    r"^\s*what(?:'s| is| was)\b",
    re.IGNORECASE,
)


_STANDALONE_COMPARE = re.compile(
    r"^\s*compare\s+(?!to\b).+\band\b",
    re.IGNORECASE,
)


_COMPARE_TO_ISSUER = re.compile(
    r"^\s*compare\s+to\s+(.+?)\s*$",
    re.IGNORECASE,
)


# "next quarter" asks for a forecast; filings only report what has happened.
FORECAST = re.compile(
    r"\bnext\s+(?:quarter|year|fiscal\s+year|fy)\b|\bforecasts?\b|\bprojected\b|\bpredict",
    re.I,
)


# Wording that asks for year-over-year change only, not quarter-to-quarter too.
EXPLICIT_YOY = re.compile(
    rf"\b(?:{YEAR_OVER_YEAR}|{YEAR_EARLIER}"
    r"|(?:from|since|vs\.?|versus|compared? (?:to|with)) "
    r"(?:a year ago|last year|the (?:prior|previous) year))\b",
    re.IGNORECASE,
)


_SEQUENTIAL = re.compile(
    r"\b(?:sequential(?:ly)?|quarter[\s-]*(?:over|on)[\s-]*quarter|qoq"
    r"|(?:from|since|vs\.?|versus|than|compared? (?:to|with)) (?:the )?"
    r"(?:last|previous|prior|preceding) quarter)\b",
    re.IGNORECASE,
)


# "How much did revenue change?", "did it move?", "what drove the change in revenue?",
# "what caused revenue to fall?", "what led to the decline in revenue?": a change
# that may name no base.
_CHANGE = re.compile(
    r"\b(?:how (?:much )?)?(?:has|have|did) .+ (?:change|move)d?\b"
    r"|\bwhat(?:'s| is| was)? (?:drove|drives|driving|caused|causes|causing|explains"
    r"|explained|behind|led to|leads to|leading to|(?:the )?reasons? (?:for|behind))"
    r" the (?:change|move|movement|shift|swing|increase|decrease"
    r"|rise|fall|drop|decline|jump)s? in\b"
    r"|\bwhat(?:'s| is| was| has| had)? (?:caused|causes|causing|made|makes|making|led"
    r"|leads|leading|drove|drives|driving|pushed|pushes|pushing) .+? (?:to )?(?:change|move"
    r"|shift|swing|increase|decrease|rise|fall|drop|decline|jump|climb|slip|dip|shrink"
    r"|go (?:up|down))\b",
    re.IGNORECASE,
)


# Growth is year over year by convention: analysts and 10-Q MD&A compare a quarter
# with the same quarter a year before, which a season does not distort (ADR 0010).
GROWTH = re.compile(r"\b(?:grow(?:th|n|ing|s)?|grew|trend(?:s|ing)?)\b", re.IGNORECASE)


COMPARISON_CANDIDATES: tuple[ComparisonBase, ...] = ("year_over_year", "sequential")


COMPARISON_LABELS = (
    "The same quarter a year earlier (year over year)",
    "The quarter before (sequential)",
)


# Four quarters, each with the quarter a year before it.
_YOY_WINDOW = 8


WHY_CHANGE = re.compile(r"^\s*why\b", re.I)


# "Explain how a share buyback affects EPS", "how does a buyback affect EPS?",
# "what is free cash flow and why does it matter?": a general question about how
# something works, which no company's figure answers (README, general question).
_EXPLANATION = re.compile(
    r"^\W*(?:(?:please|can you|could you|would you)\s+)?explain\b"
    r"|\bhow (?:does|do|did|would|could|can|might|will|should) (?:a |an |the )?[\w'/&-]+"
    r"(?: [\w'/&-]+){0,3}? (?:affects?|impacts?|influences?|works?|matters?)\b"
    r"|\bhow (?:is|are|was|were) (?:a |an |the )?[\w'/&-]+(?: [\w'/&-]+){0,3}?"
    r" (?:calculated|computed|measured|defined|derived|determined|recogni[sz]ed|accounted"
    r"|reported)\b"
    r"|\bwhy (?:does|do|is|are|would|should|might|can) .+?\b(?:matters?|important)\b"
    r"|\bwhat (?:does|do) .+? mean\b",
    re.IGNORECASE,
)


# "What is EPS?", "what are earnings per share": the measure alone, with no
# article or possessive, asks what it is. "What's the EPS?" asks for a figure.
_WHAT_IS = re.compile(r"^\W*what(?:['’]s| is| are) (?P<measure>.+?)[\s?.!]*$", re.IGNORECASE)


# "How might AI change Apple's revenue?", "What if rates rise?": what could happen,
# which no filed figure answers, even when a company and a metric are named
# (README, general question). A request to the analyst ("How would you rank
# banks?"), a follow-up ("How would that look sequentially?", "What if we look
# at Microsoft?") and a comparison ("How would Apple's revenue compare ...") are not.
_SPECULATIVE = re.compile(
    r"\bhow (?:might|could|would) (?!(?:i|we|you|one|it|that|this|these|those|they)\b)"
    r"(?!.*\bcompare\b)"
    r"|\bwhat if (?!(?:i|we|you)\b)|\bwhat would happen\b",
    re.IGNORECASE,
)


def asks_speculatively(message: str) -> bool:
    """Whether the words ask what could happen: an explanation, marked as the
    model's, even about a named company's figure, whichever planner reads it."""
    return _SPECULATIVE.search(message) is not None


def asks_for_explanation(message: str) -> bool:
    """Whether the words ask how something works rather than for a figure.

    "Explain how a share buyback affects EPS" names a metric and no company, but
    it is a general question (intent explain), as "How might AI change banking?"
    is. "What is EPS?" asks what the measure is: an explanation too. "What's the
    EPS?" asks for a figure and names no company: it asks which company. The
    wording tells them apart, not the absence of a company alone.
    """
    if _EXPLANATION.search(message) is not None or asks_speculatively(message):
        return True
    asked = _WHAT_IS.match(message)
    return asked is not None and asked.group("measure").casefold() in metric_phrases()


# A "since" window is a window: at most as many quarters as any other (README).
MAX_SINCE_QUARTERS = MAX_QUARTERS_ASKED


# Wording that asks for numbers without naming a metric. Each maps to the
# metrics that answer it, so the window shows data instead of a refusal.
OVERVIEW_METRICS: tuple[str, ...] = (
    "revenue",
    "net_income",
    "gross_margin",
    "operating_margin",
    "net_margin",
)


_BIGGER = re.compile(r"\b(?:bigger|larger|biggest|largest|size)\b", re.IGNORECASE)


_PROFITABLE = re.compile(r"\b(?:more|most|less|least)?\s*profitab(?:le|ility)\b", re.IGNORECASE)


_GROWING = re.compile(
    r"\b(?:grow(?:ing|n|th)?|grew|changed?|trend(?:ing)?|doing over time)\b", re.IGNORECASE
)


# "How is Apple doing?", "the rundown on Apple", "how has Apple been performing":
# asking how a company is doing, in any of its words (README, overview row).
_OVERVIEW = re.compile(
    r"\b(?:overview|snapshot|summary|profile|financials|fundamentals|numbers|"
    r"key metrics|at a glance|tell me about|how (?:is|are|was|were|has|have)|how's|doing|"
    r"results|run-?down|quick (?:read|look|take)|perform(?:s|ed|ing|ance)?)\b",
    re.IGNORECASE,
)


_OVERVIEW_MAX_WORDS = 3


# A planner's metric for "Compare Nvidia and AMD": companies and nothing else.
OVERVIEW_PLAN = "overview"


def implied_metrics(message: str, *, short: bool = True) -> tuple[str, ...]:
    """Metrics a question implies when it names none ("Which is bigger?").

    ``short`` lets a message of a few words ("Nvidia") ask for the overview; a
    question naming a word the catalog lacks ("Apple turnover") turns it off.
    """
    if _BIGGER.search(message):
        return ("market_cap", "revenue")
    if _PROFITABLE.search(message):
        return ("net_income", "net_margin")
    if _GROWING.search(message):
        return ("revenue",)
    if _OVERVIEW.search(message) or (short and len(message.split()) <= _OVERVIEW_MAX_WORDS):
        return OVERVIEW_METRICS
    return ()


def _names_companies(patch: SpecPatch) -> bool:
    return (
        patch.ranked_request is None
        and bool(patch.add_companies)
        and all(company and company != "unknown" for company in patch.add_companies)
    )


def _names_new_subject(patch: SpecPatch, spec: AnalysisSpec, message: str = "") -> bool:
    """Whether the patch names a company or ranking the current analysis lacks.

    A model planner often repeats the current company in a follow-up's plan, so
    naming a company already on screen is not a new question. Naming only some
    of the companies on screen, in the analyst's own words ("Walmart revenue
    over the last four quarters" after Costco and Walmart), is one.
    """
    if patch.ranked_request is not None:
        return spec.constituents is None or (
            patch.ranked_request.industry.casefold() != spec.constituents.industry.casefold()
        )
    if not _names_companies(patch):
        return False
    known = {
        label.casefold()
        for company in spec.companies
        for label in (company.query, company.name, company.ticker)
    }
    if any(company.casefold() not in known for company in patch.add_companies):
        return True
    return patch.mode == "replace" and _narrows_to_named(patch, spec, message)


def _narrows_to_named(patch: SpecPatch, spec: AnalysisSpec, message: str) -> bool:
    """Whether the analyst named fewer of the companies on screen than are shown."""
    wanted = {company.casefold() for company in patch.add_companies}
    kept = [
        company
        for company in spec.companies
        if wanted & {company.query.casefold(), company.name.casefold(), company.ticker.casefold()}
    ]
    if not kept or len(kept) >= len(spec.companies):
        return False
    words = f" {normalize_words(message)} "
    return all(
        f" {normalize_words(short_name(company.name))} " in words
        or f" {company.ticker.casefold()} " in words
        for company in kept
        if company.name or company.ticker
    )


def normalize_words(text: str) -> str:
    return " ".join(re.sub(r"[^a-z0-9&]+", " ", text.casefold()).split())


def bind_metrics_from_message(
    patch: SpecPatch, message: str, *, intent: Intent | None = None
) -> tuple[SpecPatch, TurnResult | None]:
    """Resolve metrics from the analyst's wording; never trust a model slug alone."""
    resolved = resolve_metric_phrase(message)
    effective_intent = intent or Intent.LOOKUP
    if resolved.kind == "ambiguous":
        return patch, TurnResult(
            intent=effective_intent,
            tool_traces=[],
            renderer=RendererKind.CLARIFY,
            candidates=resolved.candidates,
            clarify_kind="ambiguous_metric",
        )
    phrased = resolved.unique_metrics
    if phrased:
        order_by = (
            phrased[0]
            if patch.mode == "extend" and "order_by_metric" in patch.add_operations
            else patch.set_order_by
        )
        if patch.mode == "replace":
            return patch.model_copy(
                update={"add_metrics": phrased, "set_order_by": order_by}
            ), None
        # Extend: add phrased metrics except those this patch is removing.
        to_add = tuple(m for m in phrased if m not in patch.remove_metrics)
        metrics = tuple(dict.fromkeys([*patch.add_metrics, *to_add]))
        return patch.model_copy(
            update={"add_metrics": metrics, "set_order_by": order_by}
        ), None
    # No metric phrase in the analyst's wording.
    if patch.mode == "extend":
        return patch, None
    guessed = [metric for metric in patch.add_metrics if metric in ALLOWED_METRICS]
    # The planner names a word the catalog lacks ("turnover"): refuse with it
    # rather than answer a short question with the overview.
    unknown_word = any(
        metric not in ALLOWED_METRICS and metric not in ("unknown", OVERVIEW_PLAN)
        for metric in patch.add_metrics
    )
    # A measure the catalog lacks by name ("stock performance") is refused, not
    # read as the overview its words ("performance") or its length would imply.
    implied = (
        implied_metrics(message, short=not unknown_word)
        if _names_companies(patch) and resolved.term is None
        else ()
    )
    if not set(guessed) <= set(implied):
        # A slug the wording does not imply is the planner's alone. One it does
        # ("How fast is Broadcom growing?" as revenue) is the wording's reading.
        implied = ()
    if not implied and _names_companies(patch) and OVERVIEW_PLAN in patch.add_metrics:
        implied = OVERVIEW_METRICS
    if implied:
        return patch.model_copy(update={"add_metrics": implied}), None
    if patch.ranked_request is not None and not patch.add_metrics:
        return patch, None
    # Replace-mode metric question with an unknown phrase: refuse with the full catalog
    # even when the planner guessed a catalog slug.
    term = "unknown"
    if resolved.term is not None:
        # The analyst's own measure, as the catalog lists it ("debt-to-equity").
        term = resolved.term
    elif patch.add_metrics:
        candidate = patch.add_metrics[0]
        if candidate not in ALLOWED_METRICS:
            term = candidate
    return patch, refuse_unknown_metric(effective_intent, term)


def unique_metrics_from_phrase(text: str) -> tuple[str, ...]:
    return resolve_metric_phrase(text).unique_metrics


def _companies_named_in(companies: tuple[str, ...], text: str) -> tuple[str, ...]:
    """The planner's companies that ``text`` names in so many words."""
    words = f" {normalize_words(text)} "
    return tuple(
        company for company in companies if f" {normalize_words(company)} " in words
    )


def _without_word_uses(
    patch: SpecPatch, message: str, index: CompanyNames | None
) -> SpecPatch:
    """A company proposed from an everyday word used as the word is dropped.

    "Palantir operating income, intel aside" is Palantir's, whichever planner
    added Intel; "Intel and Palantir operating income" names both (ADR 0010).
    """
    used = word_uses(message)
    if index is None or not used or not patch.add_companies:
        return patch
    word_companies = {
        query
        for word in used
        for query in (index.named(word), index.named(word.removesuffix("s")))
        if query is not None
    }
    named = {mention.query for mention in index.find(message)}
    kept = tuple(
        company
        for company in patch.add_companies
        if (query := index.named(company)) is None
        or query not in word_companies
        or query in named
    )
    if kept == patch.add_companies:
        return patch
    return patch.model_copy(update={"add_companies": kept})


def _with_segment_companies(patch: SpecPatch, message: str) -> SpecPatch:
    """A question that names no company names the one its segment belongs to.

    "iPhone sales" is Apple's revenue, whichever planner proposed no company;
    "Microsoft iPhone sales" names Microsoft, and a ranking names a group.
    """
    if patch.add_companies or patch.ranked_request is not None:
        return patch
    companies = segment_companies(message)
    if not companies:
        return patch
    return patch.model_copy(update={"add_companies": companies})


def _company_tokens(text: str) -> tuple[str, ...]:
    text = _EDIT_FILLER.sub(" ", text)
    parts = re.split(r"\s+and\s+|,\s*", text, flags=re.IGNORECASE)
    return tuple(part.strip(" .,?!") for part in parts if part.strip(" .,?!"))


def _companies_in(
    text: str, patch: SpecPatch, index: CompanyNames | None
) -> tuple[str, ...]:
    """The companies an edit's words name, read as the planner reads a question.

    "Oracle too" is Oracle and "Goldman" is GS: the issuer index reads the
    words, so filler never becomes a company. Words it cannot place fall back
    to the planner's own companies, then to the words themselves, which the
    resolver then reports as not found.
    """
    found = _named_by_index(text, patch, index)
    if found:
        return found
    named = _companies_named_in(patch.add_companies, text)
    if named:
        return named
    if _names_companies(patch):
        return patch.add_companies
    return _company_tokens(text)


def comparison_asked(message: str) -> ComparisonBase | Literal["unclear"] | None:
    """What a change the message asks about is measured against.

    "year_over_year" or "sequential" where the wording says (growth is year
    over year by convention), "unclear" where it asks about a change but not
    against what ("why did revenue drop?"), and None where it asks for no change.
    """
    if _SEQUENTIAL.search(message) is not None:
        return "sequential"
    if YOY.search(message) is None and not _asks_change(message):
        return None
    if (
        EXPLICIT_YOY.search(message) is not None
        or GROWTH.search(message) is not None
        or read(message).names_a_window
    ):
        return "year_over_year"
    return "unclear"


# "news", "headlines": news asked for by name.
_NEWS_BY_NAME = re.compile(r"\bnews\b|\bheadlines?\b", re.IGNORECASE)


def asks_change_without_base(message: str) -> bool:
    """Whether the words ask about a change but not against what, and not for news.

    "Why did NVIDIA's revenue drop?" is asked against what (README, a change with
    no base), whichever intent a planner proposed; "What's the news on why
    NVIDIA's revenue dropped?" asks for news by name.
    """
    return comparison_asked(message) == "unclear" and _NEWS_BY_NAME.search(message) is None


# "quarter over quarter instead of year over year": one base named to rule the
# other out, not both asked for.
_ONE_NOT_THE_OTHER = re.compile(r"\b(?:instead of|rather than|not)\b", re.IGNORECASE)


def names_both_bases(message: str) -> bool:
    """Whether the wording names both comparison bases ("sequentially or versus
    last year", "quarter over quarter and year over year"), wherever they sit in
    the question: both changes are shown (README's changes row).
    """
    return (
        _SEQUENTIAL.search(message) is not None
        and EXPLICIT_YOY.search(message) is not None
        and _ONE_NOT_THE_OTHER.search(message) is None
    )


def _asks_change(message: str) -> bool:
    """A change asked about in words that name no base ("how much did revenue change?").

    Over a named window it is year over year over that window; with no window it
    is asked about. Over named periods alone, the quarters themselves are the
    answer, so no change is asked.
    """
    words = read(message)
    return _CHANGE.search(message) is not None and (
        words.names_a_window or len(words.named) <= 1
    )


def bind_periods_from_message(
    patch: SpecPatch, message: str, *, window: WindowReading | None = None
) -> SpecPatch:
    """Period windows come from the analyst's wording, not a model slug."""
    words = read(message, stored=window)
    window = words.reading
    if drops_comparison(message):
        return patch.model_copy(
            update={
                "set_periods": None,
                "add_operations": tuple(
                    operation
                    for operation in patch.add_operations
                    if operation not in _CHANGE_OPERATIONS
                ),
                "remove_operations": tuple(
                    dict.fromkeys([*patch.remove_operations, *_CHANGE_OPERATIONS])
                ),
            }
        )
    asked = window.asked_quarters if window.counted_window else None
    base = comparison_asked(message)
    # "How much did revenue change?" shows the quarters "how has it changed?" does.
    yoy = YOY.search(message) is not None or _asks_change(message)
    # "quarter over quarter" is a window of sequential changes.
    sequential = _SEQUENTIAL.search(message) is not None
    # "sequentially or versus last year": both changes, each quarter's year over
    # year from its own comparative beside its change on the quarter before.
    both = names_both_bases(message)
    if asked is None and (yoy or sequential) and YEAR_BASE.search(message) is not None:
        # "How did EBITDA change over the past year?": a change over a year named
        # with no count is over that year's four quarters, as "growth over the
        # last 4 quarters" is, not the growth default (README's growth row).
        asked = 4
    named = words.named
    if not named and asked is None and window.since_year is not None:
        # Every filed quarter since that 1 January, at most the window cap: the
        # quarters are chosen where the report dates are listed, as a named
        # period's are, not counted from today. A change over it is over those
        # quarters: year over year from each one's own comparative (ADR 0009),
        # or on the quarter before, where the oldest has none inside the window.
        operations = _change_operations(
            patch.add_operations, across=yoy or sequential, base=base, both=both
        )
        return patch.model_copy(
            update={
                "set_periods": PeriodSelection(
                    kind="last_n_quarters",
                    count=MAX_SINCE_QUARTERS,
                    since_year=window.since_year,
                    since_fiscal=window.since_fiscal,
                ),
                "add_operations": operations,
            }
        )
    if not named and asked is None and not yoy and (
        window.trailing_year or window.year_of_quarters
    ):
        # "TTM revenue": show the four quarters that make up the trailing year.
        return patch.model_copy(
            update={"set_periods": PeriodSelection(kind="last_n_quarters", count=4)}
        )
    if named:
        # A change on a named period is read as on a window: the named quarters,
        # each with its year-over-year change from its own filing's comparative
        # (ADR 0009), or with its change on the quarter before, read but not shown.
        quarters = [period for period in named if period.quarter is not None]
        operations = _change_operations(
            patch.add_operations,
            across=yoy or sequential or len(quarters) >= 2,
            base=base,
            both=both,
        )
        return patch.model_copy(
            update={
                "set_periods": PeriodSelection(
                    kind="named", named=named, company_base_dates=() if sequential else None
                ),
                "add_operations": operations,
            }
        )
    if asked is None and not yoy and not sequential:
        if LATEST.search(message) is not None:
            # "latest" after a year-over-year window: one quarter, no change chip.
            return patch.model_copy(
                update={
                    "set_periods": PeriodSelection(),
                    "remove_operations": (*patch.remove_operations, *_CHANGE_OPERATIONS),
                }
            )
        return patch
    # Growth is year over year unless the analyst says sequential (ADR 0010); a
    # change that names no base is asked about before the analysis runs.
    explicit_yoy = base == "year_over_year"
    operations = _change_operations(
        patch.add_operations, across=yoy or sequential, base=base, both=both
    )
    if asked is None and patch.set_periods is not None:
        return patch.model_copy(update={"add_operations": operations})
    count = asked if asked is not None else 5
    if sequential and asked is not None:
        # Each quarter asked for is shown with its change on the quarter before,
        # so the window reads one quarter more than it shows.
        return patch.model_copy(
            update={
                "set_periods": PeriodSelection(
                    kind="last_n_quarters", count=asked + 1, asked=asked
                ),
                "add_operations": operations,
            }
        )
    if (yoy or sequential) and count < 5 and not (explicit_yoy and asked is not None):
        # Only a change that names no base gets here with a window under 5 ("how did
        # revenue change last quarter?"): it is read over 5 until the analyst says
        # against what. A change over a window of two or more quarters is year over
        # year over it, and a sequential window returned above.
        count = 5
    if explicit_yoy and EXPLICIT_YOY.search(message) is not None and asked is None:
        # "Year over year" with no window: two years of quarters. A window the
        # analyst names is shown as asked; each quarter's base is the comparative
        # its own filing reports (ADR 0009), so no extra quarters are needed.
        count = _YOY_WINDOW
    return patch.model_copy(
        update={
            "set_periods": PeriodSelection(kind="last_n_quarters", count=count),
            "add_operations": operations,
        }
    )


def _change_operations(
    operations: tuple[str, ...],
    *,
    across: bool,
    base: ComparisonBase | Literal["unclear"] | None,
    both: bool,
) -> tuple[str, ...]:
    """The patch's operations with the change the words ask for: across the
    quarters, year over year where that base is named, and both bases where both are."""
    if across and "across_periods" not in operations:
        operations = (*operations, "across_periods")
    if base == "year_over_year" and "year_over_year" not in operations:
        operations = (*operations, "year_over_year")
    if both:
        operations = _with_operations(operations, "year_over_year", "sequential")
    return operations


def _with_operations(operations: tuple[str, ...], *names: str) -> tuple[str, ...]:
    """The operations with each name appended once."""
    return tuple(dict.fromkeys([*operations, *names]))


def _extend(patch: SpecPatch, **fields: Any) -> SpecPatch:
    """The patch as an edit of the current analysis rather than a new ranking."""
    return patch.model_copy(update={"mode": "extend", "ranked_request": None, **fields})


_CHANGE_OPERATIONS = ("across_periods", "year_over_year", "sequential")

# "lowest first", "smallest first", "ascending": the same companies, ordered from the
# lowest value of the metric. "Largest first" and "descending" turn it back.
ASCENDING = re.compile(
    r"\b(?:lowest|smallest|least|low|small)\s+first\b|\bascending\b"
    r"|\bfrom\s+the\s+(?:lowest|smallest|bottom)\b|\blow(?:est)?\s+to\s+high(?:est)?\b"
    r"|\bin\s+(?:increasing|rising)\s+order\b",
    re.IGNORECASE,
)
DESCENDING = re.compile(
    r"\b(?:largest|biggest|highest|most|high|big)\s+first\b|\bdescending\b"
    r"|\bfrom\s+the\s+(?:largest|biggest|highest|top)\b|\bhigh(?:est)?\s+to\s+low(?:est)?\b",
    re.IGNORECASE,
)


def order_direction_asked(message: str) -> bool | None:
    """True for "lowest first", False for "largest first", None when the words say neither."""
    if ASCENDING.search(message):
        return True
    if DESCENDING.search(message):
        return False
    return None


LOWEST_FIRST = "lowest_first"


def bind_order_from_message(patch: SpecPatch, message: str) -> SpecPatch:
    """The order's direction comes from the analyst's words, whichever planner proposed.

    "Lowest first" adds the operation and "largest first" removes it. It holds
    across edits until another order is named: "sort by revenue" after "lowest
    first" starts again from the largest.
    """
    ascending = order_direction_asked(message)
    if ascending is None and patch.set_order_by is None:
        return patch
    if ascending:
        if LOWEST_FIRST in patch.add_operations:
            return patch
        return patch.model_copy(update={"add_operations": (*patch.add_operations, LOWEST_FIRST)})
    if LOWEST_FIRST in patch.remove_operations:
        return patch
    return patch.model_copy(
        update={
            "add_operations": tuple(op for op in patch.add_operations if op != LOWEST_FIRST),
            "remove_operations": (*patch.remove_operations, LOWEST_FIRST),
        }
    )


def drops_comparison(message: str) -> bool:
    """ "remove year over year", "no YoY": take the change away, keep the quarters."""
    return _DROP_COMPARISON.match(message) is not None


def asks_to_swap(message: str) -> bool:
    """Whether a follow-up puts what it names in place of what is on screen."""
    return _SWAP_CUE.search(message) is not None


def is_removal(message: str) -> bool:
    """ "drop revenue", "take out Apple", "without margins": an edit that takes away."""
    return _DROP_EDIT.match(message.strip()) is not None


def takes_out_or_swaps(message: str) -> bool:
    """ "take out Apple", "swap Merck for AbbVie": an edit whose words say what goes."""
    return is_removal(message) or _swap_pair(message.strip()) is not None


def _swap_pair(message: str) -> tuple[str, str] | None:
    """(incoming, outgoing) of "use X instead of Y" or "remove Y add X"."""
    swapped = _SWAP_EDIT.match(message)
    if swapped is not None:
        return swapped.group(1).strip(), swapped.group(2).strip()
    swapped = _SWAP_FOR_EDIT.match(message)
    if swapped is not None:
        return swapped.group("in").strip(" .,"), swapped.group("out").strip(" .,")
    # "remove revenue add net income" is a swap, not the removal of both.
    both = _DROP_AND_ADD_EDIT.match(message)
    if both is not None:
        return both.group(2).strip(" .,"), both.group(1).strip(" .,")
    return None


def refine_patch_from_message(
    patch: SpecPatch,
    message: str,
    current_spec: AnalysisSpec | None,
    *,
    index: CompanyNames | None = None,
    words: Words | None = None,
) -> SpecPatch:
    """Turn follow-up wording into an extend patch when the planner still replaced.

    The edit's own words decide, whichever planner proposed the patch: "add",
    "include", "too" and "as well" add companies; "what about", "how about"
    and "same for" put them in place of the ones on screen. ``index`` reads
    which companies the words name; ``words`` is the message's period reading,
    read here when the caller holds none.
    """
    if words is None:
        words = read(message)
    patch = _without_word_uses(patch, message, index)
    patch = bind_periods_from_message(patch, message, window=words.reading)
    if current_spec is None:
        return _with_segment_companies(patch, message)
    return _keep_window_for_change(
        _refine_against(patch, message, current_spec, index), message, current_spec, words
    )


def _keep_window_for_change(
    patch: SpecPatch, message: str, current_spec: AnalysisSpec, words: Words
) -> SpecPatch:
    """ "Show that year over year" and "sequential instead" keep the quarters on screen.

    With no window named, year over year shows 8 quarters and growth 5: the 8
    were four quarters with the year before each, the 5 four with the year-earlier
    base of the newest. Each quarter's base is now the comparative its own filing
    reports (ADR 0009), so a window the analyst already has needs no extra rows,
    nor does a named period, read as on a window. A sequential change reads the
    quarter before the oldest one shown as its base, without showing it: after a
    year-over-year view, "sequential instead" switches the change to that one
    and keeps the quarters, as "year over year instead" switches back (ADR 0010).
    """
    on_screen = current_spec.periods
    base = comparison_asked(message)
    if (
        patch.mode != "extend"
        or patch.set_periods is None
        or on_screen.kind == "latest_quarter"
        or (on_screen.kind == "last_n_quarters" and (on_screen.shown or 1) <= 1)
        or base not in ("year_over_year", "sequential")
        or words.reading.counted_window
        or words.reading.trailing_year
        or words.names_a_window
        or words.named
    ):
        return patch
    if names_both_bases(message):
        # "Sequentially or versus last year": both changes on the quarters shown.
        return _switch_to_sequential(patch, on_screen, both=True)
    if base == "sequential":
        return _switch_to_sequential(patch, on_screen)
    # Year over year alone: a sequential change asked beside it goes.
    removed = tuple(dict.fromkeys([*patch.remove_operations, "sequential"]))
    if on_screen.company_base_dates is not None:
        # The quarters before a quarter-over-quarter change's named ones are no
        # longer a base.
        return patch.model_copy(
            update={
                "set_periods": on_screen.model_copy(update={"company_base_dates": None}),
                "remove_operations": removed,
            }
        )
    return patch.model_copy(update={"set_periods": None, "remove_operations": removed})


def _switch_to_sequential(
    patch: SpecPatch, on_screen: PeriodSelection, *, both: bool = False
) -> SpecPatch:
    """The quarters on screen, each with its change on the quarter before.

    The year-over-year change goes, unless ``both`` were named ("sequentially or
    versus last year"), when it stays beside. A counted window reads one quarter
    more than it shows, the oldest quarter's base; a named period reads the
    quarter before each named quarter the same way; a "since" window keeps its
    quarters as listed, so its oldest shows no change.
    """
    if both:
        added = _with_operations(patch.add_operations, "year_over_year", "sequential")
        removed = patch.remove_operations
    else:
        bases = ("year_over_year", "sequential")
        added = tuple(op for op in patch.add_operations if op not in bases)
        removed = tuple(dict.fromkeys([*patch.remove_operations, *bases]))
    periods: PeriodSelection | None
    if on_screen.kind == "named":
        # Listed afresh, so each named quarter's base is listed with it.
        periods = PeriodSelection(kind="named", named=on_screen.named, company_base_dates=())
    elif on_screen.asked is not None or on_screen.since_year is not None:
        # Already read with its base, or every quarter since a year: unchanged.
        periods = None
    else:
        shown = on_screen.count or 1
        periods = PeriodSelection(kind="last_n_quarters", count=shown + 1, asked=shown)
    return patch.model_copy(
        update={"set_periods": periods, "add_operations": added, "remove_operations": removed}
    )


def _refine_against(
    patch: SpecPatch,
    message: str,
    current_spec: AnalysisSpec,
    index: CompanyNames | None,
) -> SpecPatch:
    """The follow-up's edit of the analysis on screen."""
    if drops_comparison(message):
        # Nothing else on screen changes: not a company called "year over year".
        return _extend(
            patch, add_companies=(), remove_companies=(), add_metrics=(), remove_metrics=()
        )

    stripped = message.strip()
    swap = _swap_pair(stripped)
    if swap is not None:
        incoming, outgoing = swap
        add_metrics = unique_metrics_from_phrase(incoming)
        remove_metrics = unique_metrics_from_phrase(outgoing)
        if add_metrics and remove_metrics:
            return _extend(
                patch,
                add_metrics=add_metrics,
                remove_metrics=remove_metrics,
                add_companies=(),
                remove_companies=(),
            )
        return _extend(
            patch,
            add_companies=(incoming,),
            remove_companies=(outgoing,),
            add_metrics=(),
        )

    switched = _SWITCH_TO_EDIT.match(stripped)
    if switched is not None:
        span = (switched.group("span") or switched.group("instead")).strip(" .,")
        metrics = unique_metrics_from_phrase(span)
        if metrics:
            return _metrics_in_place(patch, metrics, current_spec)

    metric_swap = _metric_swap(message, patch, current_spec, index)
    if metric_swap is not None:
        return metric_swap

    added = _ADD_EDIT.match(stripped)
    if added is not None:
        # "now add operating margin": adding never takes anything away.
        patch = patch.model_copy(update={"remove_metrics": (), "remove_companies": ()})
        token = added.group(1).strip(" .,")
        metrics = unique_metrics_from_phrase(token)
        # "add Google margin" adds Google as well as the margin.
        named = _companies_named_in(patch.add_companies, token)
        if metrics:
            return _extend(patch, add_metrics=metrics, add_companies=named)
        resolved = resolve_metric_phrase(token)
        if resolved.kind == "ambiguous":
            return _extend(patch, add_companies=named)
        if (
            patch.add_metrics
            and all(metric in ALLOWED_METRICS for metric in patch.add_metrics)
            and not patch.add_companies
        ):
            return _extend(patch, add_companies=())
        companies = _companies_in(token, patch, index)
        return _extend(patch, add_companies=companies, add_metrics=())

    companies_edit = _company_edit(stripped, patch, current_spec, index)
    if companies_edit is not None:
        return companies_edit

    dropped = _DROP_EDIT.match(stripped)
    if dropped is not None:
        token = dropped.group(1).strip(" .,")
        metrics = unique_metrics_from_phrase(token)
        if metrics:
            return _extend(patch, remove_metrics=metrics, add_metrics=(), add_companies=())
        resolved = resolve_metric_phrase(token)
        if resolved.kind == "ambiguous":
            return _extend(patch, add_companies=(), remove_companies=(), add_metrics=())
        companies = _companies_in(token, patch, index)
        if re.fullmatch(r"(?:both|them|all|all of them|everything|every company)", token, re.I):
            # "remove both": every company on screen, which the turn then says it cannot.
            companies = tuple(company.query for company in current_spec.companies)
        return _extend(patch, remove_companies=companies, add_metrics=(), add_companies=())

    compare_to = _COMPARE_TO_ISSUER.match(stripped)
    if compare_to is not None and YOY.search(message) is None:
        token = compare_to.group(1).strip(" .,")
        if token and not unique_metrics_from_phrase(token):
            return _extend(patch, add_companies=(token,), add_metrics=())

    # "What was it last quarter?" names nothing new: it is not a question of its own.
    standalone = (patch.ranked_request is not None or _names_companies(patch)) and (
        _STANDALONE_LOOKUP.search(stripped) is not None
        or _STANDALONE_COMPARE.search(stripped) is not None
    )
    # A period on its own ("for Q3 2024", "last 8 quarters") edits the current
    # analysis. One that names another company or ranking ("Microsoft TTM net
    # income") is a new question and keeps what it names.
    period_only = not _names_new_subject(patch, current_spec, message)
    if patch.set_periods is not None and patch.mode == "replace" and not standalone and period_only:
        return _extend(patch, add_companies=(), add_metrics=())
    if standalone and YOY.search(message) is None:
        return patch.model_copy(
            update={
                "mode": "replace",
                "remove_companies": (),
                "remove_metrics": (),
            }
        )
    return patch


def _metric_swap(
    message: str,
    patch: SpecPatch,
    current_spec: AnalysisSpec,
    index: CompanyNames | None,
) -> SpecPatch | None:
    """ "what about net income" after revenue: net income in revenue's place.

    Only where the follow-up names metrics and no company: "what about Microsoft
    net income" is a company edit, read by ``_company_edit``.
    """
    if not asks_to_swap(message) or _POSSESSIVE.search(message) is not None:
        return None
    if _ADD_EDIT.match(message.strip()) or _ALSO_EDIT.match(message.strip()):
        # "now add net income", "ok, net income too": adding never takes away.
        return None
    if not current_spec.metrics or not (
        current_spec.companies or current_spec.constituents is not None
    ):
        return None
    metrics = unique_metrics_from_phrase(message)
    if not metrics or (index is not None and index.find(message)):
        return None
    return _metrics_in_place(patch, metrics, current_spec)


def _metrics_in_place(
    patch: SpecPatch, metrics: tuple[str, ...], current_spec: AnalysisSpec
) -> SpecPatch:
    """These metrics in place of the ones on screen, the companies as they are."""
    return _extend(
        patch,
        add_metrics=metrics,
        remove_metrics=tuple(m for m in current_spec.metrics if m not in metrics),
        add_companies=(),
        remove_companies=(),
    )


def _named_by_index(
    text: str, patch: SpecPatch, index: CompanyNames | None
) -> tuple[str, ...]:
    """The companies the index finds in ``text``, in the planner's spelling where it has one."""
    if index is None:
        return ()
    found = tuple(dict.fromkeys(mention.query for mention in index.find(text)))
    # The planner's "Nvidia" stays "Nvidia" when it is the NVDA the words name.
    spelled = {index.named(company) or company: company for company in patch.add_companies}
    return tuple(spelled.get(query, query) for query in found)


def _company_edit(
    message: str, patch: SpecPatch, spec: AnalysisSpec, index: CompanyNames | None
) -> SpecPatch | None:
    """ "Oracle too" adds Oracle; "what about Goldman?" puts Goldman in their place.

    Only an edit that names companies and no metric of its own: "what about
    net margin?" and "what about over the past two years?" are other edits,
    and a ranked list is left to the planner.
    """
    if spec.constituents is not None or index is None:
        return None
    instead = _INSTEAD_EDIT.match(message)
    also = None if instead is not None else _ALSO_EDIT.match(message)
    match = instead or also
    if match is None:
        return None
    span = next(group for group in match.groups() if group)
    named = _named_by_index(span, patch, index)
    if not named or unique_metrics_from_phrase(span):
        return None
    if instead is not None:
        return _extend(
            patch,
            add_companies=named,
            remove_companies=tuple(
                company.query for company in spec.companies if company.query not in named
            ),
            add_metrics=(),
            remove_metrics=(),
        )
    return _extend(patch, add_companies=named, remove_companies=(), add_metrics=())
