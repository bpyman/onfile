# 13 — Make the issuer index immutable, then cache its typo candidates

**What to build:** `issuer_index.IssuerIndex.correct()` rebuilds its candidate list from every phrase on each call. It cannot simply be cached: `IssuerIndex` is a mutable dataclass whose phrase map could change after it is built.

Make `IssuerIndex` immutable once built (frozen, with read-only maps), then compute the typo candidates once (a cached property).

**Acceptance:** `uv run python scripts/compare_answers.py` reports `0 of N conversations differ`: what the recorded demo answers does not change.

Found by the 2026-10-04 simplify review of master (#67), which left it out as larger than a cleanup.

**Blocked by:** None — can start immediately

**Status:** resolved

## Answer

`IssuerIndex` is now a frozen dataclass that owns read-only copies of all five
index maps. Snapshot names, former names, ineligible listings, and outside SEC
filers are assembled in local mutable maps during `build()` and frozen together,
so no caller can change the finished index.

`correct()` now reads one cached tuple of typo candidates instead of rebuilding
the collection on every call. Focused tests pin both the immutable boundary and
candidate reuse. All 1,659 Python tests pass, ruff and mypy pass, and the answer
comparison reports `0 of 244 conversations differ from HEAD`.
