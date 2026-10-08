# `Words.bind` and `Words.rebase`: the period part of a patch comes from the module

From the architecture review of 8 October 2026: period selection becomes one module, per `docs/process/tickets/period-selection/design.md` and ADR 0015. Restructure only: **no behaviour may change**. Read the design record in full before starting.

**Files (this ticket only):** `src/financial_analyst_agent/period_selection.py`, `src/financial_analyst_agent/request_wording.py`, `src/financial_analyst_agent/graph/clarify.py`, `src/financial_analyst_agent/graph/spec_turn.py`, `tests/unit/test_period_selection.py`, `tests/unit/test_planner_wording.py`, `tests/unit/test_planner_rules.py`, `tests/unit/test_planner_understanding.py`, `tests/unit/test_window_copy.py`, `tests/unit/test_derived_and_named_periods.py`, `tests/unit/test_follow_up_wording.py`, `tests/unit/test_filers_rankings_and_narrowing.py`

**What to build:**

1. **`ChangeAsked`** is declared in `period_selection` with the seven flags the design record lists (`base`, `yoy`, `sequential`, `both`, `explicit_yoy`, `change_words`, `dropped`) and a `NONE`. `request_wording.change_asked(message) -> ChangeAsked` builds it from the change patterns that stay in `request_wording` (`comparison_asked`, `names_both_bases`, `drops_comparison`, `YOY`, `_SEQUENTIAL`, `_CHANGE`, `EXPLICIT_YOY`). The module imports nothing from `request_wording`.
2. **`Words.bind(patch, change)`** replaces `request_wording.bind_periods_from_message` and `_change_operations`: a dropped change, a since-window, TTM and year-of-quarters as four quarters, named periods (with empty `company_base_dates` when sequential), "latest" resets, the five- and eight-quarter defaults, `count+1` with `asked` for a sequential window, and the across / year-over-year / both operations. It returns the given patch object itself when nothing applies. `clarify._read_metric` and `ask_again` call `read(message).bind(..., change_asked(message))`.
3. **`Words.rebase(patch, change, on_screen)`** replaces `_keep_window_for_change` and `_switch_to_sequential`.
4. **`refine_patch_from_message`** stays in `request_wording` and becomes the composition the design record shows: `bind` before `_without_word_uses` / `_refine_against`, `rebase` after. Its `set_periods is None` outcomes must match today's exactly (checklist).
5. Tests of `bind_periods_from_message`, `_keep_window_for_change` and `_switch_to_sequential` are rewritten against `Words.bind` and `Words.rebase` with a hand-built `ChangeAsked`, and the old ones deleted. Tests of `refine_patch_from_message` stay as they are.

**Acceptance:** `uv run python -m pytest` passes; ruff and mypy are clean; `uv run python scripts/compare_answers.py --against master` reports `0 of N conversations differ`; phrase coverage stays 555 of 555; the rules planner passes the same planner cases as master; `bind_periods_from_message`, `_keep_window_for_change`, `_switch_to_sequential` and `_change_operations` no longer exist. The checklist items touched: keep the seven flags; `bind` identity; `set_periods` presence. If a step would change behaviour, or needs a file outside this ticket's list, leave it and say so in the Answer.

Spec: `docs/process/tickets/period-selection/design.md`, ADR 0015, ADR 0009, ADR 0010.

**Blocked by:** 02 (`read` and `Words` exist)

**Status:** ready-for-agent
