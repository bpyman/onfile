"""The words of a ranking: its count, and the group they name (ADR 0010).

Both planners' rankings pass through here. The rules planner reads a ranking's
group from these words when it plans one, and the analysis graph reads it again
from the same words when a planner's proposal leaves the group out or paraphrases
every company, so the group the graph checks cannot drift from the group the
plan uses.
"""

from __future__ import annotations

import re

from financial_analyst_agent.contracts import DEFAULT_RANK_LIMIT
from financial_analyst_agent.issuer_index import expand_groups, plain_text
from financial_analyst_agent.request_wording import ASCENDING, DESCENDING
from financial_analyst_agent.services.metric_catalog import (
    resolve_metric_phrase,
    resolve_metric_phrases,
)
from financial_analyst_agent.universe import WHOLE_MARKET

_COUNT_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "fifteen": 15,
    "twenty": 20, "twenty five": 25, "twenty-five": 25, "a dozen": 12, "dozen": 12,
}  # fmt: skip
_COUNT_WORD = "|".join(sorted(map(re.escape, _COUNT_WORDS), key=len, reverse=True))
# "which five banks", "the two largest", "list three chipmakers": a count of a
# group. "One" is left alone: "which one is bigger" asks about the screen.
# "The" counts a group only before a size word: "compare the two" is the screen.
_GROUP_COUNTED_BY = (
    r"(which|rank|list|show|name|the(?=\s+\S+\s+(?:largest|biggest|most|top|leading)\b))"
)
_GROUP_COUNT_WORD = re.compile(
    rf"\b{_GROUP_COUNTED_BY}\s+"
    rf"({'|'.join(word for word in sorted(_COUNT_WORDS, key=len, reverse=True) if word != 'one')})"
    rf"\b(?!\s+(?:quarters?|years?|months?|of\b))",
    re.IGNORECASE,
)
GROUP_COUNT = re.compile(rf"\b{_GROUP_COUNTED_BY}\s+(\d+)\b(?!\s+(?:quarters?|years?|months?))")
# "top five banks" is five banks, not Five Below.
_RANK_COUNT_WORD = re.compile(
    rf"\b(top|biggest|largest|leading)\s+({_COUNT_WORD})\b"
    rf"|\b({_COUNT_WORD})\s+(biggest|largest)\b",
    re.IGNORECASE,
)
_ODD_COUNT = re.compile(r"\b(top|biggest|largest|leading)\s+(-\s*\d+|\d+\.\d+|0+)(?=\s|$)", re.I)


def _count_words_as_digits(query: str) -> str:
    """ "Top five banks" → "top 5 banks", so the count is read and Five Below is not.

    A count after "which", "the", "rank" or "list" counts a group too: "which
    five banks", "the two largest banks", "list three chipmakers".
    """

    def digits(match: re.Match[str]) -> str:
        if match.group(1):
            return f"{match.group(1)} {_COUNT_WORDS[match.group(2).casefold()]}"
        return f"{_COUNT_WORDS[match.group(3).casefold()]} {match.group(4)}"

    def group_count(match: re.Match[str]) -> str:
        return f"{match.group(1)} {_COUNT_WORDS[match.group(2).casefold()]}"

    return _GROUP_COUNT_WORD.sub(group_count, _RANK_COUNT_WORD.sub(digits, query))


def _whole_counts(query: str) -> tuple[str, list[str]]:
    """ "top -5", "top 5.5" and "top 0" as a count a ranking can list, said in a note."""
    notes: list[str] = []

    def count(match: re.Match[str]) -> str:
        raw = match.group(2).replace(" ", "")
        whole = abs(int(float(raw)))
        if whole == 0:
            notes.append(
                f"A ranking lists at least one company, so this shows the top {DEFAULT_RANK_LIMIT}."
            )
            whole = DEFAULT_RANK_LIMIT
        else:
            notes.append(f"I read “{match.group(0)}” as the top {whole}.")
        return f"{match.group(1)} {whole}"

    return _ODD_COUNT.sub(count, query), notes


def prepared(query: str) -> tuple[str, list[str]]:
    """The question as the planner reads it, and the notes its counts earn.

    Group nicknames are spelled out, markup is dropped, counts in words become
    digits, and an odd count ("top 0", "top 5.5") becomes one a ranking can
    list, said in a note.
    """
    return _whole_counts(_count_words_as_digits(expand_groups(plain_text(query))))


