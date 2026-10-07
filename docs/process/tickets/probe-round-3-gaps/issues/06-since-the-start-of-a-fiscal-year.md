# 06 — "Since the start of fiscal 2025" counts from the fiscal year

**What to build:** Found reviewing probe round 3's doubts (7 October 2026): a question a doubt raised, asked on the recorded runtime, does not do what the README's "How a question is read" now says. The fix belongs in the shared reading of words both planners pass through (ADR 0010, 0011), except where the ticket says otherwise. `Apple revenue since the start of fiscal 2025` shows the quarters since January 2025: "fiscal" is ignored. Apple's fiscal 2025 began in late September 2024. The README's window row now says `since the start of fiscal 2025` (and `since fiscal 2025`, `since FY2025`) is every quarter of that company's fiscal 2025 and after, on its own calendar, where `since 2025` is the calendar year. Resolve it where the companies' fiscal calendars are known, as a named fiscal year is.

**Acceptance:** Apple's `since the start of fiscal 2025` starts with the quarter ended December 2024 (fiscal Q1 2025) on the recorded runtime; Microsoft's with the quarter ended September 2024; `since 2025` is unchanged. `uv run python -m pytest` passes; `uv run python scripts/compare_answers.py` names every conversation whose answer changes, and each change is intended.

**Blocked by:** None — can start immediately

**Status:** ready-for-agent
