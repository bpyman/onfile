# 10 — A speculative question is an explanation, even about a named company's figure

**What to build:** Decided in `rules-to-review.md` (held-out-5-findings 07). Ticket 07 made a named company's question its figure whichever planner reads it, so `How might AI change Apple's revenue?` and `How could tariffs affect Nvidia's gross margin?` now show the latest quarter's figure, which answers neither. A speculative question (`how might`, `how could`, `how would`, `what if`, `what would happen if`) is an explanation, marked as the model's, even when it names a company and a catalog metric, as `How might AI change banking?` already is (README, a general question). `How does Apple's buyback affect its EPS?` (not speculative) stays Apple's figure.

Put the speculative wording in the shared reading (`asks_for_explanation`, or beside it) so the shared typing and the rules planner agree; say so in the README's Follow-ups, explanations and filing changes bullet.

**Acceptance:** both questions above are explanations on the recorded runtime and with a fake LLM planner proposing `lookup`; the buyback question is unchanged; phrase-coverage cases for each speculative wording. `uv run python -m pytest` passes; `uv run python scripts/compare_answers.py` names every conversation whose answer changes, and each change is intended.

**Blocked by:** None — can start immediately

**Status:** resolved

## Answer

Shipped 2026-10-07.

- `asks_speculatively` (request_wording.py) reads `how might`, `how could`, `how would`, `what if` and `what would happen`; `asks_for_explanation` includes it. Not speculation: a request to the analyst or a follow-up (`How would you rank banks by revenue?`, `How would that look sequentially?`, `What if we look at Microsoft?`: the subject is a pronoun) and a comparison (`How would Apple's revenue compare with Microsoft's?`).
- The shared typing (`request_from_proposal`, graph/turn_graph.py) types any structured proposal for a speculative question as an explanation, company named or not, and does not re-type a speculative explanation as the company's figure (`_figure_asked`). A news or exploratory proposal is left as proposed.
- The rules planner proposes an explanation for a speculative question before reading companies into a figure.
- `How does Apple's buyback affect its EPS?` is unchanged: Apple's diluted EPS, whichever planner.
- Tests: `test_speculative_wording_is_read_once` (unit), `test_a_speculative_question_is_an_explanation_whichever_planner` (recorded runtime; the rules planner, a fake LLM planner proposing `lookup`, and one proposing `explain`). Phrase coverage: five cases under General questions, one per wording; all pass (`docs/evaluation/phrase-coverage.md` and the README's count are not regenerated here).
- compare_answers: 4 of 372 conversations differ, each intended: `How might AI change Apple's revenue?`, `How could tariffs affect Nvidia's gross margin?` and `What if Apple's revenue fell 10%?` were the latest quarter's figure and are now explanations (on the recorded runtime, which replays one essay, the not-answered message); held-out-4's `h4_other_explain_ai_drug_discovery` (`How might generative AI change drug discovery?`) was a lookup refused for no metric and is now the explanation its case expects. The added `How would you rank banks by revenue?` and `How would Apple's revenue compare with Microsoft's?` do not differ.
