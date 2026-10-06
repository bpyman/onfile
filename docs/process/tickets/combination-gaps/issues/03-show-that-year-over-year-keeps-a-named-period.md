# 03 — "Show that year over year" keeps a named period

**What to build:** `Apple revenue for fiscal 2025` → `show that year over year` replaces fiscal 2025 with the latest 8 quarters. The README says that after a question about several quarters, `show that year over year` keeps those quarters; `_keep_window_for_change` (`request_wording.py`) keeps only a window of recent quarters (`last_n_quarters`). Keep a named period on screen too, each quarter with its year-over-year change. Depends on ticket 02 for how a named period shows the change.

Case: `combined_follow_up:Apple revenue for fiscal 2025 | show that year over year`.

Found by the combinations in phrase coverage ([report](../../../../evaluation/phrase-coverage.md), `src/financial_analyst_agent/phrase_coverage.py`), judged by the README's [How a question is read](../../../../../README.md#how-a-question-is-read). Each phrasing is read right alone; the gap is in how two readings combine, in the shared reading of words both planners pass through (ADR 0010, 0011), not in the rules planner alone.

**Acceptance:** the cases below are read right and taken off `KNOWN_GAPS`; `uv run python -m pytest tests/unit/test_phrase_coverage.py` passes; `uv run python scripts/compare_answers.py` names every conversation whose answer changes, and each change is intended.

**Blocked by:** 02

**Status:** resolved

## Answer

`_keep_window_for_change` (`request_wording.py`) keeps a named period on screen as it keeps a window: after `Apple revenue for fiscal 2025`, `show that year over year` (or `as growth`, `yoy please`) keeps fiscal 2025 and adds `year_over_year`, so each quarter shows its change from its own filing's comparative (ADR 0009, as ticket 02 reads a named period). A single named quarter is kept too, as `Q2 2025 year over year` shows Q2 2025 with its change. After quarter over quarter on a named period, year over year clears `company_base_dates`, so no quarter before is read as a base.

The case is off `KNOWN_GAPS`, which is now empty. The README's year-over-year row says the follow-up keeps a named period. `compare_answers` reports 0 of 244 conversations differ: no recorded demo follows a named period with year over year.
