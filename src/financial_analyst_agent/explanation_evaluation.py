"""The explanation evaluation: does Management's explanation show a paragraph that states a cause?

The design is ``docs/process/tickets/why-from-the-filing/design.md`` ("Evaluation") and the
judge's brief ``docs/evaluation/explanation-rubric.md``. Everything here is offline and calls
no model: the labels come from a judge a person runs (ticket 03).

    uv run python -m financial_analyst_agent.explanation_evaluation cases
    uv run python -m financial_analyst_agent.explanation_evaluation candidates
    uv run python -m financial_analyst_agent.explanation_evaluation brief [--case e01]
    uv run python -m financial_analyst_agent.explanation_evaluation score --labels labels.json

``cases`` draws 40 why questions from the recorded companies and metrics with a fixed seed
and writes ``explanation-cases.json``. ``candidates`` writes, for each case, the paragraphs
``explanation.py`` chooses and the baseline's to ``explanation-candidates.json``. ``brief``
prints the judge's instructions. ``score`` reads the judge's labels and writes
``explanation.md``.
"""

from __future__ import annotations

import argparse
import json
import random
from collections.abc import Mapping, Sequence
from dataclasses import asdict, dataclass
from datetime import date
from decimal import Decimal
from functools import cache
from pathlib import Path
from typing import Any, Literal

from financial_analyst_agent.contracts import (
    DIFFERENCE_FORMULAS,
    FORMULA_COMPONENTS,
    ComparisonBase,
)
from financial_analyst_agent.domain.errors import FinancialAnalystError
from financial_analyst_agent.explanation import (
    explained_metrics,
    is_about_another_metric,
    management_explanation,
    mentions_metric,
)
from financial_analyst_agent.filing_change import extract_section, section_paragraphs
from financial_analyst_agent.prose import possessive, short_name
from financial_analyst_agent.providers.sec.urls import build_filing_document_url
from financial_analyst_agent.runtime import recorded_runtime
from financial_analyst_agent.sec_facts import SecFactLookup
from financial_analyst_agent.services.metric_catalog import METRIC_DISPLAY

ROOT = Path(__file__).resolve().parents[2]
EVALUATION = ROOT / "docs" / "evaluation"
CASES_PATH = EVALUATION / "explanation-cases.json"
CANDIDATES_PATH = EVALUATION / "explanation-candidates.json"
REPORT_PATH = EVALUATION / "explanation.md"
RUBRIC_PATH = EVALUATION / "explanation-rubric.md"
RECORDINGS = Path(__file__).parent / "data" / "sec_fixture_recordings.json"

SEED = 20261023
CASE_COUNT = 40
SETS = ("dev", "held-out")
BASES: tuple[ComparisonBase, ...] = ("year_over_year", "sequential")

Direction = Literal["rose", "fell"]

# How a question names a metric, where the catalog's label is not everyday wording.
_EVERYDAY_NAMES = {
    "research_and_development": "R&D spending",
    "selling_general_and_administrative": "SG&A expenses",
    "capital_expenditure": "capital spending",
    "rd_to_sales": "R&D-to-sales ratio",
}
_BASIS_WORDS: dict[ComparisonBase, str] = {
    "year_over_year": "year over year",
    "sequential": "sequentially",
}
# {company} is possessive. Each template has a wording for a rise, a fall, and no direction.
_TEMPLATES: tuple[dict[str, str], ...] = (
    {
        "rose": "Why did {company} {metric} rise {basis} last quarter?",
        "fell": "Why did {company} {metric} fall {basis} last quarter?",
        "none": "Why did {company} {metric} change {basis} last quarter?",
    },
    {
        "rose": "What drove {company} {metric} up {basis} this quarter?",
        "fell": "What drove {company} {metric} down {basis} this quarter?",
        "none": "What drove the change in {company} {metric} {basis} this quarter?",
    },
    {
        "rose": "What caused {company} {metric} to rise {basis} last quarter?",
        "fell": "What caused {company} {metric} to fall {basis} last quarter?",
        "none": "What drove the change in {company} {metric} {basis} this quarter?",
    },
)
_RATIO_PLACES = Decimal("0.000001")


@dataclass(frozen=True)
class Figure:
    """A recorded figure: the quarter's end date and its value, as a decimal string."""

    end_date: str
    value: str


@dataclass(frozen=True)
class ExplanationCase:
    id: str
    set: str
    company: str
    cik: str
    metric: str
    basis: ComparisonBase
    question: str
    direction: Direction | None
    report_date: str
    accession: str
    document: str
    latest: Figure | None
    compared: Figure | None


