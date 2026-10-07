# 02 — A file written just after the filing watch began is not vouched for a week

**What to build:** Found by the two-axis review of PRs #69-#90 (6 October 2026), spec axis. ADR 0013: a file fetched within a day of a filing expires after 15 minutes, because SEC's structured data may still lack the filing. `FilingWatch.lifetime` (`providers/sec/filing_watch.py`, about line 149) gives a file written after `covered_from` the week-long lifetime when its company has no filing on record. But a company that filed in the day before `covered_from` has no filing on record either: the watch never saw it. After every start, or a gap that resets coverage, the warm-up (ADR 0014) fetches such companies and their facts, possibly still missing the new quarter, are vouched for a week.

A file written less than a day after `covered_from`, for a company with no filing on record, cannot rule out a filing in the unseen day before it: give it `AFTER_FILING_SECONDS`, as a file written within a day of a known filing gets. A file written a day or more after `covered_from` with no filing on record is vouched as now. Say so in ADR 0013's lifetime rules.

**Acceptance:** unit tests with a fake clock and feed: a file written an hour after coverage began, for a company with no filing seen, lasts 15 minutes; one written two days after lasts the week; a known filing still makes a file stale or 15-minute as before. `uv run python -m pytest` passes; `uv run python scripts/compare_answers.py` names every conversation whose answer changes, and each change is intended.

**Blocked by:** None — can start immediately

**Status:** ready-for-agent
