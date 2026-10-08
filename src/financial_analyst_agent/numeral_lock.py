"""The numeral lock: an essay may quote only the numbers its grounding holds (story 30).

``numeral_lock_extras`` lists the figures an essay quotes that its grounding JSON
does not contain, written as the grounding holds them, as the window shows them,
or rounded at the precision shown; dates, citation markers and the digits of
links and identifiers are not figures. ``numeral_lock_message`` is the refusal
that names them. The turn, the filing-change summary and the MCP server all
hold essays to it; ``numeral_lock_evaluation`` measures it on known sentences.
"""

import json
import re
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any

__all__ = ["numeral_lock_extras", "numeral_lock_message"]

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


def numeral_lock_extras(essay: str, tool_json: str, *, hit_count: int = 0) -> list[str]:
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


def numeral_lock_message(invented: str) -> str:
    return (
        "The written answer was withheld because it quoted numbers its sources "
        f"do not contain: {invented}."
    )
