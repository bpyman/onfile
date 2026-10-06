# 01 — Quarter over quarter keeps the window asked for

**What to build:** `apple D&A over the last 4 quarters quarter over quarter` and `AAPL vs MSFT gross margin for the last couple of quarters quarter over quarter` both show 5 quarters. `bind_periods_from_message` (`request_wording.py`) raises any window under 5 to 5 when the change is sequential ("A sequential change needs the quarter before the oldest one shown"). The README now says a window with quarter over quarter shows that many quarters, each with its change on the quarter before.

Show the quarters asked for, each with its sequential change. The oldest one's base is the quarter before it, which has to be read too; record the window the analyst asked for (`PeriodSelection.asked`) so labels, notes and chips say the asked window, whether or not the base quarter is shown as a row. Keep the 5-quarter default when no window is named.

Cases: `combined:$AAPL earnings over the last 4 quarters quarter over quarter`, `combined:AAPL vs MSFT gross margin for the last couple of quarters quarter over quarter`, `combined:AAPL vs MSFT operating profit margin over the last 4 quarters quarter over quarter`, `combined:apple D&A over the last 4 quarters quarter over quarter`.

Found by the combinations in phrase coverage ([report](../../../../evaluation/phrase-coverage.md), `src/financial_analyst_agent/phrase_coverage.py`), judged by the README's [How a question is read](../../../../../README.md#how-a-question-is-read). Each phrasing is read right alone; the gap is in how two readings combine, in the shared reading of words both planners pass through (ADR 0010, 0011), not in the rules planner alone.

**Acceptance:** the cases below are read right and taken off `KNOWN_GAPS`; `uv run python -m pytest tests/unit/test_phrase_coverage.py` passes; `uv run python scripts/compare_answers.py` names every conversation whose answer changes, and each change is intended.

**Blocked by:** None — can start immediately

**Status:** resolved

## Answer

A window named with quarter over quarter shows that many quarters, each with its change on the quarter before. `bind_periods_from_message` reads one quarter more than asked (`count = asked + 1`) and records `PeriodSelection.asked`; the new `PeriodSelection.shown` (the asked window, less any quarters the filings lack) is what the period chip, the "Last four quarters" quick action, the period notes and the LLM planner's view of the spec say. `merge_analysis` leaves out the base quarter's rows once the changes are computed, on each company's own calendar. `materialize_period_dates` keeps an `asked` already set. With no window named, quarter over quarter still shows 5 quarters.

This applies to every named window, not only those under 5: "last 6 quarters quarter over quarter" now shows 6 quarters, all with a change, where the oldest had none before (the README's "that many quarters").

The four cases are off `KNOWN_GAPS`; `tests/test_planner_conversations.py::test_quarter_over_quarter_keeps_the_window_asked_for` checks 2, 4 and 6 quarters on the recorded runtime. `compare_answers` reports 0 of 244 conversations differ: no recorded demo asks for a window with quarter over quarter.
