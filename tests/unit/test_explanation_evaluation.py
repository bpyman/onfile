"""The explanation evaluation: cases drawn by code, candidates, and the score over judge labels."""

import json
from collections import Counter
from decimal import Decimal

import pytest

from financial_analyst_agent import explanation_evaluation as ev


@pytest.fixture(scope="module")
def drawn() -> list[ev.ExplanationCase]:
    return ev.draw_cases(ev.SEED)


def test_the_draw_is_reproducible_from_the_seed(drawn: list[ev.ExplanationCase]) -> None:
    assert ev.draw_cases(ev.SEED) == drawn
    assert ev.draw_cases(ev.SEED + 1) != drawn


def test_the_committed_cases_are_the_draw_from_their_seed(
    drawn: list[ev.ExplanationCase],
) -> None:
    committed = json.loads(ev.CASES_PATH.read_text(encoding="utf-8"))
    assert committed["seed"] == ev.SEED
    assert ev.load_cases() == drawn


def test_forty_cases_split_evenly_by_set_and_basis(drawn: list[ev.ExplanationCase]) -> None:
    assert len(drawn) == 40
    assert len({(case.cik, case.metric) for case in drawn}) == 40
    assert Counter(case.set for case in drawn) == {"dev": 20, "held-out": 20}
    assert Counter((case.set, case.basis) for case in drawn) == {
        ("dev", "year_over_year"): 10,
        ("dev", "sequential"): 10,
        ("held-out", "year_over_year"): 10,
        ("held-out", "sequential"): 10,
    }


def test_every_case_is_a_metric_with_words_and_a_recorded_latest_10q(
    drawn: list[ev.ExplanationCase],
) -> None:
    documents = ev.recorded_documents()
    for case in drawn:
        assert case.metric in ev.explained_metrics()
        assert f"{case.cik}:{case.accession}:{case.document}" in documents
        assert case.latest is not None


def test_no_question_contradicts_the_recorded_direction(drawn: list[ev.ExplanationCase]) -> None:
    for case in drawn:
        words = set(case.question.rstrip("?").split())
        if case.direction == "rose":
            assert {"rise", "up"} & words and not {"fall", "down"} & words, case.question
        elif case.direction == "fell":
            assert {"fall", "down"} & words and not {"rise", "up"} & words, case.question
        else:
            assert not {"rise", "up", "fall", "down"} & words, case.question
        if case.compared is not None and case.latest is not None:
            latest, compared = Decimal(case.latest.value), Decimal(case.compared.value)
            expected = "rose" if latest > compared else "fell" if latest < compared else None
            assert case.direction == expected, case.id


def test_the_direction_is_the_recorded_figures(drawn: list[ev.ExplanationCase]) -> None:
    facts = ev.recorded_facts()
    for case in drawn:
        moved = ev.figure_move(facts, case.cik, case.metric, case.report_date, case.basis)
        latest, compared = moved
        assert latest == case.latest
        assert compared == case.compared


def test_questions_name_the_basis() -> None:
    assert ev.question_for("Apple", "gross_margin", "year_over_year", "rose", 0) == (
        "Why did Apple's gross margin rise year over year last quarter?"
    )
    assert ev.question_for("Micron", "revenue", "sequential", "fell", 1) == (
        "What drove Micron's revenue down sequentially this quarter?"
    )
    assert ev.question_for("Pfizer", "capital_expenditure", "sequential", "rose", 2) == (
        "What caused Pfizer's capital spending to rise sequentially last quarter?"
    )
    assert ev.question_for("AMD", "net_income", "year_over_year", None, 2) == (
        "What drove the change in AMD's net income year over year this quarter?"
    )


def test_candidates_are_offline_deterministic_and_committed() -> None:
    cases = ev.load_cases()
    built = ev.build_candidates(cases)
    assert built == ev.build_candidates(cases)
    committed = json.loads(ev.CANDIDATES_PATH.read_text(encoding="utf-8"))
    assert committed == json.loads(json.dumps(built))
    for entry in built["cases"]:
        ids = {paragraph["id"] for paragraph in entry["paragraphs"]}
        assert len(entry["scored"]) <= 3
        assert {rank["paragraph"] for rank in entry["scored"]} <= ids
        assert entry["baseline"] is None or entry["baseline"] in ids


def _candidate(case_id: str, scored: list[str], baseline: str | None) -> dict[str, object]:
    ids = sorted({*scored, *([baseline] if baseline else [])})
    return {
        "id": case_id,
        "metric": "gross_margin",
        "paragraphs": [{"id": pid, "text": f"Gross margin rose. ({pid})"} for pid in ids],
        "scored": [
            {"paragraph": pid, "rank": n + 1, "score": 10 - n} for n, pid in enumerate(scored)
        ],
        "baseline": baseline,
    }


