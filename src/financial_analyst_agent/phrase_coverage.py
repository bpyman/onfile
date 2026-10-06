"""How many everyday phrasings of a metric, a window, a change or a follow-up are read right.

The planner comparison asks a few dozen written questions; this asks the same
kind of question in every common phrasing, so a gap in the shared reading of
words ("year on year", "NII", "18 months") shows up before a held-out set finds
it. Each case is a conversation on the recorded runtime with the rules planner,
the keyless planner, and is judged by the README's "How a question is read":
what a reasonable analyst means, not what the code's word lists hold.

``KNOWN_GAPS`` lists the cases that fail today. The test keeps both lists true:
a case that newly fails is a regression, and a gap that starts passing must be
taken off the list.

Each phrasing is asked alone first. Then the combinations: every pair of a
company form, a metric phrasing, a window and a change word is asked together
at least once (all pairs, not every combination), and each kind of first
question is followed by each kind of follow-up, since a reading can be right
alone and wrong beside another.

The live app plans with the cascade (ADR 0012), which sends a turn the rules
planner is unsure of to the LLM planner. Here a stand-in that declines takes the
LLM planner's place, so every answer is still the rules planner's, and the
report lists the phrasings the live app would send on: each can be misread live
though it is read right here. ``SENT_TO_MODEL`` lists them, kept true the same way.

    uv run python -m financial_analyst_agent.phrase_coverage   # writes the report
"""

from __future__ import annotations

import argparse
import itertools
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from financial_analyst_agent.contracts import RendererKind
from financial_analyst_agent.conversation import ConversationTurn, run_conversation_turn
from financial_analyst_agent.domain.errors import PlannerError
from financial_analyst_agent.planner_cascade import CascadeCompleter
from financial_analyst_agent.planner_evaluation import Observation, observe
from financial_analyst_agent.ranking import SnapshotRanking
from financial_analyst_agent.request_wording import OVERVIEW_METRICS
from financial_analyst_agent.runtime import recorded_runtime
from financial_analyst_agent.thread_store import EphemeralThreadStore

REPORT_PATH = Path("docs/evaluation/phrase-coverage.md")

Check = Callable[[Observation, ConversationTurn], bool]


@dataclass(frozen=True)
class PhraseCase:
    case_id: str
    group: str
    turns: tuple[str, ...]
    expected: str
    check: Check


def _answers_metric(slug: str) -> Check:
    def check(seen: Observation, _turn: ConversationTurn) -> bool:
        # A fact the recording lacks still planned the right metric.
        return seen.outcome in ("answer", "no_data") and seen.metrics == frozenset({slug})

    return check


def _asks(seen: Observation, _turn: ConversationTurn) -> bool:
    return seen.outcome == "clarify"


def _explains(seen: Observation, _turn: ConversationTurn) -> bool:
    # The recorded demo replays one written answer; any other explanation is
    # refused by the essay completer after it was read right, so the intent decides.
    return seen.intent == "explain"


def _asks_which_company(seen: Observation, turn: ConversationTurn) -> bool:
    return seen.outcome == "refuse" and (turn.result.message or "").startswith(
        "I couldn't tell which company you mean"
    )


def _refuses_naming(measure: str) -> Check:
    def check(seen: Observation, turn: ConversationTurn) -> bool:
        return seen.outcome == "refuse" and f"look up {measure}" in (turn.result.message or "")

    return check


def _window(kind: str, count: int | None = None) -> Check:
    def check(seen: Observation, _turn: ConversationTurn) -> bool:
        seen_kind, seen_count = seen.periods
        return (
            seen.outcome in ("answer", "no_data")
            and seen_kind == kind
            and (count is None or seen_count == count)
        )

    return check


def _year_over_year(seen: Observation, turn: ConversationTurn) -> bool:
    return seen.outcome in ("answer", "no_data") and any(
        row.comparison == "year_over_year" for row in turn.result.table_rows
    )


def _sequential(seen: Observation, turn: ConversationTurn) -> bool:
    return seen.outcome in ("answer", "no_data") and any(
        row.comparison == "sequential" for row in turn.result.table_rows
    )


def _each_quarter_changed(turn: ConversationTurn, comparison: str) -> bool:
    """Every quarter shown has its change: no row stands only as another's base."""
    rows = turn.result.table_rows
    levels = {row.end_date for row in rows if row.comparison is None and row.value is not None}
    changed = {row.end_date for row in rows if row.comparison == comparison}
    return bool(levels) and levels <= changed


