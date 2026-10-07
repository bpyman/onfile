# 07 — "How did EBITDA change over the past year?" is that window, year over year

**What to build:** Found reviewing probe round 3's doubts (7 October 2026): a question a doubt raised, asked on the recorded runtime, does not do what the README's "How a question is read" now says. The fix belongs in the shared reading of words both planners pass through (ADR 0010, 0011), except where the ticket says otherwise. `How did AMD's EBITDA change over the past year?` shows 5 quarters with year-over-year change: the growth default, though the question names a window. The README now says a change over a named window (`change over the past year`, `grow over the last 2 years`) is year over year over that window (4 and 8 quarters), as `growth over the last 4 quarters` already is.

**Acceptance:** that question shows 4 quarters, each with its year-over-year change; `How did AMD's EBITDA change?` still asks against what; phrase-coverage cases for both. `uv run python -m pytest` passes; `uv run python scripts/compare_answers.py` names every conversation whose answer changes, and each change is intended.

**Blocked by:** None — can start immediately

**Status:** resolved

## Answer

Shipped 7 October 2026. In the shared reading of periods both planners pass through (`bind_periods_from_message` in `request_wording.py`, ADR 0010, 0011), a change asked over a year named with no count (`over the past year`, `in the last year`, `during the last twelve months`) is read as a 4-quarter window, as `growth over the last 4 quarters` already was, instead of falling through to the growth default of 5. `How did AMD's EBITDA change over the past year?` now shows 4 quarters with the "Last 4 quarters" and "Year over year" chips (the recording holds no EBITDA for AMD, so each row reads "Missing fact"); `How did Apple's revenue change over the past year?` shows 4 quarters, each with its year-over-year change. `How has Tesla's revenue changed over the last year?` is 4 quarters too; its unit test expected 5 from before the README's rule and was updated. `grow over the last 2 years` was already 8 quarters and is pinned. `How did AMD's EBITDA change sequentially over the past year?` shows the 4 quarters with the quarter before the oldest read as its base, as any quarter-over-quarter window does. `How did AMD's EBITDA change?` still asks "Compared with what?". `Apple revenue over the past year` with no change is unchanged: 4 quarters, no change column, the last-year banner.

Phrase coverage gains `WINDOW_CHANGE_QUESTIONS` (4 cases under "A change over a window", checked by window and operation so the AMD case passes without a figure) and `How did AMD's EBITDA change?` in `NO_BASE_QUESTIONS`; none is sent to the model. ADR 0010's growth paragraph names the rule.

Recorded for review (`docs/process/rules-to-review.md`): `How much did Intel's revenue change over the last year?` still shows four quarters with no change column, because the year-over-year pattern reads "how did ... change" but not "how much did ... change"; a test pins it, so it is left for a person.

compare_answers: `2 of 264 conversations differ from HEAD`, the two conversations added for this ticket (`How did AMD's EBITDA change over the past year?`, `How did Apple's revenue change over the past year?`), each 5 quarters with year-over-year change before and 4 now. No other conversation changes.
