# 08 — A fund beside a company is left out, with a note saying so

**What to build:** Decided in `rules-to-review.md` (2026-10-07, probe-round-3-gaps 03). `SPY and Apple revenue` shows two rows: SPY reading "Company not found" (live: "not an operating company") and Apple's revenue, with the note "Showing SPDR S&P 500 ETF TRUST for “SPY”", which reads as if the fund were shown. The README says a fund beside a company is left out with a note. Leave a name the snapshot marks as not an operating company (a fund, an ETF, a trust; ADR 0001's ineligible issuers) out of the table, and say so: "SPY (SPDR S&P 500 ETF Trust) is a fund, not an operating company, so it is left out." A name no company matched keeps its note as now. A fund asked alone is still refused.

**Acceptance:** on the recorded runtime, `SPY and Apple revenue` shows Apple's row only, intent `lookup`, and that note; `SPY revenue` alone is refused as now. `uv run python -m pytest` passes; `uv run python scripts/compare_answers.py` names every conversation whose answer changes, and each change is intended.

**Blocked by:** None — can start immediately

**Status:** resolved

## Answer

Shipped 2026-10-07. A fund named beside an operating company is left out of the table with a note, in the shared resolution layer both planners pass through (ADR 0010, 0011): `drop_funds` in `graph/spec_turn.py` runs after `resolve_spec`, beside `drop_annual_filers`, and leaves out a company whose CIK is on the ineligible list or whose SEC title names an instrument (`sec_identity_is_operating`), or, when SEC did not identify it (the recorded runtime), whose ticker is on the ineligible list. The dropped (ticker, SEC name) pairs ride on `CompiledAnalysis.funds` and `annotate_analysis` puts `fund_note` (`answer_notes.py`) first: "SPY (SPDR S&P 500 ETF Trust) is a fund, not an operating company, so it is left out." Two or more read "… are funds, not operating companies, so they are left out." SEC's shouted name is set in prose (a word of up to three letters, or four with no vowel, is an acronym and keeps its case). A fund asked alone is kept, so `SPY revenue` is refused as before. The rules planner no longer says "Showing SPDR S&P 500 ETF TRUST for 'SPY'" for an ineligible ticker.

On the recorded runtime `SPY and Apple revenue` is Apple's lookup (a fact card) with that note; `SPY, Apple and Microsoft revenue` is the two-company comparison with the note; `add SPY` to Apple's revenue keeps Apple's lookup and adds the note. compare_answers: `3 of 266 conversations differ`, all intended: `SPY and Apple revenue` (two rows, SPY "Company not found", and the "Showing" note before; Apple's lookup with the fund note now) and the two conversations added for this ticket (`SPY, Apple and Microsoft revenue`, `Apple revenue` / `add SPY`). ADR 0002 and CONTEXT.md's "Ineligible issuer" entry state the rule.
