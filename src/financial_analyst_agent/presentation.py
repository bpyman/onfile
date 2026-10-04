from __future__ import annotations

import re
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any
from urllib.parse import urlparse

from financial_analyst_agent.contracts import (
    ALLOWED_METRICS,
    DIFFERENCE_FORMULAS,
    EXPLORATORY_RESEARCH_BANNER,
    FORMULA_METRICS,
    MODEL_ANALYSIS_BANNER,
    MULTIPLE_FORMULAS,
    NEWS_SUMMARY_BANNER,
    NO_DIVIDEND_THIS_QUARTER,
    PER_SHARE_METRICS,
    PERCENT_FORMULAS,
    REPORTED_METRICS,
    SNAPSHOT_BANNER_PREFIX,
    SNAPSHOT_METRICS,
    SPLIT_RATIO,
    SUM_FORMULAS,
    TRAILING_YEAR_FORMULAS,
    ComparisonBase,
    Intent,
    RendererKind,
    TableRow,
    TurnResult,
    split_between,
)
from financial_analyst_agent.evidence_store import THREAD_EVIDENCE_BANNER
from financial_analyst_agent.graph.clarify import clarify_prompt
from financial_analyst_agent.guide import possessive, short_name
from financial_analyst_agent.services.fact_selector import (
    FOURTH_QUARTER_LABEL,
    TRAILING_YEAR_LABEL,
    YEAR_TO_DATE_LABEL,
)
from financial_analyst_agent.services.filing_selector import FISCAL_WEEK_TOLERANCE
from financial_analyst_agent.services.fiscal_periods import (
    BANK_REVENUE_LABEL,
    DEPRECIATION_AMORTIZATION_LABEL,
    GROSS_PROFIT_LABEL,
    REVENUE_FROM_COMPONENTS_LABEL,
)
from financial_analyst_agent.services.metric_catalog import METRIC_DISPLAY, segment_term

_MONTHS = (
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
)
_TRILLION = Decimal("1000000000000")
_BILLION = Decimal("1000000000")
_MILLION = Decimal("1000000")
_THOUSAND = Decimal("1000")
_CENTS = Decimal("0.01")
_FOUR_PLACES = Decimal("0.0001")
# Per-share figures below this keep their fractions of a cent; a share price does not.
_FINE_PER_SHARE_BELOW = Decimal("10")
_TENTH = Decimal("0.1")

_REASON_LABELS = {
    "missing_fact": "Missing fact",
    "not_operating_company": "Not an operating company",
    "period_mismatch": "Period mismatch",
    "ambiguous_concept": "Ambiguous concept",
    "zero_denominator": "Not meaningful (zero base)",
    "source_unavailable": "Source unavailable",
    "lookup_failed": "Lookup failed",
    "company_not_found": "Company not found",
    "not_reported_for_quarter": "Reported for the year only",
    "no_dividend_this_quarter": "No dividend declared this quarter",
    "not_meaningful": "Not meaningful (loss)",
    "negative_equity": "Not meaningful (negative equity)",
    "negative_revenue": "Not meaningful (negative revenue)",
    "pretax_loss": "Not meaningful (pretax loss)",
    "extreme_margin": "Not meaningful (beyond ±1,000%)",
    "latest_period_only": "Latest period only",
}
# Labels for the table's own columns; a metric's label is its catalog entry's.
_FIELD_LABELS = {
    "comparison": "Change",
    "cik": "CIK",
    "source_url": "Source URL",
    "company_name": "Company",
    "accession_number": "Accession number",
    "start_date": "Start date",
    "end_date": "End date",
}
# Marks a derived value in a table cell; a banner says how it was derived.
DERIVED_MARK = " †"
_DERIVED_NOTES = {
    FOURTH_QUARTER_LABEL: (
        "a fiscal fourth quarter is the 10-K's full year minus the 10-Q's nine months"
    ),
    YEAR_TO_DATE_LABEL: (
        "a cash-flow quarter is the 10-Q's year to date minus the previous quarter's"
    ),
    GROSS_PROFIT_LABEL: (
        "gross profit is revenue minus cost of revenue as the filing tags them; "
        "companies draw that cost line differently (an oil company's may hold only "
        "purchased crude), so derived margins compare poorly across companies"
    ),
    REVENUE_FROM_COMPONENTS_LABEL: (
        "revenue is gross profit plus cost of revenue, because the filing's own "
        "revenue figure is smaller than either, so its scale was mis-tagged"
    ),
    TRAILING_YEAR_LABEL: (
        "trailing-year net income is the last 10-K's year plus this year to date "
        "minus the same months a year earlier"
    ),
    DEPRECIATION_AMORTIZATION_LABEL: (
        "depreciation and amortization is depreciation plus amortization of intangibles"
    ),
    BANK_REVENUE_LABEL: (
        "a bank's revenue is its net interest income plus noninterest income, "
        "because it tags no total revenue"
    ),
}


def format_usd(value: Decimal) -> str:
    sign = "-" if value < 0 else ""
    amount = abs(value)
    if amount == 0:
        return "$0"
    units = ((_TRILLION, "T"), (_BILLION, "B"), (_MILLION, "M"), (_THOUSAND, "K"))
    for index, (unit, suffix) in enumerate(units):
        if amount < unit:
            continue
        scaled = (amount / unit).quantize(_CENTS, rounding=ROUND_HALF_UP)
        if scaled >= 1000 and index > 0:
            # Rounding reached the next unit: $999,996,000 is "$1.00 B", not "$1000.00 M".
            unit, suffix = units[index - 1]
            scaled = (amount / unit).quantize(_CENTS, rounding=ROUND_HALF_UP)
        return f"{sign}${scaled:.2f} {suffix}"
    grouped = f"{int(amount):,}"
    return f"{sign}${grouped}"


def format_percent(ratio: Decimal) -> str:
    percent = (ratio * Decimal("100")).quantize(_TENTH, rounding=ROUND_HALF_UP)
    return f"{percent:.1f}%"


def format_per_share(value: Decimal) -> str:
    """Cents, or up to four places when a small figure has them: a $0.2475 dividend."""
    sign = "-" if value < 0 else ""
    amount = abs(value)
    cents = amount.quantize(_CENTS, rounding=ROUND_HALF_UP)
    if amount == cents or amount >= _FINE_PER_SHARE_BELOW:
        return f"{sign}${cents:.2f}"
    fine = amount.quantize(_FOUR_PLACES, rounding=ROUND_HALF_UP).normalize()
    places = max(2, -int(fine.as_tuple().exponent))
    return f"{sign}${fine:.{places}f}"


def format_multiple(ratio: Decimal) -> str:
    scaled = ratio.quantize(_TENTH, rounding=ROUND_HALF_UP)
    return f"{scaled:.1f}x"


def format_date(value: date) -> str:
    return f"{_MONTHS[value.month - 1]} {value.day}, {value.year}"


def format_datetime_utc(value: datetime) -> str:
    aware = value if value.tzinfo is not None else value.replace(tzinfo=UTC)
    utc = aware.astimezone(UTC)
    hour12 = utc.hour % 12 or 12
    suffix = "AM" if utc.hour < 12 else "PM"
    return f"{format_date(utc.date())}, {hour12}:{utc.minute:02d} {suffix} UTC"


def format_field_name(key: str) -> str:
    display = METRIC_DISPLAY.get(key)
    label = display.label if display is not None else _FIELD_LABELS.get(key)
    if label is None:
        return " ".join(part.capitalize() for part in key.split("_"))
    return label


def _in_sentence(label: str) -> str:
    """ "Net margin" → "net margin" mid-sentence; "EBITDA" and "P/E ratio" keep their case."""
    if len(label) > 1 and (label[1].isupper() or not label[1].isalpha()):
        return label
    return label[:1].lower() + label[1:]


def format_reason(reason: str) -> str:
    label = _REASON_LABELS.get(reason)
    if label is None:
        label = " ".join(reason.split("_")).capitalize()
    return label


def chart_value_kind(metric: str) -> str:
    display = METRIC_DISPLAY.get(metric)
    return display.value_kind if display is not None else "usd"


_VALUE_FORMATTERS = {
    "multiple": format_multiple,
    "percent": format_percent,
    "per_share": format_per_share,
    "usd": format_usd,
}


def format_metric_value(metric: str, value: Decimal | None) -> str:
    if value is None:
        return ""
    return _VALUE_FORMATTERS[chart_value_kind(metric)](value)


def derived_banner(rows: list[TableRow]) -> str:
    """One line on how the table's derived values were computed, or ""."""
    labels: list[str] = []
    for row in rows:
        if row.value is None:
            continue
        for label in [row.derivation, *(component.derivation for component in row.components)]:
            if label and label not in labels:
                labels.append(label)
    if not labels:
        return ""
    notes = [_DERIVED_NOTES.get(label, label) for label in labels]
    return (
        "† Derived from reported figures because the filings do not report it on its own: "
        + "; ".join(notes)
        + ". The source facts are in the evidence."
    )


# A 13-week quarter is 91 days; a 14-week one 98. Anything longer is a long quarter.
_LONG_QUARTER_DAYS = 98


def long_quarter_banner(rows: list[TableRow]) -> str:
    """Say which quarters run longer than about 13 weeks (Costco's 16-week Q4), or ""."""
    long: dict[str, list[tuple[date, int]]] = {}
    for row in rows:
        if row.value is None or row.start_date is None or row.end_date is None:
            continue
        if row.comparison is not None or row.metric in TRAILING_YEAR_FORMULAS:
            # A change row spans both quarters it compares, not one long quarter;
            # return on equity and P/E cover a trailing year by definition.
            continue
        days = (row.end_date - row.start_date).days + 1
        if days > _LONG_QUARTER_DAYS:
            name = short_name(row.company_name) or row.company_name
            if (row.end_date, days) not in long.get(name, []):
                long.setdefault(name, []).append((row.end_date, days))
    notes: list[str] = []
    for name, quarters in long.items():
        weeks = " or ".join(str(week) for week in sorted({round(days / 7) for _, days in quarters}))
        ends = _join_words([format_date(end) for end, _ in quarters])
        plural = "quarters" if len(quarters) > 1 else "quarter"
        owner = possessive(name)
        notes.append(f"{owner} {plural} ended {ends} ran {weeks} weeks")
    if not notes:
        return ""
    return "; ".join(notes) + ", longer than the usual 13 weeks, which lifts those amounts."


def restated_banners(rows: list[TableRow]) -> list[str]:
    """Say where the table's year-earlier levels differ from the base a change used.

    A year-over-year change starts from the comparative the newer filing
    reports; the table shows each quarter as first filed. After a share split
    the two differ several times over, and the quarter-over-quarter change
    across it is left out; after a restatement they differ a little.
    """
    levels = [row for row in rows if row.comparison is None and row.value is not None]
    splits: dict[tuple[str, str], list[str]] = {}
    restated: dict[tuple[str, str], list[str]] = {}
    for row in rows:
        if row.comparison != "year_over_year" or len(row.components) != 2:
            continue
        before, after = row.components
        if before.accession_number != after.accession_number:
            continue
        first = next(
            (
                level
                for level in levels
                if (level.cik or level.company_name) == (row.cik or row.company_name)
                and level.metric == row.metric
                and level.end_date is not None
                and abs(level.end_date - before.end_date) <= FISCAL_WEEK_TOLERANCE
            ),
            None,
        )
        if first is None or first.value is None or first.value == before.value:
            continue
        key = (_owner(row), row.metric)
        ratio = abs(first.value / before.value) if before.value else Decimal(0)
        per_share = row.metric in PER_SHARE_METRICS
        if per_share and (ratio >= SPLIT_RATIO or 0 < ratio <= 1 / SPLIT_RATIO):
            splits.setdefault(key, []).append(format_date(before.end_date))
        elif abs(first.value - before.value) > abs(before.value) / 200:
            restated.setdefault(key, []).append(format_date(before.end_date))
    by_series: dict[tuple[str, str], list[TableRow]] = {}
    for level in levels:
        if level.metric in PER_SHARE_METRICS and level.end_date is not None:
            by_series.setdefault((_owner(level), level.metric), []).append(level)
    for key, series in by_series.items():
        ordered = sorted(series, key=lambda level: level.end_date or date.min, reverse=True)
        for newer, older in zip(ordered, ordered[1:], strict=False):
            if split_between(newer, older) and older.end_date is not None:
                splits.setdefault(key, []).append(format_date(older.end_date))
    notes = [
        f"{owner} {_in_sentence(format_field_name(metric))} for the "
        f"{_plural('quarter', ends)} ended {_join_words(list(dict.fromkeys(ends)))} "
        f"{'is' if len(set(ends)) == 1 else 'are'} shown as first reported, before a share "
        "split, so "
        f"{'it does' if len(set(ends)) == 1 else 'they do'} not compare with later quarters: "
        "year-over-year changes use the year-earlier figures as the later filings "
        "restate them, and no quarter-over-quarter change crosses the split."
        for (owner, metric), ends in splits.items()
    ]
    notes.extend(
        f"{owner} {_in_sentence(format_field_name(metric))} for the "
        f"{_plural('quarter', ends)} ended {_join_words(list(dict.fromkeys(ends)))} "
        "is shown as first filed; a later filing restated it, and the year-over-year "
        "change uses the restated figure that filing reports."
        for (owner, metric), ends in restated.items()
    )
    return notes


