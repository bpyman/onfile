# Give the numeral lock its own module and share the turn's row and essay rules

From a parallel `/simplify` review of the whole codebase (7 October 2026): seven read-only reviewers, one per area plus one across areas; 84 findings, consolidated into 12 tickets that never share a file. Cleanup only: **no behaviour may change**.

**Files (this ticket only):** `src/financial_analyst_agent/turn.py`, `src/financial_analyst_agent/numeral_lock.py`, `src/financial_analyst_agent/filing_change.py`, `src/financial_analyst_agent/mcp_server.py`, `src/financial_analyst_agent/numeral_lock_evaluation.py`

**What to build:** The numeral lock is about 175 lines of regexes and rounding logic kept as private helpers inside the 1,341-line turn.py (98-280). Three modules import its underscore names: filing_change.py:1167 (inside a function, to avoid a cycle), mcp_server.py:20-22 and numeral_lock_evaluation.py:32. turn.py and mcp_server.py also each decide which row builder serves a metric. Give the lock a module of its own and keep one copy of each rule. This is cleanup only: no essay, filing summary, MCP response or refusal may change.

1. **Move the lock** into a new `numeral_lock.py`, unchanged: `_NUMERIC_TOKEN`, `_CITE_MARKER`, `_IDENTIFIER_KEYS`, `_MONTH`, `_AMOUNT_AFTER`, `_DATE_TEXT`, `_YEAR`, `_UNIT_SCALE`, `_FIGURE_PARTS`, `_PERCENT_AFTER`, `_MIN_SIGNIFICANT_DIGITS`, and the functions `_strip_valid_citation_markers` through `_numeral_lock_message`. Expose `numeral_lock_extras` and `numeral_lock_message` as public names. turn, filing_change (as a top-level import, replacing the function-level one), mcp_server and numeral_lock_evaluation import from it. Keep re-exports of the old private names in turn.py only if tests use them, and prefer updating the tests.
2. **One withhold-or-show tail for essays.** `explain_answer` (turn.py:302-328) and `_news_grounded_essay_turn` (437-459) each run the lock and then return either a REFUSE result (built with the extras and their message) or an ESSAY result with banners. Extract `_locked_essay(intent, essay, lock_json, traces, banners, *, citations=(), hit_count=0) -> TurnResult`. `explain_answer` also writes out the replayed-essay banner condition itself (`runtime.kind is LIVE and not runtime.live_essays`, 363-372). Split `_replay_banners` into a news half and an essay half, or give it a `news: bool = True` parameter, so `explain_answer` calls the essay half.
3. **One row-builder dispatch.** `mcp_server._metric_rows` (50-57) repeats `_metrics_turn`'s choice (turn.py:1125-1143): `snapshot_compare_rows` for SNAPSHOT_METRICS, `market_formula_rows` for MARKET_FORMULAS (which needs a ranking), otherwise `compare_metrics`. Add a public `metric_rows(runtime, issuers, metric, *, report_date=None) -> list[TableRow]` in turn.py that holds this branch. `_metrics_turn` calls it after its single-issuer `lookup_member` special case, and mcp_server calls it in place of `_metric_rows`, dropping its three row-builder imports. Each caller checks `runtime.ranking` before the call, so each keeps its own RuntimeError text.
4. **Provenance copied by hand four times.** `_part_provenance`, `_table_row_from_fact`, `_lookup_provenance` and `_provenance_from_fact` (turn.py:479-499, 523-544, 551-565, 628-642) each copy the same provenance fields. Define `_PROVENANCE_FIELDS = ("start_date", "end_date", "form", "accession_number", "taxonomy", "concept", "source_url")` and build each target with `**fact.model_dump(include=_PROVENANCE_FIELDS)`; python mode keeps the date types. Add each target's own extras, including `split_adjustment`, as today. Inline the one-line wrappers `_fact_source_kind` and `_metric_name`. Check that the trace dicts serialise exactly as before.
5. **Five refusal blocks in `run_filing_change`** (filing_change.py:1004-1009, 1013-1018, 1025-1035, 1106-1116, 1128-1133). Add a local `refuse(message: str, exc: BaseException | None = None) -> TurnResult`. It fills the intent, traces and renderer, and sets `refusal` to `refusal_from_error(exc)` when `exc` is a FinancialAnalystError. Each refusal site becomes one line.
6. **`diff_paragraphs` recomputes normal forms** (filing_change.py:518-530, 554-620, 636-651). Compute `comparable_left/right` once (the lists already passed to SequenceMatcher) and compare those at line 614 instead of calling `_comparable` again. Compute each paragraph's word set once and pass the sets into `_aligned`. In `_aligned`, record the DP pass's `similar` in a matrix so the traceback reads it instead of calling `_likeness` again. In `_rejoin_moved`, compute each added change's `_words` once, before the loop over removed changes.
7. **Nested lambdas in numeral_lock_evaluation.py KINDS** (142, 148, 154, 166). Let `_say(quote, number: str | None)` return None when `number` is None, and write each kind as `lambda q, _qs: _say(q, _rounded(q.shown))`. For `misattributed`, add a one-line `_say_other(q, qs)`.

