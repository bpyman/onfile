"""The explanation evaluation: does Management's explanation show a paragraph that states a cause?

The design is ``docs/process/tickets/why-from-the-filing/design.md`` ("Evaluation") and the
judge's brief ``docs/evaluation/explanation-rubric.md``. Only ``judge`` and ``generate`` call
a model, and only when a person runs them (both are paid); everything else is offline.

    uv run python -m financial_analyst_agent.explanation_evaluation cases
    uv run python -m financial_analyst_agent.explanation_evaluation candidates
    uv run python -m financial_analyst_agent.explanation_evaluation brief [--case e01]
    uv run python -m financial_analyst_agent.explanation_evaluation generate --model --set tuning
    uv run python -m financial_analyst_agent.explanation_evaluation judge
    uv run python -m financial_analyst_agent.explanation_evaluation score --labels labels.json
    uv run python -m financial_analyst_agent.explanation_evaluation recordings

``cases`` writes ``explanation-cases.json``: the development set, from the first draw's seed,
a fresh held-out set from its own seed (ticket 05), a confirmation set, year over year
only, from a third (ticket 06), and phase B's final set from a fourth (ticket 07).
``candidates`` writes, for each case, the paragraphs ``explanation.py`` chooses, the
baseline's and phase B's candidates (``offered``) to ``explanation-candidates.json``.
``brief`` prints the judge's instructions. ``generate --model --set tuning|final`` asks
the essay model (phase B) to choose and explain, over the in-scope cases of the earlier
sets or of the final set, and writes ``explanation-model-<set>.json``; ``--model NAME``
names another OpenAI model. ``score`` reads the judge's labels, scores phase A and any
phase B answers, and writes ``explanation.md``. ``judge`` labels only what has no label
yet; ``--carry-from old-candidates.json`` keeps saved labels by text after ids change.
``recordings`` copies the model's answers into ``data/explanation_recordings.json``,
which the recorded runtime replays (ticket 04).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
import re
import subprocess
import tempfile
import threading
from collections import Counter
from collections.abc import Callable, Collection, Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from datetime import date
from decimal import Decimal
from functools import cache
from pathlib import Path
from typing import Any

from financial_analyst_agent.config import get_settings
from financial_analyst_agent.contracts import (
    DIFFERENCE_FORMULAS,
    FORMULA_COMPONENTS,
    ComparisonBase,
    EssayCompleter,
)
from financial_analyst_agent.domain.errors import FinancialAnalystError
from financial_analyst_agent.essay_evaluation import parse_judgement
from financial_analyst_agent.explanation import (
    EXPLANATION_INSTRUCTIONS,
    Direction,
    ExplainingParagraph,
    WhyQuestion,
    covers,
    everyday_metric,
    explained_metrics,
    explanation_candidates,
    explanation_completer,
    is_about_another_metric,
    management_explanation,
    mentions_metric,
    model_explanation,
    offered_digest,
)
from financial_analyst_agent.filing_change import extract_section, section_paragraphs
from financial_analyst_agent.prose import possessive, short_name
from financial_analyst_agent.providers.sec.urls import build_filing_document_url
from financial_analyst_agent.runtime import recorded_runtime
from financial_analyst_agent.sec_facts import SecFactLookup

ROOT = Path(__file__).resolve().parents[2]
EVALUATION = ROOT / "docs" / "evaluation"
CASES_PATH = EVALUATION / "explanation-cases.json"
CANDIDATES_PATH = EVALUATION / "explanation-candidates.json"
REPORT_PATH = EVALUATION / "explanation.md"
RUBRIC_PATH = EVALUATION / "explanation-rubric.md"
RECORDINGS = Path(__file__).parent / "data" / "sec_fixture_recordings.json"
# The model's answers the recorded runtime replays (ticket 04).
RECORDINGS_OUT = Path(__file__).parent / "data" / "explanation_recordings.json"

# The first draw (ticket 02): its development half, less the metrics no longer
# covered, is the development set.
SEED = 20261023
CASE_COUNT = 40
# The fresh held-out set (ticket 05): the first draw's held-out half was read while
# diagnosing the first judge run, so it left the evaluation.
HELD_OUT_SEED = 20261024
HELD_OUT_COUNT = 20
HELD_OUT_FIRST_ID = 41
# The confirmation set (ticket 06): drawn after phase A narrowed to year-over-year
# questions about amounts, which was chosen after reading the held-out set.
CONFIRM_SEED = 20261025
CONFIRM_COUNT = 20
CONFIRM_FIRST_ID = 61
# The final set (ticket 07): drawn before phase B's prompt is tuned, and scored once.
FINAL_SEED = 20261111
FINAL_COUNT = 20
FINAL_FIRST_ID = 81
_MOST_PER_COMPANY = 2
SETS = ("dev", "held-out", "confirm", "final")
BASES: tuple[ComparisonBase, ...] = ("year_over_year", "sequential")
# The metrics the first draw's pool was built from: ``explanation.py``'s at the time,
# cash flow and capex included, so the first draw stays reproducible from its seed.
_FIRST_DRAW_METRICS = (
    "revenue",
    "gross_margin",
    "gross_profit",
    "cost_of_revenue",
    "operating_income",
    "operating_margin",
    "net_income",
    "net_margin",
    "research_and_development",
    "rd_to_sales",
    "selling_general_and_administrative",
    "sga_ratio",
    "operating_cash_flow",
    "capital_expenditure",
    "free_cash_flow",
)
# The metrics covered when the development set was fixed and the held-out set drawn
# (ticket 05), so both stay as they were after the narrowing (ticket 06).
SECOND_DRAW_METRICS = tuple(
    metric
    for metric in _FIRST_DRAW_METRICS
    if metric not in ("operating_cash_flow", "capital_expenditure", "free_cash_flow")
)
CASES_NOTES = (
    "The development set is the first draw's development half (seed 20261023), less its "
    "operating cash flow, capex and free cash flow cases, whose metrics are no longer "
    "covered. The first draw's held-out half (e20, e22 to e40) was read while diagnosing the "
    "first judge run, so it and its labels leave the evaluation. The held-out set is a fresh "
    "draw (seed 20261024, ids from e41) from the narrowed pool, sharing no (company, metric, "
    "basis) with either half of the first draw: 10 year over year and 10 sequential. "
    "Ticket 06 narrowed phase A to year-over-year questions about amounts and gross margin, "
    "after reading the held-out set; the development and held-out sets stay for the record, "
    "drawn under the wider scope. The confirm set (seed 20261025, ids from e61) is 20 year-"
    "over-year cases from the covered metrics, sharing no (company, metric, basis) with any "
    "earlier set, and no company more than twice. The final set (seed 20261111, ids from "
    "e81) is drawn the same way for phase B (ticket 07), sharing nothing with the confirm "
    "set either; it is scored once. The earlier sets' in-scope cases tune phase B's prompt."
)

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


def question_for(
    company: str, metric: str, basis: ComparisonBase, direction: Direction | None, template: int
) -> str:
    """A why question in everyday wording; its verb follows the recorded direction."""
    wording = _TEMPLATES[template][direction or "none"]
    return wording.format(
        company=possessive(company), metric=everyday_metric(metric), basis=_BASIS_WORDS[basis]
    )


# --- the case draw -------------------------------------------------------------------


_Quarterlies = Mapping[str, tuple[str, str, str]]


def _pool(
    facts: SecFactLookup, quarterlies: _Quarterlies, metrics: Sequence[str]
) -> list[tuple[str, str]]:
    """Every recorded company with its latest 10-Q's document, crossed with the metrics,
    where the recorded facts hold that metric for that quarter (an answer shows a figure
    before a why)."""
    pool: list[tuple[str, str]] = []
    for cik in sorted(quarterlies):
        report_date = quarterlies[cik][2]
        for metric in sorted(metrics):
            latest, _ = figure_move(facts, cik, metric, report_date, "year_over_year")
            if latest is not None:
                pool.append((cik, metric))
    return pool


def _case(
    facts: SecFactLookup,
    quarterlies: _Quarterlies,
    case_id: str,
    split: str,
    pick: tuple[str, str, ComparisonBase],
    template: int,
) -> ExplanationCase:
    cik, metric, basis = pick
    accession, document, report_date = quarterlies[cik]
    latest, compared = figure_move(facts, cik, metric, report_date, basis)
    direction = _direction(latest, compared)
    company = _company_name(facts, cik, report_date, metric)
    return ExplanationCase(
        id=case_id,
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


def draw_cases(seed: int = SEED) -> list[ExplanationCase]:
    """The first draw (ticket 02): 40 why questions drawn by code from the recorded data.

    The pool is ``_pool`` over the metrics covered at the time. Half the cases are
    year over year and half sequential; each half splits evenly between the
    development and held-out sets.
    """
    facts = recorded_facts()
    quarterlies = latest_quarterlies()
    rng = random.Random(seed)
    pairs = rng.sample(_pool(facts, quarterlies, _FIRST_DRAW_METRICS), CASE_COUNT)
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
        cases.append(
            _case(facts, quarterlies, f"e{index + 1:02d}", split, (cik, metric, basis), template)
        )
    return cases


def draw_held_out(seed: int, used: Collection[tuple[str, str, str]]) -> list[ExplanationCase]:
    """A fresh held-out set: 20 why questions, 10 per basis, none already ``used``.

    ``used`` holds the (company, metric, basis) of every case drawn before. The pool
    is ``_pool`` over the metrics ``explanation.py`` covered then; no (company, metric)
    is drawn twice. Ids follow on from the first draw's.
    """
    facts = recorded_facts()
    quarterlies = latest_quarterlies()
    rng = random.Random(seed)
    pool = _pool(facts, quarterlies, SECOND_DRAW_METRICS)
    picked: list[tuple[str, str, ComparisonBase]] = []
    taken: set[tuple[str, str]] = set()
    for basis in BASES:
        open_pairs = [pair for pair in pool if (*pair, basis) not in used and pair not in taken]
        for cik, metric in rng.sample(open_pairs, HELD_OUT_COUNT // len(BASES)):
            picked.append((cik, metric, basis))
            taken.add((cik, metric))
    rng.shuffle(picked)
    templates = [rng.randrange(len(_TEMPLATES)) for _ in picked]
    return [
        _case(facts, quarterlies, f"e{HELD_OUT_FIRST_ID + index:02d}", SETS[1], pick, template)
        for index, (pick, template) in enumerate(zip(picked, templates, strict=True))
    ]


def draw_confirm(seed: int, used: Collection[tuple[str, str, str]]) -> list[ExplanationCase]:
    """The confirmation set: 20 year-over-year why questions, none already ``used``.

    The pool is ``_pool`` over the metrics ``explanation.py`` covers now. No company
    is drawn more than twice while the pool allows it. Ids follow on from the held-out set's.
    """
    return _draw_year_over_year(seed, used, CONFIRM_COUNT, CONFIRM_FIRST_ID, SETS[2])


def draw_final(seed: int, used: Collection[tuple[str, str, str]]) -> list[ExplanationCase]:
    """Phase B's final set: drawn as the confirmation set was, ids following on from it."""
    return _draw_year_over_year(seed, used, FINAL_COUNT, FINAL_FIRST_ID, SETS[3])


