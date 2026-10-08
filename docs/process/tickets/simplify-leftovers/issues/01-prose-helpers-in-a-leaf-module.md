# Prose helpers move out of the guide into a leaf module

From the leftovers of simplify pass 2 (`docs/process/tickets/simplify-pass-2/dropped.md`, "across/altitude: move format_date, joined, in_sentence, possessive and short_name from guide.py into a leaf prose.py"). It was dropped then only because the import edits collided with other tickets' files; nothing collides now. Cleanup only: **no behaviour may change**.

**Files (this ticket only):** `src/financial_analyst_agent/prose.py` (new), `src/financial_analyst_agent/guide.py`, `src/financial_analyst_agent/contracts.py`, `src/financial_analyst_agent/answer_notes.py`, `src/financial_analyst_agent/filing_change.py`, `src/financial_analyst_agent/graph/spec_turn.py`, `src/financial_analyst_agent/period_selection.py`, `src/financial_analyst_agent/presentation.py`, `src/financial_analyst_agent/request_wording.py`, `src/financial_analyst_agent/session.py`, `tests/unit/test_planner_rules.py`, and any other file that imports one of the moved names

**What to build:** `guide.py` holds the guide's replies (greetings, help, advice, not-recorded, follow-up suggestions), but it also holds the sentence helpers that eight modules use to write prose: `format_date`, `joined`, `in_sentence`, `possessive`, `short_name` and the `_SUFFIX` pattern `short_name` uses. `period_selection` imports the guide for nothing else, and `contracts.TableRow` imports `short_name` inside a method to avoid a cycle.

1. Move those five functions and `_SUFFIX`, unchanged, into a new `prose.py` that imports nothing from the package. Check each moved function's body is verbatim.
2. Every caller imports them from `prose`; `guide.py` imports what it still uses from `prose` and re-exports nothing. `short_display_name` stays in `guide.py` (it takes the company index), importing `short_name` from `prose`.
3. `contracts.py` imports `short_name` at the top of the module from `prose` and drops its function-local import.
4. Tests of the moved functions import them from `prose`.

**Acceptance:** `uv run python -m pytest` passes with the same test count; ruff and mypy are clean; `uv run python scripts/compare_answers.py --against master` reports `0 of N conversations differ`; `prose.py` has no `financial_analyst_agent` import; no module imports `format_date`, `joined`, `in_sentence`, `possessive` or `short_name` from `guide`. If a step would change behaviour, or needs a file outside this ticket's list beyond an import line, leave it and say so in the Answer.

**Blocked by:** None — can start immediately

**Status:** resolved

## Answer

Shipped 8 October 2026. `prose.py` holds `format_date`, `joined`, `in_sentence`, `possessive`,
`short_name`, `_SUFFIX` and `_MONTHS` (which `format_date` needs), cut from `guide.py` as one block, so
every body is verbatim; it imports only `re`, `collections.abc.Sequence` and `datetime.date`.
`guide.py` imports `in_sentence`, `joined`, `possessive` and `short_name` from `prose` for its own
replies and re-exports nothing; `short_display_name` stays in the guide. `contracts.py` imports
`short_name` at module top, and `TableRow.short` lost its function-local import. Every caller
(`answer_notes`, `filing_change`, `graph/spec_turn`, `period_selection`, `presentation`,
`request_wording`, `session`) imports from `prose`. `tests/unit/test_planner_rules.py` imports
`short_name` from `prose`, and `tests/test_presentation.py` imports `format_date` from `prose`
rather than through `presentation`'s import of it (one import line outside the ticket's list).

2,534 tests pass (unchanged); ruff and mypy clean; `compare_answers.py --against master` reports
`0 of 893 conversations differ from master`. No step would have changed behaviour.
