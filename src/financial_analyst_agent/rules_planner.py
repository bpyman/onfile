"""The rules planner: maps a question to a plan without a model.

The recorded runtime always uses it, and the live runtime does whenever the
deployment does not call OpenAI, so it has to read everyday questions: company
names and tickers from the ranking snapshot, misspellings, "X or Y", growth,
rankings by industry, and follow-ups that lean on the current analysis.
"""

from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path

from financial_analyst_agent.contracts import (
    ALLOWED_METRICS,
    DEFAULT_RANK_LIMIT,
    Intent,
    WorkflowPlan,
)
from financial_analyst_agent.filing_change import (
    REVIEWED_SECTIONS,
    form_named,
    requested_sections,
)
from financial_analyst_agent.graph.analysis_spec import AnalysisSpec, RankedRequest, SpecPatch
from financial_analyst_agent.guide import short_name
from financial_analyst_agent.issuer_index import (
    CompanyMention,
    IssuerIndex,
    expand_groups,
    normalize,
    plain_text,
)
from financial_analyst_agent.providers.sec.submissions import ACCESSION_PATTERN
from financial_analyst_agent.request_wording import (
    OVERVIEW_PLAN,
    asks_for_explanation,
    asks_to_swap,
    implied_metrics,
    parse_named_periods,
    takes_out_or_swaps,
)
from financial_analyst_agent.services.metric_catalog import (
    metric_phrases,
    resolve_metric_phrase,
    segment_note,
    segment_term,
)
from financial_analyst_agent.universe import (
    DEFAULT_SNAPSHOT_PATH,
    former_names,
    ineligible_issuers,
    load_universe_snapshot,
    sec_filer_names,
)

FIXTURE_UNIVERSE_SNAPSHOT_PATH = (
    Path(__file__).parent / "data" / "fixture_universe_snapshot.json"
)

_ISSUER_PHRASES: tuple[tuple[str, str], ...] = (
    ("microsoft", "Microsoft"),
    ("msft", "Microsoft"),
    ("apple", "Apple"),
    ("aapl", "Apple"),
    ("alphabet", "Google"),
    ("google", "Google"),
    ("googl", "Google"),
    ("goog", "Google"),
    ("tesla", "Tesla"),
    ("tsla", "Tesla"),
    ("general motors", "GM"),
    ("gm", "GM"),
    # The rest of the recorded cassette, so the demo answers by name for every
    # company it holds (the landing page's own examples name Eli Lilly and Merck).
    ("nvidia", "NVDA"),
    ("nvda", "NVDA"),
    ("broadcom", "AVGO"),
    ("avgo", "AVGO"),
    ("eli lilly", "LLY"),
    ("lilly", "LLY"),
    ("lly", "LLY"),
    ("advanced micro devices", "AMD"),
    ("amd", "AMD"),
    ("jpmorgan", "JPM"),
    ("jp morgan", "JPM"),
    # "J.P. Morgan" reads as "j p morgan"; "Morgan" alone is Morgan Stanley.
    ("j p morgan", "JPM"),
    ("jpm", "JPM"),
    ("johnson & johnson", "JNJ"),
    ("johnson and johnson", "JNJ"),
    ("j&j", "JNJ"),
    ("jnj", "JNJ"),
    ("abbvie", "ABBV"),
    ("abbv", "ABBV"),
    ("oracle", "ORCL"),
    ("orcl", "ORCL"),
    ("palantir", "PLTR"),
    ("pltr", "PLTR"),
    ("cisco", "CSCO"),
    ("csco", "CSCO"),
    ("bank of america", "BAC"),
    ("merck", "MRK"),
    ("mrk", "MRK"),
    ("applied materials", "AMAT"),
    ("amat", "AMAT"),
    ("unitedhealth", "UNH"),
    ("united health", "UNH"),
    ("unh", "UNH"),
    ("goldman sachs", "GS"),
    ("goldman", "GS"),
    ("wells fargo", "WFC"),
    ("wfc", "WFC"),
    ("thermo fisher", "TMO"),
    ("amgen", "AMGN"),
    ("amgn", "AMGN"),
    ("gilead", "GILD"),
    ("gild", "GILD"),
    ("abbott", "ABT"),
    ("pfizer", "PFE"),
    ("pfe", "PFE"),
    ("danaher", "DHR"),
)
# The industry a ranking with none named ranks: every snapshot member.
WHOLE_MARKET = "companies"
RECORDED_FILING_OLDER = "0000950170-25-061046"
RECORDED_FILING_NEWER = "0001193125-26-191507"


def _company_from_query(normalized: str) -> str:
    return _lookup_company(normalized) or "unknown"


