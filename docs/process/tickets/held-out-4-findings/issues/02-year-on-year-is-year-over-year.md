# 02 — "Year on year" means year over year

**What to build:** "is unitedhealth's operating cash flow up year on year" answers the latest quarter with no year-over-year change. "Year on year" (and "y/y", "YoY" if not already read) should add the `year_over_year` operation as "year over year" does, in the shared wording both planners pass through.

Case: `h4_growth_unh_ocf_year_on_year`.

Found by the fourth held-out planner set ([findings](../../../../evaluation/held-out-4-findings.md)): every planner failed it the same way, so the defect is in the code all planners share after planning.

**Acceptance:** the case below answers as expected on the recorded runtime with the rules planner, a test pins it, and `uv run python scripts/compare_answers.py` names every conversation whose answer changes. Fixing it makes the fourth held-out set development data: say so in the case file's `about`, not by editing its labels.

**Blocked by:** None — can start immediately

**Status:** ready-for-agent
