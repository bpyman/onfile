"""Trim a cached SEC companyfacts and submissions pair into a small test fixture.

Tests that pin a real filer's numbers (Verra Mobility's component revenue line,
Rapid7's revised nine months) replay these files through ``SecFactLookup``.
Only the named concepts, the facts ending on or after ``--since``, and the
periodic filings from then on are kept.

    uv run python scripts/trim_sec_test_fixture.py VRRM 0001682745 \
        --concepts Revenues,OperatingIncomeLoss --since 2025-01-01
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from financial_analyst_agent.providers.sec.submissions import KEPT_COLUMNS

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT / ".cache" / "sec"
OUT = ROOT / "tests" / "fixtures" / "sec"
PERIODIC_FORMS = frozenset({"10-Q", "10-Q/A", "10-K", "10-K/A"})


def trim(
    ticker: str, cik: str, concepts: list[str], since: str, cache: Path
) -> dict[str, Any]:
    facts = json.loads((cache / f"facts-{cik}.json").read_text())
    submissions = json.loads((cache / f"submissions-{cik}.json").read_text())
    kept: dict[str, dict[str, Any]] = {}
    for name in concepts:
        taxonomy, _, concept = name.rpartition(":")
        body = facts["facts"].get(taxonomy or "us-gaap", {}).get(concept)
        if body is None:
            continue
        units = {
            unit: [entry for entry in entries if entry["end"] >= since]
            for unit, entries in body["units"].items()
        }
        kept.setdefault(taxonomy or "us-gaap", {})[concept] = {
            "units": {unit: entries for unit, entries in units.items() if entries}
        }
    recent = submissions["filings"]["recent"]
    rows = [
        index
        for index, form in enumerate(recent["form"])
        if form in PERIODIC_FORMS and recent["reportDate"][index] >= since
    ]
    return {
        "ticker": ticker,
        "cik": cik,
        "title": submissions["name"],
        "facts": {"cik": int(cik), "entityName": facts["entityName"], "facts": kept},
        "submissions": {
            "cik": cik,
            "name": submissions["name"],
            "tickers": submissions.get("tickers", [ticker]),
            "filings": {
                "recent": {
                    field: [recent[field][index] for index in rows]
                    for field in KEPT_COLUMNS
                },
                "files": [],
            },
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ticker")
    parser.add_argument("cik")
    parser.add_argument("--concepts", required=True, help="comma-separated, taxonomy: optional")
    parser.add_argument("--since", required=True, help="keep facts ending on or after this date")
    parser.add_argument("--cache", type=Path, default=CACHE)
    args = parser.parse_args()
    fixture = trim(args.ticker, args.cik, args.concepts.split(","), args.since, args.cache)
    OUT.mkdir(parents=True, exist_ok=True)
    path = OUT / f"{args.ticker.lower()}.json"
    path.write_text(json.dumps(fixture, separators=(",", ":")) + "\n")
    print(f"wrote {path} ({path.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
