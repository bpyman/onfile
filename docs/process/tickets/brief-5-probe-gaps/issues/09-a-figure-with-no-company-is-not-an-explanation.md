# 09 — A figure with no company is not an explanation, whichever planner reads it

**What to build:** Found live (6 October 2026), reviewing ticket 08. With the live cascade, `What's the EPS?` and `What's the revenue?` name no company, so the rules planner is unsure and the LLM planner plans them; it reads both as a general explanation, and the answer is an essay. They ask for a figure: the answer should ask which company, as the rules planner's plan does (README, a general question with no company: "A figure with no company still asks which company"). Phrase coverage cannot see this, since its stand-in for the LLM planner declines.

- In the shared typing of a turn (`turn_graph.py`, where ticket 08 applies `asks_for_explanation`), an `explain` proposal that names a catalog metric, names no company and has none of the explanation wording is a figures question with no company: it asks which company. An `explain` proposal with explanation wording, or naming no catalog metric (`How might AI change banking?`), stays an explanation.
- `What is EPS?` (a metric with no article or possessive, "what is X") asks what the measure is: read it as explanation wording too, and move its phrase-coverage case (`no_company:What is EPS?`) to the explanation cases. `What's the EPS?`, `What was the revenue last quarter?` still ask which company.
- Test the shared typing with a fake LLM planner that proposes `explain` for each of these, so the test needs no OpenAI call.

**Acceptance:** with a fake LLM planner proposing `explain`, `What's the EPS?` and `What's the revenue?` ask which company, `What is EPS?` and `Explain how a share buyback affects EPS` explain; `uv run python -m pytest` passes; `uv run python scripts/compare_answers.py` names every conversation whose answer changes, and each change is intended.

**Blocked by:** None — can start immediately

**Status:** resolved

## Answer

Shipped 6 October 2026.

- `request_from_proposal` (`turn_graph.py`), the shared typing of either planner's proposal, re-types an `explain` proposal as the lookup it is when the question names a catalog metric (unique or ambiguous), names no company the issuer index knows, and has none of the explanation wording (`_figure_with_no_company`). `What's the EPS?` and `What's the revenue?` then ask which company through the usual resolution; `What's the margin?` asks which margin. An `explain` proposal with explanation wording, or naming no catalog metric (`How might AI change banking?`), stays an explanation. A question that names a company keeps the planner's reading.
- `asks_for_explanation` (`request_wording.py`) gains "what is X": `what is`/`what are`/`what's` followed by a catalog phrase alone (no article or possessive), to the end of the question. `What is EPS?`, `What are earnings per share?`, `What is EBITDA?`, `What is margin?` explain; `What is the EPS?`, `What is Apple's EPS?`, `What is Apple EPS?` do not. The rules planner's explain rule picks this up unchanged, so `What is EPS?` leaves the LLM planner live.
- Phrase coverage: `What is EPS?` moved from `NO_COMPANY_QUESTIONS` to `EXPLANATION_QUESTIONS`; `What is the EPS?` takes its place in the no-company cases. `KNOWN_GAPS` stays empty.
- The LLM planner's prompt names both cases. README's general-question row names `What is EPS?` and the "whichever planner" rule.
- Two older tests expected `What is EBITDA?` and `What is P/E?` to ask which company (`test_planner_conversations.py`, `test_planner_understanding.py`); they conflicted with this ticket's "what is X" rule and now ask with the article (`What is the EBITDA?`, `What's the P/E?`), which keeps what they check (no junk company from a determiner).
- Verified with a fake LLM planner that proposes `explain` for every question (`tests/test_run_turn_explain.py`): `What's the EPS?` and `What's the revenue?` ask which company; `What is EPS?`, the buyback question and the AI question explain. 2,048 tests pass; ruff and mypy pass; `compare_answers` reports 0 of 244 conversations differ.
