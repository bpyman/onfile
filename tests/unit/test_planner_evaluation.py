"""The planner comparison: its cases, scoring, metering and budget, without calling OpenAI."""

from __future__ import annotations

import json
import shutil
import subprocess
import uuid
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from financial_analyst_agent.conversation import run_conversation_turn
from financial_analyst_agent.planner import OpenAIStructuredCompleter, Plan
from financial_analyst_agent.planner_evaluation import (
    CASE_PATHS,
    Adjudication,
    BudgetExceeded,
    CaseRun,
    MeteredCompleter,
    MeteredOpenAIClient,
    Observation,
    PlannerCase,
    Prices,
    Usage,
    check_rule_history,
    estimate,
    load_adjudications,
    load_cases,
    observe,
    paired,
    render_markdown,
    rescore,
    run_planner,
    score,
    scored_run,
    summarize,
)
from financial_analyst_agent.runtime import recorded_runtime
from financial_analyst_agent.thread_store import EphemeralThreadStore


def _seen(**overrides: Any) -> Observation:
    fields: dict[str, Any] = {
        "outcome": "answer",
        "intent": "lookup",
        "tickers": frozenset({"MSFT"}),
        "metrics": frozenset({"revenue"}),
        "periods": ("last_n_quarters", 4),
        "operations": frozenset({"across_periods"}),
    }
    fields.update(overrides)
    return Observation(**fields)


def _ask(*messages: str) -> Observation:
    runtime = recorded_runtime()
    store = EphemeralThreadStore()
    thread_id = str(uuid.uuid4())
    turn = None
    for message in messages:
        turn = run_conversation_turn(thread_id, message, runtime, store=store)
    assert turn is not None
    return observe(turn)


def test_the_committed_cases_load_with_unique_ids_and_known_fields() -> None:
    cases = load_cases()

    assert sum(case.split == "scorecard" for case in cases) == 28
    assert sum(case.split == "dev" for case in cases) == 50 + 72 + 69
    assert sum(case.split == "held_out" for case in cases) == 66
    assert all(case.turns and case.expect for case in cases)


def test_a_case_passes_only_on_the_fields_it_labels() -> None:
    seen = _seen()

    assert score({"tickers": ["MSFT"], "metrics": ["revenue"]}, seen) == {
        "tickers": True,
        "metrics": True,
    }
    assert score({"tickers": ["MSFT", "AAPL"]}, seen) == {"tickers": False}
    assert score({"tickers_include": ["MSFT"]}, _seen(tickers=frozenset({"MSFT", "AAPL"}))) == {
        "tickers_include": True
    }
    assert score({"periods": {"kind": "last_n_quarters", "count": 8}}, seen) == {"periods": False}
    assert score({"periods": {"kind": "last_n_quarters"}}, seen) == {"periods": True}
    assert score({"operations_include": ["year_over_year"]}, seen) == {"operations_include": False}


def test_missing_recorded_data_still_counts_as_a_planned_answer() -> None:
    # The plan was right; the recorded filings lack the fact.
    assert score({"outcome": "answer"}, _seen(outcome="no_data")) == {"outcome": True}
    assert score({"outcome": "refuse"}, _seen(outcome="no_data")) == {"outcome": False}


def test_a_turn_that_raised_fails_every_labelled_field() -> None:
    assert score({"outcome": "answer", "intent": "lookup"}, None) == {
        "outcome": False,
        "intent": False,
    }


def test_observing_a_recorded_turn_reads_its_window_and_growth() -> None:
    window = _ask("Microsoft revenue over the last four quarters")
    assert window.outcome == "answer"
    assert window.tickers == {"MSFT"}
    assert window.metrics == {"revenue"}
    assert window.periods == ("last_n_quarters", 4)

    growth = _ask("Compare Nvidia and AMD revenue growth")
    assert "year_over_year" in growth.operations

    # A quarter-over-quarter change shows only as sequential rows.
    sequential = _ask("Apple revenue quarter over quarter")
    assert "sequential" in sequential.operations
    assert "sequential" not in window.operations


def test_a_fact_missing_from_the_recorded_filings_is_no_data() -> None:
    assert _ask("what did Goldman Sachs spend on R&D in its latest quarter").outcome == "no_data"
    # A window of quarters the filings lack says why too, not only a single quarter.
    assert _ask("Goldman Sachs R&D over the last three quarters").outcome == "no_data"
    # Cisco's latest quarter is a fiscal fourth, whose EPS the 10-K reports only for
    # the year: named, the filings hold no quarterly figure. Asked with no period,
    # the answer is the latest quarter with its own EPS (ADR 0007).
    assert _ask("Cisco EPS in Q4 FY2026").outcome == "no_data"
    assert _ask("What are Cisco's earnings per share?").outcome == "answer"