def _draw_year_over_year(
    seed: int, used: Collection[tuple[str, str, str]], count: int, first_id: int, split: str
) -> list[ExplanationCase]:
    facts = recorded_facts()
    quarterlies = latest_quarterlies()
    rng = random.Random(seed)
    basis: ComparisonBase = "year_over_year"
    pool = [
        pair
        for pair in _pool(facts, quarterlies, explained_metrics())
        if (*pair, basis) not in used
    ]
    rng.shuffle(pool)
    picked: list[tuple[str, str]] = []
    per_company: dict[str, int] = {}
    for cik, metric in pool:
        if len(picked) < count and per_company.get(cik, 0) < _MOST_PER_COMPANY:
            picked.append((cik, metric))
            per_company[cik] = per_company.get(cik, 0) + 1
    # Where the pool cannot spread them that far, the rest come in the shuffled order.
    picked += [pair for pair in pool if pair not in picked][: count - len(picked)]
    templates = [rng.randrange(len(_TEMPLATES)) for _ in picked]
    return [
        _case(
            facts,
            quarterlies,
            f"e{first_id + index:02d}",
            split,
            (cik, metric, basis),
            template,
        )
        for index, ((cik, metric), template) in enumerate(zip(picked, templates, strict=True))
    ]


def _triples(cases: Sequence[ExplanationCase]) -> set[tuple[str, str, str]]:
    return {(case.cik, case.metric, case.basis) for case in cases}


