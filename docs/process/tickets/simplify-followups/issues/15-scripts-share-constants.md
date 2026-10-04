# 15 — Offline scripts use the app's constants

**What to build:** `scripts/record_sec_fixtures.py` and `scripts/trim_sec_test_fixture.py` restate the submissions columns that `providers/sec/submissions._KEPT_COLUMNS` holds; `scripts/build_everyday_words.py` and `record_sec_fixtures.py` rebuild snapshot paths that `universe.DEFAULT_SNAPSHOT_PATH` and `rules_planner.FIXTURE_UNIVERSE_SNAPSHOT_PATH` provide. Make the columns public and import both.

**Acceptance:** the scripts produce the same output; `uv run ruff check src tests scripts` passes.

Found by the 2026-10-04 simplify review of master (#67), which left it out as larger than a cleanup.

**Blocked by:** None — can start immediately

**Status:** resolved

## Answer

Shipped 2026-10-04.

- `providers/sec/submissions.KEPT_COLUMNS` is public. `record_sec_fixtures.py`
  and `trim_sec_test_fixture.py` import it instead of restating the five
  columns. `record_sec_fixtures._quarterly_filings` now picks periodic rows by
  `row["form"]`, not by the column's position.
- `record_sec_fixtures.py` takes `LIVE_SNAPSHOT` and `FIXTURE_SNAPSHOT` from
  `universe.DEFAULT_SNAPSHOT_PATH` and `rules_planner.FIXTURE_UNIVERSE_SNAPSHOT_PATH`;
  `build_everyday_words.py` takes `SNAPSHOT` from `DEFAULT_SNAPSHOT_PATH`.
- `tests/unit/test_script_constants.py` loads each script and checks it holds
  the app's objects.
- Same output: `_quarterly_filings` returns identical tables (keys and order)
  on all 87 recorded submissions lists; `trim` keeps the same rows and values
  on all 19 test fixtures. One difference: a re-trimmed fixture lists its
  `recent` columns in the app's order (`form` first) rather than
  `accessionNumber` first. The committed fixtures are not regenerated.