class _FakeCompletions:
    """Returns one plan per call and reports token usage, as the OpenAI SDK does."""

    def __init__(self, plan: Plan) -> None:
        self.plan = plan
        self.calls = 0

    def parse(self, **_: Any) -> Any:
        self.calls += 1
        message = SimpleNamespace(parsed=self.plan, refusal=None)
        usage = SimpleNamespace(
            prompt_tokens=900,
            completion_tokens=50,
            completion_tokens_details=SimpleNamespace(reasoning_tokens=20),
        )
        return SimpleNamespace(choices=[SimpleNamespace(message=message)], usage=usage)


def _llm_planner(plan: Plan, usage: Usage) -> tuple[Any, _FakeCompletions]:
    completions = _FakeCompletions(plan)
    client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    planner = OpenAIStructuredCompleter(MeteredOpenAIClient(client, usage), "test-model")
    return MeteredCompleter(planner, usage), completions


_MSFT_PRETAX = PlannerCase(
    case_id="lookup_msft_pretax",
    split="scorecard",
    category="lookup",
    turns=("Microsoft pre-tax income",),
    expect={
        "outcome": "answer",
        "intent": "lookup",
        "tickers": ["MSFT"],
        "metrics": ["pretax_income"],
    },
)


def test_the_llm_path_runs_end_to_end_and_counts_its_tokens() -> None:
    usage = Usage()
    plan = Plan.model_validate(
        {"intent": "lookup", "company": "Microsoft", "metric": "pretax_income"}
    )
    completer, completions = _llm_planner(plan, usage)

    (result,) = run_planner([_MSFT_PRETAX], completer, runs=1)

    assert result.passed, result
    assert completions.calls == usage.calls == 1
    assert (usage.input_tokens, usage.output_tokens, usage.reasoning_tokens) == (900, 50, 20)
    summary = summarize([_MSFT_PRETAX], [result], usage, Prices(input=2.0, output=8.0))
    assert summary["cost_usd"] == pytest.approx((900 * 2.0 + 50 * 8.0) / 1_000_000)


def test_a_spent_budget_stops_the_run() -> None:
    usage = Usage()

    def spent() -> None:
        raise BudgetExceeded("spent")

    completer = MeteredCompleter(recorded_runtime().completer, usage, before_call=spent)

    results = run_planner([_MSFT_PRETAX, _MSFT_PRETAX], completer, runs=2)

    assert [result.error for result in results] == ["budget reached"]
    summary = summarize([_MSFT_PRETAX], results, usage, None)
    assert summary["splits"] == {} and summary["stopped_in_run"] == 0


def test_a_run_cut_short_by_the_budget_is_left_out_and_said_so() -> None:
    usage = Usage()
    calls = 0

    def spend() -> None:
        nonlocal calls
        calls += 1
        if calls > 1:
            raise BudgetExceeded("spent")

    completer = MeteredCompleter(recorded_runtime().completer, usage, before_call=spend)

    # One planner call a run: the first run completes, the second stops at once.
    results = run_planner([_MSFT_PRETAX], completer, runs=2)
    summary = summarize([_MSFT_PRETAX], results, usage, None)

    # Run 1 completed; run 2 stopped on its first case and is not averaged in.
    assert summary["runs"] == 1
    assert summary["stopped_in_run"] == 1
    assert summary["splits"]["all"]["accuracy_by_run"] == [1.0]
    assert all(failure["error"] != "budget reached" for failure in summary["failures"])


def test_agreement_counts_cases_whose_runs_all_saw_the_same() -> None:
    cases = [
        _MSFT_PRETAX,
        PlannerCase("other", "held_out", "lookup", ("q",), {"outcome": "answer"}),
    ]
    same = _seen().signature()
    results = [
        CaseRun("lookup_msft_pretax", 0, {"outcome": True}, same, 1.0),
        CaseRun("lookup_msft_pretax", 1, {"outcome": True}, same, 1.0),
        CaseRun("other", 0, {"outcome": True}, same, 1.0),
        CaseRun("other", 1, {"outcome": False}, _seen(outcome="refuse").signature(), 1.0),
    ]

    summary = summarize(cases, results, Usage(), None)

    assert summary["splits"]["all"]["agreement"] == 0.5
    assert summary["splits"]["all"]["accuracy_by_run"] == [1.0, 0.5]
    assert summary["cost_usd"] is None


