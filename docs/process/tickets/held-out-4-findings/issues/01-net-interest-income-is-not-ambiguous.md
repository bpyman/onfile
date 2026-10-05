# 01 — "Net interest income" names one metric

**What to build:** "Give me Bank of America's net interest income for the last couple of quarters" asks which metric was meant, as if "interest" were ambiguous. "Net interest income" is the catalog's `net_interest_income`; the whole phrase should resolve before its words are read as ambiguous (ADR 0004). Check "a couple of quarters" reads as 2 once the metric resolves.

Case: `h4_bac_nii_couple_quarters`.

Found by the fourth held-out planner set ([findings](../../../../evaluation/held-out-4-findings.md)): every planner failed it the same way, so the defect is in the code all planners share after planning.

**Acceptance:** the case below answers as expected on the recorded runtime with the rules planner, a test pins it, and `uv run python scripts/compare_answers.py` names every conversation whose answer changes. Fixing it makes the fourth held-out set development data: say so in the case file's `about`, not by editing its labels.

**Blocked by:** None — can start immediately

**Status:** ready-for-agent
