# 09 — Download a filing change's two documents concurrently

**What to build:** A filing change downloads its older and newer documents one after the other (`filing_change.run_filing_change`). They are independent: fetch them concurrently, with the same per-turn SEC deadline and session budget as ticket 01's pool.

**Why a person:** the same concurrency risk as ticket 01, on the live path; follow the pattern ticket 01 settles.

**Acceptance:** a cold live filing change is measurably faster; `uv run python scripts/compare_answers.py` reports `0 of N conversations differ`: what the recorded demo answers does not change.

Found by the 2026-10-04 simplify review of master (#67), which left it out as larger than a cleanup.

**Blocked by:** 01

**Status:** resolved

## Answer

Shipped 2026-10-05. `run_filing_change` downloads and reads the older and newer
documents through `fan_out.map_in_order` (ticket 01's helper), so both share
the turn's SEC deadline and session budget and keep their places; an error is
raised as before, the older filing's first.

Measured live and cold (fresh SEC cache, 8 requests a second), two runs each:

| Question | Before | After |
| --- | --- | --- |
| What changed in Microsoft's latest 10-Q? | 3.13 s, 2.45 s | 2.46 s, 2.19 s |
| What changed in Apple's latest 10-Q? | 1.71 s, 1.63 s | 1.58 s, 1.62 s |
| What changed in NVIDIA's latest 10-Q? | 1.90 s, 1.81 s | 1.90 s, 1.82 s |

A profile shows the second download starting one request slot (0.13 s) after
the first instead of after it finishes. The saving is the shorter download,
about 0.2 to 0.4 s, visible on Microsoft's larger filings and within the noise
for the smaller ones: a filing change makes four SEC requests, two of them the
documents, and the rest of the turn is parsing and the diff.

Checks: 1,781 tests pass, including one whose two downloads each wait for the
other; ruff and mypy pass; `compare_answers.py` reports `0 of 244
conversations differ`.