def declared_for_year_banners(rows: list[TableRow]) -> list[str]:
    """Say when a quarter's declared dividend may be the year's, not one quarter's.

    Walmart declares the year's dividend in its first quarter: that quarter
    shows $0.99 and the next ones "No dividend declared this quarter". A company
    that suspends its dividend files the same, so the note says "may". Beside
    other companies' quarters, the figure is not one quarter's dividend.
    """
    series: dict[str, list[TableRow]] = {}
    for row in rows:
        if row.metric == "dividends_per_share" and row.comparison is None and row.end_date:
            series.setdefault(row.cik or row.company_name.casefold(), []).append(row)
    others = len({row.cik or row.company_name.casefold() for row in rows}) > 1
    notes: list[str] = []
    for quarters in series.values():
        ordered = sorted(quarters, key=lambda row: row.end_date or date.min)
        for at, declared in enumerate(ordered):
            if declared.value is None or declared.value <= 0 or declared.end_date is None:
                continue
            after = 0
            for row in ordered[at + 1 :]:
                if row.value is not None or row.reason != NO_DIVIDEND_THIS_QUARTER:
                    break
                after += 1
            if not after:
                continue
            following = "the quarter after" if after == 1 else f"the {after} quarters after"
            notes.append(
                f"{_owner(declared)} {format_per_share(declared.value)} dividend per share for "
                f"the quarter ended {format_date(declared.end_date)} may cover the whole year: "
                f"none was declared in {following}, as when a company declares a year's "
                "dividend at once."
                + (
                    " Beside the other companies' quarters, it may be up to four quarters' "
                    "worth, not one."
                    if others
                    else ""
                )
            )
    return notes


def _owner(row: TableRow) -> str:
    return possessive(short_name(row.company_name) or row.company_name)


def _plural(word: str, items: list[str]) -> str:
    return word if len(set(items)) == 1 else f"{word}s"


def newer_filing_banner(rows: list[TableRow]) -> str:
    """Say which companies' newest filed quarter SEC's structured data still lacks, or ""."""
    pending: dict[str, date] = {}
    for row in rows:
        if row.value is not None and row.newer_filing_end is not None:
            name = short_name(row.company_name) or row.ticker
            pending.setdefault(name, row.newer_filing_end)
    if not pending:
        return ""
    if len(pending) == 1:
        ((name, end),) = pending.items()
        return (
            f"SEC's structured data does not yet include {name}'s filing for the quarter "
            f"ended {_date(end)}, so {name} is shown for the newest quarter SEC has."
        )
    filings = [f"{name} (quarter ended {_date(end)})" for name, end in pending.items()]
    return (
        "SEC's structured data does not yet include the newest filings from "
        f"{_join_words(filings)}, so those companies are shown for the newest quarter SEC has."
    )


def _date(day: date) -> str:
    return f"{day:%b} {day.day}, {day.year}"


def is_derived(row: TableRow) -> bool:
    """A derived quarter, or a value computed from one (ADR 0007)."""
    return bool(row.derivation) or any(component.derivation for component in row.components)


_TOOL_HEADERS = {
    "get_financials": "Looked up {what} in SEC filings",
    "compare_metrics": "Compared {what} in SEC filings",
    "rank_companies": "Ranked {what} in the universe snapshot",
    "filing_change": "Compared 10-Q text for {what}",
    "search_news": "Searched news for {what}",
    "explain_topic": "Wrote a qualitative summary of {what}",
}


def _as_iso_date(raw: object) -> date | None:
    if raw is None or raw == "":
        return None
    if isinstance(raw, datetime):
        return raw.date()
    if isinstance(raw, date):
        return raw
    text = str(raw)[:10]
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _trace_period(trace: Any) -> str:
    provenance = getattr(trace, "provenance", None) or {}
    start = _as_iso_date(provenance.get("start_date"))
    end = _as_iso_date(provenance.get("end_date"))
    labeled = _period_label(start, end)
    if labeled:
        return labeled
    args = getattr(trace, "args", None) or {}
    report = _as_iso_date(args.get("report_date"))
    if report is None:
        return ""
    return format_date(report)


def format_chart_amount(metric: str, value: object) -> str:
    if value is None or value == "":
        return ""
    try:
        amount = Decimal(str(value))
    except InvalidOperation:
        return ""
    if not amount.is_finite():
        return ""
    return format_metric_value(metric, amount)


def try_parse_datetime(raw: str) -> datetime | None:
    text = raw.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed


_TABLE_KEYS = (
    "rank",
    "company_name",
    "ticker",
    "cik",
    "metric",
    "comparison",
    "value",
    "currency",
    "start_date",
    "end_date",
    "form",
    "accession_number",
    "taxonomy",
    "concept",
    "source_url",
    "reason",
)
# A ranking stays narrow: no CIK, currency, or taxonomy. Rank-and-lookup rows
# keep their filing provenance so each ranked fact links to its 10-Q.
_RANK_TABLE_KEYS = (
    "rank",
    "company_name",
    "ticker",
    "value",
    "market_cap",
    "start_date",
    "end_date",
    "form",
    "accession_number",
    "concept",
    "source_url",
    "reason",
)
# A change row sits in the same value column as the levels it is derived from, so
# it must say what it is and carry an explicit sign.
_COMPARISON_LABELS = {
    "year_over_year": "Year over year",
    "sequential": "Quarter over quarter",
}
_LEVEL_LABEL = "Reported"
# Banner codes a qualitative turn carries, in the words the window shows.
_BANNER_COPY = {
    MODEL_ANALYSIS_BANNER: (
        "Model analysis — written by the model, not quoted from a filing. "
        "It may only repeat numbers the tools returned."
    ),
    EXPLORATORY_RESEARCH_BANNER: (
        "Exploratory research — a read-only brief from the cited sources. "
        "It reports no financial facts or computed values."
    ),
    NEWS_SUMMARY_BANNER: (
        "News summary — written by the model from the cited articles, not from SEC "
        "filings. Check a source before relying on it."
    ),
}
@dataclass(frozen=True)
class ChangeChip:
    """A fact's change on its card: "▲17.7% YoY", and what it was measured against."""

    label: str
    # "up", "down" or "flat": the arrow's colour, never good or bad.
    direction: str
    title: str


@dataclass(frozen=True)
class QuarterlyFactCard:
    company_name: str
    ticker: str
    metric_header: str
    amount: str
    period_label: str
    form: str
    accession_number: str
    concept: str
    source_url: str
    # "Quarterly fact", "Calculated", "Derived quarter" or "Balance sheet".
    kind_label: str = ""
    # The concept cut to a few words; the full name is ``concept``.
    concept_short: str = ""
    changes: tuple[ChangeChip, ...] = ()


@dataclass(frozen=True)
class ChipEdit:
    """An active-analysis chip and the follow-up its × sends, when it has one."""

    label: str
    kind: str
    remove: str | None = None
    # Why a chip has no ×, said on hover: the last company or metric, or a ranking.
    keep: str | None = None


@dataclass(frozen=True)
class DisplayTable:
    headers: tuple[str, ...]
    keys: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]
    # Each cell's value for sorting: amounts, ranks, and dates as day numbers.
    numbers: tuple[tuple[int | float | None, ...], ...] = ()
    # Each row's company key (ticker, else name): a bar chart's records carry the
    # same key, so the window can order bars as the table is sorted.
    row_keys: tuple[str, ...] = ()
    # Each cell's index into the answer's evidence, so a click opens its source.
    evidence: tuple[tuple[int | None, ...], ...] = ()
    # Each cell exactly: amounts as unrounded decimals, dates as ISO days.
    raw: tuple[tuple[str, ...], ...] = ()
    # A change cell's percent ("16.4"), beside its amount in raw; "" elsewhere.
    raw_percent: tuple[tuple[str, ...], ...] = ()


@dataclass(frozen=True)
class DisplayTrace:
    header: str
    inputs: tuple[tuple[str, str], ...]
    outputs: tuple[tuple[str, str], ...]


@dataclass(frozen=True)
class DisplayCitation:
    index: int
    title: str
    url: str
    published: str | None


@dataclass(frozen=True)
class Presentation:
    intent: str
    banners: tuple[str, ...]
    traces: tuple[DisplayTrace, ...]
    citations: tuple[DisplayCitation, ...]
    fact_card: QuarterlyFactCard | None
    table: DisplayTable | None
    essay: str | None
    message: str | None
    candidates: tuple[str, ...]
    intent_label: str = ""
    chart: ChartSpec | None = None
    evidence: tuple[EvidenceItem, ...] = ()
    disclosures: tuple[DisplayDisclosure, ...] = ()
    # The question a clarification asks; set only when candidates are offered.
    clarify_prompt: str | None = None
    # Next questions the window offers as one-tap chips.
    suggestions: tuple[str, ...] = ()
    # "info" for a guide reply, "warning" for a refusal.
    message_tone: str = "warning"
    # One sentence that answers the question before the table ("grew 17.8%").
    headline: str | None = None
    # Small trend charts beside one company's overview: revenue, net margin.
    trends: tuple[ChartSpec, ...] = ()


def metric_legend() -> tuple[str, ...]:
    return tuple(format_field_name(metric) for metric in ALLOWED_METRICS)


def metric_groups() -> tuple[tuple[str, tuple[str, ...]], ...]:
    return (
        (
            "Reported (SEC EDGAR)",
            tuple(format_field_name(metric) for metric in REPORTED_METRICS),
        ),
        ("Calculated", tuple(format_field_name(metric) for metric in FORMULA_METRICS)),
        (
            "Daily snapshot (FMP)",
            tuple(format_field_name(metric) for metric in SNAPSHOT_METRICS),
        ),
    )


_INTENT_LABELS = {
    "lookup": "Quarterly lookup",
    "compare": "Comparison",
    "rank": "Industry ranking",
    "rank_and_lookup": "Rank and lookup",
    "explain": "Qualitative analysis",
    "news_and_explain": "Current events",
    "exploratory_research": "Exploratory research",
    "filing_change": "Filing change",
}

_LATEST_QUARTER_RULE = "Latest standalone quarterly 10-Q; no year-to-date derivation."
_SNAPSHOT_RULE = "Universe snapshot market data; not a 10-Q filing fact."
_FORMULA_RULE = "Calculated from the listed component facts; no LLM arithmetic."
_MIXED_PERIOD_CAPTION = "Periods differ by issuer: each bar is the company's own quarter."


@dataclass(frozen=True)
class ChartSpec:
    """A chart plus every piece of text it shows, so no client formats a number.

    ``value_kind`` picks the axis tick style and ``metric_label`` titles the axis.
    Trend lines also carry ``period_labels`` (one per record), ``series`` (the
    company keys of each record), and ``amounts`` (each record's values as the
    table formats them), so tooltips read the same strings as the table.
    """

    kind: str
    title: str
    records: tuple[dict[str, object], ...]
    metric: str = ""
    caption: str = ""
    horizontal: bool = False
    value_kind: str = "usd"
    metric_label: str = ""
    period_labels: tuple[str, ...] = ()
    series: tuple[str, ...] = ()
    amounts: tuple[dict[str, str], ...] = ()
    # The caption once the analyst re-sorts the table: bars then follow the
    # table, so a caption saying how the server ordered them would be wrong.
    resorted_caption: str = ""
    # A trend's short name per series (its ticker), for end labels and the legend.
    series_labels: tuple[str, ...] = ()
    # A trend's evidence index per record and series, as ``amounts`` is keyed.
    evidence: tuple[dict[str, int], ...] = ()
    # The series whose point in each record is derived (†): drawn hollow.
    derived: tuple[tuple[str, ...], ...] = ()


