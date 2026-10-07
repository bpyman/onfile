"""Find the companies a question names, from a snapshot's names and tickers.

The rules planner reads questions without a model, so it needs to know which
words are companies: "Costco", "Coca-Cola", "$NFLX", or a misspelt "Microsft".
The index is built once per snapshot file and answers in a dictionary lookup
per word n-gram; typo matching runs only when nothing matched exactly.
"""

from __future__ import annotations

import difflib
import re
from collections.abc import Iterable, Mapping, Sequence
from collections.abc import Set as AbstractSet
from dataclasses import dataclass, field, replace
from functools import cached_property, lru_cache
from pathlib import Path
from types import MappingProxyType
from typing import Protocol

from financial_analyst_agent.services.metric_catalog import metric_phrases
from financial_analyst_agent.universe import UniverseCompany

# Legal-form and filler words a company name drops in speech.
_NAME_SUFFIXES = frozenset(
    {
        "inc",
        "incorporated",
        "corp",
        "corporation",
        "co",
        "company",
        "companies",
        "ltd",
        "limited",
        "plc",
        "llc",
        "lp",
        "l.p",
        "sa",
        "nv",
        "ag",
        "se",
        "holdings",
        "holding",
        "group",
        "reit",
        "the",
        "class",
        "com",
        "new",
        "de",
    }
)
# A fund's name says what it is ("Blackstone Secured Lending Fund"); asked, it is dropped.
_FUND_WORDS = frozenset({"fund", "trust", "etf", "inc"})
# First words that are not a company on their own ("General" Motors,
# "American" Express), plus words a question uses for something else.
_GENERIC_WORDS = frozenset(
    """
    a about above after all also american an and any are as at bank banks be best big
    biggest by can capital central century citizens common compare could data did digital
    do does doing east eastern energy equity federal financial first for from general
    global good great growth had has have health healthcare home how i in income industries
    international is it its just last latest life margin market me medical micro more most
    much my national net new north northern of on one or our pacific people profit public
    quarter quarters real restaurant restaurants revenue royal sales service services show
    so south southern stock stocks telecom than that the their them then there these they
    this to top total trade trust
    united universal us value vs was were west western what when which who why will with
    world would year you your
    """.split()  # noqa: SIM905
)
# Uppercase words in a question that are not tickers.
_NOT_TICKERS = frozenset(
    {
        "A",
        "I",
        "AI",
        "IT",
        "CEO",
        "CFO",
        "EPS",
        "FCF",
        "OCF",
        "CY",
        "LTM",
        "ROE",
        "ROA",
        "US",
        "USA",
        "SEC",
        "CIK",
        "FY",
        "YOY",
        "QOQ",
        "TTM",
        "GAAP",
        "EBIT",
        "EBITDA",
        "IPO",
        "ETF",
        "OK",
        "VS",
        "AND",
        "OR",
        "THE",
        "TOP",
        "MD",
        "API",
        "GDP",
        "R",
        "D",
        "Q",
    }
)
# Finance and chat shorthand that is never meant as a ticker unless "$"-prefixed:
# "Apple SGA" is not Saga Communications, "IMO" is not Imperial Oil.
_ACRONYMS = frozenset(
    """
    ar ap arr mrr ni gp op oi da sga cogs opex capex rev roi roic roa roce irr npv dcf
    cagr ttm ytd mtd qtd ntm eps pe peg ev ebt fcf ocf dps bps kpi kpis esg uk eu us
    usa uae nyse imo imho tbh fyi asap btw lol omg eod ath atl ipo spac bdc reit etf
    usd eur gbp jpy cny cpi ppi gdp fomc fed hr pr ir it ai ml saas vc ceo cfo coo
    cto ok vs aka yoy qoq mom h1 h2 q1 q2 q3 q4 fy cy ltm
    """.split()  # noqa: SIM905
)
# Short English words that are also tickers ("NOW", "FOR", "ARE", "SO"). One
# counts as a ticker only when nothing else in the question names a company and
# a figure follows it: "NOW revenue" is ServiceNow, "now" in a sentence is not.
_ENGLISH_WORDS = frozenset(
    """
    a about after again all also am an and any are as ask at away back be been best
    big both but buy by call can car cash cat come could day did do does done down
    each earn eat eye fast few find fly for from fun gap get give go good got had has
    have he her here high him his hot how if in into is it its just key know last
    law less let like live long look lot low made main make man many may me mean
    more most much must my need net new next no not now of off old on once one only
    or other our out over own pay per plan play plus put real run said same say see
    sell she show so some such sun take team tell ten than that the their them then
    there these they this those top true two up us use very want was way we well
    were what when which who why will win with work would year yes yet you your
    """.split()  # noqa: SIM905
)
# Names people use that no listing title contains, by the ticker they mean.
# Applied only when that ticker is in the snapshot.
_NICKNAMES: tuple[tuple[str, str], ...] = (
    ("pepsi", "PEP"),
    ("coke", "KO"),
    ("facebook", "META"),
    ("p&g", "PG"),
    ("bofa", "BAC"),
    ("disney", "DIS"),
    ("ibm", "IBM"),
    ("honeywell", "HON"),
    ("3m", "MMM"),
    ("comcast", "CMCSA"),
    ("amex", "AXP"),
    ("exxonmobil", "XOM"),
    ("berkshire", "BRK-B"),
    ("citi", "C"),
    ("chase", "JPM"),
    ("raytheon", "RTX"),
    ("ups", "UPS"),
    ("att", "T"),
    ("cvs", "CVS"),
    ("hp", "HPQ"),
    ("schwab", "SCHW"),
    ("capital one", "COF"),
    ("general electric", "GE"),
    ("southern company", "SO"),
    ("us bancorp", "USB"),
    ("bank of new york", "BNY"),
    ("oreilly", "ORLY"),
    ("tsmc", "TSM"),
    ("tmobile", "TMUS"),
    ("spacex", "SPCX"),
    ("space x", "SPCX"),
    # Tickers people type in lower case, and names no listing title holds.
    ("ge", "GE"),
    ("kkr", "KKR"),
    ("pnc", "PNC"),
    ("mgm", "MGM"),
    ("amc", "AMC"),
    ("bp", "BP"),
    ("us bank", "USB"),
    ("snapchat", "SNAP"),
    ("arm holdings", "ARM"),
    ("santander", "SAN"),
    ("royal caribbean", "RCL"),
    ("peloton", "PTON"),
)
# Words a company field holds beside the name: "Merck and Co", "Danaher Corp.".
_FILLER_WORDS = _NAME_SUFFIXES | {"and", "&", "of", "s"}
# Two-word starts of a longer name that are places or words, not that company:
# "New York" Times, "Las Vegas" Sands.
_NOT_SHORT_NAMES = frozenset({"las vegas", "grupo financiero", "super group"})
# A ticker, with a share class after a dot, dash or slash ("BRK.B"). Letters
# joined to a word are not tickers: "S&P", "T-Mobile", "O'Reilly".
_TICKER = re.compile(
    r"(?<![\w&/.'’-])\$?([A-Za-z]{1,5})(?:[./-]([A-Za-z]))?(?![\w&/'’])(?![./-][A-Za-z])"
)
# Tickers that also start a metric's name: "NET income" is not Cloudflare's.
_METRIC_STARTS = {
    "NET": frozenset({"income", "margin", "loss", "losses", "sales", "profit", "debt", "interest"}),
    "CASH": frozenset({"flow", "flows"}),
}
# SEC titles end with a state or "new" marker: "CONSUMERS BANCORP INC /OH/".
_SEC_STATE = re.compile(r"\s*/[A-Za-z .]+/?\s*$")
_CIK = re.compile(r"\bcik\s*#?:?\s*(\d{1,10})\b|\b(0\d{9})\b", re.IGNORECASE)
# "Alphabet Class C", "Series B": the letter names a share class, not Citigroup.
_SHARE_CLASS_WORD = re.compile(r"\b(?:class|series|cl)\s*$", re.IGNORECASE)
# The word after a ticker that makes it one: "NOW revenue", "NOW's margin".
_FIGURE_AFTER = re.compile(r"^(?:'s|’s)?\s*([A-Za-z&/]+)")
_MAX_NGRAM = 5
_FIRST_WORD_ALIAS_RANK = 1500
_TYPO_CUTOFF = 0.84
_TYPO_MIN_LENGTH = 5
# A four-letter word is corrected only when one letter is missing ("aple").
_SHORT_TYPO_LENGTH = 4
# Words this long are corrected at one edit ("Nvidea", "Telsa", "Oracel").
_EDIT_TYPO_LENGTHS = range(5, 8)
# A ticker just before or after a list word: "AAPL vs ON", "ON, NVDA and AMD".
_LIST_JOIN = r"(?:,|&|/|\band\b|\bor\b|\bvs\.?|\bversus\b|\bagainst\b|\bwith\b)"
_TICKER_BEFORE = re.compile(rf"\$?\b([A-Z]{{1,5}})\s*{_LIST_JOIN}\s*$")
_TICKER_AFTER = re.compile(rf"^\s*{_LIST_JOIN}\s*\$?([A-Z]{{1,5}})\b")
# Most of a question's words in capitals: it is shouted, not a list of tickers.
_SHOUTED_SHARE = 0.6
_SHOUTED_MIN_WORDS = 3


