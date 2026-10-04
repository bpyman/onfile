# 04 — Keep parsed SEC JSON across turns

**What to build:** `providers/sec/cache.py` re-reads and re-decodes a company's facts file (megabytes on the live runtime) and the ticker map from disk on every turn, because a new `SecFactLookup` is built per turn (`runtime.live_runtime`). A follow-up about the same company decodes them again.

Keep a small process-wide LRU of the parsed (trimmed) payloads, keyed by path and `st_mtime_ns`, so a file rewritten after the one-hour expiry is read afresh.

**Why a person:** cached payloads would be shared across turns and threads, so any caller that mutates one corrupts the next turn; memory and freshness need watching under live load, and the gain is only measurable live. Check every consumer of the payloads for mutation first, or hand out read-only views.

**Acceptance:** a live follow-up about the same company is measurably faster; `uv run python scripts/compare_answers.py` reports `0 of N conversations differ`: what the recorded demo answers does not change.

Found by the 2026-10-04 simplify review of master (#67), which left it out as larger than a cleanup.

Spec: ADR 0003 (SEC as the source), `providers/sec/cache.py` freshness rules.

**Blocked by:** None — can start immediately

**Status:** ready-for-human
