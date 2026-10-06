"""Compare the rules planner with the LLM planner on the same questions.

Each case is a conversation run end to end on the recorded runtime: SEC facts,
rankings and news are replayed, and only the planner changes. So a score is
what a visitor would get from that planner, after the shared guards, period
reading and resolution, not the planner's raw output. Cases are labelled in
``docs/evaluation/``: the scorecard's questions and the development cases in
``planner-cases.json``, ``planner-cases-v2.json`` and ``planner-cases-v3.json``,
and the held-out cases in ``planner-cases-held-out-4.json``. Held-out cases are
written from a brief frozen before them (``held-out-4-brief.md``) by a separate
session, and nobody changing a planner reads them before they are run.

Each case is scored twice. As labelled: the labels as committed, the score
to compare across sets. After adjudication: a case file's ``adjudications``
replace label fields that disagree with a product rule committed before the
cases were written, each with that rule and why. Every case run's observation
is kept in ``planner-comparison.json``, so ``--from-json`` scores a paid run
again after an adjudication without running a planner.

The rules planner is free and deterministic. The LLM planner calls OpenAI on
the configured key, and so does the cascade (``planner_cascade``) on the turns
the rules planner is unsure of; they run only when asked, with prices and one
budget for both given on the command line. ``--estimate`` prices an LLM run
without calling anything.

    uv run python -m financial_analyst_agent.planner_evaluation              # rules only
    uv run python -m financial_analyst_agent.planner_evaluation --estimate \\
        --runs 3 --input-price 1.25 --output-price 10
    uv run python -m financial_analyst_agent.planner_evaluation \\
        --planners rules,llm,cascade --runs 3 --input-price 1.25 --output-price 10 \\
        --budget-usd 5
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import time
import uuid
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from financial_analyst_agent.contracts import Completer, RendererKind, WorkflowPlan
from financial_analyst_agent.conversation import ConversationTurn, run_conversation_turn
from financial_analyst_agent.graph.analysis_spec import SpecPatch
from financial_analyst_agent.planner_cascade import CascadeCompleter
from financial_analyst_agent.ranking import SnapshotRanking
from financial_analyst_agent.runtime import recorded_runtime
from financial_analyst_agent.thread_store import EphemeralThreadStore

CASES_PATH = Path("docs/evaluation/planner-cases.json")
CASE_PATHS = (
    CASES_PATH,
    Path("docs/evaluation/planner-cases-v2.json"),
    Path("docs/evaluation/planner-cases-v3.json"),
    Path("docs/evaluation/planner-cases-held-out-4.json"),
)
SPLITS = (("scorecard", "Scorecard"), ("dev", "Development"), ("held_out", "Held out"))
REPORT_PATH = Path("docs/evaluation/planner-comparison.md")
REPORT_JSON_PATH = Path("docs/evaluation/planner-comparison.json")
FIELDS = (
    "outcome",
    "intent",
    "tickers",
    "tickers_include",
    "metrics",
    "periods",
    "operations_include",
)
# A rough characters-per-token ratio for English prompts and JSON schemas.
_CHARS_PER_TOKEN = 4
# A structured plan is a short JSON object; reasoning tokens, if the model uses
# them, come on top and are the main uncertainty in an estimate.
_ASSUMED_OUTPUT_TOKENS = 120
# A refusal with these codes planned correctly and found no fact in the
# recorded filings: a gap in the data, not in planning. A per-share figure a
# fiscal fourth quarter reports only for the year is one (ADR 0007).
_NO_DATA_CODES = frozenset(
    {"unsupported_quarterly_fact", "missing_fact", "not_reported_for_quarter"}
)


@dataclass(frozen=True)
class PlannerCase:
    case_id: str
    split: str
    category: str
    turns: tuple[str, ...]
    expect: dict[str, Any]
    adjudication: Adjudication | None = None

    @property
    def adjudicated(self) -> dict[str, Any] | None:
        """The label after adjudication, or None where the label stands."""
        if self.adjudication is None:
            return None
        return {**self.expect, **self.adjudication.expect}


@dataclass(frozen=True)
class Adjudication:
    """A label field replaced because it disagrees with a product rule, not with a result."""

    case_id: str
    expect: dict[str, Any]
    # The product rule, committed before the cases were written, that decides it.
    rule: str
    why: str


@dataclass(frozen=True)
class Observation:
    """What the last turn showed, in the terms a case is labelled in."""

    outcome: str
    intent: str
    tickers: frozenset[str]
    metrics: frozenset[str]
    periods: tuple[str, int | None]
    operations: frozenset[str]

    def signature(self) -> tuple[Any, ...]:
        """The observation as one comparable value, for run-to-run agreement."""
        return (
            self.outcome,
            self.intent,
            tuple(sorted(self.tickers)),
            tuple(sorted(self.metrics)),
            self.periods,
            tuple(sorted(self.operations)),
        )

    @classmethod
    def from_signature(cls, raw: Sequence[Any]) -> Observation:
        """The observation a saved signature records."""
        outcome, intent, tickers, metrics, periods, operations = raw
        kind, count = periods
        return cls(
            outcome=outcome,
            intent=intent,
            tickers=frozenset(tickers),
            metrics=frozenset(metrics),
            periods=(kind, count),
            operations=frozenset(operations),
        )


@dataclass
class Usage:
    """Planner calls, time, and tokens; tokens only for a metered LLM client."""

    calls: int = 0
    planner_ms: list[float] = field(default_factory=list)
    input_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0


@dataclass(frozen=True)
class Prices:
    """US dollars per million tokens."""

    input: float
    output: float

    def cost(self, input_tokens: int, output_tokens: int) -> float:
        return (input_tokens * self.input + output_tokens * self.output) / 1_000_000


class BudgetExceeded(RuntimeError):
    pass


def load_cases(*paths: Path) -> list[PlannerCase]:
    """The cases in ``paths``, or in every case file that exists."""
    chosen = paths or tuple(path for path in CASE_PATHS if path.exists())
    files = [json.loads(path.read_text(encoding="utf-8")) for path in chosen]
    cases = [
        PlannerCase(
            case_id=raw["id"],
            split=raw["split"],
            category=raw["category"],
            turns=tuple(raw["turns"]),
            expect=dict(raw["expect"]),
        )
        for data in files
        for raw in data["cases"]
    ]
    splits = {case.split for case in cases} - {split for split, _ in SPLITS}
    if splits:
        raise ValueError(f"unknown splits: {sorted(splits)}")
    if len({case.case_id for case in cases}) != len(cases):
        raise ValueError("case ids must be unique")
    adjudications = load_adjudications(files)
    unknown_ids = {item.case_id for item in adjudications} - {case.case_id for case in cases}
    if unknown_ids:
        raise ValueError(f"adjudications of unknown cases: {sorted(unknown_ids)}")
    by_id = {item.case_id: item for item in adjudications}
    cases = [replace(case, adjudication=by_id.get(case.case_id)) for case in cases]
    unknown = {key for case in cases for key in case.adjudicated or case.expect} - set(FIELDS)
    if unknown:
        raise ValueError(f"unknown expectation fields: {sorted(unknown)}")
    return cases


def load_adjudications(files: Sequence[dict[str, Any]]) -> list[Adjudication]:
    """Every case file's ``adjudications``, each naming its rule and why."""
    found = [
        Adjudication(
            case_id=raw["id"], expect=dict(raw["expect"]), rule=raw["rule"], why=raw["why"]
        )
        for data in files
        for raw in data.get("adjudications", ())
    ]
    if any(not (item.expect and item.rule.strip() and item.why.strip()) for item in found):
        raise ValueError("an adjudication needs the fields it replaces, a rule and why")
    if len({item.case_id for item in found}) != len(found):
        raise ValueError("a case is adjudicated once")
    return found


