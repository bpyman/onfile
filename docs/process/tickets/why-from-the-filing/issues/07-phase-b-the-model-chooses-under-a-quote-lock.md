# Phase B: the model chooses the explaining paragraphs, under a quote lock

Phase A (code alone) scored 0.79 on the unseen confirm set when same-direction part causes count, a hair under the 0.8 bar. "Nothing found" was right in only 1 of 6 cases (ticket 06's Comments). Its misses are judgement calls wording rules cannot make:
- a cost that rose given for a profit that rose;
- a segment that moved the other way;
- causes in paragraphs the wording rules rank low.

ADR 0017 planned this: a model may explain the paragraphs, held to the filing's words by a quote lock in code.

**Decisions (Blake asked for executive decisions on 11 November 2026):**

- **Model and scope:** gpt-6.1-sol, the app's essay model, through the same OpenAI client and daily spend cap (`model_spend`). Scope is phase A's narrowed one: year-over-year questions about covered amounts.
- **Candidates:** up to eight. These are phase A's eligible paragraphs for the metric, best first, beyond its top three. They are numbered in filing order and shown verbatim.
- **What the model returns:** `{"paragraphs": [numbers, best first, at most three], "explanation": "..."}`.
- **Code checks every answer**, and any failure discards the whole answer:
  - every chosen number is a candidate;
  - **quote lock:** every passage in double quotation marks in the explanation appears verbatim in one of the chosen paragraphs, allowing for whitespace and curly or straight quotes;
  - **numeral lock:** the explanation passes it, grounded on the chosen paragraphs;
  - an empty list means nothing was found.

  On a discarded answer the panel falls back to "I couldn't find management's explanation in this 10-Q", with a link to the MD&A, never to phase A's paragraphs.
- **The prompt** lives in `explanation.py` as `EXPLANATION_INSTRUCTIONS`. Its approved text comes from Blake's review: until then the constant holds the draft in `docs/process/tickets/why-from-the-filing/phase-b-prompt.md`, and **no model is called by this ticket**.

**Files (this ticket only):**
- `src/financial_analyst_agent/quote_lock.py` (new);
- `src/financial_analyst_agent/explanation.py`;
- `src/financial_analyst_agent/explanation_evaluation.py`;
- `docs/evaluation/explanation-cases.json`;
- `docs/evaluation/explanation-candidates.json`;
- tests: `tests/unit/test_quote_lock.py` (new), `tests/unit/test_explanation.py`, `tests/unit/test_explanation_evaluation.py`.

**What to build:**

1. **`quote_lock.quotes_outside(text, sources) -> list[str]`:** every quoted passage in `text` that is not verbatim in any source. Quoted means in double quotation marks, straight or curly. Comparison normalises whitespace and quote characters, and nothing else: no case-folding and no punctuation changes. A passage shorter than four words is checked too. Test it with a verbatim quote, a paraphrase inside quotation marks, two sentences joined into one quotation, a curly-quoted copy, and an unquoted paraphrase (allowed).
2. **`explanation.model_explanation(html, metric, basis, source_url, completer)`:**
   - It builds the candidates and the input: company, metric, quarter ended, direction, question, then numbered paragraphs.
   - It calls `completer.complete_essay(...)`, or a narrow protocol of your own that the OpenAI essay completer satisfies; reuse the client and the spend cap.
   - It parses and checks the answer as above, and returns a `ModelExplanation`: the chosen `ExplainingParagraph`s, the explanation, and a reason when withheld (`quote_outside`, `numeral_lock`, `bad_choice`, `unparseable`, `nothing_found`).
3. **The evaluation.**
   - **`explanation_evaluation generate --model`:** runs `model_explanation` over the in-scope cases of a set and writes `docs/evaluation/explanation-model-<set>.json`.
   - **`score`:**
     - It scores the model's chosen paragraphs exactly as it scores phase A's: precision at 1 and 3, strict and lenient, and "nothing found right".
     - It reports the withheld rate by reason.
     - Paragraphs without a label are listed, so the judge can label them with `judge --carry-from`.
   - **Offline:** `generate` must also run with a fake completer in tests.
4. **The final measure, drawn now: a fourth fresh set.**
   - 20 year-over-year cases on the covered metrics, seed `20261111`, `"set": "final"`.
   - No (company, metric, basis) shared with any earlier set; no company more than twice.
   - Count and overlap checks only; never open its candidates.
   - The earlier sets' 32 in-scope cases are the tuning set for the prompt.

**Acceptance:**
- **Tests:** unit tests for the quote lock, for each withheld reason with a fake completer, and for the final draw (reproducible, no overlap).
- **Offline:** `generate` runs with a fake completer.
- **Checks:** pytest, ruff and mypy are clean; `compare_answers.py` reports 0 differences.
- **No model:** none is called, OpenAI or Claude.

**Blocked by:** 06

**Status:** resolved

## Answer

Shipped, calling no model. Phase A's choice, its weights and the recorded answers are unchanged (`compare_answers`: 0 of 893 differ).

- **`quote_lock.quotes_outside(text, sources)`:** every passage in straight or curly double quotation marks that no source holds verbatim. Only whitespace and quote shapes (double, and apostrophes) are normalised. A one-word quotation is checked; an unclosed one runs to the end and is checked.
- **`explanation.model_explanation(html, metric, basis, source_url, completer, *, asked)`:**
  - `asked` is a `WhyQuestion` (company, question, quarter ended, direction from the recorded figures).
  - Candidates come from `explanation_candidates`: phase A's best eight eligible paragraphs, numbered in filing order.
  - The input is built by `explanation_input`, in the draft's shape.
  - It calls `completer.complete_essay(input)` (the `EssayCompleter` protocol) with no grounding JSON, so the essay completer sends its "explain" brief. `EXPLANATION_ESSAY` sets every kind to `EXPLANATION_INSTRUCTIONS`.
  - `checked_answer` parses and checks the reply, and returns a `ModelExplanation`. Withheld reasons: `unparseable`, `bad_choice` (not a candidate number, a repeat, a bool or float, or more than three), `quote_outside`, `numeral_lock` (grounded on the chosen paragraphs only). An empty list is `nothing_found`. `failed` names the quotations or figures that failed.
  - The model is not asked when there is no candidate: sequential, uncovered metric, nothing eligible. Phase A's reason is returned instead.
  - `NOT_FOUND_MESSAGE` is the panel's line.
- **`EXPLANATION_INSTRUCTIONS`:** the draft's text between its two rules, verbatim, marked DRAFT in a comment. A test holds it equal to `phase-b-prompt.md`.
- **The client and the cap:** `explanation_completer(settings, spend=None, model=None)` is an `OpenAIEssayCompleter` over the app's OpenAI client and essay model (gpt-6.1-sol). Each request goes through `DailySpendCap.call`, priced from the response's usage at `MODEL_PRICES` ($2 in, $10 out per million tokens). With no `spend`, it builds the cap from `openai_daily_budget_usd` and `openai_spend_file`, so an evaluation run counts against the same day's ceiling. `SpendCapReached` reaches the caller.
- **`everyday_metric` and `Direction`** moved into `explanation.py`, since the input names the figure. The evaluation imports them.

**The evaluation** (`explanation_evaluation`):
- **`generate --model [NAME] --set tuning|final`:**
  - It runs `model_answers` over the in-scope cases (`model_cases`): tuning is the 32 earlier ones (dev 6, held-out 6, confirm 20), and final is the 20.
  - It writes `explanation-model-<set>.json` with the model, a hash of the instructions, and each case's offered and chosen ids, explanation, reason, failed passages and raw reply.
  - A test runs it through `main` with a fake completer.
- **Candidates:** each case now lists `offered`, phase B's candidates in the order the model sees them. Their paragraphs are in `paragraphs`, so `judge` labels whatever the model can choose. The earlier cases are otherwise unchanged. Their 38 new paragraphs need labels.
- **`score`:**
  - `score_model` scores each `explanation-model-*.json` present as phase A is scored: precision at 1 and 3, lenient and strict, and "nothing found right". A withheld answer counts as nothing found, as the analyst sees it.
  - It reports outcomes by reason and the withheld rate.
  - It lists chosen paragraphs, or MD&As, with no label.
  - Phase A's `score` now reports a set none of whose covered cases has labels as "not judged yet", rather than failing.

**The final set** (`draw_final`, seed `20261111`, e81 to e100, `"set": "final"`):
- **Draw:** 20 cases, all year over year, on covered metrics.
- **Overlap:** none. No (company, metric, basis) is shared with the first draw (both halves), the held-out set or the confirm set.
- **Companies:** 14, none more than twice.
- **Metrics:**
  - net income 4, gross profit 4, cost of revenue 4;
  - revenue 3, SG&A 3;
  - gross margin 1, operating income 1;
  - R&D 0.
- **Directions:** 19 rose, 1 fell.
- **Worth knowing:** 2 (company, metric) pairs were drawn earlier on the sequential basis.
- **What was checked:** counts, metrics, companies and overlap only. No final case's paragraphs or candidates were opened. By count, 17 of 20 have phase A paragraphs, and there are 61 offered candidates in all.

**Next, a person's runs (paid; the prompt first needs Blake's approval):**
1. `uv run python -m financial_analyst_agent.explanation_evaluation generate --model --set tuning`
2. `uv run python -m financial_analyst_agent.explanation_evaluation judge`. Saved labels keep their ids, so it asks only for what has none: the 38 new tuning paragraphs, and the final set's 76 paragraphs and 20 MD&As.
3. `uv run python -m financial_analyst_agent.explanation_evaluation score --labels docs/evaluation/explanation-labels.json`
4. Once the prompt is settled, run `generate --model --set final`, then `judge` if `score` lists unlabelled paragraphs, then `score`.

ADR 0017 and the design still say phase A's paragraphs show when the model is withheld. The ticket says otherwise, and I followed the ticket (`docs/process/rules-to-review.md`, 2026-11-11).
