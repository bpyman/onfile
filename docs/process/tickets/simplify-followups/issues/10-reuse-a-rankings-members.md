# 10 — Rank an industry once per turn

**What to build:** `turn.rank_and_lookup_task` ranks the industry again in each metric's task, though `analysis_spec.resolve_spec` already ranked it and stored the members on `spec.constituents`. Each ranking scans the 5,161-row snapshot up to three times to rebuild its sector and industry sets (`universe.py`).

Compute those sets once in `SnapshotRanking.__init__`, and have the ranked tasks reuse the stored members (carried on the task) rather than ranking again.

**Acceptance:** `uv run python scripts/compare_answers.py` reports `0 of N conversations differ`: what the recorded demo answers does not change.

Found by the 2026-10-04 simplify review of master (#67), which left it out as larger than a cleanup.

Spec: ADR 0001 (snapshot membership).

**Blocked by:** None — can start immediately

**Status:** ready-for-agent
