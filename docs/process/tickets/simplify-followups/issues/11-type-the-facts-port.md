# 11 — Type the facts port's optional methods and the facts it returns

**What to build:** The turn reaches the facts port's optional methods with `getattr` (`list_quarterly_report_dates`, `fiscal_periods`, `files_quarterly`, `display_name` in `graph/spec_turn.py` and `filing_change.py`) and reads typed `FinancialFact` fields with `getattr` (`year_earlier`, `newer_filing_end`, `diluted_shares` in `turn.py`, and `market_cap` on ranked companies). The probes exist because test fakes return `SimpleNamespace` objects without those fields.

Declare the four methods on `contracts.FactsPort` and call them directly; read the fields directly. Update the test fakes: give them the methods (or a shared fake base in `tests/helpers.py`) and the fields (about 40 fakes).

**Acceptance:** no `getattr` on `runtime.facts` or on a fact's typed fields remains in `src/`; `uv run python scripts/compare_answers.py` reports `0 of N conversations differ`: what the recorded demo answers does not change.

Found by the 2026-10-04 simplify review of master (#67), which left it out as larger than a cleanup.

**Blocked by:** None — can start immediately

**Status:** resolved

## Answer

`contracts.FactsPort` declares `list_quarterly_report_dates`, `fiscal_periods`, `files_quarterly` and `display_name`. `graph/spec_turn.py`, `filing_change.py` and `EvidenceCachedFacts` call them directly; `EvidenceCachedFacts` takes a `FactsPort` and forwards each one. `turn.py` reads `year_earlier`, `diluted_shares` and `newer_filing_end` off `FinancialFact` and `market_cap` off `UniverseCompany`, and `_compare_row`, `_rank_and_lookup_row` and `_with_rank_identity` are typed to match.

Test fakes subclass `tests/helpers.FakeFacts`, which lists no quarters, knows no fiscal periods, treats every company as a 10-Q filer and keeps the name it is given. 44 fake classes across 28 files now subclass it. This matters because `spec_turn` swallows exceptions from these calls: a fake without the methods would have raised `AttributeError` and silently skipped the step. The robustness test for a wrapped port without `display_name` now checks the fallback name, because the port requires the method.

No `getattr` on `runtime.facts` or on a fact's typed fields is left in `src/`. `scripts/compare_answers.py`: 0 of 244 conversations differ.
