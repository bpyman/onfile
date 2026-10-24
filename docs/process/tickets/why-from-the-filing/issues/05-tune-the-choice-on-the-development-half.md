# Tune the paragraph choice on the development half, and draw a fresh held-out set

The first judge run (ticket 03, `docs/evaluation/explanation.md`, labels by claude-opus-5-5, spot-checked by Blake on 24 October 2026) missed the bar badly: precision at 3 was 0.32 against 0.8. The causes were plain once labelled:

- **Sequential questions:** 17 of the 20 sequential cases have no sequential cause anywhere in the MD&A, because 10-Qs explain changes against the year-earlier quarter. The scoring still showed paragraphs for 13 of them, none of them causal. Most were year-over-year or year-to-date paragraphs.
- **Cash flow and capex:** these questions landed on cash-balance and financing paragraphs ("Cash and cash equivalents increased… primarily due to… net cash provided by operating activities"; "Net cash provided by financing activities increased…").
- **Headings:** a bare heading was chosen as a paragraph ("Cost of products sold").
- **Year over year:** the cause was in the top three in 9 of the 12 cases whose MD&A holds one.

Blake approved these changes. Because the failures above were read from both halves, the existing held-out half is no longer unseen. Tune on the development half, then measure a **fresh** held-out set drawn with a new seed.

**Files (this ticket only):**
- `src/financial_analyst_agent/explanation.py`;
- `src/financial_analyst_agent/explanation_evaluation.py`;
- `docs/evaluation/explanation-cases.json`;
- `docs/evaluation/explanation-candidates.json`;
- `tests/unit/test_explanation.py` and `tests/unit/test_explanation_evaluation.py`;
- `CONTEXT.md`, only if a term changes.

**What to build:**

1. **A paragraph must compare on the basis asked.**
   - **Sequential:** the paragraph must say it compares with the quarter before. That means wording such as "sequentially", "quarter over quarter", "from the prior quarter", "compared to the second quarter of 2026" where that is the quarter before the one reported, or the sequential half of a sentence that gives both ("up 117% from a year ago and up 18% sequentially, driven by…").
   - **Year over year:** a paragraph that compares only sequentially is out. A paragraph comparing with the same quarter a year earlier, or naming no basis, stays in, since a 10-Q's MD&A compares year over year by default.
   - **A cause only for the year to date** ("first nine months", "six months ended") does not count unless the same paragraph says it applies to the quarter ("in both periods", "for the three and six months").
   - **Sequential with nothing found:** where a sequential question finds nothing but a year-over-year question on the same filing and metric would, return a new reason, `basis_not_discussed`, with those year-over-year paragraphs attached as an alternative. The panel (ticket 04) will say "This 10-Q explains the change against a year earlier, not the quarter before" and show them. The evaluation scores that case as "nothing found" for the basis asked.
2. **No headings, no cash-balance or financing paragraphs.**
   - A block of fewer than eight words, or one with no verb, is never chosen.
   - Paragraphs whose subject is the cash balance, liquidity, or financing or investing cash flows count as about another metric (`is_about_another_metric`), for every metric this module covers.
3. **Cash flow and capex are left out for now.** Operating cash flow, capex and free cash flow return `metric_not_covered`, with the words kept in the table, commented out with the reason, so they can return.
4. **A fresh held-out set.** Keep the 20 development cases (the ones whose metric is still covered). Draw 20 new held-out cases with a new seed (`20261024`):
   - from the narrowed pool;
   - excluding every (company, metric, basis) already used in either set;
   - with 10 year over year and 10 sequential, as before.

   Record both seeds in `explanation-cases.json`. Regenerate `explanation-candidates.json`. The old held-out cases leave the evaluation; say so in the cases file's notes.
5. **Tune on the development half only.** Within rules 1–3, adjust weights or wording only against the dev cases' committed judge labels in `docs/evaluation/explanation-labels.json`. Do not open the new held-out candidates' paragraphs while tuning. You may check that the draw is well formed.

**Acceptance:**
- Unit tests for each rule:
  - a sequential question never gets a paragraph that compares only year over year;
  - a year-to-date-only cause is out;
  - a heading is out;
  - a cash-balance paragraph is out;
  - cash-flow metrics are not covered;
  - `basis_not_discussed` carries its alternative.
- The fresh draw is reproducible from its seed and shares no (company, metric, basis) with the development set.
- Report in the Answer the development half's precision at 1 and 3 and its "nothing found right", by the committed labels, before and after the changes. Development paragraphs that are newly shown and have no label yet are listed, not guessed.
- pytest, ruff and mypy are clean; `compare_answers.py` reports 0 differences.
- Calls no model.

**Blocked by:** 03

**Status:** ready-for-agent
