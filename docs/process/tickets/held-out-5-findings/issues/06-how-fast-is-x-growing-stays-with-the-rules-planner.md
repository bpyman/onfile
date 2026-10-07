# 06 — "How fast is Broadcom growing?" stays with the rules planner

**What to build:** Found by the fifth held-out set's run (7 October 2026; [findings](../../../../evaluation/held-out-5-findings.md)). Fixing it makes set 5 development data, as every set before it became after its run. `How fast is Broadcom growing?` (`h5_gr_fast_avgo`): the rules planner's reading is right (growth with no metric is revenue, README), but it proposes no metric, so the cascade sends the turn to the LLM planner, which refused it on some runs. As the overview was (probe review, 6 October), make the rules planner propose what the shared reading implies (revenue, for growth with no metric) so the cascade keeps its plan. The cascade's `unsure_reason` is unchanged.

Case: `h5_gr_fast_avgo` under the cascade with a fake LLM planner that refuses; phrase coverage's `SENT_TO_MODEL` no longer lists a growth question with no metric.

**Acceptance:** `uv run python -m pytest` passes; `uv run python scripts/compare_answers.py` names every conversation whose answer changes, and each change is intended; the case named is read right by the planner(s) that failed it (rules planner and the shared code: on the recorded runtime; the LLM planner: with a fake LLM planner proposing what the run's observation shows, so no test calls OpenAI).

**Blocked by:** None — can start immediately

**Status:** ready-for-agent
