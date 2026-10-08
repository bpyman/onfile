"""Period selection: the quarters a question asks for, read from the analyst's words.

One grammar, ``read``, for every wording of a period (ADR 0015): a counted
window, a "since" window, named periods, half-years, year ranges, month
quarters, "N years ago", latest and this quarter, sub-quarter and year-to-date
words, and a specific period the grammar leaves unread. Its result, ``Words``,
holds the reading in the form the thread stores (``WindowReading``), the
periods named, and whether the words name a window at all; it proposes the
period part of a spec patch before the request is stored.

A window's wording is a recency word (or a preposition), a count and a unit:
"last 4 quarters", "the past six quarters", "previous nine quarters", "most
recent twelve quarters", "trailing seven quarters", "the 6 latest quarters",
"over 8 quarters", "the last couple of quarters", "past three years", "the
last 18 months". The recency word may be left out after the metric: "Apple
revenue 18 months", "6 quarters" and "a couple of years" are the same windows.
Counts are digits or words up to ninety-nine, "a couple" (2) or "a dozen" (12);
"a few" and "several" are read as 4 and said so. "The past decade" needs no
count: it is one. Years are four quarters each, decades forty, months a third
of one (rounded up, and said so). A whole number of years and a half ("a year
and a half", "one and a half years", "2.5 years", "the past two and a half
years") is that many years and two quarters more. A window is capped at
``MAX_QUARTERS_ASKED`` quarters, and that is said too.

A count that names something else is not a window: "3 months ended June"
names a quarter, "2 quarters ago" names one quarter, "12-month" in
"trailing 12-month revenue" is the trailing year (no space between count and
unit), and the year of a "since" window ("since 2025 year over year") is a
year, not 2025 of them. A decimal that is not a half ("1.25 years") is left
unread, rather than read by its last digits.

Named periods ("Q3 2024", "fiscal 2025", "H1 2026", "from 2022 to 2024",
"September quarter 2025", "20 years ago") are each company's own fiscal
calendar unless "calendar" says otherwise (CONTEXT.md, Named period).
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from datetime import date

from pydantic import BaseModel, Field

from financial_analyst_agent.graph.analysis_spec import (
    MAX_QUARTERS_ASKED,
    NamedPeriodSpec,
    PeriodSelection,
    SpecPatch,
)
from financial_analyst_agent.observability import log_event
from financial_analyst_agent.services.metric_catalog import (
    TRAILING_YEAR_WORDS,
    without_trailing_year_words,
)


class WindowReading(BaseModel):
    """What one message's window words say, in the form the thread stores.

    Compilation and the answer's notes share it. ``year_to_date`` is left out of
    the dump unless set, so stored dumps and compared specs are as before.
    """

    asked_quarters: int | None = None
    counted_window: bool = False
    interpretation_notes: tuple[str, ...] = ()
    trailing_year: bool = False
    # "last year", "annual": the four latest quarters, shown one by one.
    year_of_quarters: bool = False
    # "since 2024": the quarters are every filed quarter since that 1 January,
    # chosen where the companies' report dates are known, so no count is read.
    since_year: int | None = None
    # "since fiscal 2025": the year is each company's own fiscal year.
    since_fiscal: bool = False
    unread_named_period: str | None = None
    sub_quarter: bool = False
    # "YTD", "year to date": not supported; the answer says what it shows instead.
    year_to_date: bool = Field(default=False, exclude_if=lambda value: not value)


# --- The counted window -----------------------------------------------------

_ONES = [
    "one",
    "two",
    "three",
    "four",
    "five",
    "six",
    "seven",
    "eight",
    "nine",
    "ten",
    "eleven",
    "twelve",
    "thirteen",
    "fourteen",
    "fifteen",
    "sixteen",
    "seventeen",
    "eighteen",
    "nineteen",
]
_TENS = ["twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]
_NUMBER_VALUES = {word: value for value, word in enumerate(_ONES, start=1)}
_NUMBER_VALUES |= {word: 20 + 10 * place for place, word in enumerate(_TENS)}
# Counts read as 4 quarters: the analyst named no number, so the answer says so.
_VAGUE = frozenset({"few", "a few", "several"})
_SPOKEN = {"couple": 2, "a couple": 2, "pair": 2, "a pair": 2, "dozen": 12, "a dozen": 12}

_WORD_NUMBER = rf"(?:(?:{'|'.join(_TENS)})(?:[\s-](?:{'|'.join(_ONES[:9])}))?|{'|'.join(_ONES)})"
# Digits after a decimal point ("2.5", "1.25") are not a count of their own.
_DIGITS = r"(?<![\d.])\d+"
_COUNT = (
    rf"(?P<count>{_DIGITS}|{_WORD_NUMBER}|(?:a\s+)?(?:couple|pair|dozen)(?:\s+of)?"
    r"|(?:a\s+)?few|several)"
)
# "3 months ended June" names a quarter; "2 quarters ago" names one quarter.
_NOT_A_POINT_IN_TIME = r"(?![\w-])(?!\s+(?:ended|ending|ago|from now|later)\b)"
_UNIT = (
    r"(?P<unit>(?:fiscal\s+|calendar\s+)?(?:quarters?|qtrs?|qs|years?|yrs?)|months?|decades?)"
    + _NOT_A_POINT_IN_TIME
)
_HALF = r"and\s+(?:a|one)[\s-]half"
# A whole number of years and a half, with the count before or after the unit.
# ``half`` marks the form; ``years`` is the whole years, left out or "a" for one.
_HALF_YEARS = (
    # "two and a half years", "2 and a half years", "2.5 years"
    rf"(?P<years>{_DIGITS}|{_WORD_NUMBER})(?P<half>\.5|\s+{_HALF})\s+years?{_NOT_A_POINT_IN_TIME}",
    # "a year and a half", "the last year and a half", "two years and a half"
    rf"(?:(?P<years>an?|{_DIGITS}|{_WORD_NUMBER})\s+)?years?\s+(?P<half>{_HALF})"
    + _NOT_A_POINT_IN_TIME,
)
_RECENT = r"(?:last|past|previous|prior|trailing|most\s+recent|recent|latest|preceding)"
_WINDOW_PATTERNS = (
    # "the last year and a half", "over the past 2.5 years", "one and a half years":
    # the half forms come first, so a tie on where a match starts reads the half.
    *(re.compile(rf"\b{_RECENT}\s+(?:the\s+)?{span}", re.I) for span in _HALF_YEARS),
    *(
        re.compile(rf"\b(?:over|across|for|during|spanning)\s+(?:the\s+)?{span}", re.I)
        for span in _HALF_YEARS
    ),
    *(re.compile(rf"\b{span}", re.I) for span in _HALF_YEARS),
    # "last 4 quarters", "the past six quarters", "most recent twelve quarters"
    re.compile(rf"\b{_RECENT}\s+(?:the\s+)?{_COUNT}\s+{_UNIT}", re.I),
    # "the 4 most recent quarters", "6 latest quarters"
    re.compile(rf"\b{_COUNT}\s+{_RECENT}\s+{_UNIT}", re.I),
    # "over 8 quarters", "across the two years", "for a couple of quarters"
    re.compile(rf"\b(?:over|across|for|during|spanning)\s+(?:the\s+)?{_COUNT}\s+{_UNIT}", re.I),
    # "the past decade": one decade, though no count is said.
    re.compile(rf"\b{_RECENT}\s+(?P<unit>decade)(?![\w-])(?!\s+ago\b)", re.I),
    # "18 months", "6 quarters", "a couple of years": a count and a unit with no
    # recency word. The earliest match wins, so "last 4 quarters" keeps its "last".
    re.compile(rf"\b{_COUNT}\s+{_UNIT}", re.I),
)
_QUARTERS_PER = {"quarter": 1, "qtr": 1, "q": 1, "year": 4, "yr": 4, "decade": 40}

# "since 2023", "since the start of 2023", "since early 2023": every quarter from
# the start of that year. "since fiscal 2025", "since FY2025": from the start of
# each company's own fiscal year. The year is no count: "since 2025 year over
# year" is the window since 2025 began, with a change on it.
SINCE_YEAR = re.compile(
    r"\bsince\s+(?:the\s+(?:start|beginning)\s+of\s+|early\s+(?:in\s+)?)?"
    r"(?P<fiscal>fy\s*|fiscal\s+(?:year\s+)?)?(?P<y>(?:19|20)\d{2})\b",
    re.I,
)


@dataclass(frozen=True)
class _AskedWindow:
    """A window the message asks for, in quarters, and what to say about reading it."""

    quarters: int
    # The words that asked for it ("past six quarters").
    said: str
    # How many quarters the words meant before the cap, when the cap applied.
    capped_from: int | None = None
    # "a few quarters" (no number given), or "4 months" (not a whole number of quarters).
    approximate: bool = False

    def notes(self) -> list[str]:
        """What the answer says about how it read the window."""
        notes: list[str] = []
        if self.capped_from is not None:
            notes.append(
                f"A window shows at most {MAX_QUARTERS_ASKED} quarters, so this asks for "
                f"{MAX_QUARTERS_ASKED} rather than {self.capped_from}."
            )
        elif self.approximate:
            plural = "s" if self.quarters != 1 else ""
            notes.append(
                f"Read “{self.said}” as the latest {self.quarters} quarter{plural}; "
                "name a number of quarters to change it."
            )
        return notes


def _count(raw: str) -> tuple[int, bool]:
    """(value, approximate) for a count's words."""
    text = " ".join(raw.casefold().replace("-", " ").split())
    text = text.removesuffix(" of")
    if text in _VAGUE:
        return 4, True
    if text in _SPOKEN:
        return _SPOKEN[text], False
    if text.isdigit():
        return int(text), False
    words = text.split()
    return sum(_NUMBER_VALUES[word] for word in words), False