def _reads(
    tickers: frozenset[str],
    metrics: frozenset[str],
    period: tuple[str, int | None] | None,
    comparison: str | None,
) -> Check:
    """Companies, metrics, the period (``None``: not checked) and change rows, all as read."""

    def check(seen: Observation, turn: ConversationTurn) -> bool:
        return (
            seen.outcome in ("answer", "no_data")
            and seen.tickers == tickers
            and seen.metrics == metrics
            and (
                period is None
                or (
                    seen.periods[0] == period[0]
                    and (period[1] is None or seen.periods[1] == period[1])
                )
            )
            and (
                comparison is None
                or any(row.comparison == comparison for row in turn.result.table_rows)
            )
            # A named period with a change shows its own quarters, each with the change.
            and (
                comparison is None
                or period is None
                or period[0] != "named"
                or _each_quarter_changed(turn, comparison)
            )
        )

    return check


def _companies(*tickers: str, metrics: tuple[str, ...] = ("revenue",), count: int = 4) -> Check:
    def check(seen: Observation, _turn: ConversationTurn) -> bool:
        return (
            seen.outcome in ("answer", "no_data")
            and seen.tickers == frozenset(tickers)
            and seen.metrics == frozenset(metrics)
            and seen.periods == ("last_n_quarters", count)
        )

    return check


# Each catalog metric in the words analysts use for it. Bank figures are asked of
# JPMorgan, the rest of Apple.
METRIC_PHRASES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("revenue", ("revenue", "sales", "net sales", "total revenue", "top line", "turnover")),
    ("cost_of_revenue", ("cost of revenue", "cost of sales", "cost of goods sold", "COGS")),
    ("gross_profit", ("gross profit",)),
    ("operating_expenses", ("operating expenses", "opex", "total operating expenses")),
    (
        "operating_income",
        ("operating income", "operating profit", "EBIT", "income from operations"),
    ),
    ("net_income", ("net income", "net profit", "bottom line", "net earnings", "earnings")),
    (
        "research_and_development",
        ("R&D", "research and development", "R&D spending", "research spend"),
    ),
    (
        "selling_general_and_administrative",
        ("SG&A", "selling, general and administrative expenses"),
    ),
    ("interest_expense", ("interest expense",)),
    ("income_tax_expense", ("income tax expense", "tax expense", "income taxes")),
    (
        "pretax_income",
        ("pretax income", "pre-tax income", "income before taxes", "earnings before tax"),
    ),
    ("eps_diluted", ("EPS", "diluted EPS", "earnings per share", "diluted earnings per share")),
    ("eps_basic", ("basic EPS", "basic earnings per share")),
    (
        "operating_cash_flow",
        ("operating cash flow", "cash from operations", "cash flow from operations"),
    ),
    ("capital_expenditure", ("capex", "capital expenditures", "capital spending")),
    ("depreciation_amortization", ("depreciation and amortization", "D&A")),
    ("dividends_paid", ("dividends paid",)),
    ("dividends_per_share", ("dividends per share", "dividend per share", "DPS")),
    ("cash", ("cash and equivalents", "cash on hand", "cash and cash equivalents")),
    (
        "shareholders_equity",
        ("shareholders' equity", "stockholders' equity", "book value"),
    ),
    (
        "net_income_ttm",
        (
            "trailing twelve month net income",
            "TTM net income",
            "LTM net income",
            "last twelve months net income",
        ),
    ),
    ("net_interest_income", ("net interest income", "NII")),
    ("total_equity", ("total equity", "equity including noncontrolling interests")),
    ("noninterest_income", ("noninterest income", "non-interest income")),
    ("gross_margin", ("gross margin", "gross profit margin")),
    ("operating_margin", ("operating margin", "operating profit margin", "EBIT margin")),
    ("net_margin", ("net margin", "net profit margin", "profit margin")),
    ("rd_to_sales", ("R&D to sales", "R&D as a percentage of revenue", "R&D intensity")),
    ("sga_ratio", ("SG&A ratio", "SG&A as a percentage of sales")),
    ("effective_tax_rate", ("effective tax rate", "tax rate")),
    (
        "interest_coverage",
        ("interest coverage", "interest coverage ratio", "times interest earned"),
    ),
    ("free_cash_flow", ("free cash flow", "FCF")),
    ("ebitda", ("EBITDA",)),
    ("return_on_equity", ("return on equity", "ROE")),
    ("pe_ratio", ("P/E", "P/E ratio", "PE ratio", "price to earnings", "price-to-earnings ratio")),
    ("market_cap", ("market cap", "market capitalization", "market value")),
    ("price", ("share price", "stock price")),
)
_BANK_METRICS = frozenset({"net_interest_income", "noninterest_income"})
# Words that name more than one catalog metric: the answer asks which (ADR 0004).
AMBIGUOUS_WORDS = ("profit", "income", "margin", "cash flow", "interest", "expenses", "dividends")

