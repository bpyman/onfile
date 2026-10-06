# 08 — A general question that names a metric is an explanation

**What to build:** `Explain how a share buyback affects EPS` asks which company was meant. It names no company and asks how something works, not for a figure: it is a general explanation (intent `explain`), as `How might AI change banking?` is (README, a general question with no company). A question that asks for a figure and names no company still asks which company (`What's the EPS?`). Tell them apart by the explanation wording (`explain how`, `how does ... affect`, `what is ... and why does it matter`), not by the absence of a company alone.

Add cases for both kinds.

Found by the set-5 brief's probe dry-run (6 October 2026, second round): a blind session labelled 30 throwaway probes from the draft brief and the README, and the app disagreed. Judged by the README's [How a question is read](../../../../../README.md#how-a-question-is-read). The fix belongs in the shared reading of words both planners pass through (ADR 0010, 0011), not in the rules planner alone, except where the ticket says the rules planner.

**Acceptance:** the cases below are read right; any phrase-coverage case named is taken off `KNOWN_GAPS`; `uv run python -m pytest` passes; `uv run python scripts/compare_answers.py` names every conversation whose answer changes, and each change is intended.

**Blocked by:** None — can start immediately

**Status:** ready-for-agent