def _asked_window(message: str) -> _AskedWindow | None:
    """The window the message asks for, or None when it names no count of periods."""
    since_years = [since.span() for since in SINCE_YEAR.finditer(message)]
    found = [
        match
        for pattern in _WINDOW_PATTERNS
        if (match := pattern.search(message)) is not None
        and not any(match.start() < end and start < match.end() for start, end in since_years)
    ]
    if not found:
        return None
    match = min(found, key=lambda candidate: candidate.start())
    groups = match.groupdict()
    approximate = False
    if groups.get("half") is not None:
        # "two and a half years": the whole years, and two quarters more.
        years = groups.get("years")
        whole = 1 if years is None or years.casefold() in ("a", "an") else _count(years)[0]
        quarters = whole * _QUARTERS_PER["year"] + 2
    else:
        said_count = groups.get("count")
        count, approximate = _count(said_count) if said_count is not None else (1, False)
        unit = match.group("unit").casefold().split()[-1].rstrip("s")
        if unit == "month":
            quarters = math.ceil(count / 3)
            approximate = approximate or count % 3 != 0
        else:
            quarters = count * _QUARTERS_PER[unit]
    quarters = max(quarters, 1)
    capped = quarters if quarters > MAX_QUARTERS_ASKED else None
    return _AskedWindow(
        quarters=min(quarters, MAX_QUARTERS_ASKED),
        said=" ".join(match.group(0).split()),
        capped_from=capped,
        approximate=approximate,
    )


