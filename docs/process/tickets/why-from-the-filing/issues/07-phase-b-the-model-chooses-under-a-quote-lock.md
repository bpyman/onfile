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

**Status:** ready-for-agent
