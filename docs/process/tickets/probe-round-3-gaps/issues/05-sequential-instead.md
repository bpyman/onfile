# 05 — "Sequential instead" switches the change and keeps the quarters

**What to build:** Found reviewing probe round 3's doubts (7 October 2026): a question a doubt raised, asked on the recorded runtime, does not do what the README's "How a question is read" now says. The fix belongs in the shared reading of words both planners pass through (ADR 0010, 0011), except where the ticket says otherwise. `Apple revenue over the last 6 quarters` → `as growth` → `sequential instead` shows 5 quarters with year-over-year change: the switch is lost, and the window jumps from 6 to 5. The README's quarter-over-quarter row now says `sequential instead` (and `quarter over quarter instead`, `make it sequential`) after a year-over-year view switches the change to sequential and keeps the quarters on screen; `year over year instead` switches back the same way.

**Acceptance:** that conversation ends with 6 quarters and sequential changes, no year-over-year; the reverse switch keeps the quarters too; follow-up phrase-coverage cases for both. `uv run python -m pytest` passes; `uv run python scripts/compare_answers.py` names every conversation whose answer changes, and each change is intended.

**Blocked by:** None — can start immediately

**Status:** ready-for-agent
