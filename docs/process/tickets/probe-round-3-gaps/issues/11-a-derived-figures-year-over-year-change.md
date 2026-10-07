# 11 — EBITDA's year-over-year change goes missing for some companies, silently

**What to build:** Found reviewing ticket 07 (7 October 2026). On the recorded runtime, `AMD EBITDA over the last 4 quarters year over year` and `Merck EBITDA over the last 4 quarters year over year` show four quarters of EBITDA with no year-over-year change at all, and no note; Apple, Microsoft and Nvidia show the change. Live, `How did AMD's EBITDA change over the past year?` is the same. EBITDA is a formula (operating income plus depreciation and amortization, ADR 0008), and its change is the formula over its components' comparatives (ADR 0009); a derived quarter's comparative is the same subtraction over each part's own comparative. One of those comparatives is evidently missing for AMD and Merck.

Find which, from the recorded facts. Then either compute the change where the filings hold what it needs (a component's comparative from another filing, as ADR 0009 allows when a filing reports none: the year-earlier quarter as first filed), or, where they do not, show the row's change as unavailable with a note saying why, as a missing quarter says so. A change never goes missing without a word.

**Acceptance:** AMD's and Merck's EBITDA year over year on the recorded runtime each show the change or say why it is missing; Apple's is unchanged; a unit test pins the case found. `uv run python -m pytest` passes; `uv run python scripts/compare_answers.py` names every conversation whose answer changes, and each change is intended.

**Blocked by:** None — can start immediately

**Status:** resolved

## Answer

Shipped 7 October 2026. The finding, from the recorded facts: no comparative is missing; EBITDA itself is, for every quarter. On the recorded runtime both questions showed four rows reading "Missing fact" (ticket 07's Answer said so for AMD), with no note saying which part was lacking. The cassette, recorded from live EDGAR with every concept the catalog reads, holds for AMD no cash-flow depreciation and amortization line and `Depreciation` only for the fiscal year (its 10-Ks), so the depreciation-plus-amortization fallback (ADR 0008) has no quarter either; for Merck it holds no `OperatingIncomeLoss` at all and `AmortizationOfIntangibleAssets` only for the year. By how the cassette was recorded, live EDGAR reads the same way (inferred, not observed). The ticket's premise is recorded in `docs/process/rules-to-review.md` (probe-round-3-gaps 11).

So the ticket's second branch: where the filings do not hold what the figure needs, the row says why. In `compare_metrics` (`turn.py`), which every planner's lookup and comparison passes through, a formula's remaining components are read even after one is missing, and the missing ones ride on the row as `TableRow.missing_components` (the reason stays `missing_fact`; a plain metric names none). `missing_component_notes` (`answer_notes.py`), wired into `annotate_analysis` beside the fund and annual-filer notes, says which part was not found:

- `AMD EBITDA over the last 4 quarters year over year`: four "Missing fact" rows and "Advanced Micro Devices' EBITDA is missing: no standalone quarterly depreciation and amortization was found in its filings, which EBITDA needs."
- `Merck EBITDA over the last 4 quarters year over year`: four "Missing fact" rows and "Merck's EBITDA is missing: no standalone quarterly operating income or depreciation and amortization was found in its filings, which EBITDA needs."
- `Apple EBITDA over the last 4 quarters year over year` is unchanged: four quarters, each with its year-over-year change.

Companies lacking the same parts of a metric share one note ("Operating margin is missing for Pfizer and Merck: ..."); a company with the figure for other quarters in the window names the quarters it lacks ("Microsoft's operating margin is missing for Jun 30, 2024: no standalone quarterly operating income or revenue was found for that quarter, ..."); a newest quarter SEC's structured data lacks, which the newer-filing banner already explains, gets no second note. The note says what was not found rather than what the company reports: a quarter can be beyond what is on file, or the line tagged under a concept the catalog does not read.

Tests: `tests/unit/test_market_and_balance_sheet_figures.py` pins the row (one part missing, every part missing, a plain metric); `tests/unit/test_filers_rankings_and_narrowing.py` pins the notes (one part, two parts, some quarters, two companies, a plain missing fact, the newer-filing case); `tests/test_new_figures.py` pins AMD, Merck, Apple and the lone `AMD EBITDA` on the recorded runtime. README's derived-figures row and ADR 0008 say the rule.

compare_answers: `8 of 275 conversations differ from HEAD`, each gaining the note where a derived figure's part was not found, and nothing else: `h2_msft_most_recent_twelve` (Microsoft's operating margin for Jun 30, 2024, a blank row before), `h2_tmo_abt_full_names` and `h2_what_about_period` (Thermo Fisher's gross margin, no gross profit found), `h3_abt_gm_previous_seven` (Abbott's gross margin for Jun 30, 2026, a blank row before), `h3_switch_metric` (Pfizer's and Merck's operating margin, one note), `ho_orcl_overview` (Oracle's gross margin in the overview table), `How did AMD's EBITDA change over the past year?` and the conversation added here, `Merck EBITDA over the last 4 quarters year over year`.

For a person with live data: whether AMD tags its cash-flow depreciation and amortization under a concept the catalog does not read. If it does, reading that concept would make its EBITDA computable, and its change with it.

