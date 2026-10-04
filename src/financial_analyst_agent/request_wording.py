"""The analyst's words, read: metrics, named periods, windows, comparison bases, edits.

One grammar for whichever planner proposed the analysis (ADR 0010): what a
question names, what period it asks about, what a change is measured against,
and how a follow-up edits the analysis on screen. Nothing here fetches.
"""

from __future__ import annotations

import re
from datetime import date
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
    AnalysisSpec,
    NamedPeriodSpec,
    PeriodSelection,
    SpecPatch,
)
from financial_analyst_agent.guide import short_name
from financial_analyst_agent.issuer_index import CompanyNames
from financial_analyst_agent.observability import log_event
from financial_analyst_agent.period_window import asked_window
from financial_analyst_agent.services.metric_catalog import resolve_metric_phrase

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


_DROP_EDIT = re.compile(
    r"^\s*(?:drop|remove|without)\s+(.+?)\s*$",
    re.IGNORECASE,
)
# "remove year over year": the change goes, the quarters on screen stay. Read
# before the year-over-year wording, which would otherwise ask for it.
_DROP_COMPARISON = re.compile(
    r"^\s*(?:drop|remove|without|no|hide)\s+(?:the\s+)?"
    r"(?:year[\s-]*over[\s-]*year|yoy)(?:\s+(?:change|changes|growth|comparison|column))?"
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
    r"^\s*(?:drop|remove)\s+(.+?)\s*,?\s+(?:and\s+)?(?:add|include|show)\s+(.+?)\s*$",
    re.IGNORECASE,
)


YOY = re.compile(
    r"\b(?:year[\s-]*over[\s-]*year|yoy|show yoy|compare to last year|(?:a|one) year ago"
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


_YEAR = r"'?(?P<y>(?:19|20)\d{2}|\d{2})\b"


_FISCAL_WORD = r"(?:(?:fy|fiscal(?:\s+year)?)\s*)?"


_CALENDAR_WORD = r"(?P<cal>calendar\s+(?:year\s+)?|cy\s*)?"


_QUARTER_WORDS = {
    "first": 1,
    "1st": 1,
    "second": 2,
    "2nd": 2,
    "third": 3,
    "3rd": 3,
    "fourth": 4,
    "4th": 4,
}


# Named periods, most specific first: "Q3 2024", "Q3 FY25", "2024 Q3", "third
# quarter of fiscal 2024", "fiscal 2025", "FY24", "calendar 2025", "in 2024".
_NAMED_PERIOD_PATTERNS = (
    re.compile(rf"\b{_CALENDAR_WORD}q(?P<q>[1-4])\s*(?:of\s+)?{_FISCAL_WORD}{_YEAR}", re.I),
    re.compile(rf"\b{_CALENDAR_WORD}(?P<y>(?:19|20)\d{{2}})\s*q(?P<q>[1-4])\b", re.I),
    # Sell-side shorthand: "2Q 2026", "3Q25", "4QFY24".
    re.compile(rf"\b{_CALENDAR_WORD}(?P<q>[1-4])q\s*{_FISCAL_WORD}{_YEAR}", re.I),
    re.compile(
        rf"\b{_CALENDAR_WORD}(?P<qw>first|second|third|fourth|1st|2nd|3rd|4th)\s+"
        rf"(?:fiscal\s+)?quarter\s+(?:of\s+)?{_FISCAL_WORD}{_YEAR}",
        re.I,
    ),
    re.compile(rf"\b(?P<cal>calendar(?:\s+year)?\s+|cy\s*){_YEAR}", re.I),
    re.compile(rf"\b(?:fy|fiscal(?:\s+year)?)\s*{_YEAR}", re.I),
    re.compile(r"\b(?:in|for|during)\s+(?P<y>(?:19|20)\d{2})\b", re.I),
    # A bare year is that fiscal year ("Apple revenue 2024", "2025 vs 2024"), but
    # "since 2020" is a window and "top 2000" a count.
    re.compile(
        r"(?<![\w$.,/-])(?<!since )(?<!top )(?<!last )(?P<y>(?:19|20)\d{2})(?![\w%.,/-])", re.I
    ),
)


_MONTHS = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}  # fmt: skip


_MONTH = r"(?P<m>jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?"


