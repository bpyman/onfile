"""HTTP seam for the Next.js window (ADR 0006): threads, streamed turns, display records."""

from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
import uuid
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from api_server import smoke
from financial_analyst_agent import api
from financial_analyst_agent.api import (
    PUBLIC_FAILURE_MESSAGE,
    create_app,
    threads_limited_message,
)
from financial_analyst_agent.config import AppMode, Settings
from financial_analyst_agent.contracts import Runtime, RuntimeKind
from financial_analyst_agent.domain.errors import (
    AmbiguousCompanyError,
    CompanyNotFoundError,
    ConfigurationError,
    ProviderRefusal,
    RuntimeMismatchError,
    SessionQuotaError,
)
from financial_analyst_agent.runtime import recorded_runtime, resolve_runtime_kind
from financial_analyst_agent.storefront import EXAMPLE_QUERY, GUIDED_STORIES
from financial_analyst_agent.thread_store import LocalThreadStore, ThreadState

# Keys the web client reads (web/lib/types.ts). Renaming one is a client break.
PRESENTATION_KEYS = {
    "intent",
    "intent_label",
    "banners",
    "traces",
    "citations",
    "fact_card",
    "table",
    "chart",
    "evidence",
    "disclosures",
    "essay",
    "message",
    "candidates",
    "clarify_prompt",
    "suggestions",
    "message_tone",
    "headline",
    "trends",
}

# Keys of a thread view (web/lib/types.ts ThreadView).
THREAD_VIEW_KEYS = {
    "thread_id",
    "runtime",
    "turns",
    "spec_chips",
    "spec_chip_edits",
    "quick_actions",
    "pending_clarification",
    "turn_count",
    "max_turns",
    "turn_in_flight",
}


def _settings(**overrides: Any) -> Settings:
    # A User-Agent, or the live runtime is locked (no live SEC without one).
    values: dict[str, Any] = {
        "app_mode": AppMode.RECORDED,
        "_env_file": None,
        "sec_user_agent": "OnfileTests (tests@example.com)",
    }
    values.update(overrides)
    return Settings(**values)


@pytest.fixture
def client(tmp_path: Path) -> TestClient:
    return TestClient(create_app(_settings(), store_root=tmp_path / "threads"))


def _events(response: Any) -> list[tuple[str, dict[str, Any]]]:
    events: list[tuple[str, dict[str, Any]]] = smoke.sse_events(response.content)
    return events


def _new_thread(client: TestClient, runtime: str | None = None) -> str:
    body = None if runtime is None else {"runtime": runtime}
    response = client.post("/api/threads", json=body)
    assert response.status_code == 201
    return str(response.json()["thread_id"])


def _post_turn(client: TestClient, thread_id: str, message: str) -> Any:
    return client.post(f"/api/threads/{thread_id}/turns", json={"message": message})


def _ask(client: TestClient, thread_id: str, message: str) -> dict[str, Any]:
    response = _post_turn(client, thread_id, message)
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    events = _events(response)
    assert events[0][0] == "progress"
    kind, data = events[-1]
    assert kind == "thread", data
    assert all(name == "progress" for name, _ in events[:-1])
    return data


def test_meta_serves_storefront_copy_and_snapshot_banner(client: TestClient) -> None:
    meta = client.get("/api/meta").json()
    assert meta["runtime"] == {"default": "recorded", "locked": False}
    assert [story["label"] for story in meta["guided_stories"]] == [
        label for label, _ in GUIDED_STORIES
    ]
    assert meta["snapshot"] == {
        "banner": "Recorded universe snapshot as of Sep 27, 2026",
        "stale": False,
    }
    assert meta["metric_groups"][0]["title"] == "Reported (SEC EDGAR)"
    assert "Net income" in meta["metric_groups"][0]["names"]
    assert meta["runtime_copy"]["recorded"].startswith("Recorded runtime — ")
    assert meta["runtime_copy"]["locked"] == "Live runtime is off on the public demo"
    guide = meta["runtime_guide"]
    assert [runtime["kind"] for runtime in guide["runtimes"]] == ["recorded", "live"]
    # Without keys, the panel does not promise news or written analysis on live.
    assert guide["runtimes"][1]["points"][-1] == "News search and written analysis are off here."
    assert guide["footer"].startswith("A conversation stays on the runtime")


def test_public_demo_locks_the_runtime_to_recorded(tmp_path: Path) -> None:
    app = create_app(
        _settings(app_mode=AppMode.LIVE, public_demo=True), store_root=tmp_path
    )
    meta = TestClient(app).get("/api/meta?runtime=live").json()
    assert meta["runtime"] == {"default": "recorded", "locked": True}


def test_meta_defaults_to_the_live_runtime_when_app_mode_says_so(tmp_path: Path) -> None:
    client = TestClient(create_app(_settings(app_mode=AppMode.LIVE), store_root=tmp_path))
    assert client.get("/api/meta").json()["runtime"] == {"default": "live", "locked": False}
    assert client.get("/api/meta?runtime=recorded").status_code == 200
    assert client.get("/api/meta?runtime=true").status_code == 422


def test_unknown_thread_is_empty_and_malformed_id_is_404(client: TestClient) -> None:
    thread_id = _new_thread(client)
    view = client.get(f"/api/threads/{thread_id}").json()
    assert view["turns"] == []
    assert view["pending_clarification"] is False
    assert client.get("/api/threads/..%2Fetc").status_code == 404
    assert client.get("/api/threads/not-a-uuid").status_code == 404


def test_guided_story_streams_a_fact_card_with_formatted_amount(client: TestClient) -> None:
    thread_id = _new_thread(client)
    view = _ask(client, thread_id, GUIDED_STORIES[0][1])
    [turn] = view["turns"]
    presented = turn["presentation"]
    assert set(presented) == PRESENTATION_KEYS
    assert presented["intent"] == "lookup"
    card = presented["fact_card"]
    assert card is not None
    assert card["amount"].startswith("$")
    # Microsoft's latest quarter is its fiscal Q4, derived from the 10-K.
    assert card["form"] == "10-K"
    assert presented["evidence"][0]["raw_amount"].isdigit()
    assert presented["traces"], "tool traces must reach the client"
    assert view["turn_count"] == 1


