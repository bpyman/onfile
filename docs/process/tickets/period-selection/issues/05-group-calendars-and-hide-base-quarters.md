# `Periods.groups` and `Periods.shown`: calendar groups and base-row hiding move in; `compile_tasks` moves beside its caller

From the architecture review of 8 October 2026: period selection becomes one module, per `docs/process/tickets/period-selection/design.md` and ADR 0015. Restructure only: **no behaviour may change**. Read the design record in full before starting.

**Files (this ticket only):** `src/financial_analyst_agent/period_selection.py`, `src/financial_analyst_agent/graph/analysis_spec.py`, `src/financial_analyst_agent/graph/spec_turn.py`, `tests/unit/test_period_selection.py`, `tests/unit/test_analysis_spec.py`, `tests/unit/test_calendars_clarification_and_formatting.py`, `tests/unit/test_derived_and_named_periods.py`, `tests/unit/test_filers_rankings_and_narrowing.py`, and any other test that imports `compile_tasks`, `calendar_groups` or the `_without_*` helpers

**What to build:**

1. **`Periods.groups`** replaces `analysis_spec.calendar_groups`, `_quarter_phase` and `_same_grid` (with `FISCAL_WEEK_TOLERANCE` where it is used), computed once per call as today; it is now the one place that groups companies by quarter grid for compilation, notes and row hiding.
2. **`compile_tasks` moves** from `analysis_spec` to `spec_turn`, beside `resolve_request`, its one caller, and uses `Periods(spec).groups`. `analysis_spec` then holds only stored shapes, their validators and `apply_patch`, and the module can import it without a cycle. `CompiledTask` moves with it if nothing else in `analysis_spec` needs it.
3. **`Periods.shown(rows)`** replaces `_without_base_quarters` and `_without_named_bases`: a window row ending before its company's oldest shown quarter, and a named base row whose end is a base date, are dropped; rows with no end date or an unknown company stay. Rows are keyed by `row.cik or row.company_name` (checklist). `merge_analysis` calls it where it called `_without_base_quarters`.
4. Tests of `calendar_groups`, `compile_tasks` and the `_without_*` helpers are rewritten against `Periods.groups`, `compile_tasks` in its new home, and `Periods.shown`, and the old ones deleted.

**Acceptance:** `uv run python -m pytest` passes; ruff and mypy are clean; `uv run python scripts/compare_answers.py --against master` reports `0 of N conversations differ`; phrase coverage stays 555 of 555; `analysis_spec` defines no function that reads `report_dates` except validators; `calendar_groups`, `_without_base_quarters` and `_without_named_bases` no longer exist. The checklist item touched: row identity. If a step would change behaviour, or needs a file outside this ticket's list, leave it and say so in the Answer.

Spec: `docs/process/tickets/period-selection/design.md`, ADR 0015, ADR 0009 (sequential bases are read, not shown).

**Blocked by:** 04 (`Periods` exists)

**Status:** ready-for-agent
