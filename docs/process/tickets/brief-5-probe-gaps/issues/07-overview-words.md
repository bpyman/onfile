# 07 — "The rundown" and "how is X performing" ask for the overview

**What to build:** `Give me the rundown on how Wells Fargo is performing` is refused as an unknown metric ("rundown"). `How is X doing?` gives the overview; so should `how is X performing`, `how has X been performing`, `the rundown on X`, `a quick read on X` and `X's performance` (README, overview row). `_OVERVIEW` in `request_wording.py` holds the overview words.

Add these as phrase-coverage cases expecting the overview's metrics for the company.

Found by the set-5 brief's probe dry-run (6 October 2026, second round): a blind session labelled 30 throwaway probes from the draft brief and the README, and the app disagreed. Judged by the README's [How a question is read](../../../../../README.md#how-a-question-is-read). The fix belongs in the shared reading of words both planners pass through (ADR 0010, 0011), not in the rules planner alone, except where the ticket says the rules planner.

**Acceptance:** the cases below are read right; any phrase-coverage case named is taken off `KNOWN_GAPS`; `uv run python -m pytest` passes; `uv run python scripts/compare_answers.py` names every conversation whose answer changes, and each change is intended.

**Blocked by:** None — can start immediately

**Status:** ready-for-agent
