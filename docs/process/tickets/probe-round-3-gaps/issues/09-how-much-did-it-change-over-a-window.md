# 09 — "How much did revenue change over the last year?" is year over year over that window

**What to build:** Decided in `rules-to-review.md` (2026-10-07, probe-round-3-gaps 07). `How did AMD's EBITDA change over the past year?` shows 4 quarters, each with its year-over-year change (ticket 07), but `How much did Intel's revenue change over the last year?` and `Over the past 10 quarters, how has Thermo Fisher's revenue moved?` show the span's quarters with no change column (`_names_a_span` in `request_wording.py`: "the span is the answer"). Every change asked over a named window is year over year over that window, whatever the change wording (`how much did ... change`, `how has ... moved`, `how did ... change`, `how has ... grown`), as the README's growth row says. With no window, `How much did revenue change?` still asks against what.

Change `test_what_a_change_is_measured_against`'s two expectations for these questions with the reading, and say so in the commit.

**Acceptance:** both questions above show their window's quarters, each with its year-over-year change; `How much did Intel's revenue change?` still asks; phrase-coverage cases for each wording. `uv run python -m pytest` passes; `uv run python scripts/compare_answers.py` names every conversation whose answer changes, and each change is intended.

**Blocked by:** None — can start immediately

**Status:** resolved

## Answer

Shipped 2026-10-07. A change asked over a named window is year over year over that window, whatever the change wording.

- `comparison_asked` in `request_wording.py`, which both planners pass through (ADR 0010, 0011), now reads a change over a named window as year over year: `_names_a_window` is a counted window of two or more quarters or "over/in the last/past year", and `_asks_change` is a change in words that name no base (`_CHANGE`: "how much did ... change", "how has ... moved", "what caused ... to fall") over such a window or with no span at all. `_asks_change_without_base` is gone; `_names_a_span` (a window, a "since" window or several named periods) still guards the follow-up reading and the "since" cases.
- `bind_periods_from_message` sets the year-over-year operation from the same reading, so `How much did Intel's revenue change over the last year?` is 4 quarters each with its change (the "past year" rule from ticket 07 applies once the change is recognised) and `Over the past 10 quarters, how has Thermo Fisher's revenue moved?` is 10 quarters each with its change (the recording holds 9). `How did Apple's revenue change over the last 2 quarters?`, which asked "Compared with what?" before, is now year over year over the two. With no window, `How much did Intel's revenue change?` still asks.
- The two expectations in `test_what_a_change_is_measured_against` the ticket names changed from `None` to `"year_over_year"`, with two more cases ("how did ... change over the last 2 quarters", "how has ... grown over the past 6 quarters"); the binder test from ticket 07 gained the same four; `test_a_change_over_a_window_is_year_over_year_whatever_the_wording` pins both recorded answers and the no-window clarification. Phrase coverage: four cases added to `WINDOW_CHANGE_QUESTIONS`, none sent to the model.
- README's growth row and ADR 0010 say the rule holds whatever the wording. Recorded in `rules-to-review.md`: a change over a "since" window (`How much did Intel's revenue change since 2023?`) still shows the quarters alone, as the ticket's explicit test scope leaves it.
- `compare_answers`: 4 of 269 conversations differ, all intended: the evaluation case `h3_tmo_rev_past_ten` (the Thermo Fisher question: 9 quarters with no change column before, each with its year-over-year change now) and the three conversations added for this ticket (Intel over the last year: 4 quarters, now with the change; Thermo Fisher as above; Apple over the last 2 quarters: a "Compared with what?" question before, 2 quarters with their change now).
