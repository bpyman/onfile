"""How the numeral lock treats the numbers in an essay, measured on known sentences.

An essay written about an answer may quote only the numbers in that answer's
grounding: its table rows, as JSON (``evidence_store.grounding_json_from_result``).
The lock withholds an essay with any other number (``numeral_lock.numeral_lock_extras``).

This takes the grounding of recorded answers, writes sentences that quote one of
its values in a known way (exactly as the JSON holds it, as the window shows it,
rounded, with a digit changed, invented, attached to the wrong company, or in
words), and runs the lock on each. It calls no model and no network, so it
measures the lock itself, not how often a model's essays trip it.

    uv run python -m financial_analyst_agent.numeral_lock_evaluation
"""

from __future__ import annotations

import argparse
import json
import re
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, overload

from financial_analyst_agent.evidence_store import grounding_json_from_result
from financial_analyst_agent.numeral_lock import numeral_lock_extras
from financial_analyst_agent.presentation import format_metric_value
from financial_analyst_agent.runtime import recorded_runtime
from financial_analyst_agent.services.metric_catalog import METRIC_DISPLAY
from financial_analyst_agent.turn import run_turn

REPORT_PATH = Path("docs/evaluation/numeral-lock.md")
REPORT_JSON_PATH = Path("docs/evaluation/numeral-lock.json")

# Recorded answers whose rows an essay would be grounded in: lookups, windows,
# comparisons, margins, per-share figures, balance-sheet amounts and a ranking.
QUESTIONS = (
    "Compare Eli Lilly and Pfizer revenue and net margin",
    "Microsoft revenue over the last four quarters",
    "NVIDIA diluted EPS last 8 quarters",
    "Top 5 semiconductor companies by revenue",
    "Apple gross margin",
    "Compare Merck, AbbVie and Amgen R&D",
    "Oracle free cash flow over the last 4 quarters",
    "Johnson & Johnson cash",
    "Broadcom operating margin over the last six quarters",
    "Compare JPMorgan and Wells Fargo net income",
)


@dataclass(frozen=True)
class Quote:
    """One value of an answer: whose, which metric, and how the JSON and window give it."""

    company: str
    metric: str
    raw: str
    shown: str


@dataclass(frozen=True)
class Kind:
    name: str
    description: str
    # What a lock that keeps essays to their sources should do with the sentence.
    should_withhold: bool
    sentence: Callable[[Quote, Sequence[Quote]], str | None]


@overload
def _say(quote: Quote, number: str) -> str: ...
@overload
def _say(quote: Quote, number: None) -> None: ...
@overload
def _say(quote: Quote, number: str | None) -> str | None: ...


def _say(quote: Quote, number: str | None) -> str | None:
    """The sentence quoting ``number`` as the company's figure; none without a number."""
    if number is None:
        return None
    label = METRIC_DISPLAY[quote.metric].label if quote.metric in METRIC_DISPLAY else quote.metric
    return f"{quote.company} reported {label.lower()} of {number} for the quarter."


def _shown_in_words(shown: str) -> str:
    """ "$22.97 B" as "$22.97 billion"; percentages and per-share amounts as they are."""
    for short, word in ((" T", " trillion"), (" B", " billion"), (" M", " million")):
        if shown.endswith(short):
            return shown[: -len(short)] + word
    return shown


def _rounded(shown: str) -> str | None:
    """The shown number rounded to a whole number: "$22.97 B" as "$23 billion"."""
    match = re.fullmatch(r"(-?\$?)(-?[\d,]+\.\d+)(.*)", _shown_in_words(shown))
    if match is None:
        return None
    sign, digits, unit = match.groups()
    whole = round(float(digits.replace(",", "")))
    return f"about {sign}{whole}{unit}"


def _last_digit_changed(text: str) -> str | None:
    """``text`` with its last digit one higher (9 becomes 8), or None without a digit."""
    for index in range(len(text) - 1, -1, -1):
        if text[index].isdigit():
            digit = int(text[index])
            changed = str(digit + 1 if digit < 9 else 8)
            return text[:index] + changed + text[index + 1 :]
    return None


def _other(quote: Quote, quotes: Sequence[Quote]) -> Quote | None:
    """Another company's value of the same metric, if the answer has one."""
    return next(
        (
            other
            for other in quotes
            if other.company != quote.company
            and other.metric == quote.metric
            and other.raw != quote.raw
        ),
        None,
    )


def _say_other(quote: Quote, quotes: Sequence[Quote]) -> str | None:
    """Another company's value of the same metric, given as this company's."""
    other = _other(quote, quotes)
    return _say(quote, other.raw if other else None)


