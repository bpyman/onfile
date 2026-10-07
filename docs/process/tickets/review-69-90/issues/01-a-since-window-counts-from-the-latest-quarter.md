# 01 — A "since" window counts the quarters filed, not the calendar

**What to build:** Found by the two-axis review of PRs #69-#90 (6 October 2026), spec axis. The README says `since 2024` is "every quarter since that calendar year began". `since_quarters` (`request_wording.py`, about line 742) counts from `date.today()`, so on 6 October 2026 `since 2024` asks for 12 quarters, though the latest filed quarter ends in June 2026. On the recorded runtime, `Apple revenue since 2024` then says "The filings here hold only 9 of the 12 quarters asked for", which is false: it holds every quarter since 2024. The count also moves with the calendar, so recorded answers drift from day to day, and no test fixes the date.

Read a `since` window as every filed quarter that ended on or after 1 January of that year, resolved where the companies' report dates are known (as a named period is), not as a count fixed when the words are read. Keep the 40-quarter cap and its note. A window note says a quarter is missing only when the filings lack one inside the span.

**Acceptance:** `Apple revenue since 2024` on the recorded runtime shows every recorded quarter since January 2024 and no "only N of M" note; the same question gives the same quarters whatever today's date is (a test that sets the date to two different days); `since 2000` is capped at 40 with its note. `uv run python -m pytest` passes; `uv run python scripts/compare_answers.py` names every conversation whose answer changes, and each change is intended.

**Blocked by:** None — can start immediately

**Status:** resolved

## Answer

A `since` window is now every filed quarter that ended on or after 1 January of the year named, chosen where the companies' report dates are listed, and capped at 40 as every window is.

- `read_window` (`request_wording.py`) reads `since 2024` as `since_year=2024` and no count; `since_quarters` and `since_capped_from` are gone, so nothing in the reading looks at today's date. `bind_periods_from_message` sets `PeriodSelection(kind="last_n_quarters", count=40, since_year=2024)`: the cap is the listing's limit.
- `materialize_period_dates` (`spec_turn.py`) lists up to the cap for each company and keeps that company's quarters since the January (`quarters_since`, `services/fiscal_periods.py`), on its own calendar: Walmart's quarter to 31 January 2024 is since 2024. When no quarter has ended since that January (`since 2027`), the latest quarter is shown, as before. `asked` stays unset for a `since` window: it asks for whatever the filings hold.
- The window note (`answer_notes.py`) counts the span from the newest filed quarter (`quarters_in_span`): "Quarters since 2015 number 46; a window shows at most 40, so this asks for the latest 40", and "The filings here hold only 9 of the 10 quarters since 2024" only when the filings lack a quarter that ended inside the span. The period chip reads "Since 2024" rather than "Last 9 quarters".
- On the recorded runtime, `Apple revenue since 2024` shows the nine recorded quarters from June 2024 to June 2026. The note says 9 of 10, not 9 of 12: the recording lacks the quarter ended 30 March 2024, which is inside the span, so the acceptance's "no note" did not hold on this recording (recorded in `docs/process/rules-to-review.md`). `since 2025` shows every quarter and no note. A test runs the question with today set to two different days and gets the same quarters and the same note.
- `scripts/compare_answers.py` gains `Apple revenue since 2024` and `Apple revenue since 2015`, so a `since` window is compared; both differ from HEAD as intended (the note's count, the chip and the spec's `since_year`), and no other conversation does. README's window row, CONTEXT.md's Window entry and the comparison script's docstring say the new reading.