# "September quarter 2025", "December 2025 quarter", "quarter ended June 2026":
# the calendar quarter that month closes. Other months name no calendar quarter.
_MONTH_QUARTER_PATTERNS = (
    re.compile(
        rf"\b(?:quarter|period|three months)\s+(?:ended|ending|to)\s+(?:in\s+)?{_MONTH}\s+"
        rf"(?:\d{{1,2}},?\s+)?(?P<y>(?:19|20)\d{{2}})\b",
        re.I,
    ),
    re.compile(rf"\b{_MONTH}\s+(?P<y>(?:19|20)\d{{2}})\s+quarter\b", re.I),
    re.compile(rf"\b{_MONTH}\s+quarter\s+(?:of\s+)?(?P<y>(?:19|20)\d{{2}})\b", re.I),
)


# "from 2022 to 2024": each fiscal year in the range.
_YEAR_RANGE = re.compile(
    r"\b(?:from|between)\s+(?:fy\s*)?(?P<a>(?:19|20)\d{2})\s+(?:to|and|through|until|-)\s+"
    r"(?:fy\s*)?(?P<b>(?:19|20)\d{2})\b",
    re.I,
)


_MAX_RANGE_YEARS = 10


# "20 years ago" names that fiscal year; "a year ago" is a year-over-year change.
_YEARS_AGO = re.compile(r"\b(?P<n>\d{1,2})\s+years?\s+ago\b", re.I)


# "next quarter" asks for a forecast; filings only report what has happened.
FORECAST = re.compile(
    r"\bnext\s+(?:quarter|year|fiscal\s+year|fy)\b|\bforecasts?\b|\bprojected\b|\bpredict",
    re.I,
)


