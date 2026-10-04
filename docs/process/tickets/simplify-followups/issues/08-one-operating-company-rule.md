# 08 — One operating-company rule for lookups and filing changes

**What to build:** The rule that a fund, BDC or note is not an operating company (ADR 0001, 0002) is written in three places: `sec_facts.SecFactLookup.get_financials`, `filing_change.run_filing_change` and `graph/spec_turn._not_operating_once`. Lookups exempt a snapshot member from the SEC-title check (the snapshot already judged it); filing change applies the check to everyone. Today no snapshot member's SEC title trips the check (all 5,161 were checked on 2026-10-04), so the difference is latent.

Once the question below is settled: one `require_operating(...)` in `universe.py` that raises `IneligibleIssuerError`, used by both workflows.

## Question

Should a filing change exempt snapshot members from the SEC-title check, as lookups do? (The alternative is lookups applying it to members too, which today changes nothing either.)

Found by the 2026-10-04 simplify review of master (#67), which left it out as larger than a cleanup.

Spec: ADR 0001, ADR 0002.

**Blocked by:** None — can start immediately

**Status:** needs-info
