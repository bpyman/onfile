# 02 — Carry a refusal's code and details instead of re-reading its text

**What to build:** The presentation parses refusal text back into fields: `presentation._UNKNOWN_METRIC`, `_UNKNOWN_INDUSTRY` and `_COMPANY_NOT_FOUND` match the domain's messages, and `_FRIENDLY_MESSAGES` is keyed by exact message strings. `contracts.py` says so ("presentation._UNKNOWN_METRIC parses this wording back out; keep the two in step"). Rewording an error silently drops the friendly copy.

Add a typed refusal to `TurnResult` (the error's `code` and `details`), filled where a turn refuses from a `FinancialAnalystError`. Give `UnknownIndustryError` details for the industry and the sectors it knows (`ranking.py`). The presentation maps code to wording and stops matching text.

In the same change, carry the snapshot date as a field (`snapshot_as_of`) rather than parsing it back out of `snapshot_banner` text (`presentation._snapshot_day`, `_format_banner`), and mark reused evidence with a field rather than `THREAD_EVIDENCE_BANNER` string equality.

`TurnResult` is stored in thread evidence: a result saved before this change, with no refusal or snapshot field, must still load and present as it does today (test it).

**Acceptance:** no regex in `presentation.py` reads a domain error's wording; `uv run python scripts/compare_answers.py` reports `0 of N conversations differ`: what the recorded demo answers does not change.

Found by the 2026-10-04 simplify review of master (#67), which left it out as larger than a cleanup.

Spec: ADR 0002, ADR 0004.

**Blocked by:** None — can start immediately

**Status:** ready-for-agent
