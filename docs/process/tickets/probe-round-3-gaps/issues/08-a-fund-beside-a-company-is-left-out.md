# 08 — A fund beside a company is left out, with a note saying so

**What to build:** Decided in `rules-to-review.md` (2026-10-07, probe-round-3-gaps 03). `SPY and Apple revenue` shows two rows: SPY reading "Company not found" (live: "not an operating company") and Apple's revenue, with the note "Showing SPDR S&P 500 ETF TRUST for “SPY”", which reads as if the fund were shown. The README says a fund beside a company is left out with a note. Leave a name the snapshot marks as not an operating company (a fund, an ETF, a trust; ADR 0001's ineligible issuers) out of the table, and say so: "SPY (SPDR S&P 500 ETF Trust) is a fund, not an operating company, so it is left out." A name no company matched keeps its note as now. A fund asked alone is still refused.

**Acceptance:** on the recorded runtime, `SPY and Apple revenue` shows Apple's row only, intent `lookup`, and that note; `SPY revenue` alone is refused as now. `uv run python -m pytest` passes; `uv run python scripts/compare_answers.py` names every conversation whose answer changes, and each change is intended.

**Blocked by:** None — can start immediately

**Status:** ready-for-agent