# Groups people name as if they were one company.
_GROUPS: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(r"\b(?:the\s+)?(?:magnificent|mag)\s*(?:7|seven)\b", re.I),
        "Apple, Microsoft, Alphabet, Amazon, Nvidia, Meta and Tesla",
    ),
    (re.compile(r"\bfaang\b", re.I), "Meta, Apple, Amazon, Netflix and Alphabet"),
    (re.compile(r"\bfang\b", re.I), "Meta, Amazon, Netflix and Alphabet"),
)


def expand_groups(question: str) -> str:
    """ "Magnificent 7 revenue" → the seven companies' names, so each is looked up."""
    for pattern, names in _GROUPS:
        question = pattern.sub(names, question)
    return question


# Markdown a pasted question carries: "**Apple** _revenue_" is "Apple revenue".
_MARKDOWN = (
    (re.compile(r"\[([^\]]*)\]\([^)]*\)"), r"\1"),
    (re.compile(r"\*\*|__|~~|[*`]"), ""),
    (re.compile(r"(?<!\w)_(\S(?:[^_]*\S)?)_(?!\w)"), r"\1"),
)


def plain_text(question: str) -> str:
    """The question without markdown emphasis, code marks or link targets."""
    for pattern, kept in _MARKDOWN:
        question = pattern.sub(kept, question)
    return question