# Wording that asks for year-over-year change only, not quarter-to-quarter too.
EXPLICIT_YOY = re.compile(
    r"\b(?:year[\s-]*over[\s-]*year|yoy|(?:a|one) year (?:ago|earlier|before)"
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


# Growth is year over year by convention: analysts and 10-Q MD&A compare a quarter
# with the same quarter a year before, which a season does not distort (ADR 0010).
GROWTH = re.compile(r"\b(?:grow(?:th|n|ing|s)?|grew|trend(?:s|ing)?)\b", re.IGNORECASE)


# "changed over the last year": a change across a year is year over year.
_YEAR_BASE = re.compile(
    r"\b(?:over|in|during|across) the (?:last|past|previous|prior)"
    r" (?:year|twelve months|12 months)\b",
    re.IGNORECASE,
)


COMPARISON_CANDIDATES: tuple[ComparisonBase, ...] = ("year_over_year", "sequential")


COMPARISON_LABELS = (
    "The same quarter a year earlier (year over year)",
    "The quarter before (sequential)",
)


# Four quarters, each with the quarter a year before it.
_YOY_WINDOW = 8


# "Q5 2025" names no quarter; answering the latest one instead would mislead.
INVALID_QUARTER = re.compile(r"\bQ(0|[5-9]|\d{2,})\s*(?:FY\s*)?'?\d{2,4}\b", re.IGNORECASE)


# "latest revenue" after "Apple revenue Q3 2025" asks for the newest quarter again.
_LATEST = re.compile(
    r"\b(?:latest|most recent|newest)\b|\b(?:last|this|current) quarter\b", re.IGNORECASE
)


TRAILING_YEAR = re.compile(
    r"\b(?:ttm|ltm|trailing[\s-]+(?:twelve|12)[\s-]+months?|(?:last|past)\s+(?:twelve|12)\s+months)\b",
    re.I,
)


# "Apple revenue last year", "annual revenue": a year of quarters, like TTM.
YEAR_OF_QUARTERS = re.compile(
    r"\b(?:last|past|previous|prior)\s+year\b|\bannual(?:ly)?\b|\byearly\b|\bfull[\s-]year\b",
    re.I,
)


WHY_CHANGE = re.compile(r"^\s*why\b", re.I)


YEAR_TO_DATE = re.compile(r"\b(?:ytd|year[\s-]+to[\s-]+date)\b", re.I)


# "since 2023": every quarter from the start of that year.
SINCE_YEAR = re.compile(r"\bsince\s+(?:fy\s*|fiscal\s+(?:year\s+)?)?(?P<y>(?:19|20)\d{2})\b", re.I)


MAX_SINCE_QUARTERS = 20


# "H1 2026", "first half of fiscal 2026": two named quarters.
_HALF_YEAR = re.compile(
    rf"\b{_CALENDAR_WORD}(?:h(?P<h>[12])|(?P<hw>first|second|1st|2nd)\s+half(?:\s+of)?)\s*"
    rf"{_FISCAL_WORD}{_YEAR}",
    re.I,
)


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


_OVERVIEW = re.compile(
    r"\b(?:overview|snapshot|summary|profile|financials|fundamentals|numbers|"
    r"key metrics|at a glance|tell me about|how (?:is|are|was)|how's|doing|results)\b",
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
        if patch.mode == "replace":
            return patch.model_copy(update={"add_metrics": phrased}), None
        # Extend: add phrased metrics except those this patch is removing.
        to_add = tuple(m for m in phrased if m not in patch.remove_metrics)
        metrics = tuple(dict.fromkeys([*patch.add_metrics, *to_add]))
        return patch.model_copy(update={"add_metrics": metrics}), None
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
    implied = (
        implied_metrics(message, short=not unknown_word)
        if _names_companies(patch) and not guessed
        else ()
    )
    if not implied and _names_companies(patch) and OVERVIEW_PLAN in patch.add_metrics:
        implied = OVERVIEW_METRICS
    if implied:
        return patch.model_copy(update={"add_metrics": implied}), None
    if patch.ranked_request is not None and not patch.add_metrics:
        return patch, None
    # Replace-mode metric question with an unknown phrase: refuse with the full catalog
    # even when the planner guessed a catalog slug.
    term = "unknown"
    if patch.add_metrics:
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


def parse_named_periods(message: str) -> tuple[NamedPeriodSpec, ...]:
    """Every period the message names, in the order named, without repeats."""
    found: list[tuple[int, NamedPeriodSpec]] = []
    taken: list[tuple[int, int]] = []
    for match in _HALF_YEAR.finditer(message):
        start, end = match.span()
        if any(start < other_end and end > other_start for other_start, other_end in taken):
            continue
        groups = match.groupdict()
        raw_year = groups["y"]
        year = int(raw_year) + (2000 if len(raw_year) == 2 else 0)
        second = groups.get("h") == "2" or (groups.get("hw") or "").casefold() in ("second", "2nd")
        first_quarter = 3 if second else 1
        taken.append((start, end))
        for offset in (0, 1):
            found.append(
                (
                    start + offset,
                    NamedPeriodSpec(
                        year=year, quarter=first_quarter + offset, calendar=bool(groups.get("cal"))
                    ),
                )
            )
    def free(start: int, end: int) -> bool:
        return not any(start < other_end and end > other_start for other_start, other_end in taken)

    for match in _YEAR_RANGE.finditer(message):
        first, last = sorted((int(match.group("a")), int(match.group("b"))))
        if free(*match.span()) and last - first < _MAX_RANGE_YEARS:
            taken.append(match.span())
            found.extend(
                (match.start() + offset, NamedPeriodSpec(year=year))
                for offset, year in enumerate(range(last, first - 1, -1))
            )
    for pattern in _MONTH_QUARTER_PATTERNS:
        for match in pattern.finditer(message):
            month = _MONTHS[match.group("m")[:3].casefold()]
            if not free(*match.span()):
                continue
            taken.append(match.span())
            if month % 3:
                # April closes no calendar quarter; the turn says it was not read.
                continue
            period = NamedPeriodSpec(year=int(match.group("y")), quarter=month // 3, calendar=True)
            found.append((match.start(), period))
    for match in _YEARS_AGO.finditer(message):
        if int(match.group("n")) >= 2 and free(*match.span()):
            taken.append(match.span())
            found.append(
                (match.start(), NamedPeriodSpec(year=date.today().year - int(match.group("n"))))
            )
    for pattern in _NAMED_PERIOD_PATTERNS:
        for match in pattern.finditer(message):
            start, end = match.span()
            if not free(start, end):
                continue
            groups = match.groupdict()
            raw_year = groups["y"]
            year = int(raw_year) + (2000 if len(raw_year) == 2 else 0)
            quarter = None
            if groups.get("q"):
                quarter = int(groups["q"])
            elif groups.get("qw"):
                quarter = _QUARTER_WORDS[groups["qw"].casefold()]
            taken.append((start, end))
            found.append(
                (
                    start,
                    NamedPeriodSpec(year=year, quarter=quarter, calendar=bool(groups.get("cal"))),
                )
            )
    ordered = [period for _start, period in sorted(found, key=lambda item: item[0])]
    return tuple(dict.fromkeys(ordered))


def _with_year_earlier(named: tuple[NamedPeriodSpec, ...]) -> tuple[NamedPeriodSpec, ...]:
    """Add the same period a year earlier, so a year-over-year change has a base."""
    earlier = [period.model_copy(update={"year": period.year - 1}) for period in named]
    return tuple(dict.fromkeys([*named, *earlier]))


def comparison_asked(message: str) -> ComparisonBase | Literal["unclear"] | None:
    """What a change the message asks about is measured against.

    "year_over_year" or "sequential" where the wording says (growth is year
    over year by convention), "unclear" where it asks about a change but not
    against what ("why did revenue drop?"), and None where it asks for no change.
    """
    if YOY.search(message) is None and _SEQUENTIAL.search(message) is None:
        return None
    if _SEQUENTIAL.search(message) is not None:
        return "sequential"
    if (
        EXPLICIT_YOY.search(message) is not None
        or GROWTH.search(message) is not None
        or _YEAR_BASE.search(message) is not None
    ):
        return "year_over_year"
    return "unclear"


def _window_asked(message: str) -> int | None:
    """The quarters a window asks for ("past six quarters", "last 3 years"), or None."""
    window = asked_window(message)
    return window.quarters if window is not None else None


def since_quarters(since: re.Match[str]) -> int:
    """Quarters from the start of the year "since 2020" names to today."""
    today = date.today()
    return max(1, (today.year - int(since.group("y"))) * 4 + (today.month + 2) // 3)


def bind_periods_from_message(patch: SpecPatch, message: str) -> SpecPatch:
    """Period windows come from the analyst's wording, not a model slug."""
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
    asked = _window_asked(message)
    yoy = YOY.search(message) is not None
    # "quarter over quarter" is a window of sequential changes.
    sequential = _SEQUENTIAL.search(message) is not None
    named = parse_named_periods(message)
    since = SINCE_YEAR.search(message)
    if not named and asked is None and not yoy and since is not None:
        count = min(since_quarters(since), MAX_SINCE_QUARTERS)
        return patch.model_copy(
            update={"set_periods": PeriodSelection(kind="last_n_quarters", count=count)}
        )
    if not named and asked is None and not yoy and (
        TRAILING_YEAR.search(message) or YEAR_OF_QUARTERS.search(message)
    ):
        # "TTM revenue": show the four quarters that make up the trailing year.
        return patch.model_copy(
            update={"set_periods": PeriodSelection(kind="last_n_quarters", count=4)}
        )
    if named:
        operations = patch.add_operations
        quarters = [period for period in named if period.quarter is not None]
        if yoy:
            named = _with_year_earlier(named)
        if (yoy or len(quarters) >= 2) and "across_periods" not in operations:
            operations = (*operations, "across_periods")
        return patch.model_copy(
            update={
                "set_periods": PeriodSelection(kind="named", named=named),
                "add_operations": operations,
            }
        )
    if asked is None and not yoy and not sequential:
        if _LATEST.search(message) is not None:
            # "latest" after a year-over-year window: one quarter, no change chip.
            return patch.model_copy(
                update={
                    "set_periods": PeriodSelection(),
                    "remove_operations": (
                        *patch.remove_operations,
                        "across_periods",
                        "year_over_year",
                    ),
                }
            )
        return patch
    operations = patch.add_operations
    if (yoy or sequential) and "across_periods" not in operations:
        operations = (*operations, "across_periods")
    # Growth is year over year unless the analyst says sequential (ADR 0010); a
    # change that names no base is asked about before the analysis runs.
    explicit_yoy = comparison_asked(message) == "year_over_year"
    if explicit_yoy and "year_over_year" not in operations:
        operations = (*operations, "year_over_year")
    if asked is None and patch.set_periods is not None:
        return patch.model_copy(update={"add_operations": operations})
    count = asked if asked is not None else 5
    if (yoy or sequential) and count < 5 and not (explicit_yoy and asked is not None):
        # A sequential change needs the quarter before the oldest one shown.
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


def _extend(patch: SpecPatch, **fields: Any) -> SpecPatch:
    """The patch as an edit of the current analysis rather than a new ranking."""
    return patch.model_copy(update={"mode": "extend", "ranked_request": None, **fields})


_CHANGE_OPERATIONS = ("across_periods", "year_over_year")


def drops_comparison(message: str) -> bool:
    """ "remove year over year", "no YoY": take the change away, keep the quarters."""
    return _DROP_COMPARISON.match(message) is not None


def asks_to_swap(message: str) -> bool:
    """Whether a follow-up puts what it names in place of what is on screen."""
    return _SWAP_CUE.search(message) is not None


def is_removal(message: str) -> bool:
    """ "drop revenue", "remove Apple", "without margins": an edit that takes away."""
    return _DROP_EDIT.match(message.strip()) is not None


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


# Words that ask about time at all. A planner's window stands only beside one:
# "how is Nvidia doing" asks for no window, whatever the model proposed.
_PERIOD_CUE = re.compile(
    r"\b(?:quarters?|qtrs?|years?|yrs?|months?|annual(?:ly)?|window|period|periods"
    r"|recent(?:ly)?|trailing|ttm|ltm|history|historical(?:ly)?|trends?|trending|over time"
    r"|grow(?:th|n|ing)?|grew|since|yoy|qoq|sequential(?:ly)?|lately|so far)\b",
    re.IGNORECASE,
)


def planner_window(patch: SpecPatch, message: str) -> SpecPatch:
    """A planner's window, kept only where the wording asks about time but names no count.

    The wording's grammar decides first: when it reads a window, that window
    replaces the planner's (and a disagreement is logged). When it reads none,
    the planner's stands only if the message has a period word at all.
    """
    proposed = patch.set_periods
    if proposed is None or proposed.kind != "last_n_quarters":
        return patch
    read = asked_window(message)
    if read is not None:
        if read.quarters != proposed.count:
            log_event(
                "planner_window_overruled", proposed=proposed.count, read=read.quarters
            )
        return patch
    if _PERIOD_CUE.search(message):
        return patch
    log_event("planner_window_dropped", proposed=proposed.count)
    return patch.model_copy(update={"set_periods": None})


def refine_patch_from_message(
    patch: SpecPatch,
    message: str,
    current_spec: AnalysisSpec | None,
    *,
    index: CompanyNames | None = None,
) -> SpecPatch:
    """Turn follow-up wording into an extend patch when the planner still replaced.

    The edit's own words decide, whichever planner proposed the patch: "add",
    "include", "too" and "as well" add companies; "what about", "how about"
    and "same for" put them in place of the ones on screen. ``index`` reads
    which companies the words name.
    """
    patch = bind_periods_from_message(patch, message)
    if current_spec is None:
        return patch
    if drops_comparison(message):
        # Nothing else on screen changes: not a company called "year over year".
        return _extend(
            patch, add_companies=(), remove_companies=(), add_metrics=(), remove_metrics=()
        )

    swap = _swap_pair(message.strip())
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

    switched = _SWITCH_TO_EDIT.match(message.strip())
    if switched is not None:
        span = (switched.group("span") or switched.group("instead")).strip(" .,")
        metrics = unique_metrics_from_phrase(span)
        if metrics:
            return _extend(
                patch,
                add_metrics=metrics,
                remove_metrics=tuple(m for m in current_spec.metrics if m not in metrics),
                add_companies=(),
                remove_companies=(),
            )

    metric_swap = _metric_swap(message, patch, current_spec, index)
    if metric_swap is not None:
        return metric_swap

    added = _ADD_EDIT.match(message.strip())
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

    companies_edit = _company_edit(message.strip(), patch, current_spec, index)
    if companies_edit is not None:
        return companies_edit

    dropped = _DROP_EDIT.match(message.strip())
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

    compare_to = _COMPARE_TO_ISSUER.match(message.strip())
    if compare_to is not None and YOY.search(message) is None:
        token = compare_to.group(1).strip(" .,")
        if token and not unique_metrics_from_phrase(token):
            return _extend(patch, add_companies=(token,), add_metrics=())

    # "What was it last quarter?" names nothing new: it is not a question of its own.
    standalone = (patch.ranked_request is not None or _names_companies(patch)) and (
        _STANDALONE_LOOKUP.search(message.strip()) is not None
        or _STANDALONE_COMPARE.search(message.strip()) is not None
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


# Periods shorter than a quarter, which no 10-Q reports on its own.
SUB_QUARTER = re.compile(
    r"\b(?:last|this|past|previous)\s+(?:month|week)\b|\byesterday\b"
    r"|\b(?:in|for|during)\s+(?:january|february|march|april|june|july|august|september"
    r"|october|november|december)\b(?!\s+(?:19|20)\d{2})",
    re.IGNORECASE,
)


SPECIFIC_PERIOD = re.compile(
    r"\b(?:"
    r"q[1-4]\s*(?:fy\s*)?'?\d{2,4}"
    r"|[1-4]q\s*(?:fy\s*)?'?\d{2,4}"
    r"|(?:fy|fiscal(?:\s+year)?)\s*'?\d{2,4}"
    r"|(?:first|second|third|fourth|1st|2nd|3rd|4th)\s+quarter\s+(?:of\s+)?(?:fy\s*)?\d{4}"
    r"|(?:in|for|during)\s+(?:19|20)\d{2}"
    # "quarter ended April 2026": a month this parser does not read as a quarter.
    r"|(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\.?\s+(?:\d{1,2},?\s+)?"
    r"(?:19|20)\d{2}"
    r")\b",
    re.IGNORECASE,
)
