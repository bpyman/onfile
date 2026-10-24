"""Management's explanation: the MD&A paragraphs that explain a figure's move (ADR 0017).

Code chooses them, from the filing the figure came from, and they are quoted verbatim.
No model reads the filing and nothing is fetched here: the caller passes the filing's
HTML, the catalog metric and the comparison base the question asked for.

A paragraph is chosen only when it names the metric in the MD&A's own words, and that
sentence or the next says the metric changed or why. It must also:

- compare on the basis asked: a sequential question needs a paragraph that says it
  compares with the quarter before ("sequentially", "compared to the second quarter of
  2026" beside the third); a year-over-year question takes any paragraph but one that
  compares only sequentially, since a 10-Q compares with a year earlier by default;
- explain the quarter: a cause given only for the year to date ("first nine months")
  does not count, unless the paragraph says it holds for both periods;
- be prose: a block of fewer than eight words, or with no verb, is a heading.

A sequential question that finds nothing, where a year-over-year one would, gets
``basis_not_discussed`` with those paragraphs as the alternative. It is scored on:

- how often it names the metric;
- whether a sentence naming the metric gives a cause ("primarily due to", "driven by"),
  more when that sentence is about the quarter rather than only the year to date;
- causal and change wording anywhere in it;
- whether its comparison is the one asked for (year over year or sequential);
- whether it talks about a quarter, and whether it opens on the company-wide figure
  ("Total revenues") rather than a segment's ("Services revenue");
- and it loses points for looking ahead ("we expect") or defining a term.

A paragraph whose subject is another metric ("Operating income was $2.0 billion … The
increase in operating income was due to higher gross profit") is never chosen
(``is_about_another_metric``): with nothing about this metric, the answer is that the
MD&A does not discuss it. A paragraph about the cash balance, liquidity, or financing or
investing cash flows is about another metric for every metric covered. Ties keep the
filing's order. Cash flow and capex are not covered for now (``_METRIC_FAMILY``).
The weights are a first cut; the explanation evaluation measures them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from financial_analyst_agent.contracts import ComparisonBase
from financial_analyst_agent.filing_change import (
    extract_section,
    filing_anchor_url,
    section_paragraphs,
)

MAX_PARAGRAPHS = 3

# ``basis_not_discussed``: a sequential question found nothing, but the MD&A explains
# the same metric against a year earlier; those paragraphs come as the alternative.
NothingFound = Literal[
    "mda_not_found", "not_discussed", "basis_not_discussed", "metric_not_covered"
]


def _words(*phrases: str) -> re.Pattern[str]:
    # Not after a hyphen: "non-operating income" is not operating income.
    return re.compile(r"(?<![\w-])(?:" + "|".join(phrases) + r")\b", re.IGNORECASE)


# The words a family of metrics goes by in MD&A prose. Related catalog metrics share
# a family: a paragraph about gross profit explains gross margin, and cost of sales
# is how filings talk about both.
_FAMILY_WORDS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("revenue", _words(r"revenues?", r"net sales", r"sales")),
    (
        "gross",
        _words(
            r"gross margins?",
            r"gross profits?",
            # "Cost of sales"; Tesla's "cost of energy generation and storage revenue".
            r"costs? of (?:[\w&-]+ ){0,5}?(?:sales|revenues?|goods sold|products sold)",
        ),
    ),
    (
        "operating",
        _words(
            r"operating income",
            r"operating (?:loss|losses|profit)",
            r"(?:income|loss) from operations",
            r"operating margins?",
        ),
    ),
    ("net", _words(r"net income", r"net earnings", r"net loss")),
    ("rd", _words(r"research and development", r"R&D")),
    (
        "sga",
        _words(
            r"(?:selling|sales), general,? and administrative",
            r"selling, informational,? and administrative",
            r"marketing, general,? and administrative",
            r"general and administrative",
            r"(?:sales|selling) and marketing",
            r"SG&A",
        ),
    ),
    (
        "operating_cash",
        _words(
            r"cash (?:provided by|generated (?:by|from)|from|used in|flows? from) "
            r"operating activities",
            r"operating cash flows?",
            r"cash flows? from operations",
        ),
    ),
    (
        "capex",
        _words(
            r"capital expenditures?",
            r"capital spending",
            r"purchases of property,? (?:plant,? )?and equipment",
            r"additions to property,? (?:plant,? )?and equipment",
        ),
    ),
    ("free_cash", _words(r"free cash flows?")),
    # No catalog metric: a paragraph whose subject is the cash balance, liquidity, or
    # financing or investing cash flows is about another metric, whatever was asked.
    (
        "cash_balance",
        _words(
            r"cash,? (?:and )?cash equivalents",
            r"cash balances?",
            r"cash position",
            r"liquidity",
            r"(?:financing|investing) activities",
        ),
    ),
)

_FAMILY_PATTERNS = dict(_FAMILY_WORDS)

# Catalog metrics with words, by family. A metric not here gets no explanation.
_METRIC_FAMILY: dict[str, str] = {
    "revenue": "revenue",
    "gross_margin": "gross",
    "gross_profit": "gross",
    "cost_of_revenue": "gross",
    "operating_income": "operating",
    "operating_margin": "operating",
    "net_income": "net",
    "net_margin": "net",
    "research_and_development": "rd",
    "rd_to_sales": "rd",
    "selling_general_and_administrative": "sga",
    "sga_ratio": "sga",
    # Left out for now: the first judge run found these questions landing on cash-balance
    # and financing paragraphs, and the causes MD&As give are for the year to date. Their
    # words stay above, so a cash-flow paragraph is still about another metric.
    # "operating_cash_flow": "operating_cash",
    # "capital_expenditure": "capex",
    # "free_cash_flow": "free_cash",
}

# Wording that gives a cause. The qualifier ("primarily", "partially") belongs to the clause.
_CAUSAL = re.compile(
    r"\b(?:(?:primarily|mainly|largely|principally|partially|partly|in part)\s+)?"
    r"(?:due (?:primarily |mainly |largely |in part )?to|driven (?:primarily |mainly |"
    r"largely |in part )?by|as a result of|attributable to|offset by|reflect(?:s|ed|ing)?|"
    r"because of|led by|resulting from|owing to)\b",
    re.IGNORECASE,
)
_CHANGE = re.compile(
    r"\b(?:increas|decreas|grew|grow|declin|rose|fell|higher|lower|improv|expand|contract|"
    r"flat\b|up \d|down \d)\w*",
    re.IGNORECASE,
)
_YEAR_OVER_YEAR = re.compile(
    r"\b(?:compared (?:to|with) (?:the )?(?:same|corresponding|comparable|prior[- ]year) "
    r"(?:period|quarter)s?|from a year ago|year[- ]over[- ]year|prior[- ]year (?:period|quarter)s?"
    r"|same (?:period|quarter) (?:of |in )?(?:the )?(?:prior|last|previous) year)\b",
    re.IGNORECASE,
)
_SEQUENTIAL = re.compile(
    r"\b(?:sequential(?:ly)?|quarter[- ]over[- ]quarter|(?:prior|previous|preceding) quarter)\b",
    re.IGNORECASE,
)
# "the third quarter of 2026", "the second quarter of fiscal year 2027".
_NAMED_QUARTER = re.compile(
    r"\b(first|second|third|fourth) quarter of (?:fiscal (?:year )?)?(\d{4})\b",
    re.IGNORECASE,
)
_ORDINALS = {"first": 1, "second": 2, "third": 3, "fourth": 4}
_QUARTER = re.compile(r"\b(?:quarter|three (?:and (?:six|nine) )?months)\b", re.IGNORECASE)
_YEAR_TO_DATE = re.compile(
    r"\b(?:(?:six|nine) months|first (?:half|three quarters)|year[- ]to[- ]date)\b",
    re.IGNORECASE,
)
# "The increase in both periods was driven by …": a year-to-date cause said of the quarter.
_BOTH_PERIODS = re.compile(r"\b(?:both|each of the|all) periods\b", re.IGNORECASE)
# A block of fewer words, or with no verb, is a heading or a caption ("Cost of products sold").
_FEWEST_WORDS = 8
_VERB = re.compile(
    r"\b(?:is|are|was|were|be|been|being|has|have|had|will|would|could|may|might|can|"
    r"grew|grow|grows|rose|rise|rises|fell|fall|falls|drove|drives|remains?|reflects?|"
    r"includes?|"
    # A past tense; not the participles of a caption ("three months ended", "related").
    r"(?!(?:ended|based|related|consolidated|combined|selected|unaudited|diluted|adjusted|"
    r"weighted|limited|united|detailed)\b)\w{3,}ed)\b",
    re.IGNORECASE,
)
_LOOKING_AHEAD = re.compile(
    r"\b(?:we (?:expect|anticipate|plan|intend)|outlook|guidance)\b", re.IGNORECASE
)
_DEFINITION = re.compile(r"\b(?:is defined as|we define|is calculated as)\b", re.IGNORECASE)
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+(?=[A-Z“\"(])")
# A clause ends at a semicolon or a full stop that ends its sentence, not at "U.S. government".
_CLAUSE_END = re.compile(r";|\.(?=\s+[A-Z“\"(]|\s*$)")

# What may stand before the metric's words when a sentence is about the whole
# company ("Total revenues", "Our consolidated gross margin"), not a segment's
# ("Services revenue", "Data Center operating income").
_WHOLE_COMPANY = re.compile(
    r"(?:(?:our|the|total|consolidated|overall|company['’]s)\s+)*", re.IGNORECASE
)

_CAPPED = 3
# Points for where the first causal clause sits (``_first_cause``'s strength).
_CAUSE_BESIDE_METRIC = (0, 6, 9)
_WHOLE_COMPANY_POINTS = 3


@dataclass(frozen=True)
class ExplainingParagraph:
    """One MD&A paragraph, verbatim, with its score, first causal clause and link."""

    text: str
    score: int
    # Character offsets of the first causal clause in ``text``, or None.
    cause: tuple[int, int] | None
    url: str


@dataclass(frozen=True)
class ManagementExplanation:
    """Up to three paragraphs in score order, or none and the reason.

    With ``basis_not_discussed``, ``alternative`` holds the paragraphs a year-over-year
    question on the same filing and metric gets.
    """

    paragraphs: tuple[ExplainingParagraph, ...]
    reason: NothingFound | None = None
    alternative: tuple[ExplainingParagraph, ...] = ()


def explained_metrics() -> tuple[str, ...]:
    """Catalog metrics the MD&A has words for."""
    return tuple(_METRIC_FAMILY)


def _family_mentions(paragraph: str) -> dict[str, int]:
    """How often each family's words appear, in the order the families are first named.

    Where two families' words overlap, the longer wins: "cost of sales" names gross
    margin, not revenue. A family not named is absent.
    """
    found: list[tuple[int, int, str]] = []
    for family, pattern in _FAMILY_WORDS:
        found.extend((match.start(), -match.end(), family) for match in pattern.finditer(paragraph))
    found.sort()
    counts: dict[str, int] = {}
    taken_until = -1
    for start, negative_end, family in found:
        if start < taken_until:
            continue
        counts[family] = counts.get(family, 0) + 1
        taken_until = -negative_end
    return counts


def mentions_metric(paragraph: str, metric: str) -> bool:
    """Whether a paragraph names the metric in the MD&A's words."""
    family = _METRIC_FAMILY.get(metric)
    return family is not None and family in _family_mentions(paragraph)


