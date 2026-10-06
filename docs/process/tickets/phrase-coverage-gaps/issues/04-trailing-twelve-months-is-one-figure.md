# 04 — Trailing twelve months is one trailing-year figure

**What to build:** `trailing twelve month net income` and `TTM net income` show four quarters of net income. The catalog has `net_income_ttm`, one trailing-year figure (ADR 0008); read "trailing twelve months", "TTM" and "LTM" before a metric that has a trailing-year form as that form.

Found by phrase coverage ([report](../../../../evaluation/phrase-coverage.md), `src/financial_analyst_agent/phrase_coverage.py`), judged by the README's [How a question is read](../../../../../README.md#how-a-question-is-read). The fix belongs in the shared reading of words both planners pass through (ADR 0010, 0011), not in the rules planner alone.

**Acceptance:** the cases below are read right and taken off `KNOWN_GAPS`; `uv run python -m pytest tests/unit/test_phrase_coverage.py` passes; `uv run python scripts/compare_answers.py` names every conversation whose answer changes, and each change is intended.

**Blocked by:** None — can start immediately

**Status:** resolved

## Answer

2026-10-06. "TTM net income", "LTM net income" and "trailing twelve month(s) net income" (also "trailing 12-month", and before "net profit", "net earnings" or "earnings") read as `net_income_ttm`, one amount over the four quarters to the latest report. The four phrase-coverage cases are off `KNOWN_GAPS`.

- The catalog reads the words before a figure that has a trailing-year form (only net income) as that form, after the longest phrases are taken; both planners read through it (ADR 0010, 0011). "TTM revenue" still shows the latest 4 quarters.
- Those words are not a window: `read_window`, the span check for changes and the planner-window cue read the question without them, so the answer is the latest period, one figure.
- `net_income_ttm` joins `REPORTED_METRICS`. It is shown as a trailing year, as return on equity and P/E are: "Reported · Trailing year" (or "Derived †") on the card, no quarter-over-quarter or year-over-year chips, no long-quarter note, "Period ended" in tables (`TRAILING_YEAR_FIGURES`).
- Its name is now "Trailing-year net income" (the catalog legend has no parentheses).
- README "How a question is read" gains a trailing-twelve-months row; ADR 0008 notes the figure can be asked for itself.

compare_answers: 1 of 244 conversations differs, "Apple and Tesla return on equity": its evidence and trace labels read "Trailing-year net income" instead of "Net income (trailing year)". Intended.
