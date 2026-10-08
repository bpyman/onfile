# Build facts and derivation parts in one place each

From a parallel `/simplify` review of the whole codebase (7 October 2026): seven read-only reviewers, one per area plus one across areas; 84 findings, consolidated into 12 tickets that never share a file. Cleanup only: **no behaviour may change**.

**Files (this ticket only):** `src/financial_analyst_agent/services/fact_selector.py`, `src/financial_analyst_agent/services/stock_splits.py`, `src/financial_analyst_agent/services/fiscal_periods.py`, `src/financial_analyst_agent/universe.py`

**What to build:** Building a FinancialFact, mapping a fact to a DerivationPart, and testing for a standalone quarter are each written out more than once in the services layer. A new provenance field has to be added in three places, and missing one silently leaves derived facts different from reported ones. This is cleanup only: every fact, derivation and industry group must stay the same.

1. **`FinancialFact(...)` built by hand three times** (fact_selector.py:125-156 `_build_financial_fact`, 388-411 `_derived_fact`, 641-671 `derive_trailing_year`), each copying the same dozen owner and provenance fields. Add one `_fact(anchor: FactRecord, metric, owner, source_url, *, value, start_date, directly_reported, derivation=None, year_earlier=None)` and call it from all three. `_build_financial_fact` reduces to its start_date check plus that call. Keep `currency=owner.currency.upper()` and `source=SEC_XBRL`.
2. **The quarter-length band in two places.** stock_splits.py defines `_QUARTER_DAYS = (70, 110)` (27) and re-implements the standalone-quarter test in `series_agrees` (147-151), which fact_selector already owns (`_MIN_QUARTER_DAYS`, `MAX_QUARTER_DAYS`, `_is_standalone_quarter_duration`, 44-46, 59-63). Rename `_is_standalone_quarter_duration` to the public `is_standalone_quarter(start, end)`, call it from `series_agrees`, and delete `_QUARTER_DAYS`. First confirm that the two bands and their inclusive or exclusive ends agree today. If they do not, stop and report the difference instead of changing either.
3. **DerivationPart mapping twice** (fiscal_periods.py:274-287, 320-321, 365-367, 423-435). `gross_profit_from_components` defines a nested `part()` that copies `_derivation_part` and adds `metric`; the other two callers write `.model_copy(update={"metric": ...})`. Give `_derivation_part` a `metric: str | None = None` keyword, delete the nested `part`, and call `_derivation_part(fact, metric=fact.metric.value)` at all three sites, with `metric=fact.metric.value if name_parts else None` in `sum_of_components`.
4. **One hard-coded alias in the industry matcher** (universe.py:308-310, 441-446). `resolve_industry_group` special-cases the literal `pattern == "Oil & Gas"` as a prefix match, because the alias convention marks prefixes only with a trailing " -". Give the alias table a general prefix marker, such as a trailing "*" or `(text, prefix: bool)` tuples. Write the oil aliases with it and drop the branch. Prefix matching already covers the equality case. The matched industries for every alias must stay the same; check this with a test that lists each group's members before and after.

Do not change `select_quarterly_fact`'s signature or remove `select_quarterly_fact_with_filing_fallback`; sec_facts.py (ticket 01) still calls them as they are.

**Acceptance:** all tests pass; ruff and mypy are clean; `uv run python scripts/compare_answers.py` reports `0 of N conversations differ`.

**Findings covered:**
- facts/simplification: FinancialFact built by hand three times in fact_selector
- facts/reuse: stock_splits redefines the standalone-quarter band fact_selector owns
- facts/reuse: gross_profit_from_components nested part() duplicates _derivation_part
- facts/altitude: resolve_industry_group special-cases the literal 'Oil & Gas'

**Acceptance:** `uv run python -m pytest` passes; ruff and mypy are clean; `uv run python scripts/compare_answers.py` reports `0 of N conversations differ`; phrase coverage stays 555 of 555. If a step would change behaviour, or needs a file outside this ticket's list, leave it and say so in the Answer.

**Blocked by:** None — can start immediately

**Status:** resolved

## Answer

Shipped 8 October 2026. Cleanup only: 2,378 tests pass (six added), ruff and mypy are clean, `uv run python scripts/compare_answers.py` reports `0 of 893 conversations differ from HEAD` (which replays every phrase-coverage case, so coverage stays 555 of 555).

1. **One fact builder.** `fact_selector._fact(anchor, metric, owner, source_url, *, value, start_date, directly_reported, derivation=None, year_earlier=None)` builds every `FinancialFact` the module returns: the owner's name, ticker, CIK and `currency.upper()`, the anchor's end date, form, filed date, accession, taxonomy and concept, `source=SEC_XBRL`. `_build_financial_fact` is its start-date check plus the call (the anchor is the selected record); `_derived_fact` anchors on the longer record and `derive_trailing_year` on the year-to-date record, as before. The trailing year no longer passes `source` explicitly; `_fact` sets it. Two tests pin that a derived quarter and a trailing year carry the owner's and the anchor filing's fields exactly as a reported fact would.
2. **One quarter band.** Checked first: `fact_selector` read `70 <= days <= 110` and `stock_splits` read `_QUARTER_DAYS[0] <= days <= _QUARTER_DAYS[1]` with `(70, 110)`, both inclusive, both skipping a record with no start. `_is_standalone_quarter_duration` is now the public `is_standalone_quarter(start, end)`; `series_agrees` calls it and `_QUARTER_DAYS` is deleted. No import cycle: `stock_splits` is imported only by `sec_facts`, and `fact_selector` imports nothing from it. A test pins the band's ends and that the split cross-check reads only quarter-length records.
3. **One derivation-part mapping.** `_derivation_part(fact, *, metric=None)` sets `metric` directly; the nested `part()` in `gross_profit_from_components` and the two `.model_copy(update={"metric": ...})` sites are gone. `sum_of_components` passes `metric=fact.metric.value if name_parts else None`. A test pins the parts' metrics for a named sum (bank revenue), an unnamed one (depreciation plus amortization) and the rebuilt revenue, and that each part keeps its provenance.
4. **A general prefix marker.** An `INDUSTRY_GROUP_ALIASES` value ending in `*` names every snapshot industry starting with the text before it (`_PREFIX`); the trailing `" -"` entries became `" -*"` and the oil entries `"Oil & Gas*"`, so `resolve_industry_group`'s `pattern == "Oil & Gas"` branch is deleted and `_names(pattern, industry)` is the one test. `test_each_everyday_group_name_lists_the_same_snapshot_industries` pins every alias's members against the committed snapshot, captured before the change and unchanged after it.

Noticed, not changed (it would be a behaviour change outside a cleanup ticket): the alias key `"oil and gas"` is never looked up, because `_normalize_group` singularises "gas" to "ga" ("oil and ga"). It does no harm today because the planner writes the industry as "oil & gas" (`test_oil_and_gas_is_one_industry_in_a_ranking`), and the pin test records it as resolving to nothing. A later ticket could delete the key or stop the singulariser at words ending in "as".
