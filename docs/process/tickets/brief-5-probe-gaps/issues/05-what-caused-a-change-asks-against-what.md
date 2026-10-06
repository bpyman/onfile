# 05 — "What caused revenue to fall?" asks against what

**What to build:** `What caused Pfizer's earnings to fall?` answers the latest quarter's net income. Like `Why did revenue drop?` and `What drove the change in revenue?`, it names a change with no base, so it asks what to compare against (README, a change with no base). Read `what caused ... to fall / rise / drop`, `what's behind the drop in ...` and `what led to the decline in ...` with them.

Case: phrase coverage `no_base:What caused Apple's revenue to fall?`.

Found by the set-5 brief's probe dry-run (6 October 2026, second round): a blind session labelled 30 throwaway probes from the draft brief and the README, and the app disagreed. Judged by the README's [How a question is read](../../../../../README.md#how-a-question-is-read). The fix belongs in the shared reading of words both planners pass through (ADR 0010, 0011), not in the rules planner alone, except where the ticket says the rules planner.

**Acceptance:** the cases below are read right; any phrase-coverage case named is taken off `KNOWN_GAPS`; `uv run python -m pytest` passes; `uv run python scripts/compare_answers.py` names every conversation whose answer changes, and each change is intended.

**Blocked by:** None — can start immediately

**Status:** ready-for-agent