def is_about_another_metric(paragraph: str, metric: str) -> bool:
    """Whether the paragraph's subject is another metric.

    It is when another metric's words outnumber this one's, or match them and come
    first ("Cash provided by operating activities increased … due to higher
    revenue" is about cash flow), or when its first sentence names another metric
    and not this one ("Total gross margin decreased by 2.0 percentage points." opens
    a summary that goes on to revenue).
    """
    family = _METRIC_FAMILY.get(metric)
    if family is None:
        return False
    counts = _family_mentions(paragraph)
    own = counts.get(family, 0)
    named = list(counts)
    named_before = named[: named.index(family)] if family in counts else named
    if any(count > own for count in counts.values()):
        return True
    if any(counts[other] >= own for other in named_before):
        return True
    start, end = _sentences(paragraph)[0]
    opening = _family_mentions(paragraph[start:end])
    return bool(opening) and family not in opening


def _sentences(paragraph: str) -> list[tuple[int, int]]:
    spans = []
    start = 0
    for boundary in _SENTENCE_END.finditer(paragraph):
        spans.append((start, boundary.start()))
        start = boundary.end()
    spans.append((start, len(paragraph)))
    return spans


def _causal_clause(paragraph: str, start: int, end: int) -> tuple[int, int] | None:
    match = _CAUSAL.search(paragraph, start, end)
    if match is None:
        return None
    stop = _CLAUSE_END.search(paragraph, match.end(), end)
    clause_end = stop.start() if stop else end
    return match.start(), len(paragraph[:clause_end].rstrip())