def evaluation_cases() -> list[ExplanationCase]:
    """The development set (the first draw's, with a metric covered in ticket 05), the
    fresh held-out set, the confirmation set and phase B's final set."""
    first = draw_cases(SEED)
    dev = [case for case in first if case.set == SETS[0] and case.metric in SECOND_DRAW_METRICS]
    used = _triples(first)
    held_out = draw_held_out(HELD_OUT_SEED, used)
    used |= _triples(held_out)
    confirm = draw_confirm(CONFIRM_SEED, used)
    used |= _triples(confirm)
    return dev + held_out + confirm + draw_final(FINAL_SEED, used)


def _company_name(facts: SecFactLookup, cik: str, report_date: str, metric: str) -> str:
    part = FORMULA_COMPONENTS.get(metric, (metric,))[0]
    fact = facts.get_financials(cik, part, report_date=date.fromisoformat(report_date))
    return short_name(fact.company_name)


def cases_payload(cases: Sequence[ExplanationCase]) -> dict[str, Any]:
    return {
        "seeds": {
            SETS[0]: SEED,
            SETS[1]: HELD_OUT_SEED,
            SETS[2]: CONFIRM_SEED,
            SETS[3]: FINAL_SEED,
        },
        "notes": CASES_NOTES,
        "cases": [asdict(case) for case in cases],
    }


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


def _places(html: str) -> dict[str, int]:
    """Each MD&A paragraph's place, by its text: a paragraph id is ``<case>-m<place>``."""
    places: dict[str, int] = {}
    for place, text in enumerate(section_paragraphs(extract_section(html, "mda"))):
        places.setdefault(text, place)
    return places


def _cause(paragraph: ExplainingParagraph) -> str | None:
    if paragraph.cause is None:
        return None
    return paragraph.text[paragraph.cause[0] : paragraph.cause[1]]


