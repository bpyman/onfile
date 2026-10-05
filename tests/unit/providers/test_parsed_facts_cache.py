"""Parsed company facts are shared across turns while their cached file is unchanged."""

import contextlib
import json
import os
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from financial_analyst_agent import sec_facts
from financial_analyst_agent.domain.errors import FinancialAnalystError
from financial_analyst_agent.providers.sec.cache import CachingSECDataSource
from financial_analyst_agent.sec_facts import SecFactLookup, _ParsedFacts, _ParsedFactsCache
from sec_fixtures import FixtureSEC, _load

TICKERS = ("NVDA", "WMT", "BAC")
# A figure each trimmed fixture holds.
FIRST_METRIC = {"NVDA": "eps_diluted", "WMT": "revenue", "BAC": "revenue"}


@pytest.fixture(autouse=True)
def _fresh_shared_parses() -> Iterator[None]:
    sec_facts._PARSED_FACTS.clear()
    yield
    sec_facts._PARSED_FACTS.clear()


class _CountingCache(CachingSECDataSource):
    """The disk cache, counting the facts files it reads and decodes."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.decoded: list[str] = []

    def get_company_facts(self, cik: str) -> dict[str, Any]:
        self.decoded.append(cik)
        return super().get_company_facts(cik)


def _source(tmp_path: Path) -> _CountingCache:
    return _CountingCache(FixtureSEC(*TICKERS), tmp_path)


def _turn(source: _CountingCache) -> SecFactLookup:
    """A fresh lookup over ``source``, as each API turn builds one."""
    listed = {_load(ticker)["cik"]: _load(ticker)["ticker"] for ticker in TICKERS}
    return SecFactLookup(client=source, listed_tickers=listed)


def _cik(ticker: str) -> str:
    return str(_load(ticker)["cik"])


def test_the_stamp_names_the_fresh_file_on_disk_and_changes_when_it_is_rewritten(
    tmp_path: Path,
) -> None:
    source = _source(tmp_path)
    cik = _cik("NVDA")

    assert source.company_facts_stamp(cik) is None
    source.prefetch_company_facts(cik)
    first = source.company_facts_stamp(cik)
    assert first is not None

    path = tmp_path / f"facts-{cik}.json"
    os.utime(path, ns=(first[1] + 1_000_000, first[1] + 1_000_000))
    assert source.company_facts_stamp(cik) not in (None, first)


def test_a_second_turn_about_the_same_company_reuses_the_parse(tmp_path: Path) -> None:
    source = _source(tmp_path)

    first = _turn(source).get_financials("WMT", "revenue")
    second = _turn(source).get_financials("WMT", "revenue")

    assert second == first
    assert source.decoded == [_cik("WMT")]


def test_an_expired_digest_is_fetched_and_parsed_again(tmp_path: Path) -> None:
    source = _source(tmp_path)
    cik = _cik("WMT")
    _turn(source).get_financials("WMT", "revenue")

    # Without a filing watch a digest lasts the hour, as its facts file did.
    digest = tmp_path / f"digest-{cik}.json.gz"
    then = time.time() - 2 * 3600
    os.utime(digest, (then, then))
    _turn(source).get_financials("WMT", "revenue")

    assert source.decoded == [cik, cik]


def test_a_source_without_stamps_parses_each_turn(tmp_path: Path) -> None:
    fixture = FixtureSEC("WMT")
    listed = {_cik("WMT"): "WMT"}

    first = SecFactLookup(client=fixture, listed_tickers=listed).get_financials("WMT", "revenue")
    second = SecFactLookup(client=fixture, listed_tickers=listed).get_financials("WMT", "revenue")

    assert first == second
    assert sec_facts._PARSED_FACTS.get(("anything", 0, 0)) is None


def test_lookups_never_change_a_shared_parse(tmp_path: Path) -> None:
    source = _source(tmp_path)
    metrics = (
        "revenue",
        "net_income",
        "eps_diluted",
        "gross_margin",
        "operating_margin",
        "free_cash_flow",
        "cash",
        "shareholders_equity",
        "return_on_equity",
    )
    stamps = {}
    before = {}
    for ticker in TICKERS:
        _turn(source).get_financials(ticker, FIRST_METRIC[ticker])
        digest = source.read_facts_digest(_cik(ticker))
        assert digest is not None
        stamps[ticker] = digest[0]
    for ticker in TICKERS:
        parsed = sec_facts._PARSED_FACTS.get(stamps[ticker])
        assert parsed is not None
        before[ticker] = json.dumps(parsed.concepts, sort_keys=True, default=str)

    for ticker in TICKERS:
        lookup = _turn(source)
        for metric in metrics:
            # A metric a trimmed fixture lacks is refused; that is beside the point here.
            with contextlib.suppress(FinancialAnalystError):
                lookup.get_financials(ticker, metric)
        lookup.list_quarterly_report_dates(ticker, limit=8)
        lookup.fiscal_periods(ticker)

    for ticker in TICKERS:
        parsed = sec_facts._PARSED_FACTS.get(stamps[ticker])
        assert parsed is not None
        assert json.dumps(parsed.concepts, sort_keys=True, default=str) == before[ticker]


def _parsed() -> _ParsedFacts:
    return _ParsedFacts(concepts={}, labels={}, filings=())


def test_the_least_recently_used_company_goes_first() -> None:
    cache = _ParsedFactsCache(limit=2)
    cache.put(("a", 1, 1), _parsed())
    cache.put(("b", 1, 1), _parsed())
    assert cache.get(("a", 1, 1)) is not None
    cache.put(("c", 1, 1), _parsed())

    assert cache.get(("b", 1, 1)) is None
    assert cache.get(("a", 1, 1)) is not None
    assert cache.get(("c", 1, 1)) is not None


def test_a_newer_copy_of_a_file_replaces_the_older_one() -> None:
    cache = _ParsedFactsCache(limit=4)
    cache.put(("a", 1, 1), _parsed())
    cache.put(("a", 2, 1), _parsed())

    assert cache.get(("a", 1, 1)) is None
    assert cache.get(("a", 2, 1)) is not None