def test_follow_up_extends_thread_and_reload_returns_history(client: TestClient) -> None:
    thread_id = _new_thread(client)
    _ask(client, thread_id, GUIDED_STORIES[1][1])
    view = _ask(client, thread_id, "add Apple")
    assert [turn["message"] for turn in view["turns"]] == [GUIDED_STORIES[1][1], "add Apple"]
    assert "AAPL" in view["spec_chips"]
    chart = view["turns"][-1]["presentation"]["chart"]
    assert chart["kind"] == "line"
    assert chart["value_kind"] == "usd"
    assert chart["metric_label"] == "Revenue"
    assert len(chart["period_labels"]) == len(chart["records"]) == len(chart["amounts"])
    assert chart["period_labels"][0].startswith(("Mar", "Jun", "Sep", "Dec"))
    assert set(chart["series"]) == {"Microsoft Corporation", "Apple Inc."}
    assert all(
        amount.startswith("$") or amount == ""
        for row in chart["amounts"]
        for amount in row.values()
    )
    reloaded = client.get(f"/api/threads/{thread_id}").json()
    assert reloaded == view
    assert set(view) == THREAD_VIEW_KEYS
    assert view["turn_in_flight"] is False


def test_ambiguous_metric_offers_live_candidates_on_last_turn_only(client: TestClient) -> None:
    thread_id = _new_thread(client)
    view = _ask(client, thread_id, "What was Google's latest quarterly profit?")
    turn = view["turns"][-1]
    assert view["pending_clarification"] is True
    assert turn["clarify_enabled"] is True
    assert turn["candidate_slugs"] == ["gross_profit", "operating_income", "net_income"]
    assert turn["presentation"]["candidates"] == ["Gross profit", "Operating income", "Net income"]
    assert turn["presentation"]["clarify_prompt"] == "Which metric do you mean?"

    answered = _ask(client, thread_id, "net_income")
    assert answered["pending_clarification"] is False
    assert answered["turns"][0]["clarify_enabled"] is False
    assert answered["turns"][-1]["presentation"]["fact_card"] is not None


def test_start_over_clears_thread(client: TestClient) -> None:
    thread_id = _new_thread(client)
    _ask(client, thread_id, GUIDED_STORIES[0][1])
    assert client.delete(f"/api/threads/{thread_id}").status_code == 204
    assert client.get(f"/api/threads/{thread_id}").json()["turns"] == []


def test_turn_quota_streams_public_error(tmp_path: Path) -> None:
    client = TestClient(
        create_app(_settings(max_turns_per_thread=1), store_root=tmp_path)
    )
    thread_id = _new_thread(client)
    _ask(client, thread_id, GUIDED_STORIES[0][1])
    kind, data = _events(_post_turn(client, thread_id, "add Apple"))[-1]
    assert kind == "error"
    assert "turn limit" in data["message"]


def test_meta_serves_the_capability_catalog_and_example_query(client: TestClient) -> None:
    meta = client.get("/api/meta").json()

    assert meta["example_query"] == EXAMPLE_QUERY
    descriptions = [item["description"] for item in meta["capabilities"]]
    assert descriptions == [
        "Look up any quarter's financials, EPS, cash flow, or market cap for any "
        "operating publicly-listed US company",
        "Compare companies on metrics, rank by market cap, or combine rank and lookup",
        "Access and analyze relevant financial news linked to specific companies",
        "Answer general queries and provide qualitative industry analysis",
        "Stay on the same thread to extend the current analysis, or start a new one",
    ]
    examples = [example for item in meta["capabilities"] for example in item["examples"]]
    assert examples == [
        "What was Microsoft's latest quarterly revenue?",
        "Apple diluted EPS in Q3 FY2025",
        "Microsoft free cash flow over the last four quarters",
        "How is Nvidia doing?",
        "Compare Eli Lilly and Merck net margins",
        "What are the top 10 tech companies and R&D spend for each?",
        "Top 5 semiconductor companies by revenue",
        # The recorded runtime has no live news or model: these it can replay.
        "Effects of recent Strait of Hormuz closures on Exxon",
        "How can AI disrupt healthcare?",
        "add Apple",
        "now add operating margin",
        "make that the last four quarters",
        "show year-over-year",
    ]
    groups = {group["title"]: group["names"] for group in meta["metric_groups"]}
    assert list(groups) == ["Reported (SEC EDGAR)", "Calculated", "Daily snapshot (FMP)"]
    assert groups["Reported (SEC EDGAR)"][0] == "Revenue"
    assert "Gross margin" in groups["Calculated"]
    assert groups["Daily snapshot (FMP)"] == ["Market cap", "Share price"]
    assert not any("_" in name for names in groups.values() for name in names)


@pytest.mark.parametrize(
    ("failure", "shown"),
    [
        (ProviderRefusal("Recorded answer unavailable"), "Recorded answer unavailable"),
        (CompanyNotFoundError("No company called Acme"), "No company called Acme"),
        (
            AmbiguousCompanyError("Several companies are called Acme"),
            "Several companies are called Acme",
        ),
        (SessionQuotaError("Turn limit reached"), "Turn limit reached"),
        (RuntimeMismatchError("Start a new live thread"), "Start a new live thread"),
        (RuntimeError("provider failed"), PUBLIC_FAILURE_MESSAGE),
        # Operator configuration is not the visitor's to read or fix.
        (ConfigurationError("SEC_USER_AGENT is not set"), PUBLIC_FAILURE_MESSAGE),
    ],
)
def test_failed_turn_streams_a_public_error_and_keeps_prior_turns(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
    failure: Exception,
    shown: str,
) -> None:
    thread_id = _new_thread(client)
    before = _ask(client, thread_id, GUIDED_STORIES[0][1])

    def fail(*_args: Any, **_kwargs: Any) -> None:
        raise failure

    monkeypatch.setattr(api, "run_conversation_turn", fail)
    kind, data = _events(_post_turn(client, thread_id, "add Apple"))[-1]

    assert (kind, data) == ("error", {"message": shown})
    after = client.get(f"/api/threads/{thread_id}").json()
    assert after["turns"] == before["turns"]