def _first_cause(paragraph: str, family: str) -> tuple[tuple[int, int] | None, int]:
    """The first causal clause, preferring one in a sentence about the metric's quarter.

    The strength says where it sits: 2 in a sentence naming the metric and the
    quarter, 1 in one naming the metric only for the year to date ("the first nine
    months"), 0 elsewhere.
    """
    best: tuple[tuple[int, int] | None, int] = (None, 0)
    for start, end in _sentences(paragraph):
        clause = _causal_clause(paragraph, start, end)
        if clause is None:
            continue
        sentence = paragraph[start:end]
        strength = 0
        if family in _family_mentions(sentence):
            strength = 2 if _QUARTER.search(sentence) else 1
        if best[0] is None or strength > best[1]:
            best = (clause, strength)
    return best


def _opens_on_whole_company(paragraph: str, family: str) -> bool:
    """Whether the first sentence names the metric for the whole company, first thing."""
    start, end = _sentences(paragraph)[0]
    match = _FAMILY_PATTERNS[family].search(paragraph, start, end)
    if match is None:
        return False
    return _WHOLE_COMPANY.fullmatch(paragraph[start : match.start()].lstrip()) is not None


def _bases(paragraph: str) -> set[ComparisonBase]:
    """The comparisons a paragraph makes, from its wording and the quarters it names."""
    bases: set[ComparisonBase] = set()
    if _YEAR_OVER_YEAR.search(paragraph):
        bases.add("year_over_year")
    if _SEQUENTIAL.search(paragraph):
        bases.add("sequential")
    for start, end in _sentences(paragraph):
        quarters = [
            (_ORDINALS[match.group(1).lower()], int(match.group(2)))
            for match in _NAMED_QUARTER.finditer(paragraph, start, end)
        ]
        for index, (ordinal, year) in enumerate(quarters):
            for other_ordinal, other_year in quarters[index + 1 :]:
                if ordinal == other_ordinal and year != other_year:
                    bases.add("year_over_year")
                elif abs((year * 4 + ordinal) - (other_year * 4 + other_ordinal)) == 1:
                    bases.add("sequential")
    return bases


