"""A company's cached SEC data lasts until it files again, while the filing watch can vouch."""

import os
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import pytest

from financial_analyst_agent.config import Settings
from financial_analyst_agent.domain.errors import ProviderError
from financial_analyst_agent.providers.sec import filing_watch
from financial_analyst_agent.providers.sec.cache import CachingSECDataSource
from financial_analyst_agent.providers.sec.client import SECClient
from financial_analyst_agent.providers.sec.filing_watch import (
    AFTER_FILING_SECONDS,
    DEFAULT_SECONDS,
    PAGE_SIZE,
    VOUCHED_SECONDS,
    FilingWatch,
    current_filing_watch,
    parse_feed,
    start_filing_watch,
)
from sec_fixtures import FixtureSEC, _load

DAY = 24 * 3600
NOW = datetime(2026, 10, 5, 16, 0, tzinfo=UTC).timestamp()
INTERVAL = 300.0


def _entry(cik: str, form: str, accepted: float) -> str:
    stamp = datetime.fromtimestamp(accepted, UTC).isoformat()
    return (
        "<entry>"
        f"<title>{form} - SOME COMPANY ({cik}) (Filer)</title>"
        f"<updated>{stamp}</updated>"
        f'<category scheme="https://www.sec.gov/" label="form type" term="{form}"/>'
        f"<id>urn:tag:sec.gov,2008:accession-number=0000000000-26-{int(accepted) % 999999:06d}</id>"
        "</entry>"
    )


def _feed(*entries: str) -> str:
    return (
        '<?xml version="1.0" encoding="ISO-8859-1" ?>'
        '<feed xmlns="http://www.w3.org/2005/Atom"><title>Latest Filings</title>'
        + "".join(entries)
        + "</feed>"
    )


class _Feed:
    """SEC's latest filings, set per form; pages as the real feed pages them."""

    def __init__(self) -> None:
        # The real feed always reaches back days; an empty one could vouch for nothing.
        self.filings: dict[str, list[tuple[str, str, float]]] = {
            "10-Q": [("0000000002", "10-Q", NOW - 5 * DAY)],
            "10-K": [("0000000003", "10-K", NOW - 5 * DAY)],
        }
        self.asked: list[tuple[str, int]] = []

    def page(self, form: str, start: int) -> str:
        self.asked.append((form, start))
        newest_first = sorted(self.filings[form], key=lambda item: -item[2])
        chosen = newest_first[start : start + PAGE_SIZE]
        return _feed(*(_entry(cik, kind, accepted) for cik, kind, accepted in chosen))


class _Clock:
    def __init__(self, now: float) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


def _watch(feed: _Feed, clock: _Clock) -> FilingWatch:
    return FilingWatch(feed.page, interval=INTERVAL, clock=clock)


def test_the_feed_gives_each_filers_cik_form_and_acceptance_time() -> None:
    text = _feed(_entry("0000033002", "10-Q", NOW - 60), _entry("0001830072", "10-K/A", NOW - 3600))

    filings = parse_feed(text)

    assert [(f.cik, f.form, f.accepted) for f in filings] == [
        ("0000033002", "10-Q", NOW - 60),
        ("0001830072", "10-K/A", NOW - 3600),
    ]


def test_a_company_that_has_not_filed_keeps_its_files_for_a_week() -> None:
    feed, clock = _Feed(), _Clock(NOW)
    feed.filings["10-Q"] = [("0000000001", "10-Q", NOW - 2 * DAY)]
    watch = _watch(feed, clock)
    watch.poll()

    assert watch.lifetime("0000000099", NOW - 3600) == VOUCHED_SECONDS


def test_a_filing_after_the_file_was_written_makes_it_out_of_date() -> None:
    feed, clock = _Feed(), _Clock(NOW)
    feed.filings["10-Q"] = [
        ("0000000001", "10-Q", NOW - 2 * DAY),
        ("0000000099", "10-Q/A", NOW - 600),
    ]
    watch = _watch(feed, clock)
    watch.poll()

    assert watch.lifetime("0000000099", NOW - 3600) == 0.0


def test_after_a_filing_the_files_refresh_often_for_a_day() -> None:
    feed, clock = _Feed(), _Clock(NOW)
    feed.filings["10-K"] = [
        ("0000000001", "10-K", NOW - 3 * DAY),
        ("0000000099", "10-K", NOW - 3600),
    ]
    watch = _watch(feed, clock)
    watch.poll()

    # Written after the filing, while SEC's structured data may still lack it.
    assert watch.lifetime("0000000099", NOW - 600) == AFTER_FILING_SECONDS
    clock.now = NOW + DAY
    watch.poll()
    # Written more than a day after the filing: vouched for again.
    assert watch.lifetime("0000000099", NOW + DAY - 600) == VOUCHED_SECONDS


