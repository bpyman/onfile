# 07 — A question about a named company's figure is that figure, whichever planner reads it

**What to build:** Found by the fifth held-out set's run (7 October 2026; [findings](../../../../evaluation/held-out-5-findings.md)). Fixing it makes set 5 development data, as every set before it became after its run. The LLM planner reads `How does Apple's buyback affect its EPS?` (`h5_co_buyback`) and `Why is Goldman's revenue so volatile?` (`h5_co_volatile`) as general explanations, and the recorded runtime refuses them. The README says a named company's question is that company's figure (the general-question row: "With a company named, it is that company's figure"; the why row: the figures it names, with a note). The shared typing re-types an explanation as a lookup only when no company is named (brief-5-probe-gaps 09). Extend it: an `explain` proposal for a question that names a recorded company and a catalog metric is that company's lookup, with the why note where the question asks why. A question naming a company and no metric (`How might AI change Goldman Sachs's business?`) stays an explanation.

Cases: both above, with a fake LLM planner proposing `explain`.

**Acceptance:** `uv run python -m pytest` passes; `uv run python scripts/compare_answers.py` names every conversation whose answer changes, and each change is intended; the case named is read right by the planner(s) that failed it (rules planner and the shared code: on the recorded runtime; the LLM planner: with a fake LLM planner proposing what the run's observation shows, so no test calls OpenAI).

**Blocked by:** None — can start immediately

**Status:** resolved

## Answer

Shipped 7 October 2026. The shared typing (`_figure_asked`, `graph/turn_graph.py`, replacing
`_figure_with_no_company`) re-types an `explain` proposal whose question names a catalog metric:
with one recorded company named (the turn's issuer index), as that company's lookup; with
several, their comparison; with none, as before, a lookup asking which company only where none
of the explanation wording is there. The why note comes from the words (`answer_notes`), so
"Why is Goldman's revenue so volatile?" has it whichever planner planned, and "How does Apple's
buyback affect its EPS?" does not. A question naming a company and no metric ("How might AI
change Goldman Sachs's business?") stays an explanation.

- Tests (`tests/test_held_out_5_findings.py`): `h5_co_buyback` and `h5_co_volatile` with a fake
  LLM planner proposing `explain`, on every field; three named-company questions with the rules
  planner and an `explain` proposal; the why note and its absence; two questions that stay
  explanations.
- compare_answers: `1 of 364 conversations differ` (+4 added). "How might AI change Apple's
  revenue?" was an explanation (refused on the recorded runtime, which replays one essay) and is now
  Apple's revenue, as the rule asks; recorded
  in `docs/process/rules-to-review.md`. "Why is Goldman's revenue so volatile?", "How does
  Apple's buyback affect its EPS?" and "How might AI change Goldman Sachs's business?" do not
  differ: the rules planner already answered the first two as figures.
