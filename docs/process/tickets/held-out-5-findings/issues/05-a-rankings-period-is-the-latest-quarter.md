# 05 — A ranking asked over a window records the latest quarter it shows

**What to build:** Found by the fifth held-out set's run (7 October 2026; [findings](../../../../evaluation/held-out-5-findings.md)). Fixing it makes set 5 development data, as every set before it became after its run. `Over the past year, the top 3 drugmakers by gross margin` (`h5_rk_drugs_gm`), when ranked (the LLM planner and the cascade), shows each company's latest quarter with the README's note that a ranking does not show a window, but the analysis records the window asked for (4 quarters), so the evaluation, which reads the period from the analysis, scores the period wrong though the screen and the label agree. Record a ranking's period as the latest quarter it shows, keeping the window only to say so in the note. Check that nothing else reads a ranking's recorded window (chips, follow-ups such as `add Intel` after a ranking, which keeps the ranked companies' latest quarter).

Case: `h5_rk_drugs_gm`'s period, once ticket 04 lets the rules planner rank it.

**Acceptance:** `uv run python -m pytest` passes; `uv run python scripts/compare_answers.py` names every conversation whose answer changes, and each change is intended; the case named is read right by the planner(s) that failed it (rules planner and the shared code: on the recorded runtime; the LLM planner: with a fake LLM planner proposing what the run's observation shows, so no test calls OpenAI).

**Blocked by:** None — can start immediately

**Status:** resolved

## Answer

Shipped 7 October 2026. `resolve_spec` records a ranking's period as the latest quarter it shows, whichever planner planned it; `ranked_window_asked` (from the draft) carries the asked window or named period to `period_notes`, which says so in the ranking's note and nothing else. The "four latest quarters" banner no longer sits beside a ranking that shows one, and no report dates are listed for it.

What read the recorded window: the period chip already said "Latest quarter"; `add Intel` after a ranking took the ranking's window and now keeps the latest quarter. A growth ranking (`top 5 banks by revenue growth`) needed a window only to pass validation: its change is each company's latest quarter against its filing's comparative, so `validate_spec` no longer asks a ranking for a window, and the rows are as before. Adding a company to a growth ranking shows growth over growth's own five quarters, as it did.

Tests: `h5_rk_drugs_gm` on every field with the rules planner and with the LLM planner's proposal (4 recent quarters); windowed, counted and named-period rankings record the latest quarter with the note; a ranking with no window has none; `add Pfizer` after a windowed ranking keeps the latest quarter; a growth ranking and `add Apple` after it.

compare_answers: 3 of 358 conversations differ, all intended: `h3_chips_window` records the latest quarter (its answer is unchanged); "Over the past year, the top 3 drugmakers by gross margin" loses the four-quarters banner; and "add Pfizer" after it compares the latest quarter, not four. "top 5 banks by revenue growth" then "add Apple" does not differ.