def _lookup_company(normalized: str) -> str | None:
    """The company a question names, or None: never "unknown" or "the"."""
    companies = _companies_from_query(normalized)
    if companies:
        return companies[0]
    return _issuer_from_lookup_query(normalized)


def _companies_from_query(normalized: str) -> list[str]:
    """Issuers named in the query, in the order the analyst named them.

    Whole words only, so "gm" does not match inside "algorithm".
    """
    first_seen: dict[str, int] = {}
    for phrase, name in _ISSUER_PHRASES:
        match = re.search(rf"(?<![\w&]){re.escape(phrase)}(?![\w&])", normalized)
        if match is None:
            continue
        if name not in first_seen or match.start() < first_seen[name]:
            first_seen[name] = match.start()
    return sorted(first_seen, key=first_seen.__getitem__)


# "what was Apple's revenue": the words between the question and a metric.
_LOOKUP_ISSUER = re.compile(
    r"\b(?:what (?:was|is|were)|whats)\s+(.+?)(?:'s)?\s+(?:"
    + "|".join(re.escape(phrase) for phrase in metric_phrases())
    + r")\b"
)


def _issuer_from_lookup_query(normalized: str) -> str | None:
    match = _LOOKUP_ISSUER.search(normalized)
    if match is None:
        return None
    issuer = match.group(1).strip(" .,?!'")
    # "what was the revenue?" names no company: "the" is not one.
    words = [word for word in issuer.split() if word not in _NOT_A_NAME]
    return " ".join(words) or None


# Words a lookup question puts where a company's name would go.
_NOT_A_NAME = frozenset(
    """
    the a an this that its it their his her my our your these those total latest
    last current quarterly annual reported company's company companies firm stock
    """.split()  # noqa: SIM905
)


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


def _metric_from_query(normalized: str) -> str:
    # The catalog owns metric phrases (ADR 0004, 0005): "income" and "profit" are
    # ambiguous there, so the spec clarifies instead of the planner guessing.
    resolved = resolve_metric_phrase(normalized)
    if resolved.unique_metrics:
        return resolved.unique_metrics[0]
    if resolved.term is not None:
        # A measure the catalog lacks, named as it lists it ("debt-to-equity").
        return resolved.term
    if re.search(r"\brevs?\b", normalized):
        return "revenue"
    if "cost of revenue" not in normalized and re.search(r"\bcosts?\b", normalized):
        return "costs"
    return "unknown"


def _is_news_query(normalized: str) -> bool:
    if "hormuz" in normalized and "themes" not in normalized:
        return True
    if "supply chain" in normalized or "supply-chain" in normalized:
        return True
    return (
        re.search(
            r"what(?:['’]?s| is) (?:going on|happening)|\bnews\b|\bheadlines?\b"
            r"|\blatest on\b|\bin the news\b",
            normalized,
        )
        is not None
    )


_FILING_WORDS = (
    "md&a",
    "mda",
    "risk factor",
    "management discussion",
    "management's discussion",
    "10-q",
    "10q",
    "10-k",
    "10k",
    "annual report",
    "filing",
    "disclosure",
    "quarterly report",
)


def _is_filing_change_query(normalized: str) -> bool:
    asks_change = re.search(
        r"what(?:['’]?s| has| is)? (?:changed|new)|filing change|\bchanges? (?:in|to)\b"
        r"|\bdiff(?:erence)?s? (?:in|between)\b|\bsummar(?:y|ise|ize)\b"
        # "how the newest 10-Q differs from the one before", "10-K vs the prior one"
        r"|\bdiffer(?:s|ed|ent|ence|ences)?\b|\bcompared? (?:to|with|against)\b"
        r"|\b(?:vs\.?|versus) (?:the )?(?:prior|previous|last|one before)\b|\bnew since\b",
        normalized,
    )
    return asks_change is not None and (
        any(token in normalized for token in _FILING_WORDS)
        or ACCESSION_PATTERN.search(normalized) is not None
    )


def _filing_change_plan(query: str, normalized: str) -> WorkflowPlan:
    accessions = ACCESSION_PATTERN.findall(query)
    older = accessions[0] if len(accessions) >= 2 else ""
    newer = accessions[1] if len(accessions) >= 2 else ""
    # "What changed in Apple's 10-Q?" names no section: it asks about the filing.
    # The plan's section field is text, as the model planner fills it.
    section = " and ".join(requested_sections(normalized) or REVIEWED_SECTIONS)
    return WorkflowPlan(
        intent=Intent.FILING_CHANGE,
        company=_company_from_query(normalized),
        older_accession=older,
        newer_accession=newer,
        section=section,
        form=form_named(normalized),
        summarize="summar" in normalized,
    )


