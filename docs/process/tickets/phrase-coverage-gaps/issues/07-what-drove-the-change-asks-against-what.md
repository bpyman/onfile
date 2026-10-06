# 07 — "What drove the change" asks against what

**What to build:** `What drove the change in Apple's revenue?` answers the latest revenue. Like "why did revenue drop?" and "how much did revenue change?", it names a change with no base, so it asks what to compare against.

Found by phrase coverage ([report](../../../../evaluation/phrase-coverage.md), `src/financial_analyst_agent/phrase_coverage.py`), judged by the README's [How a question is read](../../../../../README.md#how-a-question-is-read). The fix belongs in the shared reading of words both planners pass through (ADR 0010, 0011), not in the rules planner alone.

**Acceptance:** the cases below are read right and taken off `KNOWN_GAPS`; `uv run python -m pytest tests/unit/test_phrase_coverage.py` passes; `uv run python scripts/compare_answers.py` names every conversation whose answer changes, and each change is intended.

**Blocked by:** None — can start immediately

**Status:** resolved

## Answer

`What drove the change in Apple's revenue?` now asks what to compare against, as "why did revenue drop?" does. `_CHANGE` in `request_wording.py`, which both planners read through (ADR 0010, 0011), also reads "what drove / caused / explains / is behind the change (move, shift, increase, decrease, rise, fall, drop, decline, jump) in …" as a change with no base. A base or span named with it still wins: "… year over year" is year over year, "… since 2023" is the span. The case is off `KNOWN_GAPS`; README "How a question is read" names the wording in the no-base row. compare_answers: 0 of 244 conversations differ.
