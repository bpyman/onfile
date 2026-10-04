# 01 — Fetch a ranking's or comparison's companies in parallel

**What to build:** The dispatcher runs metrics and periods in parallel, but inside one task the companies are fetched one after another: `turn.rank_and_lookup_task` and `turn.compare_metrics` call `get_financials` per company in sequence (up to `MAX_RANKED_COMPANIES`, 25). So does the work before dispatch: `materialize_period_dates`, `_materialize_named_periods` and `drop_annual_filers` in `graph/spec_turn.py` loop over companies calling the facts port. On the live runtime, the public demo's default, a cold "top 10 banks by revenue" downloads each company's facts file in series.

Fan the per-company calls out through the existing bounded pool (`DEFAULT_TASK_MAX_WORKERS`), keeping row order, the per-turn SEC deadline (`sec_turn_seconds_left`), `SessionQuotaError` propagation and `copy_context()` for each worker.

**Why a person:** the risk is concurrency against a shared rate limiter, per-turn deadline, session budget and cache fill locks, and the gain can only be measured live. Time a cold live ranking before and after; the recorded cassette shows neither races nor throttling.

**Acceptance:** a cold live "top 10 banks by revenue" is measurably faster; `uv run python scripts/compare_answers.py` reports `0 of N conversations differ`: what the recorded demo answers does not change.

Found by the 2026-10-04 simplify review of master (#67), which left it out as larger than a cleanup.

Spec: ADR 0005 (bounded fan-out).

**Blocked by:** None — can start immediately

**Status:** ready-for-human