def _is_exploratory_query(normalized: str) -> bool:
    if "themes" in normalized and ("coverage" in normalized or "emerging" in normalized):
        return True
    return "exploratory" in normalized


_PEERS = re.compile(
    r"\b(?:peers?|competitors?|rivals?|comparables?|similar (?:companies|firms|to)"
    r"|companies like)\b"
)
_SORT_BY = re.compile(r"^(?:sort|order|rank)(?:ed)?\s+(?:them\s+|it\s+|these\s+)?by\s+.+$")
_LIST_WORDING = re.compile(r"\b(?:vs|versus|compare[ds]?|and|or|against)\b|,")
_RANK_WORDS = re.compile(
    r"\b(?:top|biggest|largest|leading|rank|ranked|ranking)\b"
    # "worth the most", "most valuable": the largest by market cap.
    r"|\bworth the most\b|\bmost valuable\b"
)
# "Which tech company has the highest net margin?" ranks an industry by a metric.
_WHICH_HIGHEST = re.compile(
    r"\bwhich\s+(?P<group>[a-z&][a-z&\- ]*?)\s+"
    r"(?P<noun>companies|company|stocks|stock|firms|firm)?\s*"
    r"(?:has|have|had|is|are|with)\s+the\s+(?:highest|most|biggest|largest|best|greatest|top)\b"
)
_ORDER_WORDING = re.compile(
    r"\b(?:by|in terms of|ranked by|sorted by|with the (?:most|highest|biggest|largest))\b"
)
_ADD_WORDING = re.compile(r"^\s*(?:and|also|plus|with|include|now add|add)\b|\b(?:their|its)\b")
# "compare it to Google", "vs AMD": set a named company beside the current analysis.
_COMPARE_TO_WORDING = re.compile(
    r"^\s*(?:now\s+)?compare[ds]?\s+(?:it|them|this|that|these|those)\s+(?:to|with|against)\b"
    r"|^\s*(?:vs\.?|versus|against)\s"
    r"|^\s*(?:and\s+)?how\s+(?:does\s+it|do\s+they)\s+compare\s+(?:to|with)\b"
)
# "compare them": the companies already on screen (or the last two named), side by side.
_COMPARE_THEM = re.compile(
    r"(?:now\s+|ok\s+|okay\s+)?compare\s+(?:them|the\s+two|both|these|those)"
    r"(?:\s+side\s+by\s+side)?"
)
_LEADING_AND = re.compile(r"^\s*(?:and|also|plus|add)\b")
_TOP_N = re.compile(r"\b(?:only |just )?(?:the )?top\s+(\d+)\b")
_LIMIT_WORDS = re.compile(
    r"\b(?:top|biggest|largest|leading)\s+(\d+)\b|\b(\d+)\s+(?:biggest|largest)\b"
)
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
_GROUP_COUNT = re.compile(
    rf"\b{_GROUP_COUNTED_BY}\s+(\d+)\b(?!\s+(?:quarters?|years?|months?))"
)
# Words before an industry that say how a ranking is cut, not which group it is.
_GROUP_LEAD = re.compile(
    r"^(?:(?:the|top|\d+|biggest|largest|leading|most valuable|best)\s+)+", re.IGNORECASE
)
# "top five banks" is five banks, not Five Below.
_RANK_COUNT_WORD = re.compile(
    rf"\b(top|biggest|largest|leading)\s+({_COUNT_WORD})\b"
    rf"|\b({_COUNT_WORD})\s+(biggest|largest)\b",
    re.IGNORECASE,
)
_FOLLOW_UP_MAX_WORDS = 7
_METRIC_WORDS = frozenset(word for phrase in metric_phrases() for word in phrase.split()) | {
    "eps",
    "earnings",
    "share",
    "cash",
    "flow",
    "free",
    "capex",
    "capital",
    "spending",
}
# Words a question uses around a company: a filer named with one of them is not
# indexed, so its name cannot swallow "Nvidia stock price" or "Apple vs Microsoft".
_FILER_RESERVED_WORDS = _METRIC_WORDS | {
    "vs",
    "versus",
    "compare",
    "quarter",
    "quarterly",
    "annual",
    "latest",
    "last",
    "stock",
    "shares",
    "results",
    "report",
    "growth",
}


@lru_cache(maxsize=4)
def _index_for(path: Path, _mtime_ns: int) -> IssuerIndex:
    snapshot = load_universe_snapshot(path)
    return IssuerIndex.build(
        snapshot.companies,
        _ISSUER_PHRASES,
        # Names the larger companies used to file under: "Facebook", "Raytheon Technologies".
        former=former_names(),
        # Funds are left out of the snapshot, yet "SPY revenue" names one: the
        # lookup then says it is not an operating company (ADR 0001).
        outside=ineligible_issuers(),
        # Operating filers the snapshot leaves out, by full name: "Southern California
        # Edison" is that utility, not California Resources and Edison International.
        filers=sec_filer_names(),
        reserved=_FILER_RESERVED_WORDS,
    )


