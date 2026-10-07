# 04 — "Semis", "chipmakers" and a ranking with no "top"

**What to build:** Found reviewing probe round 3's doubts (7 October 2026): a question a doubt raised, asked on the recorded runtime, does not do what the README's "How a question is read" now says. The fix belongs in the shared reading of words both planners pass through (ADR 0010, 0011), except where the ticket says otherwise.

- `top 5 semis by market cap and revenue` is refused: "Unknown industry 'semis'". Everyday names for a snapshot group name it: `semis`, `chipmakers`, `chip companies`, `chip stocks` (Semiconductors); `drugmakers`, `drug makers`, `big pharma` (Drug Manufacturers - General); `big banks` (Banks - Diversified); `tech` already works. Add them where industry names are read (the snapshot's group aliases), for both planners.
- `chipmakers by free cash flow, lowest first` asks which company: a group and `by` a metric, with no `top`, is a ranking (the README's default length, 10).
- `lowest first` (and `smallest first`, `ascending`) orders the same ranked companies from the lowest value of the metric; the members are still the largest by market value (README). `bottom 5` stays refused, as now.

**Acceptance:** each phrasing above on the recorded runtime gives the ranking the README describes; phrase-coverage cases for the group names and for `lowest first`. `uv run python -m pytest` passes; `uv run python scripts/compare_answers.py` names every conversation whose answer changes, and each change is intended.

**Blocked by:** None — can start immediately

**Status:** ready-for-agent
