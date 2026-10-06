# 04 — Trailing twelve months is one trailing-year figure

**What to build:** `trailing twelve month net income` and `TTM net income` show four quarters of net income. The catalog has `net_income_ttm`, one trailing-year figure (ADR 0008); read "trailing twelve months", "TTM" and "LTM" before a metric that has a trailing-year form as that form.

Found by phrase coverage ([report](../../../../evaluation/phrase-coverage.md), `src/financial_analyst_agent/phrase_coverage.py`), judged by the README's [How a question is read](../../../../../README.md#how-a-question-is-read). The fix belongs in the shared reading of words both planners pass through (ADR 0010, 0011), not in the rules planner alone.

**Acceptance:** the cases below are read right and taken off `KNOWN_GAPS`; `uv run python -m pytest tests/unit/test_phrase_coverage.py` passes; `uv run python scripts/compare_answers.py` names every conversation whose answer changes, and each change is intended.

**Blocked by:** None — can start immediately

**Status:** ready-for-agent
