# 04 — Keep parsed SEC JSON across turns

**What to build:** `providers/sec/cache.py` re-reads and re-decodes a company's facts file (megabytes on the live runtime) and the ticker map from disk on every turn, because a new `SecFactLookup` is built per turn (`runtime.live_runtime`). A follow-up about the same company decodes them again.

Keep a small process-wide LRU of the parsed (trimmed) payloads, keyed by path and `st_mtime_ns`, so a file rewritten after the one-hour expiry is read afresh.

**Why a person:** cached payloads would be shared across turns and threads, so any caller that mutates one corrupts the next turn; memory and freshness need watching under live load, and the gain is only measurable live. Check every consumer of the payloads for mutation first, or hand out read-only views.

**Acceptance:** a live follow-up about the same company is measurably faster; `uv run python scripts/compare_answers.py` reports `0 of N conversations differ`: what the recorded demo answers does not change.

Found by the 2026-10-04 simplify review of master (#67), which left it out as larger than a cleanup.

Spec: ADR 0003 (SEC as the source), `providers/sec/cache.py` freshness rules.

**Blocked by:** None — can start immediately

**Status:** resolved

## Answer

Shipped 2026-10-05, in the trimmed form. Measured first: a warm turn decodes
each company's facts file again (34 to 56 ms for 6 to 9 MB) and summarises it
(about 25 ms). Keeping the decoded JSON, as this ticket proposed, would cost
about 4.4 times the file in memory, 26 to 39 MB a large company and about
306 MB for ten banks, too much for a 512 MB instance. The trimmed facts a
lookup reads, with their summaries, take 2.5 to 3.8 MB.

`SecFactLookup` now keeps each company's trimmed facts, fiscal labels and
facts-derived filings in one process-wide store (`_ParsedFactsCache`), keyed
by the cached file's stamp (path, modified time, size) from
`CachingSECDataSource.company_facts_stamp`. A refreshed file has a new stamp
and is parsed again, so freshness is unchanged: the cache's expiry decides
it, as before (then the hour; since ADR 0013, the filing-driven rule). It holds 32 companies at most (about 130 MB), least recently
used first out. Sources without a stamp (the recording, test fakes) parse
each turn as before. The filings summary is stored as a tuple, and a test
checks that nine metrics, report dates and fiscal periods on three companies
leave a shared parse unchanged.

Measured live, warm (median of 7, same process, the store cleared before each
turn for "before"):

| Turn | Before | After |
| --- | --- | --- |
| Citigroup revenue | 0.49 s | 0.22 s |
| Compare JPMorgan and Bank of America net income, last 4 quarters | 0.92 s | 0.36 s |
| Compare six large tech companies' revenue | 1.30 s | 0.89 s |
| Top 10 banks by revenue | 2.68 s | 1.23 s |

Checks: 1,788 tests pass; ruff and mypy pass; `compare_answers.py` reports
`0 of 244 conversations differ`.
