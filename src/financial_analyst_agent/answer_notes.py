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
from financial_analyst_agent.guide import (
    format_date,
    in_sentence,
    joined,
    possessive,
    short_name,
)
from financial_analyst_agent.request_wording import EXPLICIT_YOY, GROWTH, WHY_CHANGE
from financial_analyst_agent.services.filing_selector import FISCAL_WEEK_TOLERANCE
from financial_analyst_agent.services.metric_catalog import (
    METRIC_DISPLAY,
    segment_note,
    segment_term,
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
        (row.cik or row.company_name, row.newer_filing_end)
        for row in rows
        if row.value is not None and row.newer_filing_end is not None
    }
    for row in rows:
        company = row.cik or row.company_name
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
        named = []
        for company, (name, dates) in companies.items():
            short = short_name(name) or name
            if (company, metric) in shown and dates:
                short += f" ({joined([format_date(day) for day in dates])})"
            named.append(short)
        # What was looked for and not found, not what the company reports: a
        # quarter can be beyond what is on file, or the line tagged in a way this
        # does not read.
        if len(named) == 1:
            (only,) = named
            when = where = ""
            if only.endswith(")"):
                only, _, dates_shown = only[:-1].partition(" (")
                when = f" for {dates_shown}"
                where = " for that quarter" if " and " not in dates_shown else " for those quarters"
            else:
                where = " in its filings"
            notes.append(
                f"{possessive(only)} {label} is missing{when}: no standalone quarterly "
                f"{lacked} was found{where}, which {label} needs."
            )
        else:
            notes.append(
                f"{label[:1].upper()}{label[1:]} is missing for {joined(named)}: no standalone "
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
