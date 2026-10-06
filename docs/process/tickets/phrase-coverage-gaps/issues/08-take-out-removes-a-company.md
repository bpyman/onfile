# 08 — "Take out" removes a company

**What to build:** After a comparison of Apple and Microsoft, `take out Microsoft` is refused as an unknown metric ("take out"). Read it as `remove`, with "drop", "remove" and "without".

Found by phrase coverage ([report](../../../../evaluation/phrase-coverage.md), `src/financial_analyst_agent/phrase_coverage.py`), judged by the README's [How a question is read](../../../../../README.md#how-a-question-is-read). The fix belongs in the shared reading of words both planners pass through (ADR 0010, 0011), not in the rules planner alone.

**Acceptance:** the cases below are read right and taken off `KNOWN_GAPS`; `uv run python -m pytest tests/unit/test_phrase_coverage.py` passes; `uv run python scripts/compare_answers.py` names every conversation whose answer changes, and each change is intended.

**Blocked by:** None — can start immediately

**Status:** resolved

## Answer

"take out Microsoft" after Apple and Microsoft now leaves Apple alone. The words
that take something off the screen are one list in `request_wording.py`, which both
planners read through (ADR 0010, 0011): "drop", "remove" and "take out", with
"without" for a removal. The same list serves "take out the year-over-year column"
and "take out revenue and add net income". The case is off `KNOWN_GAPS`;
compare_answers reports 0 of 244 conversations differ. README "How a question is
read" names the wording in the follow-up row.