def issuer_index(path: Path | None = None) -> IssuerIndex:
    """The index for a snapshot file, rebuilt when the file changes."""
    resolved = path or DEFAULT_SNAPSHOT_PATH
    return _index_for(resolved, resolved.stat().st_mtime_ns)


def recorded_issuer_index() -> IssuerIndex:
    return issuer_index(FIXTURE_UNIVERSE_SNAPSHOT_PATH)


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


def _limit(normalized: str) -> int:
    match = _LIMIT_WORDS.search(normalized)
    if match is not None:
        return int(match.group(1) or match.group(2))
    counted = _GROUP_COUNT.search(normalized)
    if counted is not None:
        return int(counted.group(2))
    return DEFAULT_RANK_LIMIT


def _clean_group(industry: str) -> str:
    """The group alone: "5 banks" and "largest banks" rank banks."""
    return _GROUP_LEAD.sub("", industry).strip() or industry


_ODD_COUNT = re.compile(r"\b(top|biggest|largest|leading)\s+(-\s*\d+|\d+\.\d+|0+)(?=\s|$)", re.I)


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


_COUNT_NOUN_PLURALS = {"company": "companies", "stock": "stocks", "firm": "firms"}
# Everyday words for an industry the snapshot names otherwise.
_INDUSTRY_WORDS = {
    word: "automakers"
    for word in (
        "ev", "evs", "electric vehicle", "electric vehicles", "electric vehicle makers",
        "ev makers", "car", "cars", "car makers", "carmakers", "auto", "autos",
    )
}  # fmt: skip


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
    text = re.sub(r"\b(?:by|in terms of|ranked by)\b.*$", "", normalized)
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


def _mention_note(index: IssuerIndex, mention: CompanyMention) -> str:
    name = short_name(index.display_name(mention.query)) or mention.query
    return f"Showing {name} for “{mention.typed}”."