@dataclass(frozen=True)
class EvidenceItem:
    label: str
    amount: str
    raw_amount: str
    company_name: str
    ticker: str
    cik: str
    concept: str
    period_label: str
    accession_number: str
    form: str
    source_url: str
    selection_rule: str
    # raw_amount for reading: "44,047,000,000", a ratio to six decimals.
    exact_amount: str = ""


@dataclass(frozen=True)
class DisplayDisclosure:
    section_label: str
    change_kind: str
    before_text: str
    after_text: str
    older_accession: str
    newer_accession: str
    older_url: str
    newer_url: str
    subsection: str = ""


def intent_label(intent: str) -> str:
    return _INTENT_LABELS.get(intent, format_field_name(intent))


def spec_chips(spec: Any) -> tuple[str, ...]:
    """Compact labels for the active analysis spec."""
    chips: list[str] = []
    companies = getattr(spec, "companies", ())
    for company in companies:
        label = company.ticker or company.name
        if label and label != "unknown":
            chips.append(label)
    constituents = getattr(spec, "constituents", None)
    if constituents is not None:
        chips.append(f"Top {constituents.limit} {constituents.industry}")
    for metric in getattr(spec, "metrics", ()):
        chips.append(format_field_name(str(metric)))
    periods = getattr(spec, "periods", None)
    as_of = getattr(spec, "as_of", None)
    if isinstance(as_of, date):
        # Market cap and price are the snapshot's, not a quarter's.
        chips.append(f"As of {format_date(as_of)}")
    elif constituents is not None:
        # A ranking shows each company's latest quarter whatever period was named.
        chips.append("Latest quarter")
    elif periods is not None:
        kind = getattr(periods, "kind", "")
        if kind == "last_n_quarters":
            chips.append("Last quarter" if periods.count == 1 else f"Last {periods.count} quarters")
        elif kind == "named":
            chips.append(getattr(periods, "label", "") or "Named period")
        else:
            chips.append("Latest quarter")
    for operation in getattr(spec, "operations", ()):
        label = _OPERATION_CHIPS.get(str(operation))
        if label:
            chips.append(label)
    return tuple(chips)


_KEEP_LAST = {
    "company": "The only company here. Name another to look at instead, or start over.",
    "metric": "The only metric here. Name another to show instead, or start over.",
    "constituents": "The ranking is what this analysis lists. Ask for another, or start over.",
}
# A window or a named period goes back to the latest quarter, as a person would ask.
_LATEST_QUARTER_EDIT = "latest quarter"
_REMOVE_OPERATION = {"Year over year": "remove year over year"}


def spec_chip_edits(spec: Any) -> tuple[ChipEdit, ...]:
    """``spec_chips`` with what kind each is and the follow-up its × sends.

    The follow-ups are the planner's own words ("remove Apple", "drop revenue",
    "latest quarter", "remove year over year"). The last company or metric, and a
    ranking, have none: removing it would leave nothing to show, and ``keep``
    says so.
    """
    companies = [
        company
        for company in getattr(spec, "companies", ())
        if (company.ticker or company.name) and (company.ticker or company.name) != "unknown"
    ]
    metrics = [str(metric) for metric in getattr(spec, "metrics", ())]
    ranked = getattr(spec, "constituents", None) is not None
    kinds: list[str] = ["company"] * len(companies)
    if ranked:
        kinds.append("constituents")
    kinds.extend(["metric"] * len(metrics))
    removals: list[str | None] = [
        f"remove {short_name(company.name) or company.query or company.ticker}"
        if len(companies) > 1
        else None
        for company in companies
    ]
    if ranked:
        removals.append(None)
    removals.extend(
        f"drop {_in_sentence(format_field_name(metric))}" if len(metrics) > 1 else None
        for metric in metrics
    )
    edits: list[ChipEdit] = []
    for index, label in enumerate(spec_chips(spec)):
        kind = kinds[index] if index < len(kinds) else "period"
        if kind == "period" and label in _OPERATION_CHIPS.values():
            kind = "operation"
        if index < len(removals):
            remove = removals[index]
        elif kind == "operation":
            remove = _REMOVE_OPERATION.get(label)
        else:
            # A ranking and a snapshot figure show their own period, not one asked for.
            moved = label != "Latest quarter" and not label.startswith("As of")
            remove = _LATEST_QUARTER_EDIT if moved and not ranked else None
        keep = _KEEP_LAST.get(kind) if remove is None else None
        edits.append(ChipEdit(label=label, kind=kind, remove=remove, keep=keep))
    return tuple(edits)


# Companies and metrics the "+" on the active analysis offers, in the planner's words.
# The companies are ones the recorded runtime holds filings for.
_QUICK_COMPANIES = ("Apple", "Microsoft", "Alphabet", "NVIDIA", "JPMorgan", "Eli Lilly")
_QUICK_METRICS = ("revenue", "net_income", "operating_margin", "net_margin", "free_cash_flow")
_QUICK_SHOWN = 4


@dataclass(frozen=True)
class QuickAction:
    label: str
    message: str


def chip_quick_actions(spec: Any) -> dict[str, tuple[QuickAction, ...]]:
    """Follow-ups the active analysis's "+" offers: a company, a metric, or a period.

    Each is a message the planner already reads ("add Apple", "make that the last
    four quarters"); a ranking's members come from the snapshot, so it takes none.
    """
    if spec is None:
        return {}
    ranked = getattr(spec, "constituents", None) is not None
    held = {
        name.casefold()
        for company in getattr(spec, "companies", ())
        for name in (company.query, company.ticker, short_name(company.name) or company.name)
        if name
    }
    companies = (
        ()
        if ranked
        else tuple(
            QuickAction(label=name, message=f"add {name}")
            for name in _QUICK_COMPANIES
            if name.casefold() not in held
        )[:_QUICK_SHOWN]
    )
    metrics = tuple(
        QuickAction(
            label=format_field_name(metric),
            message=f"add {_in_sentence(format_field_name(metric))}",
        )
        for metric in _QUICK_METRICS
        if metric not in {str(metric) for metric in getattr(spec, "metrics", ())}
    )[:_QUICK_SHOWN]
    periods: tuple[QuickAction, ...] = ()
    if not ranked and getattr(spec, "as_of", None) is None:
        kind = getattr(getattr(spec, "periods", None), "kind", "latest_quarter")
        operations = {str(operation) for operation in getattr(spec, "operations", ())}
        periods = tuple(
            action
            for action, offered in (
                (
                    QuickAction("Latest quarter", "just the latest quarter"),
                    kind != "latest_quarter",
                ),
                (
                    QuickAction("Last four quarters", "make that the last four quarters"),
                    kind != "last_n_quarters" or getattr(spec.periods, "count", 0) != 4,
                ),
                (
                    QuickAction("Year over year", "show year-over-year"),
                    "year_over_year" not in operations,
                ),
            )
            if offered
        )
    return {"company": companies, "metric": metrics, "period": periods}


# Only operations the other chips do not already show: several companies are
# "across companies", a window is "across periods", and a ranking's banner
# says what it is ordered by.
_OPERATION_CHIPS = {"year_over_year": "Year over year"}


def _fiscal_week_buckets(ends: set[date]) -> dict[date, date]:
    """Map each period end to the latest end within a fiscal week of it.

    Apple's March 28 and Microsoft's March 31 are one quarter on the chart, not
    two points a few days apart.
    """
    buckets: dict[date, date] = {}
    cluster: list[date] = []
    for end in sorted(ends):
        if cluster and end - cluster[0] > FISCAL_WEEK_TOLERANCE:
            buckets.update(dict.fromkeys(cluster, cluster[-1]))
            cluster = []
        cluster.append(end)
    buckets.update(dict.fromkeys(cluster, cluster[-1]))
    return buckets


def _no_evidence(_row: TableRow) -> int | None:
    return None


def _chart_spec(
    result: TurnResult,
    table: DisplayTable | None,
    locate: Callable[[TableRow], int | None] = _no_evidence,
) -> ChartSpec | None:
    growth = _growth_chart(result, locate)
    if growth is not None:
        return growth
    comparison_free = [row for row in result.table_rows if row.comparison is None]
    rank_cross_section = result.intent in (Intent.RANK, Intent.RANK_AND_LOOKUP)
    rows = (
        comparison_free
        if rank_cross_section
        else [row for row in comparison_free if row.value is not None]
    )
    if table is None or len(rows) < 2:
        return None
    if len({row.metric for row in rows}) > 1:
        return None
    companies = {row.company_name for row in rows}
    periods_by_company: dict[str, set[date]] = {}
    for row in rows:
        if row.end_date is None:
            continue
        periods_by_company.setdefault(row.company_name, set()).add(row.end_date)
    if not rank_cross_section and any(len(periods) >= 2 for periods in periods_by_company.values()):
        # Valued rows decide whether a trend is worth drawing; every dated row
        # keeps its quarter, so a missing one is a gap, not a skipped period.
        series_companies = {row.company_name for row in rows}
        dated = [
            row
            for row in comparison_free
            if row.end_date is not None
            and row.metric == rows[0].metric
            and row.company_name in series_companies
        ]
        buckets = _fiscal_week_buckets({row.end_date for row in dated if row.end_date})
        merged: dict[date, dict[str, object]] = {}
        sources: dict[date, dict[str, TableRow]] = {}
        for row in dated:
            if row.end_date is None:
                continue
            period = buckets[row.end_date]
            bucket = merged.setdefault(period, {"Period": period.isoformat()})
            bucket[row.company_name] = float(row.value) if row.value is not None else None
            sources.setdefault(period, {})[row.company_name] = row
        metric = rows[0].metric
        periods = sorted(merged)
        records = tuple(merged[period] for period in periods)
        series = tuple(dict.fromkeys(row.company_name for row in rows))
        return ChartSpec(
            kind="line",
            title="Trend",
            records=records,
            metric=metric,
            value_kind=chart_value_kind(metric),
            metric_label=format_field_name(metric),
            period_labels=tuple(format_date(period) for period in periods),
            series=series,
            amounts=tuple(
                {
                    key: format_chart_amount(metric, value)
                    for key, value in record.items()
                    if key != "Period"
                }
                for record in records
            ),
            **_point_sources(series, [sources[period] for period in periods], rows, locate),
        )
    if len(companies) >= 2:
        ends = {row.end_date for row in rows if row.end_date is not None}
        mixed_periods = len(ends) >= 2
        metric = rows[0].metric
        return ChartSpec(
            kind="bar",
            title="Comparison",
            records=tuple(
                _bar_record(row, ranked=rank_cross_section, evidence=locate(row)) for row in rows
            ),
            metric=metric,
            caption=_bar_caption(
                ranked=rank_cross_section,
                metric=metric,
                mixed_periods=mixed_periods,
                ordered_by=result.ordered_by,
            ),
            resorted_caption=_bar_caption(
                ranked=rank_cross_section,
                metric=metric,
                mixed_periods=mixed_periods,
                ordered_by=result.ordered_by,
                resorted=True,
            ),
            horizontal=rank_cross_section,
            value_kind=chart_value_kind(metric),
            metric_label=format_field_name(metric),
        )
    return None


def _point_sources(
    series: tuple[str, ...],
    by_period: list[dict[str, TableRow]],
    rows: list[TableRow],
    locate: Callable[[TableRow], int | None],
) -> dict[str, Any]:
    """A trend's tickers, each point's evidence index, and which points are derived."""
    tickers = {row.company_name: row.ticker for row in rows if row.ticker}
    evidence: list[dict[str, int]] = []
    for points in by_period:
        places = {name: locate(row) for name, row in points.items()}
        evidence.append({name: place for name, place in places.items() if place is not None})
    return {
        "series_labels": tuple(tickers.get(name) or short_name(name) or name for name in series),
        "evidence": tuple(evidence),
        "derived": tuple(
            tuple(name for name, row in points.items() if is_derived(row)) for points in by_period
        ),
    }


