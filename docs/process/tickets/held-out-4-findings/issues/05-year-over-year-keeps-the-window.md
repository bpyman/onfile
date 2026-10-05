# 05 — Showing year over year keeps the window

**What to build:** "amgen and gilead revenue, last 6 quarters" → "show that year over year" widens the window to 8 quarters, and "Thermo Fisher revenue last 4 quarters" → "Danaher too" → "as growth" widens it to 5. Adding the `year_over_year` operation should keep the window the analyst chose; the year-earlier quarters a change needs are read as comparatives (ADR 0009), not added as rows. Decide and record where the 8 and the 5 come from before changing them.

Cases: `h4_fu_amgn_gild_yoy`, `h4_fu_tmo_dhr_too_growth`.

Found by the fourth held-out planner set ([findings](../../../../evaluation/held-out-4-findings.md)): every planner failed it the same way, so the defect is in the code all planners share after planning.

**Acceptance:** the case below answers as expected on the recorded runtime with the rules planner, a test pins it, and `uv run python scripts/compare_answers.py` names every conversation whose answer changes. Fixing it makes the fourth held-out set development data: say so in the case file's `about`, not by editing its labels.

**Blocked by:** None — can start immediately

**Status:** ready-for-agent
