# 03 — "How much did revenue change?" asks against what

**What to build:** "How much did Intel's revenue change?" answers the latest revenue. A change that names no base asks what to compare against, as "why did revenue drop?" already does (README, ADR 0004's clarify path). Extend that guard to change words that name no base ("change", "move", "how much did … change"), and keep questions that name one ("year over year", "since last quarter") answering.

Case: `h4_clarify_intel_change_no_base`.

Found by the fourth held-out planner set ([findings](../../../../evaluation/held-out-4-findings.md)): every planner failed it the same way, so the defect is in the code all planners share after planning.

**Acceptance:** the case below answers as expected on the recorded runtime with the rules planner, a test pins it, and `uv run python scripts/compare_answers.py` names every conversation whose answer changes. Fixing it makes the fourth held-out set development data: say so in the case file's `about`, not by editing its labels.

**Blocked by:** None — can start immediately

**Status:** resolved

## Answer

"How much did Intel's revenue change?" now asks what to compare against (`ambiguous_comparison`), as "why did revenue drop?" and "how has revenue changed?" already did.

- A new `_CHANGE` wording in `request_wording.py` reads "how much did/has … change", "did … change" and "how did … move" as a change. `comparison_asked` returns "unclear" for it unless the wording names a base.
- Wording that names a base keeps answering. "Year over year" gives year over year. "Since last quarter" gives sequential. A span of quarters ("over the past 10 quarters", "since 2023", "over the last year", two named quarters) is measured from its own first quarter. That span rule keeps `h3_tmo_rev_past_ten` ("Over the past 10 quarters, how has Thermo Fisher's revenue moved?") answering as recorded.
- After the analyst replies, the question shows the same quarters "how has … changed?" does: 10 rows for Intel, either base. `bind_periods_from_message` treats the base-less change as a change. `YOY` itself is unchanged.
- Tests: the held-out case in `tests/test_held_out_4_findings.py`, the wording cases in `tests/unit/test_planner_wording.py`, and the ask-then-answer conversation in `tests/unit/test_conversation_edges.py`.
- `compare_answers`: 0 of 244 conversations differ. The case file's `about` lists this case among the fixed ones. No label changed.