# --- Named periods ----------------------------------------------------------

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


# "H1 2026", "first half of fiscal 2026": two named quarters.
_HALF_YEAR = re.compile(
    rf"\b{_CALENDAR_WORD}(?:h(?P<h>[12])|(?P<hw>first|second|1st|2nd)\s+half(?:\s+of)?)\s*"
    rf"{_FISCAL_WORD}{_YEAR}",
    re.I,
)


def _named_periods(message: str) -> tuple[NamedPeriodSpec, ...]:
    """Every period the message names, in the order named, without repeats."""
    found: list[tuple[int, NamedPeriodSpec]] = []
    taken: list[tuple[int, int]] = []

    def free(start: int, end: int) -> bool:
        return not any(start < other_end and end > other_start for other_start, other_end in taken)

    for match in _HALF_YEAR.finditer(message):
        start, end = match.span()
        if not free(start, end):
            continue
        groups = match.groupdict()
        year = _full_year(groups["y"])
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
    # "since the start of 2023" is a window; its year names no period.
    taken.extend(match.span() for match in SINCE_YEAR.finditer(message))
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
            year = _full_year(groups["y"])
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


def _full_year(raw: str) -> int:
    """ "25" and "2025" are both 2025."""
    return int(raw) + (2000 if len(raw) == 2 else 0)


# --- Other period words -----------------------------------------------------

# "Q5 2025" names no quarter; answering the latest one instead would mislead.
INVALID_QUARTER = re.compile(r"\bQ(0|[5-9]|\d{2,})\s*(?:FY\s*)?'?\d{2,4}\b", re.IGNORECASE)


# "latest revenue" after "Apple revenue Q3 2025" asks for the newest quarter again.
LATEST = re.compile(
    r"\b(?:latest|most recent|newest)\b|\b(?:last|this|current) quarter\b", re.IGNORECASE
)


TRAILING_YEAR = re.compile(rf"\b(?:{TRAILING_YEAR_WORDS})\b", re.I)


# "Apple revenue last year", "annual revenue": a year of quarters, like TTM.
YEAR_OF_QUARTERS = re.compile(
    r"\b(?:last|past|previous|prior)\s+year\b|\bannual(?:ly)?\b|\byearly\b|\bfull[\s-]year\b",
    re.I,
)


# "changed over the last year": a change across a year is year over year.
YEAR_BASE = re.compile(
    r"\b(?:over|in|during|across) the (?:last|past|previous|prior)"
    r" (?:year|twelve months|12 months)\b",
    re.IGNORECASE,
)


YEAR_TO_DATE = re.compile(r"\b(?:ytd|year[\s-]+to[\s-]+date)\b", re.I)


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


