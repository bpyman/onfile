# 04 — "18 months" and "a couple of years" are windows without "last" or "past"

**What to build:** Found by the two-axis review of PRs #69-#90 (6 October 2026), spec axis. The README's window row lists `18 months`, and the window rules count `a couple of years` as 8 quarters. `Apple revenue 18 months` and `Apple revenue a couple of years` show the latest quarter, because `period_window.py` (about line 61) reads a count of months or years only after a recency word or a preposition (`last`, `past`, `over`, `for`). Read a bare count of quarters, months or years after a metric as that window too: `Apple revenue 18 months`, `apple revenue 2 years`, `MSFT net income a couple of years`, `Apple revenue 6 quarters`.

Do not read a count that names something else: `12-month` in `trailing 12-month revenue` is the trailing year, and a fiscal-year phrase (`fiscal 2025`) is a named period.

**Acceptance:** phrase-coverage window cases for each bare form above, each the count the README gives; `trailing 12-month revenue` unchanged. `uv run python -m pytest` passes; `uv run python scripts/compare_answers.py` names every conversation whose answer changes, and each change is intended.

**Blocked by:** None — can start immediately

**Status:** ready-for-agent
