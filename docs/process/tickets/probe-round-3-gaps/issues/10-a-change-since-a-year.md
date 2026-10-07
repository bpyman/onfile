# 10 — A change since a year is year over year since it, and "since 2025 year over year" reads a year

**What to build:** Decided in `rules-to-review.md` (2026-10-07, probe-round-3-gaps 09). Two parts:

- **A misreading.** `Apple revenue since 2025 year over year` reads `2025` as a count of quarters instead of the year a `since` window starts (noted in ticket 05's work). With any change word after it (`year over year`, `quarter over quarter`, `as growth`), `since 2025` is still the window since 2025 began.
- **The rule.** A change asked over a `since` window (`How much did Intel's revenue change since 2023?`, `What caused Apple's revenue to fall since 2023?`'s window, `Apple revenue growth since 2024`) is year over year over that window, as ticket 09 made every counted window: each filed quarter since the year began, with its year-over-year change. A change that names no base and no window still asks against what.

Change `test_what_a_change_is_measured_against`'s expectations for the since-window questions with the reading, and say so in the commit.

**Acceptance:** on the recorded runtime, `Apple revenue since 2025 year over year` shows the quarters since 2025 began, each with its year-over-year change; `How much did Intel's revenue change since 2023?` the same over its window; `How much did Intel's revenue change?` still asks; phrase-coverage cases for each. `uv run python -m pytest` passes; `uv run python scripts/compare_answers.py` names every conversation whose answer changes, and each change is intended.

**Blocked by:** None — can start immediately

**Status:** ready-for-agent