class DemoCompleter:
    """Rules planner; see the module docstring.

    ``index`` names the companies it recognizes: the recorded cassette's by
    default, the live snapshot's on the live runtime.
    """

    def __init__(self, index: IssuerIndex | None = None, *, recorded: bool = False) -> None:
        self._index = index
        self._recorded = recorded

    @property
    def index(self) -> IssuerIndex:
        if self._index is None:
            self._index = recorded_issuer_index()
        return self._index

    @property
    def outside_index(self) -> IssuerIndex | None:
        """The live snapshot's index on the recorded runtime, to name what was not recorded."""
        return issuer_index() if self._recorded else None

    def complete(
        self, query: str, current_spec: object = None, *, _nested: bool = False
    ) -> WorkflowPlan | SpecPatch:
        query, count_notes = _whole_counts(
            _count_words_as_digits(expand_groups(plain_text(query)))
        )
        normalized = query.strip().casefold()
        metric = _metric_from_query(normalized)
        mentions = self.index.find(query)
        notes: list[str] = []
        if not mentions:
            mentions = self.index.correct(query, ignore=_METRIC_WORDS)
            notes = [_mention_note(self.index, mention) for mention in mentions]
        elif _LIST_WORDING.search(normalized):
            # "Microsoft vs Aple": a misspelled name beside a correct one still counts.
            named_words = frozenset(
                word for mention in mentions for word in normalize(mention.typed).split()
            )
            known = {mention.query for mention in mentions}
            extra = [
                mention
                for mention in self.index.correct(query, ignore=_METRIC_WORDS | named_words)
                if mention.query not in known
            ]
            if extra:
                mentions = sorted([*mentions, *extra], key=lambda mention: mention.start)
                notes = [_mention_note(self.index, mention) for mention in extra]
        notes.extend(_ticker_notes(self.index, mentions))
        companies = [mention.query for mention in mentions]

        if _is_filing_change_query(normalized):
            plan = _filing_change_plan(query, normalized)
            if companies:
                # One company's filings are compared at a time; the turn says so.
                plan = plan.model_copy(
                    update={"company": companies[0], "other_companies": tuple(companies[1:])}
                )
            return plan.model_copy(update={"notes": tuple(notes)})
        if "disrupt" in normalized or re.search(
            r"\bhow (?:can|could|will|might|would) ai\b", normalized
        ):
            return WorkflowPlan(intent=Intent.EXPLAIN, topic=query)
        if not companies and asks_for_explanation(query):
            # "Explain how a share buyback affects EPS": a general question that
            # names a metric, not a figure with no company (the shared words decide).
            return WorkflowPlan(intent=Intent.EXPLAIN, topic=query)
        if _is_exploratory_query(normalized):
            return WorkflowPlan(intent=Intent.EXPLORATORY_RESEARCH, topic=query)
        if _is_news_query(normalized):
            # The news workflow searches the question itself.
            return WorkflowPlan(intent=Intent.NEWS_AND_EXPLAIN)

        spec = current_spec if isinstance(current_spec, AnalysisSpec) else None
        if spec is not None:
            follow_up = _follow_up(normalized, companies, metric, spec)
            if follow_up is not None:
                return follow_up

        plan = self._plan(query, normalized, metric, mentions)
        planned = [*count_notes, *notes, *plan.notes]
        if not _nested:
            planned.extend(self._unanswered_notes(query, normalized, plan, mentions))
        return plan.model_copy(update={"notes": tuple(dict.fromkeys(planned))})

    def _plan(
        self, query: str, normalized: str, metric: str, mentions: list[CompanyMention]
    ) -> WorkflowPlan:
        """The closed plan a question asks for, before notes on what it leaves out."""
        companies = [mention.query for mention in mentions]
        which = _WHICH_HIGHEST.search(normalized) if not companies else None
        ranked = _RANK_WORDS.search(normalized) is not None or which is not None
        if ranked and _ranks_with(normalized, companies):
            if which is not None:
                group = which.group("group")
                industry = group if which.group("noun") else _plural_group(group)
            else:
                industry = _ranked_industry(normalized)
            industry = _clean_group(industry)
            industry = _INDUSTRY_WORDS.get(industry, industry)
            limit = _limit(normalized)
            notes = (
                (_left_out_of_ranking(self.index, mentions[0], industry, limit),)
                if mentions
                else ()
            )
            phrase = resolve_metric_phrase(normalized)
            if metric not in ALLOWED_METRICS and phrase.kind == "ambiguous" and phrase.candidates:
                # "highest income": still a ranked lookup ordered by the metric; the
                # spec asks which metric before any provider call.
                metric = phrase.candidates[0]
            if metric in ALLOWED_METRICS:
                ordered = metric != "market_cap" and (
                    which is not None or bool(_ORDER_WORDING.search(normalized))
                )
                return WorkflowPlan(
                    intent=Intent.RANK_AND_LOOKUP,
                    industry=industry,
                    limit=limit,
                    metric=metric,
                    # "top 5 banks by net income" orders by it; "and their net income" does not.
                    order_by_metric=ordered,
                    notes=notes,
                )
            return WorkflowPlan(intent=Intent.RANK, industry=industry, limit=limit, notes=notes)
        segment = segment_term(query)
        segment_notes = (segment_note(segment),) if segment and metric in ALLOWED_METRICS else ()
        if len(companies) == 1 and _PEERS.search(normalized):
            # "Compare Nvidia to its peers": the conversation adds the peers.
            return WorkflowPlan(
                intent=Intent.COMPARE,
                companies=tuple(companies),
                metric=metric if metric != "unknown" else OVERVIEW_PLAN,
                notes=(),
                peers=True,
            )
        unknown_wording = resolve_metric_phrase(normalized).kind == "unknown"
        if metric == "unknown" and companies and unknown_wording:
            # "Apple happiness index": name the word rather than show an overview.
            metric = segment or _unknown_term(query, mentions) or metric
        # "Meta margin Q2 2026 vs Q2 2025" compares periods of one company.
        compare_words = re.search(r"\b(?:compare|vs|versus)\b", normalized) and not (
            len(companies) == 1 and len(parse_named_periods(normalized)) >= 2
        )
        if len(companies) >= 2 or compare_words:
            if metric == "unknown" and len(companies) >= 2 and _names_only(query, mentions):
                metric = OVERVIEW_PLAN
            return WorkflowPlan(
                intent=Intent.COMPARE,
                companies=tuple(companies),
                metric=metric,
                notes=segment_notes,
                # "Rank Apple, Microsoft and Nvidia by revenue" orders the companies.
                order_by_metric=_RANK_NAMED.search(normalized) is not None,
            )
        company = companies[0] if companies else _lookup_company(normalized)
        return WorkflowPlan(
            intent=Intent.LOOKUP, company=company, metric=metric, notes=segment_notes
        )

    def _unanswered_notes(
        self, query: str, normalized: str, plan: WorkflowPlan, mentions: list[CompanyMention]
    ) -> list[str]:
        """Say what a plan leaves out: a name no company matched, a second question."""
        notes: list[str] = []
        if plan.intent in (Intent.COMPARE, Intent.LOOKUP) and _LIST_WORDING.search(normalized):
            outside = self.outside_index
            for name in _unfound_names(query, mentions):
                if outside is not None and outside.find(name):
                    # The recorded runtime says on its own what it did not record.
                    continue
                notes.append(f"I couldn't find a company called “{name}”, so it is left out.")
        answered = _subject(plan)
        for part in _question_parts(query):
            if not _covers(answered, _subject(self.complete(part, _nested=True))):
                notes.append(f"This answers one question at a time: ask “{part}” on its own.")
        return notes