def normalize(text: str) -> str:
    """Casefold, drop possessives, and keep only word characters and ``&``."""
    text = text.casefold().replace("’", "'")
    text = re.sub(r"'s\b", "", text)
    text = re.sub(r"[^\w&]+", " ", text)
    return " ".join(text.split())


# A listing's description of the security, not part of the company's name:
# "Pony AI Inc. American Depositary Shares", "Webull Corporation Class A Ordinary Shares".
_SECURITY_TAIL = re.compile(
    r"\s+(?:class\s+[a-z]\b|series\s+[a-z]\b|common\s+stock|ordinary\s+shares?"
    r"|american\s+depositary|depositary\s+(?:shares?|receipts?)|(?:un)?sponsored\b"
    r"|adss?\b|adrs?\b).*$",
    re.IGNORECASE,
)
# Letters of a spelt-out legal form at the end of a name: "S.A.B. de C.V.",
# "L.P.", "S.A.", "KGaA".
_LEGAL_LETTERS = frozenset({"s", "a", "b", "c", "v", "l", "p", "sab", "cv", "sapi", "kgaa", "spa"})


def _core_name(name: str, suffixes: frozenset[str] = _NAME_SUFFIXES) -> str:
    suffixes = suffixes | _LEGAL_LETTERS
    words = normalize(_SECURITY_TAIL.sub("", name)).split()
    while words and words[-1] in suffixes:
        words.pop()
    while words and words[0] == "the":
        words.pop(0)
    return " ".join(words)


@dataclass(frozen=True)
class CompanyMention:
    """One company named in a question, in the order it was named."""

    query: str
    start: int
    typed: str
    corrected: bool = False
    # Read as a ticker with no "$" and no name: the planner says so beside a name.
    bare_ticker: bool = False
    # Other words in the question that named the same company ("GOOG", "GOOGL").
    also_typed: tuple[str, ...] = ()


class CompanyNames(Protocol):
    """What a turn reads company names with: the issuer index, or a test's stand-in."""

    def find(self, question: str, *, company_slot: bool = False) -> list[CompanyMention]: ...

    def named(self, company: str) -> str | None: ...

    def display_name(self, query: str) -> str: ...


