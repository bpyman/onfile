# 05 — "What caused revenue to fall?" asks against what

**What to build:** `What caused Pfizer's earnings to fall?` answers the latest quarter's net income. Like `Why did revenue drop?` and `What drove the change in revenue?`, it names a change with no base, so it asks what to compare against (README, a change with no base). Read `what caused ... to fall / rise / drop`, `what's behind the drop in ...` and `what led to the decline in ...` with them.

Case: phrase coverage `no_base:What caused Apple's revenue to fall?`.

Found by the set-5 brief's probe dry-run (6 October 2026, second round): a blind session labelled 30 throwaway probes from the draft brief and the README, and the app disagreed. Judged by the README's [How a question is read](../../../../../README.md#how-a-question-is-read). The fix belongs in the shared reading of words both planners pass through (ADR 0010, 0011), not in the rules planner alone, except where the ticket says the rules planner.

**Acceptance:** the cases below are read right; any phrase-coverage case named is taken off `KNOWN_GAPS`; `uv run python -m pytest` passes; `uv run python scripts/compare_answers.py` names every conversation whose answer changes, and each change is intended.

**Blocked by:** None — can start immediately

**Status:** resolved

## Answer

Shipped 2026-10-06. `What caused Pfizer's earnings to fall?`, `What caused Apple's revenue to fall?`, `What led to the decline in Pfizer revenue?` and `What's the reason for the drop in Intel's revenue?` now ask what to compare against, as `Why did revenue drop?` does. `What's behind the drop in Apple's revenue?` already asked.

- The fix is in `_CHANGE` (`request_wording.py`), the shared reading of a change that may name no base, which both planners pass through (ADR 0010, 0011). It gains two shapes: `what (caused|made|led|drove|pushed) ... (to) (fall|rise|drop|decline|jump|climb|slip|dip|shrink|go up|go down|change|move|shift|swing|increase|decrease)`, and `led to` / `the reason for` / `the reason behind` beside `drove`, `caused` and `behind` before `the (change|drop|decline|...) in`. The rules planner is unchanged.
- A base or a span still answers: `What caused Apple's revenue to fall year over year?` is the eight-quarter year-over-year table, and `What caused Apple's revenue to fall since 2023?` is the quarters since 2023, as for `What drove the change in ... since 2023?`.
- Phrase coverage: `no_base:What caused Apple's revenue to fall?` is off `KNOWN_GAPS`, which is now empty; `NO_BASE_QUESTIONS` gains the Pfizer earnings, "what's behind the drop in" and "what led to the decline in" questions.
- `tests/unit/test_planner_wording.py`: nine new cases on `comparison_asked`, including the year-over-year and since-2023 forms.

`uv run python scripts/compare_answers.py`: 0 of 244 conversations differ (no recorded conversation uses these words). The README row "A change with no base" already names `What caused revenue to fall?`, so it is unchanged.
