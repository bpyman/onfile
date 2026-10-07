# 01 — "The last year and a half" is 6 quarters

**What to build:** Found by the set-5 brief's probe round 3 (7 October 2026): Claude's probes, written blind from the brief and scored against the recorded runtime. Judged by the README's "How a question is read". The fix belongs in the shared reading of words both planners pass through (ADR 0010, 0011), not in the rules planner alone, except where the ticket says the rules planner. `Danaher net income the last year and a half` shows 4 quarters: the window grammar (`period_window.py`) reads "the last year" and drops "and a half". It is 18 months, 6 quarters, as `18 months` already is (README: months are a third, rounded up). Read a whole number of years and a half as that many quarters plus 2: `a year and a half` (6), `one and a half years` (6), `two and a half years` (10), `1.5 years` (6), `the past 2.5 years` (10). Today `Apple revenue over the past 2.5 years` shows 20 quarters: it reads the `5` of `2.5` as five years, so a decimal count is worse than ignored.

**Acceptance:** phrase-coverage window cases for each form above, with those counts. `uv run python -m pytest` passes; `uv run python scripts/compare_answers.py` names every conversation whose answer changes, and each change is intended.

**Blocked by:** None — can start immediately

**Status:** ready-for-agent