def test_score_computes_precision_at_one_and_three() -> None:
    sets = {"a": "dev", "b": "dev", "c": "dev", "d": "dev", "e": "held-out"}
    candidates = {
        "cases": [
            _candidate("a", ["a1", "a2", "a3"], "a1"),  # first explains
            _candidate("b", ["b1", "b2", "b3"], "b9"),  # third explains; baseline does not
            _candidate("c", ["c1"], "c1"),  # nothing explains
            _candidate("d", [], None),  # nothing shown, and nothing to find
            _candidate("e", [], "e9"),  # nothing shown, but there was a cause to find
        ]
    }
    labels = {
        "labels": {
            "a": {"nothing_to_find": False, "explains": {"a1": True, "a2": False, "a3": True}},
            "b": {
                "nothing_to_find": False,
                "explains": {"b1": False, "b2": False, "b3": True, "b9": False},
            },
            "c": {"nothing_to_find": True, "explains": {"c1": False}},
            "d": {"nothing_to_find": True, "explains": {}},
            "e": {"nothing_to_find": False, "explains": {"e9": True}},
        }
    }
    summary = ev.score(candidates, labels, sets)
    dev = summary["dev"]
    assert dev["scoring"]["shown"] == 3
    assert dev["scoring"]["at_1"] == 1
    assert dev["scoring"]["at_3"] == 2
    assert dev["scoring"]["nothing_found"] == 1
    assert dev["scoring"]["nothing_found_right"] == 1
    assert dev["baseline"]["shown"] == 3
    assert dev["baseline"]["at_1"] == 1
    assert dev["baseline"]["at_3"] == 1
    held_out = summary["held-out"]
    assert held_out["scoring"]["nothing_found"] == 1
    assert held_out["scoring"]["nothing_found_right"] == 0
    assert held_out["baseline"]["at_1"] == 1
    assert summary["all"]["scoring"]["shown"] == 3
    assert summary["all"]["scoring"]["nothing_found"] == 2


def test_score_needs_a_label_for_every_paragraph_shown() -> None:
    candidates = {"cases": [_candidate("a", ["a1", "a2"], "a1")]}
    labels = {"labels": {"a": {"nothing_to_find": False, "explains": {"a1": True}}}}
    with pytest.raises(ValueError, match="a2"):
        ev.score(candidates, labels, {"a": "dev"})


def test_the_report_lists_first_places_about_another_metric() -> None:
    entry = _candidate("a", ["a1"], "a1")
    entry["paragraphs"] = [
        {
            "id": "a1",
            "text": (
                "Operating income rose. The increase in operating income was due to gross profit."
            ),
        }
    ]
    labels = {"labels": {"a": {"nothing_to_find": False, "explains": {"a1": False}}}}
    summary = ev.score({"cases": [entry]}, labels, {"a": "dev"})
    assert [first["case"] for first in summary["dev"]["other_metric_firsts"]] == ["a"]
    report = ev.report_markdown(summary, judge="test")
    assert "Operating income rose." in report
    assert "Precision at 1" in report


def test_the_brief_is_the_rubric_and_names_the_json_shape() -> None:
    brief = ev.brief()
    assert "equity analyst" in brief
    assert '"explains"' in brief
    assert '"nothing_to_find"' in brief
    assert "## Changes" not in brief


def test_the_prompts_show_the_case_and_only_the_text_judged() -> None:
    entry = json.loads(ev.CANDIDATES_PATH.read_text(encoding="utf-8"))["cases"][0]
    paragraph = entry["paragraphs"][0]
    prompt = ev.paragraph_prompt(entry, paragraph)
    # One judgement per prompt: the shared standard and its own question and answer shape.
    assert prompt.startswith(ev.judgement_brief(ev.PARAGRAPH_JUDGEMENT))
    assert "## What counts as a cause" in prompt
    assert ev.MDA_JUDGEMENT not in prompt and "nothing_to_find" not in prompt
    mda = ev.mda_prompt(entry, "<html></html>")
    assert ev.PARAGRAPH_JUDGEMENT not in mda and '"explains"' not in mda
    assert "## What counts as a cause" in mda
    assert entry["question"] in prompt and paragraph["text"] in prompt
    others = [p["text"] for p in entry["paragraphs"][1:] if p["text"] not in paragraph["text"]]
    assert not any(text in prompt for text in others)
    html = "<html><body><div>Item 1. Financial Statements</div></body></html>"
    assert "(no MD&A text was found)" in ev.mda_prompt(entry, html)


def test_the_judge_labels_every_paragraph_and_mda_once_and_resumes() -> None:
    candidates = {
        "cases": [
            {
                "id": "a",
                "question": "Why?",
                "company": "Apple",
                "metric": "gross_margin",
                "basis": "year_over_year",
                "report_date": "2026-06-27",
                "paragraphs": [
                    {"id": "a-p1", "text": "Gross margin rose due to mix."},
                    {"id": "a-p2", "text": "Gross margin rose."},
                ],
            }
        ]
    }
    asked: list[str] = []
    failures = iter([True])

    def fake(prompt: str) -> str:
        asked.append(prompt)
        if "MD&A to judge" in prompt:
            return 'Here: {"nothing_to_find": false, "where": "Gross margin rose", "reason": "x"}'
        if next(failures, False):
            return "not JSON"  # retried
        explains = "due to mix" in prompt
        return json.dumps({"explains": explains, "scope": "company", "reason": "x"})

    saved: list[dict[str, object]] = []
    record = ev.judge_candidates(candidates, {"a": "<html></html>"}, fake, None, saved.append)
    assert record["judge"] == ev.JUDGE_MODEL
    assert record["labels"] == {
        "a": {"nothing_to_find": False, "explains": {"a-p1": True, "a-p2": False}}
    }
    assert len(saved) == 3
    # A resumed run asks for nothing it already has.
    asked.clear()
    again = ev.judge_candidates(candidates, {"a": "<html></html>"}, fake, record)
    assert asked == [] and again["labels"] == record["labels"]
    assert ev.spot_check(record, count=1) in (["a-p1"], ["a-p2"])
