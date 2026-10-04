# 01 — Fetch a ranking's or comparison's companies in parallel

**What to build:** The dispatcher runs metrics and periods in parallel, but inside one task the companies are fetched one after another: `turn.rank_and_lookup_task` and `turn.compare_metrics` call `get_financials` per company in sequence (up to `MAX_RANKED_COMPANIES`, 25). So does the work before dispatch: `materialize_period_dates`, `_materialize_named_periods` and `drop_annual_filers` in `graph/spec_turn.py` loop over companies calling the facts port. On the live runtime, the public demo's default, a cold "top 10 banks by revenue" downloads each company's facts file in series.

Fan the per-company calls out through the existing bounded pool (`DEFAULT_TASK_MAX_WORKERS`), keeping row order, the per-turn SEC deadline (`sec_turn_seconds_left`), `SessionQuotaError` propagation and `copy_context()` for each worker.

**Why a person:** the risk is concurrency against a shared rate limiter, per-turn deadline, session budget and cache fill locks, and the gain can only be measured live. Time a cold live ranking before and after; the recorded cassette shows neither races nor throttling.

**Acceptance:** a cold live "top 10 banks by revenue" is measurably faster; `uv run python scripts/compare_answers.py` reports `0 of N conversations differ`: what the recorded demo answers does not change.

Found by the 2026-10-04 simplify review of master (#67), which left it out as larger than a cleanup.

Spec: ADR 0005 (bounded fan-out).

**Blocked by:** None — can start immediately

**Status:** resolved

## Answer

`fan_out.map_in_order` runs a list of calls through a bounded pool
(`DEFAULT_TASK_MAX_WORKERS`, now defined there), each in a copy of the caller's
context so it shares the turn's SEC deadline, and returns results in item order.
An error escaping a call, such as `SessionQuotaError`, is raised and the calls
not yet started are cancelled. `compare_metrics`, `market_formula_rows` and
`rank_and_lookup_task` fetch their companies through it and then build rows in
order, so deduplication and row order are unchanged; `materialize_period_dates`,
`_materialize_named_periods` and `drop_annual_filers` list or check their
companies the same way.

Measured live and cold (fresh SEC cache, rules planner), three runs each:

| Turn | master | this change |
|---|---|---|
| top 10 banks by revenue | 12.8, 8.4, 11.5 s | 8.0, 8.0, 8.0 s |
| compare revenue for six companies | 4.1, 4.2, 4.7 s | 4.1, 4.1, 4.2 s |

The gain is capped by the request rate, not by the downloads. A cold
"top 10 banks by revenue" makes 34 SEC requests, and `SEC_MAX_REQUESTS_PER_SECOND`
allows at most 5 a second (the settings refuse more), so 34 requests take at
least 6.8 s however many run at once: the workers spent 30 s in all waiting for
a slot and 7.8 s downloading. With the limiter at SEC's own 10 a second (an
experiment, not a setting), the same turns took 4.8 s here against 11.8 s on
master, and the six-company comparison 2.9 s against 4.7 s.

Decided afterwards: the cap rises to 8 a second (`config.SEC_MAX_REQUESTS_PER_SECOND`,
the default and the most the settings accept), leaving SEC's 10 room for anything
else on the address. At 8, cold: top 10 banks by revenue 5.8 s, by net margin
5.9 s, the six-company comparison 3.4 s.

Left for its own change: the older submissions pages that 13 of the 34 requests
fetch (JPMorgan, Bank of America and Citi, pages 001 to 004), when company facts
already supply that history (`SecFactLookup._with_facts_filings`).

Checks: 1,704 tests pass, including `tests/unit/test_fan_out.py` (order,
overlap, the shared deadline, a quota stop, and a ranked lookup whose members
are fetched at once); ruff and mypy pass; `compare_answers.py --against master`
reports `0 of 244 conversations differ`.
