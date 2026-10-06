# 08 — A general question that names a metric is an explanation

**What to build:** `Explain how a share buyback affects EPS` asks which company was meant. It names no company and asks how something works, not for a figure: it is a general explanation (intent `explain`), as `How might AI change banking?` is (README, a general question with no company). A question that asks for a figure and names no company still asks which company (`What's the EPS?`). Tell them apart by the explanation wording (`explain how`, `how does ... affect`, `what is ... and why does it matter`), not by the absence of a company alone.

Add cases for both kinds.

Found by the set-5 brief's probe dry-run (6 October 2026, second round): a blind session labelled 30 throwaway probes from the draft brief and the README, and the app disagreed. Judged by the README's [How a question is read](../../../../../README.md#how-a-question-is-read). The fix belongs in the shared reading of words both planners pass through (ADR 0010, 0011), not in the rules planner alone, except where the ticket says the rules planner.

**Acceptance:** the cases below are read right; any phrase-coverage case named is taken off `KNOWN_GAPS`; `uv run python -m pytest` passes; `uv run python scripts/compare_answers.py` names every conversation whose answer changes, and each change is intended.

**Blocked by:** None — can start immediately

**Status:** resolved

## Answer

Shipped 2026-10-06.

`asks_for_explanation` in `request_wording.py` is the shared reading of explanation wording: `explain …` (also `can you explain`, `please explain`), `how does/do/would/could … affect/impact/influence/work/matter`, `how is/are … calculated/computed/measured/defined/derived/determined/recognized/accounted/reported`, `why does/is … matter/important` (so `what is free cash flow and why does it matter?`), and `what does … mean`. Both planners pass through it:

- The rules planner proposes `explain` (topic: the question) when the words ask for an explanation and the question names no company, before its follow-up and lookup rules. Its AI-disruption rule is unchanged. So `Explain how a share buyback affects EPS`, `How does a buyback affect EPS?`, `What is free cash flow and why does it matter?` and `How is EPS calculated?` are explanations, and the live cascade keeps the plan (no LLM call). Before, `What is free cash flow and why does it matter?` also read "free" as the company.
- `request_from_proposal` (`turn_graph.py`), which types either planner's proposal, turns a figures proposal that names no company (a lookup or comparison with no company, or a spec patch adding none) into an explain request when the words ask for an explanation. So an LLM proposal of `lookup eps_diluted` with no company for the same question still explains. A ranking, a filing change or a proposal naming a company is untouched.
- The LLM planner's prompt says explain is also for a general question about how a figure works that names no company.

A figure with no company still asks which company: `What's the EPS?`, `What is EPS?`, `What's the revenue?` and `What was the revenue last quarter?` are unchanged. With a company named (`How does Apple's buyback affect its EPS?`), the answer stays that company's figure, as the README's why-question row treats a why with a company.

Phrase coverage gains the group "General questions": `EXPLANATION_QUESTIONS` (8 cases, each expecting intent `explain`; on the recorded runtime the essay completer then refuses any question but its one recorded essay, so the intent is what is checked) and `NO_COMPANY_QUESTIONS` (4 cases, each expecting the which-company question). The no-company cases are listed in `SENT_TO_MODEL`: the rules planner is unsure of a lookup with no company, and the LLM planner, told to name companies as the user wrote them, has none to name. Nothing was on `KNOWN_GAPS` for this ticket; it stays empty. The README's general-question row names the wording and the contrast.

Checks: 2,032 tests pass; ruff and mypy pass; `compare_answers` reports `0 of 244 conversations differ from HEAD` (no recorded conversation asks a general question that names a metric).
