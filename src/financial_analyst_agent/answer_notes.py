"""The notes an analysis answer carries: what was shown in place of what was asked.

A fund or annual filer left out, a formula's part missing, a company already
on screen, a ranking shorter than asked: each says so in a line above the
table. The notes about the periods shown come from ``period_selection``; the
change banners here sit between its two lists.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import date

from financial_analyst_agent.contracts import TableRow
from financial_analyst_agent.graph.analysis_spec import (
    MAX_RANKED_COMPANIES,
    AnalysisSpec,
    ResolvedCompany,
    SpecPatch,
)
from financial_analyst_agent.prose import format_date, in_sentence, joined, possessive, short_name
from financial_analyst_agent.request_wording import EXPLICIT_YOY, GROWTH, WHY_CHANGE
from financial_analyst_agent.services.filing_selector import FISCAL_WEEK_TOLERANCE
from financial_analyst_agent.services.metric_catalog import (
    METRIC_DISPLAY,
    resolve_metric_phrases,
    segment_note,
    segment_term,
    unworked_share,
)

WHY_CHANGE_BANNER = (
    "Filings report what changed, not why: here is the change. Management explains "
    "the quarter in the 10-Q's MD&A, and “what changed in the latest 10-Q” shows it."
)


GROWTH_IS_YEAR_OVER_YEAR_BANNER = (
    "Growth here is year over year: each quarter against the same quarter a year "
    "earlier, as filings and analysts compare quarters. Ask for sequential growth to "
    "compare each quarter with the one before."
)


PROFIT_MARGIN_IS_NET_BANNER = (
    "Profit margin here is net margin: net income as a share of revenue. "
    "Ask for gross or operating margin to see one of those."
)


# "Profit margin" with no gross, operating or net before it (ADR 0004).
_BARE_PROFIT_MARGIN = re.compile(
    r"(?<!gross )(?<!operating )(?<!net )\bprofit margin\b", re.IGNORECASE
)


def annual_filer_note(names: list[str]) -> str:
    listed = joined(names)
    verb = "files" if len(names) == 1 else "file"
    return (
        f"{listed} {verb} annual reports with the SEC (Form 20-F or 40-F) rather than "
        "quarterly 10-Qs, so there are no quarterly figures to show."
    )


def fund_note(funds: list[tuple[str, str]]) -> str:
    """Say a fund named beside a company is left out: "SPY (SPDR S&P 500 ETF Trust) is a fund"."""
    listed = joined([f"{ticker} ({_name_in_prose(name)})" for ticker, name in funds])
    if len(funds) == 1:
        return f"{listed} is a fund, not an operating company, so it is left out."
    return f"{listed} are funds, not operating companies, so they are left out."


def missing_component_notes(rows: Sequence[TableRow]) -> list[str]:
    """Say which part of a formula the filings lack, where a row has no value for it.

    EBITDA is operating income plus depreciation and amortization (ADR 0008). A
    company whose filings report no standalone quarterly depreciation and
    amortization has no EBITDA, and so no change in it; the cell reads "Missing
    fact", and this names the part, so a change never goes missing without a word.
    Companies lacking the same parts of a metric share one note; a company's
    quarters are named only where it has the figure for others in the window.
    """
    # (metric, parts) → company key → (name, the quarters missing it)
    missing: dict[tuple[str, tuple[str, ...]], dict[str, tuple[str, list[date]]]] = {}
    shown: set[tuple[str, str]] = set()
    # A newest quarter SEC's structured data lacks: the newer-filing banner says so.
    pending: set[tuple[str, date]] = {
        (row.company_key, row.newer_filing_end)
        for row in rows
        if row.value is not None and row.newer_filing_end is not None
    }
    for row in rows:
        company = row.company_key
        if row.missing_components:
            if row.end_date is not None and any(
                company == other and abs(row.end_date - end) <= FISCAL_WEEK_TOLERANCE
                for other, end in pending
            ):
                continue
            companies = missing.setdefault((row.metric, tuple(row.missing_components)), {})
            _name, dates = companies.setdefault(company, (row.company_name, []))
            if row.end_date is not None:
                dates.append(row.end_date)
        elif row.value is not None and row.comparison is None:
            shown.add((company, row.metric))
    notes: list[str] = []
    for (metric, parts), companies in missing.items():
        label = _metric_in_prose(metric)
        lacked = joined([_metric_in_prose(part) for part in parts], "or")
        # (short name, the quarters named): a company's quarters are named only
        # where it has the figure for others in the window. Kept as a pair, not
        # formatted and parsed back: eleven snapshot short names end in ")".
        named = [
            (
                short_name(name) or name,
                [format_date(day) for day in dates] if (company, metric) in shown else [],
            )
            for company, (name, dates) in companies.items()
        ]
        # What was looked for and not found, not what the company reports: a
        # quarter can be beyond what is on file, or the line tagged in a way this
        # does not read.
        if len(named) == 1:
            ((only, quarters),) = named
            if quarters:
                when = f" for {joined(quarters)}"
                where = " for that quarter" if len(quarters) == 1 else " for those quarters"
            else:
                when = ""
                where = " in its filings"
            notes.append(
                f"{possessive(only)} {label} is missing{when}: no standalone quarterly "
                f"{lacked} was found{where}, which {label} needs."
            )
        else:
            listed = joined(
                [
                    f"{short} ({joined(quarters)})" if quarters else short
                    for short, quarters in named
                ]
            )
            notes.append(
                f"{label[:1].upper()}{label[1:]} is missing for {listed}: no standalone "
                f"quarterly {lacked} was found in their filings, which {label} needs."
            )
    return notes


def _metric_in_prose(metric: str) -> str:
    display = METRIC_DISPLAY.get(metric)
    return in_sentence(display.label if display is not None else metric.replace("_", " "))


def _name_in_prose(name: str) -> str:
    """ "SPDR S&P 500 ETF TRUST" → "SPDR S&P 500 ETF Trust"; a mixed-case name as it is.

    SEC shouts a name. A word of up to three letters (ETF, BDC), or of four with
    no vowel (SPDR), is an acronym and keeps its case; every other word is
    capitalised.
    """
    words = name.split()
    if not all(word.isupper() for word in words if word.isalpha()):
        return name

    def acronym(word: str) -> bool:
        return len(word) <= 3 or (len(word) == 4 and not set(word) & set("AEIOU"))

    return " ".join(
        word if not word.isalpha() or acronym(word) else word.capitalize() for word in words
    )


def metric_reading_notes(message: str, spec: AnalysisSpec) -> list[str]:
    """Say which metric a loose phrase was read as: "profit margin" is net margin."""
    if "net_margin" in spec.metrics and _BARE_PROFIT_MARGIN.search(message):
        return [PROFIT_MARGIN_IS_NET_BANNER]
    return []


def segment_notes(message: str, spec: AnalysisSpec) -> list[str]:
    """Say a segment's figure is the company-wide one, whichever planner read it.

    "iPhone sales" shows Apple's revenue: filings' structured data reports
    totals. A ranking ranks companies, not segments, so it says nothing.
    """
    term = segment_term(message)
    if term is None or not spec.metrics or spec.constituents is not None:
        return []
    return [segment_note(term)]


def short_ranking_notes(spec: AnalysisSpec) -> list[str]:
    """Say so when an industry has fewer snapshot members than the ranking asked for."""
    ranked = spec.constituents
    if ranked is None or not ranked.members or len(ranked.members) >= ranked.limit:
        return []
    count = len(ranked.members)
    noun = "company" if count == 1 else "companies"
    return [
        f"The snapshot holds only {count} {noun} in {ranked.industry}, so this list "
        f"is shorter than the {ranked.limit} asked for."
    ]


def capped_ranking_notes(patch: SpecPatch) -> list[str]:
    """Say so when a ranking asked for more companies than one lists."""
    if patch.ranked_request is None or patch.ranked_request.limit <= MAX_RANKED_COMPANIES:
        return []
    return [
        f"A ranking lists at most {MAX_RANKED_COMPANIES} companies, so this shows the "
        f"top {MAX_RANKED_COMPANIES} rather than {patch.ranked_request.limit}."
    ]


def already_present_notes(
    patch: SpecPatch, current: AnalysisSpec | None, spec: AnalysisSpec
) -> list[str]:
    """Say so when an "add" names a company the analysis already has."""
    if current is None or patch.mode != "extend" or not patch.add_companies:
        return []
    before = {company.cik for company in current.companies if company.cik}
    if len(spec.companies) > len(current.companies):
        return []
    names = [
        _shown_name(company)
        for company in spec.companies
        if company.cik in before
        and any(
            token.casefold() in (company.query.casefold(), company.ticker.casefold())
            or token.casefold() in company.name.casefold()
            for token in patch.add_companies
        )
    ]
    if not names:
        return []
    return [f"{' and '.join(names)} {'is' if len(names) == 1 else 'are'} already in this analysis."]


def _shown_name(company: ResolvedCompany) -> str:
    """The name a note calls a company by: its short name, or the words that named it."""
    return short_name(company.name) or company.query


WHY_NOT_ANSWERED_NOTE = (
    "Filings report what happened, not why, so the “why” is not answered here. "
    "Management explains the quarter in the 10-Q's MD&A, and “what changed in the "
    "latest 10-Q” shows it."
)

# An amount, its number read whole (possessive): "over 12 quarters" is not "over 1".
# A year ("over 2024") and a span of time or a count ("over 3 fiscal years", "more
# than 5 companies") are not amounts a company would have to pass.
_YEAR = r"(?:19|20)\d\d\b(?![%.,\d])"
_SPAN = (
    r"\s+(?:[a-z-]+\s+)?"
    r"(?:quarters?|years?|months?|weeks?|days?|companies|stocks|firms|names)\b"
)
_AMOUNT = (
    rf"(?!{_YEAR})\$?\d[\d,]*+(?:\.\d++)?"
    r"(?:\s*(?:%|percent\b|x\b|(?:bn|[bmkt]|billion|million|trillion|thousand)\b))?"
    rf"(?!{_SPAN})"
)
# A figure past a threshold: "growth above 20%", "P/E under 15", "more than $10B",
# "between $5B and $20B", "20% or more", "$1T+".
_THRESHOLD = re.compile(
    r"(?:\b(?:more|greater|higher|bigger|larger|less|lower|fewer|smaller) than"
    r"|\b(?:over|above|below|under|at least|at most|in excess of|north of|south of)"
    r"|\bexceed(?:s|ing)?|[<>]=?)"
    rf"\s*{_AMOUNT}"
    rf"|\bbetween\s+{_AMOUNT}\s+and\s+{_AMOUNT}"
    rf"|(?<![\w.$]){_AMOUNT}"
    r"(?:\+|\s+(?:plus|or (?:more|higher|greater|above|over|less|lower|below|fewer|under))\b)",
    re.IGNORECASE,
)
# A quality, or an index or exchange a company would have to be in: rankings take
# the largest companies by market cap and filter on nothing else. "The most
# profitable" orders rather than screens; "S&P Global" and "Dow Inc." are companies.
_CONDITION = re.compile(
    r"(?<!most )(?<!more )(?<!least )(?<!less )\b(?:un)?profitable\b"
    r"|\b(?:making|make|makes|losing|lose|loses) money\b"
    r"|\b(?:money|loss)[- ](?:losing|making)\b"
    r"|\b(?:positive|negative) (?:free cash flow|fcf|cash flow|earnings|net income|income"
    r"|margins?|growth|eps)\b"
    r"|\bdividend[- ]paying\b|\bpay(?:s|ing)? (?:a |any )?dividends?\b"
    r"|\bdebt[- ]free\b|\bno debt\b|\bcash[- ]rich\b|\bhigh[- ]growth\b"
    r"|\b(?:small|mid|micro)[- ]?caps?\b|\b(?:double|triple)[- ]digit\b"
    r"|\bs&p ?500\b|\bdow jones\b|\bnasdaq(?:[- ]?100)?\b|\bnyse\b"
    r"|\brussell ?(?:1000|2000|3000)\b",
    re.IGNORECASE,
)
# A place: the filings' structured data reports company-wide totals.
_REGION = re.compile(
    r"\b(?:geograph(?:y|ic|ical|ically)|by (?:regions?|country|countries|geography)"
    r"|international(?:ly)?(?! (?:accounting|financial reporting|standards))"
    r"|overseas|abroad|(?:greater |mainland )?china|europe|emea|apac"
    r"|asia(?:[- ]pacific)?|japan|india|latin america|north america|americas)\b",
    re.IGNORECASE,
)
_ASKS_WHY = re.compile(
    r"\bwhy\b|\bwhat (?:drove|drives|caused|causes|explains?|is behind|was behind)\b"
    r"|\breasons? (?:for|behind)\b|\bdrivers? (?:of|behind)\b",
    re.IGNORECASE,
)
# A ranking by how fast a figure grew, which is ordered by the figure itself. "By
# revenue and their growth" orders by revenue, as asked.
_BY_GROWTH = re.compile(
    r"\bby (?:(?!and\b|with\b|their\b|its\b|plus\b)[\w&-]+ ){0,2}growth\b"
    r"|\bfastest[- ]growing\b|\bgrew (?:the )?(?:most|fastest)\b"
    r"|\b(?:highest|most|fastest) growth\b",
    re.IGNORECASE,
)


def unapplied_notes(message: str, spec: AnalysisSpec) -> list[str]:
    """Say which words of the question the answer does not act on, whichever planner read it.

    An answer that drops part of a question looks like an answer to all of it:
    "software companies that grew more than 20% while staying profitable" shown as
    the largest software companies, or "FCF yield" beside revenue shown as revenue
    alone. Each part the analysis cannot express is named in the analyst's own
    words, with what is shown instead.
    """
    notes: list[str] = []
    if spec.constituents is not None:
        conditions = list(
            dict.fromkeys(
                [
                    *(match.group(0).strip() for match in _THRESHOLD.finditer(message)),
                    *(match.group(0) for match in _CONDITION.finditer(message)),
                    *_regions(message, spec),
                ]
            )
        )
        if conditions:
            quoted = joined([f"“{condition}”" for condition in conditions])
            verb = "is" if len(conditions) == 1 else "are"
            notes.append(
                f"I can't screen companies by a condition yet, so {quoted} {verb} not "
                "applied: the list is the largest companies by market cap."
            )
    if not spec.metrics:
        return notes
    unknown = [
        phrase.term
        for phrase in resolve_metric_phrases(message)
        if phrase.kind == "unknown" and phrase.term
    ]
    # A measure left out comes first: it is what was asked for.
    notes[:0] = [
        f"I can't look up “{term}” yet, so this answer leaves it out."
        for term in dict.fromkeys(unknown)
    ]
    if spec.constituents is not None:
        if "order_by_metric" in spec.operations and _BY_GROWTH.search(message):
            # The banner after says which figure orders the list.
            notes.append(
                "A ranking cannot be ordered by growth yet, so each company's growth is "
                "shown beside the figure the list is ordered by."
            )
    else:
        notes.extend(
            "Filings' structured data reports company-wide totals, not regions such as "
            f"“{region}”, so this shows the company-wide figure."
            for region in dict.fromkeys(_regions(message, spec))
        )
    share = unworked_share(message)
    if share is not None:
        notes.append(
            f"I divide one figure by another only for the ratios I list, so “{share}” is "
            "not worked out here: the figures are shown as reported."
        )
    if _ASKS_WHY.search(message) and not WHY_CHANGE.search(message):
        notes.append(WHY_NOT_ANSWERED_NOTE)
    return notes


def _regions(message: str, spec: AnalysisSpec) -> list[str]:
    """The places a question names, other than as part of a company's name ("Yum China")."""
    companies = [
        *spec.companies,
        *(spec.constituents.members if spec.constituents is not None else ()),
    ]
    typed = message.casefold()
    return [
        match.group(0)
        for match in _REGION.finditer(message)
        if not any(_in_typed_name(company.name, match.group(0), typed) for company in companies)
    ]


