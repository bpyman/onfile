# 07 — Merge and annotate read the spec, not the message again

**What to build:** After `request_wording` has read the analyst's words, the merge reads them again: `spec_turn._ordering_metric` re-parses the wording for the metric to order by, though the spec has `order_by`; `answer_notes.period_notes` and `_window_notes` re-run `SPECIFIC_PERIOD`, `TRAILING_YEAR`, `SUB_QUARTER`, `asked_window` and `SINCE_YEAR`. Two readings of the same words can drift.

Have `request_wording` set `set_order_by` and record its reading of the window (asked count, trailing year, since-year cap, an unread named period) on `CompiledAnalysis`; the merge and the notes read those.

**Acceptance:** `uv run python scripts/compare_answers.py` reports `0 of N conversations differ`: what the recorded demo answers does not change.

Found by the 2026-10-04 simplify review of master (#67), which left it out as larger than a cleanup.

Spec: ADR 0010 (one reading of names and windows).

**Blocked by:** None — can start immediately

**Status:** ready-for-agent