def test_an_estimate_counts_every_turn_and_prices_only_when_asked() -> None:
    cases = load_cases()
    turns = sum(len(case.turns) for case in cases)

    unpriced = estimate(cases, 3, None)
    priced = estimate(cases, 3, Prices(input=1.0, output=1.0))

    assert unpriced["planner_calls"] == priced["planner_calls"] == turns * 3
    assert unpriced["cost_usd"] is None
    assert priced["cost_usd"] == pytest.approx(
        (priced["input_tokens"] + priced["output_tokens"]) / 1_000_000
    )


_GROWTH = PlannerCase(
    "growth",
    "held_out",
    "growth",
    ("How fast is Nvidia's revenue growing?",),
    {"tickers": ["NVDA"], "periods": {"kind": "latest_quarter"}},
)
_RULE_COMMIT = "a" * 40
_CASES_COMMIT = "b" * 40
_GROWTH_ADJUDICATED = PlannerCase(
    *(_GROWTH.case_id, _GROWTH.split, _GROWTH.category, _GROWTH.turns, _GROWTH.expect),
    adjudication=Adjudication(
        case_id="growth",
        expect={"periods": {"kind": "last_n_quarters"}},
        rule="charts the growth rates",
        why="a chart",
        rule_file="README.md",
        rule_commit=_RULE_COMMIT,
        cases_commit=_CASES_COMMIT,
    ),
)
_FIVE_QUARTERS = _seen(tickers=frozenset({"NVDA"}), periods=("last_n_quarters", 5))


def test_the_committed_adjudications_replace_a_field_and_keep_the_label() -> None:
    cases = {case.case_id: case for case in load_cases()}

    growth = cases["h4_growth_nvda_how_fast"]
    assert growth.expect["periods"] == {"kind": "latest_quarter"}
    assert growth.adjudicated is not None
    assert growth.adjudicated["periods"] == {"kind": "last_n_quarters"}
    assert growth.adjudicated["tickers"] == growth.expect["tickers"]
    assert cases["h4_bac_nii_couple_quarters"].adjudicated is None


def test_an_adjudication_needs_its_rule_and_reason_and_a_case_once() -> None:
    entry = {
        "id": "x",
        "expect": {"outcome": "answer"},
        "rule": "README",
        "rule_file": "README.md",
        "rule_commit": _RULE_COMMIT,
        "why": "because",
    }
    file = {"cases_commit": _CASES_COMMIT, "adjudications": [entry]}

    (loaded,) = load_adjudications([file])
    assert loaded.rule == "README"
    assert (loaded.rule_file, loaded.rule_commit) == ("README.md", _RULE_COMMIT)
    assert loaded.cases_commit == _CASES_COMMIT
    with pytest.raises(ValueError):
        load_adjudications([{**file, "adjudications": [{**entry, "rule": " "}]}])
    with pytest.raises(ValueError):
        load_adjudications([{**file, "adjudications": [entry, entry]}])


def test_an_adjudication_names_the_commits_that_hold_its_rule_and_its_cases() -> None:
    entry = {
        "id": "x",
        "expect": {"outcome": "answer"},
        "rule": "README",
        "rule_file": "README.md",
        "rule_commit": _RULE_COMMIT,
        "why": "because",
    }

    # A case file with adjudications names the commit that added its cases, in full.
    with pytest.raises(ValueError, match="cases_commit"):
        load_adjudications([{"adjudications": [entry]}])
    with pytest.raises(ValueError, match="cases_commit"):
        load_adjudications([{"cases_commit": "bc237f0", "adjudications": [entry]}])
    # One without adjudications need not.
    assert load_adjudications([{"adjudications": []}, {"cases": []}]) == []
    # Each adjudication names the file and the full commit that hold its rule.
    file = {"cases_commit": _CASES_COMMIT}
    for broken in (
        {**entry, "rule_commit": "54a0e22"},
        {**entry, "rule_commit": "54A0E22" + "0" * 33},
        {**entry, "rule_file": " "},
        {key: value for key, value in entry.items() if key != "rule_file"},
        {key: value for key, value in entry.items() if key != "rule_commit"},
    ):
        with pytest.raises(ValueError, match="rule_file|rule_commit"):
            load_adjudications([{**file, "adjudications": [broken]}])


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.com", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    return result.stdout.strip()


def _commit(repo: Path, path: str, text: str) -> str:
    (repo / path).write_text(text, encoding="utf-8")
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", f"change {path}")
    return _git(repo, "rev-parse", "HEAD")


