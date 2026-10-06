# 09 — A figure with no company is not an explanation, whichever planner reads it

**What to build:** Found live (6 October 2026), reviewing ticket 08. With the live cascade, `What's the EPS?` and `What's the revenue?` name no company, so the rules planner is unsure and the LLM planner plans them; it reads both as a general explanation, and the answer is an essay. They ask for a figure: the answer should ask which company, as the rules planner's plan does (README, a general question with no company: "A figure with no company still asks which company"). Phrase coverage cannot see this, since its stand-in for the LLM planner declines.

- In the shared typing of a turn (`turn_graph.py`, where ticket 08 applies `asks_for_explanation`), an `explain` proposal that names a catalog metric, names no company and has none of the explanation wording is a figures question with no company: it asks which company. An `explain` proposal with explanation wording, or naming no catalog metric (`How might AI change banking?`), stays an explanation.
- `What is EPS?` (a metric with no article or possessive, "what is X") asks what the measure is: read it as explanation wording too, and move its phrase-coverage case (`no_company:What is EPS?`) to the explanation cases. `What's the EPS?`, `What was the revenue last quarter?` still ask which company.
- Test the shared typing with a fake LLM planner that proposes `explain` for each of these, so the test needs no OpenAI call.

**Acceptance:** with a fake LLM planner proposing `explain`, `What's the EPS?` and `What's the revenue?` ask which company, `What is EPS?` and `Explain how a share buyback affects EPS` explain; `uv run python -m pytest` passes; `uv run python scripts/compare_answers.py` names every conversation whose answer changes, and each change is intended.

**Blocked by:** None — can start immediately

**Status:** ready-for-agent