WINDOW_PHRASES: tuple[tuple[str, str, int | None], ...] = (
    ("over the last 4 quarters", "last_n_quarters", 4),
    ("for the last four quarters", "last_n_quarters", 4),
    ("last 6 quarters", "last_n_quarters", 6),
    ("in the last 5 quarters", "last_n_quarters", 5),
    ("over the past 8 quarters", "last_n_quarters", 8),
    ("over the past two years", "last_n_quarters", 8),
    ("over the last 3 years", "last_n_quarters", 12),
    ("over the past year", "last_n_quarters", 4),
    ("over the past 12 months", "last_n_quarters", 4),
    ("over the last 18 months", "last_n_quarters", 6),
    ("over the last six months", "last_n_quarters", 2),
    ("for the last few quarters", "last_n_quarters", 4),
    ("over several quarters", "last_n_quarters", 4),
    ("over the last couple of quarters", "last_n_quarters", 2),
    ("for the last two quarters", "last_n_quarters", 2),
    ("for the trailing four quarters", "last_n_quarters", 4),
    ("over the past decade", "last_n_quarters", 40),
    ("since 2024", "last_n_quarters", None),
    ("since the start of 2024", "last_n_quarters", None),
    ("since the beginning of 2024", "last_n_quarters", None),
    ("for the most recent quarter", "latest_quarter", None),
    ("for the latest quarter", "latest_quarter", None),
    ("in Q2 2025", "named", None),
    ("in fiscal 2025", "named", None),
    ("for FY2024", "named", None),
    ("in calendar Q1 2026", "named", None),
)
# Whole questions whose window words only read right beside their metric: after
# net income, "last twelve months" is a span of quarters; before it, LTM.
WINDOW_QUESTIONS: tuple[tuple[str, str, int | None], ...] = (
    ("pfizer net income over the last twelve months", "last_n_quarters", 4),
)

YEAR_OVER_YEAR_QUESTIONS = (
    "Apple revenue year over year",
    "Apple revenue year-over-year",
    "Apple revenue YoY",
    "Apple revenue y/y",
    "Apple revenue year on year",
    "Apple revenue versus a year ago",
    "Apple revenue compared with the same quarter last year",
    "Apple revenue growth",
    "Apple revenue growth rate",
    "How fast is Apple's revenue growing?",
    "Is Apple's revenue up from a year earlier?",
)
# A named fiscal year is four quarters, each with its change from its own comparative.
NAMED_CHANGE_QUESTIONS = ("Apple R&D for fiscal 2025 year over year",)
SEQUENTIAL_QUESTIONS = (
    "Apple revenue quarter over quarter",
    "Apple revenue QoQ",
    "Apple revenue sequentially",
    "Apple revenue versus the previous quarter",
)
NO_BASE_QUESTIONS = (
    "Why did Apple revenue drop?",
    "How much did Apple's revenue change?",
    "What drove the change in Apple's revenue?",
    "Why did Apple's revenue go up?",
    "What caused Apple's revenue to fall?",
    "What caused Pfizer's earnings to fall?",
    "What's behind the drop in Apple's revenue?",
    "What led to the decline in Apple's revenue?",
)
# An idiom that contains a company's everyday-word name ("apples to apples",
# "building blocks") names no company: only the real companies are read.
IDIOM_QUESTIONS: tuple[tuple[str, tuple[str, ...], str], ...] = (
    ("Apples to apples: Merck vs Pfizer net margin", ("MRK", "PFE"), "net_margin"),
    (
        "comparing apples to apples, how do Merck and Pfizer stack up on net income?",
        ("MRK", "PFE"),
        "net_income",
    ),
    ("an apples-to-apples comparison of Merck and Pfizer net margin", ("MRK", "PFE"), "net_margin"),
    ("Merck and Pfizer net margin, apples with apples", ("MRK", "PFE"), "net_margin"),
    ("Merck vs Pfizer net margin, apples and oranges", ("MRK", "PFE"), "net_margin"),
    ("the building blocks of Microsoft and Oracle revenue", ("MSFT", "ORCL"), "revenue"),
)
# Asking how a company is doing, in any of its words, is the overview: revenue,
# net income and three margins. "Performance" and "rundown" name no metric.
OVERVIEW_QUESTIONS: tuple[tuple[str, tuple[str, ...], tuple[str, int | None]], ...] = (
    ("How is Apple doing?", ("AAPL",), ("latest_quarter", None)),
    ("Give me the rundown on how Wells Fargo is performing", ("WFC",), ("latest_quarter", None)),
    ("How is Wells Fargo performing?", ("WFC",), ("latest_quarter", None)),
    ("How has Wells Fargo been performing?", ("WFC",), ("latest_quarter", None)),
    ("the rundown on Apple", ("AAPL",), ("latest_quarter", None)),
    ("Give me the rundown on Apple and Microsoft", ("AAPL", "MSFT"), ("latest_quarter", None)),
    ("a quick read on Apple", ("AAPL",), ("latest_quarter", None)),
    ("a quick look at Apple", ("AAPL",), ("latest_quarter", None)),
    ("Wells Fargo's performance", ("WFC",), ("latest_quarter", None)),
    ("Apple's performance over the last 4 quarters", ("AAPL",), ("last_n_quarters", 4)),
)
# A measure the catalog lacks is refused by name, even when a word inside it
# would be ambiguous alone ("equity") or would name a metric ("turnover").
UNKNOWN_MEASURE_QUESTIONS: tuple[tuple[str, str], ...] = (
    ("What's Apple's debt-to-equity ratio?", "debt-to-equity"),
    ("Apple debt to equity", "debt-to-equity"),
    ("Apple D/E", "debt-to-equity"),
    ("What is Apple's return on assets?", "return on assets"),
    ("Apple ROA", "return on assets"),
    ("Apple's equity multiplier", "equity multiplier"),
    ("Apple dividend yield", "dividend yield"),
    ("Apple's net debt", "net debt"),
    ("Apple interest-bearing debt", "debt"),
    ("Apple total debt", "debt"),
    ("JPMorgan net interest margin", "net interest margin"),
    ("Apple asset turnover", "asset turnover"),
    ("Apple price to book", "price to book"),
    ("Apple's stock performance", "stock performance"),
    ("Oracle remaining performance obligations", "remaining performance obligations"),
    ("Oracle RPO", "remaining performance obligations"),
    ("Apple's price-to-sales ratio", "price to sales"),
    ("Apple EV/EBITDA", "EV/EBITDA"),
    ("Apple's customer acquisition cost", "customer acquisition cost"),
)

