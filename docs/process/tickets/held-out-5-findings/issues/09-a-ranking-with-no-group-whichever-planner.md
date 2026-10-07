# 09 — "Which companies are worth the most?" ranks every company, whichever planner reads it

**What to build:** Found by the fifth held-out set's run (7 October 2026; [findings](../../../../evaluation/held-out-5-findings.md)). Fixing it makes set 5 development data, as every set before it became after its run. The LLM planner refused `which companies are worth the most?` (`h5_rk_worth`); the rules planner and the cascade rank every company in the snapshot by market value (README, a ranking with no group). Find what the LLM planner proposed (a ranking with no industry, refused as an unknown industry, is the likely shape) and make the shared resolution of a ranking with no group rank every company, whichever planner proposed it.

Case: `h5_rk_worth`, with a fake LLM planner proposing a ranking with no industry.

**Acceptance:** `uv run python -m pytest` passes; `uv run python scripts/compare_answers.py` names every conversation whose answer changes, and each change is intended; the case named is read right by the planner(s) that failed it (rules planner and the shared code: on the recorded runtime; the LLM planner: with a fake LLM planner proposing what the run's observation shows, so no test calls OpenAI).

**Blocked by:** None — can start immediately

**Status:** resolved

## Answer

Shipped 7 October 2026. The run's observation shows the LLM planner proposed a ranking
(`rank`) with no industry and no metric, refused as an unknown industry. `_lifted_plan`
(graph/spec_turn.py) now gives a ranking plan with no industry the whole market
(`WHOLE_MARKET`, moved from rules_planner.py to universe.py), the group the rules planner
already uses when the words name none, so every company in the snapshot is ranked by
market value, whichever planner proposed it. Tests: h5_rk_worth with a fake LLM planner
proposing `WorkflowPlan(intent=Intent.RANK)`; `test_run_turn_rank.py`'s test that refused
a ranking with no industry now expects every company (recorded in rules-to-review).
compare_answers: 0 of 368 conversations differ (the recorded demo uses the rules planner,
which names the group); two conversations added.
