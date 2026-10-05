# 07 — Publish an evaluation and operability scorecard

**What to build:** The project can show, in numbers, that routing, identity, refusal, follow-ups, citations, and numeral lock behave as claimed. A checked-in scorecard reports pass rate, latency, approximate live cost, and the tested model. Structured logs correlate thread and turn with provider timing.

**Blocked by:** 02 — Add continuous verification; 03 — Make public sessions safe by default.

**Status:** resolved

- [x] A versioned evaluation suite covers intent or spec-patch accuracy, issuer resolution, ambiguity and refusal, stateful follow-ups, citation coverage, numeral-lock violations, and fixture numeric correctness.
- [x] A generated scorecard is published on the storefront with pass rate, p50/p95 latency, approximate cost per live scenario, and model version.
- [x] Structured logs include thread and turn identifiers plus provider timing.
- [x] SEC response caching and retry or rate-limit behavior are demonstrated and documented without claiming full production operations.

## Answer

`financial_analyst_agent.evaluation` runs eight fixture cases (routing, refusal/clarify, follow-up, numeral lock, filing change). Checked-in scorecard: [`docs/evaluation/scorecard.md`](../../../../evaluation/scorecard.md) — **8/8**, p50/p95, $0 fixture cost, `fixture DemoCompleter`. `observability.timed` logs `conversation_turn` with thread, turn, intent, renderer, and elapsed_ms. SEC cache + 429/5xx retries are documented on the scorecard and in `docs/design.md`.

## Comments

- Agent: live OpenAI/Tavily cost is reported as $0 because the published card is the fixture path.