def observe(turn: ConversationTurn) -> Observation:
    result = turn.result
    spec = turn.analysis_spec
    codes = {
        trace.provenance["error"].get("code")
        for trace in result.tool_traces
        if isinstance(trace.provenance.get("error"), dict)
    }
    if result.refusal is not None:
        codes.add(result.refusal.code)
    if result.renderer is RendererKind.CLARIFY:
        outcome = "clarify"
    elif result.renderer is RendererKind.REFUSE:
        outcome = "no_data" if codes & _NO_DATA_CODES else "refuse"
    else:
        outcome = "answer"
    rows = [row for row in result.table_rows if row.ticker]
    tickers = {row.ticker for row in rows}
    metrics = {row.metric for row in result.table_rows if row.metric}
    periods: tuple[str, int | None] = ("latest_quarter", None)
    operations: frozenset[str] = frozenset()
    if spec is not None:
        tickers |= {company.ticker for company in spec.companies if company.ticker}
        metrics = set(spec.metrics) or metrics
        # A window is scored as asked: the recording holds about nine quarters a
        # company, and the answer says when it shows fewer than were asked for.
        periods = (spec.periods.kind, spec.periods.asked or spec.periods.count)
        operations = frozenset(spec.operations)
    # A comparison shows growth as year-over-year rows rather than an operation, and
    # a quarter-over-quarter change only as sequential rows.
    if any(row.comparison == "year_over_year" for row in result.table_rows):
        operations |= {"year_over_year"}
    if any(row.comparison == "sequential" for row in result.table_rows):
        operations |= {"sequential"}
    return Observation(
        outcome=outcome,
        intent=result.intent.value,
        tickers=frozenset(tickers),
        metrics=frozenset(metrics),
        periods=periods,
        operations=operations,
    )


def score(expect: dict[str, Any], seen: Observation | None) -> dict[str, bool]:
    """Each labelled field, right or wrong. A turn that raised is wrong on all of them."""
    if seen is None:
        return {name: False for name in expect}
    checks: dict[str, bool] = {}
    for name, wanted in expect.items():
        if name == "outcome":
            # A right plan that met a gap in the recorded data still planned an answer.
            checks[name] = seen.outcome == wanted or (
                wanted == "answer" and seen.outcome == "no_data"
            )
        elif name == "intent":
            checks[name] = seen.intent == wanted
        elif name == "tickers":
            checks[name] = seen.tickers == frozenset(wanted)
        elif name == "tickers_include":
            checks[name] = frozenset(wanted) <= seen.tickers
        elif name == "metrics":
            checks[name] = seen.metrics == frozenset(wanted)
        elif name == "periods":
            kind, count = seen.periods
            checks[name] = kind == wanted["kind"] and (
                "count" not in wanted or count == wanted["count"]
            )
        elif name == "operations_include":
            checks[name] = frozenset(wanted) <= seen.operations
    return checks