@dataclass(frozen=True)
class IssuerIndex:
    """Phrases that name a company, mapped to the query the resolver takes."""

    phrases: Mapping[str, str] = field(default_factory=dict)
    tickers: Mapping[str, str] = field(default_factory=dict)
    display_names: Mapping[str, str] = field(default_factory=dict)
    ciks: Mapping[str, str] = field(default_factory=dict)
    # First words two large companies share ("lincoln"), by their tickers.
    shared: Mapping[str, tuple[str, ...]] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(self, "phrases", MappingProxyType(dict(self.phrases)))
        object.__setattr__(self, "tickers", MappingProxyType(dict(self.tickers)))
        object.__setattr__(self, "display_names", MappingProxyType(dict(self.display_names)))
        object.__setattr__(self, "ciks", MappingProxyType(dict(self.ciks)))
        object.__setattr__(self, "shared", MappingProxyType(dict(self.shared)))

    @classmethod
    def build(
        cls,
        companies: Sequence[UniverseCompany],
        aliases: Iterable[tuple[str, str]] = (),
        *,
        former: Iterable[tuple[str, str]] = (),
        outside: Iterable[tuple[str, str]] = (),
        filers: Iterable[tuple[str, str]] = (),
        reserved: frozenset[str] = frozenset(),
    ) -> IssuerIndex:
        phrases: dict[str, str] = {}
        tickers: dict[str, str] = {}
        display_names: dict[str, str] = {}
        ciks: dict[str, str] = {}
        shared: dict[str, tuple[str, ...]] = {}
        for phrase, query in aliases:
            phrases.setdefault(normalize(phrase), query)
        listed = {company.ticker.upper() for company in companies}
        for phrase, ticker in _NICKNAMES:
            if ticker in listed:
                phrases.setdefault(phrase, ticker)
        ranked = sorted(companies, key=lambda company: company.market_cap, reverse=True)
        first_words: dict[str, list[str]] = {}
        short_names: dict[str, list[str]] = {}
        for rank, company in enumerate(ranked):
            ticker = company.ticker.upper()
            tickers.setdefault(ticker, ticker)
            ciks.setdefault(company.cik, ticker)
            display_names.setdefault(ticker, company.name)
            core = _core_name(company.name)
            # "Power REIT" is named in full too, where "power" alone is not it.
            spoken = _core_name(company.name, _NAME_SUFFIXES - {"reit"})
            if spoken != core and " " in spoken:
                phrases.setdefault(spoken, ticker)
            if not core or (" " not in core and (core in _GENERIC_WORDS or len(core) < 3)):
                # "Southern Company" is not "southern"; "Target" still is "target".
                continue
            if " " not in core and rank >= _FIRST_WORD_ALIAS_RANK and core in _common_words():
                # A small listing does not own an everyday word: "power" is not Power REIT.
                continue
            phrases.setdefault(core, ticker)
            # "Lowe's" is also typed "Lowes".
            joined = _core_name(company.name.replace("'", "").replace("’", ""))
            if joined != core:
                phrases.setdefault(joined, ticker)
            if "&" in core:
                phrases.setdefault(core.replace("&", "and"), ticker)
            compound = normalize(company.name.split()[0])
            if "-" in company.name.split()[0] and " " in compound and compound != core:
                # "Take-Two" for Take-Two Interactive: a hyphened word is one name.
                phrases.setdefault(compound, ticker)
            words = core.split()
            if (
                rank < _FIRST_WORD_ALIAS_RANK
                and len(words) > 1
                and len(words[0]) >= 4
                and words[0] not in _GENERIC_WORDS
            ):
                first_words.setdefault(words[0], []).append(ticker)
            if (
                rank < _FIRST_WORD_ALIAS_RANK
                and len(words) > 2
                and words[0] not in _GENERIC_WORDS
                and len(words[1]) >= 4
                and words[1] not in _GENERIC_WORDS
                and words[1] not in _NAME_SUFFIXES
            ):
                short_names.setdefault(" ".join(words[:2]), []).append(ticker)
        for word, owners in (*first_words.items(), *short_names.items()):
            # "Costco" for Costco Wholesale, "Johnson Controls" for Johnson
            # Controls International; a start two large companies share
            # ("Bank" of America and "Bank" of New York) names neither.
            if len(owners) == 1 and word not in _NOT_SHORT_NAMES:
                phrases.setdefault(word, owners[0])
            elif " " not in word and word not in phrases and word not in _everyday_words():
                shared[word] = tuple(owners)
        for ticker, name in former:
            _add_former_name(phrases, tickers, ticker, name)
        for ticker, name in outside:
            _add_outside_name(phrases, tickers, display_names, ticker, name)
        for ticker, name in filers:
            _add_filer_name(phrases, display_names, ticker, name, reserved=reserved)
        return cls(
            phrases=phrases,
            tickers=tickers,
            display_names=display_names,
            ciks=ciks,
            shared=shared,
        )

    def find(self, question: str, *, company_slot: bool = False) -> list[CompanyMention]:
        """Companies named exactly, longest phrase first, in question order.

        A one-word name that is also an everyday word ("target", "block", "gap")
        counts only where the question uses it as a company: "Target's revenue",
        "compare Target and Walmart", not "Nvidia's target margin" or "the gap".
        ``company_slot`` says the whole text is already known to name a company
        (a planner's company field), so no such reading is needed.
        """
        normalized = normalize(question)
        words = normalized.split()
        offsets: list[int] = []
        position = 0
        for word in words:
            offsets.append(position)
            position += len(word) + 1
        taken = [False] * len(words)
        found: dict[str, CompanyMention] = {}
        typed_shapes = _word_shapes(question, len(words))
        shapes = None if company_slot else typed_shapes
        # "$TEAM" is Atlassian's ticker, whoever "team" names: the ticker pass reads it.
        dollar = {
            position
            for position, shape in enumerate(typed_shapes or ())
            if shape.before.endswith("$")
        }
        # "intel aside", "to the micron": the word, not the company.
        used = set() if company_slot else _word_use_positions(normalized)
        # One-word everyday names, judged once every other name is known.
        tentative: list[tuple[int, str, CompanyMention]] = []
        # Names several companies share: kept only where read as a company.
        strict: set[int] = set()
        shouted = _shouted(question)

        def note(query: str, mention: CompanyMention) -> None:
            shown = found.get(query)
            if shown is None:
                found[query] = mention
            elif mention.typed.casefold() not in {
                typed.casefold() for typed in (shown.typed, *shown.also_typed)
            }:
                # "GOOG vs GOOGL": one company, named twice; the planner says so.
                found[query] = replace(shown, also_typed=(*shown.also_typed, mention.typed))

        spans: list[tuple[int, int]] = []
        for size in range(min(_MAX_NGRAM, len(words)), 0, -1):
            for start in range(len(words) - size + 1):
                if any(taken[start : start + size]):
                    continue
                phrase = " ".join(words[start : start + size])
                if size == 1 and (start in dollar or start in used):
                    continue
                shared = size == 1 and phrase not in self.phrases and phrase in self.shared
                if shared:
                    # "Lincoln": Lincoln Electric or Lincoln National. The
                    # resolver finds both, and the analyst is asked which.
                    owner = phrase.title()
                    if shapes is not None:
                        strict.add(start)
                elif phrase in self.phrases:
                    owner = self.phrases[phrase]
                else:
                    continue
                typed = typed_shapes[start].typed if typed_shapes and size == 1 else ""
                ticker = self.tickers.get(typed) if typed.isupper() and len(typed) > 1 else None
                as_ticker = (
                    ticker is not None
                    and not shouted
                    and ticker != owner
                    and (shared or owner in self.tickers)
                    # "HP" is HP Inc.'s own name, written so: the name stands.
                    and [word.strip(",.") for word in self.display_name(owner).split()[:1]]
                    != [typed]
                )
                if as_ticker and ticker is not None:
                    # "TEAM revenue" typed as a ticker is Atlassian, though "team"
                    # names Team Inc; "COKE" is Coca-Cola Consolidated, not Coke.
                    owner, shared = ticker, False
                    strict.discard(start)
                for slot in range(start, start + size):
                    taken[slot] = True
                mention = CompanyMention(owner, offsets[start], phrase)
                ordinary = shared or _ordinary(phrase)
                if shapes is not None and size == 1 and ordinary and not as_ticker:
                    tentative.append((start, owner, mention))
                else:
                    spans.append((start, start + size))
                    note(owner, mention)
        if shapes is not None:
            kept = _as_companies(words, shapes, spans, tentative, strict)
            for start, owner, mention in tentative:
                if start in kept:
                    note(owner, mention)
                else:
                    # An everyday word: free for the ticker pass, like any word.
                    taken[start] = False
        for match in _CIK.finditer(question):
            # "CIK 320193" or SEC's ten-digit "0000320193".
            query = self.ciks.get((match.group(1) or match.group(2)).zfill(10))
            if query is not None and query not in found:
                found[query] = CompanyMention(query, _char_to_word_offset(question, match), query)
        named = bool(found)
        # The "J" of "J.P. Morgan" belongs to the name the phrase pass found.
        name_words = {word for word, used in zip(words, taken, strict=True) if used}
        for match in _TICKER.finditer(question):
            raw, share_class = match.group(1), match.group(2)
            dollar_typed = match.group(0).startswith("$")
            before = normalize(question[: match.start()]).split()
            if not dollar_typed and (
                raw.casefold() in name_words
                # "Novartis AG", "BioNTech SE": the legal form, not a ticker.
                or (
                    raw.casefold() in _NAME_SUFFIXES
                    and bool(before)
                    and (before[-1] in name_words or before[-1] in _NAME_SUFFIXES)
                )
                or not self._bare_ticker(question, match, named=named, shouted=shouted)
            ):
                continue
            if share_class is not None:
                # "BRK.B" is Berkshire's B shares; "P/E" and "U.S." name no class.
                query = self._share_class(raw, share_class)
            elif raw.casefold() in self.phrases and not dollar_typed:
                # "AAPL" is also an alias phrase; the phrase pass named it once.
                continue
            else:
                query = self.tickers.get(raw.upper())
            if query is not None:
                start = _char_to_word_offset(question, match)
                note(query, CompanyMention(query, start, raw, bare_ticker=not dollar_typed))
        return sorted(found.values(), key=lambda mention: mention.start)

    def named(self, company: str) -> str | None:
        """The one company a company field names ("Goldman Sachs", "Merck & Co.", "$TMO").

        None when the field names no company, several, or a company plus other
        words: "Morgan Stanley Bank" is not a name this index holds whole.
        """
        mentions = self.find(company, company_slot=True)
        if len({mention.query for mention in mentions}) != 1:
            return None
        left = normalize(company).split()
        for mention in mentions:
            for typed in (mention.typed, *mention.also_typed):
                for word in normalize(typed).split():
                    if word in left:
                        left.remove(word)
        return mentions[0].query if all(word in _FILLER_WORDS for word in left) else None

    def _bare_ticker(
        self, question: str, match: re.Match[str], *, named: bool, shouted: bool
    ) -> bool:
        """Whether a capitalised word with no "$" is a ticker here."""
        raw = match.group(1)
        if raw != raw.upper() or raw in _NOT_TICKERS or raw.casefold() in _ACRONYMS:
            return False
        if _SHARE_CLASS_WORD.search(question[: match.start()]):
            return False
        following = question[match.end() :].split(maxsplit=1)
        if following and following[0].casefold() in _METRIC_STARTS.get(raw, frozenset()):
            return False
        if (
            shouted
            and named
            and _is_a_word(raw.casefold())
            and not self._listed_beside_ticker(question, match)
        ):
            # "WHAT IS NVIDIA NET MARGIN NOW?": capitals are the question's tone, so a
            # word is a word. "NVDA, AMD AND INTC REVENUE" still lists three tickers.
            return False
        if raw.casefold() in _ENGLISH_WORDS or raw.casefold() in _figure_words():
            # "NOW revenue" is ServiceNow; "Apple, now and then" is not; "AAPL vs ON"
            # lists onsemi beside another ticker.
            return (
                not named and not shouted and _figure_follows(question, match)
            ) or self._listed_beside_ticker(question, match)
        return True

    def _listed_beside_ticker(self, question: str, match: re.Match[str]) -> bool:
        """Whether the word sits in a list next to another ticker: "AAPL vs ON", "ON, NVDA"."""
        before = _TICKER_BEFORE.search(question[: match.start()])
        after = _TICKER_AFTER.match(question[match.end() :])
        return any(
            found is not None
            and found.group(1) in self.tickers
            and not _is_a_word(found.group(1).casefold())
            for found in (before, after)
        )

    def _share_class(self, raw: str, share_class: str) -> str | None:
        """ "BRK.B" as listed, or "BRK.A" as the class the snapshot keeps."""
        query = self.tickers.get(f"{raw}-{share_class}".upper())
        if query is not None:
            return query
        prefix = f"{raw.upper()}-"
        other = next((ticker for ticker in self.tickers if ticker.startswith(prefix)), None)
        return self.tickers[other] if other is not None else None

    def correct(
        self, question: str, *, ignore: frozenset[str] = frozenset()
    ) -> list[CompanyMention]:
        """Close misspellings of a company name ("Microsft", "Nvida").

        A word inside a hyphened phrase ("apples-to-apples", "year-over-year")
        or an idiom ("apples to apples", "building blocks") is that phrase's,
        not a misspelt name.
        """
        candidates = self._typo_candidates
        ignore = (
            ignore
            | {
                part.casefold()
                for compound in re.findall(r"\w+(?:-\w+)+", question)
                for part in compound.split("-")
            }
            | {word for idiom in _IDIOMS.findall(normalize(question)) for word in idiom.split()}
        )
        mentions: list[CompanyMention] = []
        position = 0
        for word in normalize(question).split():
            start = position
            position += len(word) + 1
            if len(word) == _SHORT_TYPO_LENGTH and word.isalpha() and word not in ignore:
                short = _one_letter_missing(word, candidates)
                if (
                    short is not None
                    and word not in _GENERIC_WORDS
                    and word not in self.phrases
                    and all(mention.query != self.phrases[short] for mention in mentions)
                ):
                    mentions.append(
                        CompanyMention(self.phrases[short], start, word, corrected=True)
                    )
                continue
            if (
                len(word) < _TYPO_MIN_LENGTH
                or not word.isalpha()
                or word in _GENERIC_WORDS
                or word in ignore
                or word in self.phrases
                or word in _common_words()
            ):
                continue
            close = difflib.get_close_matches(word, candidates, n=1, cutoff=_TYPO_CUTOFF)
            phrase = close[0] if close and close[0][0] == word[0] else None
            if phrase is None and len(word) in _EDIT_TYPO_LENGTHS:
                phrase = _one_edit_away(word, candidates)
            if phrase is not None:
                query = self.phrases[phrase]
                if all(mention.query != query for mention in mentions):
                    mentions.append(CompanyMention(query, start, word, corrected=True))
        return mentions

    @cached_property
    def _typo_candidates(self) -> tuple[str, ...]:
        return tuple(phrase for phrase in self.phrases if len(phrase) >= _TYPO_MIN_LENGTH)

    def display_name(self, query: str) -> str:
        return self.display_names.get(query.upper(), query)