def test_a_file_written_before_the_watch_could_see_falls_back_to_the_hour() -> None:
    feed, clock = _Feed(), _Clock(NOW)
    feed.filings["10-Q"] = [("0000000001", "10-Q", NOW - DAY)]
    watch = _watch(feed, clock)
    watch.poll()

    assert watch.lifetime("0000000099", NOW - 2 * DAY) == DEFAULT_SECONDS


def test_a_watch_that_has_stopped_polling_vouches_for_nothing() -> None:
    feed, clock = _Feed(), _Clock(NOW)
    feed.filings["10-Q"] = [("0000000001", "10-Q", NOW - 2 * DAY)]
    watch = _watch(feed, clock)

    assert watch.lifetime("0000000099", NOW - 60) == DEFAULT_SECONDS
    watch.poll()
    clock.now = NOW + 4 * INTERVAL
    assert watch.lifetime("0000000099", NOW - 60) == DEFAULT_SECONDS


def test_a_poll_pages_back_until_it_reaches_the_last_one() -> None:
    feed, clock = _Feed(), _Clock(NOW)
    old = [(f"{index:010d}", "10-Q", NOW - 2 * DAY - index) for index in range(1, 50)]
    feed.filings["10-Q"] = old
    watch = _watch(feed, clock)
    watch.poll()

    # Earnings season: a page and a half of new 10-Qs since the last poll.
    new = [(f"{1000 + index:010d}", "10-Q", NOW + 100 + index) for index in range(150)]
    feed.filings["10-Q"] = old + new
    feed.asked.clear()
    clock.now = NOW + INTERVAL + 400
    watch.poll()

    assert ("10-Q", PAGE_SIZE) in feed.asked
    assert watch.lifetime("0000001000", NOW) == 0.0
    # Coverage reached back to the first poll, so a file from before it is still vouched for.
    assert watch.lifetime("0000000999", NOW - 3600) == VOUCHED_SECONDS


def test_a_gap_the_pages_cannot_close_moves_the_coverage_forward() -> None:
    feed, clock = _Feed(), _Clock(NOW)
    feed.filings["10-Q"] = [("0000000001", "10-Q", NOW - DAY)]
    watch = _watch(feed, clock)
    watch.poll()

    flood = [(f"{index:010d}", "10-Q", NOW + 1000 + index) for index in range(10 * PAGE_SIZE)]
    feed.filings["10-Q"] = flood
    clock.now = NOW + 2 * DAY
    watch.poll()

    oldest_read = NOW + 1000 + 10 * PAGE_SIZE - 5 * PAGE_SIZE
    assert watch.lifetime("0000000999", oldest_read - 1) == DEFAULT_SECONDS
    # Just after the coverage moved, the unseen gap before it may hold a filing: 15 minutes,
    # even for the company whose older filing the watch did see.
    assert watch.lifetime("0000099999", oldest_read + 1) == AFTER_FILING_SECONDS
    assert watch.lifetime("0000000001", oldest_read + 1) == AFTER_FILING_SECONDS
    assert watch.lifetime("0000099999", oldest_read + DAY + 1) == VOUCHED_SECONDS


def test_no_interval_starts_no_watch() -> None:
    assert start_filing_watch(lambda form, start: "", 0) is None
    assert current_filing_watch() is None


class _CountingFixture(FixtureSEC):
    def __init__(self, *tickers: str) -> None:
        super().__init__(*tickers)
        self.fetched: list[str] = []

    def get_company_facts(self, cik: str) -> dict[str, Any]:
        self.fetched.append(cik)
        return super().get_company_facts(cik)


class _FixedLifetime:
    def __init__(self, seconds: float) -> None:
        self.seconds = seconds

    def lifetime(self, cik: str, written: float) -> float:
        return self.seconds


def _age(path: Path, seconds: float) -> None:
    then = time.time() - seconds
    os.utime(path, (then, then))


@pytest.mark.parametrize(
    ("lifetime", "fetched_again"),
    [(VOUCHED_SECONDS, False), (0.0, True), (DEFAULT_SECONDS, True)],
)
def test_the_cache_keeps_a_company_file_as_long_as_the_watch_says(
    tmp_path: Path, lifetime: float, fetched_again: bool
) -> None:
    inner = _CountingFixture("WMT")
    cik = str(_load("WMT")["cik"])
    source = CachingSECDataSource(inner, tmp_path, watch=_FixedLifetime(lifetime))  # type: ignore[arg-type]
    source.get_company_facts(cik)
    _age(tmp_path / f"facts-{cik}.json", 2 * 3600)

    source.get_company_facts(cik)

    assert inner.fetched == ([cik, cik] if fetched_again else [cik])


def test_without_a_watch_the_hour_still_applies(tmp_path: Path) -> None:
    inner = _CountingFixture("WMT")
    cik = str(_load("WMT")["cik"])
    source = CachingSECDataSource(inner, tmp_path)
    source.get_company_facts(cik)
    _age(tmp_path / f"facts-{cik}.json", 2 * 3600)

    source.get_company_facts(cik)

    assert inner.fetched == [cik, cik]