class MeteredCompleter:
    """Times each planner call; everything else is the wrapped planner's own."""

    def __init__(
        self, inner: Completer, usage: Usage, before_call: Callable[[], None] = lambda: None
    ):
        self._inner = inner
        self._usage = usage
        self._before_call = before_call

    def complete(self, query: str, current_spec: Any = None) -> WorkflowPlan | SpecPatch:
        self._before_call()
        started = time.perf_counter()
        try:
            return self._inner.complete(query, current_spec=current_spec)
        finally:
            self._usage.calls += 1
            self._usage.planner_ms.append((time.perf_counter() - started) * 1000)

    def __getattr__(self, name: str) -> Any:
        # The rules planner's issuer index and the like reach the runtime unchanged.
        return getattr(self._inner, name)


class MeteredOpenAIClient:
    """An OpenAI client whose structured-output calls add their token counts to ``usage``."""

    def __init__(self, client: Any, usage: Usage) -> None:
        self.chat = _Namespace(completions=_MeteredCompletions(client.chat.completions, usage))


@dataclass(frozen=True)
class _Namespace:
    completions: Any


class _MeteredCompletions:
    def __init__(self, completions: Any, usage: Usage) -> None:
        self._completions = completions
        self._usage = usage

    def parse(self, **kwargs: Any) -> Any:
        completion = self._completions.parse(**kwargs)
        used = getattr(completion, "usage", None)
        if used is not None:
            self._usage.input_tokens += int(getattr(used, "prompt_tokens", 0) or 0)
            self._usage.output_tokens += int(getattr(used, "completion_tokens", 0) or 0)
            details = getattr(used, "completion_tokens_details", None)
            self._usage.reasoning_tokens += int(getattr(details, "reasoning_tokens", 0) or 0)
        return completion


@dataclass
class CaseRun:
    case_id: str
    run: int
    checks: dict[str, bool]
    signature: tuple[Any, ...] | None
    turn_ms: float
    error: str = ""
    # Checks against the adjudicated label, or None where the label stands.
    adjudicated_checks: dict[str, bool] | None = None

    @property
    def passed(self) -> bool:
        return not self.error and bool(self.checks) and all(self.checks.values())

    def passes(self, adjudicated: bool) -> bool:
        checks = self.adjudicated_checks if adjudicated else None
        if checks is None:
            return self.passed
        return not self.error and bool(checks) and all(checks.values())


def scored_run(
    case: PlannerCase,
    run: int,
    seen: Observation | None,
    *,
    turn_ms: float = 0.0,
    error: str = "",
) -> CaseRun:
    """One run of ``case``, scored as labelled and, where adjudicated, after adjudication."""
    return CaseRun(
        case_id=case.case_id,
        run=run,
        checks=score(case.expect, seen),
        signature=seen.signature() if seen else None,
        turn_ms=turn_ms,
        error=error,
        adjudicated_checks=score(case.adjudicated, seen) if case.adjudicated else None,
    )


def run_planner(
    cases: Sequence[PlannerCase],
    completer: Any,
    *,
    runs: int,
    runtime: Any = None,
) -> list[CaseRun]:
    """Each case ``runs`` times, a fresh thread each time, with ``completer`` planning."""
    base = runtime or recorded_runtime()
    planned = replace(base, completer=completer)
    results: list[CaseRun] = []
    for run in range(runs):
        for case in cases:
            store = EphemeralThreadStore()
            thread_id = f"planner-eval-{uuid.uuid4()}"
            started = time.perf_counter()
            seen: Observation | None = None
            error = ""
            try:
                turn = None
                for message in case.turns:
                    turn = run_conversation_turn(thread_id, message, planned, store=store)
                assert turn is not None
                seen = observe(turn)
            except BudgetExceeded:
                error = "budget reached"
            except Exception as exc:  # noqa: BLE001 - a failed case is reported, not fatal
                error = type(exc).__name__
            results.append(
                scored_run(
                    case,
                    run,
                    seen,
                    turn_ms=(time.perf_counter() - started) * 1000,
                    error=error,
                )
            )
            if error == "budget reached":
                # A run cut short would be averaged as if complete: keep only the
                # complete runs, and one marker that says the budget ran out.
                kept = [result for result in results if result.run != run]
                return [
                    *kept,
                    replace(results[-1], checks={}, signature=None, adjudicated_checks=None),
                ]
    return results


def _percentile(values: Sequence[float], share: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, math.ceil(share * len(ordered)) - 1)]


def summarize(
    cases: Sequence[PlannerCase],
    results: Sequence[CaseRun],
    usage: Usage,
    prices: Prices | None,
) -> dict[str, Any]:
    """Accuracy per split, its spread across runs, field accuracy, agreement, time, cost."""
    complete = [result for result in results if result.error != "budget reached"]
    cost = prices.cost(usage.input_tokens, usage.output_tokens) if prices else None
    return {
        **scores(cases, results),
        "planner_calls": usage.calls,
        "planner_ms_p50": _percentile(usage.planner_ms, 0.5),
        "planner_ms_p95": _percentile(usage.planner_ms, 0.95),
        "turn_ms_p50": _percentile([r.turn_ms for r in complete], 0.5),
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "reasoning_tokens": usage.reasoning_tokens,
        "cost_usd": cost,
        "cost_per_planner_call_usd": cost / usage.calls
        if cost is not None and usage.calls
        else None,
        # What each case run showed, so --from-json can score it again.
        "observations": [
            {"id": r.case_id, "run": r.run, "seen": r.signature, "error": r.error} for r in results
        ],
    }