# --- recorded data -------------------------------------------------------------------


@cache
def _recording() -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads(RECORDINGS.read_text(encoding="utf-8"))
    return loaded


def recorded_documents() -> dict[str, str]:
    """The recorded filing documents, keyed ``cik:accession:document``."""
    documents: dict[str, str] = _recording()["filing_documents"]
    return documents


def recorded_facts() -> SecFactLookup:
    """The recorded runtime's fact lookup: the figures a recorded answer shows."""
    facts = recorded_runtime().facts
    assert isinstance(facts, SecFactLookup)
    return facts


def latest_quarterlies() -> dict[str, tuple[str, str, str]]:
    """Each recorded company's latest 10-Q, when its document is recorded.

    CIK → (accession, primary document, report date).
    """
    documents = recorded_documents()
    latest: dict[str, tuple[str, str, str]] = {}
    for cik, submissions in sorted(_recording()["submissions"].items()):
        recent = submissions["filings"]["recent"]
        rows = [
            (report, accession, document)
            for form, accession, report, document in zip(
                recent["form"],
                recent["accessionNumber"],
                recent["reportDate"],
                recent["primaryDocument"],
                strict=True,
            )
            if form == "10-Q"
        ]
        if not rows:
            continue
        report, accession, document = max(rows)
        if f"{cik}:{accession}:{document}" in documents:
            latest[cik] = (accession, document, report)
    return latest


def _value(metric: str, values: Sequence[Decimal]) -> Decimal:
    if metric not in FORMULA_COMPONENTS:
        return values[0]
    first, second = values
    if metric in DIFFERENCE_FORMULAS:
        return first - second
    return (first / second).quantize(_RATIO_PLACES)


def figure_move(
    facts: SecFactLookup, cik: str, metric: str, report_date: str, basis: ComparisonBase
) -> tuple[Figure | None, Figure | None]:
    """The metric's latest recorded figure and the one the basis compares it with.

    Year over year compares with the comparative the filing reports (ADR 0009);
    sequential with the quarter before, as the recorded filings date it.
    """
    components = FORMULA_COMPONENTS.get(metric, (metric,))
    on = date.fromisoformat(report_date)
    try:
        latest_facts = [facts.get_financials(cik, part, report_date=on) for part in components]
    except FinancialAnalystError:
        return None, None
    if any(fact.end_date != on for fact in latest_facts):
        return None, None
    try:
        latest = Figure(on.isoformat(), str(_value(metric, [f.value for f in latest_facts])))
    except (ArithmeticError, ValueError):
        return None, None
    compared_values: list[Decimal] = []
    compared_end: date | None = None
    if basis == "year_over_year":
        for fact in latest_facts:
            if fact.year_earlier is None:
                return latest, None
            compared_values.append(fact.year_earlier.value)
            compared_end = fact.year_earlier.end_date
    else:
        dates = facts.list_quarterly_report_dates(cik, limit=8)
        earlier = [day for day in dates if day < on]
        if not earlier:
            return latest, None
        compared_end = max(earlier)
        try:
            compared_values = [
                facts.get_financials(cik, part, report_date=compared_end).value
                for part in components
            ]
        except FinancialAnalystError:
            return latest, None
    try:
        compared_value = _value(metric, compared_values)
    except (ArithmeticError, ValueError):
        return latest, None
    assert compared_end is not None
    return latest, Figure(compared_end.isoformat(), str(compared_value))


def _direction(latest: Figure | None, compared: Figure | None) -> Direction | None:
    if latest is None or compared is None:
        return None
    now, then = Decimal(latest.value), Decimal(compared.value)
    if now > then:
        return "rose"
    if now < then:
        return "fell"
    return None


def everyday_metric(metric: str) -> str:
    """ "gross margin", "R&D spending": the metric as a question would name it."""
    return _EVERYDAY_NAMES.get(metric) or METRIC_DISPLAY[metric].label.lower().replace(
        "sg&a", "SG&A"
    )


def question_for(
    company: str, metric: str, basis: ComparisonBase, direction: Direction | None, template: int
) -> str:
    """A why question in everyday wording; its verb follows the recorded direction."""
    wording = _TEMPLATES[template][direction or "none"]
    return wording.format(
        company=possessive(company), metric=everyday_metric(metric), basis=_BASIS_WORDS[basis]
    )


# --- the case draw -------------------------------------------------------------------


