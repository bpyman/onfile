# `Periods.dated`: dating the quarters and the two period refusals move into the module

From the architecture review of 8 October 2026: period selection becomes one module, per `docs/process/tickets/period-selection/design.md` and ADR 0015. Restructure only: **no behaviour may change**. Read the design record in full before starting.

**Files (this ticket only):** `src/financial_analyst_agent/period_selection.py`, `src/financial_analyst_agent/graph/spec_turn.py`, `tests/unit/test_period_selection.py`, `tests/unit/test_calendars_clarification_and_formatting.py`, `tests/unit/test_filers_rankings_and_narrowing.py`, `tests/unit/test_public_errors.py`, `tests/unit/test_multi_period.py`, `tests/unit/test_window_copy.py`

**What to build:**

1. **`Periods(spec)`** is born as the frozen view the design record gives, with `dated(facts) -> Dated` as its first member. It replaces `spec_turn.materialize_period_dates`, `_window_dates`, `_fiscal_window_dates`, `_span_asked`, `_not_yet_listed`, `_named_dates`, `_quarters_before`, `_materialize_named_periods` and `_after_latest_filing`. `_or_none` moves with them if nothing else in `spec_turn` uses it.
2. **`Dated(spec, refusal)`** folds both period refusals of `resolve_request` (the empty dated window, and the named period after the latest filing or outside the filings) into one `refusal: str | None` of finished text, with the message texts unchanged. `resolve_request` becomes the shape the design record shows: catch the first company's listing errors as today, then `if dated.refusal is not None`.
3. **The facts provider is an argument.** `dated` takes `runtime.facts`, never `Runtime`; the first company (or first constituent) is listed alone and unwrapped, the rest fanned out under `map_in_order` with every error but `SessionQuotaError` swallowed (checklist). Dates already on the spec are kept, so an added company lists only itself. A latest-quarter or already-dated spec returns the same object. An undated window is returned undated, not refused, because `overview_trend` compiles one.
4. **`overview_trend`, `earlier_quarters` and `_window_levels`** call `Periods(window_spec).dated(runtime.facts).spec`.
5. Tests of `materialize_period_dates` are rewritten against `Periods.dated` with `ListedFilings` (ticket 01), asserting per-company dates, `count`, `asked`, `company_base_dates`, `refusal`, listing order and limits, and the error asymmetry; `test_public_errors.py`'s monkeypatch of `materialize_period_dates` is rewritten to patch `Periods.dated`. Old tests are deleted.

**Acceptance:** `uv run python -m pytest` passes; ruff and mypy are clean; `uv run python scripts/compare_answers.py --against master` reports `0 of N conversations differ`; phrase coverage stays 555 of 555; `materialize_period_dates` and the eight helpers named above no longer exist in `spec_turn`. The checklist items touched: after-latest-filing re-lists unless shown safe; first-company asymmetry and fan-out; undated windows still compile. If a step would change behaviour, or needs a file outside this ticket's list, leave it and say so in the Answer.

Spec: `docs/process/tickets/period-selection/design.md`, ADR 0015, ADR 0005 (resolve materializes periods by reading only filing lists), ADR 0007.

**Blocked by:** 01 (`ListedFilings`), 02 (`period_selection` exists)

**Status:** ready-for-agent
