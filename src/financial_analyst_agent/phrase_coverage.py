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

The live app plans with the cascade (ADR 0012), which sends a turn the rules
planner is unsure of to the LLM planner. Here a stand-in that declines takes the
LLM planner's place, so every answer is still the rules planner's, and the
report lists the phrasings the live app would send on: each can be misread live
though it is read right here. ``SENT_TO_MODEL`` lists them, kept true the same way.

    uv run python -m financial_analyst_agent.phrase_coverage   # writes the report
"""

from __future__ import annotations

import argparse
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
    ("net_income_ttm", ("trailing twelve month net income", "TTM net income")),
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
    ("for the most recent quarter", "latest_quarter", None),
    ("for the latest quarter", "latest_quarter", None),
    ("in Q2 2025", "named", None),
    ("in fiscal 2025", "named", None),
    ("for FY2024", "named", None),
    ("in calendar Q1 2026", "named", None),
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
    for question in NO_BASE_QUESTIONS:
        found.append(
            PhraseCase(f"no_base:{question}", "Changes with no base", (question,), "asks", _asks)
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
    return found


# The cases that fail today, each a gap in the shared reading of words. Take a case
# off when it is fixed; the test fails until the list matches.
KNOWN_GAPS: frozenset[str] = frozenset()


# The phrasings the cascade sends to the LLM planner. The ambiguous words name no
# catalog metric, so the rules planner is unsure; the shared guard asks which
# metric was meant whatever the LLM planner proposes (ADR 0004), so the call
# costs a second but cannot misread them. Any other phrasing sent on is a
# rules-planner reading the live app would not use: make the rules planner sure
# of it, or add it here with the reason.
SENT_TO_MODEL: frozenset[str] = frozenset(f"ambiguous:{word}" for word in AMBIGUOUS_WORDS)


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
