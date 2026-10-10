"""Essay evaluation: essay instructions compared blind against a frozen rubric.

The plan is ``docs/evaluation/essay-plan.md`` and the rubric ``essay-rubric.md``.
An arm is a set of instructions on a model, written ``v1@gpt-6.1-sol``. Cases and
their frozen grounding live in ``essay-cases-dev.json`` and
``essay-cases-held-out.json``; essays, judgements and spend go under
``docs/evaluation/essays/``.

    uv run python -m financial_analyst_agent.essay_evaluation capture --set held-out
    uv run python -m financial_analyst_agent.essay_evaluation generate --arm v1@gpt-6.1-sol \\
        --set dev --samples 2 --estimate
    uv run python -m financial_analyst_agent.essay_evaluation judge --a v2@gpt-6.1-sol \\
        --b v1@gpt-6.1-sol --set dev
    uv run python -m financial_analyst_agent.essay_evaluation report --a v2@gpt-6.1-sol \\
        --b v1@gpt-6.1-sol --set held-out

Generation calls OpenAI and is charged against ``BUDGET``; judging calls the
``claude`` CLI. Neither runs in tests.
"""

from __future__ import annotations

import argparse
import json
import math
import random
import re
import subprocess
import tempfile
from collections.abc import Callable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from financial_analyst_agent.contracts import ToolTrace
from financial_analyst_agent.essay import INSTRUCTION_SETS, EssayInstructions, essay_request
from financial_analyst_agent.numeral_lock import numeral_lock_extras

ROOT = Path(__file__).resolve().parents[2]
EVALUATION = ROOT / "docs" / "evaluation"
ESSAYS = EVALUATION / "essays"
CASE_FILES = {
    "dev": EVALUATION / "essay-cases-dev.json",
    "held-out": EVALUATION / "essay-cases-held-out.json",
}
RUBRIC = EVALUATION / "essay-rubric.md"
SPEND = ESSAYS / "spend.json"
# The plan's cap on OpenAI spend for the whole evaluation, in US dollars.
BUDGET = 14.35
# US dollars per million tokens, for every model the arms use.
PRICES = {"gpt-5.6-terra": (2.0, 12.0), "gpt-6.1-sol": (2.0, 12.0)}
JUDGE_MODEL = "claude-sonnet-5-5"
CRITERIA = ("answers", "accuracy", "analysis", "clarity", "calibration")
GATES = ("citations", "no_advice", "faithful")

Kind = Literal["explain", "analysis", "news"]
Preference = Literal["A", "B", "tie"]


@dataclass(frozen=True)
class EssayCase:
    id: str
    kind: Kind
    turns: tuple[str, ...]
    note: str
    grounding: str = ""

    @property
    def question(self) -> str:
        """What the essay answers: the last turn (an analysis case's first turn is the table)."""
        return self.turns[-1]


@dataclass(frozen=True)
class Arm:
    version: str
    model: str

    @classmethod
    def parse(cls, name: str) -> Arm:
        version, _, model = name.partition("@")
        if version not in INSTRUCTION_SETS or model not in PRICES:
            raise SystemExit(
                f"unknown arm {name!r}: versions {sorted(INSTRUCTION_SETS)}, "
                f"models {sorted(PRICES)}"
            )
        return cls(version, model)

    @property
    def name(self) -> str:
        return f"{self.version}@{self.model}"

    @property
    def instructions(self) -> EssayInstructions:
        return INSTRUCTION_SETS[self.version]


@dataclass
class Essay:
    case_id: str
    sample: int
    arm: str
    essay: str
    input_tokens: int
    output_tokens: int
    cost: float
    numeral_lock_extras: list[str] = field(default_factory=list)

    @property
    def withheld(self) -> bool:
        return bool(self.numeral_lock_extras)


# --- cases and grounding -------------------------------------------------------------


def load_cases(split: str) -> list[EssayCase]:
    raw = json.loads(CASE_FILES[split].read_text(encoding="utf-8"))
    return [
        EssayCase(c["id"], c["kind"], tuple(c["turns"]), c.get("note", ""), c.get("grounding", ""))
        for c in raw["cases"]
    ]