def _case_candidates(case: ExplanationCase) -> dict[str, Any]:
    html, url = _source(case)
    explanation = management_explanation(html, case.metric, case.basis, url)
    places = _places(html)
    paragraphs: list[dict[str, Any]] = []
    ids: dict[str, str] = {}

    def paragraph_id(text: str, cause: str | None) -> str:
        """Each distinct paragraph once, so the judge labels it once.

        Its id is its place in the MD&A, so a changed choice never gives a label to
        another paragraph (``carry_judgements`` moves labels across by text).
        """
        if text not in ids:
            ids[text] = f"{case.id}-m{places[text]}"
            paragraphs.append({"id": ids[text], "text": text, "cause": cause})
        return ids[text]

    scored = []
    for rank, chosen in enumerate(explanation.paragraphs, start=1):
        scored.append(
            {
                "paragraph": paragraph_id(chosen.text, _cause(chosen)),
                "rank": rank,
                "score": chosen.score,
            }
        )
    baseline = baseline_paragraph(html, case.metric)
    baseline_id = paragraph_id(baseline, None) if baseline is not None else None
    # Phase B's candidates, in the order the model sees them (ticket 07), so the judge
    # labels whichever the model chooses.
    offered = [
        paragraph_id(paragraph.text, _cause(paragraph))
        for paragraph in explanation_candidates(html, case.metric, case.basis, url)
    ]
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
        "baseline": baseline_id,
        "offered": offered,
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

    Only the cases the narrowed scope covers are counted (``covers``: year over year,
    a covered metric); ``outside_scope`` says how many of a set's are not. The sets
    are never added together: the earlier ones were read before the narrowing. A set
    none of whose cases has labels yet is reported as ``unjudged``.
    """
    by_case = labels["labels"]
    judged = labels.get("judgements", {})

    def company_wide(case_id: str, paragraph: str) -> bool:
        return _company_wide(by_case, judged, case_id, paragraph)

    summary: dict[str, Any] = {}
    for split in SETS:
        in_set = [entry for entry in candidates["cases"] if sets[entry["id"]] == split]
        if not in_set:
            continue
        entries = [entry for entry in in_set if covers(entry["metric"], entry["basis"])]
        if entries and not any(entry["id"] in by_case for entry in entries):
            summary[split] = {"unjudged": len(entries), "outside_scope": len(in_set) - len(entries)}
            continue
        scored: list[Sequence[bool] | None] = []
        strict: list[Sequence[bool] | None] = []
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
            strict.append([company_wide(case_id, pid) for pid in ranked])
            base = entry["baseline"]
            baseline.append([_explains(by_case, case_id, base)] if base else None)
            if ranked:
                text = next(p["text"] for p in entry["paragraphs"] if p["id"] == ranked[0])
                if is_about_another_metric(text, entry["metric"]):
                    firsts.append({"case": case_id, "metric": entry["metric"], "text": text})
        summary[split] = {
            "scoring": _tally(scored, empty),
            "scoring_strict": _tally(strict, empty),
            "baseline": _tally(baseline, empty),
            "other_metric_firsts": firsts,
            "outside_scope": len(in_set) - len(entries),
        }
    return summary


def _company_wide(
    by_case: Mapping[str, Any], judged: Mapping[str, Any], case_id: str, paragraph: str
) -> bool:
    """Strict: the judge's cause is for the company's figure, not a part of it.

    The confirm spot-check found "part" causes that moved the other way (a
    segment whose margin rose, given for a company margin that fell).
    """
    scope = judged.get(paragraph, {}).get("scope")
    return _explains(by_case, case_id, paragraph) and scope == "company"


# --- phase B: the model's answers (ticket 07) ----------------------------------------

# The tuning set is the earlier sets' in-scope cases; the final set is scored once.
MODEL_SETS: dict[str, tuple[str, ...]] = {"tuning": SETS[:3], "final": (SETS[3],)}
# Why an answer shows nothing although the model was asked: the analyst then reads
# NOT_FOUND_MESSAGE. "nothing_found" is the model's own answer, not a failure.
WITHHELD = ("quote_outside", "numeral_lock", "bad_choice", "unparseable")


def model_path(split: str) -> Path:
    """Where ``generate`` writes the model's answers for ``tuning`` or ``final``."""
    return EVALUATION / f"explanation-model-{split}.json"


def model_cases(split: str, cases: Sequence[ExplanationCase]) -> list[ExplanationCase]:
    """The in-scope cases (``covers``) of the sets ``split`` names."""
    return [
        case
        for case in cases
        if case.set in MODEL_SETS[split] and covers(case.metric, case.basis)
    ]


def instructions_version() -> str:
    """A short hash of ``EXPLANATION_INSTRUCTIONS``, so a result names the prompt it used."""
    return hashlib.sha256(EXPLANATION_INSTRUCTIONS.encode("utf-8")).hexdigest()[:12]


