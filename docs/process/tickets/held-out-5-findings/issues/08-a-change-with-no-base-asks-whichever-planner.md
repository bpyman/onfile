# 08 — "Why did revenue drop?" asks against what, whichever planner reads it

**What to build:** Found by the fifth held-out set's run (7 October 2026; [findings](../../../../evaluation/held-out-5-findings.md)). Fixing it makes set 5 development data, as every set before it became after its run. On one run of three, the LLM planner read `Why did NVIDIA's revenue drop?` (`h5_cl_drop`) and `What caused Pfizer's earnings to fall?` (`h5_cl_fall`) as news, refused on the recorded runtime, instead of asking what to compare against (README, a change with no base). The rules planner and the cascade ask. Make the shared typing ask against what for a change-with-no-base question (`_asks_change_without_base` in `request_wording.py`) whatever intent the planner proposes, unless the question asks for news by name (`news`, `headlines`).

Cases: both above, with a fake LLM planner proposing `news_and_explain`.

**Acceptance:** `uv run python -m pytest` passes; `uv run python scripts/compare_answers.py` names every conversation whose answer changes, and each change is intended; the case named is read right by the planner(s) that failed it (rules planner and the shared code: on the recorded runtime; the LLM planner: with a fake LLM planner proposing what the run's observation shows, so no test calls OpenAI).

**Blocked by:** None — can start immediately

**Status:** resolved

## Answer

Shipped 7 October 2026. `asks_change_without_base` (request_wording.py) is true where
`comparison_asked` is "unclear" and the words do not name `news` or `headlines`. In
`request_from_proposal` (graph/turn_graph.py), any qualitative proposal (news, explanation,
exploratory research) for such a question is typed by `_figure_asked` as the figure it names:
a named company's lookup, which then asks year over year or sequential; with no company, the
lookup that asks which company, as the rules planner does. Tests: h5_cl_drop and h5_cl_fall
with a fake LLM planner proposing `news_and_explain`, three named-company changes and the
no-company one under both planners, and two news-by-name questions that stay news.
compare_answers: 0 of 366 conversations differ (the recorded demo uses the rules planner,
which already asked); two conversations added.
