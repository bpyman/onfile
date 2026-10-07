# 10 — A speculative question is an explanation, even about a named company's figure

**What to build:** Decided in `rules-to-review.md` (held-out-5-findings 07). Ticket 07 made a named company's question its figure whichever planner reads it, so `How might AI change Apple's revenue?` and `How could tariffs affect Nvidia's gross margin?` now show the latest quarter's figure, which answers neither. A speculative question (`how might`, `how could`, `how would`, `what if`, `what would happen if`) is an explanation, marked as the model's, even when it names a company and a catalog metric, as `How might AI change banking?` already is (README, a general question). `How does Apple's buyback affect its EPS?` (not speculative) stays Apple's figure.

Put the speculative wording in the shared reading (`asks_for_explanation`, or beside it) so the shared typing and the rules planner agree; say so in the README's Follow-ups, explanations and filing changes bullet.

**Acceptance:** both questions above are explanations on the recorded runtime and with a fake LLM planner proposing `lookup`; the buyback question is unchanged; phrase-coverage cases for each speculative wording. `uv run python -m pytest` passes; `uv run python scripts/compare_answers.py` names every conversation whose answer changes, and each change is intended.

**Blocked by:** None — can start immediately

**Status:** ready-for-agent
