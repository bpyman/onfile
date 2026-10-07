"""A newer held-out set: the older is development data; the set is scored by writer and overlap."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from financial_analyst_agent import planner_evaluation
from financial_analyst_agent.held_out_overlap import _company_words, label_agreement, template
from financial_analyst_agent.planner_evaluation import (
    Observation,
    load_cases,
    protocol,
    scored_run,
    scores,
)


def _case(case_id: str, question: str, **extra: Any) -> dict[str, Any]:
    return {
        "id": case_id,
        "split": "held_out",
        "category": "lookup",
        "turns": [question],
        "expect": {"outcome": "answer", "tickers": ["AAPL"]},
        **extra,
    }


def _write(path: Path, cases: list[dict[str, Any]], **extra: Any) -> Path:
    path.write_text(json.dumps({"about": "test", "cases": cases, **extra}), encoding="utf-8")
    return path


@pytest.fixture
def two_sets(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    monkeypatch.setattr(planner_evaluation, "EVALUATION_DIR", tmp_path)
    fourth = _write(tmp_path / "planner-cases-held-out-4.json", [_case("h4_a", "Apple revenue")])
    fifth = _write(
        tmp_path / "planner-cases-held-out-5.json",
        [
            _case("h5_grok", "apple sales please", writer="grok-4.7-high"),
            _case("h5_claude", "Apple revenue last 4 quarters"),
        ],
        writer="claude",
    )
    (tmp_path / "held-out-5-overlap.json").write_text(
        json.dumps({"familiar": [{"id": "h5_claude"}]}), encoding="utf-8"
    )
    return fourth, fifth


def test_an_older_held_out_set_is_development_data_once_a_newer_exists(
    two_sets: tuple[Path, Path],
) -> None:
    cases = {case.case_id: case for case in load_cases(*two_sets)}

    assert planner_evaluation.current_held_out().number == 5
    assert cases["h4_a"].split == "dev"
    assert cases["h5_grok"].split == "held_out"
    # A case's own writer wins over its file's.
    assert cases["h5_grok"].writer == "grok-4.7-high"
    assert cases["h5_claude"].writer == "claude"
    assert (cases["h5_claude"].familiar, cases["h5_grok"].familiar) == (True, False)
    assert cases["h4_a"].familiar is None


def test_the_held_out_set_is_scored_by_writer_and_familiarity(
    two_sets: tuple[Path, Path],
) -> None:
    cases = [case for case in load_cases(*two_sets) if case.split == "held_out"]
    right = Observation(
        "answer", "lookup", frozenset({"AAPL"}), frozenset(), ("latest_quarter", None), frozenset()
    )
    wrong = Observation(
        "refuse", "lookup", frozenset(), frozenset(), ("latest_quarter", None), frozenset()
    )
    by_id = {case.case_id: case for case in cases}
    results = [scored_run(by_id["h5_grok"], 0, right), scored_run(by_id["h5_claude"], 0, wrong)]

    groups = scores(cases, results)["held_out_groups"]

    assert groups["written by grok-4.7-high"] == {"cases": 1, "accuracy": 1.0}
    assert groups["written by claude"] == {"cases": 1, "accuracy": 0.0}
    assert groups["familiar"]["accuracy"] == 0.0
    assert groups["novel"]["accuracy"] == 1.0


def test_the_protocol_names_the_set_held_out() -> None:
    fourth = "\n".join(protocol(4, 66))
    fifth = "\n".join(protocol(5, 160))

    assert "66), the held-out split here." in fourth
    assert "Fifth set" not in fourth
    assert "development data since" in fifth
    assert "5. **Fifth set**" in fifth and "160), the held-out split here." in fifth
    assert "160 cases detect only large" in fifth


def test_a_template_replaces_companies_and_numbers() -> None:
    companies = _company_words()

    assert template("Microsoft revenue last 4 quarters", companies) == template(
        "Apple revenue last 8 quarters", companies
    )
    assert template("$NVDA's EPS", companies) == template("Lilly's EPS", companies)
    assert template("Apple revenue", companies) != template("Apple net income", companies)


def test_two_labellings_are_compared_field_by_field(tmp_path: Path) -> None:
    first = _write(
        tmp_path / "a.json",
        [_case("a1", "q1"), {**_case("a2", "q2"), "expect": {"outcome": "clarify"}}],
    )
    second = _write(
        tmp_path / "b.json",
        [
            {**_case("b1", "q1"), "expect": {"outcome": "answer", "tickers": ["AAPL"]}},
            {**_case("b2", "q2"), "expect": {"outcome": "answer"}},
            _case("b3", "q3"),
        ],
    )

    agreement = label_agreement(first, second)

    assert agreement["questions"] == 2
    assert agreement["only_second"] == 1
    assert agreement["agree_on_every_field"] == 1
    assert agreement["fields"]["outcome"] == {"labelled": 2, "agree": 1}
    assert agreement["disagreements"][0]["fields"] == {
        "outcome": {"first": "clarify", "second": "answer"}
    }