def _growth_chart(
    result: TurnResult, locate: Callable[[TableRow], int | None] = _no_evidence
) -> ChartSpec | None:
    """Growth rates, not levels: what a year-over-year or sequential question asks.

    One company draws a bar per quarter; several companies at one quarter each, a
    bar per company; several companies over quarters, a line per company. With
    several metrics the chart follows the first that changes by a percent, since
    a margin changes in points; the table keeps the levels and the rest.
    """
    changes = [
        row for row in result.table_rows if row.comparison is not None and row.value is not None
    ]
    if not changes:
        return None
    # Quarter over quarter across a window with the latest year over year beside
    # it: chart the kind that covers more quarters.
    counts = Counter(row.comparison for row in changes if row.comparison is not None)
    kind = max(counts, key=lambda kind: (counts[kind], _COMPARISON_ORDER[kind]))
    extras = [
        *(["the other metrics"] if len({row.metric for row in changes}) > 1 else []),
        *(f"the {_CHANGE_COLUMN_LABELS[other]} change" for other in counts if other != kind),
    ]
    changes = [row for row in changes if row.comparison == kind]
    metric = next((row.metric for row in changes if change_percent(row) is not None), None)
    if metric is None:
        return None
    rows = [row for row in changes if row.metric == metric]
    label = _CHANGE_COLUMN_LABELS[kind]
    humanized = format_field_name(metric)
    rest = "".join(f" and {extra}" for extra in extras)
    metric_label = f"{humanized} growth, {label}"
    quarters: dict[str, int] = {}
    for row in rows:
        company = row.cik or row.company_name
        quarters[company] = quarters.get(company, 0) + 1
    if len(quarters) == 1:
        if len(rows) < 2 or any(change_percent(row) is None for row in rows):
            return None
        ordered = sorted(rows, key=lambda row: row.end_date or date.min)
        return ChartSpec(
            kind="bar",
            title="Growth",
            records=tuple(
                _growth_bar(
                    row, name=_month_label(row.end_date), key=_dated_key(row), evidence=locate(row)
                )
                for row in ordered
            ),
            caption=f"{label} growth in {_in_sentence(humanized)}, quarter by quarter; "
            f"the table lists the amounts{rest}.",
            metric=metric,
            value_kind="percent",
            metric_label=metric_label,
        )
    if all(count == 1 for count in quarters.values()):
        return ChartSpec(
            kind="bar",
            title="Growth",
            records=tuple(
                _growth_bar(row, name=_row_key(row), key=_row_key(row), evidence=locate(row))
                for row in rows
            ),
            caption=f"{label} growth in {_in_sentence(humanized)} in each company's latest "
            "quarter; "
            f"the table lists the amounts{rest}.",
            metric=metric,
            value_kind="percent",
            metric_label=metric_label,
        )
    buckets = _fiscal_week_buckets({row.end_date for row in rows if row.end_date})
    merged: dict[date, dict[str, object]] = {}
    shown: dict[date, dict[str, str]] = {}
    sources: dict[date, dict[str, TableRow]] = {}
    for row in rows:
        if row.end_date is None:
            continue
        period = buckets[row.end_date]
        sources.setdefault(period, {})[row.company_name] = row
        percent = change_percent(row)
        merged.setdefault(period, {"Period": period.isoformat()})[row.company_name] = (
            float(percent) / 100 if percent is not None else None
        )
        if percent is not None:
            shown.setdefault(period, {})[row.company_name] = _percent_label(percent)
    periods = sorted(merged)
    series = tuple(dict.fromkeys(row.company_name for row in rows))
    return ChartSpec(
        kind="line",
        title="Growth",
        records=tuple(merged[period] for period in periods),
        caption=f"{label} growth in {_in_sentence(humanized)}, quarter by quarter; "
        f"the table lists the amounts{rest}.",
        period_labels=tuple(format_date(period) for period in periods),
        series=series,
        amounts=tuple(shown.get(period, {}) for period in periods),
        **_point_sources(series, [sources[period] for period in periods], rows, locate),
        metric=metric,
        value_kind="percent",
        metric_label=metric_label,
    )


def _growth_bar(
    row: TableRow, *, name: str, key: str, evidence: int | None = None
) -> dict[str, object]:
    """A bar for one change row: its percent, or a gap when the base was zero or below."""
    percent = change_percent(row)
    amount = _percent_label(percent) if percent is not None else ""
    return {
        "Key": key,
        "Company": name,
        "Value": float(percent) / 100 if percent is not None else 0.0,
        "Amount": amount,
        "Label": amount or "No % change",
        "Missing": percent is None,
        "Period": _period_label(row.start_date, row.end_date),
        "Evidence": evidence,
        "Derived": is_derived(row),
    }


def _month_label(end: date | None) -> str:
    return f"{end:%b} {end.year}" if end else ""


def _percent_label(percent: Decimal) -> str:
    return f"{'+' if percent > 0 else ''}{percent:.1f}%"


def _bar_record(row: TableRow, *, ranked: bool, evidence: int | None = None) -> dict[str, object]:
    ticker = row.ticker or row.company_name
    name = f"#{row.rank} {ticker}" if ranked and row.rank is not None else ticker
    missing = row.value is None
    amount = "" if missing else format_chart_amount(row.metric, row.value)
    reason = str(row.reason or "")
    label = amount if not missing else _REASON_LABELS.get(reason, reason or "Missing")
    record: dict[str, object] = {
        "Key": _row_key(row),
        "Company": name,
        "Value": float(row.value) if row.value is not None else 0.0,
        "Amount": amount,
        "Label": label,
        "Missing": missing,
        "Evidence": evidence,
        "Derived": is_derived(row),
    }
    period = _period_label(row.start_date, row.end_date)
    if period:
        record["Period"] = period
    return record


def _bar_caption(
    *,
    ranked: bool,
    metric: str,
    mixed_periods: bool,
    ordered_by: str | None = None,
    resorted: bool = False,
) -> str:
    if ranked and metric != "market_cap" and resorted:
        caption = f"Bar length is latest-quarter {format_field_name(metric)}."
        return f"{caption} Periods differ by issuer." if mixed_periods else caption
    if ranked and metric != "market_cap":
        order = (
            f"Ordered by {_in_sentence(format_field_name(ordered_by))} among the largest by "
            "market cap"
            if ordered_by
            else "Ordered by market cap"
        )
        caption = f"{order}; bar length is latest-quarter {format_field_name(metric)}."
        if mixed_periods:
            return f"{caption} Periods differ by issuer."
        return caption
    if mixed_periods:
        return _MIXED_PERIOD_CAPTION
    return ""


def _period_label(start: date | None, end: date | None) -> str:
    if start is not None and start == end:
        # A balance-sheet amount or a snapshot value: one day, not a period.
        return f"At {format_date(start)}"
    if start is not None and end is not None:
        return f"{format_date(start)} – {format_date(end)}"
    if end is not None:
        return format_date(end)
    return ""


def _selection_rule(row: TableRow) -> str:
    if row.metric in SNAPSHOT_METRICS:
        return _SNAPSHOT_RULE
    if row.comparison is not None:
        return _change_rule(row)
    # A compare row carries its one fact as a component; only a formula is calculated.
    single = row.components[0] if len(row.components) == 1 else None
    derivation = row.derivation or (
        single.derivation if single is not None and single.metric == row.metric else None
    )
    if derivation:
        return f"Derived quarter: {derivation}. The reported facts are listed."
    if row.components and (single is None or single.metric != row.metric):
        return _FORMULA_RULE
    form = row.form or (single.form if single else None)
    if form and row.start_date is not None and row.start_date == row.end_date:
        return f"Balance-sheet amount the {form} reports at the stated date."
    if form:
        return f"Standalone {form} fact for the stated period; no year-to-date derivation."
    return _LATEST_QUARTER_RULE


def _change_rule(row: TableRow) -> str:
    """A change, with the period and filing of each level it compares."""
    kind = "Year-over-year" if row.comparison == "year_over_year" else "Quarter-over-quarter"
    if len(row.components) != 2:
        return f"{kind} change between two reported periods."
    before, after = row.components
    filing = f"{after.form} {after.accession_number}"
    newer = f"{_period_label(after.start_date, after.end_date)} ({filing})"
    older = _period_label(before.start_date, before.end_date)
    if before.accession_number == after.accession_number:
        source = "as that filing reports it beside the quarter"
    else:
        source = f"as {before.form} {before.accession_number} reports it"
    marked = " Derived figures are marked †." if is_derived(row) else ""
    return f"{kind} change: {newer} against {older}, {source}.{marked}"


def _exact_amount(value: Decimal | None) -> str:
    if value is None:
        return ""
    if value == value.to_integral_value():
        return f"{int(value):,}"
    return f"{value:,.6f}".rstrip("0").rstrip(".")


def _row_provenance(row: TableRow) -> tuple[str, str, str, str]:
    """Concept, form, accession and URL, falling back to formula components."""
    concept = row.concept or ""
    form = row.form or ""
    accession_number = row.accession_number or ""
    source_url = row.source_url or ""
    if row.components and not concept:
        concept = " / ".join(component.concept for component in row.components if component.concept)
        # A snapshot component (P/E's market cap) has no filing to point at.
        filed = [component for component in row.components if component.accession_number]
        first = filed[0] if filed else row.components[0]
        form = form or first.form
        accession_number = accession_number or first.accession_number
        source_url = source_url or first.source_url
    return concept, form, accession_number, source_url


def _evidence_item(row: TableRow) -> EvidenceItem:
    amount = (
        format_metric_value(row.metric, row.value)
        if row.value is not None
        else format_reason(row.reason)
        if row.reason
        else ""
    )
    raw = str(row.value) if row.value is not None else ""
    period = _period_label(row.start_date, row.end_date)
    concept, form, accession_number, source_url = _row_provenance(row)
    if row.comparison is not None and len(row.components) == 2:
        # A change spans two periods, not the months between them; it cites the newer filing.
        before, after = row.components
        period = (
            f"{_period_label(after.start_date, after.end_date)} vs "
            f"{_period_label(before.start_date, before.end_date)}"
        )
        concept, form = after.concept, after.form
        accession_number, source_url = after.accession_number, after.source_url
    change = _COMPARISON_LABELS.get(row.comparison or "")
    metric_label = _metric_heading(row.metric) + (f" · {change.lower()} change" if change else "")
    return EvidenceItem(
        label=f"{row.company_name} · {metric_label}" + (f" · {period}" if period else ""),
        amount=amount,
        raw_amount=raw,
        exact_amount=_exact_amount(row.value),
        company_name=row.company_name,
        ticker=row.ticker,
        cik=row.cik,
        concept=concept,
        period_label=period,
        accession_number=accession_number,
        form=form,
        source_url=source_url,
        selection_rule=_selection_rule(row),
    )


def _component_rule(component: Any) -> str:
    if component.metric in SNAPSHOT_METRICS:
        return _SNAPSHOT_RULE
    derivation = getattr(component, "derivation", None)
    if derivation:
        return f"Derived: {derivation}. The reported facts are listed."
    if component.start_date == component.end_date:
        return f"Balance-sheet amount the {component.form} reports at the stated date."
    if (component.end_date - component.start_date).days > 110:
        return f"Reported {component.form} amount for the stated period."
    return (
        f"Standalone {component.form} component fact for the stated period; "
        "no year-to-date derivation."
    )


def _evidence_from_component(row: TableRow, component: Any) -> EvidenceItem:
    period = _period_label(component.start_date, component.end_date)
    return EvidenceItem(
        label=(
            f"{row.company_name} · {format_field_name(component.metric)}"
            + (f" · {period}" if period else "")
        ),
        amount=format_metric_value(component.metric, component.value),
        raw_amount=str(component.value),
        exact_amount=_exact_amount(component.value),
        company_name=row.company_name,
        ticker=row.ticker,
        cik=row.cik,
        concept=component.concept,
        period_label=period,
        accession_number=component.accession_number,
        form=component.form,
        source_url=component.source_url,
        selection_rule=_component_rule(component),
    )


def _evidence_items(row: TableRow) -> tuple[EvidenceItem, ...]:
    items = [_evidence_item(row)]
    items.extend(_evidence_from_component(row, part) for part in _sources(row.derived_from))
    items.extend(_evidence_from_component(row, part) for part in _sources(row.components))
    return tuple(items)


def _sources(components: Any) -> list[Any]:
    """Each component, then the facts it came from, however deep (a margin's
    fiscal-Q4 revenue lists its 10-K and 10-Q)."""
    flat: list[Any] = []
    for component in components:
        flat.append(component)
        flat.extend(_sources(component.derived_from))
    return flat


def _evidence_key(item: EvidenceItem) -> tuple[str, str, str]:
    return (item.label, item.raw_amount, item.accession_number)


def _evidence_in_table_order(
    rows: list[TableRow], cell_rows: list[list[TableRow | None]]
) -> tuple[tuple[EvidenceItem, ...], Callable[[TableRow], int | None]]:
    """The inspector's sources in the table's reading order, and each row's place among them.

    A cell, bar, or point opens its row's own entry; the facts a derived or
    calculated figure came from follow it.
    """
    ordered: dict[int, TableRow] = {}
    for line in cell_rows:
        for row in line:
            if row is not None:
                ordered.setdefault(id(row), row)
    for row in rows:
        ordered.setdefault(id(row), row)
    items: list[EvidenceItem] = []
    own: dict[int, tuple[str, str, str]] = {}
    for row in ordered.values():
        if not (row.cik or row.source_url or row.components):
            continue
        row_items = _evidence_items(row)
        own[id(row)] = _evidence_key(row_items[0])
        items.extend(row_items)
    evidence = _dedupe_evidence(items)
    places = {_evidence_key(item): index for index, item in enumerate(evidence)}

    def locate(row: TableRow) -> int | None:
        key = own.get(id(row))
        return places.get(key) if key is not None else None

    return evidence, locate


