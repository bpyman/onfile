# 15 — Offline scripts use the app's constants

**What to build:** `scripts/record_sec_fixtures.py` and `scripts/trim_sec_test_fixture.py` restate the submissions columns that `providers/sec/submissions._KEPT_COLUMNS` holds; `scripts/build_everyday_words.py` and `record_sec_fixtures.py` rebuild snapshot paths that `universe.DEFAULT_SNAPSHOT_PATH` and `rules_planner.FIXTURE_UNIVERSE_SNAPSHOT_PATH` provide. Make the columns public and import both.

**Acceptance:** the scripts produce the same output; `uv run ruff check src tests scripts` passes.

Found by the 2026-10-04 simplify review of master (#67), which left it out as larger than a cleanup.

**Blocked by:** None — can start immediately

**Status:** ready-for-agent
