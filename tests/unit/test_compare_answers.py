"""compare_answers replays the evaluation and phrase-coverage conversations, and its own only
when neither source has them; a conversation only one run replays is skipped and counted."""

import importlib.util
from pathlib import Path
from types import ModuleType

import pytest

from financial_analyst_agent.phrase_coverage import cases as phrase_cases
from financial_analyst_agent.planner_evaluation import load_cases

ROOT = Path(__file__).resolve().parents[2]


def _script(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_extra_conversations_are_ones_neither_source_replays() -> None:
    module = _script("compare_answers")
    replayed = {tuple(case.turns) for case in phrase_cases()}
    replayed |= {tuple(case.turns) for case in load_cases() if case.split != "held_out"}

    assert [messages for messages in module.EXTRA if tuple(messages) in replayed] == []
    assert len(module.EXTRA) == len({tuple(messages) for messages in module.EXTRA})


def test_a_conversation_only_one_run_replays_is_skipped_and_counted(
    capsys: pytest.CaptureFixture[str],
) -> None:
    module = _script("compare_answers")
    before = {"case:a": {"answers": [1]}, "extra:gone": {"answers": [2]}}
    after = {"case:a": {"answers": [1]}, "phrase:new": {"answers": [3]}}

    assert module.report(before, after, "master", shown=20) == 0
    out = capsys.readouterr().out
    assert "0 of 1 conversations differ from master." in out
    assert "1 conversation master does not replay" in out
    assert "1 conversation the working tree no longer replays" in out


def test_a_shared_conversation_that_differs_is_listed(capsys: pytest.CaptureFixture[str]) -> None:
    module = _script("compare_answers")
    before = {"case:a": {"answers": [1]}}
    after = {"case:a": {"answers": [2]}}

    assert module.report(before, after, "HEAD", shown=20) == 1
    out = capsys.readouterr().out
    assert "1 of 1 conversations differ from HEAD." in out
    assert "== case:a" in out
    assert "skipped" not in out
