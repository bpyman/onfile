"""The explanation evaluation: cases drawn by code, candidates, and the score over judge labels."""

import json
from collections import Counter
from decimal import Decimal
from pathlib import Path

import pytest

from financial_analyst_agent import explanation_evaluation as ev


@pytest.fixture(scope="module")
def first() -> list[ev.ExplanationCase]:
    return ev.draw_cases(ev.SEED)


@pytest.fixture(scope="module")
def drawn() -> list[ev.ExplanationCase]:
    return ev.evaluation_cases()


def _triples(cases: list[ev.ExplanationCase]) -> set[tuple[str, str, str]]:
    return {(case.cik, case.metric, case.basis) for case in cases}


def test_the_first_draw_is_reproducible_from_its_seed(first: list[ev.ExplanationCase]) -> None:
    assert ev.draw_cases(ev.SEED) == first
    assert ev.draw_cases(ev.SEED + 1) != first
    assert len(first) == 40
    assert len({(case.cik, case.metric) for case in first}) == 40
    assert Counter((case.set, case.basis) for case in first) == {
        ("dev", "year_over_year"): 10,
        ("dev", "sequential"): 10,
        ("held-out", "year_over_year"): 10,
        ("held-out", "sequential"): 10,
    }


def test_the_development_set_is_the_first_draws_with_a_covered_metric(
    first: list[ev.ExplanationCase], drawn: list[ev.ExplanationCase]
) -> None:
    dev = [case for case in drawn if case.set == "dev"]
    # Covered when the development set was fixed (ticket 05), not now: it stays as it was.
    assert dev == [
        case for case in first if case.set == "dev" and case.metric in ev.SECOND_DRAW_METRICS
    ]
    assert len(dev) == 16


def test_the_fresh_held_out_draw_is_reproducible_and_unseen(
    first: list[ev.ExplanationCase], drawn: list[ev.ExplanationCase]
) -> None:
    held_out = [case for case in drawn if case.set == "held-out"]
    assert ev.draw_held_out(ev.HELD_OUT_SEED, _triples(first)) == held_out
    assert ev.draw_held_out(ev.HELD_OUT_SEED + 1, _triples(first)) != held_out
    # Nothing in either half of the first draw, whatever its basis split.
    assert not _triples(held_out) & _triples(first)
    assert len(held_out) == 20
    assert len({(case.cik, case.metric) for case in held_out}) == 20
    assert Counter(case.basis for case in held_out) == {"year_over_year": 10, "sequential": 10}
    # Fresh ids: no label from the first held-out half can attach to a new case.
    assert not {case.id for case in held_out} & {case.id for case in first}


def test_the_confirm_draw_is_reproducible_year_over_year_covered_and_unseen(
    first: list[ev.ExplanationCase], drawn: list[ev.ExplanationCase]
) -> None:
    earlier = [case for case in drawn if case.set != "confirm"]
    held_out = [case for case in earlier if case.set == "held-out"]
    used = _triples(first) | _triples(held_out)
    confirm = [case for case in drawn if case.set == "confirm"]
    assert ev.draw_confirm(ev.CONFIRM_SEED, used) == confirm
    assert ev.draw_confirm(ev.CONFIRM_SEED + 1, used) != confirm
    assert len(confirm) == 20
    assert {case.basis for case in confirm} == {"year_over_year"}
    assert {case.metric for case in confirm} <= set(ev.explained_metrics())
    # Nothing from the first draw (both halves) or the second held-out draw.
    assert not _triples(confirm) & used
    assert len(_triples(confirm)) == 20
    assert max(Counter(case.cik for case in confirm).values()) <= 2
    assert not {case.id for case in confirm} & {case.id for case in [*first, *held_out]}


def test_the_final_draw_is_reproducible_year_over_year_covered_and_unseen(
    first: list[ev.ExplanationCase], drawn: list[ev.ExplanationCase]
) -> None:
    # Counts, metrics, companies and overlap only: the final cases' paragraphs are not read.
    earlier = [case for case in drawn if case.set in ("held-out", "confirm")]
    used = _triples(first) | _triples(earlier)
    final = [case for case in drawn if case.set == "final"]
    assert ev.FINAL_SEED == 20261111
    assert ev.draw_final(ev.FINAL_SEED, used) == final
    assert ev.draw_final(ev.FINAL_SEED + 1, used) != final
    assert len(final) == 20
    assert {case.basis for case in final} == {"year_over_year"}
    assert {case.metric for case in final} <= set(ev.explained_metrics())
    assert not _triples(final) & used
    assert len(_triples(final)) == 20
    assert max(Counter(case.cik for case in final).values()) <= 2
    assert [case.id for case in final] == [f"e{number}" for number in range(81, 101)]
    assert not {case.id for case in final} & {case.id for case in [*first, *earlier]}


def test_the_model_sets_are_the_in_scope_cases(drawn: list[ev.ExplanationCase]) -> None:
    tuning = ev.model_cases("tuning", drawn)
    final = ev.model_cases("final", drawn)
    assert len(tuning) == 32
    assert {case.set for case in tuning} == {"dev", "held-out", "confirm"}
    assert len(final) == 20
    assert all(ev.covers(case.metric, case.basis) for case in [*tuning, *final])


