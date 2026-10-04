# 08 — One operating-company rule for lookups and filing changes

**What to build:** The rule that a fund, BDC or note is not an operating company (ADR 0001, 0002) is written in three places: `sec_facts.SecFactLookup.get_financials`, `filing_change.run_filing_change` and `graph/spec_turn._not_operating_once`. Lookups exempt a snapshot member from the SEC-title check (the snapshot already judged it); filing change applies the check to everyone. Today no snapshot member's SEC title trips the check (all 5,161 were checked on 2026-10-04), so the difference is latent.

Add one `require_operating(cik, title, listed_ciks)` in `universe.py` that raises `IneligibleIssuerError` (with the message lookups use today): a CIK on the ineligible list is never operating; a snapshot member is otherwise operating, since the snapshot already applied the membership rule; any other company is judged by its SEC title. `sec_facts.SecFactLookup.get_financials` and `filing_change.run_filing_change` both call it, filing change catching it as it catches `CompanyNotFoundError`. `graph/spec_turn._not_operating_once` keeps only the wording it still needs.

## Question

Should a filing change exempt snapshot members from the SEC-title check, as lookups do? (The alternative is lookups applying it to members too, which today changes nothing either.)

## Decision

2026-10-04: a filing change exempts snapshot members from the SEC-title check, as lookups do. The snapshot applies the fuller membership rule (ADR 0001), so one rule holds everywhere. No snapshot member's SEC title trips the check today, so no answer changes.

**Acceptance:** both workflows call `require_operating`; a test shows a snapshot member whose SEC title reads like a note listing is still compared by a filing change, and a non-member with such a title is refused; `uv run python scripts/compare_answers.py` reports `0 of N conversations differ`.

Found by the 2026-10-04 simplify review of master (#67), which left it out as larger than a cleanup.

Spec: ADR 0001, ADR 0002.

**Blocked by:** None — can start immediately

**Status:** ready-for-agent
