# 02 — "Year on year" means year over year

**What to build:** "is unitedhealth's operating cash flow up year on year" answers the latest quarter with no year-over-year change. "Year on year" (and "y/y", "YoY" if not already read) should add the `year_over_year` operation as "year over year" does, in the shared wording both planners pass through.

Case: `h4_growth_unh_ocf_year_on_year`.

Found by the fourth held-out planner set ([findings](../../../../evaluation/held-out-4-findings.md)): every planner failed it the same way, so the defect is in the code all planners share after planning.

**Acceptance:** the case below answers as expected on the recorded runtime with the rules planner, a test pins it, and `uv run python scripts/compare_answers.py` names every conversation whose answer changes. Fixing it makes the fourth held-out set development data: say so in the case file's `about`, not by editing its labels.

**Blocked by:** None — can start immediately

**Status:** resolved

## Answer

"Year on year" was not in the year-over-year wording, so the question was read as a plain lookup. Now:

- `request_wording.py`: one `YEAR_OVER_YEAR` pattern covers "year over year", "year on year" (spaced or hyphened), "YoY" and "y/y". It is shared by the wording that asks for the change (`YOY`, `EXPLICIT_YOY`) and the wording that removes it ("remove year on year"). Both planners pass through this wording. `graph/clarify.py` also reads "y/y" as an answer to "Compared with what?"
- Each spelling now binds the same periods and operations as "year over year" (`tests/unit/test_planner_wording.py`).
- The case adds the `year_over_year` operation and passes on outcome, intent, tickers, metrics and operations. It does **not** pass on periods. The ticket asks for "year on year" to work as "year over year" does. "Year over year" with no window shows two years of quarters (8), but the label says the latest quarter. This is the same label-versus-design disagreement as `h4_growth_nvda_how_fast` (a growth question that names no period shows recent quarters by design). `held-out-4-findings.md` now says so. No label was changed. `tests/test_held_out_4_findings.py` checks that the case's plan matches the "year over year" phrasing's and that every field except periods passes.
- `uv run python scripts/compare_answers.py`: 0 of 244 conversations differ. No recorded conversation says "year on year" or "y/y".
- `planner-cases-held-out-4.json`'s `about` lists this case among those code was changed to pass.

If a yes/no question ("is X up year over year?") should show only the latest quarter, that is a new design decision for a person. It would apply to "year over year" as well.
