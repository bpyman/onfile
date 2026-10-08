"""A company's SEC facts are read, parsed and merged once per turn."""

import contextlib
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from financial_analyst_agent import sec_facts
from financial_analyst_agent.domain.errors import FinancialAnalystError
from financial_analyst_agent.providers.sec import company_facts
from financial_analyst_agent.providers.sec.cache import CachingSECDataSource
from financial_analyst_agent.sec_facts import SecFactLookup
from sec_fixtures import FixtureSEC, _load

TICKERS = ("NVDA", "WMT", "BAC")


@pytest.fixture(autouse=True)
def _fresh_shared_parses() -> Iterator[None]:
    sec_facts._PARSED_FACTS.clear()
    yield
    sec_facts._PARSED_FACTS.clear()


def _cik(ticker: str) -> str:
    return str(_load(ticker)["cik"])


def _listed() -> dict[str, str]:
    return {_cik(ticker): ticker for ticker in TICKERS}


class _CountingCache(CachingSECDataSource):
    """The disk cache, counting the digest reads and facts decodes it is asked for."""

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.digest_reads: list[str] = []
        self.decoded: list[str] = []

    def read_facts_digest(self, cik: str) -> tuple[tuple[str, int, int], bytes] | None:
        self.digest_reads.append(cik)
        return super().read_facts_digest(cik)

    def get_company_facts(self, cik: str) -> dict[str, Any]:
        self.decoded.append(cik)
        return super().get_company_facts(cik)


def _turn(cache: CachingSECDataSource) -> SecFactLookup:
    return SecFactLookup(client=cache, listed_tickers=_listed())


def test_a_turn_over_a_parse_in_memory_reads_no_digest_file(tmp_path: Path) -> None:
    cache = _CountingCache(FixtureSEC(*TICKERS), tmp_path)
    cik = _cik("WMT")

    first = _turn(cache).get_financials("WMT", "revenue")
    assert cache.decoded == [cik]
    second = _turn(cache).get_financials("WMT", "revenue")
    third = _turn(cache).get_financials("WMT", "gross_profit")

    assert second == first
    assert third.metric == "gross_profit"
    # The cold turn parsed the facts file; the warm turns found the parse in memory
    # by the digest's stamp, without reading or decompressing the digest.
    assert cache.decoded == [cik]
    assert cache.digest_reads == []


def test_a_digest_on_disk_is_read_once_when_memory_holds_no_parse(tmp_path: Path) -> None:
    cache = _CountingCache(FixtureSEC(*TICKERS), tmp_path)
    cik = _cik("WMT")
    _turn(cache).get_financials("WMT", "revenue")
    sec_facts._PARSED_FACTS.clear()

    lookup = _turn(cache)
    lookup.get_financials("WMT", "revenue")
    lookup.get_financials("WMT", "net_income")
    lookup.fiscal_periods("WMT")

    assert cache.decoded == [cik]
    assert cache.digest_reads == [cik]


def test_the_digest_stamp_is_the_stamp_the_digest_reads_back_with(tmp_path: Path) -> None:
    cache = CachingSECDataSource(FixtureSEC(*TICKERS), tmp_path)
    cik = _cik("WMT")

    assert cache.facts_digest_stamp(cik) is None
    _turn(cache).get_financials("WMT", "revenue")

    digest = cache.read_facts_digest(cik)
    assert digest is not None
    assert cache.facts_digest_stamp(cik) == digest[0]


def test_a_turn_parses_each_concept_set_of_a_company_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    parses: list[tuple[str, tuple[tuple[str, str], ...], str]] = []
    real = company_facts.parse_company_facts_for_concepts

    def counting(
        payload: dict[str, Any], concepts: list[tuple[str, str]], unit: str
    ) -> tuple[list[Any], list[dict[str, Any]]]:
        parses.append((str(payload.get("cik")), tuple(concepts), unit))
        return real(payload, concepts, unit)

    monkeypatch.setattr(sec_facts, "parse_company_facts_for_concepts", counting)
    monkeypatch.setattr(company_facts, "parse_company_facts_for_concepts", counting)
    lookup = SecFactLookup(client=FixtureSEC(*TICKERS), listed_tickers=_listed())

    for _pass in range(2):
        for metric in ("revenue", "gross_profit", "cost_of_revenue", "eps_diluted", "net_income"):
            # A metric the trimmed fixture lacks is refused; that is beside the point here.
            with contextlib.suppress(FinancialAnalystError):
                lookup.get_financials("WMT", metric)

    assert parses, "the lookup parsed nothing"
    assert len(parses) == len(set(parses))