def _says_metric_moved(paragraph: str, family: str) -> bool:
    """Whether a sentence naming the metric, or the next one, gives a change or a cause.

    "Gross margin was 54% and 40% … The increase in both periods was driven by …"
    """
    sentences = _sentences(paragraph)
    for index, (start, end) in enumerate(sentences):
        if family not in _family_mentions(paragraph[start:end]):
            continue
        for near_start, near_end in sentences[index : index + 2]:
            sentence = paragraph[near_start:near_end]
            if _CAUSAL.search(sentence) or _CHANGE.search(sentence):
                return True
    return False


def _is_heading(paragraph: str) -> bool:
    """A block of fewer than eight words, or with no verb: a heading or a caption."""
    return len(paragraph.split()) < _FEWEST_WORDS or _VERB.search(paragraph) is None


def _compares_on(paragraph: str, basis: ComparisonBase | None) -> bool:
    """Whether the paragraph's comparison can answer the basis asked.

    Sequential needs the paragraph to say it compares with the quarter before. Year
    over year takes any paragraph but one comparing only sequentially: a 10-Q's MD&A
    compares with the year-earlier quarter unless it says otherwise.
    """
    if basis is None:
        return True
    bases = _bases(paragraph)
    if basis == "sequential":
        return "sequential" in bases
    return bases != {"sequential"}