# A general question that names a metric asks how something works, not for a
# figure: an explanation (intent explain), as "How might AI change banking?" is.
EXPLANATION_QUESTIONS = (
    "Explain how a share buyback affects EPS",
    "How does a buyback affect EPS?",
    "How do buybacks impact diluted EPS?",
    "What is free cash flow and why does it matter?",
    "How is EPS calculated?",
    "Why does operating margin matter?",
    "What does diluted EPS mean?",
    "How might AI change banking?",
)
# A figure with no company asks which company: the absence of a company alone
# does not make a question general.
NO_COMPANY_QUESTIONS = (
    "What's the EPS?",
    "What is EPS?",
    "What's the revenue?",
    "What was the revenue last quarter?",
)

_FIRST = "Apple revenue over the last 4 quarters"
_BOTH = "Compare Apple and Microsoft revenue over the last 4 quarters"
_FIRST_NAMES = {_FIRST: "Apple", _BOTH: "Apple and Microsoft"}
FOLLOW_UPS: tuple[tuple[str, str, Check, str], ...] = (
    (_FIRST, "add Microsoft", _companies("AAPL", "MSFT"), "Apple and Microsoft"),
    (_FIRST, "also Microsoft", _companies("AAPL", "MSFT"), "Apple and Microsoft"),
    (_FIRST, "Microsoft too", _companies("AAPL", "MSFT"), "Apple and Microsoft"),
    (_FIRST, "and Microsoft", _companies("AAPL", "MSFT"), "Apple and Microsoft"),
    (_FIRST, "include Microsoft", _companies("AAPL", "MSFT"), "Apple and Microsoft"),
    (_FIRST, "plus Microsoft", _companies("AAPL", "MSFT"), "Apple and Microsoft"),
    (_FIRST, "what about Microsoft?", _companies("MSFT"), "Microsoft alone"),
    (_FIRST, "how about Microsoft?", _companies("MSFT"), "Microsoft alone"),
    (_FIRST, "same for Microsoft", _companies("MSFT"), "Microsoft alone"),
    (_FIRST, "do Microsoft instead", _companies("MSFT"), "Microsoft alone"),
    (_BOTH, "drop Microsoft", _companies("AAPL"), "Apple alone"),
    (_BOTH, "remove Microsoft", _companies("AAPL"), "Apple alone"),
    (_BOTH, "without Microsoft", _companies("AAPL"), "Apple alone"),
    (_BOTH, "take out Microsoft", _companies("AAPL"), "Apple alone"),
    (_BOTH, "swap Microsoft for Oracle", _companies("AAPL", "ORCL"), "Apple and Oracle"),
    (_FIRST, "make it the last 8 quarters", _companies("AAPL", count=8), "8 quarters"),
    (_FIRST, "over the past two years instead", _companies("AAPL", count=8), "8 quarters"),
    (
        _FIRST,
        "add net income",
        _companies("AAPL", metrics=("revenue", "net_income")),
        "revenue and net income",
    ),
    (
        _FIRST,
        "and net income too",
        _companies("AAPL", metrics=("revenue", "net_income")),
        "revenue and net income",
    ),
)


