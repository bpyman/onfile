"""The warm-up fetches large companies' SEC data in the background, behind visitors."""

import threading
from datetime import UTC, datetime

import httpx
import pytest

from financial_analyst_agent import facts_warmer
from financial_analyst_agent.config import Settings
from financial_analyst_agent.facts_warmer import FactsWarmer
from financial_analyst_agent.providers.sec.client import SEC_PAUSE, SECClient
from financial_analyst_agent.providers.sec.filing_watch import (
    AFTER_FILING_SECONDS,
    VOUCHED_SECONDS,
    FilingWatch,
)
from financial_analyst_agent.runtime import recorded_runtime

NOW = datetime(2026, 10, 5, 16, 0, tzinfo=UTC).timestamp()
DAY = 24 * 3600


@pytest.fixture(autouse=True)
def _quick_pauses(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(facts_warmer, "_IDLE_CHECK_SECONDS", 0.001)
    monkeypatch.setattr(facts_warmer, "_FAILURE_PAUSE_SECONDS", 0.001)


def _warmer(
    needing: set[str],
    warmed: list[str],
    *,
    idle: list[bool] | None = None,
    failing: set[str] = frozenset(),  # type: ignore[assignment]
) -> FactsWarmer:
    answers = iter(idle or [])

    def warm(cik: str) -> None:
        if cik in failing:
            raise RuntimeError("SEC would not serve it")
        warmed.append(cik)

    return FactsWarmer(
        ("A", "B", "C", "D"),
        warm=warm,
        needs_warming=lambda cik: cik in needing,
        idle=lambda: next(answers, True),
        rate=1000.0,
    )


def test_a_sweep_warms_only_the_companies_that_need_it_largest_first() -> None:
    warmed: list[str] = []

    count = _warmer({"D", "B"}, warmed).sweep(threading.Event())

    assert warmed == ["B", "D"]
    assert count == 2


def test_the_warm_up_waits_while_visitors_requests_are_queued() -> None:
    warmed: list[str] = []
    idle = [False, False, True]

    _warmer({"A"}, warmed, idle=idle).sweep(threading.Event())

    assert warmed == ["A"]


def test_a_company_that_fails_is_left_for_a_visitors_turn() -> None:
    warmed: list[str] = []

    count = _warmer({"A", "B", "C"}, warmed, failing={"B"}).sweep(threading.Event())

    assert warmed == ["A", "C"]
    assert count == 2


def test_a_stopped_warm_up_warms_nothing_more() -> None:
    warmed: list[str] = []
    stop = threading.Event()
    stop.set()

    assert _warmer({"A", "B"}, warmed).sweep(stop) == 0
    assert warmed == []


class _Clock:
    def __init__(self, now: float) -> None:
        self.now = now

    def __call__(self) -> float:
        return self.now


def _feed(*entries: tuple[str, str, float]) -> str:
    body = "".join(
        f"<entry><title>{form} - CO ({cik}) (Filer)</title>"
        f"<updated>{datetime.fromtimestamp(accepted, UTC).isoformat()}</updated>"
        f'<category term="{form}"/></entry>'
        for cik, form, accepted in entries
    )
    return f'<feed xmlns="http://www.w3.org/2005/Atom">{body}</feed>'


def _watch(clock: _Clock, filed: dict[str, float]) -> FilingWatch:
    def page(form: str, start: int) -> str:
        entries = [("0000000002", form, NOW - 5 * DAY)]
        entries += [(cik, form, when) for cik, when in filed.items() if form == "10-Q"]
        return _feed(*entries)

    return FilingWatch(page, interval=300.0, clock=clock)


def test_the_watch_says_when_a_company_needs_warming() -> None:
    clock = _Clock(NOW)
    watch = _watch(clock, {"0000000010": NOW - 3600})

    # A watch that has not polled warms nothing: every file would go hourly.
    assert watch.needs_warming("0000000099", None) is False
    watch.poll()

    assert watch.needs_warming("0000000099", None) is True
    assert watch.needs_warming("0000000099", NOW - 60) is False
    # Filed since the file was written: fetch it again.
    assert watch.needs_warming("0000000010", NOW - 2 * 3600) is True
    # Written after the filing and past its 15 minutes: left to visitors for the day.
    assert watch.needs_warming("0000000010", NOW - AFTER_FILING_SECONDS - 60) is False
    # A week old, with no filing since: fetch it again.
    assert watch.needs_warming("0000000099", NOW - VOUCHED_SECONDS - 60) is True


def test_the_largest_companies_come_first_one_cik_each() -> None:
    ranking = recorded_runtime().ranking
    assert ranking is not None

    ciks = ranking.largest_ciks(5)  # type: ignore[attr-defined]

    caps = {company.cik: company.market_cap for company in ranking.snapshot_companies()}
    assert len(ciks) == len(set(ciks)) == 5
    assert [caps[cik] for cik in ciks] == sorted((caps[cik] for cik in ciks), reverse=True)
    assert max(caps.values()) == caps[ciks[0]]


def test_the_client_is_idle_only_when_sec_is_neither_paused_nor_busy() -> None:
    settings = Settings(_env_file=None, sec_user_agent="OnfileTests (tests@example.com)")  # type: ignore[call-arg]
    client = SECClient(
        settings, client=httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(200)))
    )

    assert client.idle()
    SEC_PAUSE.extend(60)
    assert not client.idle()


def test_the_warm_up_waits_for_the_filing_watch_before_its_first_walk(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(facts_warmer, "_READY_CHECK_SECONDS", 0.001)
    warmed: list[str] = []
    stop = threading.Event()
    checks = iter([False, False, True])

    def ready() -> bool:
        return next(checks, True)

    warmer = _warmer({"A"}, warmed)
    original = warmer.sweep

    def sweep_once(event: threading.Event) -> int:
        count = original(event)
        stop.set()
        return count

    warmer.sweep = sweep_once  # type: ignore[method-assign]
    warmer.run(stop, interval=0.001, ready=ready)

    assert warmed == ["A"]
