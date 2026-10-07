# 12 — A planner's invented group for "which companies are worth the most?" ranks every company

**What to build:** Found re-checking set 5's failures with the real LLM planner (7 October 2026, $0.16). Ticket 09 made a planner's ranking with *no* group rank every company, but for `which companies are worth the most?` (`h5_rk_worth`) the LLM planner (`gpt-5.6-terra`) proposes a group: `intent=rank, industry='all US public companies'`, refused as an unknown industry. The rules planner and the cascade rank every company.

The group comes from the question's words (ADR 0010: one reading), so combine tickets 09 and 11 in the shared resolution of a planner's ranking:

- a group the snapshot knows is used, as now;
- a group it does not know, when the question's own words name no group (read as ticket 11 reads them), ranks every company: the planner's group is its paraphrase of "all companies", not the analyst's;
- a group it does not know that the question's words do name (`top 10 companies in AI`) is refused, as ticket 11 made it.

**Acceptance:** with a fake LLM planner proposing `industry='all US public companies'` (and, separately, `'companies'`), `which companies are worth the most?` ranks every company by market value; with a fake planner proposing `industry='AI'`, `top 10 companies in AI` is still refused; `top 5 banks by revenue` with a planner proposing `industry='Banks - Diversified'` is unchanged. `uv run python -m pytest` passes; `uv run python scripts/compare_answers.py` names every conversation whose answer changes, and each change is intended.

**Blocked by:** None — can start immediately

**Status:** resolved

## Answer

Shipped 7 October 2026. `request_from_proposal` (graph/turn_graph.py): a rank or
rank_and_lookup proposal whose group the snapshot does not know (the ranking's
`knows_industry`), for words that name no group (`ranked_group(message)` is
`WHOLE_MARKET`), ranks every company. `which companies are worth the most?` with a fake
planner proposing `industry='all US public companies'` or `'companies'` ranks every company
by market value (`'companies'` already did); `top 10 companies in AI` with a planner
proposing `industry='AI'` is still refused; `top 5 banks by revenue` with `'Banks -
Diversified'` is unchanged. Tests: four in `tests/test_held_out_5_findings.py`.
compare_answers: 0 of 375 conversations differ (the recorded demo uses the rules planner,
which names no invented group; the three questions are already compared).