def scores(cases: Sequence[PlannerCase], results: Sequence[CaseRun]) -> dict[str, Any]:
    """Accuracy per split as labelled and after adjudication, and the cases failed."""
    split_of = {case.case_id: case.split for case in cases}
    adjudicated_ids = {case.case_id for case in cases if case.adjudicated is not None}
    stopped = [result for result in results if result.error == "budget reached"]
    results = [result for result in results if result.error != "budget reached"]
    runs = sorted({result.run for result in results})
    splits: dict[str, Any] = {}
    for split in (*(name for name, _ in SPLITS), "all"):
        chosen = [r for r in results if split == "all" or split_of[r.case_id] == split]
        if not chosen:
            continue
        per_run = [
            statistics.mean(r.passed for r in chosen if r.run == run)
            for run in runs
            if any(r.run == run for r in chosen)
        ]
        adjudicated_per_run = [
            statistics.mean(r.passes(adjudicated=True) for r in chosen if r.run == run)
            for run in runs
            if any(r.run == run for r in chosen)
        ]
        fields: dict[str, float] = {}
        for name in FIELDS:
            scored = [r.checks[name] for r in chosen if name in r.checks]
            if scored:
                fields[name] = statistics.mean(scored)
        by_case: dict[str, list[CaseRun]] = {}
        for r in chosen:
            by_case.setdefault(r.case_id, []).append(r)
        repeated = [rows for rows in by_case.values() if len(rows) > 1]
        agreement = (
            statistics.mean(len({row.signature for row in rows}) == 1 for rows in repeated)
            if repeated
            else None
        )
        splits[split] = {
            "cases": len(by_case),
            "accuracy": statistics.mean(per_run),
            "accuracy_by_run": per_run,
            "accuracy_sd": statistics.stdev(per_run) if len(per_run) > 1 else 0.0,
            "adjudicated_cases": len(adjudicated_ids & set(by_case)),
            "adjudicated_accuracy": statistics.mean(adjudicated_per_run),
            "fields": fields,
            "agreement": agreement,
        }
    return {
        "splits": splits,
        "runs": len(runs),
        # The run the budget ran out in, left out of every figure above.
        "stopped_in_run": stopped[0].run if stopped else None,
        "case_runs": len(results),
        "failures": [
            {
                "id": r.case_id,
                "run": r.run,
                "error": r.error,
                "wrong": sorted(k for k, v in r.checks.items() if not v),
                **(
                    {"passes_adjudicated": r.passes(adjudicated=True)}
                    if r.adjudicated_checks is not None
                    else {}
                ),
            }
            for r in results
            if not r.passed
        ],
    }


def case_passes(results: Sequence[CaseRun], *, adjudicated: bool = False) -> dict[str, bool]:
    """Whether each case passed in at least half of its complete runs."""
    by_case: dict[str, list[bool]] = {}
    for result in results:
        if result.error != "budget reached":
            by_case.setdefault(result.case_id, []).append(result.passes(adjudicated))
    return {case_id: 2 * sum(runs) >= len(runs) for case_id, runs in by_case.items()}


def mcnemar_p(only_a: int, only_b: int) -> float:
    """Two-sided exact McNemar p-value from the cases only one planner passed."""
    discordant = only_a + only_b
    if discordant == 0:
        return 1.0
    tail = sum(math.comb(discordant, k) for k in range(min(only_a, only_b) + 1))
    return min(1.0, 2 * tail / (1 << discordant))


def wilson_interval(passed: int, total: int, z: float = 1.96) -> tuple[float, float]:
    """The 95% Wilson score interval for ``passed`` of ``total``."""
    if total == 0:
        return (0.0, 1.0)
    share = passed / total
    denominator = 1 + z * z / total
    centre = (share + z * z / (2 * total)) / denominator
    half = z * math.sqrt(share * (1 - share) / total + z * z / (4 * total * total)) / denominator
    return (max(0.0, centre - half), min(1.0, centre + half))


def paired(
    cases: Sequence[PlannerCase],
    first: Sequence[CaseRun],
    second: Sequence[CaseRun],
) -> dict[str, dict[str, Any]]:
    """Per split, the cases each planner passed alone, and McNemar's p for the difference.

    A planner that is deterministic run to run gives one result a case, so the
    unit is the case (passed in at least half its runs), not the case run.
    """
    split_of = {case.case_id: case.split for case in cases}
    adjudicated_ids = {case.case_id for case in cases if case.adjudicated is not None}
    out: dict[str, dict[str, Any]] = {}
    for adjudicated in (False, True):
        a = case_passes(first, adjudicated=adjudicated)
        b = case_passes(second, adjudicated=adjudicated)
        shared = sorted(set(a) & set(b))
        for split in (*(name for name, _ in SPLITS), "all"):
            ids = [i for i in shared if split == "all" or split_of[i] == split]
            if not ids or (adjudicated and not adjudicated_ids & set(ids)):
                continue
            only_a = sum(a[i] and not b[i] for i in ids)
            only_b = sum(b[i] and not a[i] for i in ids)
            out[f"{split}:adjudicated" if adjudicated else split] = {
                "cases": len(ids),
                "both": sum(a[i] and b[i] for i in ids),
                "only_first": only_a,
                "only_second": only_b,
                "neither": sum(not a[i] and not b[i] for i in ids),
                "first_interval": wilson_interval(sum(a[i] for i in ids), len(ids)),
                "second_interval": wilson_interval(sum(b[i] for i in ids), len(ids)),
                "p_value": mcnemar_p(only_a, only_b),
            }
    return out


