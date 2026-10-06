# 03 — "Apples to apples" does not name Apple

**What to build:** `Apples to apples: Merck vs Pfizer net margin` compares Apple, Merck and Pfizer. The rules planner reads "apples" as Apple; it notes the correction, so the live cascade sends the turn to the LLM planner, which plans it right (held-out-4 findings: `h4_ow_apples_word_mrk_pfe`), but the rules planner alone does not. An idiom that contains a company's ordinary-word name names no company: `apples to apples`, `apples-to-apples`, `apples and oranges`, `apples with apples`. This one is the rules planner's company reading (`issuer_index`, the common-words list).

Add a phrase-coverage group or cases for ordinary-word idioms beside a real company (these, and one each for another ordinary-word company where an idiom is common, if any), each expecting only the real companies.

Found by the set-5 brief's probe dry-run (6 October 2026): a blind session labelled 30 throwaway probes from the draft brief and the README, and the app disagreed. Judged by the README's [How a question is read](../../../../../README.md#how-a-question-is-read). The fix belongs in the shared reading of words both planners pass through (ADR 0010, 0011), not in the rules planner alone, except where the ticket says the rules planner.

**Acceptance:** the cases below are read right; any phrase-coverage case named is taken off `KNOWN_GAPS`; `uv run python -m pytest` passes; `uv run python scripts/compare_answers.py` names every conversation whose answer changes, and each change is intended.

**Blocked by:** None — can start immediately

**Status:** resolved

## Answer

Resolved 6 October 2026.

`Apples to apples: Merck vs Pfizer net margin` compares Merck and Pfizer only, with no correction note, so the live cascade keeps the rules planner's plan instead of sending the turn to the LLM planner.

The misreading was in the index's typo corrector (`IssuerIndex.correct`), not in `find`: "apple" is a common word, but its plural "apples" is not on the list, and it is one letter away from Apple, so it was corrected to Apple wherever the question had no company at all or listed companies ("Merck vs Pfizer"). The hyphened form was already read right because a word inside a hyphened phrase is that phrase's.

- `_IDIOMS` in `issuer_index.py` lists idioms whose words are the idiom's, not a misspelt name: `apples to/with/for/and apples|oranges`, the same with `oranges` first, and `building|stumbling|road blocks` (the live snapshot's Block, whose plural slipped past the corrector the same way). `correct` adds the words of any idiom in the normalized question to the words it ignores, beside the hyphened-phrase parts. `find` is unchanged: "apple to apple" still names Apple, since the singular is the company's own name.
- Phrase coverage gains the group "Idioms beside a company" (`IDIOM_QUESTIONS`): the four apple idioms beside Merck and Pfizer, the hyphened form, and "the building blocks of Microsoft and Oracle revenue", each expecting only the real companies for the latest quarter. No case was on `KNOWN_GAPS` for this ticket.
- `tests/unit/test_planner_wording.py`: the hyphened-phrase test becomes a parametrized idiom test on the live index's `correct`, and a planner test shows the compare plan names `MRK, PFE` with no notes.

`compare_answers` reports 1 of 244 conversations differ: `case:h3_apples_to_apples` ("Compare Nvidia and AMD revenue apples to apples over the last four quarters") now shows Nvidia and AMD only, as its label expects; before, it added Apple with a "Showing Apple for apples" note. 1,957 tests pass; ruff and mypy pass.
