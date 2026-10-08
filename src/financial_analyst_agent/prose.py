"""Sentence helpers: dates, lists, possessives and short company names in prose."""

from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import date

_SUFFIX = re.compile(
    r"(?:,?\s+(?:inc|incorporated|corp|corporation|co|company|ltd|plc|holdings|group"
    r"|& co|& company|and company|a/s|ag|s\.?a|n\.?v|se)\.?)+$",
    re.IGNORECASE,
)


_MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def format_date(value: date) -> str:
    """ "Mar 31, 2026", the same whatever the locale."""
    return f"{_MONTHS[value.month - 1]} {value.day}, {value.year}"


def joined(words: Sequence[str], conjunction: str = "and") -> str:
    """Words in prose: "A", "A and B", "A, B and C"."""
    if len(words) <= 1:
        return "".join(words)
    return f"{', '.join(words[:-1])} {conjunction} {words[-1]}"


def in_sentence(label: str) -> str:
    """ "Net margin" → "net margin" mid-sentence; "EBITDA" and "P/E ratio" keep their case."""
    if len(label) > 1 and (label[1].isupper() or not label[1].isalpha()):
        return label
    return label[:1].lower() + label[1:]


def possessive(name: str) -> str:
    """ "Apple's", "Abbott Laboratories'", and "Lowe's" left as it is."""
    if name.endswith(("'s", "’s")):
        return name
    return f"{name}'" if name.endswith("s") else f"{name}'s"


def short_name(name: str) -> str:
    """ "NVIDIA Corporation" → "NVIDIA"; "Eli Lilly and Company" → "Eli Lilly"."""
    short = _SUFFIX.sub("", name.strip()).strip(" ,.")
    # "The Goldman Sachs Group, Inc." reads as "Goldman Sachs".
    return re.sub(r"^the\s+(?=\S)", "", short, flags=re.IGNORECASE)
