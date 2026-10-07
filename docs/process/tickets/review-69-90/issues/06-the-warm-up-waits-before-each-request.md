# 06 — The warm-up waits for visitors before each request, not each company

**What to build:** Found by the two-axis review of PRs #69-#90 (6 October 2026), spec axis. ADR 0014: "The warm-up never goes ahead of a visitor … It waits whenever a request is queued for a slot". `FactsWarmer.sweep` (`facts_warmer.py`, about line 71) checks `idle()` once per company and then `_warm(cik)` makes two requests (the facts file and the submissions), so a visitor who queues between them waits behind the second.

Check `idle()` before each of the warm-up's requests, waiting as the sweep does now (and stopping when `stop` is set). Keep the pause between companies.

**Acceptance:** a unit test with a fake `idle` that turns busy after the first request: the second request waits until it is idle again. `uv run python -m pytest` passes; `uv run python scripts/compare_answers.py` names every conversation whose answer changes, and each change is intended.

**Blocked by:** None — can start immediately

**Status:** ready-for-agent