def _subject(plan: WorkflowPlan | SpecPatch) -> tuple[str, frozenset[str]] | None:
    """What a plan is about: its companies, its ranking, or a kind of answer."""
    if isinstance(plan, SpecPatch):
        return None
    intent = plan.intent
    if intent in (Intent.RANK, Intent.RANK_AND_LOOKUP):
        return "rank", frozenset({str(plan.industry).casefold()})
    if intent is Intent.COMPARE:
        return "companies", frozenset(plan.companies)
    if intent is Intent.LOOKUP:
        return ("companies", frozenset({plan.company})) if plan.company else None
    if isinstance(intent, Intent):
        return intent.value, frozenset()
    return None


def _covers(
    answered: tuple[str, frozenset[str]] | None, part: tuple[str, frozenset[str]] | None
) -> bool:
    if part is None or answered is None:
        return True
    return answered[0] == part[0] and part[1] <= answered[1]


# A second question in one message: "… revenue and rank the top 5 banks", "…? What about …".
_QUESTION_BREAK = re.compile(
    # A full stop ends a sentence after a word, not after an initial ("J.P. Morgan").
    r"(?:[?;]|(?<=[a-z0-9]{2})\.(?=\s))\s+"
    r"|,?\s+(?:and|also|then|plus)\s+(?=(?:what|how|which|who|why|rank|show|list|give|tell"
    r"|compare|top)\b)",
    re.IGNORECASE,
)


def _question_parts(query: str) -> list[str]:
    parts = [part.strip(" .?;,!") for part in _QUESTION_BREAK.split(query)]
    parts = [part for part in parts if part]
    return parts if len(parts) > 1 else []


_RANK_NAMED = re.compile(r"\b(?:rank|ranked|sort|sorted|order|ordered)\b")


def _ranks_with(normalized: str, companies: list[str]) -> bool:
    """Whether a question with rank words is a ranking rather than a lookup.

    "Apple top line" and "Apple's biggest expense" are about Apple; "Top 5 banks
    and Apple revenue" is a ranking that leaves Apple out, and says so.
    """
    if not companies:
        return True
    if len(companies) > 1:
        return False
    return bool(
        _LIMIT_WORDS.search(normalized)
        or re.search(r"\brank(?:ed|s)?\s+(?:in|among|within|across)\b", normalized)
    )


def _left_out_of_ranking(
    index: IssuerIndex, mention: CompanyMention, industry: str, limit: int
) -> str:
    name = short_name(index.display_name(mention.query)) or mention.typed
    return (
        f"This ranks the top {limit} {industry}; {name} is listed only if it is among "
        f"them. Ask about {name} on its own for its figures."
    )


def _ticker_notes(index: IssuerIndex, mentions: list[CompanyMention]) -> list[str]:
    """Say when a bare ticker adds a company beside a named one, or one is named twice."""
    notes: list[str] = []
    # Beside "JPM", "BAC" reads as the ticker it is; beside "Apple", "DAN" may not.
    named = any(
        not mention.bare_ticker and mention.typed.upper() not in index.tickers
        for mention in mentions
    )
    for mention in mentions:
        name = short_name(index.display_name(mention.query)) or mention.query
        if mention.bare_ticker and named:
            notes.append(f"Showing {name} for “{mention.typed}”.")
        if mention.also_typed:
            typed = " and ".join(
                dict.fromkeys(word.upper() if len(word) <= 5 else word
                              for word in (mention.typed, *mention.also_typed))
            )
            notes.append(f"{typed} are both {name}, so it is shown once.")
    return notes


# Capitalised words beside a list joiner: the names a compare question lists.
_LISTED_NAME = re.compile(
    r"(?:\b(?:and|or|vs\.?|versus|with|to|against)\s+|,\s*)"
    r"(?P<after>[A-Z][\w.&'’-]*(?:\s+[A-Z][\w.&'’-]*)*)"
    r"|(?P<before>[A-Z][\w.&'’-]*(?:\s+[A-Z][\w.&'’-]*)*)"
    r"(?=\s*,|\s+(?:and|or|vs\.?|versus)\b)"
)


