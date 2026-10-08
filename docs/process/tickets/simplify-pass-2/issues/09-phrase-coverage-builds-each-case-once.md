# Build each phrase-coverage case from one set of arguments

From a parallel `/simplify` review of the whole codebase (7 October 2026): seven read-only reviewers, one per area plus one across areas; 84 findings, consolidated into 12 tickets that never share a file. Cleanup only: **no behaviour may change**.

**Files (this ticket only):** `src/financial_analyst_agent/phrase_coverage.py`, `scripts/compare_answers.py`

**What to build:** In phrase_coverage.py, every reading case passes the same four arguments twice: once to `_expected(...)` and once to `_reads(...)`. This happens at 749-750, 795-796, 850-865, 876-886 and 943-985. A typo between the two would make the report's "Expected" column disagree with what is actually checked. `cases()` is about 200 lines, mostly copied loops, and 37 of compare_answers.py's hand-written conversations are copies of its questions.

1. **One builder per case.** Add `_reading(case_id, group, turns, tickers, metrics, period, comparison) -> PhraseCase` that builds both `expected` and `check` from one set of arguments, and use it at every reading site. Loop the three same-shaped tables once: `for prefix, group, table in (("idiom", "Idioms beside a company", IDIOM_QUESTIONS), ("word use", ...), ("segment", ...))`. Merge the WINDOW_PHRASES loop (questions built as `f"Apple revenue {p}"`) and the WINDOW_QUESTIONS loop (questions as written) into one. Case ids, groups, order and expected text stay the same.
2. **Three check builders for one rule (107-116, 214-223).** `_companies(*tickers, metrics, count)` is exactly `_reads(frozenset(tickers), frozenset(metrics), ("last_n_quarters", count), None)`; make it a thin call or drop it from FOLLOW_UPS. Replace `_year_over_year` and `_sequential` with one `_shows(comparison: str) -> Check`. Add `_planned(seen) -> bool`, carrying the existing comment ("A fact the recording lacks still planned the right metric"), and use it at all 12 sites that write `seen.outcome in ("answer", "no_data")`.
3. **Replay the phrase cases in compare_answers (scripts/compare_answers.py:37-128, 161-165).** In `dump`, also replay `case.turns` for each `phrase_coverage.cases()` under a `phrase:<case_id>` key, and delete the 37 EXTRA conversations that copy those questions, keeping only conversations neither source has. A comparison against a ref without this change would list the new keys as differing, so skip names missing from `before`, and say how many were skipped. Land this step as its own commit.

The phrase-coverage report must stay the same.

**Acceptance:** all tests pass; ruff and mypy are clean; the regenerated phrase coverage report is byte for byte the same (555 of 555); `uv run python scripts/compare_answers.py --against master` reports `0 of N conversations differ` with the new phrase keys skipped, and N grows by the number of phrase cases on the next run.

**Findings covered:**
- eval/simplification: every reading case builds _expected and _reads from the same four arguments; copied loops in cases()
- eval/simplification: _companies duplicates _reads; _year_over_year and _sequential are one function; 'planned an answer' spelled out at 12 sites
- eval/altitude: compare_answers EXTRA copies 37 phrase-coverage conversations

**Acceptance:** `uv run python -m pytest` passes; ruff and mypy are clean; `uv run python scripts/compare_answers.py` reports `0 of N conversations differ`; phrase coverage stays 555 of 555. If a step would change behaviour, or needs a file outside this ticket's list, leave it and say so in the Answer.

**Blocked by:** None — can start immediately

**Status:** ready-for-agent