def _in_typed_name(name: str, place: str, typed: str) -> bool:
    """Whether ``place`` is a word of ``name`` that the question typed as part of the name.

    "Yum China revenue" types "Yum China"; "IBM international revenue" names a place,
    though "international" is a word of IBM's name.
    """
    words = name.casefold().replace(",", " ").split()
    place_words = place.casefold().split()
    size = len(place_words)
    for start in range(len(words) - size + 1):
        if words[start : start + size] != place_words:
            continue
        before = " ".join(words[max(start - 1, 0) : start + size])
        after = " ".join(words[start : start + size + 1])
        if (start > 0 and before in typed) or (start + size < len(words) and after in typed):
            return True
    return False


def change_banners(message: str, spec: AnalysisSpec) -> list[str]:
    """Say what a change is measured against, and that filings report no why.

    They sit between the period notes about how the words were read and those
    about what is shown (``PeriodNotes.read`` and ``.shown``).
    """
    notes: list[str] = []
    if (
        "year_over_year" in spec.operations
        and GROWTH.search(message)
        and not EXPLICIT_YOY.search(message)
    ):
        notes.append(GROWTH_IS_YEAR_OVER_YEAR_BANNER)
    if WHY_CHANGE.search(message):
        notes.append(WHY_CHANGE_BANNER)
    return notes