def model_answers(
    cases: Sequence[ExplanationCase], completer: EssayCompleter, model: str
) -> dict[str, Any]:
    """``model_explanation`` over each case, with paragraphs named by their candidates' ids."""
    answers = []
    for case in cases:
        html, url = _source(case)
        places = _places(html)
        asked = WhyQuestion(case.company, case.question, case.report_date, case.direction)
        result = model_explanation(html, case.metric, case.basis, url, completer, asked=asked)
        ids = {
            paragraph.text: f"{case.id}-m{places[paragraph.text]}"
            for paragraph in result.offered
        }
        answers.append(
            {
                "id": case.id,
                "set": case.set,
                "metric": case.metric,
                "basis": case.basis,
                "offered": [ids[paragraph.text] for paragraph in result.offered],
                "chosen": [
                    {"id": ids[paragraph.text], "text": paragraph.text}
                    for paragraph in result.paragraphs
                ],
                "explanation": result.explanation,
                "reason": result.reason,
                "failed": list(result.failed),
                "reply": result.reply,
            }
        )
    return {"model": model, "instructions": instructions_version(), "cases": answers}


def explanation_recordings() -> dict[str, Any]:
    """The model's answers from the evaluation runs, for the recorded runtime to replay.

    One per case the model was asked about, keyed by CIK, accession and metric, with a
    digest of the paragraphs it was offered: a replay checks the same numbered
    paragraphs are offered before it trusts the answer's numbers. The reply is kept
    raw, so the replay goes through the same checks a live answer does.
    """
    cases = {case.id: case for case in load_cases()}
    recordings = []
    models = []
    for split in MODEL_SETS:
        run = json.loads(model_path(split).read_text(encoding="utf-8"))
        models.append({"set": split, "model": run["model"], "instructions": run["instructions"]})
        for answer in run["cases"]:
            if not answer["offered"]:
                continue
            case = cases[answer["id"]]
            html, url = _source(case)
            offered = explanation_candidates(html, case.metric, case.basis, url)
            places = _places(html)
            ids = [f"{case.id}-m{places[paragraph.text]}" for paragraph in offered]
            if ids != answer["offered"]:
                raise ValueError(f"{case.id}: the candidates changed since the model's run")
            recordings.append(
                {
                    "case": case.id,
                    "company": case.company,
                    "cik": case.cik,
                    "accession": case.accession,
                    "metric": case.metric,
                    "offered": offered_digest(offered),
                    "reply": answer["reply"],
                }
            )
    return {"runs": models, "recordings": recordings}


def score_model(answers: Mapping[str, Any], labels: Mapping[str, Any]) -> dict[str, Any]:
    """The model's chosen paragraphs, scored as ``score`` scores phase A's.

    A withheld answer shows nothing, so it counts as "nothing found", as the analyst
    sees it; ``outcomes`` counts each case by its reason. A case whose chosen
    paragraphs, or whose MD&A, the judge has not labelled is left out of the tally
    and listed in ``unlabelled``, for ``judge`` to label.
    """
    by_case = labels["labels"]
    judged = labels.get("judgements", {})
    lenient: list[Sequence[bool] | None] = []
    strict: list[Sequence[bool] | None] = []
    empty: list[bool] = []
    unlabelled: list[dict[str, str]] = []
    outcomes: Counter[str] = Counter()
    for entry in answers["cases"]:
        case_id = entry["id"]
        outcomes[entry["reason"] or "shown"] += 1
        explains = by_case.get(case_id, {}).get("explains", {})
        missing = [
            {"case": case_id, "paragraph": chosen["id"]}
            for chosen in entry["chosen"]
            if chosen["id"] not in explains
        ]
        if case_id not in by_case:
            missing.append({"case": case_id, "paragraph": f"{case_id}-mda"})
        if missing:
            unlabelled += missing
            continue
        ids = [chosen["id"] for chosen in entry["chosen"]]
        empty.append(bool(by_case[case_id]["nothing_to_find"]))
        lenient.append([_explains(by_case, case_id, pid) for pid in ids])
        strict.append([_company_wide(by_case, judged, case_id, pid) for pid in ids])
    return {
        "model": answers.get("model"),
        "instructions": answers.get("instructions"),
        "answered": len(answers["cases"]),
        "scoring": _tally(lenient, empty),
        "scoring_strict": _tally(strict, empty),
        "outcomes": dict(sorted(outcomes.items())),
        "withheld": sum(outcomes[reason] for reason in WITHHELD),
        "unlabelled": unlabelled,
    }


_SET_SCOPES = {
    "dev": "Drawn under the wider scope and tuned on (ticket 05).",
    "held-out": "Drawn under the wider scope; read before the narrowing (ticket 06).",
    "confirm": "Drawn under the narrowed scope (ticket 06), unseen.",
    "final": "Drawn for phase B (ticket 07) under the narrowed scope; scored once.",
}


