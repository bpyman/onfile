# 06 — One rule for which errors a visitor may read

**What to build:** Six places decide whether an error's own text is safe to show a visitor: `api.public_error_message`, `filing_change._public_message`, `graph/spec_turn.resolve_request` (the `public` check), `turn` (the essay path), `filing_change` (the summary banner) and `presentation._SOURCE_ERROR_CODES`. They trust different sets: the API shows quota and runtime errors, filing change shows refusals and company lookups, the essay path refusals only.

Add a `public` class flag on `FinancialAnalystError`, set on the five errors the decision below names, and one `visitor_message(exc, fallback)` helper: the error's own text when it is public, else the site's fallback. Every site above uses it, each keeping its own fallback (the generic failure message, "couldn't read the filings", the SEC-unavailable message, the essay and summary messages). `presentation._SOURCE_ERROR_CODES` reads the same flag through the code.

## Question

Which errors may a visitor read verbatim, everywhere? Today `ProviderRefusal`, `CompanyNotFoundError`, `AmbiguousCompanyError`, `SessionQuotaError` and `RuntimeMismatchError` are each shown in some paths and not others. One answer for all of them, or a reason a path should differ.

## Decision

2026-10-04: all five are written for the visitor (a company name, a quota, a refusal reason), so all five may be shown verbatim everywhere: `ProviderRefusal`, `CompanyNotFoundError`, `AmbiguousCompanyError`, `SessionQuotaError` and `RuntimeMismatchError`. Every other error gets the site's generic message, as today. Most of these errors cannot reach the paths that do not show them today, so few answers change; any that do are named in the Answer.

**Acceptance:** one `visitor_message` decides at every site; tests show each of the five errors' own text at each site that can meet it, and a generic message for any other error; `uv run python scripts/compare_answers.py` shows no difference, or only ones named in the Answer.

Found by the 2026-10-04 simplify review of master (#67), which left it out as larger than a cleanup.

Spec: ADR 0006 (what the window shows).

**Blocked by:** None — can start immediately

**Status:** ready-for-agent
