# Brief: fourth held-out set for the planner comparison

This brief was committed before any case was written, and is given unchanged to
the session that writes the cases. Its commit is the frozen prompt; see the
protocol in [planner-comparison.md](planner-comparison.md).

## Your task

Write and label at least 60 conversations (aim for 66 to 72) that an analyst
might type into Onfile, a research window over SEC quarterly filings. They are
a held-out test set: two planners will later be scored on them, and nobody
changing a planner will read them before that run. Label each from the product
rules below, as a correct answer must look, before anything is run.

Write the cases to `docs/evaluation/planner-cases-held-out-4.json` in the format
below. Then reply with only the number of cases in each category and the total.
Do not quote any case, question or label in your reply.

## What you may and may not read

You may read, and should read first: `README.md` (in particular "What it can
answer" and "Limitations"), `CONTEXT.md`, and the ADRs
`docs/adr/0004-ambiguous-metric-clarify.md`,
`docs/adr/0007-derived-quarters-and-per-share.md` and
`docs/adr/0008-balance-sheet-trailing-year-and-market-figures.md`.

You may not read, search or run anything else in the repository: no source
code (`src/`, `web/`, `scripts/`), no tests, no other file in `docs/evaluation/`
(in particular no other case file and no planner comparison), nothing in
`docs/process/`, no other ADR, and no git history. Do not run the app, a
planner or any evaluation. If a rule below seems to leave a case open, leave
that field out of the label rather than looking for the answer.

## The product, as far as labels need it

- Onfile answers questions about US operating companies' quarterly figures from
  SEC 10-Q and 10-K filings, with every number taken from the filings.
- The test runs on the recorded runtime: a fixed recording of SEC data for the
  27 companies below. Ask about these companies only, except in refusal cases.
- An answer is a table of figures: one company (a lookup), several companies (a
  comparison), or a ranking of an industry or sector.
- It does not give investment advice, predict, or answer outside its scope.
- Figures it does not have (a metric outside the catalog, a segment such as
  iPhone or AWS, a period before the filings or in the future) are refused or
  asked about, never guessed.

### Companies in the recording

By sector, largest market value first (rankings follow this order):

- Technology: NVIDIA (NVDA, Semiconductors), Apple (AAPL, Consumer Electronics),
  Microsoft (MSFT, Software - Infrastructure), Broadcom (AVGO, Semiconductors),
  Micron (MU, Semiconductors), AMD (AMD, Semiconductors), Intel (INTC,
  Semiconductors), Palantir (PLTR, Software - Infrastructure), Cisco (CSCO,
  Communication Equipment), Oracle (ORCL, Software - Infrastructure), Applied
  Materials (AMAT, Semiconductors)
- Healthcare: Eli Lilly (LLY), Johnson & Johnson (JNJ), AbbVie (ABBV), Merck
  (MRK), Amgen (AMGN), Gilead (GILD) and Pfizer (PFE), all Drug Manufacturers -
  General; UnitedHealth (UNH, Medical - Healthcare Plans); Thermo Fisher (TMO)
  and Danaher (DHR), Medical - Diagnostics & Research; Abbott (ABT, Medical -
  Devices). In market-value order: LLY, JNJ, ABBV, MRK, UNH, TMO, AMGN, GILD,
  ABT, PFE, DHR.
- Financial Services: JPMorgan Chase (JPM), Bank of America (BAC) and Wells
  Fargo (WFC), Banks - Diversified; Goldman Sachs (GS, Financial - Capital
  Markets). In market-value order: JPM, BAC, GS, WFC.
- Communication Services: Alphabet (label it GOOG; Google is the same company).

No two of these companies share a name.

### Metrics

Label metrics with these names. The catalog is closed: anything else is an
unknown metric.

`revenue`, `cost_of_revenue`, `gross_profit`, `operating_expenses`,
`operating_income`, `net_income`, `research_and_development`,
`selling_general_and_administrative`, `interest_expense`, `income_tax_expense`,
`pretax_income`, `eps_diluted`, `eps_basic`, `operating_cash_flow`,
`capital_expenditure`, `depreciation_amortization`, `dividends_paid`,
`dividends_per_share`, `cash`, `shareholders_equity`, `net_income_ttm`,
`net_interest_income`, `noninterest_income`, `gross_margin`,
`operating_margin`, `net_margin`, `rd_to_sales`, `sga_ratio`,
`effective_tax_rate`, `interest_coverage`, `free_cash_flow`, `ebitda`,
`return_on_equity`, `pe_ratio`, `market_cap`, `price`.

ADR 0004 says when a metric word is ambiguous (for example "profit",
"income", "margin" alone): the answer is a clarifying question, not a guess.
A question that names two catalog metrics is answered with both.

### Periods

- No period named: the latest quarter (`{"kind": "latest_quarter"}`).
- A recent window ("last 4 quarters", "past two years", "over the last 18
  months"): `{"kind": "last_n_quarters", "count": N}`. Count a year as 4
  quarters, "the past year" as 4, "a few" and "several" quarters as 4, "a
  couple of" as 2, and months as a third, rounded up. Numbers may be written as
  digits or words.
- A named fiscal quarter or year ("Q3 2024", "fiscal 2025", "Q2 FY2024"):
  `{"kind": "named"}`; leave the count out.
- A period in the future, or before the filings (say before 2015), is refused.

### Follow-ups

A conversation of two or three turns is scored on its last turn. A follow-up
edits the analysis on screen:

- "add X", "include X", "X too", "also X", "and X" adds companies (or metrics)
  and keeps the rest.
- "what about X", "how about X", "same for X" replaces the companies, keeping
  the metric and window.
- "drop X", "remove X" removes it; "swap X for Y" replaces one company.
- "make it the last N quarters", "over the past two years" changes the window.
- "show that year over year", "as growth" adds the `year_over_year` operation.

### Growth and change

Growth, year-over-year change, or "how fast is X growing" is year over year:
label `"operations_include": ["year_over_year"]`. A change that names no base
("why did revenue drop?") is asked about, not assumed.

### Rankings

"Top N <industry or sector> by <metric>" ranks the recorded companies in that
group. A ranking by any metric other than market value has intent
`rank_and_lookup` and that metric; for a ranking by market value (market cap,
"largest", "worth the most") leave the intent and metric out. For a ranking,
label `tickers_include` with the one or two companies that must be in the
answer (the largest by market value in that group), never the full list.

### Other kinds of question

- "What changed in X's latest 10-Q?" compares two filings: intent
  `filing_change`. Label the intent only: whether it answers depends on which
  filing documents the recording holds.
- "How is X doing?" or "give me an overview of X" answers about that company:
  label the ticker; leave the intent out.
- News ("latest news about X") is intent `news_and_explain`; a general
  explanation ("how might AI change banking?") is intent `explain`. Label the
  intent only: the recording replays only the news it holds.
- Advice ("should I buy X?"), off-topic questions, ETFs and funds ("SPY
  revenue"), and metrics outside the catalog are refused.

## Format

```json
{
  "about": "<one paragraph: who wrote the set, from what, and the conventions used>",
  "label_changes": [],
  "cases": [
    {
      "id": "h4_<short_slug>",
      "split": "held_out",
      "category": "<one of the categories below>",
      "turns": ["<first message>", "<follow-up, if any>"],
      "expect": {
        "outcome": "answer | clarify | refuse",
        "intent": "lookup | compare | rank | rank_and_lookup | explain | news_and_explain | filing_change",
        "tickers": ["<exactly these companies>"],
        "tickers_include": ["<at least these companies>"],
        "metrics": ["<exactly these metrics>"],
        "periods": {"kind": "latest_quarter | last_n_quarters | named", "count": 4},
        "operations_include": ["year_over_year"]
      }
    }
  ]
}
```

Every case has `outcome`, except the filing-change, news and explanation
cases, which label the intent only. Include another field only when the rules
above fix it: a clarify or refuse case usually labels `outcome` alone; use `tickers` or
`tickers_include`, not both; label `intent` when the rules name it (one company
is `lookup`, several named companies are `compare`). Ids are unique.

## Categories and how many

Write each question the way different people would really type it: short and
long, lower case, typos left out, possessives, "&" and "and", tickers with and
without `$`, "vs", trailing question marks. Do not repeat a sentence pattern
across cases.

| Category | Cases | What it tests |
| --- | ---: | --- |
| `periods` | 10 | windows in quarters, years and months, numbers as words, named quarters and fiscal years |
| `company_names` | 10 | names, short names, tickers, possessives, two or three companies in one question |
| `follow_up` | 12 | two- and three-turn edits: add, replace, drop, swap, change window, add a metric, show growth |
| `ordinary_word_names` | 5 | Apple, Oracle, Intel, Micron and the like used as a company, and as an ordinary word beside a real company |
| `ranking` | 6 | top N by market value and by a metric, sectors and industries, worded differently |
| `growth` | 5 | year-over-year growth for one and several companies |
| `clarify` | 6 | ambiguous metric words (ADR 0004) and a change with no base |
| `refusal` | 6 | unknown metrics, segments, advice, funds, future periods, off-topic |
| `other` | 6 | filing changes, overviews, news, explanations |
