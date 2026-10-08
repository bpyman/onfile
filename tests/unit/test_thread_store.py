"""LocalThreadStore durability: atomic saves, unreadable files, expiry that spares busy threads."""

from __future__ import annotations

import json
import threading
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from financial_analyst_agent import thread_store
from financial_analyst_agent.thread_store import LocalThreadStore, ThreadMessage, ThreadState

LONG_AGO = datetime(2026, 1, 1, tzinfo=UTC)
LATER = LONG_AGO + timedelta(days=1)


def test_a_failed_save_leaves_the_previous_checkpoint_whole(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = LocalThreadStore(tmp_path)
    first = ThreadState(thread_id="t", messages=(ThreadMessage(role="analyst", content="q1"),))
    store.save(first)

    def crash(*_: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(thread_store.os, "replace", crash)
    second = first.model_copy(update={"turn_count": 2})
    with pytest.raises(OSError):
        store.save(second)

    assert store.load("t") == first
    assert sorted(path.name for path in tmp_path.iterdir()) == ["evidence", "t.json"]


def test_an_unreadable_thread_file_reads_as_missing(tmp_path: Path) -> None:
    store = LocalThreadStore(tmp_path)
    (tmp_path / "torn.json").write_text('{"thread_id": "torn", "mess', encoding="utf-8")

    assert store.load("torn") is None
    assert store.load("torn", ttl_seconds=60) is None


def test_purge_spares_threads_the_caller_keeps(tmp_path: Path) -> None:
    store = LocalThreadStore(tmp_path)
    for thread_id in ("busy", "idle"):
        store.save(ThreadState(thread_id=thread_id, updated_at=LONG_AGO))

    removed = store.purge_expired(now=LATER, ttl_seconds=60, keep=lambda tid: tid == "busy")

    assert removed == 1
    assert store.load("busy") is not None
    assert store.load("idle") is None


def _write_evidence(root: Path, thread_id: str, name: str) -> Path:
    path = root / "evidence" / thread_id / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{}", encoding="utf-8")
    return path


def test_purge_never_deletes_a_checkpoint_saved_after_it_decided(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = LocalThreadStore(tmp_path)
    store.save(ThreadState(thread_id="t", updated_at=LONG_AGO))
    fresh = ThreadState(thread_id="t", updated_at=LATER, turn_count=1)
    real_read = LocalThreadStore._read
    reads: list[Path] = []

    def a_turn_finishes_after_the_scan(path: Path) -> ThreadState | None:
        state = real_read(path)
        if not reads:
            _write_evidence(tmp_path, "t", "result-1.json")
            store.save(fresh)
        reads.append(path)
        return state

    monkeypatch.setattr(LocalThreadStore, "_read", staticmethod(a_turn_finishes_after_the_scan))
    removed = store.purge_expired(now=LATER, ttl_seconds=60)
    monkeypatch.undo()

    assert removed == 0
    assert store.load("t") == fresh
    assert (tmp_path / "evidence" / "t" / "result-1.json").is_file()


def test_a_turn_that_starts_during_an_expiry_reads_only_once_it_is_done(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    store = LocalThreadStore(tmp_path)
    store.save(ThreadState(thread_id="t", updated_at=LONG_AGO))
    _write_evidence(tmp_path, "t", "result-old.json")
    clearing, go = threading.Event(), threading.Event()
    real_rmtree = thread_store.shutil.rmtree

    def slow_rmtree(path: Path) -> None:
        clearing.set()
        assert go.wait(10)
        real_rmtree(path)

    monkeypatch.setattr(thread_store.shutil, "rmtree", slow_rmtree)
    purging = threading.Thread(
        target=lambda: store.purge_expired(now=LATER, ttl_seconds=60), daemon=True
    )
    purging.start()
    assert clearing.wait(10)
    seen: dict[str, ThreadState | None] = {}

    def turn() -> None:
        seen["prior"] = store.load("t", now=LATER, ttl_seconds=60)
        _write_evidence(tmp_path, "t", "result-new.json")
        store.save(ThreadState(thread_id="t", updated_at=LATER, turn_count=1))

    turning = threading.Thread(target=turn, daemon=True)
    turning.start()
    turning.join(0.2)  # a turn not held back would have written its evidence by now
    go.set()
    purging.join(10)
    turning.join(10)

    assert seen["prior"] is None
    assert (tmp_path / "evidence" / "t" / "result-new.json").is_file()
    assert not (tmp_path / "evidence" / "t" / "result-old.json").exists()
    saved = store.load("t")
    assert saved is not None and saved.turn_count == 1


def test_load_spares_an_expired_thread_the_caller_keeps(tmp_path: Path) -> None:
    store = LocalThreadStore(tmp_path)
    stale = ThreadState(thread_id="t", updated_at=LONG_AGO)
    store.save(stale)
    evidence = _write_evidence(tmp_path, "t", "result-1.json")

    assert store.load("t", now=LATER, ttl_seconds=60, keep=lambda tid: tid == "t") == stale
    assert evidence.is_file()
    assert store.load("t", now=LATER, ttl_seconds=60) is None
    assert not evidence.exists()


@pytest.mark.parametrize("thread_id", ["..", "../x", "", "a" * 129, "a/b"])
def test_a_thread_id_that_is_not_a_plain_name_is_refused(tmp_path: Path, thread_id: str) -> None:
    store = LocalThreadStore(tmp_path)
    store.save(ThreadState(thread_id="kept"))

    with pytest.raises(ValueError):
        store.clear(thread_id)

    assert store.load("kept") is not None


def test_a_damaged_answer_is_left_out_of_its_thread(tmp_path: Path) -> None:
    from financial_analyst_agent.contracts import Intent, RendererKind, TurnResult

    store = LocalThreadStore(tmp_path)
    evidence = store.evidence_for("t")
    kept = evidence.put_result(
        TurnResult(
            intent=Intent.LOOKUP, tool_traces=[], renderer=RendererKind.REFUSE, message="kept"
        )
    )
    damaged = evidence.put_result(
        TurnResult(
            intent=Intent.LOOKUP, tool_traces=[], renderer=RendererKind.REFUSE, message="lost"
        )
    )
    (tmp_path / "evidence" / "t" / f"{damaged}.json").write_text("{", encoding="utf-8")
    state = ThreadState(thread_id="t", evidence_refs=(kept, damaged), last_result_ref=damaged)

    assert [result.message for result in store.resolve_results(state)] == ["kept"]
    assert store.resolve_last_result(state) is None


def test_a_thread_dated_in_the_future_expires(tmp_path: Path) -> None:
    store = LocalThreadStore(tmp_path)
    now = datetime(2026, 9, 30, tzinfo=UTC)
    store.save(ThreadState(thread_id="t", updated_at=now + timedelta(days=365)))

    assert store.load("t", now=now, ttl_seconds=7200) is None


def test_a_result_stored_when_a_change_row_said_yoy_still_loads() -> None:
    # The comparison base once had two spellings; a thread saved then holds "yoy".
    from financial_analyst_agent.contracts import TurnResult

    stored = json.dumps(
        {
            "intent": "lookup",
            "tool_traces": [],
            "renderer": "table",
            "table_rows": [
                {
                    "company_name": "Apple Inc.",
                    "ticker": "AAPL",
                    "cik": "0000320193",
                    "metric": "revenue",
                    "value": "10",
                    "comparison": "yoy",
                }
            ],
        }
    )

    (row,) = TurnResult.model_validate_json(stored).table_rows
    assert row.comparison == "year_over_year"


def test_a_stored_answer_is_read_by_its_ref_and_a_damaged_one_reads_as_none(
    tmp_path: Path,
) -> None:
    from financial_analyst_agent.contracts import Intent, RendererKind, TurnResult

    store = LocalThreadStore(tmp_path)
    evidence = store.evidence_for("t")
    kept = evidence.put_result(
        TurnResult(
            intent=Intent.LOOKUP, tool_traces=[], renderer=RendererKind.REFUSE, message="kept"
        )
    )
    damaged = evidence.put_result(
        TurnResult(
            intent=Intent.LOOKUP, tool_traces=[], renderer=RendererKind.REFUSE, message="lost"
        )
    )
    (tmp_path / "evidence" / "t" / f"{damaged}.json").write_text("{", encoding="utf-8")
    state = ThreadState(thread_id="t", evidence_refs=(kept, "facts-1", damaged))

    assert state.result_refs() == (kept, damaged)
    read = store.resolve_result("t", kept)
    assert read is not None and read.message == "kept"
    assert store.resolve_result("t", damaged) is None
    assert store.resolve_result("t", "result-never-written") is None