def draw_cases(seed: int = SEED) -> list[ExplanationCase]:
    """40 why questions drawn by code from the recorded companies and metrics.

    The pool is every recorded company with its latest 10-Q's document, crossed
    with the metrics ``explanation.py`` has words for, where the recorded facts
    hold that metric for that quarter (an answer shows a figure before a why).
    Half the cases are year over year and half sequential; each half splits
    evenly between the development and held-out sets.
    """
    facts = recorded_facts()
    quarterlies = latest_quarterlies()
    rng = random.Random(seed)
    pool: list[tuple[str, str]] = []
    for cik in sorted(quarterlies):
        report_date = quarterlies[cik][2]
        for metric in sorted(explained_metrics()):
            latest, _ = figure_move(facts, cik, metric, report_date, "year_over_year")
            if latest is not None:
                pool.append((cik, metric))
    pairs = rng.sample(pool, CASE_COUNT)
    bases = [basis for basis in BASES for _ in range(CASE_COUNT // len(BASES))]
    rng.shuffle(bases)
    templates = [rng.randrange(len(_TEMPLATES)) for _ in pairs]
    seen: dict[ComparisonBase, int] = {}
    cases = []
    for index, ((cik, metric), basis, template) in enumerate(
        zip(pairs, bases, templates, strict=True)
    ):
        order = seen.get(basis, 0)
        seen[basis] = order + 1
        split = SETS[0] if order < CASE_COUNT // (2 * len(BASES)) else SETS[1]
        accession, document, report_date = quarterlies[cik]
        latest, compared = figure_move(facts, cik, metric, report_date, basis)
        direction = _direction(latest, compared)
        company = _company_name(facts, cik, report_date, metric)
        cases.append(
            ExplanationCase(
                id=f"e{index + 1:02d}",
                set=split,
                company=company,
                cik=cik,
                metric=metric,
                basis=basis,
                question=question_for(company, metric, basis, direction, template),
                direction=direction,
                report_date=report_date,
                accession=accession,
                document=document,
                latest=latest,
                compared=compared,
            )
        )
    return cases


def _company_name(facts: SecFactLookup, cik: str, report_date: str, metric: str) -> str:
    part = FORMULA_COMPONENTS.get(metric, (metric,))[0]
    fact = facts.get_financials(cik, part, report_date=date.fromisoformat(report_date))
    return short_name(fact.company_name)


def cases_payload(cases: Sequence[ExplanationCase], seed: int = SEED) -> dict[str, Any]:
    return {"seed": seed, "cases": [asdict(case) for case in cases]}


def _case_from(raw: Mapping[str, Any]) -> ExplanationCase:
    fields = dict(raw)
    for key in ("latest", "compared"):
        fields[key] = Figure(**fields[key]) if fields[key] is not None else None
    return ExplanationCase(**fields)


def load_cases(path: Path = CASES_PATH) -> list[ExplanationCase]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    return [_case_from(case) for case in raw["cases"]]


# --- candidates ----------------------------------------------------------------------


def _source(case: ExplanationCase) -> tuple[str, str]:
    html = recorded_documents()[f"{case.cik}:{case.accession}:{case.document}"]
    return html, build_filing_document_url(case.cik, case.accession, case.document)


def baseline_paragraph(html: str, metric: str) -> str | None:
    """The baseline: the MD&A's first paragraph that names the metric."""
    for paragraph in section_paragraphs(extract_section(html, "mda")):
        if mentions_metric(paragraph, metric):
            return paragraph
    return None


def _case_candidates(case: ExplanationCase) -> dict[str, Any]:
    html, url = _source(case)
    explanation = management_explanation(html, case.metric, case.basis, url)
    paragraphs: list[dict[str, Any]] = []
    ids: dict[str, str] = {}

    def paragraph_id(text: str, cause: str | None) -> str:
        """Each distinct paragraph once, so the judge labels it once."""
        if text not in ids:
            ids[text] = f"{case.id}-p{len(ids) + 1}"
            paragraphs.append({"id": ids[text], "text": text, "cause": cause})
        return ids[text]

    scored = []
    for rank, chosen in enumerate(explanation.paragraphs, start=1):
        cause = chosen.text[chosen.cause[0] : chosen.cause[1]] if chosen.cause else None
        scored.append(
            {"paragraph": paragraph_id(chosen.text, cause), "rank": rank, "score": chosen.score}
        )
    baseline = baseline_paragraph(html, case.metric)
    return {
        "id": case.id,
        "set": case.set,
        "question": case.question,
        "company": case.company,
        "metric": case.metric,
        "basis": case.basis,
        "report_date": case.report_date,
        "accession": case.accession,
        "url": url,
        "reason": explanation.reason,
        "paragraphs": paragraphs,
        "scored": scored,
        "baseline": paragraph_id(baseline, None) if baseline is not None else None,
    }


def build_candidates(cases: Sequence[ExplanationCase]) -> dict[str, Any]:
    """Each case's chosen paragraphs, best first, and the baseline's, for the judge to label."""
    return {"cases": [_case_candidates(case) for case in cases]}


# --- scoring -------------------------------------------------------------------------


def _explains(labels: Mapping[str, Any], case_id: str, paragraph: str) -> bool:
    explains = labels[case_id]["explains"]
    if paragraph not in explains:
        raise ValueError(f"no label for paragraph {paragraph} of case {case_id}")
    return bool(explains[paragraph])


def _tally(
    shown: Sequence[Sequence[bool] | None], nothing_to_find: Sequence[bool]
) -> dict[str, int]:
    """Precision counts for one method: each case's labels for what it showed, best first."""
    tally = {"cases": len(shown), "shown": 0, "at_1": 0, "at_3": 0}
    tally |= {"nothing_found": 0, "nothing_found_right": 0}
    for labels, empty in zip(shown, nothing_to_find, strict=True):
        if not labels:
            tally["nothing_found"] += 1
            tally["nothing_found_right"] += int(empty)
            continue
        tally["shown"] += 1
        tally["at_1"] += int(labels[0])
        tally["at_3"] += int(any(labels[:3]))
    return tally


def score(
    candidates: Mapping[str, Any], labels: Mapping[str, Any], sets: Mapping[str, str]
) -> dict[str, Any]:
    """Precision at 1 and 3, and "nothing found", for the scoring and the baseline, per set.

    Precision at k is the share of cases shown at least one paragraph where one of
    the first k states a cause (the design's label). "Nothing found" is right when
    the judge found no cause anywhere in the MD&A.
    """
    by_case = labels["labels"]
    summary: dict[str, Any] = {}
    for split in (*SETS, "all"):
        entries = [
            entry
            for entry in candidates["cases"]
            if split == "all" or sets[entry["id"]] == split
        ]
        if not entries:
            continue
        scored: list[Sequence[bool] | None] = []
        baseline: list[Sequence[bool] | None] = []
        empty = []
        firsts = []
        for entry in entries:
            case_id = entry["id"]
            if case_id not in by_case:
                raise ValueError(f"no labels for case {case_id}")
            empty.append(bool(by_case[case_id]["nothing_to_find"]))
            ranked = [rank["paragraph"] for rank in entry["scored"]]
            scored.append([_explains(by_case, case_id, pid) for pid in ranked])
            base = entry["baseline"]
            baseline.append([_explains(by_case, case_id, base)] if base else None)
            if ranked:
                text = next(p["text"] for p in entry["paragraphs"] if p["id"] == ranked[0])
                if is_about_another_metric(text, entry["metric"]):
                    firsts.append({"case": case_id, "metric": entry["metric"], "text": text})
        summary[split] = {
            "scoring": _tally(scored, empty),
            "baseline": _tally(baseline, empty),
            "other_metric_firsts": firsts,
        }
    return summary


def _rate(hits: int, of: int) -> str:
    return f"{hits / of:.2f} ({hits} of {of})" if of else "n/a (0 of 0)"


def report_markdown(summary: Mapping[str, Any], *, judge: str) -> str:
    """The evaluation's report, ``docs/evaluation/explanation.md``."""
    lines = [
        "# Management's explanation: evaluation",
        "",
        "Written by `uv run python -m financial_analyst_agent.explanation_evaluation score`. "
        f"Labels by {judge}. The cases are `explanation-cases.json`; the paragraphs labelled "
        "are `explanation-candidates.json`; the judge's brief is `explanation-rubric.md`.",
        "",
        "Precision at k: of the cases shown at least one paragraph, the share where one of "
        "the first k states a cause of the metric's move. The baseline shows the MD&A's "
        "first paragraph that names the metric, so its precision at 1 and at 3 are the same. "
        "\"Nothing found\" is right when the judge found no cause anywhere in the MD&A.",
        "",
        "Bar: precision at 3 of 0.8 or better for the scoring, with no first-place paragraph "
        "about another metric.",
        "",
    ]
    for split, results in summary.items():
        lines += [
            f"## {split}",
            "",
            "| Method | Shown | Precision at 1 | Precision at 3 | Nothing found right |",
            "| --- | --- | --- | --- | --- |",
        ]
        for method in ("scoring", "baseline"):
            tally = results[method]
            lines.append(
                f"| {method} | {tally['shown']} of {tally['cases']} "
                f"| {_rate(tally['at_1'], tally['shown'])} "
                f"| {_rate(tally['at_3'], tally['shown'])} "
                f"| {_rate(tally['nothing_found_right'], tally['nothing_found'])} |"
            )
        lines += ["", "First-place paragraphs about another metric (by code's reading):", ""]
        firsts = results["other_metric_firsts"]
        if not firsts:
            lines.append("- None.")
        for first in firsts:
            text = " ".join(first["text"].split())
            lines.append(f"- {first['case']} ({first['metric']}): {text[:200]}")
        lines.append("")
    return "\n".join(lines)


# --- the judge's brief ---------------------------------------------------------------


def brief() -> str:
    """The judge's instructions: the rubric, without its history of changes."""
    text = RUBRIC_PATH.read_text(encoding="utf-8")
    return text.split("\n## Changes", 1)[0].strip()


_BASIS_NAMES: dict[str, str] = {
    "year_over_year": "year over year (against the same quarter a year earlier)",
    "sequential": "sequential (against the quarter before)",
}


def paragraph_prompt(entry: Mapping[str, Any], paragraph: Mapping[str, Any]) -> str:
    """What the judge is shown to label one paragraph."""
    return "\n".join(
        [
            brief(),
            "",
            "## The paragraph to judge",
            "",
            *_case_lines(entry),
            "Paragraph:",
            "",
            paragraph["text"],
            "",
            'Answer with the paragraph judgement\'s JSON object only: {"explains": ..., '
            '"scope": ..., "reason": ...}.',
        ]
    )


def mda_prompt(entry: Mapping[str, Any], html: str) -> str:
    """What the judge is shown to decide whether the MD&A holds a cause at all."""
    paragraphs = section_paragraphs(extract_section(html, "mda"))
    return "\n".join(
        [
            brief(),
            "",
            "## The MD&A to judge",
            "",
            *_case_lines(entry),
            "The MD&A, one paragraph per block:",
            "",
            "\n\n".join(paragraphs) or "(no MD&A text was found)",
            "",
            'Answer with the MD&A judgement\'s JSON object only: {"nothing_to_find": ..., '
            '"where": ..., "reason": ...}.',
        ]
    )


def _case_lines(entry: Mapping[str, Any]) -> list[str]:
    return [
        f"Question: {entry['question']}",
        f"Company: {entry['company']}",
        f"Metric: {everyday_metric(entry['metric'])}",
        f"Basis: {_BASIS_NAMES[entry['basis']]}",
        f"Quarter ended: {entry['report_date']}",
        "",
    ]


# --- command line --------------------------------------------------------------------


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("cases", help="draw the cases from the recorded data")
    sub.add_parser("candidates", help="write each case's paragraphs for the judge")
    bri = sub.add_parser("brief", help="print the judge's instructions")
    bri.add_argument("--case", help="print the filled prompts for one case instead")
    sco = sub.add_parser("score", help="score the judge's labels")
    sco.add_argument("--labels", required=True, type=Path)
    args = parser.parse_args(argv)

    if args.command == "cases":
        cases = draw_cases(SEED)
        _write_json(CASES_PATH, cases_payload(cases, SEED))
        moved = sum(case.direction is not None for case in cases)
        print(f"wrote {len(cases)} cases (seed {SEED}); {moved} with a recorded direction")
        return
    if args.command == "candidates":
        built = build_candidates(load_cases())
        _write_json(CANDIDATES_PATH, built)
        empty = sum(not entry["scored"] for entry in built["cases"])
        print(f"wrote candidates for {len(built['cases'])} cases; nothing found for {empty}")
        return
    if args.command == "brief":
        if not args.case:
            print(brief())
            return
        entries = json.loads(CANDIDATES_PATH.read_text(encoding="utf-8"))["cases"]
        entry = next(entry for entry in entries if entry["id"] == args.case)
        case = next(case for case in load_cases() if case.id == args.case)
        for paragraph in entry["paragraphs"]:
            print(f"===== {paragraph['id']}\n{paragraph_prompt(entry, paragraph)}\n")
        print(f"===== {args.case} MD&A\n{mda_prompt(entry, _source(case)[0])}")
        return
    if args.command == "score":
        candidates = json.loads(CANDIDATES_PATH.read_text(encoding="utf-8"))
        labels = json.loads(args.labels.read_text(encoding="utf-8"))
        sets = {case.id: case.set for case in load_cases()}
        summary = score(candidates, labels, sets)
        REPORT_PATH.write_text(
            report_markdown(summary, judge=str(labels.get("judge", "an unnamed judge"))) + "\n",
            encoding="utf-8",
        )
        print(json.dumps({split: result["scoring"] for split, result in summary.items()}))


if __name__ == "__main__":
    main()
