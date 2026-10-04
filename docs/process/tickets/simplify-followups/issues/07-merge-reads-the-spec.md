# 07 — Merge and annotate read the spec, not the message again

**What to build:** After `request_wording` has read the analyst's words, the merge reads them again: `spec_turn._ordering_metric` re-parses the wording for the metric to order by, though the spec has `order_by`; `answer_notes.period_notes` and `_window_notes` re-run `SPECIFIC_PERIOD`, `TRAILING_YEAR`, `SUB_QUARTER`, `asked_window` and `SINCE_YEAR`. Two readings of the same words can drift.

Have `request_wording` set `set_order_by` and record its reading of the window (asked count, trailing year, since-year cap, an unread named period) on `CompiledAnalysis`; the merge and the notes read those.

**Acceptance:** `uv run python scripts/compare_answers.py` reports `0 of N conversations differ`: what the recorded demo answers does not change.

Found by the 2026-10-04 simplify review of master (#67), which left it out as larger than a cleanup.

Spec: ADR 0010 (one reading of names and windows).

**Blocked by:** None — can start immediately

**Status:** resolved

## Answer

Shipped 2026-10-04.

- `request_wording` now produces one typed `WindowReading` for counted windows,
  trailing years, since-year caps, sub-quarter wording, and unread named periods.
  The structured request and `CompiledAnalysis` carry that reading into answer notes.
- Metric wording records `set_order_by` for follow-up ordering edits. Merge reads
  `AnalysisSpec.order_by` and never parses the message for an ordering metric.
- `answer_notes` consumes the compiled reading instead of running the five window
  regular expressions and grammar again.
- Focused red/green tests cover ordering and every recorded window detail.
  `scripts/compare_answers.py` reports `0 of 244 conversations differ from HEAD`.

No blocker remains.
