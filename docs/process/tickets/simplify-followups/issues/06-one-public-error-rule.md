# 06 — One rule for which errors a visitor may read

**What to build:** Six places decide whether an error's own text is safe to show a visitor: `api.public_error_message`, `filing_change._public_message`, `graph/spec_turn.resolve_request` (the `public` check), `turn` (the essay path), `filing_change` (the summary banner) and `presentation._SOURCE_ERROR_CODES`. They trust different sets: the API shows quota and runtime errors, filing change shows refusals and company lookups, the essay path refusals only.

Once the question below is settled: a `public` class flag on `FinancialAnalystError` and one `visitor_message(exc, fallback)` helper used by every site.

## Question

Which errors may a visitor read verbatim, everywhere? Today `ProviderRefusal`, `CompanyNotFoundError`, `AmbiguousCompanyError`, `SessionQuotaError` and `RuntimeMismatchError` are each shown in some paths and not others. One answer for all of them, or a reason a path should differ.

Found by the 2026-10-04 simplify review of master (#67), which left it out as larger than a cleanup.

Spec: ADR 0006 (what the window shows).

**Blocked by:** None — can start immediately

**Status:** needs-info
