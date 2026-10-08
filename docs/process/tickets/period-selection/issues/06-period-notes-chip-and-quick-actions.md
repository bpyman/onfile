# `Periods.notes`, `chip` and `quick_actions`: what the answer says about its periods comes from the module

From the architecture review of 8 October 2026: period selection becomes one module, per `docs/process/tickets/period-selection/design.md` and ADR 0015. Restructure only: **no behaviour may change**. Read the design record in full before starting.

**Files (this ticket only):** `src/financial_analyst_agent/period_selection.py`, `src/financial_analyst_agent/answer_notes.py`, `src/financial_analyst_agent/presentation.py`, `src/financial_analyst_agent/graph/spec_turn.py`, `tests/unit/test_period_selection.py`, `tests/unit/test_window_copy.py`, `tests/unit/test_calendars_clarification_and_formatting.py`, `tests/unit/test_filers_rankings_and_narrowing.py`, `tests/unit/test_answer_card.py`, `tests/test_presentation.py`, `tests/unit/test_api.py`

**What to build:**

1. **`Periods.notes(reading, change, *, ranked_window=False) -> PeriodNotes`** replaces the period parts of `answer_notes.period_notes`, `_named_period_notes`, `_window_notes` and `_since_notes`, and the banner constants they use (`YEAR_OF_QUARTERS_BANNER`, `TRAILING_YEAR_BANNER`, `RANKED_LATEST_QUARTER_BANNER`, `FISCAL_Q4_GAP_BANNER`, `CALENDARS_DIFFER_BANNER`), with every text unchanged. `PeriodNotes.read` holds the notes about how the words were read (unread period, TTM or year of quarters, sub-quarter); `PeriodNotes.shown` the notes about what is shown (year to date, ranked list shows the latest quarter, named-period notes, calendars differ, fiscal Q4 gap, capped or short window, since notes). The growth-is-year-over-year and why-change banners stay in `answer_notes`, and `annotate_analysis` splices them between the two lists, so banner order is unchanged (checklist).
2. **Notes stop re-reading the message.** Year of quarters comes from `reading.year_of_quarters` and year to date from `reading.year_to_date` (ticket 02); `change.yoy` keeps the "last year" note off a year-over-year question. `answer_notes` imports no period regex afterwards.
3. **`Periods.chip`** replaces `presentation._period_chip` ("Since [fiscal] Y", "Last N quarters", the named label, and whether × returns to the latest quarter); `spec_chip_edits` calls it. `Periods.quick_actions` replaces the period part of `chip_quick_actions` as `(label, message)` pairs, which presentation wraps in `QuickAction`. The "as of" and ranked cases stay in presentation if they read `as_of` or `constituents` only.
4. Tests of `period_notes`, `_period_chip` and the period quick actions are rewritten against `Periods.notes`, `Periods.chip` and `Periods.quick_actions` on dated specs, and the old ones deleted; tests of `spec_chip_edits` and `chip_quick_actions` stay.

**Acceptance:** `uv run python -m pytest` passes; ruff and mypy are clean; `uv run python scripts/compare_answers.py --against master` reports `0 of N conversations differ`; phrase coverage stays 555 of 555; `answer_notes` imports nothing from `period_selection` but `WindowReading`, `Periods` and `PeriodNotes`, and no period regex; `_period_chip`, `_window_notes`, `_since_notes` and `_named_period_notes` no longer exist. The checklist item touched: banner order. If a step would change behaviour, or needs a file outside this ticket's list, leave it and say so in the Answer.

Spec: `docs/process/tickets/period-selection/design.md`, ADR 0015, ADR 0005 (ranked lists show each company's latest quarter), ADR 0008 (trailing year).

**Blocked by:** 03 (`ChangeAsked`), 05 (`Periods.groups`)

**Status:** ready-for-agent