def _dedupe_evidence(items: Any) -> tuple[EvidenceItem, ...]:
    """One inspector entry per fact: change rows repeat the levels they compare."""
    seen: set[tuple[str, str, str]] = set()
    unique: list[EvidenceItem] = []
    for item in items:
        key = _evidence_key(item)
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return tuple(unique)


GUIDE_LABEL = "Guide"
REFUSED_LABEL = "Not answered"
CLARIFY_LABEL = "Question for you"
# One company at a glance: "How is Nvidia doing?"
OVERVIEW_LABEL = "Overview"


def present_turn(result: TurnResult) -> Presentation:
    fact_card = None
    table = None
    if (
        result.intent is Intent.LOOKUP
        and result.renderer is RendererKind.TABLE
        and len(result.table_rows) == 1
        and result.table_rows[0].value is not None
        and result.table_rows[0].start_date is not None
        and result.table_rows[0].end_date is not None
    ):
        fact_card = _fact_card(
            result.table_rows[0], result.prior_quarter_rows, result.year_earlier_rows
        )
    cell_rows: list[list[TableRow | None]] = []
    if fact_card is None and result.renderer is RendererKind.TABLE and result.table_rows:
        table, cell_rows = _display_table(
            result.table_rows, intent=result.intent, snapshot_day=_snapshot_day(result.banners)
        )
    evidence, locate = _evidence_in_table_order(result.table_rows, cell_rows)
    if table is not None:
        table = replace(
            table,
            evidence=tuple(
                tuple(locate(row) if row is not None else None for row in line)
                for line in cell_rows
            ),
        )
    disclosures = tuple(
        DisplayDisclosure(
            section_label=item.section_label,
            change_kind=item.change_kind,
            before_text=item.before_text,
            after_text=item.after_text,
            older_accession=item.older_accession,
            newer_accession=item.newer_accession,
            older_url=item.older_url,
            newer_url=item.newer_url,
            subsection=item.subsection,
        )
        for item in result.disclosure_changes
    )
    # Reusing figures already fetched is how a follow-up works, not news to the
    # reader; the evidence still records where every figure came from.
    banners = [
        _format_banner(banner) for banner in result.banners if banner != THREAD_EVIDENCE_BANNER
    ]
    derived = derived_banner(result.table_rows)
    if derived:
        banners.append(derived)
    long_quarters = long_quarter_banner(result.table_rows)
    if long_quarters:
        banners.append(long_quarters)
    newer = newer_filing_banner(result.table_rows)
    if newer:
        banners.append(newer)
    banners.extend(restated_banners(result.table_rows))
    banners.extend(declared_for_year_banners(result.table_rows))
    if result.ordered_by:
        label = _in_sentence(format_field_name(result.ordered_by))
        amount = (
            f"a higher {label}"
            if result.ordered_by in (*PERCENT_FORMULAS, *MULTIPLE_FORMULAS, *PER_SHARE_METRICS)
            else f"more {label}"
        )
        banners.append(
            f"Ordered by {label}. The companies are the largest by market cap in "
            f"the snapshot, so a smaller company with {amount} is not listed."
        )
    return Presentation(
        intent=result.intent.value,
        intent_label=(
            GUIDE_LABEL
            if result.guide
            else REFUSED_LABEL
            if result.renderer is RendererKind.REFUSE
            else CLARIFY_LABEL
            if result.renderer is RendererKind.CLARIFY
            else OVERVIEW_LABEL
            if result.trend_rows
            else intent_label(result.intent.value)
        ),
        banners=tuple(banners),
        traces=tuple(
            _display_trace(trace, names=_names_by_cik(result.table_rows))
            for trace in result.tool_traces
        ),
        citations=tuple(
            _display_citation(index, hit) for index, hit in enumerate(result.citations, start=1)
        ),
        fact_card=fact_card,
        table=table,
        chart=_chart_spec(result, table, locate),
        evidence=evidence,
        disclosures=disclosures,
        essay=result.essay,
        message=(
            _friendly_message(result.message)
            if result.renderer is not RendererKind.CLARIFY
            else None
        ),
        candidates=result.candidate_labels
        or tuple(format_field_name(name) for name in result.candidates),
        clarify_prompt=_clarify_prompt(result),
        suggestions=tuple(result.suggestions),
        message_tone="info" if result.guide else "warning",
        headline=growth_headline(result.table_rows)
        or overview_headline(result.table_rows)
        or (comparison_headline(result.table_rows, result.intent) if table is not None else None),
        trends=overview_trends(result.trend_rows),
    )


_UNKNOWN_METRIC = re.compile(r"^Unknown metric '(?P<term>[^']*)'\. Allowed: .*$", re.DOTALL)
# Themes people rank by that the snapshot does not group companies by.
_THEME_HINT = (
    "The snapshot groups companies by industry, and “{theme}” isn't one. Try {instead}, "
    "for example “top 5 {example} companies by revenue”."
)
_THEME_HINTS = {
    theme: _THEME_HINT.format(theme=label, instead=instead, example=example)
    for theme, label, instead, example in (
        ("ai", "AI", "semiconductors or software", "semiconductor"),
        ("artificial intelligence", "artificial intelligence", "semiconductors or software",
         "semiconductor"),
        ("cloud", "cloud", "software", "software"),
        ("cybersecurity", "cybersecurity", "software", "software"),
        ("crypto", "crypto", "capital markets or software", "software"),
        ("unicorn", "unicorn", "an industry such as software", "software"),
    )
}  # fmt: skip
_UNKNOWN_INDUSTRY = re.compile(r"^Unknown industry '(?P<industry>.*)'\. Allowed: (?P<allowed>.*)$")
_COMPANY_NOT_FOUND = re.compile(r"^Company not found for query '(?P<query>.*)'$")
_METRIC_EXAMPLES = "revenue, net income, R&D, or operating margin"
_FRIENDLY_MESSAGES = {
    "No recorded filing document": (
        "The recorded demo holds 10-Q text only for the companies it recorded, and "
        "this filing is not among them. With live data, any company's 10-Qs can be compared."
    ),
    "Analysis has no companies or ranked constituents": (
        "I couldn't tell which company you mean. Name a company or ticker, "
        "for example “What was Apple's revenue?”"
    ),
    "Analysis has no metrics": (
        "That leaves no metric to show. Name one, for example “Apple net income”."
    ),
    "No 10-Q or 10-Q/A filing found": (
        "This company has no 10-Q filings. Foreign private issuers file 20-F and "
        "6-K reports instead, which this app does not read yet."
    ),
    "No dividend was declared in this quarter; one was declared earlier in the fiscal year": (
        "The filing reports no dividend declared in this quarter and one declared "
        "earlier in the fiscal year. Some companies declare the whole year's dividend "
        "at once; a company that suspends its dividend reports the same way, so the "
        "filing's text says which."
    ),
    "Per-share figures for this quarter are reported only for a longer period": (
        "Filings report per-share figures such as EPS for a fiscal fourth quarter "
        "only inside the full-year total, and EPS cannot be subtracted the way "
        "revenue can, so there is no fourth-quarter figure to show."
    ),
    "No reported or derivable quarter exists for metric": (
        "This company's filings do not report that metric for this quarter. Not every "
        "company reports every line item: banks, for example, report no cost of "
        "revenue or capital spending the way operating companies do."
    ),
    "SEC's structured data does not yet include this quarter's filing": (
        "This quarter's report is filed, but SEC's structured data, which the figures "
        "here are read from, does not include it yet. It usually appears within a "
        "few weeks of the filing."
    ),
    "Multiple directly reported quarterly facts remain after precedence rules": (
        "The filing reports different figures for that metric in the same quarter, "
        "so none is shown rather than a guess."
    ),
    "No directly reported standalone-quarter fact exists for metric": (
        "This company's 10-Q does not report a standalone quarterly value for that "
        "metric. Not every company reports every line item: banks, for example, "
        "report no cost of revenue or capital spending the way operating companies do."
    ),
}


def _friendly_message(message: str | None) -> str | None:
    """Put the domain's refusal text in the window's words.

    Domain messages name catalog slugs and internal terms (the MCP server and
    tests read them as they are); the audience window should not.
    """
    if message is None:
        return None
    if message in _FRIENDLY_MESSAGES:
        return _FRIENDLY_MESSAGES[message]
    unknown = _UNKNOWN_METRIC.match(message)
    if unknown is not None:
        term = unknown.group("term")
        if term in ("", "unknown"):
            return (
                "I couldn't find a metric I can look up in that question. I answer "
                f"from SEC 10-Q facts such as {_METRIC_EXAMPLES}, for example "
                "“What was Microsoft's latest quarterly revenue?”"
            )
        if segment_term(term) is not None:
            return (
                "Filings' structured data reports company-wide figures, so segment and "
                f"operating figures such as “{term}” aren't covered. Try revenue or "
                "operating income instead."
            )
        return (
            f"I can't look up “{term}” yet. I answer from 10-Q figures such as revenue, "
            "net income, margins, EPS, free cash flow and P/E."
        )
    industry = _UNKNOWN_INDUSTRY.match(message)
    if industry is not None:
        named = industry.group("industry").strip()
        theme = _THEME_HINTS.get(named.casefold())
        if theme is not None:
            return theme
        if named.casefold() in ("", "unknown"):
            return (
                "Which industry should I rank? Name one, for example “top 5 banks” or "
                "“top 10 semiconductor companies by revenue”."
            )
        # Aliases ("finance") are lower case; the snapshot's sectors are titled.
        sectors = [name for name in industry.group("allowed").split(", ") if name[:1].isupper()]
        covers = f" It covers {_join_words(sectors)} companies." if sectors else ""
        return (
            f"I couldn't find “{named}” companies in this snapshot."
            f"{covers} You can also name an industry within those, such as "
            "semiconductors, software, pharma or banks."
        )
    missing = _COMPANY_NOT_FOUND.match(message)
    if missing is not None and missing.group("query").strip().casefold() in ("", "unknown"):
        return (
            "I couldn't tell which company you mean. Name it or use its ticker, "
            "for example “Apple revenue” or “AAPL revenue”."
        )
    if missing is not None:
        return (
            f"I couldn't find a company called “{missing.group('query')}” in the "
            "filings available here. Check the spelling, or try the ticker."
        )
    return message


def _clarify_prompt(result: TurnResult) -> str | None:
    if result.renderer is not RendererKind.CLARIFY or not result.candidates:
        return None
    return clarify_prompt(result.clarify_kind, result.clarify_subject)


_INPUT_NAMES = {"net_income_ttm": "trailing-year net income"}


def _formula_inputs(row: TableRow) -> str:
    """ "Market cap (Sep 27, 2026) ÷ trailing-year net income": what a figure is computed from."""
    operator = " ÷ "
    if row.metric in DIFFERENCE_FORMULAS:
        operator = " − "
    elif row.metric in SUM_FORMULAS:
        operator = " + "
    names = []
    for component in row.components:
        name = _INPUT_NAMES.get(component.metric) or _in_sentence(
            format_field_name(component.metric)
        )
        if component.metric in SNAPSHOT_METRICS:
            name += f" ({format_date(component.end_date)})"
        names.append(name)
    text = operator.join(names)
    return text[:1].upper() + text[1:]


def _metric_heading(metric: str) -> str:
    """A metric's name in a table or card; a trailing-year ratio says it is one."""
    label = format_field_name(metric)
    return f"{label} (trailing year)" if metric in TRAILING_YEAR_FORMULAS else label


