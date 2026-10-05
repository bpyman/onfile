# 04 — Removing a company keeps the metric and window

**What to build:** "JPMorgan net interest income for the last 4 quarters" → "and Wells Fargo" → "remove JPMorgan" shows Wells Fargo's overview: the metric and the window are lost. Removing a company should edit the analysis on screen and keep its metrics, window and operations, as removing one of two companies already does in the development cases. Find why this three-turn path resets it (the added company, the `net_interest_income` metric, or the window).

Case: `h4_fu_jpm_and_wfc_remove_jpm`.

Found by the fourth held-out planner set ([findings](../../../../evaluation/held-out-4-findings.md)): every planner failed it the same way, so the defect is in the code all planners share after planning.

**Acceptance:** the case below answers as expected on the recorded runtime with the rules planner, a test pins it, and `uv run python scripts/compare_answers.py` names every conversation whose answer changes. Fixing it makes the fourth held-out set development data: say so in the case file's `about`, not by editing its labels.

**Blocked by:** None — can start immediately

**Status:** resolved

## Answer

The cause was the metric, fixed by ticket 01. Before it, the first turn asked
which "interest" was meant. "and Wells Fargo" did not answer that question, so it
discarded the pending clarification and showed Wells Fargo's overview, and
"remove JPMorgan" had nothing to remove. At ac2b514 the case fails. Since 5433fab
it answers Wells Fargo net interest income for the last 4 quarters. The removal
itself was never wrong: the same three turns with revenue kept the metric and
window before the fix.

No code changed. `tests/test_held_out_4_findings.py` pins the case with the rules
planner on the recorded runtime. The case file's `about` lists it among the fixed
cases. `held-out-4-findings.md` records the cause. `compare_answers`: 0 of 244
conversations differ.

The spec keeps `across_companies` after removing down to one company. The
development case `ho_follow_drop_company` does the same, and no label checks
operations, so it was left alone.