# The combinations. Each dimension's values are read right alone (above); here
# every pair of values from two dimensions is asked together at least once.
COMBINED_COMPANIES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Apple", ("AAPL",)),
    ("apple", ("AAPL",)),
    ("AAPL", ("AAPL",)),
    ("$AAPL", ("AAPL",)),
    ("Apple and Microsoft", ("AAPL", "MSFT")),
    ("AAPL vs MSFT", ("AAPL", "MSFT")),
    ("Nvidia, AMD and Intel", ("NVDA", "AMD", "INTC")),
)
COMBINED_METRICS: tuple[tuple[str, str], ...] = (
    ("sales", "revenue"),
    ("top line", "revenue"),
    ("earnings", "net_income"),
    ("bottom line", "net_income"),
    ("EPS", "eps_diluted"),
    ("gross margin", "gross_margin"),
    ("operating profit margin", "operating_margin"),
    ("profit margin", "net_margin"),
    ("R&D", "research_and_development"),
    ("income before taxes", "pretax_income"),
    ("free cash flow", "free_cash_flow"),
    ("cash from operations", "operating_cash_flow"),
    ("D&A", "depreciation_amortization"),
    ("SG&A", "selling_general_and_administrative"),
)
COMBINED_WINDOWS: tuple[tuple[str, tuple[str, int | None] | None], ...] = (
    ("", None),
    ("over the last 4 quarters", ("last_n_quarters", 4)),
    ("over the past two years", ("last_n_quarters", 8)),
    ("for the last 18 months", ("last_n_quarters", 6)),
    ("for the last couple of quarters", ("last_n_quarters", 2)),
    ("in Q2 2025", ("named", None)),
    ("for fiscal 2025", ("named", None)),
)
# A change word, the window it shows when none is named, and the rows it adds.
COMBINED_CHANGES: tuple[tuple[str, tuple[str, int | None], str | None], ...] = (
    ("", ("latest_quarter", None), None),
    ("growth", ("last_n_quarters", 5), "year_over_year"),
    ("year over year", ("last_n_quarters", 8), "year_over_year"),
    ("quarter over quarter", ("last_n_quarters", 5), "sequential"),
)


def _all_pairs(sizes: Sequence[int]) -> list[tuple[int, ...]]:
    """Rows of value indices covering every pair of values of every two dimensions."""
    pairs = list(itertools.combinations(range(len(sizes)), 2))
    uncovered = {(i, x, j, y) for i, j in pairs for x in range(sizes[i]) for y in range(sizes[j])}
    candidates = list(itertools.product(*(range(size) for size in sizes)))
    rows: list[tuple[int, ...]] = []
    while uncovered:
        best = max(
            candidates, key=lambda row: sum((i, row[i], j, row[j]) in uncovered for i, j in pairs)
        )
        rows.append(best)
        uncovered -= {(i, best[i], j, best[j]) for i, j in pairs}
    return rows


def _combined_cases() -> list[PhraseCase]:
    found = []
    sizes = [len(COMBINED_COMPANIES), len(COMBINED_METRICS), len(COMBINED_WINDOWS)]
    for c, m, w, ch in _all_pairs([*sizes, len(COMBINED_CHANGES)]):
        company, tickers = COMBINED_COMPANIES[c]
        phrase, metric = COMBINED_METRICS[m]
        window_words, window = COMBINED_WINDOWS[w]
        change, default_window, comparison = COMBINED_CHANGES[ch]
        words = [company, phrase, "growth" if change == "growth" else "", window_words]
        words.append(change if change not in ("", "growth") else "")
        question = " ".join(word for word in words if word)
        period = window or default_window
        found.append(
            PhraseCase(
                f"combined:{question}",
                "Combinations",
                (question,),
                _expected(tickers, (metric,), period, comparison),
                _reads(frozenset(tickers), frozenset({metric}), period, comparison),
            )
        )
    return found