def _unfound_names(query: str, mentions: list[CompanyMention]) -> list[str]:
    """Names a list question gives that no company matched ("Apple and Foobar")."""
    named = {word for mention in mentions for word in normalize(mention.typed).split()}
    found: list[str] = []
    for match in _LISTED_NAME.finditer(query):
        name = (match.group("after") or match.group("before") or "").strip(" .,'’")
        words = normalize(name).split()
        if not words or any(word in named for word in words):
            continue
        if all(
            word in _METRIC_WORDS
            or word in _QUESTION_WORDS
            or re.fullmatch(r"[qh]\d|fy\d*|\d+|cy\d*", word)
            for word in words
        ):
            continue
        if name not in found:
            found.append(name)
    return found


# Words a short question uses around a company and a figure, none a metric:
# what is left after them is the word the catalog does not know.
_QUESTION_WORDS = frozenset(
    """
    what whats was is are were be been the a an of for in on at to and or by s show me
    give tell about please latest last recent current quarter quarterly this that it its
    their how much many did does do has have had numbers number year years now today
    report reported figure figures data compare comparing versus vs with i want know
    see get find look up who which why when where can could you your our my most
    overview snapshot summary profile financials fundamentals key metrics glance
    results doing going performing performance like q1 q2 q3 q4 fy ttm ytd lately
    explain all every same
    """.split()  # noqa: SIM905
)
_MAX_UNKNOWN_WORDS = 3


def _unknown_term(query: str, mentions: list[CompanyMention]) -> str | None:
    """The word a short question asks for that names no metric ("happiness index").

    It keeps the analyst's own spelling: "CEO", not "ceo".
    """
    named = {word for mention in mentions for word in normalize(mention.typed).split()}
    left = [
        typed
        for typed in re.findall(r"[\w&]+", re.sub(r"['’]s\b", "", query))
        if (word := typed.casefold()) not in named
        and word not in _QUESTION_WORDS
        and word not in _COMPARE_FILLER
        and not re.fullmatch(r"(?:fy|cy)?\d+|q\d|\dq|h\d", word)
    ]
    if not left or len(left) > _MAX_UNKNOWN_WORDS or implied_metrics(query, short=False):
        return None
    return " ".join(left)


# Wording that names no metric but implies some (see ``implied_metrics``). The
# overview fallback for short messages is left out: "chart it" is not a request
# for revenue and margins.
_IMPLIED_WORDING = re.compile(
    r"\b(?:profitab|bigger|larger|biggest|largest|grow(?:ing|n|th)?\b|grew\b)", re.IGNORECASE
)

_COMPARE_FILLER = frozenset(
    """
    compare comparing comparison and vs versus against with to between the how do does
    stack up side by
    """.split()  # noqa: SIM905
)


def _names_only(query: str, mentions: list[CompanyMention]) -> bool:
    """Whether a question is companies and compare words alone ("Compare Nvidia and AMD")."""
    named = {word for mention in mentions for word in normalize(mention.typed).split()}
    return all(word in named or word in _COMPARE_FILLER for word in normalize(query).split())


_WHICH_OF_TWO = re.compile(r"\b(?:which (?:one|is|of)|both|them|compared?|vs|versus)\b")
# "which is biggest?" asks about the companies on screen, not a ranking.
_WHICH_OF_THEM = re.compile(
    r"^which(?: one| company| stock| firm"
    r"| of (?:them|these|those|the (?:two|three|four|companies)))?"
    r"(?: of them)?\s+(?:is|has|had|was|were|grew|makes?|made|earns?|earned)\b"
)
# "what was it last quarter?": the analysis on screen, asked again.
_PRONOUN_QUESTION = re.compile(
    r"^(?:and |so |ok |okay )?(?:what|how much|how)\s+(?:was|is|were|are|about)\s+"
    r"(?:it|that|this|they|them|those|these)\b"
)
# "compare with the first one": the first company this thread looked at.
_COMPARE_FIRST = re.compile(
    r"(?:now |ok |okay )?compare (?:it |them |this |that )?(?:with|to|against) the "
    r"(?:first|1st|original) (?:one|company)"
)
# "what about pharma?" after a ranking: the same ranking of another industry.
_INDUSTRY_SWAP = re.compile(
    r"^(?:and |ok |okay |now )?(?:what about|how about|same for|now do|and) (?:the )?"
    r"(?P<industry>[a-z&][a-z& -]*?)(?: companies| stocks| firms)?$"
)


