# 02 — "Last twelve months" before a metric is the trailing-year figure

**What to build:** `pfizer's last twelve months net income` shows 4 quarters of net income. LTM stands for "last twelve months", and `LTM net income` already reads as `net_income_ttm`. Spelled out before the metric, it is the same figure: read `last twelve months` and `last 12 months` before a metric that has a trailing-year form as `TTM` is read. After the metric (`net income over the last twelve months`) it stays a window of 4 quarters, as the README's trailing-twelve-months row now says.

Cases: phrase coverage `metric:last twelve months net income:question` and `:terse`; add `pfizer net income over the last twelve months` as a window case of 4 quarters.

Found by the set-5 brief's probe dry-run (6 October 2026): a blind session labelled 30 throwaway probes from the draft brief and the README, and the app disagreed. Judged by the README's [How a question is read](../../../../../README.md#how-a-question-is-read). The fix belongs in the shared reading of words both planners pass through (ADR 0010, 0011), not in the rules planner alone, except where the ticket says the rules planner.

**Acceptance:** the cases below are read right; any phrase-coverage case named is taken off `KNOWN_GAPS`; `uv run python -m pytest` passes; `uv run python scripts/compare_answers.py` names every conversation whose answer changes, and each change is intended.

**Blocked by:** None — can start immediately

**Status:** resolved

## Answer

Shipped 6 October 2026. `pfizer's last twelve months net income`, `last 12 months net income` and `past twelve months net income` now read as `net_income_ttm`, the one trailing-year amount, exactly as `LTM net income` does. After the metric, `pfizer net income over the last twelve months` stays a window of 4 quarters.

The fix is in the shared reading of words both planners pass through: the metric catalog's trailing-year words (`_TRAILING_YEAR_WORDS` in `services/metric_catalog.py`) accept `last` or `past` + `twelve`/`12 months` just before a metric with a trailing-year form, so `resolve_metric_phrase` reads the figure and `without_trailing_year_words` strips the words before the window is read. The words only count directly before the metric, so the after-the-metric form is untouched. The rules planner and `request_wording.TRAILING_YEAR` are unchanged.

Cases: `metric:last twelve months net income:question` and `:terse` are off `KNOWN_GAPS`; `window:pfizer net income over the last twelve months` is a new window case of 4 quarters (`WINDOW_QUESTIONS` in `phrase_coverage.py`). Unit tests in `tests/unit/services/test_metric_phrase.py` and `tests/unit/test_derived_and_named_periods.py` cover both sides.

1,949 tests pass; ruff and mypy pass; `compare_answers.py` reports 0 of 244 conversations differ (no recorded conversation uses these words). The README's trailing-twelve-months row already described this reading, so it is unchanged.