# Words that ask about time at all. A planner's window stands only beside one:
# "how is Nvidia doing" asks for no window, whatever the model proposed.
_PERIOD_CUE = re.compile(
    r"\b(?:quarters?|qtrs?|years?|yrs?|months?|annual(?:ly)?|window|period|periods"
    r"|recent(?:ly)?|trailing|ttm|ltm|history|historical(?:ly)?|trends?|trending|over time"
    r"|grow(?:th|n|ing)?|grew|since|yoy|qoq|sequential(?:ly)?|lately|so far)\b",
    re.IGNORECASE,
)


def _window_words(message: str) -> str:
    """The wording a window is read from: "TTM net income" names a figure, not quarters."""
    return without_trailing_year_words(message)


def _within(outer: re.Match[str], inner: re.Match[str]) -> bool:
    return outer.start() <= inner.start() and inner.end() <= outer.end()


def _read_window(message: str) -> WindowReading:
    """Read once the window details that compilation and answer notes both need."""
    year_of_quarters = YEAR_OF_QUARTERS.search(message) is not None
    year_to_date = YEAR_TO_DATE.search(message) is not None
    message = _window_words(message)
    window = _asked_window(message)
    since = SINCE_YEAR.search(message) if window is None else None
    specific = SPECIFIC_PERIOD.search(message)
    unread = (
        specific.group(0)
        if specific is not None
        and not _named_periods(message)
        # "since fiscal 2025" names the window's year, not a period left unread.
        and not (since is not None and _within(since, specific))
        else None
    )
    return WindowReading(
        asked_quarters=window.quarters if window is not None else None,
        counted_window=window is not None,
        interpretation_notes=tuple(window.notes()) if window is not None else (),
        trailing_year=TRAILING_YEAR.search(message) is not None,
        year_of_quarters=year_of_quarters,
        since_year=int(since.group("y")) if since is not None else None,
        since_fiscal=since is not None and since.group("fiscal") is not None,
        unread_named_period=unread,
        sub_quarter=SUB_QUARTER.search(message) is not None,
        year_to_date=year_to_date,
    )


def _names_a_window(message: str) -> bool:
    """Whether the wording names a window of quarters ("over the past 10 quarters",
    "over the last year", "since 2023").

    A change asked over one, in any wording, is year over year over that window
    (README's growth row); a "since" window is a window too.
    """
    window = _asked_window(_window_words(message))
    return (
        (window is not None and window.quarters > 1)
        or YEAR_BASE.search(message) is not None
        or SINCE_YEAR.search(message) is not None
    )


# --- The reading ------------------------------------------------------------


@dataclass(frozen=True)
class Words:
    """The whole reading of one message. Not persisted; ``reading`` is its stored part."""

    message: str
    reading: WindowReading
    # The periods named, in the order named, without repeats.
    named: tuple[NamedPeriodSpec, ...]
    # A counted window of more than one quarter, "over the past year", or "since".
    names_a_window: bool

    def propose(self, patch: SpecPatch, *, model_quarters: int | None = None) -> SpecPatch:
        """The period part of a proposal, before the request is stored.

        ``model_quarters`` is the planner's count of recent quarters (None for a
        rank intent or a follow-up patch): capped and set as the window. Then the
        planner-window rule: the grammar's own reading decides first, and when it
        reads a window that window stands (a disagreement is logged). When it
        reads none, the planner's stands only if the words have a period cue at
        all. Nothing is bound here; the words bind when the request is resolved.
        """
        if model_quarters is not None and model_quarters >= 1:
            selection = PeriodSelection(
                kind="last_n_quarters", count=min(model_quarters, MAX_QUARTERS_ASKED)
            )
            patch = patch.model_copy(update={"set_periods": selection})
        proposed = patch.set_periods
        if proposed is None or proposed.kind != "last_n_quarters":
            return patch
        if self.reading.counted_window:
            assert self.reading.asked_quarters is not None
            if self.reading.asked_quarters != proposed.count:
                log_event(
                    "planner_window_overruled",
                    proposed=proposed.count,
                    read=self.reading.asked_quarters,
                )
            return patch
        if _PERIOD_CUE.search(_window_words(self.message)):
            return patch
        log_event("planner_window_dropped", proposed=proposed.count)
        return patch.model_copy(update={"set_periods": None})


def read(message: str, *, stored: WindowReading | None = None) -> Words:
    """The one period grammar, read over ``message``.

    Pure. ``stored`` replaces the grammar's reading with the one a request
    already holds (a checkpointed request, or a clarification's held question);
    the named periods and the window cue are still read from ``message``.
    """
    return Words(
        message=message,
        reading=stored if stored is not None else _read_window(message),
        named=_named_periods(message),
        names_a_window=_names_a_window(message),
    )
