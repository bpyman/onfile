# Narrow phase A to year-over-year amounts, and draw a confirmation set

The second judge run (`docs/evaluation/explanation.md`, revised rubric, spot-checked by Blake on 24 October 2026) measured the fresh held-out set at precision at 3 of 0.75 (6 of 8 shown), under the 0.8 bar. By basis:

| Held-out | MD&A states a cause | Shown | Hit at 3 | Recall |
| --- | --- | --- | --- | --- |
| year over year (10) | 10 | 7 | 6 | 6 of 10 |
| sequential (10) | 2 | 1 | 0 | 0 of 2 |

- **Most year-over-year misses were margins.** Apple's net margin, an operating margin and another net margin all had their cause in a component's paragraph (gross margin, R&D, interest expense), which code rightly does not show.
- **Sequential causes are rare in 10-Qs,** which explain changes against the year-earlier quarter.

Blake approved narrowing phase A to where it works and confirming that on a third fresh set. Choosing the slice after seeing the held-out set makes its 0.86 on that slice a hypothesis, not a result.

**Files (this ticket only):**
- `src/financial_analyst_agent/explanation.py`;
- `src/financial_analyst_agent/explanation_evaluation.py`;
- `docs/evaluation/explanation-cases.json`;
- `docs/evaluation/explanation-candidates.json`;
- `tests/unit/test_explanation.py` and `tests/unit/test_explanation_evaluation.py`;
- `CONTEXT.md` (the Management's explanation entry).

**What to build:**

1. **Phase A covers year-over-year questions about amounts.** These are the metrics: revenue, cost of revenue, gross profit and gross margin, operating income, net income, R&D, and SG&A. Gross margin stays in: its own paragraphs explain it (Apple, AMD and Micron in the first runs).
   - **Not covered:** every other margin and ratio (operating margin, net margin, R&D to sales, SG&A ratio, effective tax rate and the rest) returns `metric_not_covered`. Keep their words in the table, commented out, with this ticket as the reason.
   - **A sequential question no longer searches for a sequential cause.** It returns `basis_not_discussed`, with the year-over-year paragraphs for the same filing and metric attached as the alternative. If there are none, it returns plain `not_discussed`.
2. **A confirmation set.**
   - Draw 20 new cases with seed `20261025`, all year over year, from the covered metrics.
   - Exclude every (company, metric, basis) used in any earlier set: the first draw's dev and held-out halves, and the second held-out draw. Spread them across companies: no company more than twice, if the pool allows.
   - Mark them `"set": "confirm"`. `score` reports a confirm section beside dev and held-out.
   - The dev and second held-out cases stay in the file for the record, but `score` should say clearly which sets were measured under which scope. Write a short note at the top of the report that the dev and held-out figures predate this narrowing.
3. **Regenerate the candidates.** Paragraph ids keep their MD&A-place form, so the existing labels carry over by text (`judge --carry-from`).
4. **No tuning against the confirm set.** Do not open its candidates' paragraphs; check counts and overlap only.

**Acceptance:**
- **Unit tests:**
  - a margin other than gross margin is not covered;
  - a sequential question returns `basis_not_discussed` with year-over-year paragraphs, or `not_discussed`;
  - the confirm draw is reproducible from its seed, all year over year, from covered metrics, with no overlap with earlier sets.
- **Report the counts:** how many confirm cases were drawn, and how many earlier dev and held-out cases the narrowed scope still covers.
- **Checks:** pytest, ruff and mypy are clean; `compare_answers.py` reports 0 differences. No model is called.

**Blocked by:** 05

**Status:** resolved

## Answer

Shipped, calling no model. Scoring weights are unchanged.

- **Coverage** (`explanation._METRIC_FAMILY`): revenue, cost of revenue, gross profit, gross margin, operating income, net income, R&D and SG&A.
  - Operating margin, net margin, R&D to sales and the SG&A ratio are commented out, with this ticket as the reason. They return `metric_not_covered`. Their words stay in the family table, so a paragraph about them still counts as another metric.
  - The effective tax rate and other ratios were never covered and still are not.
- **Sequential:** `management_explanation` no longer searches for a sequential cause, even where one is there. It returns `basis_not_discussed` with the year-over-year paragraphs as `alternative`, or `not_discussed` when there are none. `_compares_on` lost its sequential branch. A year-over-year question still drops paragraphs that compare only sequentially.
- **`explanation.covers(metric, basis)`:** a covered metric, asked year over year or with no basis named. This is the narrowed scope, and `score` counts only these cases.

**The confirmation set** (`draw_confirm`, seed `20261025`, e61 to e80, `"set": "confirm"`):
- **Draw:** 20 cases, all year over year, from the covered metrics.
- **Overlap:** none. No (company, metric, basis) is shared with either half of the first draw or with the second held-out draw.
- **Metrics:** operating income 5, SG&A 4, revenue 3, gross margin 3, R&D 2, cost of revenue 1, gross profit 1, net income 1.
- **Companies:** 15 in all, none more than twice. Broadcom, Microsoft, Pfizer, Tesla and UnitedHealth have two cases each. AMD, Alphabet, Apple, Applied Materials, Cisco, Eli Lilly, General Motors, Gilead, Nvidia and Thermo Fisher have one each.
- **Directions:** 14 rose and 6 fell.
- **Worth knowing:** 6 of the 20 (company, metric) pairs were drawn earlier as sequential questions. The ticket excludes by (company, metric, basis), so they stay in, but the judge has seen those MD&As.
- **What was checked:** counts and overlap only. No confirm case's candidates or paragraphs were opened. Of the 20, 14 show paragraphs and 6 are `not_discussed`.

**The earlier sets under the narrowed scope:**
- **Unchanged:** the dev and held-out cases are byte-for-byte what they were. `SECOND_DRAW_METRICS` freezes ticket 05's metric list for the dev filter and the held-out pool.
- **Dev:** the scope still covers 6 of 16. Out of scope are 9 sequential cases and 1 margin.
- **Held-out:** the scope still covers 6 of 20. Out of scope are 10 sequential cases and 4 margins or ratios.
- **In total:** 12 of 36.
- **Their candidates:** the 12 covered cases' candidates are identical to before. The others now have no scored paragraphs: 9 `basis_not_discussed`, 3 `not_discussed` and 12 `metric_not_covered`.
- **Their figures, by the committed labels:**
  - dev precision at 1 and at 3 is 0.75 (3 of 4), with "nothing found right" at 0 of 2;
  - held-out precision at 1 is 0.67 (4 of 6), and precision at 3 is 1.00 (6 of 6).

  Both sets were read before the narrowing, so these figures are a hypothesis, not a result.

**`score` and the report:**
- **Sections:** dev, held-out and confirm. Each counts only the covered cases and says how many of its cases are outside the scope (`outside_scope`).
- **Scope lines:** each section says what it was drawn under. Dev was drawn under the wider scope and tuned on; held-out under the wider scope and read before the narrowing; confirm under the narrowed scope, unseen.
- **The top note:** says the dev and held-out figures predate the narrowing.
- **The "all" section is gone:** it would add sets read before the narrowing to the unseen confirm set.

**Candidates:** regenerated. Paragraph ids keep their MD&A-place form. Carrying the committed labels by text leaves 0 judgements to ask for dev and held-out, and 63 for confirm (20 MD&As and 43 paragraphs).

**Next, a person's run (paid):**
1. `git show b1afb9f:docs/evaluation/explanation-candidates.json > old-candidates.json`
2. `uv run python -m financial_analyst_agent.explanation_evaluation judge --carry-from old-candidates.json` judges only the 20 confirm cases.
3. `uv run python -m financial_analyst_agent.explanation_evaluation score --labels docs/evaluation/explanation-labels.json`

Until then, the committed `explanation.md` is the second run's report, and `score` fails for want of confirm labels.

## Comments

11 November 2026, confirm set scored once (`explanation.md`):

- **Lenient** (company-wide and part causes): precision at 3 of 0.86, 12 of 14.
- **Strict** (company-wide only): 0.57, 8 of 14.
- **Same direction**, classified by hand from the four cases that count only on a part cause:
  - e66 Nvidia, Compute & Networking up on revenue growth: counts.
  - e70 Cisco, product gross margin down on mix and pricing: counts. The EMEA paragraph, where the segment rose, does not.
  - e76 Broadcom, both segments up on demand: counts.
  - e64 Tesla, cost of sales up on deliveries: does not explain gross profit rising.
  - That gives 11 of 14, 0.79, a hair under the 0.8 bar.
- **"Nothing found":** right in 1 of 6 cases. In five, the MD&A states a cause the wording rules missed.

The bar stays where it was set. Phase A does not ship as a panel on its own: it becomes the retrieval stage for phase B (ADR 0017), where the model chooses among a wider set of candidate paragraphs under a quote lock. For the next rubric, record that a part's cause counts only when the part moved the same way as the figure asked about.
