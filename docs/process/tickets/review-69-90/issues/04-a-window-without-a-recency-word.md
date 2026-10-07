# 04 — "18 months" and "a couple of years" are windows without "last" or "past"

**What to build:** Found by the two-axis review of PRs #69-#90 (6 October 2026), spec axis. The README's window row lists `18 months`, and the window rules count `a couple of years` as 8 quarters. `Apple revenue 18 months` and `Apple revenue a couple of years` show the latest quarter, because `period_window.py` (about line 61) reads a count of months or years only after a recency word or a preposition (`last`, `past`, `over`, `for`). Read a bare count of quarters, months or years after a metric as that window too: `Apple revenue 18 months`, `apple revenue 2 years`, `MSFT net income a couple of years`, `Apple revenue 6 quarters`.

Do not read a count that names something else: `12-month` in `trailing 12-month revenue` is the trailing year, and a fiscal-year phrase (`fiscal 2025`) is a named period.

**Acceptance:** phrase-coverage window cases for each bare form above, each the count the README gives; `trailing 12-month revenue` unchanged. `uv run python -m pytest` passes; `uv run python scripts/compare_answers.py` names every conversation whose answer changes, and each change is intended.

**Blocked by:** None — can start immediately

**Status:** resolved

## Answer

Resolved 6 October 2026. The window grammar (`period_window.py`) gains a fifth pattern: a count and a unit with no recency word or preposition. `Apple revenue 18 months` is 6 quarters, `apple revenue 2 years` and `MSFT net income a couple of years` 8, `Apple revenue 6 quarters` 6, each the count the README gives. The earliest match wins, so `last 4 quarters` keeps its "last" as the words that asked.

A count that names something else stays what it names, by the unit's existing guards: `3 months ended June` and `2 quarters ago` name a quarter, `fiscal 2025` and `FY2024` have no unit word, and `12-month` in `trailing 12-month revenue` has no space between count and unit, so it stays the trailing year (`TRAILING_YEAR`) and shows the latest 4 quarters as before.

Phrase coverage: `18 months` and `6 quarters` join `WINDOW_PHRASES` (asked as `Apple revenue …`); `apple revenue 2 years`, `MSFT net income a couple of years` and `Apple trailing 12-month revenue` (unchanged, `last_n_quarters 4`) join `WINDOW_QUESTIONS`. The rules planner is sure of every one, so none is sent to the LLM planner. `tests/unit/test_period_window.py` reads each bare form, rejects `fiscal 2025`, `FY2024` and `trailing 12-month`, and binds `Apple revenue 18 months` and `MSFT net income a couple of years` to the spec.

The README's window row and ADR 0010's "One period grammar" say the recency word may be left out after the metric and name the counts that are not windows. `scripts/compare_answers.py` gains `Apple revenue 18 months`; it is the one conversation that differs from HEAD (latest quarter before, 6 quarters now), as intended. 2,069 tests pass; ruff and mypy pass.
