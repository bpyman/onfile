"""The essay evaluation's bookkeeping: requests, the numeral lock, pairing and statistics."""

from __future__ import annotations

import json

import pytest

from financial_analyst_agent.essay import INSTRUCTIONS, INSTRUCTIONS_V1, essay_request
from financial_analyst_agent.essay_evaluation import (
    Arm,
    Essay,
    EssayCase,
    case_outcomes,
    combine,
    estimate,
    generate,
    judge_pairs,
    pairwise_summary,
    parse_judgement,
    sign_test,
)

_HITS = json.dumps(
    [
        {
            "title": "Apple cuts orders",
            "url": "https://example.com/a",
            "content": "Orders cut by 20%.",
        },
        {"title": "Suppliers react", "url": "https://example.com/b", "content": "Shares fell."},
    ]
)
_ROWS = json.dumps([{"company_name": "Apple Inc.", "metric": "revenue", "value": "94930000000"}])

_EXPLAIN = EssayCase("e1", "explain", ("How does a buyback affect EPS?",), "")
_ANALYSIS = EssayCase(
    "a1", "analysis", ("Apple revenue last 4 quarters", "Why the dip?"), "", _ROWS
)
_NEWS = EssayCase("n1", "news", ("Why are Apple suppliers down?",), "", _HITS)
_ARM = Arm("v1", "gpt-6.1-sol")


def test_the_app_sends_the_first_instructions_until_a_revision_is_chosen() -> None:
    assert INSTRUCTIONS is INSTRUCTIONS_V1


@pytest.mark.parametrize(
    ("query", "tool_json", "kind", "starts"),
    [
        ("How does a buyback affect EPS?", "", "explain", "How does a buyback"),
        ("Why the dip?", _ROWS, "analysis", "Why the dip?\n\nAnalysis JSON:"),
        ("Why are suppliers down?", _HITS, "news", "User query:\nWhy are suppliers down?"),
    ],
)
def test_an_essay_request_is_chosen_by_its_grounding(
    query: str, tool_json: str, kind: str, starts: str
) -> None:
    chosen, instructions, input_text = essay_request(query, tool_json)
    assert chosen == kind
    assert instructions == getattr(INSTRUCTIONS_V1, kind)
    assert input_text.startswith(starts)


def test_an_arm_names_its_instructions_and_model() -> None:
    assert Arm.parse("v1@gpt-5.6-terra") == Arm("v1", "gpt-5.6-terra")
    with pytest.raises(SystemExit):
        Arm.parse("v9@gpt-5.6-terra")
    with pytest.raises(SystemExit):
        Arm.parse("v1@some-other-model")


def test_generation_holds_each_essay_to_the_numeral_lock_and_prices_it() -> None:
    texts = {
        "e1": "A buyback lowers the share count, so EPS rises if earnings hold.",
        "a1": "Revenue was 94930000000, up 17.3% on the year.",
        "n1": "Apple cut orders [1], and supplier shares fell [2].",
    }

    def complete(model: str, instructions: str, input_text: str) -> tuple[str, int, int]:
        case = next(
            key
            for key, case in {"e1": _EXPLAIN, "a1": _ANALYSIS, "n1": _NEWS}.items()
            if input_text.find(case.question) >= 0
        )
        return texts[case], 1_000_000, 1_000_000

    essays = {
        e.case_id: e for e in generate([_EXPLAIN, _ANALYSIS, _NEWS], _ARM, 1, complete, workers=1)
    }

    assert not essays["e1"].withheld
    assert essays["a1"].numeral_lock_extras == ["17.3"]
    assert not essays["n1"].withheld
    assert essays["e1"].cost == pytest.approx(2.0 + 10.0)


def test_an_estimate_grows_with_samples_and_output() -> None:
    one = estimate([_EXPLAIN, _ANALYSIS, _NEWS], _ARM, 1, 1000)
    assert estimate([_EXPLAIN, _ANALYSIS, _NEWS], _ARM, 2, 1000) == pytest.approx(2 * one)
    assert estimate([_EXPLAIN, _ANALYSIS, _NEWS], _ARM, 1, 2000) > one


def test_a_judgement_is_read_from_the_first_json_object_in_the_reply() -> None:
    reply = 'Here it is:\n{"preference": {"overall": "A"}, "reason": "clearer"}\nDone.'
    assert parse_judgement(reply)["preference"]["overall"] == "A"
    with pytest.raises(ValueError):
        parse_judgement("no verdict")


def _verdict(**preference: str) -> dict[str, object]:
    return {"preference": preference}


def test_a_preference_counts_only_when_it_survives_the_swap() -> None:
    # X was A first and B second: "A" then "B" both mean X.
    agreed = combine(_verdict(overall="A", clarity="A"), _verdict(overall="B", clarity="A"))
    assert agreed["overall"] == "X"
    assert agreed["clarity"] == "tie"  # A both times is position, not preference
    assert combine(_verdict(overall="tie"), _verdict(overall="tie"))["overall"] == "tie"


def test_each_case_scores_once_whatever_its_number_of_samples() -> None:
    pairs = [
        {"case_id": "c1", "preference": {"overall": "X"}},
        {"case_id": "c1", "preference": {"overall": "X"}},
        {"case_id": "c2", "preference": {"overall": "X"}},
        {"case_id": "c2", "preference": {"overall": "Y"}},
        {"case_id": "c3", "preference": {"overall": "Y"}},
        {"case_id": "c3", "preference": {"overall": "tie"}},
    ]
    assert case_outcomes(pairs) == {"c1": 1, "c2": 0, "c3": -1}


def test_the_sign_test_is_exact_and_two_sided() -> None:
    assert sign_test(0, 0) == 1.0
    assert sign_test(5, 5) == 1.0
    assert sign_test(10, 0) == pytest.approx(2 / 1024)
    assert sign_test(9, 1) == pytest.approx(2 * 11 / 1024)
    assert sign_test(1, 9) == sign_test(9, 1)


def test_pairs_are_judged_in_both_orders_without_naming_the_arms() -> None:
    x = [Essay("e1", 1, "v2@gpt-6.1-sol", "Essay from X.", 0, 0, 0.0)]
    y = [Essay("e1", 1, "v1@gpt-6.1-sol", "Essay from Y.", 0, 0, 0.0)]
    prompts: list[str] = []

    def judge(prompt: str) -> str:
        prompts.append(prompt)
        winner = "A" if prompt.index("Essay from X.") < prompt.index("Essay from Y.") else "B"
        return json.dumps(
            {
                "gates": {"A": {}, "B": {}},
                "preference": {
                    key: winner
                    for key in (
                        "answers",
                        "accuracy",
                        "analysis",
                        "clarity",
                        "calibration",
                        "overall",
                    )
                },
            }
        )

    pairs = judge_pairs([_EXPLAIN], x, y, judge, workers=1)

    assert len(prompts) == 2
    assert all("v1@" not in p and "v2@" not in p for p in prompts)
    assert pairs[0]["preference"]["overall"] == "X"
    assert pairwise_summary(pairs)["overall"]["x_cases"] == 1