KINDS: tuple[Kind, ...] = (
    Kind(
        "exact_json",
        "the value exactly as the JSON holds it (22974000000, 0.3088273701)",
        False,
        lambda q, _qs: _say(q, q.raw),
    ),
    Kind(
        "as_shown",
        "the value as the window shows it ($22.97 B, 30.9%)",
        False,
        lambda q, _qs: _say(q, q.shown),
    ),
    Kind(
        "as_shown_in_words",
        "the shown value with its unit in words ($22.97 billion)",
        False,
        lambda q, _qs: _say(q, _shown_in_words(q.shown)),
    ),
    Kind(
        "rounded",
        "the shown value rounded to a whole number (about $23 billion)",
        False,
        lambda q, _qs: _say(q, _rounded(q.shown)),
    ),
    Kind(
        "json_digit_changed",
        "the JSON value with its last digit changed",
        True,
        lambda q, _qs: _say(q, _last_digit_changed(q.raw)),
    ),
    Kind(
        "shown_digit_changed",
        "the shown value with its last digit changed ($22.98 B)",
        True,
        lambda q, _qs: _say(q, _last_digit_changed(q.shown)),
    ),
    Kind(
        "invented",
        "a number the answer does not hold (a growth rate of 17.3%)",
        True,
        lambda q, _qs: _say(q, q.raw) + " That is growth of 17.3% from a year earlier.",
    ),
    Kind(
        "misattributed",
        "another company's value of the same metric, given as this company's",
        True,
        _say_other,
    ),
    Kind(
        "in_words",
        "a figure written out in words (twenty-three billion dollars)",
        True,
        lambda q, _qs: _say(q, "twenty-three billion dollars"),
    ),
)


def quotes_for(question: str, runtime: Any) -> tuple[str, list[Quote]]:
    """A recorded answer's grounding JSON, and each value in it, raw and as the window shows it."""
    grounding = grounding_json_from_result(run_turn(question, runtime))
    if not grounding:
        return grounding, []
    quotes = [
        Quote(
            company=str(row["company_name"]),
            metric=str(row["metric"]),
            raw=str(row["value"]),
            shown=format_metric_value(str(row["metric"]), Decimal(str(row["value"]))),
        )
        for row in json.loads(grounding)
        if row.get("value") not in (None, "") and row.get("metric")
    ]
    return grounding, quotes


def sentences(quotes: Sequence[Quote]) -> Iterator[tuple[Kind, Quote, str]]:
    for quote in quotes:
        for kind in KINDS:
            sentence = kind.sentence(quote, quotes)
            if sentence is not None:
                yield kind, quote, sentence


def measure(questions: Sequence[str] = QUESTIONS) -> dict[str, Any]:
    runtime = recorded_runtime()
    counts = {kind.name: {"sentences": 0, "withheld": 0} for kind in KINDS}
    examples: dict[str, dict[str, Any]] = {}
    answers = 0
    for question in questions:
        grounding, quotes = quotes_for(question, runtime)
        if not quotes:
            continue
        answers += 1
        for kind, _quote, sentence in sentences(quotes):
            withheld = bool(numeral_lock_extras(sentence, grounding))
            counts[kind.name]["sentences"] += 1
            counts[kind.name]["withheld"] += withheld
            examples.setdefault(kind.name, {"sentence": sentence, "withheld": withheld})
    return {
        "generated_at": datetime.now(UTC).isoformat(),
        "answers": answers,
        "questions": list(questions),
        "kinds": [
            {
                "name": kind.name,
                "description": kind.description,
                "should_withhold": kind.should_withhold,
                **counts[kind.name],
                "example": examples.get(kind.name),
            }
            for kind in KINDS
        ],
    }


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Numeral lock",
        "",
        f"Generated `{report['generated_at']}` on the recorded runtime. An essay about an "
        "answer may quote only the numbers in that answer's grounding, its table rows as "
        "JSON; the lock withholds an essay with any other number. Here the grounding of "
        f"{report['answers']} recorded answers is quoted one value at a time, in each way "
        "below, and the lock is run on each sentence. No model is called: this measures "
        "the lock itself.",
        "",
        "| A sentence that quotes | Should be withheld | Sentences | Withheld | Right |",
        "| --- | :---: | ---: | ---: | ---: |",
    ]
    for kind in report["kinds"]:
        total = kind["sentences"]
        withheld = kind["withheld"]
        right = withheld if kind["should_withhold"] else total - withheld
        lines.append(
            f"| {kind['description']} | {'yes' if kind['should_withhold'] else 'no'} | "
            f"{total} | {withheld} ({withheld / total:.0%}) | {right / total:.0%} |"
            if total
            else f"| {kind['description']} | — | 0 | — | — |"
        )
    lines += [
        "",
        "How to read it: a number passes when the grounding holds it, or when it rounds "
        "from a grounded value at the precision it is written to, with at least two "
        "significant digits: $22.97 B, $22.97 billion, about $23 billion and 30.9% all "
        "round from 22974000000 or 0.3088273701. A digit changed at that precision, or a "
        "number nothing grounded rounds to, is withheld. A figure rounded to one "
        "significant digit (about $2 for $2.46) is too coarse to tie to one value and is "
        "withheld too: those are the rounded sentences withheld above.",
        "",
        "It checks numbers, not meaning: a true value given to the wrong company passes, "
        "and so does a figure written in words. Until 5 October 2026 the lock matched "
        "digits exactly, and withheld every true figure written as the window shows it or "
        "rounded (100% of those sentences); exact quotes and changed or invented numbers "
        "were treated as now.",
    ]
    lines += ["", "<details><summary>One sentence of each kind</summary>", ""]
    for kind in report["kinds"]:
        example = kind.get("example")
        if example:
            verdict = "withheld" if example["withheld"] else "passed"
            lines.append(f"- `{kind['name']}` ({verdict}): {example['sentence']}")
    lines += ["", "</details>", ""]
    return "\n".join(lines)


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--no-write", action="store_true", help="print, do not write the report")
    args = parser.parse_args(argv)
    report = measure()
    markdown = render_markdown(report)
    if args.no_write:
        print(markdown)
        return
    REPORT_PATH.write_text(markdown, encoding="utf-8")
    REPORT_JSON_PATH.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
