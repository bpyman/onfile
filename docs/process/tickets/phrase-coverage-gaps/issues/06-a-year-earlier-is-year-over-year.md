# 06 — "The same quarter last year" and "a year earlier" are year over year

**What to build:** `Apple revenue compared with the same quarter last year` shows four quarters with no change, and `Is Apple's revenue up from a year earlier?` shows the latest quarter. Both ask for the year-over-year change; read "the same quarter last year", "a year earlier", "a year ago" and "from last year" with the year-over-year words.

Found by phrase coverage ([report](../../../../evaluation/phrase-coverage.md), `src/financial_analyst_agent/phrase_coverage.py`), judged by the README's [How a question is read](../../../../../README.md#how-a-question-is-read). The fix belongs in the shared reading of words both planners pass through (ADR 0010, 0011), not in the rules planner alone.

**Acceptance:** the cases below are read right and taken off `KNOWN_GAPS`; `uv run python -m pytest tests/unit/test_phrase_coverage.py` passes; `uv run python scripts/compare_answers.py` names every conversation whose answer changes, and each change is intended.

**Blocked by:** None — can start immediately

**Status:** ready-for-agent