def _follow_up(
    normalized: str, companies: list[str], metric: str, spec: AnalysisSpec
) -> SpecPatch | None:
    """Short edits that lean on the current analysis ("and net margin", "what about MSFT?")."""
    if len(normalized.split()) > _FOLLOW_UP_MAX_WORDS:
        return None
    text = normalized.strip(" .?!")
    top = _TOP_N.search(normalized)
    if (
        top is not None
        and spec.constituents is not None
        and not companies
        and re.fullmatch(r"(?:only |just |show )?(?:the )?top\s+\d+", text)
    ):
        return SpecPatch(
            mode="extend",
            ranked_request=RankedRequest(
                industry=spec.constituents.industry, limit=int(top.group(1))
            ),
        )
    on_screen = bool(spec.companies) or spec.constituents is not None
    sort = _SORT_BY.match(text)
    if sort is not None and on_screen and not companies:
        # "sort by revenue": order the companies on screen, largest first.
        wanted = metric if metric in ALLOWED_METRICS else None
        return SpecPatch(
            mode="extend",
            add_metrics=(wanted,) if wanted and wanted not in spec.metrics else (),
            add_operations=("order_by_metric",),
            set_order_by=wanted,
        )
    if len(spec.companies) >= 2 and not companies and _WHICH_OF_THEM.match(text):
        # "which is biggest?" orders the companies on screen by what it asks.
        asked: tuple[str, ...] = (
            (metric,) if metric in ALLOWED_METRICS else implied_metrics(text, short=False)
        ) or ("market_cap", "revenue")
        return SpecPatch(
            mode="extend",
            add_metrics=tuple(m for m in asked if m not in spec.metrics),
            add_operations=("order_by_metric",),
            set_order_by=asked[0],
        )
    if _RANK_WORDS.search(normalized) or _WHICH_HIGHEST.search(normalized):
        # "largest pharma companies by net income" is a new ranking, not an edit.
        return None
    if not companies and metric not in ALLOWED_METRICS and on_screen and (
        _PRONOUN_QUESTION.match(text)
    ):
        # The period wording ("last quarter", "a year ago") is read from the message.
        return SpecPatch(mode="extend")
    if not companies and spec.companies and _COMPARE_FIRST.fullmatch(text):
        shown = {company.query for company in spec.companies}
        first = [query for query in spec.seen_companies[:1] if query not in shown]
        return SpecPatch(mode="extend", add_companies=tuple(first))
    if (
        not companies
        and metric == "unknown"
        and spec.companies
        and _COMPARE_THEM.fullmatch(text)
    ):
        earlier = spec.earlier_companies if len(spec.companies) == 1 else ()
        return SpecPatch(mode="extend", add_companies=earlier)
    swap = _INDUSTRY_SWAP.match(text)
    if spec.constituents is not None and not companies and metric == "unknown" and swap:
        # "what about pharma?": the same ranking, another industry.
        industry = swap.group("industry").strip()
        return SpecPatch(
            mode="extend",
            ranked_request=RankedRequest(industry=industry, limit=spec.constituents.limit),
        )
    if companies and metric == "unknown" and not on_screen and spec.metrics:
        # "revenue", then "for Apple": the company the question was missing.
        return SpecPatch(mode="extend", add_companies=tuple(companies))
    if companies and metric in ALLOWED_METRICS and spec.companies and _LEADING_AND.search(
        normalized
    ):
        # "and msft revenue" after Apple's revenue: Microsoft joins the table.
        return SpecPatch(
            mode="extend",
            add_companies=tuple(companies),
            add_metrics=(metric,) if metric not in spec.metrics else (),
        )
    if companies and metric == "unknown" and spec.companies:
        if _ADD_WORDING.search(normalized) or _COMPARE_TO_WORDING.search(normalized):
            return SpecPatch(mode="extend", add_companies=tuple(companies))
        if takes_out_or_swaps(normalized):
            # The shared reading of the edit's words says which companies go (ADR 0010).
            return SpecPatch(mode="extend")
        if asks_to_swap(normalized) or len(normalized.split()) <= 2:
            return SpecPatch(
                mode="extend",
                remove_companies=tuple(company.query for company in spec.companies),
                add_companies=tuple(companies),
            )
        return None
    if (
        not companies
        and metric not in ALLOWED_METRICS
        and (spec.companies or spec.constituents is not None)
        and _IMPLIED_WORDING.search(normalized)
    ):
        # "which one is more profitable?" asks the current analysis a new question.
        earlier = (
            spec.earlier_companies
            if len(spec.companies) == 1 and _WHICH_OF_TWO.search(normalized)
            else ()
        )
        # After "what about AMD?", "which one" means Nvidia and AMD.
        return SpecPatch(
            mode="extend", add_companies=earlier, add_metrics=implied_metrics(normalized)
        )
    if companies or metric not in ALLOWED_METRICS:
        return None
    if not (spec.companies or spec.constituents is not None):
        return None
    # "what about net income" swaps rather than adds: the shared edit reading
    # decides that for both planners (request_wording).
    return SpecPatch(mode="extend", add_metrics=(metric,))
