"""The notes an analysis answer carries: what was shown in place of what was asked.

A window shorter than asked, a fiscal fourth quarter skipped, calendars that
differ, a ranked list over a window, a company already on screen: each says
so in a line above the table.
"""

from __future__ import annotations

import re
from datetime import date

from financial_analyst_agent.graph.analysis_spec import (
    MAX_RANKED_COMPANIES,
    AnalysisSpec,
    SpecPatch,
    calendar_groups,
)
from financial_analyst_agent.guide import format_date, joined, possessive, short_name
from financial_analyst_agent.request_wording import (
    EXPLICIT_YOY,
    GROWTH,
    MAX_SINCE_QUARTERS,
    WHY_CHANGE,
    YEAR_OF_QUARTERS,
    YEAR_TO_DATE,
    YOY,
    WindowReading,
)
from financial_analyst_agent.services.fiscal_periods import (
    adjacent_quarters,
    quarters_in_span,
)

YEAR_OF_QUARTERS_BANNER = (
    "The last year: these are the four latest quarters, shown one by one rather "
    "than summed."
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


TRAILING_YEAR_BANNER = (
    "Trailing twelve months: these are the four latest quarters, shown one by one "
    "rather than summed."
)


RANKED_LATEST_QUARTER_BANNER = (
    "Ranked lists show each company's latest quarter. "
    "Name the companies to see a multi-quarter window."
)


FISCAL_Q4_GAP_BANNER = (
    "This window skips fiscal fourth quarters: companies report them in the 10-K, "
    "not a 10-Q, so they have no standalone quarterly fact."
)


PROFIT_MARGIN_IS_NET_BANNER = (
    "Profit margin here is net margin: net income as a share of revenue. "
    "Ask for gross or operating margin to see one of those."
)


# "Profit margin" with no gross, operating or net before it (ADR 0004).
_BARE_PROFIT_MARGIN = re.compile(
    r"(?<!gross )(?<!operating )(?<!net )\bprofit margin\b", re.IGNORECASE
)


CALENDARS_DIFFER_BANNER = (
    "These companies' fiscal quarters end on different dates, "
    "so each row shows the company's own quarter."
)


def annual_filer_note(names: list[str]) -> str:
    listed = joined(names)
    verb = "files" if len(names) == 1 else "file"
    return (
        f"{listed} {verb} annual reports with the SEC (Form 20-F or 40-F) rather than "
        "quarterly 10-Qs, so there are no quarterly figures to show."
    )


def metric_reading_notes(message: str, spec: AnalysisSpec) -> list[str]:
    """Say which metric a loose phrase was read as: "profit margin" is net margin."""
    if "net_margin" in spec.metrics and _BARE_PROFIT_MARGIN.search(message):
        return [PROFIT_MARGIN_IS_NET_BANNER]
    return []


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
        short_name(company.name) or company.query
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


def _named_period_notes(spec: AnalysisSpec) -> list[str]:
    """Say which quarter ends a named fiscal period stands for, and who has none."""
    notes: list[str] = []
    periods = spec.periods
    own = dict(periods.company_report_dates)
    label = periods.label
    missing = [
        short_name(company.name) or company.query
        for company in spec.companies
        if not own.get(company.key)
    ]
    single = len(periods.named) == 1 and periods.named[0].quarter is not None
    dated = [company for company in spec.companies if own.get(company.key)]
    if single and not periods.named[0].calendar and len(dated) == 1:
        company = dated[0]
        notes.append(
            f"{possessive(short_name(company.name) or company.query)} {label} ended "
            f"{format_date(own[company.key][0])}."
        )
    elif single and not periods.named[0].calendar and dated:
        ends = [
            f"{possessive(short_name(company.name) or company.query)} ended "
            f"{format_date(own[company.key][0])}"
            for company in spec.companies
            if own.get(company.key)
        ]
        if ends:
            notes.append(
                f"{label} is each company's own fiscal quarter: " + "; ".join(ends) + "."
            )
    if missing and len(missing) < len(spec.companies):
        notes.append(f"No filing for {label} from {', '.join(missing)}.")
    # "Apple revenue 2024" is four quarters; say when the filings here hold fewer.
    expected = sum(4 if period.quarter is None else 1 for period in periods.named)
    for company in dated:
        held = len(own[company.key])
        if held < expected:
            name = short_name(company.name) or company.query
            notes.append(
                f"The filings here hold {held} of the {expected} quarters in "
                f"{joined([period.label() for period in periods.named])} for {name}."
            )
    return notes


def period_notes(
    message: str, spec: AnalysisSpec, *, window: WindowReading
) -> list[str]:
    """Say plainly when the window shown is not the one the analyst asked for."""
    notes: list[str] = []
    shown_window = (
        f"the last {spec.periods.shown} quarters"
        if spec.periods.kind == "last_n_quarters"
        else "the latest quarter"
    )
    if window.unread_named_period is not None and spec.periods.kind != "named":
        notes.append(
            f"I couldn't read “{window.unread_named_period}” as a period; "
            f"this shows {shown_window}. "
            "Try “Q3 2024” or “fiscal 2025”."
        )
    if spec.periods.kind == "last_n_quarters" and window.trailing_year:
        notes.append(TRAILING_YEAR_BANNER)
    elif (
        spec.periods.kind == "last_n_quarters"
        and YEAR_OF_QUARTERS.search(message)
        and not YOY.search(message)
    ):
        notes.append(YEAR_OF_QUARTERS_BANNER)
    if spec.periods.kind != "named" and window.sub_quarter:
        notes.append(
            f"Filings report quarters, not months or weeks, so this shows {shown_window}."
        )
    if (
        "year_over_year" in spec.operations
        and GROWTH.search(message)
        and not EXPLICIT_YOY.search(message)
    ):
        notes.append(GROWTH_IS_YEAR_OVER_YEAR_BANNER)
    if WHY_CHANGE.search(message):
        notes.append(WHY_CHANGE_BANNER)
    if YEAR_TO_DATE.search(message):
        notes.append(
            f"Year-to-date totals aren't supported yet, so this shows {shown_window}. "
            "Try “last 4 quarters”."
        )
    if spec.periods.kind == "named":
        notes.extend(_named_period_notes(spec))
        if spec.constituents is not None:
            notes.append(RANKED_LATEST_QUARTER_BANNER)
        return notes
    if spec.constituents is not None and spec.periods.kind == "last_n_quarters":
        # compile_tasks does not expand ranked lists over a period window; say so
        # instead of showing a "Last N quarters" chip over one quarter of data.
        notes.append(RANKED_LATEST_QUARTER_BANNER)
    windows = [spec.periods.report_dates]
    if spec.periods.kind == "last_n_quarters" and spec.companies:
        groups = calendar_groups(spec)
        windows = [dates for _, dates in groups]
        if len(groups) > 1:
            notes.append(CALENDARS_DIFFER_BANNER)
    if any(
        not adjacent_quarters(newer, older)
        for dates in windows
        for newer, older in zip(dates, dates[1:], strict=False)
    ):
        notes.append(FISCAL_Q4_GAP_BANNER)
    if spec.periods.kind == "last_n_quarters":
        notes.extend(_window_notes(window, windows))
    return notes


def _window_notes(window: WindowReading, windows: list[tuple[date, ...]]) -> list[str]:
    """Say when a window is shorter than asked: capped, or more than the filings hold."""
    notes = list(window.interpretation_notes)
    shown = max((len(dates) for dates in windows), default=0)
    if window.since_year is not None:
        return [*notes, *_since_notes(window.since_year, windows, shown)]
    wanted = window.asked_quarters
    if wanted is not None and 0 < shown < wanted:
        notes.append(f"The filings here hold only {shown} of the {wanted} quarters asked for.")
    return notes


def _since_notes(year: int, windows: list[tuple[date, ...]], shown: int) -> list[str]:
    """A "since" window's span, counted from the newest filed quarter, not from today.

    The span is capped as any window is; a quarter is missing only when the
    filings lack one that ended inside the span.
    """
    newest = max((dates[0] for dates in windows if dates), default=None)
    if newest is None:
        return []
    span = quarters_in_span(year, newest)
    notes: list[str] = []
    if span > MAX_SINCE_QUARTERS:
        notes.append(
            f"Quarters since {year} number {span}; a window shows at most "
            f"{MAX_SINCE_QUARTERS}, so this asks for the latest {MAX_SINCE_QUARTERS}."
        )
    wanted = min(span, MAX_SINCE_QUARTERS)
    if 0 < shown < wanted:
        notes.append(f"The filings here hold only {shown} of the {wanted} quarters since {year}.")
    return notes
