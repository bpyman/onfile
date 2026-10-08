# Remove the copies in the planner evaluation and fixture scripts

From a parallel `/simplify` review of the whole codebase (7 October 2026): seven read-only reviewers, one per area plus one across areas; 84 findings, consolidated into 12 tickets that never share a file. Cleanup only: **no behaviour may change**.

**Files (this ticket only):** `src/financial_analyst_agent/planner_evaluation.py`, `src/financial_analyst_agent/evaluation.py`, `src/financial_analyst_agent/held_out_overlap.py`, `scripts/record_sec_fixtures.py`, `scripts/trim_sec_test_fixture.py`, `scripts/build_everyday_words.py`

**What to build:** The evaluation harness repeats its bookkeeping. The budget-stopped marker is a bare string, accuracy per run is computed three times, `main` has one block per planner, and the protocol text is patched with `str.replace`. Remove the copies. The reports, saved JSON and printed figures must not change.

1. **The protocol is patched with `str.replace` (planner_evaluation.py:892-978).** `protocol()` replaces whole literal sentences ("66), the held-out split here.", "66 cases detect only large") and finds where to insert the fifth-set paragraph through the `_FIFTH_AT` sentinel. Make the protocol a function of `(held_out, held_out_count)` that writes its lines directly, with f-strings for the fourth set's clause and the count, and append the fifth-set item when `held_out >= 5`. The output must be identical; `test_the_protocol_names_the_set_held_out` pins it.
2. **Accuracy per run, three copies** (`scores` 499-507 and 626-635, `_held_out_groups` 707-711). Add `_accuracy_by_run(chosen, runs, *, adjudicated=False) -> list[float]` using `r.passes(adjudicated)`. Make `CaseRun.passed` return `self.passes(adjudicated=False)`, so `passes` holds the one all-checks-right test.
3. **The "budget reached" marker** is written once (555) and compared at five sites (567, 592, 618, 619, 723). Use a module constant `_BUDGET_REACHED = "budget reached"`, or a `CaseRun.stopped` property, everywhere. The saved JSON keeps the same value.
4. **`main` has one block per planner (1185-1204, 1233-1239, 1276-1333).** Add `_write(report)` for both writes, the `--from-json` branch included. Add `_scored(name, label, cases, completer, usage, prices, **extra)`, which runs a planner and records `results_by_planner[name]` and `report["planners"][name]`. Read `settings.require_openai_model()` once in `_llm_completer`. Copy the cascade's three token counts with `dataclasses.replace`.
5. **Codes as literals (part of the across codes finding).** Build `_NO_DATA_CODES` (123-125) from `UnsupportedQuarterlyFactError.code` and the contracts.py constants for `missing_fact` and `not_reported_for_quarter`. The values do not change.
6. **evaluation.py.** `_check_result` (352-381) repeats one pattern six times: build a `have_*` set and report the expected items missing from it. Add `_missing(label, wanted, have) -> str` and chain the six checks through it. In `run_suite` (432-503), time each case once (`try/finally`, or one `elapsed_ms`). First verify that `passed` always equals `not detail` (an exception sets `detail` to its name), then set `passed = not detail`.
7. **held_out_overlap.py (101-130, 142-143).** Add `_earlier(source, turns, companies) -> Earlier` for the three constructors. Call `load_cases()` with no arguments and drop the `CASE_PATHS` import. Compute the nearest match's similarity once (`scored = [(_similarity(words, e.words), e) for e in earlier]`, then `max(scored, key=lambda pair: pair[0])`). This keeps the first-wins tie order that `max(key=...)` has today; never compare `Earlier` objects.
8. **Scripts.** record_sec_fixtures.py:66 and trim_sec_test_fixture.py:24 each redefine `PERIODIC_FORMS`. Import it from `financial_analyst_agent.domain.enums`; `FormType` is a StrEnum, so raw form strings still match. In `_sync_fixture_snapshot` (record_sec_fixtures.py:96-101), build `live_by_cik` once instead of five cik-keyed dicts. In `build_everyday_words._sample` (41-45), read the snapshot through `universe.load_universe_snapshot(SNAPSHOT).companies`, sorted by `company.market_cap`, as `build_former_names.main` does.

**Acceptance:** all tests pass; ruff and mypy are clean; `uv run python -m financial_analyst_agent.planner_evaluation --from-json <the latest saved report>` writes the same Markdown and JSON as before; the held-out overlap report is unchanged; re-running the fixture trimmer on the current fixture changes no file.

**Findings covered:**
- eval/altitude: protocol() patches the fixed text with str.replace and the _FIFTH_AT sentinel
- eval/simplification: accuracy per run computed three times; passed and passes repeat the test
- eval/simplification: 'budget reached' marker is a bare string compared at five sites
- eval/simplification: main repeats one block per planner; duplicated writes; model name read twice
- across/reuse (planner_evaluation part): _NO_DATA_CODES spelled as literals
- eval/simplification: evaluation._check_result repeats a missing-items pattern six times; run_suite timing and passed flag
- eval/simplification: held_out_overlap builds Earlier three times, restates load_cases' default, recomputes similarity
- eval/reuse: record_sec_fixtures and trim_sec_test_fixture redefine PERIODIC_FORMS
- eval/simplification: _sync_fixture_snapshot builds five dicts; build_everyday_words parses the snapshot by hand