def _add_former_name(
    phrases: dict[str, str], tickers: dict[str, str], ticker: str, name: str
) -> None:
    """Add a snapshot company's former filing name before the index is frozen."""
    query = tickers.get(ticker.upper())
    core = _core_name(_SEC_STATE.sub("", name))
    if query is None or not core or any(char.isdigit() for char in core):
        return
    one_word_name = len(core) >= 4 and core not in _GENERIC_WORDS and not _ordinary(core)
    if " " in core or one_word_name:
        phrases.setdefault(core, query)


def _add_outside_name(
    phrases: dict[str, str],
    tickers: dict[str, str],
    display_names: dict[str, str],
    ticker: str,
    name: str,
) -> None:
    """Add a non-snapshot listing before the index is frozen."""
    query = ticker.upper()
    tickers.setdefault(query, query)
    display_names.setdefault(query, name)
    for core in {_core_name(name), _core_name(name, _NAME_SUFFIXES | _FUND_WORDS)}:
        if " " in core:
            phrases.setdefault(core, query)


def _add_filer_name(
    phrases: dict[str, str],
    display_names: dict[str, str],
    ticker: str,
    name: str,
    *,
    reserved: frozenset[str],
) -> None:
    """Add an operating filer outside the snapshot before the index is frozen."""
    core = _core_name(_SEC_STATE.sub("", name))
    words = core.split()
    if len(words) < 2 or any(word in reserved or word.isdigit() for word in words):
        return
    query = ticker.upper()
    if phrases.setdefault(core, query) == query:
        display_names.setdefault(query, name)


