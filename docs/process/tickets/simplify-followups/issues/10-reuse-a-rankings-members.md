# 10 — Rank an industry once per turn

**What to build:** `turn.rank_and_lookup_task` ranks the industry again in each metric's task, though `analysis_spec.resolve_spec` already ranked it and stored the members on `spec.constituents`. Each ranking scans the 5,161-row snapshot up to three times to rebuild its sector and industry sets (`universe.py`).

Compute those sets once in `SnapshotRanking.__init__`, and have the ranked tasks reuse the stored members (carried on the task) rather than ranking again.

**Acceptance:** `uv run python scripts/compare_answers.py` reports `0 of N conversations differ`: what the recorded demo answers does not change.

Found by the 2026-10-04 simplify review of master (#67), which left it out as larger than a cleanup.

Spec: ADR 0001 (snapshot membership).

**Blocked by:** None — can start immediately

**Status:** resolved

## Answer

- `universe.SnapshotGroups` holds a snapshot's sectors and industries.
  `SnapshotRanking.__init__` builds it once, and `resolve_industry_group`,
  `resolve_industry` and `allowed_industry_names` read it instead of rescanning
  the snapshot rows on every ranking.
- `resolve_spec` keeps the ranking port's table on `RankedSet.table`, and
  `_base_tasks` copies it to `CompiledTask.ranked`. `turn._ranked_table` uses
  that table, so rank and rank-and-lookup tasks no longer rank again. A task
  with no table, such as one built by hand or from a held spec, still ranks.
- Both fields are excluded from serialization, so a stored spec looks the same.
- Test: `test_an_industry_is_ranked_once_for_every_metric_of_a_turn`. A
  two-metric ranked question calls `rank_companies` once (it called it three
  times before).
- `compare_answers.py`: `0 of 244 conversations differ from HEAD`.
