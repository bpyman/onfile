# 03 — ADR 0009 and the split ticket say what the code does

**What to build:** Found by the two-axis review of PRs #69-#90 (6 October 2026), spec axis. Documentation only.

- ADR 0009's Decision still says "A sequential change still needs the quarter before the oldest one shown, so it can widen a window to 5", which its own revision note (the quarters a change adds) withdrew. Rewrite that sentence to the revised rule: the quarter before the oldest is read as its base and not shown.
- combination-gaps ticket 04's Acceptance still reads "$0.60 (5.98 ÷ 10, rounded as the window rounds)". The value is $0.598, kept to four places (its Answer says why). Correct the acceptance line, marking it revised on review.
- The split cross-check guards a series only where a later filing reports the restated figure; a quarter no later filing restates (most quarters more than a year before a split) is adjusted by the reported ratio alone. That is intended (the ratio is reported), but neither ADR 0009's revision note nor `stock_splits.series_agrees`'s docstring says it. Say so in both.

**Acceptance:** the three texts match the code; no code behaviour changes; `compare_answers` reports 0 differ. `uv run python -m pytest` passes; `uv run python scripts/compare_answers.py` names every conversation whose answer changes, and each change is intended.

**Blocked by:** None — can start immediately

**Status:** ready-for-agent
