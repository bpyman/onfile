# 07 — "How did EBITDA change over the past year?" is that window, year over year

**What to build:** Found reviewing probe round 3's doubts (7 October 2026): a question a doubt raised, asked on the recorded runtime, does not do what the README's "How a question is read" now says. The fix belongs in the shared reading of words both planners pass through (ADR 0010, 0011), except where the ticket says otherwise. `How did AMD's EBITDA change over the past year?` shows 5 quarters with year-over-year change: the growth default, though the question names a window. The README now says a change over a named window (`change over the past year`, `grow over the last 2 years`) is year over year over that window (4 and 8 quarters), as `growth over the last 4 quarters` already is.

**Acceptance:** that question shows 4 quarters, each with its year-over-year change; `How did AMD's EBITDA change?` still asks against what; phrase-coverage cases for both. `uv run python -m pytest` passes; `uv run python scripts/compare_answers.py` names every conversation whose answer changes, and each change is intended.

**Blocked by:** None — can start immediately

**Status:** ready-for-agent
