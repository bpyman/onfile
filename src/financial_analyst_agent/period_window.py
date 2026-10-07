"""How many quarters a question's window asks for: one grammar for every wording.

"last 4 quarters", "the past six quarters", "previous nine quarters", "most
recent twelve quarters", "trailing seven quarters", "the 6 latest quarters",
"over 8 quarters", "the last couple of quarters", "past three years", "the
last 18 months": each is a recency word (or a preposition), a count and a
unit. The recency word may be left out after the metric: "Apple revenue 18
months", "6 quarters" and "a couple of years" are the same windows. Counts are
digits or words up to ninety-nine, "a couple" (2) or "a dozen" (12); "a few"
and "several" are read as 4 and said so. "The past decade" needs no count: it
is one. Years are four quarters each, decades forty, months a third of one
(rounded up, and said so). A window is capped at ``MAX_QUARTERS_ASKED``
quarters, and that is said too.

A count that names something else is not a window: "3 months ended June"
names a quarter, "2 quarters ago" names one quarter, and "12-month" in
"trailing 12-month revenue" is the trailing year (no space between count and
unit).
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

from financial_analyst_agent.graph.analysis_spec import MAX_QUARTERS_ASKED

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
_COUNT = (
    rf"(?P<count>\d+|{_WORD_NUMBER}|(?:a\s+)?(?:couple|pair|dozen)(?:\s+of)?"
    r"|(?:a\s+)?few|several)"
)
_UNIT = (
    r"(?P<unit>(?:fiscal\s+|calendar\s+)?(?:quarters?|qtrs?|qs|years?|yrs?)|months?|decades?)"
    # "3 months ended June" names a quarter; "2 quarters ago" names one quarter.
    r"(?![\w-])(?!\s+(?:ended|ending|ago|from now|later)\b)"
)
_RECENT = r"(?:last|past|previous|prior|trailing|most\s+recent|recent|latest|preceding)"
_WINDOW_PATTERNS = (
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


@dataclass(frozen=True)
class AskedWindow:
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


def asked_window(message: str) -> AskedWindow | None:
    """The window the message asks for, or None when it names no count of periods."""
    found = [match for pattern in _WINDOW_PATTERNS if (match := pattern.search(message))]
    if not found:
        return None
    match = min(found, key=lambda candidate: candidate.start())
    said_count = match.groupdict().get("count")
    count, approximate = _count(said_count) if said_count is not None else (1, False)
    unit = match.group("unit").casefold().split()[-1].rstrip("s")
    if unit == "month":
        quarters = math.ceil(count / 3)
        approximate = approximate or count % 3 != 0
    else:
        quarters = count * _QUARTERS_PER[unit]
    quarters = max(quarters, 1)
    capped = quarters if quarters > MAX_QUARTERS_ASKED else None
    return AskedWindow(
        quarters=min(quarters, MAX_QUARTERS_ASKED),
        said=" ".join(match.group(0).split()),
        capped_from=capped,
        approximate=approximate,
    )
