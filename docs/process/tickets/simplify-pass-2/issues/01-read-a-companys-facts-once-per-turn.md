# Read a company's SEC facts once per turn

From a parallel `/simplify` review of the whole codebase (7 October 2026): seven read-only reviewers, one per area plus one across areas; 84 findings, consolidated into 12 tickets that never share a file. Cleanup only: **no behaviour may change**.

**Files (this ticket only):** `src/financial_analyst_agent/sec_facts.py`, `src/financial_analyst_agent/providers/sec/cache.py`, `src/financial_analyst_agent/runtime.py`

**What to build:** `SecFactLookup` (sec_facts.py) already has a per-turn cache, but many lookups go around it, and one company's parse is split across several dicts. Tidy the facts path so each company is read, parsed and merged once per turn. This is cleanup only: no fact, answer, note, refusal or trace may change.

1. **Component and check records go around `_metric_records` (sec_facts.py:585-595).** `parse_company_facts` / `parse_company_facts_for_concepts` run again at 847, 853, 879, 927, 1061, 1155, 1231 and 1241: `_plausible_revenue` (gross profit and cost of revenue), `_revenue_checks` (about a dozen concepts), `_with_diluted_shares` / `_on_latest_basis` (shares and split ratios), and the gross-profit fallback, which parses REVENUE again. Change the cache key from (cik, metric, unit) to (cik, concepts tuple, unit). Have the module helpers take a `records(concepts_or_metric, unit)` callable bound to `self` and the cik, instead of the raw payload plus a parse function. Return the cached lists without the defensive `list(...)` copies, since no caller extends them (`_with_predecessor_facts` already builds `[*records, *extra]`), and delete the stale "Callers extend the lists" comment.
2. **A memory hit still reads and gunzips the digest file.** `_parsed_from_disk` (sec_facts.py:621-631) calls `read_facts_digest` (cache.py:212-227) before it checks `_PARSED_FACTS`. Split the cache API the way `company_facts_stamp` already splits the facts file: add `facts_digest_stamp(cik)` (freshness check plus stat), look the stamp up in `_PARSED_FACTS`, and read and decompress the file only on a miss.
3. **`_filings(cik)` is rebuilt on every call (sec_facts.py:495-540, called at 690, 960 and 982).** Memoise it in `self._filings_by_cik`; every input it reads is already cached for the turn. Factor the merge-then-sort that `_filings` (509-515) and `_with_facts_filings` (532-540) both write out into one `_merged(filings, extra)` helper.
4. **One parse is spread over three dicts plus a 404 sentinel (sec_facts.py:396-406, 597-619, 940-944).** Replace `_company_facts_by_cik`, `_fiscal_labels_by_cik` and `_facts_filings_by_cik` with `self._parsed_by_cik: dict[str, _ParsedFacts]`, filled through the existing `_remembering_failure(f"facts:{cik}", ...)`, and read `.concepts`, `.labels` and `.filings` from it. Remove the None sentinel and the setdefault side effect in `_fiscal_labels`. First confirm that every caller branches only on `status_code == 404` and never on the error message.
5. **`get_financials` (sec_facts.py:670-799) is about 130 lines.** Hoist `predecessor`, `name`, `owner` and `targets` above the per-CIK loop. Compute `in_xbrl = self._period_in_xbrl(...)` once per failed period; it currently runs at 750 and again at 766. Extract the pending / year-only step-back walk into a `_first_available(...)` helper that returns the fact or the last error.
6. **The candidate filings are chosen twice (sec_facts.py:301-346).** `_select_or_derive_in_unit` computes `quarterly`, then calls `select_quarterly_fact_with_filing_fallback`, which computes the same list again and returns a one-element tuple. Loop over `quarterly` and call `select_quarterly_fact` per filing, as the instant and derive loops below already do. Keep the wrapper's error semantics exactly: the error raised is the **last** filing's `UnsupportedQuarterlyFactError`, not the first. Leave fact_selector.py unchanged (another ticket owns it); the wrapper stays for its tests.
7. **Cache file names are spelled out about a dozen times (cache.py:33, 205, 219, 237, 248, 264, 279, 295, 302, 374; runtime.py:277-280).** Add module-level `facts_file(cik)`, `digest_file(cik)`, `missing_file(cik)` and `submissions_file(cik)` in cache.py, keep `_COMPANY_FILE` next to them, and use them at every site, including `company_needs_warming` in runtime.py.
8. **Snapshot lookups in runtime.py (186-209, 241-251, 342-378).** Add `_snapshot_version(path) -> int` (the default path plus `stat().st_mtime_ns`) and use it in `_snapshot_maps` and `_snapshot_ranking`. Have `_member_ticker` take the `SnapshotRanking` that the caller already holds. Add `_facts_lookup(client, path, ranking) -> SecFactLookup` and use it in both `recorded_runtime` and `live_runtime`.

**Acceptance:** all tests pass; ruff and mypy are clean; `uv run python scripts/compare_answers.py` reports `0 of N conversations differ`. A profile of a warm 10-company ranking shows one digest read per cold company and no `parse_company_facts` calls on cache hits.

Not in this ticket: walking the payload once for `fiscal_labels` and `filings_from_company_facts`; it is left for a measured follow-up.

**Findings covered:**
- facts/efficiency: component and check records parsed again around _metric_records (sec_facts.py:585-595)
- facts/efficiency: _parsed_from_disk reads and gunzips the digest before checking _PARSED_FACTS (sec_facts.py:621-631, cache.py:212-227)
- facts/efficiency: _filings(cik) rebuilt on every call; duplicated merge-then-sort (sec_facts.py:495-540)
- facts/simplification: one parse spread over three per-cik dicts plus a 404 sentinel (sec_facts.py:396-406, 597-619)
- facts/simplification: get_financials loop-invariant work and _period_in_xbrl evaluated twice (sec_facts.py:670-799)
- facts/simplification: _select_or_derive_in_unit computes candidate filings twice (sec_facts.py:301-346)
- facts/simplification: cache per-company file names spelled at about a dozen sites (cache.py, runtime.py:277-280)
- turn/simplification: runtime _snapshot_maps/_snapshot_ranking repeat the version lookup; _member_ticker re-reads the ranking; SecFactLookup wiring copied (runtime.py)

**Acceptance:** `uv run python -m pytest` passes; ruff and mypy are clean; `uv run python scripts/compare_answers.py` reports `0 of N conversations differ`; phrase coverage stays 555 of 555. If a step would change behaviour, or needs a file outside this ticket's list, leave it and say so in the Answer.

**Blocked by:** None — can start immediately

**Status:** ready-for-agent
