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

**Status:** ready-for-agent
