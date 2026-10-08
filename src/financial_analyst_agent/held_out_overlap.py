"""Which held-out cases share a template with earlier data, and how far two labellers agree.

A held-out set measures how a planner reads wording it has not been tuned on.
Its writer never sees the development cases, so a held-out question that
shares their template ("Apple revenue last 4 quarters" beside "Microsoft
revenue last 4 quarters") is chance, as it would be in real traffic. Nothing
is removed for it: dropping familiar questions would push each new set toward
rarer wording and make sets incomparable. This report lists them, and the
planner comparison scores the held-out set as familiar and novel beside the
whole (``planner_evaluation``).

A template is a question with its companies and numbers replaced; two
questions share one when their templates' words overlap by ``THRESHOLD`` or
more (Jaccard). Earlier data is every development case and every phrase-coverage
phrasing, plus any probe files named on the command line.

``--labels FIRST SECOND`` compares two labellings of the same held-out questions
field by field, for the check made before any planner runs.

    uv run python -m financial_analyst_agent.held_out_overlap
    uv run python -m financial_analyst_agent.held_out_overlap --labels a.json b.json
"""

from __future__ import annotations

import argparse
import json
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from financial_analyst_agent.planner_evaluation import FIELDS, current_held_out, load_cases
from financial_analyst_agent.rules_planner import FIXTURE_UNIVERSE_SNAPSHOT_PATH

THRESHOLD = 0.8

# Names the recorded companies go by beyond their snapshot names and tickers.
_ALIASES = (
    "google",
    "nvidia",
    "lilly",
    "j&j",
    "jnj",
    "bofa",
    "wells",
    "goldman",
    "thermo",
    "jpmorgan",
    "unitedhealth",
    "abbvie",
)
_WORD = re.compile(r"[a-z0-9&$/'-]+")
_NUMBER = re.compile(r"^\$?\d[\d,.]*%?$|^(?:one|two|three|four|five|six|seven|eight|nine|ten)$")


def _company_words() -> frozenset[str]:
    snapshot = json.loads(FIXTURE_UNIVERSE_SNAPSHOT_PATH.read_text(encoding="utf-8"))
    words: set[str] = set(_ALIASES)
    for company in snapshot["companies"]:
        words.add(str(company.get("ticker", "")).casefold())
        name = str(company.get("name", "")).casefold()
        # The name's distinctive first word: "apple", "microsoft", "eli".
        words.update(_WORD.findall(name)[:1])
    return frozenset(word for word in words if word)


def template(question: str, companies: frozenset[str]) -> frozenset[str]:
    """The question's words, with companies and numbers replaced by placeholders."""
    words = []
    for word in _WORD.findall(question.casefold()):
        bare = word.strip("'$").removesuffix("'s")
        if bare in companies:
            words.append("<company>")
        elif _NUMBER.match(word):
            words.append("<n>")
        else:
            words.append(bare)
    return frozenset(words)


def _similarity(first: frozenset[str], second: frozenset[str]) -> float:
    if not first or not second:
        return 0.0
    return len(first & second) / len(first | second)


@dataclass(frozen=True)
class Earlier:
    source: str
    text: str
    words: frozenset[str]


def _earlier(source: str, turns: Sequence[str], companies: frozenset[str]) -> Earlier:
    return Earlier(source, " → ".join(turns), template(" ".join(turns), companies))


def earlier_data(probe_files: Sequence[Path], companies: frozenset[str]) -> list[Earlier]:
    """Every development case, every phrase-coverage phrasing, and the probes given."""
    from financial_analyst_agent.phrase_coverage import cases as phrase_cases

    found = [
        _earlier(f"case {case.case_id}", case.turns, companies)
        for case in load_cases()
        if case.split != "held_out"
    ]
    found += [
        _earlier(f"coverage {case.case_id}", case.turns, companies) for case in phrase_cases()
    ]
    for path in probe_files:
        for raw in json.loads(path.read_text(encoding="utf-8"))["cases"]:
            found.append(_earlier(f"probe {raw['id']}", list(raw["turns"]), companies))
    return found


