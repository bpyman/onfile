# 06 — "Since the start of fiscal 2025" counts from the fiscal year

**What to build:** Found reviewing probe round 3's doubts (7 October 2026): a question a doubt raised, asked on the recorded runtime, does not do what the README's "How a question is read" now says. The fix belongs in the shared reading of words both planners pass through (ADR 0010, 0011), except where the ticket says otherwise. `Apple revenue since the start of fiscal 2025` shows the quarters since January 2025: "fiscal" is ignored. Apple's fiscal 2025 began in late September 2024. The README's window row now says `since the start of fiscal 2025` (and `since fiscal 2025`, `since FY2025`) is every quarter of that company's fiscal 2025 and after, on its own calendar, where `since 2025` is the calendar year. Resolve it where the companies' fiscal calendars are known, as a named fiscal year is.

**Acceptance:** Apple's `since the start of fiscal 2025` starts with the quarter ended December 2024 (fiscal Q1 2025) on the recorded runtime; Microsoft's with the quarter ended September 2024; `since 2025` is unchanged. `uv run python -m pytest` passes; `uv run python scripts/compare_answers.py` names every conversation whose answer changes, and each change is intended.

**Blocked by:** None — can start immediately

**Status:** resolved

## Answer

Shipped 7 October 2026. `since fiscal 2025`, `since the start of fiscal 2025`, `since fiscal year 2025` and `since FY2025` are read by the shared window grammar as a "since" window on each company's own fiscal year (`WindowReading.since_fiscal`, `PeriodSelection.since_fiscal`), and resolved where the company's fiscal periods are listed, as a named fiscal year is: every filed quarter whose declared fiscal year is that year or later, newest first, at most the window cap. On the recorded runtime Apple's `since the start of fiscal 2025` shows 7 quarters opening with the quarter ended December 28, 2024, and Microsoft's `since FY2025` shows 8 opening with September 30, 2024; the chip reads "Since fiscal 2025". `since 2025` is unchanged (calendar year, from March 29, 2025). The span is counted on the company's own labels so the window note can say how many quarters the filings lack since fiscal 2015. The flag is left out of a spec dump when false, so calendar windows' stored specs read as before.

compare_answers: `3 of 262 conversations differ from HEAD`, the three conversations added for this ticket (`Apple revenue since the start of fiscal 2025`, `Microsoft revenue since FY2025`, `Apple and Microsoft revenue since fiscal 2025`), each showing a "couldn't read 'fiscal 2025' as a period" banner over the last 6 quarters before and the fiscal-year window now. No other conversation changes.