def _rate(hits: int, of: int) -> str:
    return f"{hits / of:.2f} ({hits} of {of})" if of else "n/a (0 of 0)"


def report_markdown(
    summary: Mapping[str, Any], *, judge: str, model: Mapping[str, Any] | None = None
) -> str:
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
        "about another metric. From the confirm set on, the bar is held against the strict "
        "row, which counts only causes the judge gave for the company's figure: the confirm "
        "spot-check found the judge counting a segment that moved the other way as \"part\" "
        "of the cause.",
        "",
        "Scope: phase A now covers year-over-year questions about amounts and gross margin "
        "(ticket 06). Only those cases are counted below. **The dev and held-out figures "
        "predate this narrowing:** both sets were drawn under the wider scope (margins, "
        "ratios and sequential questions), and the narrowing was chosen after reading the "
        "held-out set, so their figures on it are a hypothesis, not a result. The confirm "
        "set was drawn after the narrowing, from the narrowed scope, and is the measure.",
        "",
    ]
    for split, results in summary.items():
        under = _SET_SCOPES.get(split, "")
        if "scoring" not in results:
            drawn = results["unjudged"] + results["outside_scope"]
            lines += [
                f"## {split}",
                "",
                f"{under} Not judged yet: none of its {results['unjudged']} covered cases "
                f"(of {drawn}) has labels.",
                "",
            ]
            continue
        counted = results["scoring"]["cases"]
        drawn = counted + results["outside_scope"]
        lines += [
            f"## {split}",
            "",
            f"{under} Counted: {counted} of {drawn} cases; the rest are outside the "
            "narrowed scope.",
            "",
            *_table(
                results,
                {
                    "scoring": "scoring",
                    "scoring_strict": "scoring, company-wide causes only",
                    "baseline": "baseline",
                },
            ),
        ]
        lines += ["", "First-place paragraphs about another metric (by code's reading):", ""]
        firsts = results["other_metric_firsts"]
        if not firsts:
            lines.append("- None.")
        for first in firsts:
            text = " ".join(first["text"].split())
            lines.append(f"- {first['case']} ({first['metric']}): {text[:200]}")
        lines.append("")
    for split, results in (model or {}).items():
        lines += _model_section(split, results)
    return "\n".join(lines)


def _table(results: Mapping[str, Any], names: Mapping[str, str]) -> list[str]:
    lines = [
        "| Method | Shown | Precision at 1 | Precision at 3 | Nothing found right |",
        "| --- | --- | --- | --- | --- |",
    ]
    for method, name in names.items():
        if method not in results:
            continue
        tally = results[method]
        lines.append(
            f"| {name} | {tally['shown']} of {tally['cases']} "
            f"| {_rate(tally['at_1'], tally['shown'])} "
            f"| {_rate(tally['at_3'], tally['shown'])} "
            f"| {_rate(tally['nothing_found_right'], tally['nothing_found'])} |"
        )
    return lines


def _model_section(split: str, results: Mapping[str, Any]) -> list[str]:
    """Phase B's results for the tuning or the final set."""
    answered = results["answered"]
    counted = results["scoring"]["cases"]
    outcomes = ", ".join(f"{reason} {count}" for reason, count in results["outcomes"].items())
    lines = [
        f"## Phase B, {split}: {results['model']} chooses (ticket 07)",
        "",
        f"Instructions `{results['instructions']}`. {answered} in-scope cases answered; "
        f"{counted} counted, the rest wait for labels. A withheld answer shows nothing, so "
        "it counts as nothing found, as the analyst sees it.",
        "",
        *_table(
            results,
            {
                "scoring": "model",
                "scoring_strict": "model, company-wide causes only",
            },
        ),
        "",
        f"Outcomes: {outcomes or 'none'}. Withheld: {_rate(results['withheld'], answered)}.",
        "",
    ]
    unlabelled = results["unlabelled"]
    if unlabelled:
        lines += ["Not yet labelled (`judge` labels them):", ""]
        lines += [f"- {item['paragraph']} ({item['case']})" for item in unlabelled]
        lines.append("")
    return lines


# --- the judge's brief ---------------------------------------------------------------


def brief() -> str:
    """The judge's instructions: the rubric, without its history of changes."""
    text = RUBRIC_PATH.read_text(encoding="utf-8")
    return text.split("\n## Changes", 1)[0].strip()


PARAGRAPH_JUDGEMENT = "Judging one paragraph"
MDA_JUDGEMENT = "Judging the whole MD&A"
_SHARED_SECTIONS = ("What you are shown", "What counts as a cause")