def test_the_committed_cases_are_the_draws_from_their_seeds(
    drawn: list[ev.ExplanationCase],
) -> None:
    committed = json.loads(ev.CASES_PATH.read_text(encoding="utf-8"))
    assert committed["seeds"] == {
        "dev": ev.SEED,
        "held-out": ev.HELD_OUT_SEED,
        "confirm": ev.CONFIRM_SEED,
        "final": 20261111,
    }
    assert "leave the evaluation" in committed["notes"]
    assert ev.load_cases() == drawn


def test_every_case_is_a_metric_with_words_and_a_recorded_latest_10q(
    drawn: list[ev.ExplanationCase],
) -> None:
    documents = ev.recorded_documents()
    for case in drawn:
        narrowed = case.set in ("confirm", "final")
        covered = ev.explained_metrics() if narrowed else ev.SECOND_DRAW_METRICS
        assert case.metric in covered
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
        # Phase B's candidates are labelled too, in the order the model sees them.
        assert len(entry["offered"]) <= 8
        assert set(entry["offered"]) <= ids
        assert {rank["paragraph"] for rank in entry["scored"]} <= set(entry["offered"])
        places = [int(pid.rsplit("-m", 1)[1]) for pid in entry["offered"]]
        assert places == sorted(places)
        if not ev.covers(entry["metric"], entry["basis"]):
            assert entry["offered"] == []


def test_a_paragraph_id_is_its_place_in_the_mda() -> None:
    case = ev.load_cases()[0]
    entry = ev.build_candidates([case])["cases"][0]
    html, _ = ev._source(case)
    paragraphs = ev.section_paragraphs(ev.extract_section(html, "mda"))
    assert entry["paragraphs"]
    for paragraph in entry["paragraphs"]:
        index = int(paragraph["id"].removeprefix(f"{case.id}-m"))
        assert paragraphs[index] == paragraph["text"]


def test_judgements_carry_only_to_the_same_text_of_the_same_case() -> None:
    def entry(case_id: str, basis: str, **texts: str) -> dict[str, object]:
        paragraphs = [{"id": pid, "text": text} for pid, text in texts.items()]
        question = {"metric": "revenue", "basis": basis, "accession": "1"}
        return {"id": case_id, **question, "paragraphs": paragraphs}

    previous = {
        "cases": [
            entry("a", "sequential", **{"a-p1": "X", "a-p2": "Y"}),
            entry("b", "sequential", **{"b-p1": "W"}),
        ]
    }
    candidates = {
        "cases": [
            entry("a", "sequential", **{"a-m4": "Y", "a-m9": "Z"}),
            # The same id, but another question: nothing carries.
            entry("b", "year_over_year", **{"b-m1": "W"}),
        ]
    }
    judgements = {
        "a-p1": {"explains": False},
        "a-p2": {"explains": True},
        "a-mda": {"nothing_to_find": False},
        "b-p1": {"explains": True},
        "b-mda": {"nothing_to_find": True},
    }
    carried = ev.carry_judgements(previous, candidates, judgements)
    assert carried == {"a-m4": {"explains": True}, "a-mda": {"nothing_to_find": False}}


