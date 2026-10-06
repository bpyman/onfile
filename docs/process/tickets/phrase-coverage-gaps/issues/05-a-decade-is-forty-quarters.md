# 05 — A decade is 40 quarters

**What to build:** `Apple revenue over the past decade` shows the latest quarter. A decade is ten years, 40 quarters, the most a window takes; read "decade" in the window grammar as it reads "years".

Found by phrase coverage ([report](../../../../evaluation/phrase-coverage.md), `src/financial_analyst_agent/phrase_coverage.py`), judged by the README's [How a question is read](../../../../../README.md#how-a-question-is-read). The fix belongs in the shared reading of words both planners pass through (ADR 0010, 0011), not in the rules planner alone.

**Acceptance:** the cases below are read right and taken off `KNOWN_GAPS`; `uv run python -m pytest tests/unit/test_phrase_coverage.py` passes; `uv run python scripts/compare_answers.py` names every conversation whose answer changes, and each change is intended.

**Blocked by:** None — can start immediately

**Status:** resolved

## Answer

2026-10-06. "Apple revenue over the past decade" shows the latest 40 quarters. The phrase-coverage case is off `KNOWN_GAPS`.

- The window grammar (`period_window.py`), which both planners read through (ADR 0010, 0011), reads "decade" as a unit of 40 quarters, as it reads "years" as 4: "past two decades" asks for 80 and is capped at 40, and says so.
- A recency word before "decade" needs no count: "the past decade", "the last decade", "the previous decade" are one. "A decade ago" is not a window.
- README "How a question is read" names `the past decade` in the window row.

compare_answers: 0 of 244 conversations differ. No recorded conversation says "decade".
