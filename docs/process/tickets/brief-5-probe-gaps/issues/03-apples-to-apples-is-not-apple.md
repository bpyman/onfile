# 03 — "Apples to apples" does not name Apple

**What to build:** `Apples to apples: Merck vs Pfizer net margin` compares Apple, Merck and Pfizer. The rules planner reads "apples" as Apple; it notes the correction, so the live cascade sends the turn to the LLM planner, which plans it right (held-out-4 findings: `h4_ow_apples_word_mrk_pfe`), but the rules planner alone does not. An idiom that contains a company's ordinary-word name names no company: `apples to apples`, `apples-to-apples`, `apples and oranges`, `apples with apples`. This one is the rules planner's company reading (`issuer_index`, the common-words list).

Add a phrase-coverage group or cases for ordinary-word idioms beside a real company (these, and one each for another ordinary-word company where an idiom is common, if any), each expecting only the real companies.

Found by the set-5 brief's probe dry-run (6 October 2026): a blind session labelled 30 throwaway probes from the draft brief and the README, and the app disagreed. Judged by the README's [How a question is read](../../../../../README.md#how-a-question-is-read). The fix belongs in the shared reading of words both planners pass through (ADR 0010, 0011), not in the rules planner alone, except where the ticket says the rules planner.

**Acceptance:** the cases below are read right; any phrase-coverage case named is taken off `KNOWN_GAPS`; `uv run python -m pytest` passes; `uv run python scripts/compare_answers.py` names every conversation whose answer changes, and each change is intended.

**Blocked by:** None — can start immediately

**Status:** ready-for-agent
