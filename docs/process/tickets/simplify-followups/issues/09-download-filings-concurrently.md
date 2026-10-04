# 09 — Download a filing change's two documents concurrently

**What to build:** A filing change downloads its older and newer documents one after the other (`filing_change.run_filing_change`). They are independent: fetch them concurrently, with the same per-turn SEC deadline and session budget as ticket 01's pool.

**Why a person:** the same concurrency risk as ticket 01, on the live path; follow the pattern ticket 01 settles.

**Acceptance:** a cold live filing change is measurably faster; `uv run python scripts/compare_answers.py` reports `0 of N conversations differ`: what the recorded demo answers does not change.

Found by the 2026-10-04 simplify review of master (#67), which left it out as larger than a cleanup.

**Blocked by:** 01

**Status:** ready-for-human
