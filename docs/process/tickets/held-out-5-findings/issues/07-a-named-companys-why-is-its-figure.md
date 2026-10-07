# 07 — A question about a named company's figure is that figure, whichever planner reads it

**What to build:** Found by the fifth held-out set's run (7 October 2026; [findings](../../../../evaluation/held-out-5-findings.md)). Fixing it makes set 5 development data, as every set before it became after its run. The LLM planner reads `How does Apple's buyback affect its EPS?` (`h5_co_buyback`) and `Why is Goldman's revenue so volatile?` (`h5_co_volatile`) as general explanations, and the recorded runtime refuses them. The README says a named company's question is that company's figure (the general-question row: "With a company named, it is that company's figure"; the why row: the figures it names, with a note). The shared typing re-types an explanation as a lookup only when no company is named (brief-5-probe-gaps 09). Extend it: an `explain` proposal for a question that names a recorded company and a catalog metric is that company's lookup, with the why note where the question asks why. A question naming a company and no metric (`How might AI change Goldman Sachs's business?`) stays an explanation.

Cases: both above, with a fake LLM planner proposing `explain`.

**Acceptance:** `uv run python -m pytest` passes; `uv run python scripts/compare_answers.py` names every conversation whose answer changes, and each change is intended; the case named is read right by the planner(s) that failed it (rules planner and the shared code: on the recorded runtime; the LLM planner: with a fake LLM planner proposing what the run's observation shows, so no test calls OpenAI).

**Blocked by:** None — can start immediately

**Status:** ready-for-agent
