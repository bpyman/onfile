"""The offline scripts read the app's snapshot paths and submissions columns."""

import importlib.util
from pathlib import Path
from types import ModuleType

from financial_analyst_agent.providers.sec.submissions import KEPT_COLUMNS
from financial_analyst_agent.rules_planner import FIXTURE_UNIVERSE_SNAPSHOT_PATH
from financial_analyst_agent.universe import DEFAULT_SNAPSHOT_PATH

ROOT = Path(__file__).resolve().parents[2]


def _script(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_record_sec_fixtures_uses_the_apps_snapshots_and_columns() -> None:
    module = _script("record_sec_fixtures")
    assert module.LIVE_SNAPSHOT is DEFAULT_SNAPSHOT_PATH
    assert module.FIXTURE_SNAPSHOT is FIXTURE_UNIVERSE_SNAPSHOT_PATH
    assert module.KEPT_COLUMNS is KEPT_COLUMNS


def test_trim_sec_test_fixture_keeps_the_apps_columns() -> None:
    assert _script("trim_sec_test_fixture").KEPT_COLUMNS is KEPT_COLUMNS


def test_build_everyday_words_reads_the_live_snapshot() -> None:
    assert _script("build_everyday_words").SNAPSHOT is DEFAULT_SNAPSHOT_PATH
