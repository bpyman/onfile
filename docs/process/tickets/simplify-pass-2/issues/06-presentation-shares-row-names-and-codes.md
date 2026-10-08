# Share row identity, short names, codes and chart building in presentation

From a parallel `/simplify` review of the whole codebase (7 October 2026): seven read-only reviewers, one per area plus one across areas; 84 findings, consolidated into 12 tickets that never share a file. Cleanup only: **no behaviour may change**.

**Files (this ticket only):** `src/financial_analyst_agent/presentation.py`, `src/financial_analyst_agent/contracts.py`

**What to build:** presentation.py (2,829 lines) works out several things inline at every site where it needs them: which company a row belongs to, what that company is called in a sentence, the refusal and reason codes, and the line-chart points. Give each one a single definition. This is cleanup only: every headline, banner, label, chart and table must stay the same.

1. **`row.cik or row.company_name`** keys a TableRow by its company at presentation.py:318, 1107, 2007, 2219, 2331, 2368, 2410 and 2449. Add a `company_key` property to `TableRow` in contracts.py (`self.cik or self.company_name`), as `ResolvedCompany.key` already does, and use it at those sites. Leave 377-378 alone: its casefolded variant is a different key. Do not edit spec_turn.py or answer_notes.py, which belong to tickets 05 and 02; they can adopt the property afterwards.
2. **`short_name(row.company_name) or row.company_name`** is written six times (254, 409, 2337, 2381, 2426, and comparison_headline's local `name()`). Add a `short` property to `TableRow` with that expression. Use it at those sites and in `_names_by_cik`, and define `_owner` as `possessive(row.short)`. Leave the sites that fall back to the ticker (421, 454) as they are.
3. **`_names_by_cik` is rebuilt for each trace** inside `present_turn`'s generator over `tool_traces` (1586-1589, 2594-2600). Compute it once before the `Presentation(...)` call and pass it in.
4. **Two line charts built the same way** (`_chart_spec`'s level trend, 986-1018, and `_growth_chart`, 1113-1173). Extract `_trend_points(rows, value: Callable[[TableRow], float | None], label: Callable[[TableRow], str]) -> (periods, records, amounts, sources)`, covering the bucketing, merged records, sources, sorted periods, series and period labels, and use it for both. In `_growth_chart`, gather the shared ChartSpec arguments (`title="Growth", metric=metric, value_kind="percent", metric_label=metric_label`) once. The two copies have drifted: one fills `amounts` from merged records, the other from a separate `shown` dict. Confirm the chart JSON is unchanged for both.
5. **One banner opening, three copies** (`split_adjusted_banners` 287-293; `restated_banners` 346-362). Add `_quarters_clause(owner, metric, ends) -> tuple[str, bool]`, returning "{owner} {metric} for the quarter(s) ended {dates}" and whether there is a single quarter. Build each banner from it, choosing is/are and it/them from the flag.
6. **Refusal and reason codes as literals.** `_friendly_message` (1693-1765) compares codes as strings; compare against the error classes' `.code` instead (`UnknownIndustryError.code` and so on, from domain/errors.py, which imports nothing from the package). Key `_REASON_LABELS` (76-93) on the reason constants from contracts.py (COMPANY_NOT_FOUND, NOT_REPORTED_FOR_QUARTER, NO_DIVIDEND_THIS_QUARTER, ...). Build `_SOURCE_ERROR_CODES` (2572) from `ProviderError.code` and `DataIntegrityError.code`. In contracts.py, `refuse_unknown_metric` (536) uses `UnknownMetricError.code`. Leave the spec-validation codes (`invalid_metric`, `empty_spec`) and the frozen `_legacy_refusal` migration table as they are. No value changes.

**Acceptance:** all tests pass; ruff and mypy are clean; `uv run python scripts/compare_answers.py` reports `0 of N conversations differ`, which compares presentations, charts and banners.

**Findings covered:**
- across/simplification (presentation part): row.cik or row.company_name used as a TableRow's company key
- across/simplification (TableRow half) + turn/efficiency (duplicate): short_name(row.company_name) or row.company_name six times
- turn/efficiency: _names_by_cik rebuilt per trace in present_turn
- turn/simplification: _chart_spec level trend and _growth_chart build line charts the same way
- turn/simplification: banner opening written three times in split_adjusted_banners and restated_banners
- across/reuse (presentation and contracts part): refusal and reason codes written as string literals

**Acceptance:** `uv run python -m pytest` passes; ruff and mypy are clean; `uv run python scripts/compare_answers.py` reports `0 of N conversations differ`; phrase coverage stays 555 of 555. If a step would change behaviour, or needs a file outside this ticket's list, leave it and say so in the Answer.

**Blocked by:** None — can start immediately

**Status:** ready-for-agent
