# 02 — A named period keeps its change

**What to build:** A change on a named period is lost or misread:

- `AAPL R&D in Q2 2025 year over year` and `AAPL vs MSFT EPS in Q2 2025 year over year` show Q2 2025 with no change. The named-period branch of `bind_periods_from_message` reads year over year as a second named period a year earlier (`_with_year_earlier`), so the change appears only when that quarter is fetched too. The year-earlier quarter is not in the recording, so the change silently disappears, though the newer filing reports the comparative (ADR 0009). Live (6 October 2026), `NVIDIA diluted EPS in Q2 2025 year over year` shows the change right, +$0.42 from the restated comparative, but also shows the year-earlier quarter as a row at its pre-split $2.48 beside $0.67, with a note that it is shown as first reported, before a split: the table reads as a fall where the change says a rise.
- `Apple and Microsoft gross margin growth in Q2 2025`: the same, for growth.
- `Apple profit margin in Q2 2025 quarter over quarter` and `Apple R&D for fiscal 2025 quarter over quarter`: the named branch ignores the sequential wording, so no change is shown.
- Not yet a failing case, but the same cause: `Apple R&D for fiscal 2025 year over year` shows two fiscal years with sequential changes, not fiscal 2025's quarters each with its year-over-year change.

Read a change on a named period as on a window: the named quarters, each with its year-over-year change from its own filing's comparative, or its change on the quarter before, without a row for the year-earlier quarter as first filed. The README's named-period row now says so.

Cases: `combined:Apple and Microsoft gross margin growth in Q2 2025`, `combined:AAPL vs MSFT EPS in Q2 2025 year over year`, `combined:AAPL R&D in Q2 2025 year over year`, `combined:Apple profit margin in Q2 2025 quarter over quarter`, `combined:Apple R&D for fiscal 2025 quarter over quarter`. Add `fiscal 2025 year over year` as a case that checks every quarter shown has a year-over-year row.

Found by the combinations in phrase coverage ([report](../../../../evaluation/phrase-coverage.md), `src/financial_analyst_agent/phrase_coverage.py`), judged by the README's [How a question is read](../../../../../README.md#how-a-question-is-read). Each phrasing is read right alone; the gap is in how two readings combine, in the shared reading of words both planners pass through (ADR 0010, 0011), not in the rules planner alone.

**Acceptance:** the cases below are read right and taken off `KNOWN_GAPS`; `uv run python -m pytest tests/unit/test_phrase_coverage.py` passes; `uv run python scripts/compare_answers.py` names every conversation whose answer changes, and each change is intended.

**Blocked by:** None — can start immediately

**Status:** resolved

## Answer

A change on a named period is read as on a window. `bind_periods_from_message` no longer adds the year-earlier period (`_with_year_earlier` is gone):

- Year over year, growth included, keeps the named periods and adds `year_over_year`, so each quarter's change comes from the comparative its own filing reports (ADR 0009), with no row for the year-earlier quarter as first filed. "Apple R&D for fiscal 2025 year over year" shows fiscal 2025's four quarters, each with its change, where it showed two fiscal years with sequential changes.
- Quarter over quarter adds `across_periods` and sets `PeriodSelection.company_base_dates` to `()`. When each company's dates are listed, it holds the quarter before each named quarter whose own quarter before is not named. Those quarters are fetched as the changes' bases, and `merge_analysis` leaves their rows out. `None` (the default) means no base is read. A sequential base chosen after "Compared with what?" sets it the same way.

As with a window, fiscal 2025 quarter over quarter also shows a year-over-year change for Q4, measured against the Q4 FY2024 base it reads.

The five cases are off `KNOWN_GAPS`. Phrase coverage now checks that a named period with a change has the change on every quarter shown, and the new case `named_change:Apple R&D for fiscal 2025 year over year` checks the same. `tests/test_planner_conversations.py` checks fiscal 2025 under both bases, and Q2 2025 after each answer to "Compared with what?". `compare_answers` reports 0 of 244 conversations differ: no recorded demo asks for a named period with a change.

ADR 0009 still says a sequential change can widen a window to 5; that is filed in `docs/process/rules-to-review.md`.
