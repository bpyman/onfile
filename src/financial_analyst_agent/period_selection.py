"""Period selection: the quarters a question asks for, read from the analyst's words.

One grammar, ``read``, for every wording of a period (ADR 0015): a counted
window, a "since" window, named periods, half-years, year ranges, month
quarters, "N years ago", latest and this quarter, sub-quarter and year-to-date
words, and a specific period the grammar leaves unread. Its result, ``Words``,
holds the reading in the form the thread stores (``WindowReading``), the
periods named, and whether the words name a window at all; it proposes the
period part of a spec patch before the request is stored, binds it when
the request is resolved, and rebases a change follow-up on the quarters on
screen. Which change the words ask for is read outside and passed in as a
``ChangeAsked``. The view ``Periods`` dates a spec's quarters for each company
from its own filings, the facts provider passed in.

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
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import date
from functools import partial
from typing import Any, ClassVar, Literal

from pydantic import BaseModel, Field

from financial_analyst_agent.contracts import ComparisonBase, FactsPort
from financial_analyst_agent.domain.errors import SessionQuotaError
from financial_analyst_agent.fan_out import map_in_order
from financial_analyst_agent.graph.analysis_spec import (
    MAX_QUARTERS_ASKED,
    AnalysisSpec,
    NamedPeriodSpec,
    PeriodSelection,
    ResolvedCompany,
    SpecPatch,
)
from financial_analyst_agent.observability import log_event
from financial_analyst_agent.services.fiscal_periods import (
    FiscalPeriod,
    adjacent_quarters,
    calendar_quarter,
    dates_for,
    quarters_in_fiscal_span,
    quarters_since,
    quarters_since_fiscal_year,
)
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
_LATEST = re.compile(
    r"\b(?:latest|most recent|newest)\b|\b(?:last|this|current) quarter\b", re.IGNORECASE
)


TRAILING_YEAR = re.compile(rf"\b(?:{TRAILING_YEAR_WORDS})\b", re.I)


# "Apple revenue last year", "annual revenue": a year of quarters, like TTM.
YEAR_OF_QUARTERS = re.compile(
    r"\b(?:last|past|previous|prior)\s+year\b|\bannual(?:ly)?\b|\byearly\b|\bfull[\s-]year\b",
    re.I,
)


# "changed over the last year": a change across a year is year over year.
_YEAR_BASE = re.compile(
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
        or _YEAR_BASE.search(message) is not None
        or SINCE_YEAR.search(message) is not None
    )


# --- The change asked -------------------------------------------------------


# A "since" window is a window: at most as many quarters as any other (README).
MAX_SINCE_QUARTERS = MAX_QUARTERS_ASKED


# Growth with no window named: four quarters, and the year-earlier base of the
# newest. Year over year named with no window: four, each with the quarter a
# year before it.
_GROWTH_WINDOW = 5
_YOY_WINDOW = 8


_CHANGE_OPERATIONS = ("across_periods", "year_over_year", "sequential")


@dataclass(frozen=True)
class ChangeAsked:
    """Which change the words ask for: this module's input, read outside it.

    ``request_wording.change_asked`` builds one from the change patterns; this
    module never searches the message for change words (ADR 0015). The binding
    tells all seven flags apart: growth with no window shows five quarters,
    year over year named as such eight, a change with no base is asked about,
    and a sequential change reads base quarters.
    """

    # What the change is measured against: "unclear" where the words ask about
    # a change but not against what, None where no change is asked.
    base: ComparisonBase | Literal["unclear"] | None
    # Growth, "how has it changed", "versus last year": a change over quarters.
    yoy: bool
    # "quarter over quarter", "vs the previous quarter".
    sequential: bool
    # "sequentially or versus last year": both changes on each quarter.
    both: bool
    # Year over year named as such, not implied by growth.
    explicit_yoy: bool
    # "how much did it change", "what drove the change in": a change that may
    # name no base.
    change_words: bool
    # "remove year over year": the change goes, the quarters stay.
    dropped: bool

    NONE: ClassVar[ChangeAsked]


ChangeAsked.NONE = ChangeAsked(
    base=None,
    yoy=False,
    sequential=False,
    both=False,
    explicit_yoy=False,
    change_words=False,
    dropped=False,
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

    def bind(self, patch: SpecPatch, change: ChangeAsked) -> SpecPatch:
        """The words' periods on the patch, with the change asked over them.

        A dropped change keeps the quarters; a "since" window names its year;
        the trailing year and "last year" are four quarters; named periods are
        themselves, with base quarters to list when the change is sequential;
        "latest" is one quarter again; a change with no window is over the
        five quarters of growth or the eight of year over year; and a
        sequential window reads one quarter more than it shows. Returns
        ``patch`` itself when nothing applies: a clarification tells a period
        reply by comparing the two. Runs before the company and metric edit,
        which reads ``set_periods``; ``rebase`` runs after it.
        """
        if change.dropped:
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
        reading = self.reading
        asked = reading.asked_quarters if reading.counted_window else None
        # "How much did revenue change?" shows the quarters "how has it changed?"
        # does: words that ask about a change with no base ask it over a window,
        # or with at most one named period. Over named periods alone, the
        # periods themselves are the answer, so no change is asked.
        yoy = change.yoy or (
            change.change_words and (self.names_a_window or len(self.named) <= 1)
        )
        # "quarter over quarter" is a window of sequential changes.
        sequential = change.sequential
        if asked is None and (yoy or sequential) and _YEAR_BASE.search(self.message) is not None:
            # "How did EBITDA change over the past year?": a change over a year named
            # with no count is over that year's four quarters, as "growth over the
            # last 4 quarters" is, not the growth default (README's growth row).
            asked = 4
        named = self.named
        if not named and asked is None and reading.since_year is not None:
            # Every filed quarter since that 1 January, at most the window cap: the
            # quarters are chosen where the report dates are listed, as a named
            # period's are, not counted from today. A change over it is over those
            # quarters: year over year from each one's own comparative (ADR 0009),
            # or on the quarter before, where the oldest has none inside the window.
            operations = _operations_with_change(
                patch.add_operations, across=yoy or sequential, base=change.base, both=change.both
            )
            return patch.model_copy(
                update={
                    "set_periods": PeriodSelection(
                        kind="last_n_quarters",
                        count=MAX_SINCE_QUARTERS,
                        since_year=reading.since_year,
                        since_fiscal=reading.since_fiscal,
                    ),
                    "add_operations": operations,
                }
            )
        if not named and asked is None and not yoy and (
            reading.trailing_year or reading.year_of_quarters
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
            operations = _operations_with_change(
                patch.add_operations,
                across=yoy or sequential or len(quarters) >= 2,
                base=change.base,
                both=change.both,
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
            if _LATEST.search(self.message) is not None:
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
        year_over_year = change.base == "year_over_year"
        operations = _operations_with_change(
            patch.add_operations, across=yoy or sequential, base=change.base, both=change.both
        )
        if asked is None and patch.set_periods is not None:
            return patch.model_copy(update={"add_operations": operations})
        count = asked if asked is not None else _GROWTH_WINDOW
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
        if (
            (yoy or sequential)
            and count < _GROWTH_WINDOW
            and not (year_over_year and asked is not None)
        ):
            # Only a change that names no base gets here with a window under 5 ("how did
            # revenue change last quarter?"): it is read over 5 until the analyst says
            # against what. A change over a window of two or more quarters is year over
            # year over it, and a sequential window returned above.
            count = _GROWTH_WINDOW
        if year_over_year and change.explicit_yoy and asked is None:
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

    def rebase(self, patch: SpecPatch, change: ChangeAsked, on_screen: AnalysisSpec) -> SpecPatch:
        """ "Show that year over year" and "sequential instead" keep the quarters on screen.

        With no window named, year over year shows 8 quarters and growth 5: the 8
        were four quarters with the year before each, the 5 four with the year-earlier
        base of the newest. Each quarter's base is now the comparative its own filing
        reports (ADR 0009), so a window the analyst already has needs no extra rows,
        nor does a named period, read as on a window. A sequential change reads the
        quarter before the oldest one shown as its base, without showing it: after a
        year-over-year view, "sequential instead" switches the change to that one
        and keeps the quarters, as "year over year instead" switches back (ADR 0010).
        Runs after the company and metric edit: it acts only on an extend patch,
        which that edit makes of a follow-up.
        """
        shown = on_screen.periods
        if (
            patch.mode != "extend"
            or patch.set_periods is None
            or shown.kind == "latest_quarter"
            or (shown.kind == "last_n_quarters" and (shown.shown or 1) <= 1)
            or change.base not in ("year_over_year", "sequential")
            or self.reading.counted_window
            or self.reading.trailing_year
            or self.names_a_window
            or self.named
        ):
            return patch
        if change.both:
            # "Sequentially or versus last year": both changes on the quarters shown.
            return _sequential_on(patch, shown, both=True)
        if change.base == "sequential":
            return _sequential_on(patch, shown)
        # Year over year alone: a sequential change asked beside it goes.
        removed = tuple(dict.fromkeys([*patch.remove_operations, "sequential"]))
        if shown.company_base_dates is not None:
            # The quarters before a quarter-over-quarter change's named ones are no
            # longer a base.
            return patch.model_copy(
                update={
                    "set_periods": shown.model_copy(update={"company_base_dates": None}),
                    "remove_operations": removed,
                }
            )
        return patch.model_copy(update={"set_periods": None, "remove_operations": removed})


def _operations_with_change(
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


def _sequential_on(
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


# --- Dating the periods for each company ------------------------------------


@dataclass(frozen=True)
class Periods:
    """View of a spec's companies and period selection.

    ``dated`` is the one member that reads the filings; the rest are pure and
    work on any ``PeriodSelection``, dated or not.
    """

    spec: AnalysisSpec

    def dated(self, facts: FactsPort) -> Dated:
        """The spec with its quarters dated for each company from its own filings.

        A window lists quarter ends (or, since a fiscal year, fiscal periods);
        named periods list fiscal periods (ADR 0007). The first company (or first
        constituent) is listed alone and its failure raised; the rest are listed
        in spec order, a failure leaving that company unlisted, so it shares the
        window's dates. A spent session budget always stops the turn. Dates
        already on the spec are kept, so an added company lists only itself; a
        latest-quarter or already-dated spec is returned as it is. A window the
        filings cannot date is returned undated with the refusal, as is a named
        period no company filed for; the refusal is finished text.
        """
        spec = self.spec
        if spec.periods.kind == "named":
            spec = _named_periods_dated(spec, facts)
        elif spec.periods.kind == "last_n_quarters":
            spec = _window_dated(spec, facts)
        return Dated(spec=spec, refusal=_refusal(spec, facts))


@dataclass(frozen=True)
class Dated:
    """A spec dated against the filings, and the refusal when they cannot date it."""

    spec: AnalysisSpec
    # Finished text: a named period after the latest filing or outside the
    # filings, or a window with no quarters to date.
    refusal: str | None

    @property
    def periods(self) -> Periods:
        return Periods(self.spec)


def _refusal(spec: AnalysisSpec, facts: FactsPort) -> str | None:
    periods = spec.periods
    if periods.kind == "named" and spec.companies and not periods.report_dates:
        future = all(
            period.year > date.today().year for period in periods.named
        ) or _after_latest_filing(spec, facts)
        if future:
            return f"No filings found for {periods.label}: it has not been reported yet."
        return (
            f"No filings found for {periods.label}. Periods are fiscal years as each "
            "company names them; filings older than about ten years may not be available."
        )
    if periods.kind == "last_n_quarters" and not periods.report_dates:
        return "Could not determine quarterly report dates for the requested window"
    return None


def _window_dated(spec: AnalysisSpec, facts: FactsPort) -> AnalysisSpec:
    """A window's report dates from the filings.

    The first company's quarter ends become ``report_dates``; every other named
    company gets its own, so a company on a different fiscal calendar is asked
    for its quarters rather than the first company's.
    """
    first = spec.companies[0] if spec.companies else None
    if first is None and spec.constituents is not None and spec.constituents.members:
        first = spec.constituents.members[0]
    if first is None:
        return spec
    periods = spec.periods
    since = periods.since_year
    cap = periods.count or 1
    listing: Callable[..., _Listed]
    if since is not None and periods.since_fiscal:
        listing = partial(_fiscal_window_dates, facts.fiscal_periods, since=since)
    else:
        listing = partial(_window_dates, facts.list_quarterly_report_dates, since=since)
    spans: list[int] = []
    listed_first = False
    if not periods.report_dates:
        dates, span = listing(first.handle, limit=cap)
        if not dates:
            return spec
        # A "since" window asks for whatever the filings hold since that
        # January, so only a counted window can hold fewer than asked.
        asked = periods.asked or (
            periods.count
            if since is None and periods.count and len(dates) < periods.count
            else None
        )
        periods = periods.model_copy(
            update={"count": len(dates), "report_dates": dates, "asked": asked}
        )
        spans.extend([] if span is None else [span])
        listed_first = True
    known = dict(periods.company_report_dates)
    if listed_first and spec.companies:
        known[first.key] = periods.report_dates
    # Each company on its own calendar: a "since" window lists up to the cap and
    # keeps that company's quarters since the January; a counted one lists the count.
    count = cap if since is not None else periods.count or 1
    pending = _not_yet_listed(spec.companies, known)
    listed = map_in_order(
        lambda company: _or_none(partial(listing, company.handle, limit=count)),
        pending,
    )
    for company, company_listed in zip(pending, listed, strict=True):
        if company_listed is None:
            continue
        company_dates, span = company_listed
        if company_dates:
            known[company.key] = company_dates
        spans.extend([] if span is None else [span])
    periods = periods.model_copy(
        update={
            "company_report_dates": tuple(known.items()),
            "asked": _span_asked(periods, spans, [periods.report_dates, *known.values()]),
        }
    )
    if periods == spec.periods:
        return spec
    return spec.model_copy(update={"periods": periods})


# A company's quarter ends for a window, newest first, and the quarters its
# span holds when the listing counted them (a fiscal year's span).
_Listed = tuple[tuple[date, ...], int | None]


def _window_dates(
    list_dates: Callable[..., Sequence[date]], handle: str, *, limit: int, since: int | None
) -> _Listed:
    """A company's quarter ends for a window, newest first.

    For a "since" window, the listed quarters that ended on or after 1 January
    of that year; when none has (the year is ahead of the filings), the latest
    quarter, so the answer shows a figure rather than nothing.
    """
    dates = tuple(list_dates(handle, limit=limit))
    if since is None or not dates:
        return dates, None
    return quarters_since(since, dates) or dates[:1], None


def _fiscal_window_dates(
    list_periods: Callable[[str], Sequence[FiscalPeriod]], handle: str, *, limit: int, since: int
) -> _Listed:
    """A company's quarter ends since the start of its own fiscal ``since``, newest first.

    Read where its fiscal periods are listed, as a named fiscal year is: Apple's
    fiscal 2025 opens with the quarter ended December 2024, Microsoft's with
    September 2024. The span is counted on the company's labels, so the answer
    can say how many quarters the filings lack. A year ahead of the filings
    shows the latest quarter, as a calendar year does.
    """
    periods = tuple(list_periods(handle))
    if not periods:
        return (), None
    dates = quarters_since_fiscal_year(since, periods)[:limit]
    if not dates:
        return (max(period.end for period in periods),), None
    return dates, quarters_in_fiscal_span(since, periods)


def _span_asked(
    periods: PeriodSelection, spans: list[int], windows: list[tuple[date, ...]]
) -> int | None:
    """The quarters a fiscal span asks for, when the filings show fewer; else as it was."""
    shown = max((len(dates) for dates in windows), default=0)
    longest = max(spans, default=0)
    if longest <= shown:
        return periods.asked
    return max(periods.asked or 0, longest)


def _or_none[T](read: Callable[[], T]) -> T | None:
    """``read()``, or None when it fails.

    One company's failure must not refuse the whole window for the companies
    that do resolve: its cells report it. A spent session budget still stops
    the turn.
    """
    try:
        return read()
    except SessionQuotaError:
        raise
    except Exception:
        return None


def _not_yet_listed(
    companies: tuple[ResolvedCompany, ...], known: dict[str, Any]
) -> list[ResolvedCompany]:
    """The companies without report dates yet, each once, in the spec's order."""
    pending: dict[str, ResolvedCompany] = {}
    for company in companies:
        if company.key not in known:
            pending.setdefault(company.key, company)
    return list(pending.values())