def _one_letter_missing(word: str, candidates: Sequence[str]) -> str | None:
    """The one five-letter single-word name that ``word`` is missing a letter of.

    The dropped letter is inside the word: "Appl" is a prefix of several names
    (Apple, Applied Materials, AppLovin), so it is left for the resolver to refuse.
    """
    found = [
        phrase
        for phrase in candidates
        if len(phrase) == len(word) + 1
        and " " not in phrase
        and phrase[0] == word[0]
        and any(phrase[:cut] + phrase[cut + 1 :] == word for cut in range(1, len(phrase) - 1))
    ]
    return found[0] if len(found) == 1 else None


def _one_edit_away(word: str, candidates: Sequence[str]) -> str | None:
    """The one single-word name ``word`` is a letter swap, slip, drop or extra from.

    Damerau-Levenshtein distance one, same first letter: "Nvidea" is Nvidia,
    "Telsa" is Tesla. Two names that close leave the word alone.
    """
    found = [
        phrase
        for phrase in candidates
        if " " not in phrase
        and phrase[0] == word[0]
        and abs(len(phrase) - len(word)) <= 1
        and phrase != word
        and _within_one_edit(word, phrase)
    ]
    return found[0] if len(found) == 1 else None


def _within_one_edit(left: str, right: str) -> bool:
    if len(left) == len(right):
        differ = [index for index, (a, b) in enumerate(zip(left, right, strict=True)) if a != b]
        if len(differ) == 1:
            return True
        # Two neighbouring letters swapped: "telsa".
        return (
            len(differ) == 2
            and differ[1] == differ[0] + 1
            and left[differ[0]] == right[differ[1]]
            and left[differ[1]] == right[differ[0]]
        )
    shorter, longer = sorted((left, right), key=len)
    return any(longer[:cut] + longer[cut + 1 :] == shorter for cut in range(len(longer)))


def _shouted(question: str) -> bool:
    """Whether most of the question's words are in capitals."""
    words: list[str] = re.findall(r"[A-Za-z]{2,}", question)
    if len(words) < _SHOUTED_MIN_WORDS:
        return False
    return sum(word.isupper() for word in words) >= _SHOUTED_SHARE * len(words)