def _client(handler: Any) -> SECClient:
    settings = Settings(_env_file=None, sec_user_agent="OnfileTests (tests@example.com)")  # type: ignore[call-arg]
    return SECClient(settings, client=httpx.Client(transport=httpx.MockTransport(handler)))


def test_the_client_reads_one_page_of_the_latest_filings_feed() -> None:
    asked: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        asked.append(str(request.url))
        return httpx.Response(
            200,
            content=_feed(_entry("0000033002", "10-Q", NOW)).encode(),
            headers={"content-type": "application/atom+xml"},
        )

    text = _client(handler).get_latest_filings("10-Q", start=100)

    assert [f.cik for f in parse_feed(text)] == ["0000033002"]
    assert "action=getcurrent" in asked[0] and "type=10-Q" in asked[0]
    assert "start=100" in asked[0] and "output=atom" in asked[0]


def test_a_page_that_is_not_the_feed_is_refused() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"<html>busy</html>")

    with pytest.raises(ProviderError):
        _client(handler).get_latest_filings("10-K")


@pytest.fixture(autouse=True)
def _no_process_watch() -> Any:
    yield
    filing_watch._WATCH = None


def test_a_file_fetched_just_after_a_filing_never_turns_fresh_for_a_week() -> None:
    feed, clock = _Feed(), _Clock(NOW + 600)
    feed.filings["10-Q"].append(("0000000099", "10-Q", NOW))
    watch = _watch(feed, clock)
    watch.poll()
    written = NOW + 360  # six minutes after the filing: may lack its quarter

    for later in (3600, 23 * 3600, 25 * 3600, 3 * DAY):
        clock.now = NOW + later
        watch.poll()
        lifetime = watch.lifetime("0000000099", written)
        assert lifetime == AFTER_FILING_SECONDS
        assert clock.now - written > lifetime, later
    # Within the day its visitors refresh it; after the day the warm-up does, once.
    clock.now = NOW + 3600
    assert watch.needs_warming("0000000099", written) is False
    clock.now = NOW + 25 * 3600
    assert watch.needs_warming("0000000099", written) is True


def test_a_later_poll_that_does_not_reach_the_last_one_moves_the_coverage() -> None:
    feed, clock = _Feed(), _Clock(NOW)
    watch = _watch(feed, clock)
    watch.poll()
    assert watch.lifetime("0000000099", NOW - DAY) == VOUCHED_SECONDS

    # A short page whose filings are all newer than the last poll: a gap before them.
    feed.filings["10-Q"] = [("0000000001", "10-Q", NOW + 2 * DAY)]
    clock.now = NOW + 2 * DAY + 60
    watch.poll()

    assert watch.lifetime("0000000099", NOW + DAY) == DEFAULT_SECONDS
    assert watch.lifetime("0000000099", NOW + 2 * DAY + 30) == AFTER_FILING_SECONDS


def test_an_empty_later_page_vouches_only_from_now() -> None:
    feed, clock = _Feed(), _Clock(NOW)
    watch = _watch(feed, clock)
    watch.poll()

    feed.filings["10-K"] = []
    clock.now = NOW + 600
    watch.poll()

    assert watch.lifetime("0000000099", NOW + 300) == DEFAULT_SECONDS


def test_a_file_written_just_after_coverage_began_refreshes_often_for_a_day() -> None:
    feed, clock = _Feed(), _Clock(NOW)
    feed.filings["10-Q"] = [("0000000001", "10-Q", NOW - 3600)]
    watch = _watch(feed, clock)
    watch.poll()

    # An hour after coverage began, with no filing seen: the day before it is unseen.
    assert watch.lifetime("0000000099", NOW) == AFTER_FILING_SECONDS
    clock.now = NOW + 2 * DAY
    watch.poll()
    # Two days after coverage began: any filing in that day would have been seen.
    assert watch.lifetime("0000000099", NOW + 2 * DAY - 3600) == VOUCHED_SECONDS


def test_a_company_fetched_just_after_coverage_began_is_warmed_once_more_after_the_day() -> None:
    feed, clock = _Feed(), _Clock(NOW)
    feed.filings["10-Q"] = [("0000000001", "10-Q", NOW - 3600)]
    watch = _watch(feed, clock)
    watch.poll()
    written = NOW  # an hour after coverage began, with no filing seen

    clock.now = NOW + 3600
    watch.poll()
    assert watch.lifetime("0000000099", written) == AFTER_FILING_SECONDS
    # Past its 15 minutes, but a fetch now would be as short-lived: left to its visitors.
    assert watch.needs_warming("0000000099", written) is False
    clock.now = NOW + DAY
    watch.poll()
    assert watch.needs_warming("0000000099", written) is True
