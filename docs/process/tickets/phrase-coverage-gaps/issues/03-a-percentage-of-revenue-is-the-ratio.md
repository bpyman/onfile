# 03 — "As a percentage of revenue" asks for the ratio

**What to build:** `R&D as a percentage of revenue` shows R&D and revenue side by side, and `SG&A as a percentage of sales` shows SG&A and revenue. Both ask for the catalog ratios, `rd_to_sales` and `sga_ratio`. Read "X as a percentage (or share) of revenue or sales" as X's ratio where the catalog has one.

Found by phrase coverage ([report](../../../../evaluation/phrase-coverage.md), `src/financial_analyst_agent/phrase_coverage.py`), judged by the README's [How a question is read](../../../../../README.md#how-a-question-is-read). The fix belongs in the shared reading of words both planners pass through (ADR 0010, 0011), not in the rules planner alone.

**Acceptance:** the cases below are read right and taken off `KNOWN_GAPS`; `uv run python -m pytest tests/unit/test_phrase_coverage.py` passes; `uv run python scripts/compare_answers.py` names every conversation whose answer changes, and each change is intended.

**Blocked by:** None — can start immediately

**Status:** resolved

## Answer

The catalog (`services/metric_catalog.py`), which both planners read through, now reads a figure followed by "as a percentage (percent, %, share, proportion or fraction) of revenue or sales" as that figure's ratio over revenue, where the catalog has one: R&D → `rd_to_sales`, SG&A → `sga_ratio`, and likewise gross profit, operating income and net income → their margins. A figure with no such ratio ("capex as a percentage of revenue") still shows the figure and revenue side by side. The four cases are off `KNOWN_GAPS`. `compare_answers`: 0 of 244 conversations differ; no recorded conversation uses this phrasing.