def _fact_card(
    row: TableRow,
    prior_quarter: list[TableRow] | None = None,
    year_earlier: list[TableRow] | None = None,
) -> QuarterlyFactCard:
    assert row.start_date is not None
    assert row.end_date is not None
    concept, form, accession_number, source_url = _row_provenance(row)
    span = ""
    if row.metric in FORMULA_METRICS and row.components:
        # Calculated from its inputs, which the concept field names; no one filing's form.
        lead = "Calculated" + DERIVED_MARK if is_derived(row) else "Calculated"
        span = "Trailing year · " if row.metric in TRAILING_YEAR_FORMULAS else ""
        concept, form = _formula_inputs(row), ""
        kind = "Calculated"
    elif is_derived(row):
        lead = "Derived †"
        kind = "Derived quarter"
    elif row.start_date == row.end_date:
        lead = "Balance sheet"
        kind = "Balance sheet"
    else:
        lead = "Standalone quarter"
        kind = "Quarterly fact"
    return QuarterlyFactCard(
        kind_label=kind,
        concept_short=_short_concept(concept),
        changes=_change_chips(row, prior_quarter or [], year_earlier or []),
        company_name=row.company_name,
        ticker=row.ticker,
        metric_header=_metric_heading(row.metric),
        amount=format_metric_value(row.metric, row.value),
        period_label=f"{lead} · {span}{_period_label(row.start_date, row.end_date)}",
        form=form,
        accession_number=accession_number,
        concept=concept,
        source_url=source_url,
    )


# A concept longer than this shows its first words on the card; the tooltip has it all.
_SHORT_CONCEPT_CHARS = 26


def _short_concept(concept: str) -> str:
    """ "IncomeLossFromContinuing…" for a long XBRL concept; a short one stays whole."""
    if len(concept) <= _SHORT_CONCEPT_CHARS:
        return concept
    words = re.findall(r"[A-Z][a-z0-9]*|[a-z0-9]+|[^A-Za-z0-9]+", concept)
    kept = ""
    for word in words:
        if len(kept) + len(word) > _SHORT_CONCEPT_CHARS - 1:
            break
        kept += word
    return (kept or concept[: _SHORT_CONCEPT_CHARS - 1]).rstrip(" /") + "…"


def _change_chips(
    row: TableRow, prior_quarter: list[TableRow], year_earlier: list[TableRow]
) -> tuple[ChangeChip, ...]:
    """Year over year, then quarter over quarter from the quarter before.

    Year over year starts from the comparative the fact's own filing reports, or,
    when it reports none, from the quarter a year earlier as first filed, and the
    chip's title says which (ADR 0009). A trailing-year or snapshot figure gets
    none, and neither does a base at or below zero.
    """
    if row.value is None or row.metric in (*TRAILING_YEAR_FORMULAS, *SNAPSHOT_METRICS):
        return ()
    now = Decimal(str(row.value))
    chips: list[ChangeChip | None] = []
    before = row.year_earlier
    if before is not None:
        base = Decimal(str(before.value))
        filing = f"{before.form} {before.accession_number}".strip()
        chips.append(
            _change_chip(
                row.metric,
                now,
                base,
                "YoY",
                f"Against {format_metric_value(row.metric, base)} for "
                f"{_period_label(before.start_date, before.end_date)}, as {filing} reports it",
            )
        )
    elif len(year_earlier) == 1 and year_earlier[0].value is not None:
        first = year_earlier[0]
        filing = f"{first.form} {first.accession_number}".strip()
        chips.append(
            _change_chip(
                row.metric,
                now,
                Decimal(str(first.value)),
                "YoY",
                f"Against {_format_cell(first, 'value')} for "
                f"{_period_label(first.start_date, first.end_date)}, as first filed in "
                f"{filing}: the latest filing reports no year-earlier figure",
            )
        )
    earlier = prior_quarter[0] if len(prior_quarter) == 1 else None
    if earlier is not None and earlier.value is not None:
        source = f", from {earlier.form} {earlier.accession_number}" if earlier.form else ""
        chips.append(
            _change_chip(
                row.metric,
                now,
                Decimal(str(earlier.value)),
                "QoQ",
                f"Against {_format_cell(earlier, 'value')} for "
                f"{_period_label(earlier.start_date, earlier.end_date)}{source}",
            )
        )
    return tuple(chip for chip in chips if chip is not None)


def _change_chip(
    metric: str, now: Decimal, base: Decimal, label: str, title: str
) -> ChangeChip | None:
    if metric in PERCENT_FORMULAS:
        # A margin moves in percentage points, not a percent of itself.
        change = ((now - base) * Decimal("100")).quantize(_TENTH, rounding=ROUND_HALF_UP)
        shown = f"{abs(change):.1f} pts"
    else:
        if base <= 0:
            return None
        change = ((now - base) / base * Decimal("100")).quantize(_TENTH, rounding=ROUND_HALF_UP)
        shown = f"{abs(change):.1f}%"
    direction = "up" if change > 0 else "down" if change < 0 else "flat"
    arrow = {"up": "▲", "down": "▼", "flat": "▬"}[direction]
    return ChangeChip(label=f"{arrow}{shown} {label}", direction=direction, title=title)


def _cell_empty(value: Any) -> bool:
    return value is None or value == "" or value == []


def _numeric_cell(row: TableRow, key: str) -> int | float | None:
    if key == "rank":
        return row.rank
    if key == "value" and row.value is not None:
        return float(row.value)
    if key in ("start_date", "end_date"):
        day = getattr(row, key)
        return day.toordinal() if day is not None else None
    if key == "market_cap" and row.market_cap is not None:
        return float(row.market_cap)
    return None


def _row_key(row: TableRow) -> str:
    return row.ticker or row.company_name


def _row_keys(rows: list[TableRow]) -> tuple[str, ...]:
    """Each row's company key; with several rows a company, its quarter as well."""
    plain = [_row_key(row) for row in rows]
    if len(set(plain)) == len(plain):
        return tuple(plain)
    return tuple(_dated_key(row) for row in rows)


def _dated_key(row: TableRow) -> str:
    return f"{_row_key(row)}@{row.end_date.isoformat() if row.end_date else ''}"


WIDE_VALUE_PREFIX = "value:"
WIDE_CHANGE_PREFIX = "change:"
_CHANGE_COLUMN_LABELS: dict[ComparisonBase, str] = {"year_over_year": "YoY", "sequential": "QoQ"}


_COMPARISON_ORDER: dict[ComparisonBase | None, int] = {
    None: 0,
    "sequential": 1,
    "year_over_year": 2,
}


def _change_key(metric: str, kind: ComparisonBase | None) -> str:
    """ "change:revenue", or "change:revenue:sequential" when a table has two kinds of change."""
    return f"{WIDE_CHANGE_PREFIX}{metric}" + (f":{kind}" if kind else "")


def _wide_table(
    rows: list[TableRow], *, intent: Intent | None, snapshot_day: date | None = None
) -> tuple[DisplayTable, list[list[TableRow | None]]] | None:
    """A row per company and quarter (and change), a column per metric.

    "How is Apple doing?" and "their operating margin" read across a row, not
    down a list of company-metric pairs; over a window, each quarter is one row
    and each change one more. Provenance stays per value in the evidence list,
    so the wide table carries no filing columns.
    """
    metrics = list(dict.fromkeys(row.metric for row in rows if row.metric))
    if len(metrics) < 2 and (len(rows) < 2 or intent in (Intent.RANK, Intent.RANK_AND_LOOKUP)):
        return None
    cells: dict[tuple[str, date | None, ComparisonBase | None], dict[str, TableRow]] = {}
    for row in rows:
        place: tuple[str, date | None, ComparisonBase | None] = (
            row.cik or row.company_name,
            row.end_date,
            row.comparison,
        )
        if row.metric in cells.setdefault(place, {}):
            return None
        cells[place][row.metric] = row
    # Failed cells carry no date: fold them into their company's only row.
    for undated in [place for place in cells if place[1] is None and place[2] is None]:
        dated = [other for other in cells if other[0] == undated[0] and other != undated]
        if len(dated) == 1 and not set(cells[undated]) & set(cells[dated[0]]):
            cells[dated[0]].update(cells.pop(undated))
    # A change reads best beside its level: a row per quarter, each kind of
    # change (quarter over quarter, year over year) in its own column.
    kinds = sorted(
        {slot[2] for slot in cells if slot[2] is not None},
        key=lambda kind: _COMPARISON_ORDER[kind],
    )
    change_headers: dict[str, str] = {}
    if kinds:
        for metric in metrics:
            for kind in kinds:
                label = _CHANGE_COLUMN_LABELS[kind]
                key = _change_key(metric, kind if len(kinds) > 1 else None)
                change_headers[key] = (
                    f"{label} change"
                    if len(metrics) == 1
                    else f"{format_field_name(metric)}, {label}"
                )
        for slot in [slot for slot in cells if slot[2] is not None]:
            level = cells.setdefault((slot[0], slot[1], None), {})
            for metric, row in cells.pop(slot).items():
                level[_change_key(metric, slot[2] if len(kinds) > 1 else None)] = row
    entities = list(dict.fromkeys(slot[0] for slot in cells))
    ordered = sorted(
        cells,
        key=lambda slot: (
            entities.index(slot[0]),
            _COMPARISON_ORDER[slot[2]] > 0,
            -(slot[1].toordinal() if slot[1] else 0),
            _COMPARISON_ORDER[slot[2]],
        ),
    )
    ranked = intent in (Intent.RANK, Intent.RANK_AND_LOOKUP) and any(
        row.rank is not None for row in rows
    )
    changes = any(slot[2] is not None for slot in cells)
    keys = [
        *(["rank"] if ranked else []),
        "company_name",
        "ticker",
        *(["comparison"] if changes else []),
        *(f"{WIDE_VALUE_PREFIX}{metric}" for metric in metrics),
        *(key for key in change_headers if any(key in group for group in cells.values())),
        "end_date",
    ]
    # A trailing year or a snapshot price is not a quarter.
    quarterly = not set(metrics) & {*TRAILING_YEAR_FORMULAS, *SNAPSHOT_METRICS}
    headers = tuple(
        change_headers[key]
        if key.startswith(WIDE_CHANGE_PREFIX)
        else _metric_heading(key[len(WIDE_VALUE_PREFIX) :])
        if key.startswith(WIDE_VALUE_PREFIX)
        else ("Quarter ended" if quarterly else "Period ended")
        if key == "end_date"
        else format_field_name(key)
        for key in keys
    )
    # A snapshot figure beside filed ones says its own date, not the period's.
    dated_snapshot = snapshot_day if any(m not in SNAPSHOT_METRICS for m in metrics) else None
    rendered: list[tuple[str, ...]] = []
    numbers: list[tuple[int | float | None, ...]] = []
    raws: list[tuple[str, ...]] = []
    percents: list[tuple[str, ...]] = []
    sources: list[list[TableRow | None]] = []
    identities: list[TableRow] = []
    for group in ordered:
        by_metric = cells[group]
        first = next(iter(by_metric.values()))
        identity = next((row for row in by_metric.values() if row.ticker), first)
        ends = [row.end_date for row in by_metric.values() if row.end_date is not None]
        text: list[str] = []
        values: list[int | float | None] = []
        cell_sources: list[TableRow | None] = []
        for key in keys:
            cell_sources.append(
                by_metric.get(key[len(WIDE_VALUE_PREFIX) :])
                if key.startswith(WIDE_VALUE_PREFIX)
                else by_metric.get(key)
                if key.startswith(WIDE_CHANGE_PREFIX)
                else None
            )
            if key.startswith(WIDE_VALUE_PREFIX):
                cell = by_metric.get(key[len(WIDE_VALUE_PREFIX) :])
                if cell is None:
                    text.append("")
                    values.append(None)
                elif cell.value is None:
                    # A narrow cell: the label alone ("Missing fact"), code in evidence.
                    text.append(_REASON_LABELS.get(cell.reason or "", "") or "")
                    values.append(None)
                else:
                    shown = _format_cell(cell, "value")
                    if dated_snapshot is not None and cell.metric in SNAPSHOT_METRICS:
                        shown += f" on {format_date(dated_snapshot)}"
                    text.append(shown)
                    values.append(float(cell.value))
            elif key.startswith(WIDE_CHANGE_PREFIX):
                change = by_metric.get(key)
                if change is None or change.value is None:
                    text.append("")
                    values.append(None)
                else:
                    text.append(_format_cell(change, "value"))
                    # Sorts by the percent change where it has one, else the amount.
                    percent = change_percent(change)
                    values.append(float(percent if percent is not None else change.value))
            elif key == "end_date":
                text.append(format_date(max(ends)) if ends else "")
                values.append(max(ends).toordinal() if ends else None)
            elif key == "rank":
                rank = identity.rank if identity.rank is not None else first.rank
                text.append(str(rank) if rank is not None else "")
                values.append(rank)
            elif key == "comparison":
                text.append(_format_cell(first, "comparison"))
                values.append(None)
            else:
                text.append(_format_cell(identity, key))
                values.append(None)
        rendered.append(tuple(text))
        numbers.append(tuple(values))
        sources.append(cell_sources)
        raws.append(
            tuple(
                _raw_value(source)
                if source is not None
                else max(ends).isoformat()
                if key == "end_date" and ends
                else shown
                for key, source, shown in zip(keys, cell_sources, text, strict=True)
            )
        )
        percents.append(
            tuple(
                _raw_percent(source) if key.startswith(WIDE_CHANGE_PREFIX) and source else ""
                for key, source in zip(keys, cell_sources, strict=True)
            )
        )
        latest_end = max(ends) if ends else None
        identities.append(identity.model_copy(update={"end_date": latest_end}))
    amounts = [index for index, key in enumerate(keys) if key.startswith(WIDE_VALUE_PREFIX)]
    if not any(row[index] is not None for row in numbers for index in amounts):
        return None
    table = DisplayTable(
        headers=headers,
        keys=tuple(keys),
        rows=tuple(rendered),
        numbers=tuple(numbers),
        row_keys=_row_keys(identities),
        raw=tuple(raws),
        raw_percent=tuple(percents) if any(any(row) for row in percents) else (),
    )
    return table, sources


