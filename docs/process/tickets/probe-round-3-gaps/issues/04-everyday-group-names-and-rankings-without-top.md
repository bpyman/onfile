# 04 — "Semis", "chipmakers" and a ranking with no "top"

**What to build:** Found reviewing probe round 3's doubts (7 October 2026): a question a doubt raised, asked on the recorded runtime, does not do what the README's "How a question is read" now says. The fix belongs in the shared reading of words both planners pass through (ADR 0010, 0011), except where the ticket says otherwise.

- `top 5 semis by market cap and revenue` is refused: "Unknown industry 'semis'". Everyday names for a snapshot group name it: `semis`, `chipmakers`, `chip companies`, `chip stocks` (Semiconductors); `drugmakers`, `drug makers`, `big pharma` (Drug Manufacturers - General); `big banks` (Banks - Diversified); `tech` already works. Add them where industry names are read (the snapshot's group aliases), for both planners.
- `chipmakers by free cash flow, lowest first` asks which company: a group and `by` a metric, with no `top`, is a ranking (the README's default length, 10).
- `lowest first` (and `smallest first`, `ascending`) orders the same ranked companies from the lowest value of the metric; the members are still the largest by market value (README). `bottom 5` stays refused, as now.

**Acceptance:** each phrasing above on the recorded runtime gives the ranking the README describes; phrase-coverage cases for the group names and for `lowest first`. `uv run python -m pytest` passes; `uv run python scripts/compare_answers.py` names every conversation whose answer changes, and each change is intended.

**Blocked by:** None — can start immediately

**Status:** resolved

## Answer

Shipped 7 October 2026.

- **Group names.** `semis`, `big pharma` and `big banks` join the snapshot's group aliases (`INDUSTRY_GROUP_ALIASES` in `universe.py`): Semiconductors, Drug Manufacturers - General and Banks - Diversified. `chipmakers`, `chip companies`, `chip stocks`, `drugmakers` and `drug makers` already resolved. Both planners' rankings resolve through the aliases.
- **A group `by` a metric is a ranking.** The rules planner reads `<group> by <metric>` with no rank word as a ranking of the default length (10), ordered by the metric, when the group is a few words that name no metric and what follows `by` is a metric. `revenue by segment`, `Apple revenue by quarter` and `net income by year` stay lookups. The intent is the planner's to pick, so this is the one part in the rules planner (ADR 0011: a keyless visitor's question it misread).
- **`lowest first`.** A new operation, `lowest_first`, read from the words for both planners (`bind_order_from_message` in `request_wording.py`, in the shared flow beside the metric and period binding): `lowest first`, `smallest first`, `ascending`, `from the lowest`, `low to high`. `largest first`, `highest first` and `descending` remove it, and so does naming another order (`sort by revenue`). It holds across edits (`add Apple` keeps it). The ranking's members are still the largest by market value; `_order_by_metric` runs them from the lowest, with a plain ranking ordered by market cap. The chip reads `Lowest first` and its × sends `largest first`, which the rules planner reads as an edit on its own, as it does `lowest first`. The banner and the chart caption say `, lowest first`. `bottom 5` stays refused; the guide's `smallest` rule no longer catches `smallest first`.
- **Coverage.** Fourteen `RANKING_QUESTIONS` in phrase coverage, none sent to the model. Recorded-runtime tests in `test_says_what_it_cannot_do.py`; planner tests in `test_planner_wording.py` and `test_planner_rules.py`; `apply_patch` in `test_analysis_spec.py`. ADR 0010 has a "ranking's group and order" paragraph.
- **compare_answers:** 5 of 257 conversations differ, the five added for this ticket (`top 5 semis by market cap and revenue`, `chipmakers by free cash flow, lowest first`, `big pharma by revenue`, `Top 5 banks by revenue, smallest first`, `Top 5 banks by revenue | lowest first | largest first`); each was refused or asked which company before and ranks now.
