# 02 — NII is net interest income

**What to build:** `What was JPMorgan's NII?` is refused as an unknown metric. `NII` is the standard abbreviation for net interest income; read it as `net_interest_income`, as `EPS`, `FCF` and `ROE` are read.

Found by phrase coverage ([report](../../../../evaluation/phrase-coverage.md), `src/financial_analyst_agent/phrase_coverage.py`), judged by the README's [How a question is read](../../../../../README.md#how-a-question-is-read). The fix belongs in the shared reading of words both planners pass through (ADR 0010, 0011), not in the rules planner alone.

**Acceptance:** the cases below are read right and taken off `KNOWN_GAPS`; `uv run python -m pytest tests/unit/test_phrase_coverage.py` passes; `uv run python scripts/compare_answers.py` names every conversation whose answer changes, and each change is intended.

**Blocked by:** None — can start immediately

**Status:** resolved

## Answer

"NII" is a unique phrase for `net_interest_income` in the catalog (`services/metric_catalog.py`), which both planners read through, as "eps", "fcf" and "roe" are. The two NII cases are off `KNOWN_GAPS`. `compare_answers`: 0 of 244 conversations differ; no recorded conversation says "NII".
