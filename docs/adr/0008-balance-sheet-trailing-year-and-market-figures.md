# Balance-sheet amounts, trailing years and market figures

> **Extends [ADR 0007](0007-derived-quarters-and-per-share.md).** Everything stays deterministic, in Decimal, and traceable to the filings or the snapshot. Two new derivations join the two in 0007, and they follow the same labelling rules.

Analysts ask for P/E, return on equity, EBITDA, share price, cash and dividends as soon as they have seen revenue and margins. Until now each of these got "I can't look up X yet". None of them is a single standalone-quarter duration fact. Cash and equity are balance-sheet amounts at a date. Return on equity and P/E need a year of earnings. EBITDA needs depreciation, which is a cash-flow item. Price and market cap come from the market, not from a filing.

## Decision

**Balance-sheet amounts** (`cash`, `shareholders_equity`) are the instant a 10-Q or 10-K reports at its own report date, from that filing. They have no start date. The row's period starts and ends on that date, and the window shows it as "At Jun 27, 2026".

**Trailing year** (`net_income_ttm`, used only as a formula component; *revised:* also asked for itself, as "TTM net income", "LTM net income" or "trailing twelve month net income", and shown as one amount, not a quarter) is the four quarters ending on a report date:

- After a 10-K, it is the fiscal-year amount the 10-K reports.
- After a 10-Q, it is last fiscal year (10-K) plus this year to date (10-Q) minus the same months a year earlier (the comparative in that 10-Q). The fiscal year must end the day before the year to date starts, within a week. The earlier amount must end a year before, within a week, and cover the same length, within a week. Only a 10-K's year counts, because proxy statements tag net income too.

A derived trailing year is marked † like any derived quarter, and all three facts are evidence.

**New figures**

| Metric | Built from | Unit |
|---|---|---|
| `cash` | `CashAndCashEquivalentsAtCarryingValue`, else the total including restricted cash | USD, at the date |
| `shareholders_equity` | `StockholdersEquity`, else the total including noncontrolling interest | USD, at the date |
| `depreciation_amortization` | the cash-flow statement's D&A line. For filers without one (Microsoft, Alphabet), `Depreciation` plus `AmortizationOfIntangibleAssets` for the same period | USD, derived like cash flow |
| `dividends_paid` | `PaymentsOfDividendsCommonStock`, `PaymentsOfDividends` | USD, derived like cash flow |
| `dividends_per_share` | paid, else declared, per share (*revised:* first written as declared, else paid; Walmart declares the year's dividend in one quarter, so declared first showed $0.00 in the others). A quarter with none declared, after one earlier in the year, reads "No dividend declared this quarter" rather than $0.00: the filing reads the same for a year's dividend declared at once and for a suspension. When a window shows a declared quarter followed by such quarters, a note says the declared figure may cover the year, and, beside other companies, may be up to four quarters' worth | USD/share, never derived |
| `ebitda` | operating income plus D&A | USD |
| `return_on_equity` | trailing-year net income divided by equity at the year's end | percent |
| `pe_ratio` | snapshot market cap divided by trailing-year net income | multiple |
| `price` | the snapshot's share price, quoted with its market cap | USD/share |

"Dividends" alone asks which of the two dividend figures is meant, as "margin" does.

A formula whose component a company's filings do not report as a standalone quarter has no value, and the answer names the missing part (*revised 7 October 2026*, probe-round-3-gaps ticket 11): AMD reports depreciation only for the fiscal year and no cash-flow D&A line this reads, so its EBITDA is missing, and with it any change in it; Merck reports no operating income line. The cell reads "Missing fact" and a note says which part the filings lack, so a missing figure, and a missing change, never go without a word. Every component is read even after one is missing, so the note names each.

**Market figures come from the snapshot.** The snapshot holds one market cap and one price, both taken at its `as_of`. So P/E is given only for each company's latest trailing year. A past period's cell says "Latest period only" rather than dividing today's market cap by old earnings. A trailing-year loss gives "Not meaningful (loss)", not a negative P/E. The snapshot build now records FMP's price beside market cap. Snapshots built before that leave it out, and the price cell then says the fact is missing.

## Considered options

- **Annualise the quarter (net income × 4) for ROE and P/E.** Rejected: seasonal companies (retailers, Apple's holiday quarter) would swing wildly, and it is not what analysts quote.
- **Price divided by trailing diluted EPS for P/E.** Rejected: trailing EPS needs per-share subtraction, which ADR 0007 forbids. Market cap over trailing net income is the same ratio when the share count is steady, and it is computed only from amounts.
- **Average equity for ROE.** Deferred: year-end equity is the common simple definition. Averaging would need five balance sheets per row.
- **Fetch a live quote per question.** Rejected: an answer would change from minute to minute, and it would add a provider at request time. The snapshot is dated and cited.
