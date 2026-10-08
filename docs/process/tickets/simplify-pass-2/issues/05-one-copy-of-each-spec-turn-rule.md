# Keep one copy of each rule in spec_turn and apply_patch

From a parallel `/simplify` review of the whole codebase (7 October 2026): seven read-only reviewers, one per area plus one across areas; 84 findings, consolidated into 12 tickets that never share a file. Cleanup only: **no behaviour may change**.

**Files (this ticket only):** `src/financial_analyst_agent/graph/spec_turn.py`, `src/financial_analyst_agent/graph/analysis_spec.py`, `src/financial_analyst_agent/graph/state.py`

**What to build:** spec_turn.py (1,581 lines) writes several of its rules two or three times: failure isolation, the derived-window history read, the latest-level ranking, and the refusal builders. `apply_patch` writes one list edit in two styles. Keep one copy of each. This is cleanup only: no answer, refusal, note or row order may change.

1. **Failure isolation twice** (`dispatch_compiled_tasks`, 579-584 and 606-611). Add `_run_isolated(task, runtime) -> TurnResult`, which wraps `execute_compiled_task` in the existing `except SessionQuotaError: raise / except Exception as exc: _task_failure_result(task, exc)`. The sequential loop appends `_run_isolated(task, runtime)`. The pool submits `copy_context().run, partial(_run_isolated, task, runtime)` and stores `future.result()` with no try; a spent quota still re-raises through `future.result()`.
2. **`_after_latest_filing` (1421-1428)** has its own copy of the quota rule. Use `listed = _or_none(partial(runtime.facts.fiscal_periods, spec.companies[0].handle))`; the existing `if not listed: return False` covers both None and an empty list.
3. **The derived-window pipeline twice.** `overview_trend` (1468-1484) and `earlier_quarters` (1535-1571) both run materialize, compile, dispatch and `merge_task_results(across_periods=False)`, both catch `(CompanyNotFoundError, SessionQuotaError, *SOURCE_FAILURES)` and both keep level rows. Extract `_window_levels(window, runtime, *, max_workers, narrow=None) -> TurnResult | None`, where `narrow(window) -> AnalysisSpec | None` is earlier_quarters' choice of the adjacent and year-earlier dates (None means no answer). It returns only rows with `comparison is None and value is not None`. `overview_trend` becomes one call; `earlier_quarters` keeps only its date choice, its split filter, and the split into prior and year-earlier rows.
4. **The latest level per company twice** (`_order_by_metric` and `_order_companies_by_metric`, 832-899). Extract `_latest_levels(rows, metric, key: Callable[[TableRow], str | None]) -> dict[str, TableRow]` and `_value_order(latest, ascending, tiebreak)` for the shared `(value is None, sign * (value or 0), tiebreak)` sort key. Keep each caller's own filtering: the ranking keys on `row.cik` and skips rows without one; named companies key on `row.cik or row.company_name` and skip rows without a value. Keep the `end_date` comparison as it is.
5. **Three ways to build a REFUSE result** (487-494, 1006-1019, 1110-1177, 1367-1376). Make `_rejection_result(rejection, intent)` return `_refusal(intent, rejection.message, refusal=Refusal(code=rejection.code, details=rejection.details))`. Add `_empty_spec(asked, message)` for the four `SpecRejection(code="empty_spec", ...)` sites (1113, 1141, 1159, 1173). Replace the inline invalid-quarter `TurnResult` (1008-1017) with `_refusal(intent, ...)`; both use `intent or Intent.LOOKUP`.
6. **The invalid-metric rejection twice** (spec_turn.py:1060-1072; analysis_spec.py:502-507). Add `metric_rejection(metrics) -> SpecRejection | None` to analysis_spec.py, returning the detailed form (term and allowed). `validate_spec` calls it first, and resolve_request's early check, which must stay before `resolve_spec` so an invalid metric is refused before any ranking or SEC identity read, becomes `rejection = metric_rejection(draft.metrics)`. The turn's answer is unchanged; `validate_spec`'s rejection only gains details, which no answer reads.
7. **`apply_patch` (analysis_spec.py:292-359, 384-389)** writes "drop the removed items, then append the added ones not yet present" as comprehensions in the ranking branch and as loops in the extend branch, and filters companies by `_company_matches_token` three times. Add `_edited(items, remove, add) -> list` and `_kept(companies, tokens) -> list[ResolvedCompany]`, and use them for metrics, operations and companies in both branches and in `emptied_by`. Order and de-duplication stay as today.
8. **The window is read in two places** (state.py:77; spec_turn.py:1000). Give `StructuredRequest` a `model_validator(mode="before")` that fills `window` from `read_window(wording)` when it is absent or None, and type the field as `WindowReading`. Stored checkpoints holding `window: null` must still load. spec_turn then reads `request.window` with no fallback. Leave clarify.py, turn_graph.py and request_wording.py unchanged; their own defaults stay.

**Acceptance:** all tests pass; ruff and mypy are clean; an existing stored thread with a pending clarification still resumes; `uv run python scripts/compare_answers.py` reports `0 of N conversations differ`.

Not in this ticket: spec_turn's eight `row.cik or row.company_name` sites, which can switch to `TableRow.company_key` once ticket 06 lands.

**Findings covered:**
- graph/simplification: dispatch_compiled_tasks writes failure isolation twice
- graph/reuse: _after_latest_filing repeats _or_none
- graph/reuse: overview_trend and earlier_quarters run the same derived-window pipeline
- graph/simplification: _order_by_metric and _order_companies_by_metric copy latest-level map and sort key
- graph/simplification: resolve_request builds REFUSE results three ways; four empty_spec wrappers
- graph/reuse: invalid-metric rejection built in resolve_request and validate_spec
- graph/simplification: apply_patch writes the same list edit in two styles and the company filter three times
- across/simplification: StructuredRequest.window optional with read_window fallbacks

**Acceptance:** `uv run python -m pytest` passes; ruff and mypy are clean; `uv run python scripts/compare_answers.py` reports `0 of N conversations differ`; phrase coverage stays 555 of 555. If a step would change behaviour, or needs a file outside this ticket's list, leave it and say so in the Answer.

**Blocked by:** None — can start immediately

**Status:** ready-for-agent