def _only_for_the_year_to_date(paragraph: str) -> bool:
    """Whether the paragraph explains only the year to date, not the quarter.

    Each sentence's period is the one it names (the quarter, or the year to date:
    "first nine months", "six months ended"), or else the last one named before it.
    The paragraph is the year to date's when every causal sentence is, or, with no
    cause, every sentence is, unless it says its cause holds "in both periods".
    """
    if _BOTH_PERIODS.search(paragraph):
        return False
    period: str | None = None
    periods: list[str | None] = []
    causal: list[str | None] = []
    for start, end in _sentences(paragraph):
        sentence = paragraph[start:end]
        if _QUARTER.search(sentence):
            period = "quarter"
        elif _YEAR_TO_DATE.search(sentence):
            period = "year_to_date"
        periods.append(period)
        if _CAUSAL.search(sentence):
            causal.append(period)
    return all(named == "year_to_date" for named in causal or periods)


def _score(
    paragraph: str, family: str, basis: ComparisonBase | None
) -> tuple[int, tuple[int, int] | None] | None:
    """A paragraph's score and first causal clause, or None when it cannot be chosen."""
    if _is_heading(paragraph) or not _says_metric_moved(paragraph, family):
        return None
    if not _compares_on(paragraph, basis) or _only_for_the_year_to_date(paragraph):
        return None
    mentions = _family_mentions(paragraph)[family]
    causes = len(_CAUSAL.findall(paragraph))
    changes = len(_CHANGE.findall(paragraph))
    cause, strength = _first_cause(paragraph, family)
    score = 2 * min(mentions, _CAPPED) + 2 * min(causes, _CAPPED) + min(changes, _CAPPED)
    score += _CAUSE_BESIDE_METRIC[strength]
    if basis is not None and basis in _bases(paragraph):
        score += 3
    if _QUARTER.search(paragraph):
        score += 2
    if _opens_on_whole_company(paragraph, family):
        score += _WHOLE_COMPANY_POINTS
    if _LOOKING_AHEAD.search(paragraph):
        score -= 4
    if _DEFINITION.search(paragraph):
        score -= 4
    return score, cause


def management_explanation(
    html: str, metric: str, basis: ComparisonBase | None, source_url: str
) -> ManagementExplanation:
    """The MD&A paragraphs of a filing that explain the metric's move, best first."""
    family = _METRIC_FAMILY.get(metric)
    if family is None:
        return ManagementExplanation((), "metric_not_covered")
    paragraphs = section_paragraphs(extract_section(html, "mda"))
    if not paragraphs:
        return ManagementExplanation((), "mda_not_found")
    chosen = _choose(paragraphs, metric, family, basis, source_url)
    if chosen:
        return ManagementExplanation(chosen)
    if basis == "sequential":
        # 10-Qs explain the quarter against a year earlier; say so, and offer that.
        alternative = _choose(paragraphs, metric, family, "year_over_year", source_url)
        if alternative:
            return ManagementExplanation((), "basis_not_discussed", alternative)
    return ManagementExplanation((), "not_discussed")


def _choose(
    paragraphs: list[str],
    metric: str,
    family: str,
    basis: ComparisonBase | None,
    source_url: str,
) -> tuple[ExplainingParagraph, ...]:
    ranked: list[tuple[int, int, ExplainingParagraph]] = []
    for position, paragraph in enumerate(paragraphs):
        # A paragraph about another metric is never shown: with nothing about this
        # one, the honest answer is that the MD&A does not discuss it (ADR 0017).
        if is_about_another_metric(paragraph, metric):
            continue
        scored = _score(paragraph, family, basis)
        if scored is None:
            continue
        score, cause = scored
        chosen = ExplainingParagraph(
            text=paragraph,
            score=score,
            cause=cause,
            url=filing_anchor_url(source_url, paragraph),
        )
        ranked.append((-score, position, chosen))
    ranked.sort(key=lambda entry: entry[:2])
    return tuple(entry[2] for entry in ranked[:MAX_PARAGRAPHS])
