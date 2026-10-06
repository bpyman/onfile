# 06 — "The same quarter last year" and "a year earlier" are year over year

**What to build:** `Apple revenue compared with the same quarter last year` shows four quarters with no change, and `Is Apple's revenue up from a year earlier?` shows the latest quarter. Both ask for the year-over-year change; read "the same quarter last year", "a year earlier", "a year ago" and "from last year" with the year-over-year words.

Found by phrase coverage ([report](../../../../evaluation/phrase-coverage.md), `src/financial_analyst_agent/phrase_coverage.py`), judged by the README's [How a question is read](../../../../../README.md#how-a-question-is-read). The fix belongs in the shared reading of words both planners pass through (ADR 0010, 0011), not in the rules planner alone.

**Acceptance:** the cases below are read right and taken off `KNOWN_GAPS`; `uv run python -m pytest tests/unit/test_phrase_coverage.py` passes; `uv run python scripts/compare_answers.py` names every conversation whose answer changes, and each change is intended.

**Blocked by:** None — can start immediately

**Status:** resolved

## Answer

Shipped 2026-10-06. One fragment, `YEAR_EARLIER` in `request_wording.py`, names the base of a year-over-year change without the words: "a/one year ago, earlier, before", "the same quarter (or period) last year / a year earlier / of the prior year" and "the year-earlier quarter". Both the year-over-year wording (`YOY`) and the year-over-year-only wording (`EXPLICIT_YOY`) read it, so both planners do (ADR 0010, 0011). "Apple revenue compared with the same quarter last year" and "Is Apple's revenue up from a year earlier?" now show the latest 8 quarters, each with its year-over-year change, as "year over year" does. "from last year" and "a year ago" already read so; a test now holds them.

Both cases are off `KNOWN_GAPS`. `compare_answers`: 0 of 244 conversations differ (no recorded conversation uses these phrasings). README's "How a question is read" names the new wording in the year-over-year row.
