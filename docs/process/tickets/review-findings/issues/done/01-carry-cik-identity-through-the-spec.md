# 01 — Carry CIK identity through the analysis spec

**What to build:** An analysis spec holds CIKs for every named company before any provider call, as `CONTEXT.md` ("Resolved means CIKs") and ADR 0005 ("A spec must be resolved before any provider call") say. Today `graph/analysis_spec._resolve_company` keeps `cik=""` for a company the ranking snapshot does not hold, and `_base_tasks` / `calendar_groups` compile `company.query` (the analyst's text) even when a CIK was resolved, so the facts port re-resolves text per cell.

Resolve a snapshot miss through SEC identity (the runtime's `filings` port has the ticker map), keep an unresolvable name as a typed miss row (ADR 0002: other compare rows stay), and compile tasks by CIK.

Found by the 2026-10-01 PRD/ADR review (Standards S2). A trial that only compiled `company.cik or company.query` regressed the recorded demo (the four-quarter comparison lost its quarters; charts and traces changed), because per-company state is keyed on the query text. The work is:

- Key per-company state on CIK, not `company.query.casefold()`: `PeriodSelection.company_report_dates`, `calendar_groups`, `materialize_period_dates`, `_fill_identity` and the trend/overview helpers in `graph/spec_turn.py`, and `_companies_named_in` in `request_wording.py`.
- Name a failed cell from the spec's resolved company, not from the task's query string.
- Key `evidence_store.fact_evidence_id` on CIK, so "Google" and "GOOGL" share evidence (review smell: evidence keyed on query text).
- Bundle the identity that travels positionally through `services/fact_selector.py` (`company_name, ticker, cik`, plus `currency`) into one type while those signatures are open (review smell: data clump).
- Teach the test fakes that answer by company name to accept CIKs, or give them a small name→CIK map.

Spec: `CONTEXT.md` (Analysis spec), ADR 0002, ADR 0005, `docs/design.md` ("identity is carried as SEC CIK").

**Blocked by:** None — can start immediately

**Status:** done

## Answer

Every company in a spec is pinned to its CIK before any provider call. A name the market snapshot leaves out is resolved through SEC's ticker map (`spec_turn.sec_identity`, the same resolution the facts lookup uses), so Tesla on the recorded demo is TSLA from the start; a name neither knows stays a name, and its cells say it was not found. `ResolvedCompany.key` (CIK, or the unknown name) keys every per-company state: `company_report_dates`, `calendar_groups`, the period dating, the answer notes, the quarter before and the year earlier. `ResolvedCompany.handle` (the same) is what tasks carry (`CompiledTask.issuers`, renamed from `company_queries`) and what every provider is asked for, so evidence ids are by CIK and "Google" and "GOOGL" share evidence (tested). A failed cell is named from the spec by its handle (`_fill_identity`), and `_identity_from_rows`, which named a snapshot miss from its filings after the fact, is gone. The identity that travelled positionally through `fact_selector` and the `sec_facts` helpers is one `FactOwner`. Test fakes that answer by name read the CIK back through `tests/helpers.named_by_cik`. `_companies_named_in` matches the analyst's words, not state, and keeps the query. What the recorded runtime shows was compared across 244 conversations before and after: tables, chips, notes and evidence are unchanged except one intended fix (a company SEC knows but the snapshot lacks now reads "Not in the market snapshot" for market cap, price and P/E, not "Company not found" or its CIK in a message); trace headers name companies by their short name ("NVIDIA", not "NVDA"), as ranked lookups already did, and trace inputs show the CIK each lookup asked for. The rules planner scores the same on all 219 evaluation cases.
