# 03 — "Show that year over year" keeps a named period

**What to build:** `Apple revenue for fiscal 2025` → `show that year over year` replaces fiscal 2025 with the latest 8 quarters. The README says that after a question about several quarters, `show that year over year` keeps those quarters; `_keep_window_for_change` (`request_wording.py`) keeps only a window of recent quarters (`last_n_quarters`). Keep a named period on screen too, each quarter with its year-over-year change. Depends on ticket 02 for how a named period shows the change.

Case: `combined_follow_up:Apple revenue for fiscal 2025 | show that year over year`.

Found by the combinations in phrase coverage ([report](../../../../evaluation/phrase-coverage.md), `src/financial_analyst_agent/phrase_coverage.py`), judged by the README's [How a question is read](../../../../../README.md#how-a-question-is-read). Each phrasing is read right alone; the gap is in how two readings combine, in the shared reading of words both planners pass through (ADR 0010, 0011), not in the rules planner alone.

**Acceptance:** the cases below are read right and taken off `KNOWN_GAPS`; `uv run python -m pytest tests/unit/test_phrase_coverage.py` passes; `uv run python scripts/compare_answers.py` names every conversation whose answer changes, and each change is intended.

**Blocked by:** 02

**Status:** ready-for-agent
