# A comparison over several quarters gets a headline about the trend

From the product review (`docs/process/tickets/product-review/review.md`, Tier 1 item 3). On the live demo, "How has Costco's gross margin trended over the last 3 years, and how does it compare with Walmart and Target?" got the headline "Of these 3 companies, Target reported the highest gross margin, 33.7% †, and Costco Wholesale the lowest, 12.7% †, each in its latest quarter." That headline says nothing about how anything trended. On the recorded runtime, "Compare Apple and Microsoft gross margin over the last 8 quarters" gets "Microsoft's gross margin was 67.2% †, ahead of Apple's 50.1%, each in its latest quarter."

**Files (this ticket only):** `src/financial_analyst_agent/presentation.py` (`comparison_headline`, `_trend_headline`), `tests/test_presentation.py` or the conversation tests that pin headlines, the README only if it quotes a headline that changes.

**What to build:** When a comparison of one metric shows two or more companies with three or more quarters each, the headline describes each company's path over the window instead of only the latest quarter:

- Each company gets a clause built from the table's own formatted amounts: where it started and ended, as `_trend_headline` writes for one company. For example: "Over 8 quarters to Jun 30, 2026, Apple's gross margin rose from 46.3% to 50.1% and Microsoft's from 68.7% to 67.2% †". The verb follows the direction ("rose", "fell", "was unchanged at").
- Where a company's latest quarter is the highest or lowest in its window, say so ("its highest in the window").
- Keep the sentence short. With more than four companies, fall back to today's leader/trailer headline.
- Several metrics, a ranking, and changes (growth or YoY) keep their current headlines.
- Every amount in the sentence must be one the table shows, formatted the same way, with † where the table has it. No arithmetic beyond choosing first, last, highest and lowest.

**Acceptance:**
- A recorded two-company, 8-quarter gross-margin comparison gets a headline naming both companies' start and end values, with a test that pins it.
- One-company trends and rankings keep their existing headlines (existing tests unchanged).
- `compare_answers.py --against master` shows only comparison-over-a-window conversations changing, and only in `.headline`; name them in the Answer.

**Blocked by:** None — can start immediately

**Status:** resolved

## Answer

`comparison_headline` hands a comparison (not a ranking) of one amount over two to four companies,
each with three or more quarters, to a new `_trends_headline`. It names each company's first and
last amount in the table's own cells (with † where the cell has it), "rose" / "fell" / "was
unchanged at" (unchanged when the two cells read the same), and ", its highest in the window" or
", its lowest" where the latest quarter is above or below every earlier one and no earlier cell
reads the same. Companies come in table order. Five or more companies, rankings, changes and
several metrics keep their headlines; one company keeps `_trend_headline`.

The window opens the sentence: "Over 8 quarters to Jun 30, 2026," when every company's latest
quarter ends on one date; "Over each company's last 8 quarters," when the dates differ (Apple's
quarter ends Jun 27, Microsoft's Jun 30, so the ticket's "to Jun 30, 2026" would misdate Apple's);
"Over the quarters shown" when the companies show different numbers of quarters. With three or four
clauses and an appositive, the clauses are joined with semicolons.

Recorded: "Compare Apple and Microsoft gross margin over the last 8 quarters" → "Over each
company's last 8 quarters, Apple's gross margin rose from 46.2% † to 50.1%, its highest in the
window, and Microsoft's fell from 69.4% to 67.2% †, its lowest." (pinned in
`tests/test_presentation.py`; unit tests in `tests/unit/test_answer_card.py` pin the dated window,
"unchanged", highest/lowest and the five-company fallback).

`compare_answers.py` (against HEAD, the previous commit): 53 of 893 conversations differ, all in
`.answers[n].headline` only, and every one is a comparison of one amount over a window of several
quarters for two or three companies: the two-company follow-ups that default to the last 4 quarters
("Apple | add Microsoft" and its phrasings, "Apple and Microsoft | remove Microsoft" and the like,
whose first answer compares both), the "AAPL vs MSFT … over the past two years / 18 months / fiscal
2025" and "Nvidia, AMD and Intel … for the last 18 months / fiscal 2025" phrase cases, the
evaluation cases with a two-company window (`calendars_differ`, `h2_*`, `h3_*`, `h4_fu_*`,
`ho_pfe_mrk_six_quarters`, `follow_up_metric_and_company`), and the extras "Tesla vs GM revenue
last 4 quarters", "Apple and Microsoft revenue last 4 quarters / fiscal 2025 / since fiscal 2025",
"Apple revenue | add Tesla | last 4 quarters" and "Apple, Microsoft and NVIDIA net margin last 6
quarters". The README quotes no headline that changed.
