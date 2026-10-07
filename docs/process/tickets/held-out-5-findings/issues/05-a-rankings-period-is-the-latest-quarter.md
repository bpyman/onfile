# 05 — A ranking asked over a window records the latest quarter it shows

**What to build:** Found by the fifth held-out set's run (7 October 2026; [findings](../../../../evaluation/held-out-5-findings.md)). Fixing it makes set 5 development data, as every set before it became after its run. `Over the past year, the top 3 drugmakers by gross margin` (`h5_rk_drugs_gm`), when ranked (the LLM planner and the cascade), shows each company's latest quarter with the README's note that a ranking does not show a window, but the analysis records the window asked for (4 quarters), so the evaluation, which reads the period from the analysis, scores the period wrong though the screen and the label agree. Record a ranking's period as the latest quarter it shows, keeping the window only to say so in the note. Check that nothing else reads a ranking's recorded window (chips, follow-ups such as `add Intel` after a ranking, which keeps the ranked companies' latest quarter).

Case: `h5_rk_drugs_gm`'s period, once ticket 04 lets the rules planner rank it.

**Acceptance:** `uv run python -m pytest` passes; `uv run python scripts/compare_answers.py` names every conversation whose answer changes, and each change is intended; the case named is read right by the planner(s) that failed it (rules planner and the shared code: on the recorded runtime; the LLM planner: with a fake LLM planner proposing what the run's observation shows, so no test calls OpenAI).

**Blocked by:** None — can start immediately

**Status:** ready-for-agent