@lru_cache(maxsize=1)
def _figure_words() -> frozenset[str]:
    """Words that start a figure's name: "revenue", "net", "earnings", "stock"."""
    starts = {re.split(r"[\s/_-]", phrase)[0] for phrase in metric_phrases()}
    return frozenset(
        {*starts, "stock", "shares", "earnings", "results", "financials", "filings", "10-q"}
    )


def _figure_follows(question: str, match: re.Match[str]) -> bool:
    """Whether a figure's name follows the word, or the word is the whole question."""
    rest = question[match.end() :]
    if not rest.strip(" ?!."):
        return not question[: match.start()].strip(" $")
    after = _FIGURE_AFTER.match(rest.lstrip())
    return after is not None and after.group(1).casefold() in _figure_words()


@dataclass(frozen=True)
class _Shape:
    """How a word of the question was typed: its case, a possessive, what came before."""

    typed: str
    possessive: bool
    before: str


def _word_shapes(question: str, count: int) -> list[_Shape] | None:
    """The typed form of each of ``normalize(question)``'s words, or None if they differ."""
    text = question.replace("’", "'")
    shapes: list[_Shape] = []
    end = 0
    for match in re.finditer(r"[\w&]+", text):
        word = match.group(0)
        if word.casefold() == "s" and text[match.start() - 1 : match.start()] == "'":
            # normalize() drops the "'s": the word before it is possessive.
            if shapes and match.start() - 1 == end:
                shapes[-1] = replace(shapes[-1], possessive=True)
            end = match.end()
            continue
        shapes.append(_Shape(word, False, text[end : match.start()]))
        end = match.end()
    return shapes if len(shapes) == count else None


def _is_a_word(word: str) -> bool:
    """Whether a capitalised token is plausibly a word rather than a ticker."""
    return (
        word in _ENGLISH_WORDS
        or word in _GENERIC_WORDS
        or word in _figure_words()
        or word in _common_words()
        or word in _everyday_words()
    )


def _ordinary(phrase: str) -> bool:
    """Whether a one-word name is also a word people write ("target", "oracle")."""
    return phrase in _everyday_words() or phrase in _common_words()


# Idioms whose words are the idiom's, not a misspelt company name: "apples to
# apples" is not Apple, "building blocks" is not Block.
_IDIOMS = re.compile(
    r"\b(?:apples (?:to|with|for|and) (?:apples|oranges)"
    r"|oranges (?:to|with|for|and) (?:oranges|apples)"
    r"|(?:building|stumbling|road) blocks)\b"
)
# An everyday-word name used as the word, in a normalized question: "intel" as
# information ("intel aside", "some intel on"), "micron" as a unit ("to the
# micron", "a micron"), "the apple of", "an oracle for" (ADR 0010).
_WORD_USES = re.compile(
    r"\b(?:(?P<intel>intel) aside|(?:some|any|more|no) (?P<info>intel)"
    r"|to the (?:nearest )?(?P<unit>micron)|(?:nearest|a) (?P<measure>micron)"
    r"|the (?P<apple>apple) of|an (?P<oracle>oracle) (?:for|of))\b"
)


def word_uses(question: str) -> tuple[str, ...]:
    """The everyday-word names ``question`` uses as the word, apples to apples included.

    "Palantir operating income, intel aside" uses "intel"; a company named
    beside the word ("Intel and Palantir") is named all the same.
    """
    normalized = normalize(question)
    used = [
        word
        for match in _WORD_USES.finditer(normalized)
        for word in match.groupdict().values()
        if word is not None
    ]
    used += [word for idiom in _IDIOMS.findall(normalized) for word in idiom.split()]
    return tuple(dict.fromkeys(used))


def _word_use_positions(normalized: str) -> set[int]:
    """Which words of a normalized question are an everyday-word name used as the word."""
    return {
        normalized[: match.start(name)].count(" ")
        for match in _WORD_USES.finditer(normalized)
        for name, word in match.groupdict().items()
        if word is not None
    }


# Words before an everyday word that make it the word, not the company:
# "its target", "the gap", "any intel", "price target".
_WORD_BEFORE = frozenset(
    """
    a an the its their our his her my your this that these those any some no every each
    another such what which whose price key main
    """.split()  # noqa: SIM905
)
# Words that join two companies: "Target and Walmart", "Block vs PayPal".
_JOINS = frozenset({"and", "or", "&", "vs", "versus", "v", "against", "with", "to", "than"})
# Legal-form words after a name typed in full: "match group", "gap inc".
_NAME_ENDS = frozenset(
    {"inc", "corp", "corporation", "company", "co", "ltd", "plc", "holdings", "group"}
)
# Words before a company in a question: "compare Target", "what about Block?".
_COMPANY_BEFORE = frozenset(
    {"compare", "about", "between", "versus", "vs", "add", "include", "plus"}
)
# Words after a company in a follow-up: "target too", "block as well".
_COMPANY_AFTER = frozenset({"too", "also", "as"})
# A company as the object of "for" or "of" closes its clause: "revenue for Target",
# "revenue for Target last quarter", but not "a target of 30%".
_OBJECT_BEFORE = frozenset({"for", "of", "at", "from"})
_CLAUSE_AFTER = frozenset(
    {
        "last",
        "past",
        "previous",
        "prior",
        "trailing",
        "recent",
        "most",
        "in",
        "over",
        "since",
        "during",
        "this",
        "and",
        "or",
        "vs",
        "versus",
        "compared",
        "q1",
        "q2",
        "q3",
        "q4",
        "fy",
    }
)
# Verbs a company does in a question: "how did Target do", "is Block growing".
_COMPANY_VERBS = frozenset(
    """
    do does did doing done perform performs performed performing earn earns earned earning
    make makes made making report reports reported reporting grow grows grew growing
    spend spends spent stack stacks stacked rank ranks ranked compare compares compared
    """.split()  # noqa: SIM905
)