def test_failed_turn_still_counts_against_the_thread_budget(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    thread_id = _new_thread(client)
    _ask(client, thread_id, GUIDED_STORIES[0][1])
    monkeypatch.setattr(
        api,
        "runtime_for",
        lambda _kind, *, settings, budget: SimpleNamespace(budget=budget),
    )

    def spend_then_fail(_thread_id: str, _message: str, runtime: Any, **_: Any) -> None:
        runtime.budget.consume_live_sec()
        raise RuntimeError("provider failed")

    monkeypatch.setattr(api, "run_conversation_turn", spend_then_fail)
    assert _events(_post_turn(client, thread_id, "add Apple"))[-1][0] == "error"

    saved = LocalThreadStore(tmp_path / "threads").load(thread_id)
    assert saved is not None
    assert saved.turn_count == 2
    assert saved.live_sec_requests == 1
    assert [message.content for message in saved.messages] == [GUIDED_STORIES[0][1]]


def test_thread_survives_an_api_restart(tmp_path: Path) -> None:
    root = tmp_path / "threads"
    first = TestClient(create_app(_settings(), store_root=root))
    thread_id = _new_thread(first)
    _ask(first, thread_id, GUIDED_STORIES[1][1])
    view = _ask(first, thread_id, "add Apple")

    restarted = TestClient(create_app(_settings(), store_root=root))

    assert restarted.get(f"/api/threads/{thread_id}").json() == view


def test_expired_thread_reloads_empty_and_is_purged(client: TestClient, tmp_path: Path) -> None:
    thread_id = _new_thread(client)
    _ask(client, thread_id, GUIDED_STORIES[0][1])
    store = LocalThreadStore(tmp_path / "threads")
    state = store.load(thread_id)
    assert state is not None
    store.save(state.model_copy(update={"updated_at": datetime(2020, 1, 1, tzinfo=UTC)}))

    view = client.get(f"/api/threads/{thread_id}").json()

    assert view["turns"] == []
    assert view["turn_count"] == 0
    assert store.load(thread_id) is None


def test_blank_message_is_rejected(client: TestClient) -> None:
    thread_id = _new_thread(client)
    assert _post_turn(client, thread_id, "   ").status_code == 422


@pytest.fixture
def runtimes_built(monkeypatch: pytest.MonkeyPatch) -> list[RuntimeKind]:
    """Record the runtime each turn asks for; serve recorded providers so tests stay offline."""
    built: list[RuntimeKind] = []

    def fake_runtime_for(kind: RuntimeKind, *, settings: Settings, **_: Any) -> Runtime:
        built.append(kind)
        return replace(recorded_runtime(), kind=resolve_runtime_kind(kind, settings))

    monkeypatch.setattr(api, "runtime_for", fake_runtime_for)
    return built


def test_thread_is_created_on_the_runtime_asked_for(
    client: TestClient, runtimes_built: list[RuntimeKind]
) -> None:
    recorded = client.post("/api/threads", json={"runtime": "recorded"}).json()
    live = client.post("/api/threads", json={"runtime": "live"}).json()

    assert recorded["runtime"] == "recorded"
    assert live["runtime"] == "live"
    assert recorded["notice"] is None and live["notice"] is None
    assert client.get(f"/api/threads/{recorded['thread_id']}").json()["runtime"] == "recorded"
    assert client.get(f"/api/threads/{live['thread_id']}").json()["runtime"] == "live"


def test_thread_without_a_runtime_takes_the_deployment_default(tmp_path: Path) -> None:
    client = TestClient(create_app(_settings(app_mode=AppMode.LIVE), store_root=tmp_path))
    assert client.post("/api/threads").json()["runtime"] == "live"


def test_turns_follow_the_thread_runtime(
    client: TestClient, runtimes_built: list[RuntimeKind]
) -> None:
    live = _new_thread(client, "live")
    recorded = _new_thread(client, "recorded")

    _ask(client, live, GUIDED_STORIES[0][1])
    _ask(client, recorded, GUIDED_STORIES[0][1])
    view = _ask(client, live, "add Apple")

    assert runtimes_built == [RuntimeKind.LIVE, RuntimeKind.RECORDED, RuntimeKind.LIVE]
    assert view["runtime"] == "live"
    assert len(view["turns"]) == 2


def test_locked_public_demo_creates_live_request_as_recorded(tmp_path: Path) -> None:
    client = TestClient(
        create_app(_settings(app_mode=AppMode.LIVE, public_demo=True), store_root=tmp_path)
    )
    created = client.post("/api/threads", json={"runtime": "live"}).json()

    assert created["runtime"] == "recorded"
    assert created["notice"] == "Live runtime is off on the public demo"
    view = _ask(client, created["thread_id"], GUIDED_STORIES[0][1])
    assert view["runtime"] == "recorded"


def test_turn_on_a_thread_bound_to_the_other_runtime_streams_a_public_error(
    tmp_path: Path, runtimes_built: list[RuntimeKind]
) -> None:
    open_demo = TestClient(create_app(_settings(), store_root=tmp_path))
    thread_id = _new_thread(open_demo, "live")
    locked_demo = TestClient(
        create_app(_settings(app_mode=AppMode.LIVE, public_demo=True), store_root=tmp_path)
    )

    events = _events(_post_turn(locked_demo, thread_id, GUIDED_STORIES[0][1]))

    kind, data = events[-1]
    assert kind == "error"
    assert data["message"] == (
        "This thread runs on the live runtime and cannot take a recorded turn. "
        "Start over to switch runtime."
    )
    view = locked_demo.get(f"/api/threads/{thread_id}").json()
    assert view["turns"] == []
    assert view["turn_count"] == 0
    assert view["runtime"] == "live"


def test_turn_request_no_longer_carries_a_runtime_flag(client: TestClient) -> None:
    thread_id = _new_thread(client)
    response = client.post(
        f"/api/threads/{thread_id}/turns", json={"message": "hi", "recorded": False}
    )
    assert response.status_code == 422


# --- Only the window's proxy may call the API (ADR 0006, ticket 03) ---

PROXY_TOKEN = "s3cret-proxy-token"
PROXY_HEADER = "X-Proxy-Token"  # web/lib/proxy.ts sends this name


@pytest.fixture
def guarded(tmp_path: Path) -> TestClient:
    return TestClient(
        create_app(_settings(api_proxy_token=PROXY_TOKEN), store_root=tmp_path / "threads")
    )


@pytest.mark.parametrize("header", [None, "", "wrong-token", PROXY_TOKEN + "x"])
def test_token_set_refuses_requests_without_the_matching_header(
    guarded: TestClient, header: str | None
) -> None:
    headers = {} if header is None else {PROXY_HEADER: header}
    for method, path, body in (
        ("GET", "/api/meta", None),
        ("POST", "/api/threads", {}),
        ("GET", f"/api/threads/{'0' * 8}-0000-0000-0000-{'0' * 12}", None),
        ("POST", f"/api/threads/{'0' * 8}-0000-0000-0000-{'0' * 12}/turns", {"message": "hi"}),
        ("DELETE", f"/api/threads/{'0' * 8}-0000-0000-0000-{'0' * 12}", None),
        ("GET", "/api/openapi.json", None),
    ):
        response = guarded.request(method, path, json=body, headers=headers)
        assert response.status_code == 401, (method, path)
        assert response.json() == {"detail": "Not authorized."}
        assert PROXY_TOKEN not in response.text


def test_token_set_serves_requests_with_the_matching_header(guarded: TestClient) -> None:
    guarded.headers[PROXY_HEADER] = PROXY_TOKEN
    assert guarded.get("/api/meta").status_code == 200
    thread_id = _new_thread(guarded)
    data = _ask(guarded, thread_id, GUIDED_STORIES[0][1])
    assert data["turns"][0]["presentation"]["fact_card"] is not None


def test_health_check_answers_with_or_without_the_token(guarded: TestClient) -> None:
    assert guarded.get("/api/health").json() == {"status": "ok"}
    assert guarded.get("/api/health", headers={PROXY_HEADER: "wrong"}).status_code == 200


def test_token_unset_needs_no_header(client: TestClient) -> None:
    assert client.get("/api/meta").status_code == 200
    assert client.get("/api/meta", headers={PROXY_HEADER: "anything"}).status_code == 200
    _ask(client, _new_thread(client), GUIDED_STORIES[0][1])


def test_token_comparison_is_constant_time(
    guarded: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    compared: list[tuple[bytes, bytes]] = []
    real = api.hmac.compare_digest

    def spy(a: bytes, b: bytes) -> bool:
        compared.append((a, b))
        return real(a, b)

    monkeypatch.setattr(api.hmac, "compare_digest", spy)
    guarded.get("/api/meta", headers={PROXY_HEADER: "wrong"})
    assert compared == [(b"wrong", PROXY_TOKEN.encode())]


def test_public_demo_without_a_token_warns_at_startup(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.WARNING, logger="financial_analyst_agent")
    create_app(_settings(public_demo=True), store_root=tmp_path)
    assert any("API_PROXY_TOKEN" in record.getMessage() for record in caplog.records)


@pytest.mark.parametrize(
    "overrides", [{"public_demo": False}, {"public_demo": True, "api_proxy_token": "t"}]
)
def test_no_startup_warning_locally_or_with_a_token(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, overrides: dict[str, Any]
) -> None:
    caplog.set_level(logging.WARNING, logger="financial_analyst_agent")
    create_app(_settings(**overrides), store_root=tmp_path)
    assert not any("API_PROXY_TOKEN" in record.getMessage() for record in caplog.records)


def test_proxy_token_is_not_shown_in_settings_repr() -> None:
    assert PROXY_TOKEN not in repr(_settings(api_proxy_token=PROXY_TOKEN))


# --- A turn always ends, and nothing else disturbs its thread while it runs ---


def _post_turn_within(
    client: TestClient, thread_id: str, message: str, seconds: float = 30.0
) -> Any:
    """POST a turn, failing (not hanging) if its stream never ends."""
    outcome: dict[str, Any] = {}

    def call() -> None:
        outcome["response"] = _post_turn(client, thread_id, message)

    worker = threading.Thread(target=call, daemon=True)
    worker.start()
    worker.join(seconds)
    assert not worker.is_alive(), "the turn stream never sent a terminal event"
    return outcome["response"]


def _boom(*_: Any, **__: Any) -> Any:
    raise FileNotFoundError("evidence gone")


@pytest.mark.parametrize(
    "broken",
    [
        {"thread_view": _boom},
        {"persist_session_budget": _boom},
        {"run_conversation_turn": _boom, "persist_session_budget": _boom},
    ],
    ids=["thread-view", "budget-after-success", "budget-after-failure"],
)
def test_a_failure_after_the_turn_still_ends_the_stream_with_one_public_error(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, broken: dict[str, Any]
) -> None:
    thread_id = _new_thread(client)
    for name, replacement in broken.items():
        monkeypatch.setattr(api, name, replacement)

    events = _events(_post_turn_within(client, thread_id, GUIDED_STORIES[0][1]))

    terminal = [event for event in events if event[0] != "progress"]
    assert terminal == [("error", {"message": PUBLIC_FAILURE_MESSAGE})]
    monkeypatch.undo()
    assert _post_turn_within(client, thread_id, "hi").status_code == 200


def test_a_running_turn_keeps_its_thread_past_the_ttl(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "threads"
    client = TestClient(create_app(_settings(thread_ttl_seconds=60), store_root=root))
    store = LocalThreadStore(root)
    thread_id = _new_thread(client)
    _ask(client, thread_id, GUIDED_STORIES[1][1])
    seen: dict[str, Any] = {}
    real_turn = api.run_conversation_turn

    def long_turn(*args: Any, **kwargs: Any) -> Any:
        # The turn outlives the TTL; meanwhile another visitor's GET purges
        # expired threads, and a reload of this window reads this one.
        aged = store.load(thread_id)
        assert aged is not None
        store.save(aged.model_copy(update={"updated_at": datetime.now(UTC) - timedelta(hours=3)}))
        client.get(f"/api/threads/{uuid.uuid4()}")
        seen["mid_turn"] = client.get(f"/api/threads/{thread_id}").json()
        return real_turn(*args, **kwargs)

    monkeypatch.setattr(api, "run_conversation_turn", long_turn)
    view = _ask(client, thread_id, "add Apple")

    assert seen["mid_turn"]["turn_in_flight"] is True
    assert len(seen["mid_turn"]["turns"]) == 1
    assert len(view["turns"]) == 2
    assert view["turn_in_flight"] is False
    assert client.get(f"/api/threads/{thread_id}").json()["turn_in_flight"] is False


def test_start_over_holds_the_thread_while_it_clears(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    thread_id = _new_thread(client)
    during: dict[str, int] = {}
    real_clear = LocalThreadStore.clear

    def clear(self: LocalThreadStore, cleared: str) -> None:
        during["turn"] = _post_turn(client, cleared, "hi").status_code
        real_clear(self, cleared)

    monkeypatch.setattr(LocalThreadStore, "clear", clear)
    assert client.delete(f"/api/threads/{thread_id}").status_code == 204
    assert during["turn"] == 409


def test_turn_locks_do_not_outlive_their_turns(client: TestClient) -> None:
    thread_id = _new_thread(client)
    _ask(client, thread_id, GUIDED_STORIES[0][1])
    for _ in range(3):
        assert client.delete(f"/api/threads/{uuid.uuid4()}").status_code == 204
    assert client.delete(f"/api/threads/{thread_id}").status_code == 204
    app: Any = client.app
    assert len(app.state.turn_locks) == 0


def test_an_unreadable_thread_file_reads_as_an_empty_thread(tmp_path: Path) -> None:
    root = tmp_path / "threads"
    client = TestClient(create_app(_settings(), store_root=root))
    thread_id = _new_thread(client)
    (root / f"{thread_id}.json").write_text('{"thread_id": "', encoding="utf-8")

    response = client.get(f"/api/threads/{thread_id}")

    assert response.status_code == 200
    assert response.json()["runtime"] is None
    assert response.json()["turns"] == []


# --- Admission: only threads the API created take turns, and only a few at once ---


def _record_turns(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    ran: list[str] = []

    def record(thread_id: str, *_: Any, **__: Any) -> None:
        ran.append(thread_id)

    monkeypatch.setattr(api, "run_conversation_turn", record)
    return ran


def test_a_turn_on_a_thread_never_created_is_refused_before_any_work(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    ran = _record_turns(monkeypatch)
    thread_id = str(uuid.uuid4())

    response = _post_turn(client, thread_id, "hi")

    assert response.status_code == 404
    assert response.json() == {"detail": "Unknown thread."}
    assert ran == []
    assert not any(t.name == f"turn-{thread_id}" for t in threading.enumerate())
    assert list((tmp_path / "threads").glob("*.json")) == []
    app: Any = client.app
    assert len(app.state.turn_locks) == 0
    assert len(app.state.turn_slots) == 0


def test_a_turn_on_an_expired_thread_is_refused_and_the_thread_cleared(
    client: TestClient, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    thread_id = _new_thread(client)
    store = LocalThreadStore(tmp_path / "threads")
    state = store.load(thread_id)
    assert state is not None
    store.save(state.model_copy(update={"updated_at": datetime(2020, 1, 1, tzinfo=UTC)}))
    ran = _record_turns(monkeypatch)

    response = _post_turn(client, thread_id, "hi")

    assert response.status_code == 404
    assert ran == []
    assert store.load(thread_id) is None


class _HeldTurn:
    """Stands in for ``run_conversation_turn``: the first call waits until let go."""

    def __init__(self, real: Any) -> None:
        self.started = threading.Event()
        self.go = threading.Event()
        self.calls = 0
        self._real = real

    def __call__(self, *args: Any, **kwargs: Any) -> Any:
        self.calls += 1
        if self.calls == 1:
            self.started.set()
            assert self.go.wait(10), "the held turn was never let go"
        return self._real(*args, **kwargs)


def test_a_turn_past_the_process_cap_is_refused_busy_until_a_slot_frees(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = TestClient(create_app(_settings(max_concurrent_turns=1), store_root=tmp_path))
    first, second = _new_thread(client), _new_thread(client)
    held = _HeldTurn(api.run_conversation_turn)
    monkeypatch.setattr(api, "run_conversation_turn", held)
    outcome: dict[str, Any] = {}

    def ask_first() -> None:
        outcome["response"] = _post_turn(client, first, GUIDED_STORIES[0][1])

    running = threading.Thread(target=ask_first, daemon=True)
    running.start()
    assert held.started.wait(10)

    busy = _post_turn(client, second, GUIDED_STORIES[0][1])

    assert busy.status_code == 429
    assert busy.json() == {"detail": "The analysis service is busy. Please try again in a moment."}
    assert busy.headers["retry-after"] == "5"
    assert held.calls == 1
    app: Any = client.app
    assert not app.state.turn_locks.held(second)
    # Only turns are capped: the wake-up check and thread creation still answer.
    assert client.get("/api/health").json() == {"status": "ok"}
    assert client.post("/api/threads").status_code == 201

    held.go.set()
    running.join(30)
    assert _events(outcome["response"])[-1][0] == "thread"
    assert len(app.state.turn_slots) == 0
    assert _ask(client, second, GUIDED_STORIES[0][1])["turn_count"] == 1


def test_waiting_for_a_busy_slot_does_not_use_up_the_hour(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # The window retries a busy turn on its own; those tries are not questions asked.
    client = TestClient(
        create_app(
            _settings(max_concurrent_turns=1, client_turns_per_hour=2), store_root=tmp_path
        )
    )
    first, second = _new_thread(client), _new_thread(client)
    held = _HeldTurn(api.run_conversation_turn)
    monkeypatch.setattr(api, "run_conversation_turn", held)
    outcome: dict[str, Any] = {}
    running = threading.Thread(
        target=lambda: outcome.setdefault("response", _post_turn(client, first, "hi")),
        daemon=True,
    )
    running.start()
    assert held.started.wait(10)

    for _ in range(3):
        assert _post_turn(client, second, GUIDED_STORIES[0][1]).status_code == 429

    held.go.set()
    running.join(30)
    assert _ask(client, second, GUIDED_STORIES[0][1])["turn_count"] == 1


def test_a_failed_turn_frees_its_slot(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    thread_id = _new_thread(client)
    monkeypatch.setattr(api, "run_conversation_turn", _boom)

    assert _events(_post_turn_within(client, thread_id, "hi"))[-1][0] == "error"

    app: Any = client.app
    assert len(app.state.turn_slots) == 0


def test_a_turn_keeps_its_slot_after_the_reader_leaves_and_frees_it_when_done(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    app = create_app(_settings(max_concurrent_turns=1), store_root=tmp_path)
    client = TestClient(app)
    thread_id = _new_thread(client)
    held = _HeldTurn(api.run_conversation_turn)
    monkeypatch.setattr(api, "run_conversation_turn", held)
    path = f"/api/threads/{thread_id}/turns"
    scope = {
        "type": "http",
        # Below ASGI 2.4, Starlette listens for the reader's disconnect.
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": "POST",
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "root_path": "",
        "headers": [(b"content-type", b"application/json")],
        "client": ("testclient", 50000),
        "server": ("testserver", 80),
    }

    async def read_the_first_event_then_leave() -> None:
        request = {
            "type": "http.request",
            "body": json.dumps({"message": GUIDED_STORIES[0][1]}).encode(),
            "more_body": False,
        }
        first_event = asyncio.Event()
        messages = [request]

        async def receive() -> dict[str, Any]:
            if messages:
                return messages.pop()
            await first_event.wait()
            return {"type": "http.disconnect"}

        async def send(message: dict[str, Any]) -> None:
            if message["type"] == "http.response.body" and message.get("body"):
                first_event.set()

        await app(scope, receive, send)  # returns once the reader has gone
        assert held.started.wait(10)
        assert len(app.state.turn_slots) == 1, "the turn still runs, so it holds its slot"

        held.go.set()
        [worker] = [t for t in threading.enumerate() if t.name == f"turn-{thread_id}"]
        await asyncio.to_thread(worker.join, 30)
        assert not worker.is_alive()

    asyncio.run(read_the_first_event_then_leave())

    assert len(app.state.turn_slots) == 0
    assert len(app.state.turn_locks) == 0
    assert client.get(f"/api/threads/{thread_id}").json()["turn_count"] == 1


def test_a_turn_begun_as_a_reload_reads_is_not_expired_by_that_reload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "threads"
    client = TestClient(create_app(_settings(thread_ttl_seconds=60), store_root=root))
    thread_id = _new_thread(client)
    _ask(client, thread_id, GUIDED_STORIES[0][1])
    client.get(f"/api/threads/{uuid.uuid4()}")  # spends this minute's purge
    store = LocalThreadStore(root)
    state = store.load(thread_id)
    assert state is not None
    store.save(state.model_copy(update={"updated_at": datetime.now(UTC) - timedelta(hours=3)}))
    app: Any = client.app
    real_read = LocalThreadStore._read

    def a_turn_begins_as_the_reload_reads(path: Path) -> Any:
        # The reload saw no turn in flight; one starts before the store decides.
        app.state.turn_locks.try_acquire(thread_id)
        return real_read(path)

    monkeypatch.setattr(LocalThreadStore, "_read", staticmethod(a_turn_begins_as_the_reload_reads))
    view = client.get(f"/api/threads/{thread_id}").json()
    monkeypatch.undo()

    assert len(view["turns"]) == 1
    assert store.load(thread_id) is not None
    assert any((root / "evidence" / thread_id).iterdir())


def test_an_overlong_message_is_refused_without_echoing_it(client: TestClient) -> None:
    thread_id = _new_thread(client)
    message = "x" * 2001
    response = client.post(f"/api/threads/{thread_id}/turns", json={"message": message})
    assert response.status_code == 422
    assert response.json() == {
        "detail": "That message is longer than 2,000 characters. Shorten it and send it again."
    }
    assert message not in response.text


def test_a_visitor_is_limited_to_a_number_of_new_threads_an_hour(tmp_path: Path) -> None:
    app = create_app(
        _settings(client_threads_per_hour=2, api_proxy_token=SecretStr("t")),
        store_root=tmp_path / "threads",
    )
    client = TestClient(app, headers={"x-proxy-token": "t"})

    def create(ip: str) -> Any:
        return client.post("/api/threads", json={}, headers={"x-client-ip": ip})

    assert [create("1.1.1.1").status_code for _ in range(2)] == [201, 201]
    refused = create("1.1.1.1")
    assert refused.status_code == 429
    assert int(refused.headers["retry-after"]) > 0
    # Another visitor behind the same proxy is counted separately.
    assert create("2.2.2.2").status_code == 201


def test_a_visitor_is_limited_to_a_number_of_turns_an_hour(tmp_path: Path) -> None:
    client = TestClient(
        create_app(_settings(client_turns_per_hour=1), store_root=tmp_path / "threads")
    )
    first, second = _new_thread(client), _new_thread(client)

    assert _post_turn(client, first, GUIDED_STORIES[0][1]).status_code == 200
    assert _post_turn(client, second, GUIDED_STORIES[0][1]).status_code == 429


def test_the_rate_limit_forgets_events_older_than_its_window() -> None:
    limit = api.ClientRateLimit(1, window_seconds=10)

    assert limit.try_acquire("a", now=0) is None
    assert limit.try_acquire("a", now=5) == pytest.approx(5)
    assert limit.try_acquire("a", now=10.5) is None


def test_a_refund_of_a_clients_only_event_leaves_the_limit_working() -> None:
    # A busy 429 refunds the visitor's only event; the next sweep used to read
    # that emptied record and fail every turn, for everyone, until a restart.
    limit = api.ClientRateLimit(2, window_seconds=10)

    assert limit.try_acquire("a", now=0) is None
    limit.refund("a")

    assert limit.try_acquire("b", now=1) is None
    assert limit.try_acquire("a", now=2) is None
    assert limit.try_acquire("a", now=3) is None
    assert limit.try_acquire("a", now=4) == pytest.approx(8)


def test_an_oversized_body_is_refused(client: TestClient) -> None:
    thread_id = _new_thread(client)
    padded = '{"message": "Apple revenue"' + " " * 20_000 + "}"

    response = client.post(
        f"/api/threads/{thread_id}/turns",
        content=padded,
        headers={"content-type": "application/json"},
    )

    assert response.status_code == 413


def test_a_turn_must_be_sent_as_json(client: TestClient) -> None:
    thread_id = _new_thread(client)

    as_form = client.post(
        f"/api/threads/{thread_id}/turns",
        content='{"message": "Apple revenue"}',
        headers={"content-type": "text/plain"},
    )
    create_as_form = client.post(
        "/api/threads", content="a=1", headers={"content-type": "application/x-www-form-urlencoded"}
    )

    # Refused for its type before its body is validated.
    assert as_form.status_code == 415
    assert as_form.json() == {"detail": "Send the request as JSON."}
    assert create_as_form.status_code == 415


@pytest.mark.parametrize("message", ["   ", "​​", "‮⁦ ‍"])
def test_an_invisible_message_asks_for_a_question(client: TestClient, message: str) -> None:
    thread_id = _new_thread(client)

    response = _post_turn(client, thread_id, message)

    assert response.status_code == 422
    assert response.json()["detail"] == "Ask a question."
    assert client.get(f"/api/threads/{thread_id}").json()["turn_count"] == 0


def test_trailing_spaces_do_not_count_against_the_length_limit(client: TestClient) -> None:
    thread_id = _new_thread(client)
    message = GUIDED_STORIES[0][1] + " " * 2000

    assert _post_turn(client, thread_id, message).status_code == 200


def test_the_public_demo_does_not_publish_its_api_docs(tmp_path: Path) -> None:
    public = TestClient(create_app(_settings(public_demo=True), store_root=tmp_path / "a"))
    private = TestClient(create_app(_settings(), store_root=tmp_path / "b"))

    assert public.get("/api/docs").status_code == 404
    assert public.get("/api/openapi.json").status_code == 404
    assert private.get("/api/openapi.json").status_code == 200


def test_health_answers_head_requests(client: TestClient) -> None:
    head = client.head("/api/health")
    get = client.get("/api/health")

    assert head.status_code == 200
    # A proxy passes a HEAD through only with the GET's headers.
    assert head.headers["content-type"] == get.headers["content-type"] == "application/json"
    assert head.headers["content-length"] == get.headers["content-length"]
    assert head.content == b""


def test_a_misconfigured_deployment_does_not_charge_the_turn(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    thread_id = _new_thread(client)

    def fail(*_args: Any, **_kwargs: Any) -> None:
        raise ConfigurationError("SEC_USER_AGENT is not set")

    monkeypatch.setattr(api, "run_conversation_turn", fail)
    kind, data = _events(_post_turn(client, thread_id, "Apple revenue"))[-1]

    assert (kind, data) == ("error", {"message": PUBLIC_FAILURE_MESSAGE})
    assert client.get(f"/api/threads/{thread_id}").json()["turn_count"] == 0


def test_a_stuck_turn_ends_with_an_error_and_frees_its_thread_and_slot(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    client = TestClient(
        create_app(
            _settings(turn_timeout_seconds=0.3, max_concurrent_turns=1),
            store_root=tmp_path / "threads",
        )
    )
    thread_id = _new_thread(client)
    let_go = threading.Event()

    def stuck(_thread_id: str, _message: str, _runtime: Any, *, store: Any, **_: Any) -> None:
        let_go.wait(10)
        # A late finish must not land on the thread the visitor has moved on with.
        store.save(store.load(thread_id).model_copy(update={"turn_count": 99}))

    monkeypatch.setattr(api, "run_conversation_turn", stuck)
    started = time.monotonic()
    events = _events(_post_turn_within(client, thread_id, "Apple revenue", seconds=5))

    assert time.monotonic() - started < 3
    assert events[-1] == ("error", {"message": api.TURN_TIMED_OUT_MESSAGE})
    app: Any = client.app
    assert len(app.state.turn_locks) == 0
    assert len(app.state.turn_slots) == 0
    assert client.get(f"/api/threads/{thread_id}").json()["turn_count"] == 1
    let_go.set()
    time.sleep(0.2)
    assert client.get(f"/api/threads/{thread_id}").json()["turn_count"] == 1
    assert client.delete(f"/api/threads/{thread_id}").status_code == 204


def test_a_turn_runs_within_its_sec_time_budget(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    from financial_analyst_agent.providers.sec.client import sec_turn_seconds_left

    seen: list[float] = []

    def note_budget(*_args: Any, **_kwargs: Any) -> None:
        seen.append(sec_turn_seconds_left())

    monkeypatch.setattr(api, "run_conversation_turn", note_budget)
    _ask(client, _new_thread(client), "Apple revenue")

    assert len(seen) == 1
    assert 0 < seen[0] <= Settings().sec_turn_budget_seconds


def test_a_failed_turn_restarts_its_threads_expiry_clock(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "threads"
    client = TestClient(create_app(_settings(thread_ttl_seconds=60), store_root=root))
    thread_id = _new_thread(client)
    store = LocalThreadStore(root)
    state = store.load(thread_id)
    assert state is not None
    # Saved 59 s ago: the failed turn below outlives what was left of its hour.
    almost = datetime.now(UTC) - timedelta(seconds=59)
    store.save(state.model_copy(update={"updated_at": almost}))

    def slow_failure(*_args: Any, **_kwargs: Any) -> None:
        time.sleep(1.5)
        raise RuntimeError("provider failed")

    monkeypatch.setattr(api, "run_conversation_turn", slow_failure)
    assert _events(_post_turn(client, thread_id, "Apple revenue"))[-1][0] == "error"

    view = client.get(f"/api/threads/{thread_id}").json()
    assert view["turn_count"] == 1


def test_refused_turns_do_not_use_up_the_visitors_hour(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "threads"
    client = TestClient(
        create_app(_settings(client_turns_per_hour=1, max_turns_per_thread=1), store_root=root)
    )
    _record_turns(monkeypatch)
    full = _new_thread(client)
    store = LocalThreadStore(root)
    state = store.load(full)
    assert state is not None
    store.save(state.model_copy(update={"turn_count": 1}))
    busy = _new_thread(client)
    app: Any = client.app
    assert app.state.turn_locks.try_acquire(busy)

    assert _post_turn(client, str(uuid.uuid4()), "hi").status_code == 404
    assert _post_turn(client, busy, "hi").status_code == 409
    over_cap = _events(_post_turn(client, full, "hi"))
    assert over_cap[-1][0] == "error"
    assert "turn limit" in over_cap[-1][1]["message"]
    app.state.turn_locks.release(busy)

    assert _post_turn(client, busy, "hi").status_code == 200
    assert len(app.state.turn_locks) == 0


def test_a_quota_refusal_is_logged_without_a_traceback(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    client = TestClient(create_app(_settings(max_turns_per_thread=1), store_root=tmp_path))
    thread_id = _new_thread(client)
    _ask(client, thread_id, GUIDED_STORIES[0][1])

    with caplog.at_level(logging.INFO, logger="financial_analyst_agent"):
        assert _events(_post_turn(client, thread_id, "add Apple"))[-1][0] == "error"

    refusals = [record for record in caplog.records if record.msg == "api_turn_over_cap"]
    assert [record.levelno for record in refusals] == [logging.INFO]
    assert not any(record.exc_info for record in caplog.records)


def test_a_streamed_oversized_body_is_refused_in_our_words(client: TestClient) -> None:
    thread_id = _new_thread(client)

    def chunks() -> Any:
        yield b'{"message": "Apple revenue"'
        for _ in range(40):
            yield b" " * 1024
        yield b"}"

    response = client.post(
        f"/api/threads/{thread_id}/turns",
        content=chunks(),
        headers={"content-type": "application/json"},
    )

    assert response.status_code == 413
    assert response.json() == {"detail": "That request is too large for the analysis service."}


def test_a_body_that_cannot_be_read_is_refused_in_our_words(client: TestClient) -> None:
    thread_id = _new_thread(client)

    response = client.post(
        f"/api/threads/{thread_id}/turns",
        content=b'{"message": "\xff\xfe"}',
        headers={"content-type": "application/json"},
    )

    assert response.status_code in (400, 422)
    assert "error parsing the body" not in response.text


def test_a_trailing_slash_is_not_redirected(client: TestClient) -> None:
    response = client.get("/api/health/", follow_redirects=False)

    assert response.status_code == 404
    assert "location" not in response.headers


def test_the_new_conversation_limit_says_how_long_to_wait(tmp_path: Path) -> None:
    client = TestClient(
        create_app(_settings(client_threads_per_hour=1), store_root=tmp_path / "threads")
    )
    assert client.post("/api/threads", json={}).status_code == 201

    refused = client.post("/api/threads", json={})

    assert refused.status_code == 429
    detail = refused.json()["detail"]
    assert "conversations" in detail
    assert "about 60 minutes" in detail


@pytest.mark.parametrize(
    ("wait_seconds", "shown"),
    [
        # Both requests in one clock tick: (t + 3600) - t comes out a hair over 3600.
        ((496.00625 + 3600.0) - 496.00625, "about 60 minutes"),
        (3599.2, "about 60 minutes"),
        (3601.0, "about 61 minutes"),
        (20.0, "about 1 minute,"),
    ],
)
def test_the_conversation_limit_counts_whole_minutes(wait_seconds: float, shown: str) -> None:
    assert shown in threads_limited_message(wait_seconds)


def test_starting_a_thread_also_purges_expired_ones(tmp_path: Path) -> None:
    root = tmp_path / "threads"
    store = LocalThreadStore(root)
    old = "11111111-1111-4111-8111-111111111111"
    store.save(ThreadState(thread_id=old, updated_at=datetime(2020, 1, 1, tzinfo=UTC)))
    client = TestClient(create_app(_settings(), store_root=root))

    _new_thread(client)

    deadline = time.monotonic() + 5
    while (root / f"{old}.json").exists() and time.monotonic() < deadline:
        time.sleep(0.02)
    assert not (root / f"{old}.json").exists()


def test_uvicorn_does_not_trust_forwarded_headers(monkeypatch: pytest.MonkeyPatch) -> None:
    import uvicorn

    seen: dict[str, Any] = {}
    monkeypatch.setattr(uvicorn, "run", lambda *_args, **kwargs: seen.update(kwargs))

    api.main()

    assert seen["proxy_headers"] is False


def test_without_a_sec_user_agent_the_live_runtime_is_locked_and_says_so(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.WARNING, logger="financial_analyst_agent"):
        client = TestClient(
            create_app(
                _settings(app_mode=AppMode.LIVE, sec_user_agent=""), store_root=tmp_path
            )
        )
    meta = client.get("/api/meta").json()
    created = client.post("/api/threads", json={"runtime": "live"}).json()

    assert meta["runtime"] == {"default": "recorded", "locked": True}
    assert created["runtime"] == "recorded"
    assert created["notice"] == "Live runtime is off on this server"
    assert any("SEC_USER_AGENT is not set" in record.getMessage() for record in caplog.records)
