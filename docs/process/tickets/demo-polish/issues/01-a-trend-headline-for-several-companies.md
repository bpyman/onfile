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

**Status:** ready-for-agent
