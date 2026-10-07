# 02 — A file written just after the filing watch began is not vouched for a week

**What to build:** Found by the two-axis review of PRs #69-#90 (6 October 2026), spec axis. ADR 0013: a file fetched within a day of a filing expires after 15 minutes, because SEC's structured data may still lack the filing. `FilingWatch.lifetime` (`providers/sec/filing_watch.py`, about line 149) gives a file written after `covered_from` the week-long lifetime when its company has no filing on record. But a company that filed in the day before `covered_from` has no filing on record either: the watch never saw it. After every start, or a gap that resets coverage, the warm-up (ADR 0014) fetches such companies and their facts, possibly still missing the new quarter, are vouched for a week.

A file written less than a day after `covered_from`, for a company with no filing on record, cannot rule out a filing in the unseen day before it: give it `AFTER_FILING_SECONDS`, as a file written within a day of a known filing gets. A file written a day or more after `covered_from` with no filing on record is vouched as now. Say so in ADR 0013's lifetime rules.

**Acceptance:** unit tests with a fake clock and feed: a file written an hour after coverage began, for a company with no filing seen, lasts 15 minutes; one written two days after lasts the week; a known filing still makes a file stale or 15-minute as before. `uv run python -m pytest` passes; `uv run python scripts/compare_answers.py` names every conversation whose answer changes, and each change is intended.

**Blocked by:** None — can start immediately

**Status:** resolved

## Answer

Shipped 2026-10-06. `FilingWatch.lifetime` gives a file written less than a day after the
watch's coverage began `AFTER_FILING_SECONDS` (15 minutes), after the stale and
filed-within-a-day rules and before the week: the day before coverage began is unseen, so a
filing there, and its absence from SEC's structured data, cannot be ruled out. A file written
a day or more after coverage began, with no filing since, is vouched for the week as before.

- The rule applies whether or not the watch saw an older filing by the company. After a gap
  moves coverage forward, a company whose filing the watch saw before the gap may have filed
  again in the gap, so the same reasoning holds; the ticket scoped it to companies with no
  filing on record, and that case is covered by it.
- `needs_warming` warms a 15-minute file once more when a file fetched now would be vouched
  for the week (`lifetime(cik, now) == VOUCHED_SECONDS`), so the warm-up fetches such a
  company once when the day since coverage began (or since its filing) is over, rather than
  every 15 minutes. Before this, a 15-minute file with no filing on record was warmed again
  at once.
- Three existing watch tests wrote files less than a day after coverage began with no filing
  on record and expected the week; each now writes a day later or expects the 15 minutes,
  keeping what it checked (paging back keeps coverage; a gap moves it).
- ADR 0013 gains the lifetime rule and a consequence (a busy feed's first poll reaches back
  hours, so the first day's files are refreshed by visitors); `docs/deploy.md`'s
  `SEC_FILING_WATCH_SECONDS` row says so.

Tests: `tests/unit/providers/test_filing_watch.py` (a file written an hour after coverage
began lasts 15 minutes; two days after, the week; such a company is warmed once more after
the day). 2,059 tests pass; ruff and mypy pass; compare_answers reports
`0 of 246 conversations differ from HEAD` (the recorded runtime has no watch).