**Acceptance:** `uv run python -m pytest` passes; ruff and mypy are clean; `uv run python scripts/compare_answers.py` reports `0 of N conversations differ`; phrase coverage stays 555 of 555. If a step would change behaviour, or needs a file outside this ticket's list, leave it and say so in the Answer.

**Blocked by:** None — can start immediately

**Status:** resolved

## Answer

Shipped 7 October 2026. Cleanup only: the planner comparison's Markdown and JSON, the held-out
overlap report, the fixture snapshot sync, the trimmer's output, the protocol text, the printed
figures and the recorded demo answers are byte for byte as before (each compared against a
baseline captured at the previous commit).

1. **protocol()** writes its lines directly: the fourth set's clause is `{fourth}` inside the
   item, the "Two limits" count is `{held_out_count}`, and the fifth-set item is spliced in
   after the fourth with `*fifth` when `held_out >= 5`. `_PROTOCOL` and `_FIFTH_AT` are gone.
   `protocol(4, 66)`, `protocol(5, 160)` and `protocol(5, 66)` are identical to before;
   `test_the_protocol_names_the_set_held_out` still pins the wording and a new test pins the
   layout (one more line, right after the fourth set).
2. **`_accuracy_by_run(chosen, runs, *, adjudicated=False)`** is the one accuracy-per-run figure,
   used twice in `scores` and once in `_held_out_groups`. `CaseRun.passes(adjudicated=False)`
   holds the one all-checks-right test and `passed` returns `passes(adjudicated=False)`.
3. **`_BUDGET_REACHED = "budget reached"`** is written once in `run_planner`, and
   `CaseRun.stopped` (`error == _BUDGET_REACHED`) is read at the five sites. The saved JSON keeps
   the same words.
4. **`main`**: `_write(report)` writes the Markdown and JSON for both the run and `--from-json`;
   `_scored(name, label, cases, completer, usage, prices, *, llm_usage=None)` is a closure in
   `main` that runs a planner and records `results_by_planner[name]` and
   `report["planners"][name]`. It takes `llm_usage` rather than `**extra` because the cascade's
   `llm_calls` and its three token counts are known only after the run; with it, the counts are
   copied with `dataclasses.replace` and `llm_calls` is added before the summary, in the same key
   order as before. `_llm_completer` reads `settings.require_openai_model()` once.
5. **`_NO_DATA_CODES`** is built from `UnsupportedQuarterlyFactError.code`, `MISSING_FACT` and
   `NOT_REPORTED_FOR_QUARTER`; the values are unchanged.
6. **evaluation.py**: `_missing(label, wanted, have)` chains the six checks; the wording
   (`missing tickers ['ZZZ']`) is unchanged and now tested. `_run_case(case, runtime)` runs a
   case's turns and returns the check's detail; `run_suite` times it once with `try/finally` and
   sets `passed = not detail` (an exception sets `detail` to its class name, so the two agreed
   before). The timing now includes the check itself, a few milliseconds the scorecard rewrites
   on every run anyway.
7. **held_out_overlap.py**: `_earlier(source, turns, companies)` builds the three `Earlier`
   kinds; `earlier_data` calls `load_cases()` with no arguments (its default is the same
   `CASE_PATHS` filter) and the `CASE_PATHS` import is gone; the nearest match's similarity is
   computed once over `scored` pairs with `max(key=lambda pair: pair[0])`, which keeps the first
   of equals (tested).
8. **Scripts**: `record_sec_fixtures` and `trim_sec_test_fixture` import `PERIODIC_FORMS` from
   `domain.enums` (tested as the same object); `_sync_fixture_snapshot` builds `live_by_cik`
   once (tested on a two-company snapshot, key order included); `build_everyday_words._sample`
   reads the snapshot through `load_universe_snapshot(SNAPSHOT).companies` sorted by
   `company.market_cap` and returns `UniverseCompany` rows, so `main` reads `company.cik` and
   `company.ticker` (tested against the live snapshot).

Checks: 2,366 tests pass; ruff and mypy are clean; `compare_answers` reports 0 of 375
conversations differ. `--from-json` on the committed `planner-comparison.json` (written to a
scratch copy) gives the same Markdown and JSON before and after. The overlap report could not be
re-run with the committed report's probe file (another session's scratchpad, gone), so
`overlap_report()` without probes was compared before and after: identical, 52 of 160 familiar.
No cached SEC pair matches a committed test fixture, so the trimmer was run on the cached Exxon
pair before and after instead: identical output. The fixture snapshot sync, run into a scratch
copy, leaves the committed file as it is.

Files: `src/financial_analyst_agent/planner_evaluation.py`, `evaluation.py`,
`held_out_overlap.py`; `scripts/record_sec_fixtures.py`, `trim_sec_test_fixture.py`,
`build_everyday_words.py`; `tests/unit/test_planner_evaluation.py` (+2),
`tests/unit/test_held_out_set.py` (+2), `tests/unit/test_script_constants.py` (+3),
`tests/test_evaluation.py` (two assertions).
