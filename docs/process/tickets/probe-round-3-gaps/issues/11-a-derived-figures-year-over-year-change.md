# 11 — EBITDA's year-over-year change goes missing for some companies, silently

**What to build:** Found reviewing ticket 07 (7 October 2026). On the recorded runtime, `AMD EBITDA over the last 4 quarters year over year` and `Merck EBITDA over the last 4 quarters year over year` show four quarters of EBITDA with no year-over-year change at all, and no note; Apple, Microsoft and Nvidia show the change. Live, `How did AMD's EBITDA change over the past year?` is the same. EBITDA is a formula (operating income plus depreciation and amortization, ADR 0008), and its change is the formula over its components' comparatives (ADR 0009); a derived quarter's comparative is the same subtraction over each part's own comparative. One of those comparatives is evidently missing for AMD and Merck.

Find which, from the recorded facts. Then either compute the change where the filings hold what it needs (a component's comparative from another filing, as ADR 0009 allows when a filing reports none: the year-earlier quarter as first filed), or, where they do not, show the row's change as unavailable with a note saying why, as a missing quarter says so. A change never goes missing without a word.

**Acceptance:** AMD's and Merck's EBITDA year over year on the recorded runtime each show the change or say why it is missing; Apple's is unchanged; a unit test pins the case found. `uv run python -m pytest` passes; `uv run python scripts/compare_answers.py` names every conversation whose answer changes, and each change is intended.

**Blocked by:** None — can start immediately

**Status:** ready-for-agent