def rescore(report: dict[str, Any], cases: Sequence[PlannerCase]) -> dict[str, Any]:
    """A saved report scored again against the cases' labels and adjudications as they are now.

    Only planners whose observations were saved are scored again; the time,
    tokens and cost of each run stay as recorded.
    """
    by_id = {case.case_id: case for case in cases}
    results_by_planner: dict[str, list[CaseRun]] = {}
    for name, planner in report["planners"].items():
        if "observations" not in planner:
            continue
        missing = {row["id"] for row in planner["observations"]} - set(by_id)
        if missing:
            raise ValueError(f"saved observations of unknown cases: {sorted(missing)}")
        results = [
            scored_run(
                by_id[row["id"]],
                row["run"],
                Observation.from_signature(row["seen"]) if row["seen"] else None,
                error=row["error"],
            )
            for row in planner["observations"]
        ]
        planner.update(scores([by_id[row["id"]] for row in planner["observations"]], results))
        results_by_planner[name] = results
    if len(results_by_planner) == len(
        [planner for planner in report["planners"].values() if "splits" in planner]
    ):
        report["paired"] = _pairs(report, cases, results_by_planner)
    if results_by_planner:
        # A report saved without observations has no adjudicated score to list them by.
        report["adjudications"] = adjudication_rows(cases)
    return report


def _pairs(
    report: dict[str, Any],
    cases: Sequence[PlannerCase],
    results_by_planner: dict[str, list[CaseRun]],
) -> list[dict[str, Any]]:
    names = list(results_by_planner)
    return [
        {
            "first": report["planners"][first]["label"].split(" (")[0],
            "second": report["planners"][second]["label"].split(" (")[0],
            "splits": paired(cases, results_by_planner[first], results_by_planner[second]),
        }
        for index, first in enumerate(names)
        for second in names[index + 1 :]
    ]


def adjudication_rows(cases: Sequence[PlannerCase]) -> list[dict[str, Any]]:
    """The adjudicated cases, for the report: what the label said and what replaced it."""
    return [
        {
            "id": case.case_id,
            "split": case.split,
            "was": {name: case.expect.get(name) for name in item.expect},
            "now": item.expect,
            "rule": item.rule,
            "why": item.why,
        }
        for case in cases
        if (item := case.adjudication) is not None
    ]


def estimate(cases: Sequence[PlannerCase], runs: int, prices: Prices | None) -> dict[str, Any]:
    """Tokens and dollars for an LLM run, from prompt and schema sizes; nothing is called."""
    from financial_analyst_agent.planner import (
        _FOLLOW_UP_PROMPT,
        _SYSTEM_PROMPT,
        FollowUpPlan,
        Plan,
    )

    first = len(_SYSTEM_PROMPT) + len(json.dumps(Plan.model_json_schema()))
    # A follow-up also carries the current analysis spec, a few short lines.
    follow = len(_FOLLOW_UP_PROMPT) + len(json.dumps(FollowUpPlan.model_json_schema())) + 300
    calls = 0
    chars = 0
    for case in cases:
        for index, message in enumerate(case.turns):
            calls += 1
            chars += (first if index == 0 else follow) + len(message)
    input_tokens = math.ceil(chars / _CHARS_PER_TOKEN) * runs
    output_tokens = _ASSUMED_OUTPUT_TOKENS * calls * runs
    return {
        "planner_calls": calls * runs,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cost_usd": prices.cost(input_tokens, output_tokens) if prices else None,
        "note": (
            f"Input from prompt and schema size at ~{_CHARS_PER_TOKEN} characters a token; "
            f"output assumed {_ASSUMED_OUTPUT_TOKENS} tokens a call. Reasoning tokens, if the "
            "model spends them, are billed as output and are not included: run a small "
            "pilot (--limit) to measure them."
        ),
    }


def _pct(value: float | None) -> str:
    return "—" if value is None else f"{value:.0%}"