RANK_WORDS = re.compile(
    r"\b(?:top|biggest|largest|leading|rank|ranked|ranking)\b"
    # "worth the most", "most valuable": the largest by market cap.
    r"|\bworth the most\b|\bmost valuable\b"
)
# "Which tech company has the highest net margin?" ranks an industry by a metric.
WHICH_HIGHEST = re.compile(
    r"\bwhich\s+(?P<group>[a-z&][a-z&\- ]*?)\s+"
    r"(?P<noun>companies|company|stocks|stock|firms|firm)?\s*"
    r"(?:has|have|had|is|are|with)\s+the\s+(?:highest|most|biggest|largest|best|greatest|top)\b"
)
_LEADING_CLAUSE = re.compile(r"^(?P<lead>[^,]+),\s*(?P<rest>.+)$")


def without_preamble(normalized: str) -> str:
    """A ranking after a leading clause, alone: "this quarter, top 5 banks by …".

    The clause before the first comma is dropped when it names no measure and
    ranks nothing itself, and what follows it is a ranking.
    """
    match = _LEADING_CLAUSE.match(normalized)
    if match is None:
        return normalized
    lead, rest = match.group("lead"), match.group("rest")
    if RANK_WORDS.search(lead) or resolve_metric_phrases(lead):
        return normalized
    if RANK_WORDS.search(rest) or group_by_metric(rest) is not None:
        return rest
    return normalized


# "chipmakers by free cash flow": a group and "by" a metric, with no "top", is a
# ranking of the README's default length.
_GROUP_BY_METRIC = re.compile(
    r"^(?:(?:the|show|show me|list)\s+)?(?:\d+\s+(?!(?:quarters?|years?|months?)\b))?"
    r"(?P<group>[a-z&][a-z&\- ]*?)"
    r"(?:\s+(?:companies|stocks|firms|names))?\s+by\s+(?P<rest>.+)$"
)
_GROUP_BY_METRIC_MAX_WORDS = 3


def group_by_metric(normalized: str) -> str | None:
    """The group of "<group> by <metric>", or None when the words name no group.

    The group is a few words that name no metric ("revenue by segment" is a
    metric cut by something, not a group), and what follows "by" is a metric.
    """
    match = _GROUP_BY_METRIC.match(normalized.strip(" .?!"))
    if match is None:
        return None
    group = match.group("group").strip()
    if not group or len(group.split()) > _GROUP_BY_METRIC_MAX_WORDS:
        return None
    if resolve_metric_phrase(group).kind != "unknown":
        return None
    after = resolve_metric_phrase(match.group("rest"))
    if after.kind == "unknown" and after.term is None:
        return None
    return group


def _normalize_industry_label(raw: str) -> str:
    label = re.split(r"\s+\band\b", raw.strip(), maxsplit=1)[0]
    return label.strip(" .,?!").strip()


def _industry_from_query(normalized: str) -> str:
    for pattern in (
        r"\btop\s+\d+\s+companies\s+in\s+(.+)",
        r"\btop\s+\d+\s+(.+?)\s+companies\b",
        r"\bin\s+(.+)",
        r"\btop\s+\d+\s+(.+)",
    ):
        match = re.search(pattern, normalized)
        if match is not None:
            label = _normalize_industry_label(match.group(1))
            if label and not re.match(r"(?:by|in terms of)\b", label):
                return label
    # "top 5 by revenue" names no industry: the whole snapshot is ranked.
    return WHOLE_MARKET


# Words before an industry that say how a ranking is cut, not which group it is.
_GROUP_LEAD = re.compile(
    r"^(?:(?:the|top|\d+|biggest|largest|leading|most valuable|best)\s+)+", re.IGNORECASE
)
_COUNT_NOUN_PLURALS = {"company": "companies", "stock": "stocks", "firm": "firms"}
# Everyday words for an industry the snapshot names otherwise.
_INDUSTRY_WORDS = {
    word: "automakers"
    for word in (
        "ev", "evs", "electric vehicle", "electric vehicles", "electric vehicle makers",
        "ev makers", "car", "cars", "car makers", "carmakers", "auto", "autos",
    )
}  # fmt: skip


