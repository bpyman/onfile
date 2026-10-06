# 01 — "Since the start of 2023" is a window, not fiscal 2023

**What to build:** `intel net income since the start of 2023` is read as the named period fiscal 2023, and refused because the recording holds none of it. `since 2023` already reads as every quarter since 2023 began (`SINCE_YEAR` in `request_wording.py`). Read `since the start of 2023`, `since the beginning of 2023` and `since early 2023` the same way. The README's window row now names `since the start of 2024`.

Cases: phrase coverage `window:since the start of 2024`; add `since the beginning of 2024` as a window case.

Found by the set-5 brief's probe dry-run (6 October 2026): a blind session labelled 30 throwaway probes from the draft brief and the README, and the app disagreed. Judged by the README's [How a question is read](../../../../../README.md#how-a-question-is-read). The fix belongs in the shared reading of words both planners pass through (ADR 0010, 0011), not in the rules planner alone, except where the ticket says the rules planner.

**Acceptance:** the cases below are read right; any phrase-coverage case named is taken off `KNOWN_GAPS`; `uv run python -m pytest` passes; `uv run python scripts/compare_answers.py` names every conversation whose answer changes, and each change is intended.

**Blocked by:** None — can start immediately

**Status:** ready-for-agent