# A computed ratio is exact to this many places in an export; amounts never reach it.
_RAW_PLACES = Decimal("1e-10")
_RAW_EXPONENT = -10


def _raw_value(row: TableRow) -> str:
    """A cell's amount unrounded, for export; a failed cell has none.

    A ratio (a margin, a P/E) is a quotient with no end, so it is cut at ten
    decimal places rather than written to 28 digits.
    """
    if row.value is None:
        return ""
    value = row.value
    exponent = value.as_tuple().exponent
    if isinstance(exponent, int) and exponent < _RAW_EXPONENT:
        value = value.quantize(_RAW_PLACES)
    return str(value)


def _raw_percent(row: TableRow) -> str:
    """A change's percent for export, beside its amount; "" for a margin's points."""
    percent = change_percent(row)
    return str(percent) if percent is not None else ""


def _raw_cell(row: TableRow, key: str, shown: str) -> str:
    if key == "value":
        return _raw_value(row)
    if key == "market_cap":
        return str(row.market_cap) if row.market_cap is not None else ""
    if key in ("start_date", "end_date"):
        day = getattr(row, key)
        return day.isoformat() if day is not None else ""
    return shown


def _snapshot_day(banners: list[str]) -> date | None:
    for banner in banners:
        if banner.startswith(SNAPSHOT_BANNER_PREFIX):
            parsed = try_parse_datetime(banner[len(SNAPSHOT_BANNER_PREFIX) :])
            if parsed is not None:
                return parsed.date()
    return None


def _display_table(
    rows: list[TableRow], *, intent: Intent | None = None, snapshot_day: date | None = None
) -> tuple[DisplayTable, list[list[TableRow | None]]]:
    """The answer table, and the row behind each cell whose source the inspector opens."""
    wide = _wide_table(rows, intent=intent, snapshot_day=snapshot_day)
    if wide is not None:
        return wide
    allowed = _RANK_TABLE_KEYS if intent in (Intent.RANK, Intent.RANK_AND_LOOKUP) else _TABLE_KEYS
    keys = [key for key in allowed if any(not _cell_empty(getattr(row, key)) for row in rows)]
    if len({row.cik or row.company_name for row in rows}) == 1:
        # One company's table: its CIK and currency are in the evidence, not columns.
        keys = [key for key in keys if key not in ("cik", "currency")]
    metrics = {row.metric for row in rows if row.metric}
    single_metric = len(metrics) == 1
    value_header = _metric_heading(next(iter(metrics))) if single_metric else None
    if single_metric:
        keys = [key for key in keys if key != "metric"]
        if "value" not in keys:
            insert_at = 0
            for marker in ("ticker", "company_name", "rank"):
                if marker in keys:
                    insert_at = keys.index(marker) + 1
                    break
            keys.insert(insert_at, "value")
    headers = tuple(
        value_header if key == "value" and value_header else format_field_name(key) for key in keys
    )
    rendered = tuple(tuple(_format_cell(row, key) for key in keys) for row in rows)
    numbers = tuple(tuple(_numeric_cell(row, key) for key in keys) for row in rows)
    table = DisplayTable(
        headers=headers,
        keys=tuple(keys),
        rows=rendered,
        numbers=numbers,
        row_keys=_row_keys(rows),
        raw=tuple(
            tuple(_raw_cell(row, key, shown) for key, shown in zip(keys, text, strict=True))
            for row, text in zip(rows, rendered, strict=True)
        ),
    )
    return table, [[row if key == "value" else None for key in keys] for row in rows]


def _format_cell(row: TableRow, key: str) -> str:
    value = getattr(row, key)
    if key == "comparison":
        return _COMPARISON_LABELS.get(str(value), _LEVEL_LABEL) if value else _LEVEL_LABEL
    if _cell_empty(value):
        return ""
    if key == "value":
        if row.comparison is not None and row.metric in PERCENT_FORMULAS:
            # A change in a margin is in percentage points, not percent.
            points = (value * Decimal("100")).quantize(_TENTH, rounding=ROUND_HALF_UP)
            formatted = f"{'+' if points > 0 else ''}{points:.1f} pts"
        else:
            formatted = format_metric_value(row.metric, value)
            if row.comparison is not None and value > 0:
                formatted = f"+{formatted}"
            percent = change_percent(row)
            if percent is not None:
                formatted = f"{formatted} ({'+' if percent > 0 else ''}{percent:.1f}%)"
        return formatted + (DERIVED_MARK if is_derived(row) else "")
    if key == "metric":
        return format_field_name(str(value))
    if key in {"start_date", "end_date"}:
        return format_date(value)
    if key == "reason":
        return format_reason(value)
    if key == "market_cap":
        return format_usd(value)
    return str(value)


def overview_trends(rows: list[TableRow]) -> tuple[ChartSpec, ...]:
    """A small line per measure over the overview's last few quarters.

    Revenue and net margin are separate charts, each on its own scale, never
    one chart with two axes. A measure with fewer than two quarters is left out.
    """
    charts: list[ChartSpec] = []
    for metric in dict.fromkeys(row.metric for row in rows):
        points = sorted(
            (
                row
                for row in rows
                if row.metric == metric and row.end_date and row.value is not None
            ),
            key=lambda row: row.end_date or date.min,
        )
        if len(points) < 2:
            continue
        name = points[0].company_name
        charts.append(
            ChartSpec(
                kind="line",
                title="Trend",
                records=tuple(
                    {
                        "Period": row.end_date.isoformat() if row.end_date else "",
                        name: float(row.value or 0),
                    }
                    for row in points
                ),
                metric=metric,
                value_kind=chart_value_kind(metric),
                metric_label=format_field_name(metric),
                period_labels=tuple(format_date(row.end_date) for row in points if row.end_date),
                series=(name,),
                amounts=tuple({name: format_chart_amount(metric, row.value)} for row in points),
            )
        )
    return tuple(charts)


def overview_headline(rows: list[TableRow]) -> str | None:
    """ "NVIDIA's revenue was $96.22 B in the quarter ended Jul 26, 2026, with a 62.0% net margin."

    For a one-company, one-quarter overview ("How is Nvidia doing?"): the sentence
    the table's first row says, in the table's own formatted amounts.
    """
    levels = [row for row in rows if row.comparison is None and row.value is not None]
    if len({row.cik or row.company_name for row in levels}) != 1:
        return None
    by_metric = {row.metric: row for row in levels}
    revenue = by_metric.get("revenue")
    if revenue is None or len({row.end_date for row in levels}) != 1 or len(by_metric) < 2:
        return None
    name = short_name(revenue.company_name) or revenue.company_name
    owner = possessive(name)
    sentence = f"{owner} revenue was {_format_cell(revenue, 'value')}"
    if revenue.end_date is not None:
        sentence += f" in the quarter ended {format_date(revenue.end_date)}"
    margin = by_metric.get("net_margin")
    income = by_metric.get("net_income")
    if margin is not None:
        sentence += f", with a {_format_cell(margin, 'value')} net margin"
    elif income is not None and income.value is not None and income.value < 0:
        # "a net loss of $541.00 M" reads better than "net income of -$541.00 M".
        loss = income.model_copy(update={"value": -income.value})
        sentence += f", with a net loss of {_format_cell(loss, 'value')}"
    elif income is not None:
        sentence += f", with net income of {_format_cell(income, 'value')}"
    return sentence + "."


def growth_headline(rows: list[TableRow]) -> str | None:
    """ "Year over year, Microsoft's revenue grew 17.8% and Apple's grew 16.4%."

    Each company's latest year-over-year change of the one amount the table
    shows, fastest first; None when there is no such change to state.
    """
    metrics = {row.metric for row in rows if row.comparison == "year_over_year"}
    if len(metrics) != 1:
        return None
    latest: dict[str, TableRow] = {}
    for row in rows:
        if row.comparison != "year_over_year" or change_percent(row) is None:
            continue
        key = row.cik or row.company_name
        shown = latest.get(key)
        if shown is None or (row.end_date or date.min) > (shown.end_date or date.min):
            latest[key] = row
    if not latest:
        return None
    ordered = sorted(
        latest.values(), key=lambda row: change_percent(row) or Decimal(0), reverse=True
    )
    label = _in_sentence(format_field_name(next(iter(metrics))))
    parts: list[str] = []
    for index, row in enumerate(ordered):
        percent = change_percent(row) or Decimal(0)
        name = short_name(row.company_name) or row.company_name
        owner = possessive(name)
        subject = f"{owner} {label}" if index == 0 else owner
        mark = DERIVED_MARK if is_derived(row) else ""
        if percent == 0:
            parts.append(f"{subject} was unchanged{mark}")
            continue
        verb = "grew" if percent > 0 else "fell"
        parts.append(f"{subject} {verb} {abs(percent):.1f}%{mark}")
    if len(parts) == 1:
        ended = format_date(ordered[0].end_date) if ordered[0].end_date else ""
        return f"Year over year, {parts[0]} in the quarter ended {ended}."
    joined = ", ".join(parts[:-1]) + " and " + parts[-1]
    return f"Year over year, {joined}, each in its latest quarter."


def comparison_headline(rows: list[TableRow], intent: Intent) -> str | None:
    """ "Of these 10 companies, Apple reported the most research and development, …"

    For a ranking or a comparison of one amount: who leads and who trails, in the
    table's own formatted amounts; for one company over quarters, where it went.
    None for changes (``growth_headline`` says those) and for several metrics.
    """
    if any(row.comparison is not None for row in rows):
        return None
    levels = [row for row in rows if row.value is not None and row.end_date is not None]
    if len({row.metric for row in levels}) != 1:
        return None
    latest: dict[str, TableRow] = {}
    for row in levels:
        key = row.cik or row.company_name
        if key not in latest or (row.end_date or date.min) > (latest[key].end_date or date.min):
            latest[key] = row
    if len(latest) == 1:
        return _trend_headline(levels)
    ordered = sorted(latest.values(), key=lambda row: Decimal(str(row.value)), reverse=True)
    top, bottom = ordered[0], ordered[-1]
    if top.value == bottom.value:
        return None
    metric = top.metric
    label = _in_sentence(format_field_name(metric))

    def amount(row: TableRow) -> str:
        return _format_cell(row, "value")

    def name(row: TableRow) -> str:
        return short_name(row.company_name) or row.company_name

    if metric == "market_cap":
        second = ordered[1]
        return (
            f"{name(top)} is the largest by market cap, at {amount(top)}, "
            f"followed by {name(second)} at {amount(second)}."
        )
    ends = {row.end_date for row in latest.values()}
    period = (
        f", in the quarter ended {format_date(top.end_date)}"
        if len(ends) == 1 and top.end_date is not None
        else ", each in its latest quarter"
        if intent not in (Intent.RANK, Intent.RANK_AND_LOOKUP)
        else ""
    )
    if len(ordered) == 2 and intent not in (Intent.RANK, Intent.RANK_AND_LOOKUP):
        return (
            f"{_owner(top)} {label} was {amount(top)}, ahead of "
            f"{_owner(bottom)} {amount(bottom)}{period}."
        )
    ratio = metric in (*PERCENT_FORMULAS, *MULTIPLE_FORMULAS, *PER_SHARE_METRICS)
    most, least = ("highest", "lowest") if ratio else ("most", "least")
    companies = len({row.cik or row.company_name for row in rows})
    return (
        f"Of these {companies} companies, {name(top)} reported the {most} {label}, "
        f"{amount(top)}, and {name(bottom)} the {least}, {amount(bottom)}{period}."
    )