PROTOCOL = (
    "## Protocol",
    "",
    "Held-out cases measure how a planner generalises only until someone changing a "
    "planner reads them. Each set so far was held out once and then became development "
    "data:",
    "",
    "1. **First set** ([`planner-cases.json`](planner-cases.json), 50 development "
    "cases). Written for the first comparison and labelled before either planner ran. "
    "The planner changes that followed were diagnosed on them.",
    "2. **Second set** ([`planner-cases-v2.json`](planner-cases-v2.json), 72). Written by "
    "a separate session, but its hand-back included the cases, so the engineer saw them "
    "partway through the planner work. It was never held out.",
    "3. **Third set** ([`planner-cases-v3.json`](planner-cases-v3.json), 69). Written blind "
    "by a separate session and held out for the run of 2026-10-03, which scored the rules "
    "planner 91% and the LLM planner 96%. After that run its results were read, one label "
    "changed with a product decision (ADR 0004: a question naming two metrics is answered "
    "with both; recorded in the file's `label_changes`), and the recorded SEC data was "
    "refreshed. Scores on it since are not blind.",
    "4. **Fourth set** ([`planner-cases-held-out-4.json`](planner-cases-held-out-4.json), "
    "66), the held-out split here. Its brief was committed before any case existed "
    "([`held-out-4-brief.md`](held-out-4-brief.md), commit `54a0e22`). A separate Claude "
    "session wrote and labelled the cases from it, reading only `README.md`, `CONTEXT.md` "
    "and ADRs 0004, 0007 and 0008, and the cases were committed (`bc237f0`) before any "
    "planner ran on them. The engineer checked only their format and counts. The cascade "
    "and the significance test were committed (`3ce77ea`) before this run, so neither "
    "was tuned on these cases. A cost estimate just before the run also ran the free "
    "rules planner on them; only its cost line was read.",
    "",
    "Labels are not edited to fit a result. A label found wrong after a run is recorded in "
    "the case file's `label_changes` with the reason, and this report scores the labels as "
    "committed.",
    "",
    "Each planner gets two scores. **As labelled** is the primary one, and the only one "
    "compared across sets. **After adjudication** replaces a label field that disagrees with "
    "a product rule: a rule in the README, `CONTEXT.md` or an ADR as committed before the "
    "case was written, quoted with where it is. A label is not adjudicated because a result "
    "disagrees with it, because a rule was decided after the run, or because every planner "
    "failed it: a shared defect is a failure. Adjudications live in the case file's "
    "`adjudications`, beside the label they replace, and a report lists each one under "
    "Adjudicated labels. Each case run's observation is saved, so an adjudication "
    "made after a paid run is scored with `--from-json` without running a planner again.",
    "",
    "Two limits. The cases were written by a Claude model, and the rules planner was "
    "written with Claude-based coding agents, so shared habits of phrasing may favour the "
    "rules planner; the LLM planner is an OpenAI model. And 66 cases detect only large "
    "differences: McNemar's test needs about six cases passed by one planner alone, and "
    "none by the other, before p falls below 0.05.",
    "",
)


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Rules planner vs LLM planner",
        "",
        f"Generated `{report['generated_at']}` on the recorded runtime, over "
        f"{report['case_count']} cases: {report['scorecard_count']} scorecard questions, "
        f"{report['dev_count']} development cases ([`planner-cases.json`](planner-cases.json), "
        "[`planner-cases-v2.json`](planner-cases-v2.json), "
        "[`planner-cases-v3.json`](planner-cases-v3.json)), and "
        f"{report['held_out_count']} held-out cases "
        "([`planner-cases-held-out-4.json`](planner-cases-held-out-4.json)). Every case was "
        "labelled before a planner ran on it. The held-out cases were written from a brief "
        "frozen first ([`held-out-4-brief.md`](held-out-4-brief.md)) by a separate session, "
        "and were not read by whoever changed a planner until this run; see "
        "[Protocol](#protocol).",
        "",
        *(
            [
                "The planners that call OpenAI ran on the "
                f"{report['paid_split'].lower().replace(' ', '-')} cases only, to keep "
                "within the evaluation budget; the rules planner ran on every case. What "
                "each held-out failure was is in "
                "[held-out-4-findings.md](held-out-4-findings.md).",
                "",
            ]
            if report.get("paid_split")
            else []
        ),
        "Each case is a conversation run end to end with only the planner swapped, and is "
        "scored on the last turn's outcome (answer, clarify or refuse), intent, companies, "
        "metrics, period and operations. A case passes when every labelled field is right.",
        "",
    ]
    for planner in report["planners"].values():
        lines.append(f"## {planner['label']}")
        lines.append("")
        if planner.get("not_run"):
            lines.append(planner["not_run"])
            lines.append("")
            continue
        if "all" not in planner["splits"]:
            lines.append("The budget ran out before one run was complete; nothing is scored.")
            lines.append("")
            continue
        adjudicated = any(row.get("adjudicated_cases") for row in planner["splits"].values())
        lines.append(
            "| Split | Cases | Accuracy | Spread across runs (sd) | Agreement across runs |"
            + (" After adjudication |" if adjudicated else "")
        )
        lines.append("| --- | ---: | ---: | ---: | ---: |" + (" ---: |" if adjudicated else ""))
        for split, label in (*SPLITS, ("all", "All")):
            row = planner["splits"].get(split)
            if row:
                after = (
                    f" {row['adjudicated_accuracy']:.0%} ({row['adjudicated_cases']} adjudicated) |"
                    if row.get("adjudicated_cases")
                    else " — |"
                )
                lines.append(
                    f"| {label} | {row['cases']} | {row['accuracy']:.0%} | "
                    f"{row['accuracy_sd']:.1%} | {_pct(row['agreement'])} |"
                    + (after if adjudicated else "")
                )
        fields = planner["splits"]["all"]["fields"]
        lines.append("")
        lines.append(
            "Field accuracy: "
            + ", ".join(f"{field_name} {value:.0%}" for field_name, value in fields.items())
            + "."
        )
        if planner.get("stopped_in_run") is not None:
            lines.append(
                f"The budget ran out during run {planner['stopped_in_run'] + 1}: that run is "
                f"left out, and the figures count the {planner['runs']} complete runs only."
            )
        if planner.get("llm_calls") is not None:
            lines.append(
                f"It sent {planner['llm_calls']} of {planner['planner_calls']} planner calls "
                f"({planner['llm_calls'] / max(planner['planner_calls'], 1):.0%}) to the LLM "
                "planner, where the rules planner was unsure."
            )
        cost = planner["cost_usd"]
        lines.append(
            f"Planner time p50 / p95: {planner['planner_ms_p50']:.0f} ms / "
            f"{planner['planner_ms_p95']:.0f} ms over {planner['planner_calls']} calls"
            + (
                f"; {planner['input_tokens']:,} input and "
                f"{planner['output_tokens']:,} output tokens "
                f"({planner['reasoning_tokens']:,} reasoning), ${cost:.2f} in all, "
                f"${planner['cost_per_planner_call_usd']:.4f} a call."
                if cost is not None
                else "."
            )
        )
        failures = planner["failures"]
        if failures:
            lines.append("")
            lines.append("<details><summary>Cases it got wrong</summary>")
            lines.append("")
            for failure in failures:
                why = failure["error"] or ", ".join(failure["wrong"])
                if failure.get("passes_adjudicated"):
                    why += "; passes after adjudication"
                lines.append(f"- `{failure['id']}` (run {failure['run'] + 1}): {why}")
            lines.append("")
            lines.append("</details>")
        lines.append("")
    if report.get("paired"):
        lines.append("## Is the difference real?")
        lines.append("")
        lines.append(
            "Each pair of planners on the same cases: how many cases each passed alone, and "
            "the two-sided exact McNemar p-value for the difference. Both planners are "
            "deterministic run to run, so a case counts once. Accuracies are given with "
            "95% Wilson intervals."
        )
        lines.append("")
        lines.append(
            "| Planners | Split | Cases | Both pass | Only first | Only second | Neither | "
            "First (95% CI) | Second (95% CI) | p |"
        )
        lines.append("| --- | --- | ---: | ---: | ---: | ---: | ---: | --- | --- | ---: |")
        labels = dict((*SPLITS, ("all", "All")))
        labels |= {f"{key}:adjudicated": f"{label}, adjudicated" for key, label in labels.items()}
        for pair in report["paired"]:
            rows = pair["splits"]
            labelled = [split for split in rows if not split.endswith(":adjudicated")]
            if len(labelled) == 2 and "all" in labelled:
                # Both planners ran on one split only: its "All" row would repeat it.
                rows = {split: row for split, row in rows.items() if not split.startswith("all")}
            for split, row in rows.items():
                first = row["first_interval"]
                second = row["second_interval"]
                a_share = (row["both"] + row["only_first"]) / row["cases"]
                b_share = (row["both"] + row["only_second"]) / row["cases"]
                lines.append(
                    f"| {pair['first']} vs {pair['second']} | {labels[split]} | {row['cases']} "
                    f"| {row['both']} | {row['only_first']} | {row['only_second']} | "
                    f"{row['neither']} | {a_share:.0%} ({first[0]:.0%}–{first[1]:.0%}) | "
                    f"{b_share:.0%} ({second[0]:.0%}–{second[1]:.0%}) | "
                    f"{row['p_value']:.2f} |"
                )
        lines.append("")
    if report.get("adjudications"):
        lines.append("## Adjudicated labels")
        lines.append("")
        lines.append(
            "Each label field below disagrees with a product rule committed before the case "
            "was written. The label stays as committed and is what the accuracy above "
            "scores; the adjudicated score replaces the field. See [Protocol](#protocol)."
        )
        lines.append("")
        lines.append("| Case | Split | Label | Adjudicated | Rule | Why |")
        lines.append("| --- | --- | --- | --- | --- | --- |")
        split_labels = dict(SPLITS)
        for row in report["adjudications"]:
            lines.append(
                f"| `{row['id']}` | {split_labels[row['split']]} | "
                f"`{json.dumps(row['was'])}` | `{json.dumps(row['now'])}` | "
                f"{row['rule']} | {row['why']} |"
            )
        lines.append("")
    lines.extend(PROTOCOL)
    if report.get("estimate"):
        est = report["estimate"]
        lines.append("## Estimated cost of an LLM run")
        lines.append("")
        priced = (
            f": about **${est['cost_usd']:.2f}** at ${report['prices']['input']} / "
            f"${report['prices']['output']} per million input / output tokens"
            if est["cost_usd"] is not None
            else " (give --input-price and --output-price to price it)"
        )
        lines.append(
            f"{est['planner_calls']} planner calls, about {est['input_tokens']:,} input and "
            f"{est['output_tokens']:,} output tokens{priced}. {est['note']}"
        )
        lines.append("")
    lines.append(
        "The rules planner is deterministic, so its spread is zero by construction. The "
        "recorded runtime replays SEC data, so the comparison isolates planning; it says "
        "nothing about EDGAR freshness. See [the scorecard](scorecard.md) and "
        "[figures checked against their filings](filing-check.md)."
    )
    lines.append("")
    return "\n".join(lines)