def _as_companies(
    words: list[str],
    shapes: list[_Shape],
    spans: list[tuple[int, int]],
    tentative: list[tuple[int, str, CompanyMention]],
    strict: AbstractSet[int] = frozenset(),
) -> set[int]:
    """The everyday-word names in ``tentative`` the question uses as companies.

    A name filings write capitalised ("Oracle", "Intel") is kept unless typed
    in lower case after a determiner or possessive ("ask the oracle", "any
    intel"). A word filings write in lower case ("target", "block", "gap") must
    be read as a company. Kept are the words the question uses so: typed with a capital
    mid-sentence ("is Target growing"), possessive ("target's margin"), listed
    with another company ("Target and Walmart"), the object of a comparison
    ("what about block?"), followed by a figure or a company's verb ("target
    revenue", "how did gap do"), or the whole question. Dropped is the word
    after a determiner or another word's possessive ("its target", "Nvidia's
    target margin"), and a lower-case word where the question capitalises the
    companies it names ("Nvidia target margin").
    """
    alphabetic = [shape.typed for shape in shapes if shape.typed.isalpha()]
    capitals = sum(word[0].isupper() for word in alphabetic)
    # A shouted or Title Case question says nothing by its capitals.
    cased = not (
        len(alphabetic) >= _SHOUTED_MIN_WORDS and capitals >= _SHOUTED_SHARE * len(alphabetic)
    )
    kept: set[int] = set()
    everyday: list[int] = []
    for start, _, _ in tentative:
        if start in strict or words[start] in _everyday_words():
            everyday.append(start)
        elif not (shapes[start].typed.islower() and _word_before(words, shapes, start)):
            # A name filings capitalise ("Nvidia", "Oracle") is a company unless
            # the question plainly uses the word: "ask the oracle", "any intel".
            kept.add(start)
    company_words = {index for start, stop in spans for index in range(start, stop)} | kept
    named_in_capitals = any(shapes[index].typed[0].isupper() for index in company_words)

    def _sentence_start(index: int) -> bool:
        return index == 0 or re.search(r"[.!?:;]\s*$", shapes[index].before) is not None

    def _joined(index: int) -> bool:
        for step in (-1, 1):
            near, far = index + step, index + 2 * step
            if not 0 <= near < len(words):
                continue
            if near in company_words:
                # "Target, Walmart" or "Target/Walmart"
                if re.search(r"[,/;]", shapes[max(near, index)].before):
                    return True
            elif words[near] in _JOINS and far in company_words:
                return True
        return False

    def _as_company(start: int) -> bool:
        shape = shapes[start]
        previous = words[start - 1] if start else None
        following = words[start + 1] if start + 1 < len(words) else None
        lower = shape.typed.islower()
        if len(words) == 1 or (
            # A capital says a name, not which company: "banks in Texas".
            cased and not lower and not _sentence_start(start) and start not in strict
        ):
            return True
        if _joined(start) or following in _NAME_ENDS:
            # "the Progressive Corporation": a legal form after the word makes it a name.
            return True
        if _word_before(words, shapes, start) or (cased and lower and named_in_capitals):
            return False
        return (
            shape.possessive
            or following in _figure_words()
            or following in _COMPANY_VERBS
            or following in _COMPANY_AFTER
            or previous in _COMPANY_BEFORE
            or (previous in _OBJECT_BEFORE and (following is None or following in _CLAUSE_AFTER))
            # "Target?" or "Revenue, Target" ends the question.
            or (not lower and following is None)
        )

    # A company found here can join the next: "compare target and gap".
    changed = True
    while changed:
        changed = False
        for start in everyday:
            if start not in company_words and _as_company(start):
                kept.add(start)
                company_words.add(start)
                changed = True
    return kept


def _word_before(words: list[str], shapes: list[_Shape], start: int) -> bool:
    """A determiner or another word's possessive before it: "its target", "Nvidia's target"."""
    return start > 0 and (words[start - 1] in _WORD_BEFORE or shapes[start - 1].possessive)


@lru_cache(maxsize=2)
def _word_list(name: str) -> frozenset[str]:
    """A word list in data/, one word per line; empty if it is missing."""
    path = Path(__file__).parent / "data" / name
    try:
        return frozenset(path.read_text(encoding="utf-8").split())
    except OSError:
        return frozenset()


def _everyday_words() -> frozenset[str]:
    """Words 10-Qs mostly write in lower case mid-sentence: English, not a name.

    Built by scripts/build_everyday_words.py.
    """
    return _word_list("everyday_words.txt")


def _common_words() -> frozenset[str]:
    """Words most 10-Qs use ("being", "inflation"): English, not a misspelt name.

    Built by scripts/build_common_words.py.
    """
    return _word_list("common_words.txt")


def _char_to_word_offset(question: str, match: re.Match[str]) -> int:
    # Mentions order by position in the normalized question; the raw offset is
    # close enough to keep tickers in the order they were typed.
    return len(normalize(question[: match.start()])) + (1 if match.start() else 0)
