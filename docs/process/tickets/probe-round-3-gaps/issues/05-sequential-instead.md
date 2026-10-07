# 05 — "Sequential instead" switches the change and keeps the quarters

**What to build:** Found reviewing probe round 3's doubts (7 October 2026): a question a doubt raised, asked on the recorded runtime, does not do what the README's "How a question is read" now says. The fix belongs in the shared reading of words both planners pass through (ADR 0010, 0011), except where the ticket says otherwise. `Apple revenue over the last 6 quarters` → `as growth` → `sequential instead` shows 5 quarters with year-over-year change: the switch is lost, and the window jumps from 6 to 5. The README's quarter-over-quarter row now says `sequential instead` (and `quarter over quarter instead`, `make it sequential`) after a year-over-year view switches the change to sequential and keeps the quarters on screen; `year over year instead` switches back the same way.

**Acceptance:** that conversation ends with 6 quarters and sequential changes, no year-over-year; the reverse switch keeps the quarters too; follow-up phrase-coverage cases for both. `uv run python -m pytest` passes; `uv run python scripts/compare_answers.py` names every conversation whose answer changes, and each change is intended.

**Blocked by:** None — can start immediately

**Status:** resolved

## Answer

Shipped 7 October 2026. `sequential instead`, `quarter over quarter instead` and `make it sequential` after a year-over-year view switch the change to the quarter before and keep the quarters on screen; `year over year instead` and `make it year over year` switch back the same way.

- The fix is in the shared reading of follow-up words both planners pass through (`_keep_window_for_change` in `request_wording.py`, ADR 0010, 0011), which until now kept the window only for a year-over-year follow-up. A sequential follow-up with no window of its own now reads the quarters on screen plus the one before the oldest, as the base read but not shown (`count = shown + 1`, `asked = shown`), and takes the `year_over_year` operation out. A named period on screen keeps its periods and reads each named quarter's base (`company_base_dates=()`); a "since" window, or one already read with its base, is left as it is.
- The ticket's conversation ends with 6 quarters, each with its change on the quarter before, and no "Year over year" chip or operation. The answer is the view `Apple revenue over the last 6 quarters quarter over quarter` gives when asked directly, column for column. That view shows a "YoY change" column beside "QoQ change" where the year-earlier quarter is on screen, as it did before this ticket; the acceptance's "no year-over-year" is read as the operation and chip, and the point is recorded in `docs/process/rules-to-review.md`.
- The reverse switch already kept the quarters (the spec keeps the base quarter read, and the merge leaves it out); it is now pinned by tests.
- `show that quarter over quarter` after four quarters used to widen the window to five shown; it now shows the four with the fifth read as the base, and the unit test's expectation was updated.
- Tests: three unit tests at the follow-up seam (`tests/unit/test_planner_wording.py`), two recorded-runtime tests comparing the switched view with the direct question's (`tests/test_recorded_regressions.py`), and six phrase-coverage cases under "Change switches" (`CHANGE_SWITCHES` in `phrase_coverage.py`), none sent to the model.
- `compare_answers`: the two switch conversations were added. The forward one differs from HEAD as intended (5 quarters with year-over-year change before; 6 quarters with sequential change now); the reverse one does not differ.
- ADR 0010's "Growth is year over year" paragraph names the switch. The README's quarter-over-quarter row already did.

