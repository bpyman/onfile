# 03 — "How much did revenue change?" asks against what

**What to build:** "How much did Intel's revenue change?" answers the latest revenue. A change that names no base asks what to compare against, as "why did revenue drop?" already does (README, ADR 0004's clarify path). Extend that guard to change words that name no base ("change", "move", "how much did … change"), and keep questions that name one ("year over year", "since last quarter") answering.

Case: `h4_clarify_intel_change_no_base`.

Found by the fourth held-out planner set ([findings](../../../../evaluation/held-out-4-findings.md)): every planner failed it the same way, so the defect is in the code all planners share after planning.

**Acceptance:** the case below answers as expected on the recorded runtime with the rules planner, a test pins it, and `uv run python scripts/compare_answers.py` names every conversation whose answer changes. Fixing it makes the fourth held-out set development data: say so in the case file's `about`, not by editing its labels.

**Blocked by:** None — can start immediately

**Status:** ready-for-agent
