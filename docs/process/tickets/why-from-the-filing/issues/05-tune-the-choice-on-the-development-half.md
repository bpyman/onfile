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

**Status:** resolved

## Answer

Shipped, calling no model:

- **The basis asked** (`explanation._compares_on`):
  - A sequential question needs a paragraph that compares with the quarter before. Either it says so, or a sentence names two adjacent quarters.
  - A year-over-year question drops only paragraphs that compare sequentially and nothing else.
- **The year to date** (`_only_for_the_year_to_date`): a paragraph is out when every causal sentence is about the year to date only. A sentence's period is the one it names, or else the last one named before it. "Both periods" and "three and six months" count for the quarter.
- **`basis_not_discussed`:** a sequential question that finds nothing gets the paragraphs a year-over-year question would get, as `ManagementExplanation.alternative`. The evaluation scores it as "nothing found".
- **Headings:** a block of fewer than eight words, or with no verb, is never chosen.
- **Cash balance and financing:** a new word family, `cash_balance`, covers the cash balance, liquidity, and financing and investing activities. No metric maps to it, so a paragraph about it is about another metric for every covered metric.
- **Cash flow and capex:** operating cash flow, capex and free cash flow are commented out of `_METRIC_FAMILY`, with the reason, and return `metric_not_covered`. Their words stay in place, so a cash-flow paragraph is still about another metric.
- **Weights:** unchanged. On the development half, every hit is already in first place (precision at 1 equals precision at 3). None of the remaining misses had a paragraph labelled as a cause among those that could be chosen, so no reweighting gains anything by the committed labels.

**The development half, by the committed labels** (claude-opus-5-5, ticket 03). Labels are matched to paragraphs by exact text within the case.

| | Shown | Precision at 1 | Precision at 3 | Nothing found right |
| --- | --- | --- | --- | --- |
| Before, all 20 dev cases | 13 of 20 | 0.23 (3 of 13) | 0.23 (3 of 13) | 0.57 (4 of 7) |
| Before, the 16 kept | 11 of 16 | 0.27 (3 of 11) | 0.27 (3 of 11) | 0.40 (2 of 5) |
| After, the 16 kept | 7 of 16 | 0.43 (3 of 7) | 0.43 (3 of 7) | 0.67 (6 of 9) |

- **Unlabelled paragraphs:** none. Every development paragraph now shown, including the baseline's, already has a label.
- **No paragraph about another metric is first.**
- **Sequential questions with nothing to find:** e03, e09, e12 and e16 now get `basis_not_discussed`.
- **Misses left:**
  - e01: Micron's sequential paragraph only names DRAM and NAND sales. Its price bullets name no basis.
  - e02: UnitedHealth has no cause to find, yet shows a portfolio-actions paragraph and a return-on-equity definition.
  - e06: Nvidia's "approximately flat sequentially" is labelled not a cause. The same judge's MD&A label points at it.
  - e21: Apple's "various factors, none of which were significant".
- **"Nothing found" that is wrong:** e05, e13 and e19. Their causes sit in paragraphs about another metric.

**The cases** (`explanation-cases.json`):
- `seeds` are `{"dev": 20261023, "held-out": 20261024}`, and `notes` say the first held-out half leaves the evaluation.
- **Development set:** the first draw's 16 development cases whose metric is still covered. e11, e15, e17 and e18 (cash flow and capex) are out, so "keep the 20" became 16.
- **Held-out set:** e41 to e60, drawn fresh by `draw_held_out` from the narrowed pool. It is 10 year over year and 10 sequential. It shares no (company, metric, basis) with either half of the first draw, and no (company, metric) is drawn twice. Tests check that it is reproducible and does not overlap.
- **Draw function:** `draw_cases` keeps the first draw's metric list, so the first draw still reproduces from its seed.

**Candidates:**
- **Paragraph ids:** each paragraph's id is now its place in the MD&A (`e04-m21`), not the order it was shown (`e04-p1`). A changed choice can no longer inherit another paragraph's label on a resumed judge run.
- **Carrying labels:** `carry_judgements`, and `judge --carry-from <old candidates>`, move saved labels to the same text within the same question.
- **Not inspected:** the held-out candidates' paragraphs were not opened. Only counts were checked: 21 of 36 cases find nothing.

**Next, a person's run:**
1. `git show 5f78089:docs/evaluation/explanation-candidates.json > old.json`
2. `uv run python -m financial_analyst_agent.explanation_evaluation judge --carry-from old.json` judges only the 20 new held-out cases, because every development label carries.
3. Run `score`.

Until then, the committed `explanation-labels.json` and `explanation.md` describe the first run, and `score` against them fails, because the ids are new.
