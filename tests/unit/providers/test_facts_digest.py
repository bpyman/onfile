"""A company's facts digest answers exactly as its facts file does, at a tenth of the size."""

import gzip
import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from financial_analyst_agent import sec_facts
from financial_analyst_agent.domain.errors import FinancialAnalystError
from financial_analyst_agent.providers.sec.cache import CachingSECDataSource
from financial_analyst_agent.sec_facts import (
    SecFactLookup,
    _digest_of,
    _parsed_from_digest,
    _ParsedFacts,
    _read_concepts_only,
    filings_from_company_facts,
)
from financial_analyst_agent.services.fiscal_periods import fiscal_labels
from sec_fixtures import FixtureSEC, _load

TICKERS = ("NVDA", "WMT", "BAC")
METRICS = (
    "revenue",
    "net_income",
    "eps_diluted",
    "gross_profit",
    "gross_margin",
    "operating_margin",
    "net_margin",
    "free_cash_flow",
    "cash",
    "shareholders_equity",
    "return_on_equity",
    "dividends_per_share",
)


@pytest.fixture(autouse=True)
def _fresh_shared_parses() -> Iterator[None]:
    sec_facts._PARSED_FACTS.clear()
    yield
    sec_facts._PARSED_FACTS.clear()


def _cik(ticker: str) -> str:
    return str(_load(ticker)["cik"])


def _listed() -> dict[str, str]:
    return {_cik(ticker): ticker for ticker in TICKERS}


def _parsed(ticker: str) -> _ParsedFacts:
    payload = FixtureSEC(ticker).get_company_facts(_cik(ticker))
    return _ParsedFacts(
        concepts=_read_concepts_only(payload),
        labels=fiscal_labels(payload),
        filings=tuple(filings_from_company_facts(payload)),
    )


def test_a_digest_reads_back_as_the_parse_it_was_made_from() -> None:
    parsed = _parsed("WMT")

    assert _parsed_from_digest(_digest_of(parsed)) == parsed


def test_a_digest_made_for_other_concepts_or_unreadable_is_not_used() -> None:
    other = _digest_of(_parsed("WMT")).replace(b'"tag":"', b'"tag":"x', 1)

    assert _parsed_from_digest(other) is None
    assert _parsed_from_digest(b"not json") is None
    assert _parsed_from_digest(b'{"tag": 1}') is None


def _answers(lookup: SecFactLookup, ticker: str) -> list[Any]:
    """Every metric's fact (or the refusal it raised), report dates and fiscal periods."""
    answers: list[Any] = []
    for metric in METRICS:
        try:
            answers.append(lookup.get_financials(ticker, metric))
        except FinancialAnalystError as exc:
            answers.append((type(exc).__name__, str(exc)))
    answers.append(lookup.list_quarterly_report_dates(ticker, limit=8))
    answers.append(lookup.fiscal_periods(ticker))
    return answers


@pytest.mark.parametrize("ticker", TICKERS)
def test_answers_from_a_digest_equal_answers_from_the_facts_file(
    tmp_path: Path, ticker: str
) -> None:
    from_file = _answers(
        SecFactLookup(client=FixtureSEC(*TICKERS), listed_tickers=_listed()), ticker
    )

    cache = CachingSECDataSource(FixtureSEC(*TICKERS), tmp_path)
    _answers(SecFactLookup(client=cache, listed_tickers=_listed()), ticker)
    assert cache.read_facts_digest(_cik(ticker)) is not None
    sec_facts._PARSED_FACTS.clear()
    from_digest = _answers(SecFactLookup(client=cache, listed_tickers=_listed()), ticker)

    assert from_digest == from_file


def test_the_digest_replaces_the_facts_file_and_is_dated_when_it_was_fetched(
    tmp_path: Path,
) -> None:
    cik = _cik("WMT")
    cache = CachingSECDataSource(FixtureSEC("WMT"), tmp_path)
    cache.prefetch_company_facts(cik)
    raw = (tmp_path / f"facts-{cik}.json").stat()
    fetched = raw.st_mtime_ns

    SecFactLookup(client=cache).get_financials("WMT", "revenue")

    digest = tmp_path / f"digest-{cik}.json.gz"
    assert not (tmp_path / f"facts-{cik}.json").exists()
    assert abs(digest.stat().st_mtime_ns - fetched) < 1_000_000
    # The fixture is already trimmed, so its digest is only a little smaller.
    assert digest.stat().st_size < raw.st_size


def test_an_unreadable_digest_falls_back_to_the_facts_file(tmp_path: Path) -> None:
    cik = _cik("WMT")
    cache = CachingSECDataSource(FixtureSEC("WMT"), tmp_path)
    first = SecFactLookup(client=cache).get_financials("WMT", "revenue")
    digest = tmp_path / f"digest-{cik}.json.gz"
    stat = digest.stat()
    digest.write_bytes(gzip.compress(b"not a digest"))
    os.utime(digest, ns=(stat.st_atime_ns, stat.st_mtime_ns))
    sec_facts._PARSED_FACTS.clear()

    assert SecFactLookup(client=cache).get_financials("WMT", "revenue") == first
