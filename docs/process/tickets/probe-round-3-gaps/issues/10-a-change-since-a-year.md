# 10 — A change since a year is year over year since it, and "since 2025 year over year" reads a year

**What to build:** Decided in `rules-to-review.md` (2026-10-07, probe-round-3-gaps 09). Two parts:

- **A misreading.** `Apple revenue since 2025 year over year` reads `2025` as a count of quarters instead of the year a `since` window starts (noted in ticket 05's work). With any change word after it (`year over year`, `quarter over quarter`, `as growth`), `since 2025` is still the window since 2025 began.
- **The rule.** A change asked over a `since` window (`How much did Intel's revenue change since 2023?`, `What caused Apple's revenue to fall since 2023?`'s window, `Apple revenue growth since 2024`) is year over year over that window, as ticket 09 made every counted window: each filed quarter since the year began, with its year-over-year change. A change that names no base and no window still asks against what.

Change `test_what_a_change_is_measured_against`'s expectations for the since-window questions with the reading, and say so in the commit.

**Acceptance:** on the recorded runtime, `Apple revenue since 2025 year over year` shows the quarters since 2025 began, each with its year-over-year change; `How much did Intel's revenue change since 2023?` the same over its window; `How much did Intel's revenue change?` still asks; phrase-coverage cases for each. `uv run python -m pytest` passes; `uv run python scripts/compare_answers.py` names every conversation whose answer changes, and each change is intended.

**Blocked by:** None — can start immediately

**Status:** resolved

## Answer

Shipped 2026-10-07. A "since" window is a window: a change asked over it, in any wording, is year over year over every filed quarter since the year began; and "since 2025 year over year" reads 2025 as the year the window starts.

- **The misreading** is fixed in the window grammar (`asked_window` in `period_window.py`), which both planners pass through (ADR 0010, 0011). `SINCE_YEAR` moved there from `request_wording.py`, and a window match that overlaps a "since <year>" phrase is dropped, so `Apple revenue since 2025 year over year` (read as 2025 years, 8100 quarters capped at 40, before) and `... quarter over quarter` (2025 quarters) are the window since 2025 began. `since fiscal 2025 year over year` keeps its fiscal reading.
- **The rule** is in `_names_a_window` and the since branch of `bind_periods_from_message` in `request_wording.py`: a "since" window is a named window, so `How much did Intel's revenue change since 2023?`, `What caused Apple's revenue to fall since 2023?` and `Apple revenue growth since 2024` show every filed quarter since the year began, each with its year-over-year change from its own comparative (ADR 0009), with the "Since 2023" and "Year over year" chips. A sequential change over a since window keeps the quarters as listed, the oldest with no change, as `sequential instead` already did (ticket 05). With no window, `How much did Intel's revenue change?` still asks "Compared with what?". `year over year` after `Apple revenue since 2025` is the direct question's view, column for column.
- `test_what_a_change_is_measured_against`'s three since-window expectations changed from `None` to `"year_over_year"`, as the ticket asks, with `Apple revenue growth since 2024` added; two binder tests and a window-grammar test pin the readings; a recorded-runtime test pins both acceptance answers, the follow-up and the no-window clarification. Phrase coverage: five `SINCE_CHANGE_QUESTIONS` cases and `How much did Intel's revenue change?` in `NO_BASE_QUESTIONS`, none sent to the model.
- README's growth row, ADR 0010 and CONTEXT.md's Window entry say the rule.
- `compare_answers`: 4 of 274 conversations differ, all added for this ticket and all intended: `Apple revenue since 2025 year over year` and `Apple revenue since 2025 quarter over quarter` (2025 read as a count with the "at most 40" note and 9 quarters before; the 6 quarters since 2025 with their change now), `Apple revenue growth since 2024` (the growth default of 5 quarters before; the 9 recorded quarters since 2024 now, each with its change) and `How much did Intel's revenue change since 2023?` (9 quarters with no change column before; each with its year-over-year change now). `Apple revenue since 2025` then `year over year` was added and does not differ.
