# 06 — An unknown measure is not the ambiguous word inside it

**What to build:** `What's Apple's debt-to-equity ratio?` asks which equity was meant (shareholders' equity or return on equity). Debt-to-equity is not in the catalog, so it should say it cannot look that up yet, naming it, as `debt` alone does (ADR 0004, unknown). The README now says a word inside an unknown measure that would be ambiguous alone does not make it a question. The longest-span rule already lets a longer unique phrase win over an ambiguous word (ADR 0004, 0010); an unknown measure needs the same: `debt-to-equity`, `debt to equity`, `D/E`, `return on assets`, `equity multiplier` are unknown, not ambiguous.

Add phrase-coverage cases for unknown measures (these and a few more), each expecting the refusal that names the measure.

Found by the set-5 brief's probe dry-run (6 October 2026, second round): a blind session labelled 30 throwaway probes from the draft brief and the README, and the app disagreed. Judged by the README's [How a question is read](../../../../../README.md#how-a-question-is-read). The fix belongs in the shared reading of words both planners pass through (ADR 0010, 0011), not in the rules planner alone, except where the ticket says the rules planner.

**Acceptance:** the cases below are read right; any phrase-coverage case named is taken off `KNOWN_GAPS`; `uv run python -m pytest` passes; `uv run python scripts/compare_answers.py` names every conversation whose answer changes, and each change is intended.

**Blocked by:** None — can start immediately

**Status:** ready-for-agent