def _llm_completer(usage: Usage, prices: Prices, budget: float) -> Any:
    import openai

    from financial_analyst_agent.config import get_settings
    from financial_analyst_agent.planner import OpenAIStructuredCompleter

    settings = get_settings()
    base_url = settings.openai_base_url.strip() or None
    client = openai.OpenAI(api_key=settings.require_openai_api_key(), base_url=base_url)
    planner = OpenAIStructuredCompleter(
        MeteredOpenAIClient(client, usage), settings.require_openai_model()
    )

    def check_budget() -> None:
        if prices.cost(usage.input_tokens, usage.output_tokens) >= budget:
            raise BudgetExceeded(f"spent ${budget:.2f}")

    return MeteredCompleter(
        planner, usage, before_call=check_budget
    ), settings.require_openai_model()


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--planners", default="rules", help="any of rules, llm and cascade, comma-separated"
    )
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument(
        "--split", choices=("all", *(name for name, _ in SPLITS)), default="all"
    )
    parser.add_argument("--limit", type=int, default=0, help="only the first N cases (a pilot)")
    parser.add_argument(
        "--paid-split",
        choices=[name for name, _ in SPLITS],
        help="run the planners that call OpenAI on this split only; rules runs on all",
    )
    parser.add_argument("--input-price", type=float, help="USD per million input tokens")
    parser.add_argument("--output-price", type=float, help="USD per million output tokens")
    parser.add_argument("--budget-usd", type=float, help="stop the LLM run once this is spent")
    parser.add_argument("--estimate", action="store_true", help="price an LLM run; call nothing")
    parser.add_argument("--no-write", action="store_true", help="print, do not write the report")
    parser.add_argument(
        "--from-json",
        action="store_true",
        help="render the report again from planner-comparison.json; run nothing",
    )
    args = parser.parse_args(argv)
    if args.from_json:
        saved = rescore(json.loads(REPORT_JSON_PATH.read_text(encoding="utf-8")), load_cases())
        REPORT_PATH.write_text(render_markdown(saved), encoding="utf-8")
        REPORT_JSON_PATH.write_text(
            json.dumps(saved, indent=2, default=str) + "\n", encoding="utf-8"
        )
        return

    cases = load_cases()
    if args.split != "all":
        cases = [case for case in cases if case.split == args.split]
    if args.limit:
        cases = cases[: args.limit]
    planners = [name.strip() for name in args.planners.split(",") if name.strip()]
    prices = (
        Prices(args.input_price, args.output_price)
        if args.input_price is not None and args.output_price is not None
        else None
    )
    calls_openai = bool({"llm", "cascade"} & set(planners))
    if calls_openai and prices is None:
        parser.error("--input-price and --output-price are required for the LLM planner")
    if calls_openai and not args.budget_usd:
        parser.error("--budget-usd is required to run the LLM planner")

    report: dict[str, Any] = {
        "generated_at": datetime.now(UTC).isoformat(),
        "case_count": len(cases),
        "scorecard_count": sum(case.split == "scorecard" for case in cases),
        "dev_count": sum(case.split == "dev" for case in cases),
        "held_out_count": sum(case.split == "held_out" for case in cases),
        "planners": {},
    }
    if prices is not None:
        report["prices"] = {"input": prices.input, "output": prices.output}
    paid_cases = cases
    if args.paid_split:
        paid_cases = [case for case in cases if case.split == args.paid_split]
        report["paid_split"] = dict(SPLITS)[args.paid_split]
    runtime = recorded_runtime()
    results_by_planner: dict[str, list[CaseRun]] = {}
    spent = 0.0
    if "rules" in planners:
        usage = Usage()
        results = run_planner(
            cases, MeteredCompleter(runtime.completer, usage), runs=args.runs, runtime=runtime
        )
        results_by_planner["rules"] = results
        report["planners"]["rules"] = {
            "label": "Rules planner",
            **summarize(cases, results, usage, None),
        }
    if "llm" in planners:
        assert prices is not None and args.budget_usd
        usage = Usage()
        completer, model = _llm_completer(usage, prices, args.budget_usd)
        results = run_planner(paid_cases, completer, runs=args.runs, runtime=runtime)
        spent += prices.cost(usage.input_tokens, usage.output_tokens)
        results_by_planner["llm"] = results
        report["planners"]["llm"] = {
            "label": f"LLM planner (`{model}`)",
            **summarize(paid_cases, results, usage, prices),
        }
    else:
        report["planners"]["llm"] = {
            "label": "LLM planner",
            "not_run": "Not run: it calls OpenAI on the configured key, and needs a budget.",
        }
    if "cascade" in planners:
        assert prices is not None and args.budget_usd
        llm_usage = Usage()
        llm, model = _llm_completer(llm_usage, prices, args.budget_usd - spent)
        ranking = runtime.ranking
        assert isinstance(ranking, SnapshotRanking)
        usage = Usage()
        cascade = CascadeCompleter(runtime.completer, llm, ranking.knows_industry)
        results = run_planner(
            paid_cases, MeteredCompleter(cascade, usage), runs=args.runs, runtime=runtime
        )
        # Time is the whole cascade's; tokens and dollars are its LLM calls'.
        usage.input_tokens = llm_usage.input_tokens
        usage.output_tokens = llm_usage.output_tokens
        usage.reasoning_tokens = llm_usage.reasoning_tokens
        results_by_planner["cascade"] = results
        report["planners"]["cascade"] = {
            "label": f"Cascade (rules planner, then `{model}` where it is unsure)",
            "llm_calls": llm_usage.calls,
            **summarize(paid_cases, results, usage, prices),
        }
    report["paired"] = _pairs(report, cases, results_by_planner)
    report["adjudications"] = adjudication_rows(cases)
    if args.estimate:
        report["estimate"] = estimate(cases, args.runs, prices)

    markdown = render_markdown(report)
    if args.no_write:
        print(markdown)
        return
    REPORT_PATH.write_text(markdown, encoding="utf-8")
    REPORT_JSON_PATH.write_text(json.dumps(report, indent=2, default=str) + "\n", encoding="utf-8")
    for name, planner in report["planners"].items():
        if "splits" in planner:
            overall = planner["splits"]["all"]
            print(f"{name}: {overall['accuracy']:.0%} over {overall['cases']} cases")
    if "estimate" in report:
        est = report["estimate"]
        priced = f", ${est['cost_usd']:.2f}" if est["cost_usd"] is not None else ""
        print(
            f"estimate: {est['planner_calls']} calls, {est['input_tokens']:,} input and "
            f"{est['output_tokens']:,} output tokens{priced}"
        )


if __name__ == "__main__":
    main()
