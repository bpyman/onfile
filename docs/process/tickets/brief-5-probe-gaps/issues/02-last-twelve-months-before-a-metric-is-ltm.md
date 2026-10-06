# 02 — "Last twelve months" before a metric is the trailing-year figure

**What to build:** `pfizer's last twelve months net income` shows 4 quarters of net income. LTM stands for "last twelve months", and `LTM net income` already reads as `net_income_ttm`. Spelled out before the metric, it is the same figure: read `last twelve months` and `last 12 months` before a metric that has a trailing-year form as `TTM` is read. After the metric (`net income over the last twelve months`) it stays a window of 4 quarters, as the README's trailing-twelve-months row now says.

Cases: phrase coverage `metric:last twelve months net income:question` and `:terse`; add `pfizer net income over the last twelve months` as a window case of 4 quarters.

Found by the set-5 brief's probe dry-run (6 October 2026): a blind session labelled 30 throwaway probes from the draft brief and the README, and the app disagreed. Judged by the README's [How a question is read](../../../../../README.md#how-a-question-is-read). The fix belongs in the shared reading of words both planners pass through (ADR 0010, 0011), not in the rules planner alone, except where the ticket says the rules planner.

**Acceptance:** the cases below are read right; any phrase-coverage case named is taken off `KNOWN_GAPS`; `uv run python -m pytest` passes; `uv run python scripts/compare_answers.py` names every conversation whose answer changes, and each change is intended.

**Blocked by:** None — can start immediately

**Status:** ready-for-agent