def capture(split: str, *, only: Sequence[str] = ()) -> list[str]:
    """Freeze each case's grounding: an analysis case's table, a news case's search results.

    Analysis tables come from the recorded runtime; news from one live search per
    case. Returns the ids whose grounding came back empty, which need a new question.
    """
    from financial_analyst_agent.config import get_settings
    from financial_analyst_agent.contracts import RuntimeKind
    from financial_analyst_agent.conversation import run_conversation_turn, start_thread
    from financial_analyst_agent.evidence_store import grounding_json_from_result
    from financial_analyst_agent.news import TavilyNewsSearch
    from financial_analyst_agent.runtime import recorded_runtime
    from financial_analyst_agent.thread_store import EphemeralThreadStore
    from financial_analyst_agent.turn import _hits_json, _usable_news_hits

    path = CASE_FILES[split]
    raw = json.loads(path.read_text(encoding="utf-8"))
    recorded = recorded_runtime()
    news = TavilyNewsSearch(get_settings())
    empty = []
    for case in raw["cases"]:
        if only and case["id"] not in only:
            continue
        grounding = ""
        if case["kind"] == "analysis":
            store = EphemeralThreadStore()
            start_thread(case["id"], RuntimeKind.RECORDED, store=store)
            turn = run_conversation_turn(case["id"], case["turns"][0], recorded, store=store)
            grounding = grounding_json_from_result(turn.result)
        elif case["kind"] == "news":
            hits = _usable_news_hits(news.search_news(case["turns"][0]))
            grounding = _hits_json(hits) if hits else ""
        case["grounding"] = grounding
        case["captured_at"] = datetime.now(UTC).isoformat(timespec="seconds")
        if case["kind"] != "explain" and not grounding:
            empty.append(case["id"])
    path.write_text(json.dumps(raw, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return empty


# --- generation ----------------------------------------------------------------------


def lock_json(case: EssayCase) -> str:
    """The grounding the app holds an essay to: the table, the results, or the topic alone."""
    if case.grounding:
        return case.grounding
    return json.dumps(
        [ToolTrace(tool="explain_topic", args={"topic": case.question}).model_dump(mode="json")]
    )


def news_count(case: EssayCase) -> int:
    return len(json.loads(case.grounding)) if case.kind == "news" and case.grounding else 0


def request(case: EssayCase, arm: Arm) -> tuple[str, str]:
    """The instructions and input the app would send for this case."""
    tool_json = case.grounding if case.kind != "explain" else ""
    _, instructions, input_text = essay_request(case.question, tool_json, arm.instructions)
    return instructions, input_text


def spent() -> float:
    if not SPEND.exists():
        return 0.0
    return float(sum(run["cost"] for run in json.loads(SPEND.read_text(encoding="utf-8"))))


def _record_spend(arm: Arm, split: str, essays: Sequence[Essay]) -> None:
    runs = json.loads(SPEND.read_text(encoding="utf-8")) if SPEND.exists() else []
    runs.append(
        {
            "at": datetime.now(UTC).isoformat(timespec="seconds"),
            "arm": arm.name,
            "set": split,
            "essays": len(essays),
            "cost": round(sum(essay.cost for essay in essays), 4),
        }
    )
    SPEND.parent.mkdir(parents=True, exist_ok=True)
    SPEND.write_text(json.dumps(runs, indent=2) + "\n", encoding="utf-8")


def estimate(cases: Sequence[EssayCase], arm: Arm, samples: int, output_tokens: int) -> float:
    """A run's cost: input from the characters sent, output at ``output_tokens`` an essay."""
    price_in, price_out = PRICES[arm.model]
    total = 0.0
    for case in cases:
        instructions, input_text = request(case, arm)
        tokens_in = (len(instructions) + len(input_text)) / 4
        total += samples * (tokens_in * price_in + output_tokens * price_out) / 1_000_000
    return total


def generate(
    cases: Sequence[EssayCase],
    arm: Arm,
    samples: int,
    complete: Callable[[str, str, str], tuple[str, int, int]],
    *,
    workers: int = 4,
) -> list[Essay]:
    """``samples`` essays per case.

    ``complete(model, instructions, input)`` returns the text and its input and output tokens.
    """
    price_in, price_out = PRICES[arm.model]

    def one(job: tuple[EssayCase, int]) -> Essay:
        case, sample = job
        instructions, input_text = request(case, arm)
        text, tokens_in, tokens_out = complete(arm.model, instructions, input_text)
        extras = numeral_lock_extras(text, lock_json(case), hit_count=news_count(case))
        return Essay(
            case.id,
            sample,
            arm.name,
            text,
            tokens_in,
            tokens_out,
            (tokens_in * price_in + tokens_out * price_out) / 1_000_000,
            extras,
        )

    jobs = [(case, sample) for case in cases for sample in range(1, samples + 1)]
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(one, jobs))


def openai_complete() -> Callable[[str, str, str], tuple[str, int, int]]:
    import openai

    from financial_analyst_agent.config import get_settings

    settings = get_settings()
    client = openai.OpenAI(
        api_key=settings.require_openai_api_key(), base_url=settings.openai_base_url.strip() or None
    )

    def complete(model: str, instructions: str, input_text: str) -> tuple[str, int, int]:
        response = client.responses.create(model=model, instructions=instructions, input=input_text)
        usage = response.usage
        if usage is None:
            raise RuntimeError("the response carried no token usage")
        return str(response.output_text), int(usage.input_tokens), int(usage.output_tokens)

    return complete


def essays_path(arm: Arm, split: str) -> Path:
    return ESSAYS / f"{arm.name}--{split}.json"


def load_essays(arm: Arm, split: str) -> list[Essay]:
    raw = json.loads(essays_path(arm, split).read_text(encoding="utf-8"))
    return [Essay(**{k: v for k, v in item.items() if k != "withheld"}) for item in raw["essays"]]


def save_essays(arm: Arm, split: str, essays: Sequence[Essay]) -> None:
    ESSAYS.mkdir(parents=True, exist_ok=True)
    payload = {
        "arm": arm.name,
        "set": split,
        "instructions": asdict(arm.instructions),
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "essays": [{**asdict(essay), "withheld": essay.withheld} for essay in essays],
    }
    essays_path(arm, split).write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


# --- judging -------------------------------------------------------------------------

_PAIR_TASK = """You are judging two answers written by a research assistant for an analyst at a
financial firm. Apply the rubric below exactly.

{rubric}

## The case

Kind: {kind}

{context}
## Answer A

{a}

## Answer B

{b}

## What to return

Judge each gate for each answer, then compare A and B on each criterion and overall.
Return only a JSON object, with no other text:

{{"gates": {{"A": {{"citations": true, "no_advice": true, "faithful": true}},
           "B": {{"citations": true, "no_advice": true, "faithful": true}}}},
 "preference": {{"answers": "A", "accuracy": "tie", "analysis": "B",
                "clarity": "A", "calibration": "tie", "overall": "A"}},
 "reason": "one sentence on the overall preference"}}

Use true for a gate that does not apply (citations outside news).
Each preference is "A", "B" or "tie".
"""

_SCORE_TASK = """You are scoring one answer written by a research assistant for an analyst at a
financial firm. Apply the rubric below exactly.

{rubric}

## The case

Kind: {kind}

{context}
## The answer

{a}

## What to return

Return only a JSON object, with no other text:

{{"gates": {{"citations": true, "no_advice": true, "faithful": true}},
 "scores": {{"answers": 4, "accuracy": 5, "analysis": 3, "clarity": 4, "calibration": 4}},
 "reason": "one sentence"}}

Use true for a gate that does not apply (citations outside news). Scores are integers from 1 to 5.
"""


def _rubric_for_judge() -> str:
    text = RUBRIC.read_text(encoding="utf-8")
    # The judge needs the standard, not the history of changes to it.
    return text.split("\n## Changes", 1)[0].strip()


def case_context(case: EssayCase) -> str:
    """What the judge is shown of a case: the question and the grounding the essay was given."""
    lines = []
    if case.kind == "analysis":
        lines += [
            f"The analyst first asked: {case.turns[0]}",
            "",
            "The table the app showed (JSON rows):",
            "",
            case.grounding or "(none)",
            "",
        ]
        lines += [f"Then asked: {case.question}", ""]
    elif case.kind == "news":
        lines += [
            f"Question: {case.question}",
            "",
            "The search results the answer could use, numbered from 1 (JSON):",
            "",
            case.grounding or "(none)",
            "",
        ]
    else:
        lines += [
            f"Question: {case.question}",
            "",
            "There is no grounding: the answer must use no numerals.",
            "",
        ]
    return "\n".join(lines)


def parse_judgement(text: str) -> dict[str, Any]:
    """The JSON object in a judge's reply, or ValueError."""
    match = re.search(r"\{.*\}", text, re.S)
    if match is None:
        raise ValueError(f"no JSON in judgement: {text[:200]!r}")
    return dict(json.loads(match.group(0)))


def claude_judge(prompt: str) -> str:
    """One judgement from the ``claude`` CLI, with no tools, run outside the repository."""
    with tempfile.TemporaryDirectory() as empty:
        done = subprocess.run(
            ["claude", "-p", "--model", JUDGE_MODEL, "--tools", ""],
            input=prompt,
            capture_output=True,
            text=True,
            encoding="utf-8",
            cwd=empty,
            timeout=600,
        )
    if done.returncode != 0:
        raise RuntimeError(done.stderr[-500:])
    return done.stdout


def _with_retry(judge: Callable[[str], str], prompt: str, tries: int = 3) -> dict[str, Any]:
    error: Exception | None = None
    for _ in range(tries):
        try:
            return parse_judgement(judge(prompt))
        except (ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
            error = exc
    raise RuntimeError(f"judge failed {tries} times: {error}")


def _flip(preference: str) -> str:
    return {"A": "B", "B": "A"}.get(preference, "tie")


def combine(first: dict[str, Any], swapped: dict[str, Any]) -> dict[str, str]:
    """Per criterion, X (the essay shown first as A) or Y, kept only where both orders agree."""
    combined = {}
    for key in (*CRITERIA, "overall"):
        one = first["preference"].get(key, "tie")
        two = _flip(swapped["preference"].get(key, "tie"))
        combined[key] = {"A": "X", "B": "Y"}.get(one, "tie") if one == two else "tie"
    return combined


def judge_pairs(
    cases: Sequence[EssayCase],
    x: Sequence[Essay],
    y: Sequence[Essay],
    judge: Callable[[str], str],
    *,
    workers: int = 4,
    seed: int = 0,
) -> list[dict[str, Any]]:
    """Every same-sample pair of ``x`` and ``y`` essays, judged in both orders."""
    rubric = _rubric_for_judge()
    by_case = {case.id: case for case in cases}
    ys = {(essay.case_id, essay.sample): essay for essay in y}
    pairs = [
        (essay, ys[(essay.case_id, essay.sample)])
        for essay in x
        if (essay.case_id, essay.sample) in ys
    ]
    random.Random(seed).shuffle(pairs)

    def one(pair: tuple[Essay, Essay]) -> dict[str, Any]:
        ex, ey = pair
        case = by_case[ex.case_id]

        def prompt(a: Essay, b: Essay) -> str:
            return _PAIR_TASK.format(
                rubric=rubric, kind=case.kind, context=case_context(case), a=a.essay, b=b.essay
            )

        first = _with_retry(judge, prompt(ex, ey))
        swapped = _with_retry(judge, prompt(ey, ex))
        return {
            "case_id": case.id,
            "kind": case.kind,
            "sample": ex.sample,
            "x": ex.arm,
            "y": ey.arm,
            "preference": combine(first, swapped),
            "gates": {
                "x": first["gates"]["A"],
                "y": first["gates"]["B"],
                "x_swapped": swapped["gates"]["B"],
                "y_swapped": swapped["gates"]["A"],
            },
            "reasons": [first.get("reason", ""), swapped.get("reason", "")],
        }

    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(one, pairs))


def score_essays(
    cases: Sequence[EssayCase],
    essays: Sequence[Essay],
    judge: Callable[[str], str],
    *,
    workers: int = 4,
) -> list[dict[str, Any]]:
    """Each essay's gates and rubric scores, judged alone."""
    rubric = _rubric_for_judge()
    by_case = {case.id: case for case in cases}

    def one(essay: Essay) -> dict[str, Any]:
        case = by_case[essay.case_id]
        result = _with_retry(
            judge,
            _SCORE_TASK.format(
                rubric=rubric, kind=case.kind, context=case_context(case), a=essay.essay
            ),
        )
        return {
            "case_id": essay.case_id,
            "sample": essay.sample,
            "arm": essay.arm,
            "kind": case.kind,
            **result,
        }

    with ThreadPoolExecutor(max_workers=workers) as pool:
        return list(pool.map(one, essays))


# --- statistics ----------------------------------------------------------------------


def sign_test(wins: int, losses: int) -> float:
    """Two-sided exact sign test; ties are left out before calling."""
    n = wins + losses
    if n == 0:
        return 1.0
    k = min(wins, losses)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / 2**n
    return float(min(1.0, 2 * tail))


def case_outcomes(pairs: Sequence[dict[str, Any]], criterion: str = "overall") -> dict[str, int]:
    """Per case, +1 when X wins more of its pairs than Y, −1 when fewer, 0 when equal."""
    net: dict[str, int] = {}
    for pair in pairs:
        side = pair["preference"][criterion]
        net[pair["case_id"]] = net.get(pair["case_id"], 0) + (
            1 if side == "X" else -1 if side == "Y" else 0
        )
    return {case: (net_ > 0) - (net_ < 0) for case, net_ in net.items()}


def bootstrap_mean(
    values_by_case: dict[str, list[float]], *, draws: int = 2000, seed: int = 0
) -> tuple[float, float, float]:
    """The mean over cases (each case's samples averaged), with a 95% interval resampling cases."""
    means = [sum(v) / len(v) for v in values_by_case.values() if v]
    if not means:
        return (math.nan, math.nan, math.nan)
    rng = random.Random(seed)
    resampled = sorted(sum(rng.choice(means) for _ in means) / len(means) for _ in range(draws))
    return (
        sum(means) / len(means),
        resampled[int(0.025 * draws)],
        resampled[int(0.975 * draws) - 1],
    )


def pairwise_summary(pairs: Sequence[dict[str, Any]]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    for criterion in (*CRITERIA, "overall"):
        outcomes = case_outcomes(pairs, criterion).values()
        wins, losses = sum(o > 0 for o in outcomes), sum(o < 0 for o in outcomes)
        summary[criterion] = {
            "x_cases": wins,
            "y_cases": losses,
            "even_cases": len(outcomes) - wins - losses,
            "p": round(sign_test(wins, losses), 4),
            "pairs_x": sum(p["preference"][criterion] == "X" for p in pairs),
            "pairs_y": sum(p["preference"][criterion] == "Y" for p in pairs),
            "pairs_tie": sum(p["preference"][criterion] == "tie" for p in pairs),
        }
    return summary


def gate_rates(essays: Sequence[Essay], scored: Sequence[dict[str, Any]]) -> dict[str, float]:
    rates = {
        "numeral_lock": round(1 - sum(e.withheld for e in essays) / len(essays), 3)
        if essays
        else math.nan
    }
    for gate in GATES:
        values = [bool(s["gates"].get(gate, True)) for s in scored]
        rates[gate] = round(sum(values) / len(values), 3) if values else math.nan
    return rates


# --- command line --------------------------------------------------------------------


def _judgements_path(kind: str, x: Arm, y: Arm | None, split: str) -> Path:
    name = f"{kind}--{x.name}" + (f"--vs--{y.name}" if y else "") + f"--{split}.json"
    return ESSAYS / name


def main(argv: Sequence[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    sub = parser.add_subparsers(dest="command", required=True)
    cap = sub.add_parser("capture", help="freeze analysis tables and news results")
    cap.add_argument("--set", required=True, choices=sorted(CASE_FILES))
    cap.add_argument("--only", nargs="*", default=[])
    gen = sub.add_parser("generate", help="write essays for an arm (paid)")
    gen.add_argument("--arm", required=True)
    gen.add_argument("--set", required=True, choices=sorted(CASE_FILES))
    gen.add_argument("--samples", type=int, default=2)
    gen.add_argument(
        "--output-tokens", type=int, default=1500, help="assumed per essay, for the estimate"
    )
    gen.add_argument("--estimate", action="store_true", help="price the run and stop")
    jud = sub.add_parser("judge", help="judge two arms pairwise")
    jud.add_argument("--a", required=True)
    jud.add_argument("--b", required=True)
    jud.add_argument("--set", required=True, choices=sorted(CASE_FILES))
    sco = sub.add_parser("score", help="score an arm's essays on the rubric")
    sco.add_argument("--arm", required=True)
    sco.add_argument("--set", required=True, choices=sorted(CASE_FILES))
    rep = sub.add_parser("report", help="summarise a pairwise judgement")
    rep.add_argument("--a", required=True)
    rep.add_argument("--b", required=True)
    rep.add_argument("--set", required=True, choices=sorted(CASE_FILES))
    args = parser.parse_args(argv)

    if args.command == "capture":
        empty = capture(args.set, only=args.only)
        print(f"captured {args.set}; empty grounding: {empty or 'none'}")
        return
    split = args.set
    cases = load_cases(split)
    if args.command == "generate":
        arm = Arm.parse(args.arm)
        cost = estimate(cases, arm, args.samples, args.output_tokens)
        left = BUDGET - spent()
        print(
            f"{arm.name} on {split}: {len(cases) * args.samples} essays, estimated ${cost:.2f}; "
            f"${left:.2f} of ${BUDGET:.2f} left"
        )
        if args.estimate:
            return
        if cost > left:
            raise SystemExit("estimate exceeds the budget left; not started")
        essays = generate(cases, arm, args.samples, openai_complete())
        save_essays(arm, split, essays)
        _record_spend(arm, split, essays)
        actual = sum(e.cost for e in essays)
        print(
            f"wrote {len(essays)} essays, ${actual:.2f}; "
            f"withheld by the numeral lock: {sum(e.withheld for e in essays)}"
        )
        return
    if args.command == "judge":
        x, y = Arm.parse(args.a), Arm.parse(args.b)
        pairs = judge_pairs(cases, load_essays(x, split), load_essays(y, split), claude_judge)
        path = _judgements_path("pairs", x, y, split)
        path.write_text(
            json.dumps({"judge": JUDGE_MODEL, "pairs": pairs}, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(json.dumps(pairwise_summary(pairs)["overall"]))
        return
    if args.command == "score":
        arm = Arm.parse(args.arm)
        scored = score_essays(cases, load_essays(arm, split), claude_judge)
        path = _judgements_path("scores", arm, None, split)
        path.write_text(
            json.dumps({"judge": JUDGE_MODEL, "scores": scored}, indent=2, ensure_ascii=False)
            + "\n",
            encoding="utf-8",
        )
        print(f"scored {len(scored)} essays")
        return
    if args.command == "report":
        x, y = Arm.parse(args.a), Arm.parse(args.b)
        pairs = json.loads(_judgements_path("pairs", x, y, split).read_text(encoding="utf-8"))[
            "pairs"
        ]
        print(json.dumps(pairwise_summary(pairs), indent=2))


if __name__ == "__main__":
    main()
