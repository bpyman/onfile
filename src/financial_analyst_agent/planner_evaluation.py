"""Compare the rules planner with the LLM planner on the same questions.

Each case is a conversation run end to end on the recorded runtime: SEC facts,
rankings and news are replayed, and only the planner changes. So a score is
what a visitor would get from that planner, after the shared guards, period
reading and resolution, not the planner's raw output. Cases are labelled in
``docs/evaluation/``: the scorecard's questions and the development cases in
``planner-cases.json`` and ``planner-cases-v2.json``, and the held-out cases in
``planner-cases-held-out.json``. Held-out cases were written by a separate
session after the planner changes they measure, and nobody changing a planner
read them before they were run.

The rules planner is free and deterministic. The LLM planner calls OpenAI on
the configured key, so it runs only when asked, with prices and a budget given
on the command line; ``--estimate`` prices a run without calling anything.

    uv run python -m financial_analyst_agent.planner_evaluation              # rules only
    uv run python -m financial_analyst_agent.planner_evaluation --estimate \\
        --runs 3 --input-price 1.25 --output-price 10
    uv run python -m financial_analyst_agent.planner_evaluation --planners rules,llm \\
        --runs 3 --input-price 1.25 --output-price 10 --budget-usd 5
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
from financial_analyst_agent.runtime import recorded_runtime
from financial_analyst_agent.thread_store import EphemeralThreadStore

CASES_PATH = Path("docs/evaluation/planner-cases.json")
CASE_PATHS = (
    CASES_PATH,
    Path("docs/evaluation/planner-cases-v2.json"),
    Path("docs/evaluation/planner-cases-held-out.json"),
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
# recorded filings: a gap in the data, not in planning.
_NO_DATA_CODES = frozenset({"unsupported_quarterly_fact", "missing_fact"})


@dataclass(frozen=True)
class PlannerCase:
    case_id: str
    split: str
    category: str
    turns: tuple[str, ...]
    expect: dict[str, Any]


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
    cases = [
        PlannerCase(
            case_id=raw["id"],
            split=raw["split"],
            category=raw["category"],
            turns=tuple(raw["turns"]),
            expect=dict(raw["expect"]),
        )
        for path in chosen
        for raw in json.loads(path.read_text(encoding="utf-8"))["cases"]
    ]
    splits = {case.split for case in cases} - {split for split, _ in SPLITS}
    if splits:
        raise ValueError(f"unknown splits: {sorted(splits)}")
    unknown = {key for case in cases for key in case.expect} - set(FIELDS)
    if unknown:
        raise ValueError(f"unknown expectation fields: {sorted(unknown)}")
    if len({case.case_id for case in cases}) != len(cases):
        raise ValueError("case ids must be unique")
    return cases


def observe(turn: ConversationTurn) -> Observation:
    result = turn.result
    spec = turn.analysis_spec
    codes = {
        trace.provenance["error"].get("code")
        for trace in result.tool_traces
        if isinstance(trace.provenance.get("error"), dict)
    }
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
    # A comparison shows growth as year-over-year rows rather than an operation.
    if any(row.comparison == "year_over_year" for row in result.table_rows):
        operations |= {"year_over_year"}
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

    @property
    def passed(self) -> bool:
        return not self.error and bool(self.checks) and all(self.checks.values())


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
                CaseRun(
                    case_id=case.case_id,
                    run=run,
                    checks=score(case.expect, seen),
                    signature=seen.signature() if seen else None,
                    turn_ms=(time.perf_counter() - started) * 1000,
                    error=error,
                )
            )
            if error == "budget reached":
                # A run cut short would be averaged as if complete: keep only the
                # complete runs, and one marker that says the budget ran out.
                kept = [result for result in results if result.run != run]
                return [*kept, replace(results[-1], checks={}, signature=None)]
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
    split_of = {case.case_id: case.split for case in cases}
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
            "fields": fields,
            "agreement": agreement,
        }
    cost = prices.cost(usage.input_tokens, usage.output_tokens) if prices else None
    return {
        "splits": splits,
        "runs": len(runs),
        # The run the budget ran out in, left out of every figure above.
        "stopped_in_run": stopped[0].run if stopped else None,
        "case_runs": len(results),
        "planner_calls": usage.calls,
        "planner_ms_p50": _percentile(usage.planner_ms, 0.5),
        "planner_ms_p95": _percentile(usage.planner_ms, 0.95),
        "turn_ms_p50": _percentile([r.turn_ms for r in results], 0.5),
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "reasoning_tokens": usage.reasoning_tokens,
        "cost_usd": cost,
        "cost_per_planner_call_usd": cost / usage.calls
        if cost is not None and usage.calls
        else None,
        "failures": [
            {
                "id": r.case_id,
                "run": r.run,
                "error": r.error,
                "wrong": sorted(k for k, v in r.checks.items() if not v),
            }
            for r in results
            if not r.passed
        ],
    }


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


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        "# Rules planner vs LLM planner",
        "",
        f"Generated `{report['generated_at']}` on the recorded runtime, over "
        f"{report['case_count']} cases: {report['scorecard_count']} scorecard questions and "
        f"{report['dev_count']} development cases ([`planner-cases.json`](planner-cases.json), "
        "[`planner-cases-v2.json`](planner-cases-v2.json)), and "
        f"{report['held_out_count']} held-out cases "
        "([`planner-cases-held-out.json`](planner-cases-held-out.json)). Every case was "
        "labelled before a planner ran on it. The held-out cases were written by a separate "
        "session after the planner changes, and were not read by whoever changed a planner "
        "until this run.",
        "",
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
        lines.append(
            "| Split | Cases | Accuracy | Spread across runs (sd) | Agreement across runs |"
        )
        lines.append("| --- | ---: | ---: | ---: | ---: |")
        for split, label in (*SPLITS, ("all", "All")):
            row = planner["splits"].get(split)
            if row:
                lines.append(
                    f"| {label} | {row['cases']} | {row['accuracy']:.0%} | "
                    f"{row['accuracy_sd']:.1%} | {_pct(row['agreement'])} |"
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
                lines.append(f"- `{failure['id']}` (run {failure['run'] + 1}): {why}")
            lines.append("")
            lines.append("</details>")
        lines.append("")
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
        "The held-out cases measure how a planner generalises only while no planner is "
        "tuned on them: once a planner is changed because of them, they become development "
        "cases and a fresh held-out set is written before comparing again. "
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
    parser.add_argument("--planners", default="rules", help="rules, llm, or rules,llm")
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument(
        "--split", choices=("all", *(name for name, _ in SPLITS)), default="all"
    )
    parser.add_argument("--limit", type=int, default=0, help="only the first N cases (a pilot)")
    parser.add_argument("--input-price", type=float, help="USD per million input tokens")
    parser.add_argument("--output-price", type=float, help="USD per million output tokens")
    parser.add_argument("--budget-usd", type=float, help="stop the LLM run once this is spent")
    parser.add_argument("--estimate", action="store_true", help="price an LLM run; call nothing")
    parser.add_argument("--no-write", action="store_true", help="print, do not write the report")
    args = parser.parse_args(argv)

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
    if "llm" in planners and prices is None:
        parser.error("--input-price and --output-price are required for the LLM planner")
    if "llm" in planners and not args.budget_usd:
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
    runtime = recorded_runtime()
    if "rules" in planners:
        usage = Usage()
        results = run_planner(
            cases, MeteredCompleter(runtime.completer, usage), runs=args.runs, runtime=runtime
        )
        report["planners"]["rules"] = {
            "label": "Rules planner",
            **summarize(cases, results, usage, None),
        }
    if "llm" in planners:
        assert prices is not None and args.budget_usd
        usage = Usage()
        completer, model = _llm_completer(usage, prices, args.budget_usd)
        results = run_planner(cases, completer, runs=args.runs, runtime=runtime)
        report["planners"]["llm"] = {
            "label": f"LLM planner (`{model}`)",
            **summarize(cases, results, usage, prices),
        }
    else:
        report["planners"]["llm"] = {
            "label": "LLM planner",
            "not_run": "Not run: it calls OpenAI on the configured key, and needs a budget.",
        }
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