def judgement_brief(judgement: str) -> str:
    """The rubric for one judgement: its opening, the shared standard and that judgement only.

    A prompt holds one question and one answer shape, so the judge never has to
    work out which of two applies.
    """
    opening, *blocks = re.split(r"^## ", brief(), flags=re.MULTILINE)
    sections = {}
    for block in blocks:
        heading, _, body = block.partition("\n")
        sections[heading.strip()] = f"## {heading.strip()}\n{body}".strip()
    chosen = [sections[name] for name in (*_SHARED_SECTIONS, judgement)]
    return "\n\n".join([opening.strip(), *chosen])


_BASIS_NAMES: dict[str, str] = {
    "year_over_year": "year over year (against the same quarter a year earlier)",
    "sequential": "sequential (against the quarter before)",
}


def paragraph_prompt(entry: Mapping[str, Any], paragraph: Mapping[str, Any]) -> str:
    """What the judge is shown to label one paragraph."""
    return "\n".join(
        [
            judgement_brief(PARAGRAPH_JUDGEMENT),
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
            judgement_brief(MDA_JUDGEMENT),
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


# --- the judge -----------------------------------------------------------------------

# Blake's choice for this evaluation (ticket 03).
JUDGE_MODEL = "claude-opus-5-5"
LABELS_PATH = EVALUATION / "explanation-labels.json"
_JUDGE_WORKERS = 6


def claude_judge(prompt: str) -> str:
    """One judgement from the ``claude`` CLI: no tools, in an empty directory, so no
    project instructions reach the judge, and a fresh context per prompt."""
    with tempfile.TemporaryDirectory() as empty:
        done = subprocess.run(
            ["claude", "-p", "--model", JUDGE_MODEL, "--tools", ""],
            input=prompt,
            capture_output=True,
            text=True,
            encoding="utf-8",
            cwd=empty,
            timeout=900,
        )
    if done.returncode != 0:
        raise RuntimeError(done.stderr[-500:] or done.stdout[-500:])
    return done.stdout


def _judgement(
    judge: Callable[[str], str], prompt: str, key: str, tries: int = 3
) -> dict[str, Any]:
    """The judge's JSON object, holding a boolean ``key``; retried on a malformed reply."""
    error: Exception | None = None
    for _ in range(tries):
        try:
            reply = parse_judgement(judge(prompt))
            if not isinstance(reply.get(key), bool):
                raise ValueError(f"{key} is not true or false: {reply!r}")
            return reply
        except (ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
            error = exc
    raise RuntimeError(f"judge failed {tries} times: {error}")


def judge_candidates(
    candidates: Mapping[str, Any],
    sources: Mapping[str, str],
    judge: Callable[[str], str],
    saved: Mapping[str, Any] | None = None,
    on_label: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    """Every paragraph and every case's MD&A, judged once each, in its own prompt.

    ``sources`` is each case's filing HTML by case id. ``saved`` holds judgements
    already made (a resumed run asks for none of them again); ``on_label`` gets the
    whole record after each new one, so a run can be saved as it goes.
    """
    record: dict[str, Any] = {
        "judge": JUDGE_MODEL,
        "judgements": dict((saved or {}).get("judgements", {})),
    }
    jobs: list[tuple[str, str, str]] = []
    for entry in candidates["cases"]:
        for paragraph in entry["paragraphs"]:
            jobs.append((paragraph["id"], paragraph_prompt(entry, paragraph), "explains"))
        whole = mda_prompt(entry, sources[entry["id"]])
        jobs.append((f"{entry['id']}-mda", whole, "nothing_to_find"))
    pending = [job for job in jobs if job[0] not in record["judgements"]]
    lock = threading.Lock()

    def run(job: tuple[str, str, str]) -> None:
        key, prompt, field = job
        reply = _judgement(judge, prompt, field)
        with lock:
            record["judgements"][key] = reply
            if on_label is not None:
                on_label(record)

    with ThreadPoolExecutor(max_workers=_JUDGE_WORKERS) as pool:
        list(pool.map(run, pending))
    record["labels"] = labels_from(candidates, record["judgements"])
    return record


def carry_judgements(
    previous: Mapping[str, Any], candidates: Mapping[str, Any], judgements: Mapping[str, Any]
) -> dict[str, Any]:
    """Judgements made on ``previous`` candidates, under the ids the same text has now.

    A judgement carries only within the same question (case id, metric, basis and
    filing): a paragraph's to the same text, and the MD&A's whole.
    """
    before = {entry["id"]: entry for entry in previous["cases"]}
    carried: dict[str, Any] = {}
    for entry in candidates["cases"]:
        old = before.get(entry["id"])
        if old is None or any(old[key] != entry[key] for key in ("metric", "basis", "accession")):
            continue
        whole = f"{entry['id']}-mda"
        if whole in judgements:
            carried[whole] = judgements[whole]
        old_ids = {paragraph["text"]: paragraph["id"] for paragraph in old["paragraphs"]}
        for paragraph in entry["paragraphs"]:
            old_id = old_ids.get(paragraph["text"])
            if old_id is not None and old_id in judgements:
                carried[paragraph["id"]] = judgements[old_id]
    return carried


def labels_from(candidates: Mapping[str, Any], judgements: Mapping[str, Any]) -> dict[str, Any]:
    """The judgements in the shape ``score`` reads."""
    return {
        entry["id"]: {
            "nothing_to_find": bool(judgements[f"{entry['id']}-mda"]["nothing_to_find"]),
            "explains": {
                paragraph["id"]: bool(judgements[paragraph["id"]]["explains"])
                for paragraph in entry["paragraphs"]
            },
        }
        for entry in candidates["cases"]
    }


def spot_check(record: Mapping[str, Any], count: int = 10, seed: int = SEED) -> list[str]:
    """The paragraph judgements a person checks, drawn with a fixed seed."""
    keys = sorted(key for key in record["judgements"] if not key.endswith("-mda"))
    return sorted(random.Random(seed).sample(keys, min(count, len(keys))))


# --- command line --------------------------------------------------------------------


def _model_completer(model: str | None) -> tuple[EssayCompleter, str]:
    """The phase B completer from the settings: the app's OpenAI client, essay model and
    daily spend cap (its budget and spend file), so a run counts against the same day."""
    settings = get_settings()
    name = model or settings.essay_model()
    return explanation_completer(settings, model=name), name


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
    jud = sub.add_parser("judge", help=f"label every candidate with {JUDGE_MODEL} (a paid run)")
    jud.add_argument(
        "--carry-from",
        type=Path,
        help="the candidates the saved labels were made on; their labels carry by text",
    )
    gen = sub.add_parser(
        "generate", help="phase B: the essay model chooses and explains (a paid run)"
    )
    gen.add_argument(
        "--model",
        nargs="?",
        const="",
        default="",
        help="the OpenAI model; the app's essay model when no name is given",
    )
    gen.add_argument("--set", dest="split", choices=tuple(MODEL_SETS), required=True)
    sub.add_parser(
        "recordings", help="copy the model's answers for the recorded runtime to replay"
    )
    args = parser.parse_args(argv)

    if args.command == "recordings":
        recordings = explanation_recordings()
        _write_json(RECORDINGS_OUT, recordings)
        print(f"wrote {len(recordings['recordings'])} recorded answers -> {RECORDINGS_OUT}")
        return

    if args.command == "generate":
        cases = model_cases(args.split, load_cases())
        completer, model = _model_completer(args.model or None)
        answers = model_answers(cases, completer, model)
        _write_json(model_path(args.split), answers)
        outcomes = Counter(entry["reason"] or "shown" for entry in answers["cases"])
        print(f"{len(cases)} {args.split} cases -> {model_path(args.split)}: {dict(outcomes)}")
        return
    if args.command == "judge":
        candidates = json.loads(CANDIDATES_PATH.read_text(encoding="utf-8"))
        by_id = {case.id: case for case in load_cases()}
        sources = {entry["id"]: _source(by_id[entry["id"]])[0] for entry in candidates["cases"]}
        saved = (
            json.loads(LABELS_PATH.read_text(encoding="utf-8")) if LABELS_PATH.exists() else None
        )
        if saved is not None and args.carry_from is not None:
            previous = json.loads(args.carry_from.read_text(encoding="utf-8"))
            saved = {"judgements": carry_judgements(previous, candidates, saved["judgements"])}
        record = judge_candidates(
            candidates, sources, claude_judge, saved, lambda done: _write_json(LABELS_PATH, done)
        )
        record["spot_check"] = spot_check(record)
        _write_json(LABELS_PATH, record)
        print(f"{len(record['judgements'])} judgements -> {LABELS_PATH}")
        return

    if args.command == "cases":
        cases = evaluation_cases()
        _write_json(CASES_PATH, cases_payload(cases))
        moved = sum(case.direction is not None for case in cases)
        print(
            f"wrote {len(cases)} cases (seeds {SEED}, {HELD_OUT_SEED}, {CONFIRM_SEED}, "
            f"{FINAL_SEED}); "
            f"{moved} with a recorded direction"
        )
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
        phase_b = {
            split: score_model(json.loads(model_path(split).read_text(encoding="utf-8")), labels)
            for split in MODEL_SETS
            if model_path(split).exists()
        }
        judge = str(labels.get("judge", "an unnamed judge"))
        REPORT_PATH.write_text(
            report_markdown(summary, judge=judge, model=phase_b) + "\n", encoding="utf-8"
        )
        tallies = {split: result.get("scoring", "unjudged") for split, result in summary.items()}
        tallies |= {f"model-{split}": result["scoring"] for split, result in phase_b.items()}
        print(json.dumps(tallies))
        unlabelled = [item for result in phase_b.values() for item in result["unlabelled"]]
        if unlabelled:
            print(f"{len(unlabelled)} chosen paragraphs or MD&As have no label; run `judge`.")


if __name__ == "__main__":
    main()