def _named_dates(
    periods: Sequence[FiscalPeriod], named: tuple[NamedPeriodSpec, ...]
) -> tuple[date, ...]:
    matched = {
        day
        for spec in named
        for day in dates_for(tuple(periods), spec.year, spec.quarter, calendar=spec.calendar)
    }
    return tuple(sorted(matched, reverse=True))


def _quarters_before(listed: Sequence[FiscalPeriod], shown: tuple[date, ...]) -> tuple[date, ...]:
    """Each quarter end just before one of ``shown`` and not itself shown, newest first.

    A quarter the filings do not hold is left out: that quarter has no change.
    """
    ends = sorted({period.end for period in listed}, reverse=True)
    before = {
        older
        for newer, older in zip(ends, ends[1:], strict=False)
        if newer in shown and older not in shown and adjacent_quarters(newer, older)
    }
    return tuple(sorted(before, reverse=True))


def _named_periods_dated(spec: AnalysisSpec, facts: FactsPort) -> AnalysisSpec:
    """Each company's own quarter ends for the named periods (ADR 0007).

    "Q3 FY2024" is Apple's quarter ended June 29 and Microsoft's ended March 31;
    each company's filings say which is which. A company without a filing for
    the period gets no cells, and the turn says so.
    """
    lister = facts.fiscal_periods
    periods = spec.periods
    known = dict(periods.company_report_dates)
    bases = dict(periods.company_base_dates or ())
    pending = _not_yet_listed(spec.companies, known)
    listings = map_in_order(
        lambda company: _or_none(partial(lister, company.handle)), pending
    )
    for company, listed in zip(pending, listings, strict=True):
        if listed is not None:
            known[company.key] = _named_dates(listed, periods.named)
            if periods.company_base_dates is not None:
                bases[company.key] = _quarters_before(listed, known[company.key])
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
            "company_base_dates": (
                None if periods.company_base_dates is None else tuple(bases.items())
            ),
        }
    )
    if updated == periods:
        return spec
    return spec.model_copy(update={"periods": updated})


def _after_latest_filing(spec: AnalysisSpec, facts: FactsPort) -> bool:
    """Whether every named period ends after the first company's newest filed quarter.

    The first company's fiscal periods are listed again: the dating keeps no listing.
    """
    if not spec.companies:
        return False
    listed = _or_none(partial(facts.fiscal_periods, spec.companies[0].handle))
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
