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

**Status:** resolved

## Answer

2026-10-04: `universe.require_operating(cik, title, listed_ciks)` is now the one rule. A CIK on the ineligible list is never operating. A snapshot member is otherwise operating. Any other company is judged by its SEC title. It raises `IneligibleIssuerError` with the wording lookups used.

- `SecFactLookup.get_financials` calls it with its listed-ticker map.
- `run_filing_change` calls it right after resolving the company, inside the same `try` that catches `CompanyNotFoundError`. A refused filing change now carries the `ineligible_issuer` refusal, and its wording is the lookup's.
- Filing change reads snapshot members from the runtime's ranking, through a new `RankingPort.member_ciks()`. Without a ranking, every company is judged by its title.
- `graph/spec_turn._not_operating_once` was already gone (ticket 03 removed it), so nothing was left to trim there.
- Tests: filing change compares a member whose SEC title reads like a note listing, and refuses a non-member with the same title. A table test covers `require_operating` directly. The test where a member is later listed ineligible now patches `universe`, where the list is read.
- `scripts/compare_answers.py`: `0 of 244 conversations differ from HEAD`.