# A first question of each kind, then each kind of follow-up.
_FIRST_QUESTIONS: tuple[tuple[str, str, tuple[str, int | None], str | None], ...] = (
    ("Apple revenue over the last 6 quarters", "revenue", ("last_n_quarters", 6), None),
    ("Apple revenue for fiscal 2025", "revenue", ("named", None), None),
    ("Apple revenue", "revenue", ("latest_quarter", None), None),
    ("Apple revenue growth", "revenue", ("last_n_quarters", 5), "year_over_year"),
    ("Apple gross margin year over year", "gross_margin", ("last_n_quarters", 8), "year_over_year"),
)
_FOLLOW_KINDS: tuple[tuple[str, str], ...] = (
    ("add Microsoft", "add"),
    ("what about Microsoft?", "swap"),
    ("same for Microsoft", "swap"),
    ("show that year over year", "year_over_year"),
    ("add net income", "metric"),
    ("and net income too", "metric"),
    ("make it the last 8 quarters", "window"),
)


def _combined_follow_up_cases() -> list[PhraseCase]:
    found = []
    for (first, metric, period, comparison), (follow, kind) in itertools.product(
        _FIRST_QUESTIONS, _FOLLOW_KINDS
    ):
        tickers = {"add": ("AAPL", "MSFT"), "swap": ("MSFT",)}.get(kind, ("AAPL",))
        metrics = (metric, "net_income") if kind == "metric" else (metric,)
        shown: tuple[str, int | None] | None = (
            ("last_n_quarters", 8) if kind == "window" else period
        )
        if kind == "year_over_year":
            comparison = "year_over_year"
            if period[0] == "latest_quarter":
                # The README keeps the quarters on screen; one quarter it leaves open.
                shown = None
        found.append(
            PhraseCase(
                f"combined_follow_up:{first} | {follow}",
                "Follow-up combinations",
                (first, follow),
                _expected(tickers, metrics, shown, comparison),
                _reads(frozenset(tickers), frozenset(metrics), shown, comparison),
            )
        )
    return found


def _expected(
    tickers: Sequence[str],
    metrics: Sequence[str],
    period: tuple[str, int | None] | None,
    comparison: str | None,
) -> str:
    parts = [", ".join(tickers), ", ".join(f"`{metric}`" for metric in metrics)]
    if period is not None:
        parts.append(period[0] if period[1] is None else f"{period[0]} {period[1]}")
    if comparison is not None:
        parts.append(f"{comparison} rows")
    return "; ".join(parts)


def _metric_cases() -> list[PhraseCase]:
    cases = []
    for slug, phrases in METRIC_PHRASES:
        company = "JPMorgan" if slug in _BANK_METRICS else "Apple"
        for phrase in phrases:
            for form, question in (
                ("question", f"What was {company}'s {phrase}?"),
                ("terse", f"{company.lower()} {phrase}"),
            ):
                cases.append(
                    PhraseCase(
                        f"metric:{phrase}:{form}",
                        "Metrics",
                        (question,),
                        f"`{slug}`",
                        _answers_metric(slug),
                    )
                )
    for word in AMBIGUOUS_WORDS:
        cases.append(
            PhraseCase(
                f"ambiguous:{word}",
                "Ambiguous metric words",
                (f"What was Apple's {word}?",),
                "asks which",
                _asks,
            )
        )
    return cases


