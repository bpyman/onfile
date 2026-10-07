# 04 — "5 banks by net income" and "Over the past year, the top 3 drugmakers by …" are rankings

**What to build:** Found by the fifth held-out set's run (7 October 2026; [findings](../../../../evaluation/held-out-5-findings.md)). Fixing it makes set 5 development data, as every set before it became after its run. The rules planner refuses two rankings (the cascade sends both on, and the LLM planner ranks):

- `5 banks by net income` (`h5_rk_banks_ni`): a count before a group `by` a metric, with no `top`;
- `Over the past year, the top 3 drugmakers by gross margin` (`h5_rk_drugs_gm`): a window leading the ranking.

Read a ranking whatever comes first: a leading count (`5 banks`, `the 3 biggest banks`), a leading window or other preamble (`Over the past year,`, `This quarter,`). A ranking with a window still shows each company's latest quarter, with its note (ticket 05 records it).

Cases: both above; phrase-coverage ranking cases with a leading count and a leading window.

**Acceptance:** `uv run python -m pytest` passes; `uv run python scripts/compare_answers.py` names every conversation whose answer changes, and each change is intended; the case named is read right by the planner(s) that failed it (rules planner and the shared code: on the recorded runtime; the LLM planner: with a fake LLM planner proposing what the run's observation shows, so no test calls OpenAI).

**Blocked by:** None — can start immediately

**Status:** resolved

## Answer

Shipped 7 October 2026. The rules planner reads a ranking whatever comes first. A count leading a group `by` a metric is the ranking's length (`5 banks by net income` ranks five banks; `the 5 quarters by revenue` stays no ranking). A clause before the first comma that names no measure and ranks nothing (`Over the past year,`, `This quarter,`, `Last quarter,`) is set aside when what follows is a ranking, so the group is `drugmakers`, not `drugmakers by gross margin`; the window is still read from the whole question, and the ranking shows each company's latest quarter with the README's note. Both held-out cases are now planned by the rules planner, so the cascade keeps its plan; the LLM planner already ranked both.

Tests: `h5_rk_banks_ni` with the rules planner; `h5_rk_drugs_gm` with the rules planner on every field but the recorded period (ticket 05); four leading-count and leading-window wordings ranked on the recorded runtime; the cascade keeping three rules rankings; 7 phrase-coverage ranking cases.

compare_answers: 3 of 356 conversations differ, all added here: "5 banks by net income", "Over the past year, the top 3 drugmakers by gross margin" and "This quarter, top 5 banks by net income" were refused and now rank. "top 3 drugmakers by gross margin" does not differ. The windowed ranking also shows the window's banner ("these are the four latest quarters, shown one by one") beside the ranking note; it comes from the recorded window, which ticket 05 replaces with the latest quarter.
