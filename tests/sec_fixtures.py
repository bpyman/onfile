"""Real filers' SEC data, trimmed by ``scripts/trim_sec_test_fixture.py``, replayed offline."""

import json
from functools import cache
from pathlib import Path
from typing import Any

from financial_analyst_agent.domain.errors import ProviderError
from financial_analyst_agent.sec_facts import SecFactLookup

FIXTURES = Path(__file__).parent / "fixtures" / "sec"


@cache
def _load(ticker: str) -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads((FIXTURES / f"{ticker.lower()}.json").read_text())
    return loaded


class FixtureSEC:
    """The SEC data source over trimmed fixture files."""

    def __init__(self, *tickers: str) -> None:
        self._by_cik = {_load(ticker)["cik"]: _load(ticker) for ticker in tickers}

    def get_company_tickers(self) -> dict[str, Any]:
        return {
            str(index): {
                "cik_str": int(cik),
                "ticker": fixture["ticker"],
                "title": fixture["title"],
            }
            for index, (cik, fixture) in enumerate(self._by_cik.items())
        }

    def _fixture(self, cik: str) -> dict[str, Any]:
        fixture = self._by_cik.get(cik)
        if fixture is None:
            raise ProviderError("not in fixtures", details={"cik": cik, "status_code": 404})
        return fixture

    def get_submissions(self, cik: str, *, with_history: bool = True) -> dict[str, Any]:
        submissions: dict[str, Any] = self._fixture(cik)["submissions"]
        return submissions

    def get_company_facts(self, cik: str) -> dict[str, Any]:
        facts: dict[str, Any] = self._fixture(cik)["facts"]
        return facts

    def close(self) -> None:
        return None


def fixture_lookup(*tickers: str) -> SecFactLookup:
    """A fact lookup over the named fixtures; each counts as a snapshot member."""
    listed = {_load(ticker)["cik"]: _load(ticker)["ticker"] for ticker in tickers}
    return SecFactLookup(client=FixtureSEC(*tickers), listed_tickers=listed)
