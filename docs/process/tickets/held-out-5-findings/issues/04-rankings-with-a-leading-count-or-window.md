# 04 — "5 banks by net income" and "Over the past year, the top 3 drugmakers by …" are rankings

**What to build:** Found by the fifth held-out set's run (7 October 2026; [findings](../../../../evaluation/held-out-5-findings.md)). Fixing it makes set 5 development data, as every set before it became after its run. The rules planner refuses two rankings (the cascade sends both on, and the LLM planner ranks):

- `5 banks by net income` (`h5_rk_banks_ni`): a count before a group `by` a metric, with no `top`;
- `Over the past year, the top 3 drugmakers by gross margin` (`h5_rk_drugs_gm`): a window leading the ranking.

Read a ranking whatever comes first: a leading count (`5 banks`, `the 3 biggest banks`), a leading window or other preamble (`Over the past year,`, `This quarter,`). A ranking with a window still shows each company's latest quarter, with its note (ticket 05 records it).

Cases: both above; phrase-coverage ranking cases with a leading count and a leading window.

**Acceptance:** `uv run python -m pytest` passes; `uv run python scripts/compare_answers.py` names every conversation whose answer changes, and each change is intended; the case named is read right by the planner(s) that failed it (rules planner and the shared code: on the recorded runtime; the LLM planner: with a fake LLM planner proposing what the run's observation shows, so no test calls OpenAI).

**Blocked by:** None — can start immediately

**Status:** ready-for-agent
