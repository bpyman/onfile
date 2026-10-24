# Product review, 23 October 2026

The app is strongest on trust: every figure is code-owned and sourced, and fiscal calendars and refusals are handled well. Its weak point is that it sometimes answers a slightly different question without saying so, which matters more for this app than for most. The recommendations start there, then add the capabilities analysts most often ask for and don't get.

Sources: five questions on the live app; about 165 analyst questions run offline through the planner; the docs and ADRs; and about 95 earlier feature ideas collected from the repo and past sessions.

## Do first

1. **Merge the snapshot refresh.** The stale-snapshot flag turns on after 30 days. *Done: PR #109; the hosted snapshot is 12 October 2026.*
2. **Merge `numeral-lock-false-positives`** (quarter labels read as figures). *Done: PR #110.*
3. **Cap OpenAI spending.** *Done: PR #111, `OPENAI_DAILY_BUDGET_USD`, $5 a day by default.*

## Tier 1: places where an answer looks right but isn't

1. **Show what was applied, and what wasn't.** "Software companies that grew revenue more than 20% while staying profitable" returned the top 10 software companies by market cap, including three below 20%, with no note. Others did the same:
   - "FCF yield" returned plain free cash flow.
   - "5-year CAGR" returned one quarter.
   - "Next earnings date" returned net income.
   - "Analyst estimates" returned reported EPS.
   - "Stock performance" returned an overview.
   - "China share of revenue" returned total revenue.
   - "Rank by growth" was ordered by revenue.
   - "…and tell me why it grew" dropped the why.

   *Done: [ADR 0016](../../../adr/0016-an-answer-names-what-it-does-not-apply.md), [ticket 01](issues/01-name-what-is-not-applied.md).*
2. **Flag unusual figures in code.**
   - Target's gross margin jumps to 33.7% in its latest quarter, against 26–30% for three years.
   - Alphabet's recorded net margin is 93.7%, because pretax income ($138.75 B) exceeds revenue through non-operating gains.

   Both appear without comment. Code could add notes such as:
   - "net income exceeds operating income by $X B (non-operating items)";
   - "highest in 12 quarters, 2.8 standard deviations above the company's mean";
   - "the cost line uses a different concept than last quarter".
3. **Make the headline answer the question asked.** "How has Costco's gross margin trended over 3 years?" got a headline about the latest quarter. A code-written trend sentence would answer it, e.g. "Costco held between 12.5% and 13.1% across 12 quarters; Target ranged 26.0–33.7%…". A quarter-over-quarter question also gets a year-over-year headline.

## Tier 2: what analysts ask for most

4. **Answer "why" by quoting the filing.**
   - Add questions over a filing section (MD&A, risk factors, business), answered with quoted passages and the accession number and section.
   - Add a quote lock: every quoted sentence must appear word for word in the filing, as the numeral lock checks figures.
   - Show a "Management's explanation" panel beneath a figure.
   - The PRD put filing full-text search out of scope because of the deadline.
5. **Balance sheet, annual totals and CAGR, all from SEC.**
   - Balance-sheet lines: total assets, liabilities, debt and shares outstanding (cover page).
   - Ratios built from them: net debt, debt-to-equity, current ratio, working capital, book value per share.
   - Fiscal-year totals from the 10-K, and CAGR computed in Decimal.
6. **Screening across the full company list.** Use SEC's Frames API to pick which companies pass a filter, then fetch the survivors' figures through the normal path so each keeps its own filing. Check whether Frames results carry the accession number (`accn`); ADR 0007's wording suggests they don't.
7. **A company list that doesn't need FMP.**
   - Take membership and exchange from SEC's `company_tickers_exchange.json`, which also fixes the exchange-mover gap.
   - Rank by revenue or public float from SEC.
   - Keep market-cap figures labelled with their date.
   - Then add P/S, EV/EBITDA, FCF yield and dividend yield.

## Tier 3: bigger bets

8. **Fact-check a claim.** Paste a sentence from an article or earnings call; the app marks it supported, contradicted or not verifiable from filings, with sources.
9. **Earnings-day briefs.** When a large company files a 10-Q, build a one-page brief automatically:
   - the key figures against a year earlier;
   - the filing diff;
   - any unusual-figure notes;
   - the quoted MD&A explanations.

   The "latest filings" feed already drives cache refresh, so it can trigger the briefs. Publish them as a page or RSS feed.
10. **A remote MCP server with full feature parity:** add periods, windows and the filing diff, and host it for Claude Desktop and ChatGPT users.
11. **A filing-event timeline:** 8-K items and Form 4 activity from the submissions data already fetched.
12. **More coverage, roughly in order of value:**
    - business segments, from the filing's inline XBRL;
    - 20-F filers under IFRS (TSMC, ASML);
    - bank and insurer measures (net interest margin, CET1, medical loss ratio).

## Presentation fixes seen while using it

- **Multi-company trend tables:** these come out as a 36-row long table; a quarter-by-company grid would read better.
- **Chart alignment:** the chart lines up raw dates, so in text mode it alternates "no value" points, and Walmart's Jul 31 quarter is plotted at Aug 1. Align on fiscal or calendar quarter.
- **Evidence list:** 198 items in one flat list; group them by company and figure. Walmart's revenue appears twice per period.
- **Clarification buttons:** they show internal ids ("year_over_year") under the labels.
- **Landing page:**
  - At short window heights the question box covers the guided stories.
  - The capability list stops at three, so the news and "How is Nvidia doing?" lines never show.
- **Follow-up bugs:**
  - "compare to its peers" adds a company row called "its peers".
  - "show it as a chart" can't find a metric.
  - "Apple 10-K" gets "can't look up 'K'".
  - "Stripe" quietly becomes Stride.
- **Share links:** they replay the questions, so a shared answer can change. A frozen, read-only answer link would make "cite this answer" reliable.

## Evaluation upgrades

- **Test on real questions:** log visitor questions anonymously, with a privacy note, and build held-out set 6 from them.
- **Catch the right figure given to the wrong company:** check each figure against the company named in the same sentence. Add the news citation check the docs already call "the next step".
- **Extend the filing check** to derived Q4, ratios and rankings.
- **Show visitors the evaluation** with a "How we test" page in the app.

## Not proposed again

These were rejected earlier:
- open tool-chaining on the number path, and model arithmetic;
- forecasts, valuation models and advice;
- vendor figures as a source of truth;
- stale-while-revalidate caching, and architecture candidate #3.

The bull/bear evidence matrix also stays out: it is too close to advice.

## Suggested order

1. The applied / not-applied check. *Done.*
2. Answering "why" from the filing, with a quote lock.
3. Balance-sheet lines, the SEC-based company list and screening.
