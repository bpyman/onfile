# 11 — A ranking of a group the snapshot does not know is refused, whichever planner reads it

**What to build:** Decided in `rules-to-review.md` (held-out-5-findings 09). Ticket 09 made a planner's ranking with no group rank every company. The rules planner refuses `top 10 companies in AI` and `top 10 AI companies by revenue` as an unknown industry, and so sends them on in the live cascade; if the LLM planner then leaves the group out, the answer ranks every company. When a planner proposes a ranking with no group, read the question for a group the way the rules planner does (in the shared reading); if it names one the snapshot does not know, refuse it as an unknown group, as now. Only a question that names no group (`which companies are worth the most?`) ranks every company.

**Acceptance:** with a fake LLM planner proposing a ranking with no industry, `top 10 companies in AI` and `top 10 AI companies by revenue` are refused as an unknown industry; `which companies are worth the most?` still ranks every company. `uv run python -m pytest` passes; `uv run python scripts/compare_answers.py` names every conversation whose answer changes, and each change is intended.

**Blocked by:** None — can start immediately

**Status:** resolved

## Answer

Shipped 7 October 2026. `ranked_group` (rules_planner.py) reads the group a ranking's words
name exactly as the rules planner's own plan does (the same `_group_named`, now shared by
both), and `WHOLE_MARKET` when they name none. `request_from_proposal`
(graph/turn_graph.py) fills a rank or rank_and_lookup proposal with no industry from it, so
`top 10 companies in AI` and `top 10 AI companies by revenue` are refused as an unknown
industry (`ai`) with a fake LLM planner proposing a ranking with no group, as with the rules
planner; `which companies are worth the most?` still ranks every company. `_lifted_plan`'s
whole-market default stays for proposals typed without a message. Tests: three in
`tests/test_held_out_5_findings.py`, each run with both planners. compare_answers: 0 of 375
conversations differ (the recorded demo uses the rules planner, which already read the group);
the three questions are added.
