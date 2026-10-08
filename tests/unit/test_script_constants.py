"""The offline scripts read the app's snapshot paths and submissions columns."""

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest

from financial_analyst_agent.domain.enums import PERIODIC_FORMS
from financial_analyst_agent.providers.sec.submissions import KEPT_COLUMNS
from financial_analyst_agent.rules_planner import FIXTURE_UNIVERSE_SNAPSHOT_PATH
from financial_analyst_agent.universe import DEFAULT_SNAPSHOT_PATH, load_universe_snapshot

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


def test_the_scripts_keep_the_apps_periodic_forms() -> None:
    assert _script("record_sec_fixtures").PERIODIC_FORMS is PERIODIC_FORMS
    assert _script("trim_sec_test_fixture").PERIODIC_FORMS is PERIODIC_FORMS


def test_the_fixture_snapshot_takes_the_live_freezes_fields(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = _script("record_sec_fixtures")
    live = {
        "as_of": "2026-09-27T00:00:00Z",
        "companies": [
            {
                "cik": "0000789019",
                "ticker": "MSFT",
                "name": "Microsoft",
                "market_cap": "2",
                "price": "400",
                "sector": "Technology",
                "industry": "Software",
            },
            # A foreign filer with no price, industry or sector recorded.
            {
                "cik": "0000001750",
                "ticker": "AIR",
                "name": "AAR",
                "market_cap": "1",
                "files_quarterly": False,
            },
        ],
    }
    fixture = {
        "as_of": "2026-01-01T00:00:00Z",
        "companies": [
            {
                "cik": "0000789019",
                "ticker": "MSFT",
                "name": "Microsoft",
                "sector": "Old",
                "market_cap": "1",
                "price": "1",
                "industry": "Old",
            },
            {
                "cik": "0000001750",
                "ticker": "AIR",
                "name": "AAR",
                "sector": "Old",
                "market_cap": "1",
                "industry": "Old",
            },
        ],
    }
    live_path = tmp_path / "live.json"
    live_path.write_text(json.dumps(live), encoding="utf-8")
    fixture_path = tmp_path / "fixture.json"
    fixture_path.write_text(json.dumps(fixture, indent=2) + "\n", encoding="utf-8")
    monkeypatch.setattr(module, "LIVE_SNAPSHOT", live_path)
    monkeypatch.setattr(module, "FIXTURE_SNAPSHOT", fixture_path)

    assert module._sync_fixture_snapshot() == "2026-09-27T00:00:00Z"

    written = fixture_path.read_text(encoding="utf-8")
    assert written.endswith("}\n")
    synced = json.loads(written)
    assert synced["as_of"] == "2026-09-27T00:00:00Z"
    msft, air = synced["companies"]
    # The price sits beside the market cap it was quoted with; the other fields keep their place.
    assert list(msft.items()) == [
        ("cik", "0000789019"),
        ("ticker", "MSFT"),
        ("name", "Microsoft"),
        ("sector", "Technology"),
        ("market_cap", "2"),
        ("price", "400"),
        ("industry", "Software"),
    ]
    assert air == {
        "cik": "0000001750",
        "ticker": "AIR",
        "name": "AAR",
        "sector": "",
        "market_cap": "1",
        "industry": "",
        "files_quarterly": False,
    }

    fixture_path.write_text(
        json.dumps({"as_of": "x", "companies": [{"cik": "0000000001", "ticker": "NOPE"}]}),
        encoding="utf-8",
    )
    with pytest.raises(SystemExit, match="NOPE"):
        module._sync_fixture_snapshot()


def test_build_everyday_words_samples_the_snapshot_by_market_cap() -> None:
    module = _script("build_everyday_words")
    companies = load_universe_snapshot(DEFAULT_SNAPSHOT_PATH).companies

    sample = module._sample(5)

    assert len(sample) == len({company.cik for company in sample}) == 5
    caps = [company.market_cap for company in sample]
    assert caps == sorted(caps, reverse=True)
    assert caps[0] == max(company.market_cap for company in companies)
    # Spread across the ranks: the sample steps through the table, not its top five.
    assert caps[-1] < sorted((company.market_cap for company in companies), reverse=True)[4]