def overlap_report(probe_files: Sequence[Path] = ()) -> dict[str, Any]:
    """The current held-out set's cases that share a template with earlier data."""
    held = current_held_out()
    companies = _company_words()
    earlier = earlier_data(probe_files, companies)
    held_out = [case for case in load_cases(held.cases) if case.split == "held_out"]
    familiar = []
    for case in held_out:
        words = template(" ".join(case.turns), companies)
        scored = [(_similarity(words, item.words), item) for item in earlier]
        # The first of equally near questions, as max(key=...) keeps the first maximum.
        score, nearest = max(scored, key=lambda pair: pair[0])
        if score >= THRESHOLD:
            familiar.append(
                {
                    "id": case.case_id,
                    "question": " → ".join(case.turns),
                    "nearest": nearest.source,
                    "nearest_question": nearest.text,
                    "similarity": round(score, 2),
                }
            )
    return {
        "held_out_set": held.number,
        "threshold": THRESHOLD,
        "cases": len(held_out),
        "earlier": len(earlier),
        "probe_files": [str(path) for path in probe_files],
        "familiar": familiar,
    }


def render_overlap(report: dict[str, Any]) -> str:
    count = len(report["familiar"])
    lines = [
        f"# Held-out set {report['held_out_set']}: overlap with earlier data",
        "",
        f"{count} of {report['cases']} held-out cases share a template with one of "
        f"{report['earlier']} earlier questions (development cases, phrase-coverage "
        "phrasings and probes): companies and numbers replaced, their words overlapping by "
        f"{report['threshold']:.0%} or more. None is removed: the planner comparison scores "
        "the set as familiar and novel beside the whole (`held_out_overlap`).",
        "",
    ]
    if report["familiar"]:
        lines += [
            "| Case | Question | Nearest earlier | Similarity |",
            "| --- | --- | --- | ---: |",
        ]
        for row in report["familiar"]:
            # A follow-up coverage case's id holds "|", which would end the cell.
            cells = {key: str(row[key]).replace("|", "\\|") for key in row}
            lines.append(
                f"| `{cells['id']}` | `{cells['question']}` | {cells['nearest']}: "
                f"`{cells['nearest_question']}` | {row['similarity']:.2f} |"
            )
        lines.append("")
    return "\n".join(lines)


def label_agreement(first: Path, second: Path) -> dict[str, Any]:
    """Two labellings of the same questions, compared field by field."""

    def by_question(path: Path) -> dict[tuple[str, ...], dict[str, Any]]:
        data = json.loads(path.read_text(encoding="utf-8"))
        return {tuple(raw["turns"]): raw for raw in data["cases"]}

    a, b = by_question(first), by_question(second)
    shared = [turns for turns in a if turns in b]
    fields: dict[str, list[bool]] = {name: [] for name in FIELDS}
    disagreements = []
    for turns in shared:
        left, right = a[turns]["expect"], b[turns]["expect"]
        differ = {}
        for name in FIELDS:
            if name in left or name in right:
                same = _same(left.get(name), right.get(name))
                fields[name].append(same)
                if not same:
                    differ[name] = {"first": left.get(name), "second": right.get(name)}
        if differ:
            disagreements.append({"id": a[turns]["id"], "turns": list(turns), "fields": differ})
    return {
        "first": str(first),
        "second": str(second),
        "questions": len(shared),
        "only_first": len(a) - len(shared),
        "only_second": len(b) - len(shared),
        "agree_on_every_field": len(shared) - len(disagreements),
        "fields": {
            name: {"labelled": len(values), "agree": sum(values)}
            for name, values in fields.items()
            if values
        },
        "disagreements": disagreements,
    }


def _same(first: Any, second: Any) -> bool:
    """Equal labels; lists compare as sets, and a field one labeller left out never agrees."""
    if isinstance(first, list) and isinstance(second, list):
        return sorted(map(str, first)) == sorted(map(str, second))
    return bool(first == second)


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--probes", nargs="*", type=Path, default=[], help="probe case files")
    parser.add_argument("--labels", nargs=2, type=Path, help="compare two labellings")
    parser.add_argument("--no-write", action="store_true", help="print, do not write")
    args = parser.parse_args(argv)
    if args.labels:
        print(json.dumps(label_agreement(*args.labels), indent=2, ensure_ascii=False))
        return
    report = overlap_report(args.probes)
    markdown = render_overlap(report)
    if args.no_write:
        print(markdown)
        return
    held = current_held_out()
    held.overlap.write_text(
        json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    held.overlap.with_suffix(".md").write_text(markdown, encoding="utf-8")
    print(f"{len(report['familiar'])} of {report['cases']} held-out cases are familiar")


if __name__ == "__main__":
    main()
