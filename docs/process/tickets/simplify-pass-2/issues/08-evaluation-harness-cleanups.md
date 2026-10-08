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

**Status:** ready-for-agent