def cases() -> list[PhraseCase]:
    """Every phrasing case, in report order."""
    found = _metric_cases()
    for phrase, kind, count in WINDOW_PHRASES:
        expected = kind if count is None else f"{kind} {count}"
        found.append(
            PhraseCase(
                f"window:{phrase}",
                "Windows",
                (f"Apple revenue {phrase}",),
                expected,
                _window(kind, count),
            )
        )
    for question, kind, count in WINDOW_QUESTIONS:
        expected = kind if count is None else f"{kind} {count}"
        found.append(
            PhraseCase(f"window:{question}", "Windows", (question,), expected, _window(kind, count))
        )
    for question in YEAR_OVER_YEAR_QUESTIONS:
        found.append(
            PhraseCase(
                f"yoy:{question}",
                "Year over year",
                (question,),
                "year-over-year rows",
                _year_over_year,
            )
        )
    for question in SEQUENTIAL_QUESTIONS:
        found.append(
            PhraseCase(
                f"qoq:{question}",
                "Quarter over quarter",
                (question,),
                "sequential rows",
                _sequential,
            )
        )
    for question in NAMED_CHANGE_QUESTIONS:
        found.append(
            PhraseCase(
                f"named_change:{question}",
                "A named period with a change",
                (question,),
                "each quarter shown with its year-over-year change",
                lambda seen, turn: seen.outcome in ("answer", "no_data")
                and _each_quarter_changed(turn, "year_over_year"),
            )
        )
    for question in NO_BASE_QUESTIONS:
        found.append(
            PhraseCase(f"no_base:{question}", "Changes with no base", (question,), "asks", _asks)
        )
    for question, tickers, metric in IDIOM_QUESTIONS:
        period = ("latest_quarter", None)
        found.append(
            PhraseCase(
                f"idiom:{question}",
                "Idioms beside a company",
                (question,),
                _expected(tickers, (metric,), period, None),
                _reads(frozenset(tickers), frozenset({metric}), period, None),
            )
        )
    for question, tickers, window in OVERVIEW_QUESTIONS:
        found.append(
            PhraseCase(
                f"overview:{question}",
                "Overviews",
                (question,),
                _expected(tickers, OVERVIEW_METRICS, window, None),
                _reads(frozenset(tickers), frozenset(OVERVIEW_METRICS), window, None),
            )
        )
    for question, measure in UNKNOWN_MEASURE_QUESTIONS:
        found.append(
            PhraseCase(
                f"unknown:{question}",
                "Unknown measures",
                (question,),
                f"refuses, naming {measure}",
                _refuses_naming(measure),
            )
        )
    for question in EXPLANATION_QUESTIONS:
        found.append(
            PhraseCase(
                f"general:{question}",
                "General questions",
                (question,),
                "an explanation (intent explain)",
                _explains,
            )
        )
    for question in NO_COMPANY_QUESTIONS:
        found.append(
            PhraseCase(
                f"no_company:{question}",
                "General questions",
                (question,),
                "asks which company",
                _asks_which_company,
            )
        )
    for first, follow, check, expected in FOLLOW_UPS:
        found.append(
            PhraseCase(
                f"follow_up:{_FIRST_NAMES[first]} | {follow}",
                "Follow-ups",
                (first, follow),
                expected,
                check,
            )
        )
    return [*found, *_combined_cases(), *_combined_follow_up_cases()]


# The cases that fail today, each a gap in the shared reading of words. Take a case
# off when it is fixed; the test fails until the list matches.
KNOWN_GAPS: frozenset[str] = frozenset()


# The phrasings the cascade sends to the LLM planner. The ambiguous words name no
# catalog metric, so the rules planner is unsure; the shared guard asks which
# metric was meant whatever the LLM planner proposes (ADR 0004), so the call
# costs a second but cannot misread them. A figure with no company ("What's the EPS?") leaves the
# rules planner unsure too; the LLM planner is told to name companies as the
# user wrote them, and the user wrote none, so its proposal asks which company
# the same way. Any other phrasing sent on is a rules-planner reading the live
# app would not use: make the rules planner sure of it, or add it here with the
# reason.
SENT_TO_MODEL: frozenset[str] = (
    frozenset(f"ambiguous:{word}" for word in AMBIGUOUS_WORDS)
    | frozenset(f"no_company:{question}" for question in NO_COMPANY_QUESTIONS)
)


# ``unsure_reason``'s codes, in words.
_UNSURE = {
    "notes": "it corrected a name or left part unanswered",
    "metric": "no catalog metric",
    "company": "no company",
    "industry": "an industry the snapshot lacks",
    "edit": "an edit it cannot place",
}


class _NoModel:
    """The LLM planner's place in the cascade: declining keeps the rules plan."""

    def complete(self, query: str, current_spec: Any = None) -> Any:
        raise PlannerError("phrase coverage calls no model")


@dataclass(frozen=True)
class Outcome:
    case: PhraseCase
    passed: bool
    seen: str
    # Why the cascade would send it to the LLM planner, or None.
    sent_to_model: str | None = None


def _describe(seen: Observation, turn: ConversationTurn) -> str:
    comparisons = sorted({str(row.comparison) for row in turn.result.table_rows if row.comparison})
    parts = [seen.outcome]
    if seen.metrics:
        parts.append("metrics " + ", ".join(sorted(seen.metrics)))
    if seen.tickers:
        parts.append("companies " + ", ".join(sorted(seen.tickers)))
    kind, count = seen.periods
    parts.append(kind if count is None else f"{kind} {count}")
    if comparisons:
        parts.append("changes " + ", ".join(comparisons))
    if seen.intent in ("explain", "news_and_explain", "exploratory_research"):
        parts.append(f"intent {seen.intent}")
    if turn.result.renderer is RendererKind.REFUSE and turn.result.message:
        parts.append(f"“{turn.result.message[:80]}”")
    return "; ".join(parts)