def test_a_rule_committed_after_its_cases_or_not_as_quoted_is_a_problem(tmp_path: Path) -> None:
    if shutil.which("git") is None:
        pytest.skip("git is not installed")
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    rule_commit = _commit(repo, "README.md", "`Compare X and Y growth` charts the growth rates\n")
    cases_commit = _commit(repo, "cases.json", "{}\n")
    assert _GROWTH_ADJUDICATED.adjudication is not None
    good = replace(
        _GROWTH_ADJUDICATED.adjudication, rule_commit=rule_commit, cases_commit=cases_commit
    )

    assert check_rule_history([good], repo) == []

    after = replace(good, rule_commit=cases_commit, cases_commit=rule_commit)
    (problem,) = check_rule_history([after], repo)
    assert "growth" in problem and cases_commit in problem and "before" in problem

    same = replace(good, cases_commit=rule_commit)
    assert len(check_rule_history([same], repo)) == 1

    misquoted = replace(good, rule="charts growth")
    (problem,) = check_rule_history([misquoted], repo)
    assert "README.md" in problem and rule_commit in problem

    elsewhere = replace(good, rule_file="CONTEXT.md")
    (problem,) = check_rule_history([elsewhere], repo)
    assert "CONTEXT.md" in problem


def test_the_committed_adjudications_cite_rules_committed_before_their_cases() -> None:
    if shutil.which("git") is None:
        pytest.skip("git is not installed")
    repo = Path(__file__).resolve().parents[2]
    if _git(repo, "rev-parse", "--is-shallow-repository") == "true":
        pytest.skip("a shallow checkout lacks the history this checks; run it in a full clone")
    files = [
        json.loads((repo / path).read_text(encoding="utf-8"))
        for path in CASE_PATHS
        if (repo / path).exists()
    ]

    adjudications = load_adjudications(files)

    assert {item.case_id for item in adjudications} >= {"h4_growth_nvda_how_fast"}
    assert check_rule_history(adjudications, repo) == []


def test_a_case_is_scored_as_labelled_and_after_adjudication() -> None:
    results = [scored_run(_GROWTH_ADJUDICATED, 0, _FIVE_QUARTERS)]

    summary = summarize([_GROWTH_ADJUDICATED], results, Usage(), None)

    held_out = summary["splits"]["held_out"]
    assert held_out["accuracy"] == 0.0
    assert held_out["adjudicated_accuracy"] == 1.0
    assert held_out["adjudicated_cases"] == 1
    assert summary["failures"][0]["passes_adjudicated"] is True


def test_a_saved_run_is_scored_again_with_an_adjudication_made_after_it() -> None:
    # The run was scored before the adjudication existed.
    results = [scored_run(_GROWTH, run, _FIVE_QUARTERS) for run in range(2)]
    saved = {
        "planners": {
            "rules": {"label": "Rules planner", **summarize([_GROWTH], results, Usage(), None)}
        }
    }
    assert saved["planners"]["rules"]["splits"]["held_out"]["adjudicated_accuracy"] == 0.0

    report = rescore(saved, [_GROWTH_ADJUDICATED])

    rules = report["planners"]["rules"]
    assert rules["splits"]["held_out"]["accuracy"] == 0.0
    assert rules["splits"]["held_out"]["adjudicated_accuracy"] == 1.0
    assert report["adjudications"][0]["was"] == {"periods": {"kind": "latest_quarter"}}
    assert report["adjudications"][0]["now"] == {"periods": {"kind": "last_n_quarters"}}


def test_the_paired_test_adds_adjudicated_rows_only_where_a_case_was_adjudicated() -> None:
    passes = [scored_run(_GROWTH_ADJUDICATED, 0, _FIVE_QUARTERS)]
    fails = [scored_run(_GROWTH_ADJUDICATED, 0, _seen(outcome="refuse"))]

    rows = paired([_GROWTH_ADJUDICATED], passes, fails)

    assert rows["held_out"]["only_first"] == 0
    assert rows["held_out:adjudicated"]["only_first"] == 1
    assert "held_out:adjudicated" not in paired([_GROWTH], passes, fails)


def test_the_report_shows_both_scores_and_lists_the_adjudications() -> None:
    results = [scored_run(_GROWTH_ADJUDICATED, 0, _FIVE_QUARTERS)]
    report = rescore(
        {
            "generated_at": "now",
            "case_count": 1,
            "scorecard_count": 0,
            "dev_count": 0,
            "held_out_count": 1,
            "planners": {
                "rules": {
                    "label": "Rules planner",
                    **summarize([_GROWTH_ADJUDICATED], results, Usage(), None),
                }
            },
        },
        [_GROWTH_ADJUDICATED],
    )

    markdown = render_markdown(report)

    assert "After adjudication" in markdown
    assert "| Held out | 1 | 0% | 0.0% | — | 100% (1 adjudicated) |" in markdown
    assert "## Adjudicated labels" in markdown
    assert f"`README.md` at `{_RULE_COMMIT[:7]}`: charts the growth rates" in markdown
    assert "passes after adjudication" in markdown
