# 06 — The warm-up waits for visitors before each request, not each company

**What to build:** Found by the two-axis review of PRs #69-#90 (6 October 2026), spec axis. ADR 0014: "The warm-up never goes ahead of a visitor … It waits whenever a request is queued for a slot". `FactsWarmer.sweep` (`facts_warmer.py`, about line 71) checks `idle()` once per company and then `_warm(cik)` makes two requests (the facts file and the submissions), so a visitor who queues between them waits behind the second.

Check `idle()` before each of the warm-up's requests, waiting as the sweep does now (and stopping when `stop` is set). Keep the pause between companies.

**Acceptance:** a unit test with a fake `idle` that turns busy after the first request: the second request waits until it is idle again. `uv run python -m pytest` passes; `uv run python scripts/compare_answers.py` names every conversation whose answer changes, and each change is intended.

**Blocked by:** None — can start immediately

**Status:** resolved

## Answer

Shipped 6 October 2026. `FactsWarmer` (`facts_warmer.py`) takes `requests`, a sequence of
per-file fetches (`SecFactLookup.warm_submissions`, `SecFactLookup.warm_facts`), in place of
one `warm(cik)`. The sweep asks `idle()` before each request and waits as it did before each
company, returning when `stop` is set; the pause between companies is `len(requests) / rate`,
so the `_REQUESTS_A_COMPANY` constant is gone. A request that fails leaves the company's later
requests unmade, logged and left to a visitor's turn, as before. The runtime builds a lookup a
request (`runtime._start_warming`), so nothing it keeps outlives the warming.

Tests: `test_the_warm_up_waits_before_each_of_a_companys_requests` logs the interleaving with a
fake `idle` that turns busy after the first request (`idle, submissions, busy, busy, idle,
facts`); `test_a_stopped_warm_up_makes_no_further_request_for_a_company` stops between the two.
ADR 0014's "never goes ahead of a visitor" bullet and `docs/deploy.md`'s
`SEC_WARM_REQUESTS_PER_SECOND` row say the wait is before each request. 2,074 tests pass; ruff
and mypy pass; `compare_answers` reports 0 of 247 conversations differ (the recorded runtime
starts no warm-up).
