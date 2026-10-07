# 01 — "The last year and a half" is 6 quarters

**What to build:** Found by the set-5 brief's probe round 3 (7 October 2026): Claude's probes, written blind from the brief and scored against the recorded runtime. Judged by the README's "How a question is read". The fix belongs in the shared reading of words both planners pass through (ADR 0010, 0011), not in the rules planner alone, except where the ticket says the rules planner. `Danaher net income the last year and a half` shows 4 quarters: the window grammar (`period_window.py`) reads "the last year" and drops "and a half". It is 18 months, 6 quarters, as `18 months` already is (README: months are a third, rounded up). Read a whole number of years and a half as that many quarters plus 2: `a year and a half` (6), `one and a half years` (6), `two and a half years` (10), `1.5 years` (6), `the past 2.5 years` (10). Today `Apple revenue over the past 2.5 years` shows 20 quarters: it reads the `5` of `2.5` as five years, so a decimal count is worse than ignored.

**Acceptance:** phrase-coverage window cases for each form above, with those counts. `uv run python -m pytest` passes; `uv run python scripts/compare_answers.py` names every conversation whose answer changes, and each change is intended.

**Blocked by:** None — can start immediately

**Status:** resolved

## Answer

Shipped 7 October 2026. The window grammar in `period_window.py` reads a whole number of years and a half as that many years and two quarters more, with the count before the unit (`two and a half years`, `2 and a half years`, `2.5 years`, `one and a half years`) or after it (`a year and a half`, `the last year and a half`), after a recency word, a preposition, or bare. Digits after a decimal point are not a count of their own, so `2.5 years` no longer reads as five years and `1.25 years` is left unread; `a year and a half ago` names a point in time, not a window. The "last year: four quarters" banner is skipped when the window counted its own quarters. Phrase coverage holds the six forms with their counts (6, 6, 6, 10, 6, 10); the README window row and ADR 0010 say the rule. `compare_answers.py` reports 2 of 249 conversations differ, both new: `Danaher net income the last year and a half` shows 6 quarters (4 before, with the last-year banner), and `Apple revenue over the past 2.5 years` asks 10 quarters (20 before).