def run(selected: Sequence[PhraseCase] | None = None, runtime: Any = None) -> list[Outcome]:
    runtime = runtime or recorded_runtime()
    ranking = runtime.ranking
    assert isinstance(ranking, SnapshotRanking)
    cascade = CascadeCompleter(runtime.completer, _NoModel(), ranking.knows_industry)
    runtime = replace(runtime, completer=cascade)
    outcomes = []
    for case in selected if selected is not None else cases():
        store = EphemeralThreadStore()
        thread = f"phrase-{uuid.uuid4().hex}"
        turn: ConversationTurn | None = None
        sent: list[str] = []
        for number, message in enumerate(case.turns, start=1):
            cascade.last_reason = None
            turn = run_conversation_turn(thread, message, runtime, store=store)
            if cascade.last_reason is not None:
                why = _UNSURE.get(cascade.last_reason, cascade.last_reason)
                sent.append(why if len(case.turns) == 1 else f"turn {number}: {why}")
        assert turn is not None
        seen = observe(turn)
        outcomes.append(
            Outcome(case, case.check(seen, turn), _describe(seen, turn), "; ".join(sent) or None)
        )
    return outcomes


def render_markdown(outcomes: Sequence[Outcome]) -> str:
    groups: dict[str, list[Outcome]] = {}
    for outcome in outcomes:
        groups.setdefault(outcome.case.group, []).append(outcome)
    passed = sum(outcome.passed for outcome in outcomes)
    sent = [outcome for outcome in outcomes if outcome.sent_to_model]
    lines = [
        "# Phrase coverage",
        "",
        f"Generated `{datetime.now(UTC).isoformat()}` on the recorded runtime with the rules "
        f"planner. {len(outcomes)} everyday phrasings of a metric, a window, a change or a "
        "follow-up, each asked as a whole question and judged by the README's "
        "[How a question is read](../../README.md#how-a-question-is-read). No network and no "
        f"model. **{passed} of {len(outcomes)} ({passed / len(outcomes):.0%}) are read right**; "
        f"the live app's cascade would send {len(sent)} to the LLM planner.",
        "",
        "| Group | Phrasings | Read right |",
        "| --- | ---: | ---: |",
    ]
    for group, rows in groups.items():
        right = sum(row.passed for row in rows)
        lines.append(f"| {group} | {len(rows)} | {right} ({right / len(rows):.0%}) |")
    misses = [outcome for outcome in outcomes if not outcome.passed]
    lines += ["", "## Not read right", ""]
    if not misses:
        lines.append("None.")
    else:
        lines += ["| Question | Expected | Got |", "| --- | --- | --- |"]
        for outcome in misses:
            question = " → ".join(f"`{turn}`" for turn in outcome.case.turns)
            lines.append(f"| {question} | {outcome.case.expected} | {outcome.seen} |")
    lines += [
        "",
        "Each miss is a gap in the shared reading of words, which every planner passes "
        "through (ADR 0010, 0011); `KNOWN_GAPS` in `phrase_coverage.py` lists them, and the "
        "test fails when a phrasing outside it is misread, or one on it starts being read "
        "right.",
        "",
        "## Sent to the LLM planner",
        "",
        "The live app plans with the cascade (ADR 0012): the rules planner, and the LLM "
        "planner on a turn the rules planner is unsure of. Here a stand-in that declines "
        "takes the LLM planner's place, so every answer above is the rules planner's. "
        "These are the phrasings the live app would send on, and so could read differently "
        "from this report.",
        "",
    ]
    if not sent:
        lines.append("None.")
    else:
        lines += ["| Question | Why the rules planner is unsure | Read right here |"]
        lines += ["| --- | --- | --- |"]
        for outcome in sent:
            question = " → ".join(f"`{turn}`" for turn in outcome.case.turns)
            read = "yes" if outcome.passed else "no"
            lines.append(f"| {question} | {outcome.sent_to_model} | {read} |")
    lines += [
        "",
        "`SENT_TO_MODEL` in `phrase_coverage.py` lists them with the reason each is "
        "expected, and the test fails when the list and the cascade disagree.",
        "",
    ]
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--no-write", action="store_true", help="print, do not write the report")
    args = parser.parse_args(argv)
    markdown = render_markdown(run())
    if args.no_write:
        print(markdown)
        return
    REPORT_PATH.write_text(markdown, encoding="utf-8")


if __name__ == "__main__":
    main()