def _candidate(case_id: str, scored: list[str], baseline: str | None) -> dict[str, object]:
    ids = sorted({*scored, *([baseline] if baseline else [])})
    return {
        "id": case_id,
        "metric": "gross_margin",
        "basis": "year_over_year",
        "paragraphs":[{"id": pid, "text": f"Gross margin rose. ({pid})"} for pid in ids],
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
    # Seen sets and the unseen confirm set are never added together.
    assert "all" not in summary


def test_score_reports_confirm_beside_the_earlier_sets_and_counts_only_the_covered() -> None:
    sequential = _candidate("b", [], "b9") | {"basis": "sequential"}
    net_margin = _candidate("c", [], None) | {"metric": "net_margin"}
    candidates = {
        "cases": [_candidate("a", ["a1"], "a1"), sequential, net_margin, _candidate("d", [], None)]
    }
    labels = {
        "labels": {
            "a": {"nothing_to_find": False, "explains": {"a1": True}},
            "b": {"nothing_to_find": False, "explains": {"b9": True}},
            "c": {"nothing_to_find": False, "explains": {}},
            "d": {"nothing_to_find": True, "explains": {}},
        }
    }
    sets = {"a": "dev", "b": "dev", "c": "held-out", "d": "confirm"}
    summary = ev.score(candidates, labels, sets)
    assert list(summary) == ["dev", "held-out", "confirm"]
    # The sequential case and the net margin case are outside the narrowed scope.
    assert summary["dev"]["scoring"]["cases"] == 1
    assert summary["dev"]["outside_scope"] == 1
    assert summary["held-out"]["scoring"]["cases"] == 0
    assert summary["held-out"]["outside_scope"] == 1
    assert summary["confirm"]["scoring"]["nothing_found_right"] == 1
    report = ev.report_markdown(summary, judge="test")
    assert "predate" in report.split("## dev")[0]
    assert "## confirm" in report
    assert "1 of 2 cases" in report.split("## dev")[1].split("## held-out")[0]


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


def test_a_set_with_no_labels_yet_is_reported_unjudged() -> None:
    candidates = {"cases": [_candidate("a", ["a1"], "a1"), _candidate("f", ["f1"], None)]}
    labels = {"labels": {"a": {"nothing_to_find": False, "explains": {"a1": True}}}}
    summary = ev.score(candidates, labels, {"a": "confirm", "f": "final"})
    assert summary["confirm"]["scoring"]["at_1"] == 1
    assert summary["final"] == {"unjudged": 1, "outside_scope": 0}
    report = ev.report_markdown(summary, judge="test")
    assert "Not judged yet" in report.split("## final")[1]


def _answer(case_id: str, chosen: list[str], reason: str | None) -> dict[str, object]:
    return {
        "id": case_id,
        "set": "dev",
        "metric": "revenue",
        "basis": "year_over_year",
        "offered": chosen,
        "chosen": [{"id": pid, "text": f"Revenue rose. ({pid})"} for pid in chosen],
        "explanation": "",
        "reason": reason,
        "failed": [],
        "reply": "",
    }


def test_the_models_choice_is_scored_like_phase_as_and_withheld_counts_as_nothing() -> None:
    answers = {
        "model": "fake",
        "instructions": "abc",
        "cases": [
            _answer("a", ["a2", "a1"], None),  # the second chosen explains
            _answer("b", [], "quote_outside"),  # withheld, and there was a cause
            _answer("c", [], "nothing_found"),  # right: nothing to find
            _answer("d", ["d7"], None),  # d7 is not labelled yet
            _answer("e", [], "numeral_lock"),  # the case is not judged at all
        ],
    }
    labels = {
        "labels": {
            "a": {"nothing_to_find": False, "explains": {"a1": True, "a2": False}},
            "b": {"nothing_to_find": False, "explains": {}},
            "c": {"nothing_to_find": True, "explains": {}},
            "d": {"nothing_to_find": False, "explains": {"d1": True}},
        },
        "judgements": {"a1": {"scope": "part"}, "a2": {"scope": "company"}},
    }
    result = ev.score_model(answers, labels)
    assert result["scoring"] == {
        "cases": 3,
        "shown": 1,
        "at_1": 0,
        "at_3": 1,
        "nothing_found": 2,
        "nothing_found_right": 1,
    }
    # Strict counts only company-wide causes: a1's cause is a part's.
    assert result["scoring_strict"]["at_3"] == 0
    assert result["outcomes"] == {
        "nothing_found": 1,
        "numeral_lock": 1,
        "quote_outside": 1,
        "shown": 2,
    }
    assert result["withheld"] == 2
    assert result["unlabelled"] == [
        {"case": "d", "paragraph": "d7"},
        {"case": "e", "paragraph": "e-mda"},
    ]
    summary = ev.score({"cases": []}, labels, {})
    report = ev.report_markdown(summary, judge="test", model={"tuning": result})
    section = report.split("## Phase B, tuning")[1]
    assert "| model | 1 of 3 | 0.00 (0 of 1) | 1.00 (1 of 1) | 0.50 (1 of 2) |" in section
    assert "Withheld: 0.40 (2 of 5)" in section
    assert "- d7 (d)" in section and "- e-mda (e)" in section


class _FakeCompleter:
    """Chooses the first candidate, with an explanation that quotes nothing."""

    def __init__(self) -> None:
        self.asked = 0

    def complete_essay(self, query: str, tool_json: str = "") -> str:
        self.asked += 1
        return json.dumps({"paragraphs": [1], "explanation": "Management gives a cause."})


def test_generate_runs_offline_with_a_fake_completer(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    fake = _FakeCompleter()
    monkeypatch.setattr(ev, "_model_completer", lambda model: (fake, model or "fake-model"))
    monkeypatch.setattr(ev, "EVALUATION", tmp_path)
    ev.main(["generate", "--model", "--set", "tuning"])
    written = json.loads((tmp_path / "explanation-model-tuning.json").read_text(encoding="utf-8"))
    assert written["model"] == "fake-model"
    assert written["instructions"] == ev.instructions_version()
    tuning = ev.model_cases("tuning", ev.load_cases())
    assert [entry["id"] for entry in written["cases"]] == [case.id for case in tuning]
    candidates = {
        entry["id"]: entry
        for entry in json.loads(ev.CANDIDATES_PATH.read_text(encoding="utf-8"))["cases"]
    }
    asked = 0
    for entry in written["cases"]:
        offered = candidates[entry["id"]]["offered"]
        assert entry["offered"] == offered
        if offered:
            asked += 1
            assert entry["reason"] is None
            assert [chosen["id"] for chosen in entry["chosen"]] == offered[:1]
        else:
            assert entry["reason"] == "not_discussed" and entry["chosen"] == []
    assert fake.asked == asked > 0
