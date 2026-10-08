# One copy of five small rules: the row's company key, the "unknown" company, typed proposal checks, the failed-read guard, and a dead alias

From the leftovers of simplify pass 2 (`docs/process/tickets/simplify-pass-2/dropped.md` and the tickets' Answers) and of the period-selection work (ticket 04's Answer). Cleanup only: **no behaviour may change**.

**Files (this ticket only):** `src/financial_analyst_agent/answer_notes.py`, `src/financial_analyst_agent/graph/spec_turn.py`, `src/financial_analyst_agent/period_selection.py`, `src/financial_analyst_agent/graph/turn_graph.py`, `src/financial_analyst_agent/filing_change.py`, `src/financial_analyst_agent/contracts.py`, `src/financial_analyst_agent/fan_out.py`, `src/financial_analyst_agent/universe.py`, and the tests that cover them

**What to build:**

1. **A row's company key.** `TableRow.company_key` (`contracts.py`) is `row.cik or row.company_name`, and simplify pass 2 deferred switching the sites outside presentation until it existed. Use it at every site that writes `row.cik or row.company_name` exactly: `answer_notes.py` (2), `graph/spec_turn.py` (5), `period_selection.py` (4, in `Periods.shown`'s helpers). Leave `presentation.py`'s `row.cik or row.company_name.casefold()` (two sites): it casefolds the name, so it is a different key.
2. **The "unknown" company.** A plan that names no company says `"unknown"`, and three places test for it: `turn_graph.py` (the figures-proposal check, about line 141), `spec_turn.py` (`plan_to_spec_patch`, about line 133) and `filing_change.py` (about line 882). Give `WorkflowPlan` one property that returns the named company or None, and use it at all three, keeping each site's behaviour (`spec_turn` also treats an empty name as none; check `filing_change`'s `company` is the plan's company before switching it).
3. **Typed proposal checks.** `is_filing_change_proposal`, `is_qualitative_proposal` and `is_structured_proposal` in `spec_turn.py` return `bool`; annotate the first two as `TypeGuard[WorkflowPlan]` and drop the `isinstance` calls that only narrow the type after them in `turn_graph.request_from_proposal`. Leave `is_structured_proposal` as `bool` if a `TypeGuard` would mis-narrow the `SpecPatch` branch.
4. **One failed-read guard.** `_or_none` (read, or None on failure; `SessionQuotaError` re-raised) is written twice, in `graph/spec_turn.py` and `period_selection.py`, word for word. Move it into `fan_out.py` beside `map_in_order` as a public `or_none`, and use it from both.
5. **A dead alias.** `universe.py`'s industry alias key `"oil and gas"` is never looked up: the group normaliser singularises "gas" to "ga" first, and `ranked_wording` rewrites "oil and gas" to "oil & gas" before that. Delete the key. The test that pins it as resolving to nothing (`test_oil_and_gas_is_one_industry_in_a_ranking`, or the pin test the simplify-pass-2 ticket 10 Answer names) must still pass unchanged; if it asserts the key's presence, update only that assertion and say so.

**Acceptance:** `uv run python -m pytest` passes; ruff and mypy are clean; `uv run python scripts/compare_answers.py --against master` reports `0 of N conversations differ`; phrase coverage stays 555 of 555; no source file but `contracts.py` writes `row.cik or row.company_name` without `.casefold()`; no source file but `contracts.py` compares a company to `"unknown"`; `_or_none` is defined once, in `fan_out.py`. If a step would change behaviour, or needs a file outside this ticket's list, leave it and say so in the Answer.

**Blocked by:** 01 (both edit import lines in `answer_notes.py`, `spec_turn.py` and `period_selection.py`)

**Status:** resolved

## Answer

Shipped 8 October 2026. Cleanup only; every step kept its site's behaviour.

1. **A row's company key.** `row.cik or row.company_name` is `row.company_key` at all eleven
   sites: `answer_notes.missing_component_notes` (2), `spec_turn` (`across_period_change_rows`,
   `_one_company_left`, `_order_companies_by_metric` x3) and `period_selection`'s
   `Periods._shown_window` / `_shown_named` (4). `presentation.py`'s two casefolded sites are
   untouched.
2. **The "unknown" company.** `WorkflowPlan.named_company` (`contracts.py`) returns the plan's
   company, or None when it is empty or `"unknown"`. `turn_graph._names_a_company` and
   `spec_turn.plan_to_spec_patch` read it in place of their identical inline checks.
   `filing_change`'s `company` is the plan's: `bind_filing_change` wrote `plan.company or ""` onto
   the request and `_request_refusal` later tested `not company or company == "unknown"`, so the
   binder now writes `plan.named_company or ""` and the refusal tests `not company`. The refusal
   wording is unchanged; the one difference is that a planner that read no company leaves the
   request's `company` empty rather than `"unknown"`, which the refused turn's trace records
   (`compare_answers` finds no recorded conversation that shows it). The refusal test passes the
   bound request's company instead of the raw `"unknown"` string.
3. **Typed proposal checks.** `is_filing_change_proposal` and `is_qualitative_proposal` are
   `TypeGuard[WorkflowPlan]`; `request_from_proposal` lost its three `isinstance` prefixes.
   `is_structured_proposal` stays `bool`: it is true for a `SpecPatch` too, so a `TypeGuard`
   would mis-narrow.
4. **One failed-read guard.** `fan_out.or_none` (public, beside `map_in_order`) replaces the two
   word-for-word `_or_none` copies; `spec_turn` and `period_selection` import it, and
   `period_selection` no longer imports `SessionQuotaError`. `fan_out` imports `domain.errors`,
   a leaf.
5. **A dead alias.** `"oil and gas"` is gone from `INDUSTRY_GROUP_ALIASES`.
   `test_oil_and_gas_is_one_industry_in_a_ranking` is unchanged. The pin test
   `test_each_everyday_group_name_lists_the_same_snapshot_industries` iterates the alias table and
   compares it to `EVERYDAY_GROUP_MEMBERS`, which listed the key as resolving to nothing; that one
   entry (and its comment) is removed, nothing else in the test changed.

New tests: `tests/unit/test_workflow_plan.py` (named company, "unknown" and empty) and
`or_none` in `tests/unit/test_fan_out.py` (a failed read is None; a spent budget still raises).

2,536 tests pass (2 new); ruff and mypy clean; `compare_answers.py --against master` reports
`0 of 893 conversations differ from master`; phrase coverage 555 of 555. No source file but
`contracts.py` writes `row.cik or row.company_name` uncasefolded or compares a company to
`"unknown"`; the guard is defined once. No step needed a file outside the ticket's list.