**Acceptance:** all tests pass, including the numeral-lock and filing-change tests; ruff and mypy are clean; `uv run python -m financial_analyst_agent.numeral_lock_evaluation` (or its test) reports the same counts; `uv run python scripts/compare_answers.py` reports `0 of N conversations differ`; `import financial_analyst_agent.filing_change` works with no function-level import of turn.

**Findings covered:**
- turn/altitude + across/altitude (duplicate): numeral lock private helpers in turn.py imported by three modules
- turn/reuse + across/reuse (duplicate): mcp_server._metric_rows repeats _metrics_turn's row-builder dispatch
- turn/simplification: explain_answer and _news_grounded_essay_turn repeat the lock tail; replayed-essay banner rule written twice
- turn/simplification: four functions copy provenance fields by hand; one-line wrappers
- turn/simplification: run_filing_change builds the REFUSE TurnResult five times
- turn/efficiency: diff_paragraphs recomputes per-paragraph normal forms and word sets
- eval/simplification: numeral_lock_evaluation KINDS use immediately-invoked nested lambdas

**Acceptance:** `uv run python -m pytest` passes; ruff and mypy are clean; `uv run python scripts/compare_answers.py` reports `0 of N conversations differ`; phrase coverage stays 555 of 555. If a step would change behaviour, or needs a file outside this ticket's list, leave it and say so in the Answer.

**Blocked by:** None — can start immediately

**Status:** resolved

## Answer

Shipped 7 October 2026, cleanup only: compare_answers `0 of 375 conversations differ`;
2,338 tests pass; ruff and mypy clean; the numeral-lock evaluation reports the same
counts before and after (36 sentences a kind, 14 misattributed; the same withheld
figures); phrase coverage 555 of 555 (report not regenerated).

1. **`numeral_lock.py`** holds the patterns and functions unchanged, with
   `numeral_lock_extras` and `numeral_lock_message` public. turn, filing_change
   (a top-level import; no function-level import of turn remains), mcp_server and
   numeral_lock_evaluation import from it. turn.py keeps no re-exports: the three
   tests in `test_filing_change.py` import from the new module, and a fourth checks
   filing_change binds the module-level name.
2. **`_locked_essay(intent, essay, lock_json, traces, banners, *, citations=None,
   hit_count=0)`** is the one withhold-or-show tail; `_replay_banners(runtime, *,
   news=True)` labels the essay alone with `news=False`, which `explain_answer` uses.
3. **`turn.metric_rows(runtime, issuers, metric, *, report_date=None)`** holds the
   row-builder branch and is in `__all__`. `_metrics_turn` calls it after the
   snapshot-metric early return (whose single-issuer `lookup_member` case and
   snapshot trace stay in `_snapshot_metrics_turn`); mcp_server's `_metric_rows`
   keeps only its ranking check and calls it, its three row-builder imports gone.
   Each caller keeps its own RuntimeError text. `tests/unit/test_metric_rows.py`
   (+2) checks the dispatch and that the MCP compare goes through it.
4. **Provenance:** `_PROVENANCE_FIELDS` and `**model_dump(include=...)` build the
   three pydantic targets (`_part_provenance`, `_table_row_from_fact`,
   `_provenance_from_fact`); `_fact_source_kind` and `_metric_name` are inlined.
   **Left as a literal:** `_lookup_provenance`. The recorded demo answers and
   compare_answers hold a trace's outputs as ordered pairs, so its key order
   (`form` first, `source` before `source_url`) is part of the answer; a model dump
   orders by model field and failed `test_committed_demo_answers_match_a_fresh_recorded_run`
   in 163 conversations. A comment at the site says why.
5. **`refuse(message, exc=None)`** local to `run_filing_change`; the five refusal
   sites are one line each.
6. **`diff_paragraphs`** computes `comparable_left/right` and the word sets once
   (`_comparable_words` on the comparable form; `_words` composes it); `_aligned`
   takes the word sets and reads the DP pass's likeness from a matrix;
   `_rejoin_moved` computes each added change's words before the loop.
7. **`_say`** is overloaded (`str -> str`, `None -> None`), each KINDS entry is a
   plain `_say(q, ...)`, and `misattributed` is `_say_other`.
