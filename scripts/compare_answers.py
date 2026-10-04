"""Compare what the recorded demo answers, before and after a change.

Replays every planner evaluation conversation, and a few more aimed at
per-company state (calendars, windows, companies outside the snapshot), on the
recorded runtime: once in the working tree and once at a git ref (``HEAD`` by
default, so the change under way). Each answer's presentation, chips and
resolved spec are compared, and every conversation that differs is listed with
the fields that changed.

A change meant to leave the answers alone must show none; one meant to change
them shows only the conversations it should. The two runs share a day, so
wording that reads today's date ("since 2023") does not differ between them.

Usage:
    uv run python scripts/compare_answers.py               # working tree vs HEAD
    uv run python scripts/compare_answers.py --against REF # working tree vs REF
Exits 1 when any conversation differs.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import uuid
from dataclasses import asdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parent.parent

# Beyond the evaluation cases: the per-company state a spec keys by company
# (quarter dates, calendars, named periods), companies outside the snapshot,
# shared names and edits.
EXTRA = [
    ["Tesla vs GM revenue last 4 quarters"],
    ["Apple and Microsoft revenue last 4 quarters"],
    ["Apple, Microsoft and NVIDIA net margin last 6 quarters"],
    ["How is Apple doing?"],
    ["How is Tesla doing?"],
    ["Compare Google and GOOGL revenue"],
    ["Google revenue", "add GOOGL"],
    ["Apple revenue Q1 2025"],
    ["Apple and Microsoft revenue fiscal 2025"],
    ["Apple and Microsoft revenue calendar Q2 2026"],
    ["Apple revenue growth last 4 quarters"],
    ["Apple revenue", "add Tesla", "last 4 quarters"],
    ["Walmart vs Apple revenue"],
    ["Acme Widgets revenue"],
    ["Apple and Acme Widgets revenue"],
    ["Apple cash"],
    ["Apple revenue", "what about Microsoft", "and Tesla"],
    ["Top 5 banks by net income", "add Apple"],
    ["Lincoln revenue", "LNC"],
    ["Coca-Cola revenue", "KO"],
    ["Tesla P/E"],
    ["Apple and Tesla return on equity"],
    ["NVIDIA diluted EPS last 8 quarters"],
    ["Apple revenue", "remove Apple"],
    ["Apple and Microsoft revenue", "remove Microsoft"],
]


def dump(out: Path) -> None:
    """Every conversation's answers, chips and spec, from the tree this runs in."""
    from financial_analyst_agent.conversation import run_conversation_turn, start_thread
    from financial_analyst_agent.planner_evaluation import load_cases
    from financial_analyst_agent.presentation import present_turn, spec_chips
    from financial_analyst_agent.runtime import RuntimeKind, recorded_runtime
    from financial_analyst_agent.thread_store import EphemeralThreadStore

    def replay(messages: list[str]) -> dict[str, Any]:
        runtime = recorded_runtime()
        store = EphemeralThreadStore()
        thread = f"compare-{uuid.uuid4().hex}"
        start_thread(thread, RuntimeKind.RECORDED, store=store)
        answers = [
            asdict(
                present_turn(run_conversation_turn(thread, message, runtime, store=store).result)
            )
            for message in messages
        ]
        state = store.load(thread)
        spec = state.analysis_spec if state is not None else None
        return {
            "answers": answers,
            "chips": list(spec_chips(spec)) if spec is not None else [],
            "spec": spec.model_dump(mode="json") if spec is not None else None,
        }

    conversations: dict[str, Any] = {}
    for case in load_cases():
        conversations[f"case:{case.case_id}"] = replay(list(case.turns))
    for messages in EXTRA:
        conversations["extra:" + " | ".join(messages)] = replay(messages)
    out.write_text(json.dumps(conversations, sort_keys=True, default=str), encoding="utf-8")


def _differences(before: Any, after: Any, path: str = "") -> list[tuple[str, Any, Any]]:
    if type(before) is not type(after):
        return [(path, before, after)]
    if isinstance(before, dict):
        return [
            difference
            for key in sorted(set(before) | set(after))
            for difference in _differences(before.get(key), after.get(key), f"{path}.{key}")
        ]
    if isinstance(before, list):
        found = [(f"{path}[len]", len(before), len(after))] if len(before) != len(after) else []
        for index, (old, new) in enumerate(zip(before, after, strict=False)):
            found.extend(_differences(old, new, f"{path}[{index}]"))
        return found
    return [] if before == after else [(path, before, after)]


def _dump_tree(root: Path, out: Path) -> None:
    """Run ``dump`` with ``root``'s own code and evaluation cases."""
    subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), "--dump", str(out), "--root", str(root)],
        cwd=root,
        check=True,
    )


def compare(against: str, shown: int) -> int:
    with tempfile.TemporaryDirectory(prefix="compare-answers-") as scratch:
        scratch_dir = Path(scratch)
        worktree = scratch_dir / "ref"
        subprocess.run(
            ["git", "worktree", "add", "--quiet", "--detach", str(worktree), against],
            cwd=ROOT,
            check=True,
        )
        try:
            _dump_tree(worktree, scratch_dir / "before.json")
        finally:
            subprocess.run(
                ["git", "worktree", "remove", "--force", str(worktree)], cwd=ROOT, check=False
            )
        _dump_tree(ROOT, scratch_dir / "after.json")
        before = json.loads((scratch_dir / "before.json").read_text(encoding="utf-8"))
        after = json.loads((scratch_dir / "after.json").read_text(encoding="utf-8"))

    changed = {
        name: found
        for name in sorted(set(before) | set(after))
        if (found := _differences(before.get(name), after.get(name)))
    }
    print(f"{len(changed)} of {len(after)} conversations differ from {against}.")
    for name, found in list(changed.items())[:shown]:
        print(f"\n== {name}")
        for path, old, new in found[:6]:
            print(f"   {path}\n     - {str(old)[:160]}\n     + {str(new)[:160]}")
        if len(found) > 6:
            print(f"   … and {len(found) - 6} more")
    if len(changed) > shown:
        print(f"\n… and {len(changed) - shown} more conversations.")
    return 1 if changed else 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("--against", default="HEAD", help="git ref to compare with (default HEAD)")
    parser.add_argument("--show", type=int, default=20, help="conversations to show in detail")
    parser.add_argument("--dump", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--root", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.dump is not None:
        # The tree's own package, not whichever one the environment installed.
        sys.path[:0] = [str(args.root / "src")]
        dump(args.dump)
        return 0
    return compare(args.against, args.show)


if __name__ == "__main__":
    raise SystemExit(main())