def _clean_group(industry: str) -> str:
    """The group alone: "5 banks" and "largest banks" rank banks."""
    return _GROUP_LEAD.sub("", industry).strip() or industry


def _plural_group(group: str) -> str:
    """ "which bank has …" ranks banks; "which tech company" ranks tech."""
    words = group.split()
    if not words or words[-1].endswith("s"):
        return group
    last = words[-1]
    if last in _COUNT_NOUN_PLURALS:
        plural = _COUNT_NOUN_PLURALS[last]
    elif last.endswith("y") and last[-2:-1] not in ("a", "e", "o", "u"):
        plural = last[:-1] + "ies"
    else:
        plural = last + "s"
    return " ".join([*words[:-1], plural])


def _ranked_industry(normalized: str) -> str:
    """The group a ranking names: "top 5 semiconductor companies", "biggest banks"."""
    # "top 5 banks lowest first": the order's direction is not part of the group.
    text = DESCENDING.sub("", ASCENDING.sub("", normalized))
    text = re.sub(r"\b(?:by|in terms of|ranked by)\b.*$", "", text)
    # "oil and gas" is one industry, not a list to cut at "and".
    text = re.sub(r"\boil and gas\b", "oil & gas", text)
    text = re.split(r"\s+(?:and|with|plus)\s+|,", text, maxsplit=1)[0]
    match = (
        re.search(
            r"\b(?:top|biggest|largest|leading|most valuable|rank(?:ed)?)\s+(?:the\s+)?"
            r"(?:top\s+)?(?:\d+\s+)?"
            r"(?:companies\s+in\s+(?:the\s+)?)?(.+)$",
            text,
        )
        or re.search(r"\b\d+\s+(?:biggest|largest)\s+(.+)$", text)
        # "which 3 chipmakers are worth the most"
        or re.search(r"\bwhich\s+(?:\d+\s+)?(.+?)\s+(?:are|is|has|have|had)\b", text)
    )
    if match is None:
        match = re.search(r"\b(?:in|among|within|across)\s+(.+)$", text)
    if match is None:
        return _industry_from_query(normalized)
    label = re.sub(
        r"^(?:companies|stocks|firms|names)\s+(?=(?:in|among|within|across)\b)", "", match.group(1)
    )
    # "rank in tech", "top 5 in banking": the preposition is not the industry.
    label = re.sub(r"^(?:in|among|within|across|of|for|from)\s+", "", label)
    label = re.sub(r"\s+(?:companies|stocks|firms|names)\b.*$", "", label)
    label = re.sub(r"^(?:companies|stocks|firms|names)$", "", label)
    label = re.sub(r"\b(?:the|us|u s|american)\s+", "", label)
    label = label.strip(" .,?!")
    return label or _industry_from_query(normalized)


def group_named(ranking: str, which: re.Match[str] | None, group_by: str | None) -> str:
    """The group a ranking names, from "which bank has the most", "banks by" or "top 5 banks"."""
    if which is not None:
        group = which.group("group")
        industry = group if which.group("noun") else _plural_group(group)
    elif group_by is not None:
        industry = group_by
    else:
        industry = _ranked_industry(ranking)
    industry = _clean_group(industry)
    return _INDUSTRY_WORDS.get(industry, industry)


def ranking_group(ranking: str) -> str:
    """The group a ranking that names no company is of, from its prepared, lower-cased words.

    "Which bank has the most …" names banks; "chipmakers by free cash flow"
    names chipmakers, with no rank word; otherwise the words after "top 5",
    "largest" or "rank".
    """
    which = WHICH_HIGHEST.search(ranking)
    rank_words = RANK_WORDS.search(ranking) is not None
    group_by = group_by_metric(ranking) if not rank_words else None
    return group_named(ranking, which, group_by)


def ranked_group(query: str) -> str:
    """The group a ranking's words name, read as the rules planner reads them.

    ``WHOLE_MARKET`` when they name none ("which companies are worth the most?");
    otherwise the words, known to the snapshot or not ("top 10 companies in AI").
    """
    query, _ = prepared(query)
    return ranking_group(without_preamble(query.strip().casefold()))