def _trend_headline(levels: list[TableRow]) -> str | None:
    """ "Microsoft's revenue rose from $77.67 B to $90.01 B † over 4 quarters to Jun 30, 2026."

    One company over several quarters: where its amount started and ended.
    """
    ordered = sorted(levels, key=lambda row: row.end_date or date.min)
    if len(ordered) < 3:
        return None
    first, last = ordered[0], ordered[-1]
    if first.value == last.value or last.end_date is None:
        return None
    verb = "rose" if Decimal(str(last.value)) > Decimal(str(first.value)) else "fell"
    label = _in_sentence(format_field_name(last.metric))
    return (
        f"{_owner(last)} {label} {verb} from {_format_cell(first, 'value')} to "
        f"{_format_cell(last, 'value')} over {len(ordered)} quarters to "
        f"{format_date(last.end_date)}."
    )


def change_percent(row: TableRow) -> Decimal | None:
    """A change row's change as a percent of the level it starts from, or None.

    Margins change in points, and a base at or below zero has no meaningful percent.
    """
    if row.comparison is None or row.value is None or row.metric in PERCENT_FORMULAS:
        return None
    if not row.components or row.components[0].value is None:
        return None
    base = Decimal(str(row.components[0].value))
    if base <= 0:
        return None
    return (Decimal(str(row.value)) / base * Decimal("100")).quantize(
        _TENTH, rounding=ROUND_HALF_UP
    )


def _format_banner(banner: str) -> str:
    if banner in _BANNER_COPY:
        return _BANNER_COPY[banner]
    if not banner.startswith(SNAPSHOT_BANNER_PREFIX):
        return banner
    parsed = try_parse_datetime(banner[len(SNAPSHOT_BANNER_PREFIX) :])
    if parsed is None:
        return banner
    return f"{SNAPSHOT_BANNER_PREFIX}{format_datetime_utc(parsed)}"


def _trace_identity(args: dict[str, Any]) -> str:
    parts: list[str] = []
    for key in ("company", "metric", "industry", "query", "topic"):
        value = args.get(key)
        if value is not None and value != "":
            parts.append(format_field_name(str(value)) if key == "metric" else str(value))
    issuers = args.get("issuers")
    if isinstance(issuers, list) and issuers:
        parts.append(", ".join(str(item) for item in issuers))
    return " · ".join(parts)


_SOURCE_LABELS = {
    "sec_xbrl": "SEC EDGAR",
}


def _truncate_url(url: str, max_len: int = 48) -> str:
    if len(url) <= max_len:
        return url
    parsed = urlparse(url)
    name = parsed.path.rstrip("/").rsplit("/", 1)[-1]
    if parsed.netloc and name:
        compact = f"{parsed.netloc}/…/{name}"
        if len(compact) < len(url):
            return compact
    keep = max(max_len - 1, 1)
    head = max(keep // 2, 1)
    tail = max(keep - head, 1)
    return f"{url[:head]}…{url[-tail:]}"


def _append_trace_field(fields: list[tuple[str, str]], key: str, value: Any) -> None:
    label = format_field_name(str(key))
    if key == "components" and isinstance(value, list):
        _append_component_fields(fields, value)
        return
    if key == "derivation" and isinstance(value, dict):
        _append_derivation_fields(fields, value)
        return
    if key == "hits" and isinstance(value, list):
        fields.append((label, _format_hit_traces(value)))
        return
    if key == "metric" and isinstance(value, str):
        fields.append((label, format_field_name(value)))
        return
    if key in _USER_TEXT_FIELDS and isinstance(value, str):
        # The analyst's own words: one plain line, so the window never renders
        # them as markdown ("**Verified by SEC:** [download](...)").
        text = " ".join(value.split())
        fields.append((label, "\\" + text if text.startswith("[") else text))
        return
    if key == "source_url" and value:
        url = str(value)
        fields.append((label, f"[{_truncate_url(url)}]({url})"))
        return
    if key == "source" and value:
        raw = str(value)
        fields.append((label, _SOURCE_LABELS.get(raw, raw)))
        return
    if key == "error" and isinstance(value, dict):
        fields.append((label, _public_trace_error(value)))
        return
    fields.append((label, _format_trace_value(value)))


# A provider's own wording ("SEC server error", a payload's shape) stays in the
# record; the window says only that the source failed.
_SOURCE_ERROR_CODES = frozenset({"provider_error", "data_integrity_error"})


def _public_trace_error(error: dict[str, Any]) -> str:
    if str(error.get("code") or "") in _SOURCE_ERROR_CODES:
        return _REASON_LABELS["source_unavailable"]
    return _friendly_message(str(error.get("message") or "")) or ""


_USER_TEXT_FIELDS = frozenset({"topic", "query", "message", "question"})


def _trace_fields(payload: dict[str, Any]) -> tuple[tuple[str, str], ...]:
    fields: list[tuple[str, str]] = []
    for key, value in payload.items():
        _append_trace_field(fields, str(key), value)
    return tuple(fields)


def _names_by_cik(rows: list[TableRow]) -> dict[str, str]:
    return {row.cik: row.company_name for row in rows if row.cik and row.company_name}


def _display_trace(trace: Any, *, names: dict[str, str] | None = None) -> DisplayTrace:
    args = dict(trace.args)
    company = args.get("company")
    if names and isinstance(company, str) and company in names:
        # Ranked lookups run by CIK; the header reads better with the name.
        args["company"] = names[company]
    issuers = args.get("issuers")
    if names and isinstance(issuers, list):
        args["issuers"] = [names.get(str(item), item) for item in issuers]
    identity = _trace_identity(args)
    period = _trace_period(trace)
    what = identity or "this request"
    template = _TOOL_HEADERS.get(str(trace.tool))
    if template:
        header = template.format(what=what)
    elif identity:
        header = f"{trace.tool} · {identity}"
    else:
        header = str(trace.tool)
    if period:
        header = f"{header} ({period})"
    return DisplayTrace(
        header=header,
        inputs=_trace_fields(trace.args),
        outputs=_trace_fields(trace.provenance),
    )


def _format_component_amount(value: Any) -> str:
    if value is None or value == "":
        return ""
    if isinstance(value, Decimal):
        return format_usd(value)
    try:
        return format_usd(Decimal(str(value)))
    except InvalidOperation:
        return str(value)


_COMPONENT_FIELD_ORDER = (
    "concept",
    "taxonomy",
    "accession_number",
    "form",
    "start_date",
    "end_date",
    "source",
    "source_url",
)


def _part_sign(method: str, index: int) -> str:
    """How a derivation part enters the amount (see ``Derivation``)."""
    if index == 0:
        return ""
    if method == "sum" or (method == "trailing_twelve_months" and index == 1):
        return "Plus "
    return "Minus "


def _append_derivation_fields(fields: list[tuple[str, str]], derivation: dict[str, Any]) -> None:
    fields.append(("Derived", str(derivation.get("label") or "Derived quarter")))
    parts = derivation.get("parts")
    if not isinstance(parts, list):
        return
    for index, part in enumerate(parts):
        if not isinstance(part, dict):
            continue
        period = _period_label(
            _as_iso_date(part.get("start_date")), _as_iso_date(part.get("end_date"))
        )
        sign = _part_sign(str(derivation.get("method") or ""), index)
        label = f"{sign}{part.get('form') or 'Filing'} {period}".strip()
        nested = part.get("derivation")
        if isinstance(nested, dict):
            # A derived part (a fiscal Q4 inside a gross profit) lists its own filings.
            fields.append((f"{label} †", _format_component_amount(part.get("value"))))
            _append_derivation_fields(fields, nested)
            continue
        fields.append((label, _format_component_amount(part.get("value"))))
        url = part.get("source_url")
        if url:
            _append_trace_field(fields, "source_url", url)


def _append_component_fields(fields: list[tuple[str, str]], components: list[Any]) -> None:
    for index, item in enumerate(components):
        if not isinstance(item, dict):
            fields.append(("", _format_trace_value(item)))
            continue
        if index:
            fields.append(("", ""))
        metric = format_field_name(str(item.get("metric") or "Component"))
        fields.append((metric, _format_component_amount(item.get("value"))))
        for key in _COMPONENT_FIELD_ORDER:
            raw = item.get(key)
            if raw:
                _append_trace_field(fields, key, raw)


_SNIPPET_DISPLAY_LIMIT = 280
_HIT_KNOWN_KEYS = frozenset({"title", "url", "snippet", "score", "published"})
_HIT_HIDDEN_KEYS = frozenset({"raw_content", "content", "favicon", "images"})
_MARKDOWN_ESCAPE = str.maketrans(
    {
        "\\": "\\\\",
        "`": "\\`",
        "*": "\\*",
        "_": "\\_",
        "{": "\\{",
        "}": "\\}",
        "[": "\\[",
        "]": "\\]",
        "(": "\\(",
        ")": "\\)",
        "#": "\\#",
        "!": "\\!",
        "|": "\\|",
        "$": "\\$",
    }
)


def _escape_markdown(text: str) -> str:
    return text.translate(_MARKDOWN_ESCAPE)


def _format_hit_snippet(value: Any) -> str:
    text = " ".join(str(value).split())
    if len(text) > _SNIPPET_DISPLAY_LIMIT:
        text = text[: _SNIPPET_DISPLAY_LIMIT - 1].rstrip() + "…"
    return _escape_markdown(text)


def _format_hit_score(value: Any) -> str:
    if isinstance(value, bool):
        return _escape_markdown(str(value))
    if isinstance(value, (int, float)):
        return f"{float(value):.2f}"
    try:
        return f"{float(str(value).strip()):.2f}"
    except ValueError:
        return _escape_markdown(str(value))


def _format_hit_traces(hits: list[Any]) -> str:
    blocks: list[str] = []
    for index, item in enumerate(hits, start=1):
        if not isinstance(item, dict):
            blocks.append(f"- **[{index}]** {_escape_markdown(_format_trace_value(item))}")
            continue
        title = _escape_markdown(str(item.get("title") or f"Hit {index}"))
        url = str(item.get("url") or "").strip()
        heading = f"- **[{index}]** [{title}]({url})" if url else f"- **[{index}]** {title}"
        lines = [heading]
        score = item.get("score")
        if score is not None and score != "":
            lines.append(f"  - Score: `{_format_hit_score(score)}`")
        published = item.get("published")
        if published:
            lines.append(f"  - Published: {_format_trace_value(published)}")
        for key, value in item.items():
            if key in _HIT_KNOWN_KEYS or key in _HIT_HIDDEN_KEYS:
                continue
            if value is None or value == "" or isinstance(value, (dict, list)):
                continue
            lines.append(
                f"  - {format_field_name(str(key))}: {_escape_markdown(_format_trace_value(value))}"
            )
        snippet = item.get("snippet")
        if snippet:
            lines.append(f"  - Snippet: {_format_hit_snippet(snippet)}")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def _format_trace_value(value: Any) -> str:
    if isinstance(value, datetime):
        return format_datetime_utc(value)
    if isinstance(value, date):
        return format_date(value)
    if isinstance(value, (int, bool)):
        return str(value)
    if isinstance(value, Decimal):
        return format_usd(value)
    if isinstance(value, str):
        parsed = try_parse_datetime(value)
        if parsed is not None and ("T" in value or " " in value.strip()):
            return format_datetime_utc(parsed)
        try:
            as_date = date.fromisoformat(value)
        except ValueError:
            return value
        return format_date(as_date)
    if isinstance(value, dict):
        lines: list[str] = []
        for key, item in value.items():
            label = format_field_name(str(key))
            formatted = _format_trace_value(item)
            if isinstance(item, (dict, list)):
                lines.append(f"{label}:")
                lines.extend(f"  {line}" for line in formatted.splitlines())
            else:
                lines.append(f"{label}: {formatted}")
        return "\n".join(lines)
    if isinstance(value, list):
        if value and all(not isinstance(item, (dict, list)) for item in value):
            return ", ".join(_format_trace_value(item) for item in value)
        lines = []
        for item in value:
            item_lines = _format_trace_value(item).splitlines()
            if not item_lines:
                lines.append("- ")
                continue
            lines.append(f"- {item_lines[0]}")
            lines.extend(f"  {line}" for line in item_lines[1:])
        return "\n".join(lines)
    return str(value)


def _display_citation(index: int, hit: Any) -> DisplayCitation:
    published = hit.published
    if published:
        published = _format_trace_value(published)
    return DisplayCitation(index=index, title=hit.title, url=hit.url, published=published)


def _join_words(words: list[str]) -> str:
    """Join words in prose: "A", "A and B", "A, B and C"."""
    if len(words) <= 1:
        return "".join(words)
    return f"{', '.join(words[:-1])} and {words[-1]}"
