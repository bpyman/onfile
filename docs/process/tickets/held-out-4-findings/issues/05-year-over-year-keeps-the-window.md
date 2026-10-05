# 05 — Showing year over year keeps the window

**What to build:** "amgen and gilead revenue, last 6 quarters" → "show that year over year" widens the window to 8 quarters, and "Thermo Fisher revenue last 4 quarters" → "Danaher too" → "as growth" widens it to 5. Adding the `year_over_year` operation should keep the window the analyst chose; the year-earlier quarters a change needs are read as comparatives (ADR 0009), not added as rows. Decide and record where the 8 and the 5 come from before changing them.

Cases: `h4_fu_amgn_gild_yoy`, `h4_fu_tmo_dhr_too_growth`.

Found by the fourth held-out planner set ([findings](../../../../evaluation/held-out-4-findings.md)): every planner failed it the same way, so the defect is in the code all planners share after planning.

**Acceptance:** the case below answers as expected on the recorded runtime with the rules planner, a test pins it, and `uv run python scripts/compare_answers.py` names every conversation whose answer changes. Fixing it makes the fourth held-out set development data: say so in the case file's `about`, not by editing its labels.

**Blocked by:** None — can start immediately

**Status:** resolved

## Answer

A year-over-year follow-up keeps the window on screen. "amgen and gilead revenue,
last 6 quarters" → "show that year over year" shows 6 quarters, and "Thermo Fisher
revenue last 4 quarters" → "Danaher too" → "as growth" shows 4. Each quarter has its
change, read from the comparative its own filing reports (ADR 0009).

Where the numbers came from: 8 is the default for "year over year" with no window
(c6c964a: four quarters and the year before each). 5 is the default for growth with
no window, and the floor for a change (e5bc932: four quarters and the newest one's
year-earlier base). Both date from before ADR 0009, when the year-earlier quarters
had to be rows. Both were applied to a follow-up even when a window was already on
screen.

- `refine_patch_from_message` keeps the current window when a follow-up asks for
  year over year or growth, names no window or period, and the analysis on screen
  already shows more than one quarter. A question that names no window still gets
  8 or 5. A follow-up after the latest quarter still gets 8. A sequential change
  can still widen to 5, because it needs the quarter before the oldest one shown.
- ADR 0009 records the decision.
- `compare_answers`: 1 of 244 conversations differs. `ho_follow_yoy` ("Tesla revenue
  over the last four quarters" → "show that year over year") now shows the 4
  quarters asked for, not 8. `test_year_over_year_shows_a_yoy_change_for_each_quarter`
  pinned the 8 and now checks 4, each with a change.
- Both cases are pinned in `tests/test_held_out_4_findings.py`. The case file's
  `about` lists them as fixed. No label changed.

