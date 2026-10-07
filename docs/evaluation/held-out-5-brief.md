# Brief: fifth held-out set for the planner comparison

> **Draft, not frozen.** Before it is frozen, a blind session labels a handful
> of throwaway probe questions from this brief alone, and every probe whose
> label differs from the app is settled: the brief is made clearer, or the app
> is fixed. Then this note is removed, and the commit that removes it is the
> frozen prompt. No case is written from a draft.
>
> Two rounds of 30 probes ran on 6 October 2026: the brief and the README's
> "How a question is read" were made clearer after each, and the app gaps they
> found are tickets in `brief-5-probe-gaps`. Those are fixed before the freeze,
> so the set measures wording nobody has seen rather than gaps already known.

This brief was committed before any case was written, and is given unchanged to
the session that writes the cases. Its commit is the frozen prompt; see the
protocol in [planner-comparison.md](planner-comparison.md).

## Your task

Write and label at least 140 conversations (aim for 150 to 170) that an analyst
might type into Onfile, a research window over SEC quarterly filings. They are a
held-out test set: planners will later be scored on them, and nobody changing a
planner will read them before that run. Label each from the product rules below,
as a correct answer must look, before anything is run.

Write the cases to `docs/evaluation/planner-cases-held-out-5.json` in the format
below. Then reply with only the number of cases in each category and the total.
Do not quote any case, question or label in your reply.

## What you may and may not read

You may read, and should read first: `README.md` (in particular "What it can
answer", **"How a question is read"** and "Limitations"), `CONTEXT.md`, and the
ADRs `docs/adr/0004-ambiguous-metric-clarify.md`,
`docs/adr/0007-derived-quarters-and-per-share.md` and
`docs/adr/0008-balance-sheet-trailing-year-and-market-figures.md`.

You may not read, search or run anything else in the repository: no source
code (`src/`, `web/`, `scripts/`), no tests, no other file in `docs/evaluation/`
(in particular no other case file, no planner comparison and no phrase
coverage), nothing in `docs/process/`, no other ADR, and no git history. Do not
run the app, a planner or any evaluation. If the rules leave a case open, leave
that field out of the label rather than looking for the answer.

## Where the rules are

**"How a question is read" in `README.md` is the rule for every default**: what
a question that leaves out a period, a base for a change, or which metric it
means is answered with, and what a follow-up does. Label from that table. This
brief adds only what a label needs that the README does not say: the companies
in the recording, the metric names, the label format and the categories. Where
this brief and that table seem to differ, the table wins.

Do not copy the README's examples verbatim. They show the rules; write each
question the way an analyst would phrase it, which is what this set tests. Where
an analyst would naturally ask much as an example does, ask it that way.

## The product, as far as labels need it

- Onfile answers questions about US operating companies' quarterly figures from
  SEC 10-Q and 10-K filings, with every number taken from the filings.
- The test runs on the recorded runtime: a fixed recording of SEC data for the
  27 companies below. Ask about these companies only, except in refusal cases.
- An answer is a table of figures: one company (a lookup), several companies (a
  comparison), or a ranking of an industry or sector.
- It does not give investment advice, predict, or answer outside its scope.
- Figures it does not have (a metric outside the catalog, a named period
  before 2015 or in the future) are refused or asked about, never guessed. A
  `since` window answers whatever year it names, at most 40 quarters. A segment
  (iPhone, AWS, Google Cloud) shows the company-wide figure with a note, as the
  README says: label it as an answer with the company-wide metric.
- The recording holds each company's 10-Qs and 10-Ks from about mid-2024 to
  mid-2026; for the four banks, from the third quarter of 2025. Name quarters
  and fiscal years inside that span. A named period between 2015 and the start
  of the span may simply be missing from the recording, so do not ask one.

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

No two of these companies share a name. Informal names analysts use (BofA,
JPM, Lilly) are fair: label the company meant.

### Metrics

Label metrics with these names. The catalog is closed: anything else is an
unknown metric.

`revenue`, `cost_of_revenue`, `gross_profit`, `operating_expenses`,
`operating_income`, `net_income`, `research_and_development`,
`selling_general_and_administrative`, `interest_expense`, `income_tax_expense`,
`pretax_income`, `eps_diluted`, `eps_basic`, `operating_cash_flow`,
`capital_expenditure`, `depreciation_amortization`, `dividends_paid`,
`dividends_per_share`, `cash`, `shareholders_equity`, `total_equity`,
`net_interest_income`, `noninterest_income`, `net_income_ttm`, `gross_margin`,
`operating_margin`, `net_margin`, `rd_to_sales`, `sga_ratio`,
`effective_tax_rate`, `interest_coverage`, `free_cash_flow`, `ebitda`,
`return_on_equity`, `pe_ratio`, `market_cap`, `price`.

Net interest income and noninterest income are bank figures: ask them of the
banks.

### Conversations, as labels

A conversation of two or three turns is scored on its last turn: label the
analysis on screen after it. Its intent follows the companies then on screen:
one company is `lookup` and several are `compare`, however many metrics are
shown and whatever the first turn asked.

### Periods, as labels

- Label the period of every answer, the latest quarter included; a ranking's
  is the latest quarter. A figure that is not a quarter's (a balance-sheet
  amount, market cap, price, P/E, a trailing-year figure) asked with no window
  is the latest quarter too.
- The latest quarter: `{"kind": "latest_quarter"}`.
- A window of recent quarters: `{"kind": "last_n_quarters", "count": N}`, with N
  as the README's table counts it. For a window `since` a year, leave the count
  out: it depends on the recording's latest quarter.
- A named fiscal or calendar quarter or year: `{"kind": "named"}`; leave the
  count out. The label records only the kind, not which period.
- A trailing-year figure (`TTM net income`): label the metric `net_income_ttm`
  and the period the latest quarter. A figure with no trailing-year form (`TTM
  revenue`) is its latest 4 quarters: `last_n_quarters`, count 4.
- A period in the future, or before 2015, is refused.

### Changes, as labels

A year-over-year change, growth included, is labelled
`"operations_include": ["year_over_year"]`, and a quarter-over-quarter change
`"operations_include": ["sequential"]`.

### Rankings, as labels

A ranking that shows a metric, whether ordered by it (`by`) or by market value
(`and their`), has intent `rank_and_lookup` and that metric. For a ranking by
market value alone (market cap, "largest", "worth the most") leave the intent
and metric out. Never label the intent `rank`. Label `tickers_include` with the one company that must be in
the answer, the largest by market value in that group, never the full list. A ranking with no group ranks every recorded company:
its largest is NVIDIA.

### Other kinds of question

- "What changed in X's latest 10-Q?" compares two filings: intent
  `filing_change`. Label the intent only: whether it answers depends on which
  filing documents the recording holds.
- An overview ("How is X doing?"): label `outcome`, the ticker and the period
  (the latest quarter, or the window named); leave the intent and metrics out.
- News ("latest news about X") is intent `news_and_explain`; a general
  explanation ("how might AI change banking?") is intent `explain`. Label the
  intent only: the recording replays only the news it holds.
- Advice ("should I buy X?"), off-topic questions, ETFs and funds ("SPY
  revenue"), and metrics outside the catalog are refused.

## Format

```json
{
  "about": "<one paragraph: who wrote the set, from what, and the conventions used>",
  "writer": "<the model that wrote and labelled the cases, as its maker names it>",
  "label_changes": [],
  "adjudications": [],
  "cases": [
    {
      "id": "h5_<short_slug>",
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
        "operations_include": ["year_over_year | sequential"]
      }
    }
  ]
}
```

Every case has `outcome`, except the filing-change, news and explanation
cases, which label the intent only. Include another field only when the rules
fix it: a clarify or refuse case labels `outcome` alone. Give each clarify or
refusal case one reason to ask or refuse, and do not write a case whose outcome
the rules leave open. Lists (`tickers`, `metrics`) compare as sets: order does
not matter; use `tickers`
or `tickers_include`, not both; label `intent` when the rules name it (one
company is `lookup`, several named companies are `compare`). Ids are unique.

## Categories and how many

Write each question the way different people would really type it: short and
long, lower case, typos left out, possessives, "&" and "and", tickers with and
without `$`, "vs", abbreviations analysts use, trailing question marks. Do not
repeat a sentence pattern across cases.

| Category | Cases | What it tests |
| --- | ---: | --- |
| `metric_words` | 16 | catalog metrics in the words analysts use for them: synonyms, abbreviations, longer phrases |
| `periods` | 22 | windows in quarters, years and months, numbers as words, trailing twelve months, named quarters and fiscal years |
| `company_names` | 20 | names, short names, tickers, possessives, two or three companies in one question |
| `follow_up` | 26 | two- and three-turn edits: add, replace, drop, swap, change window, add or swap a metric, show growth |
| `ordinary_word_names` | 10 | Apple, Oracle, Intel, Micron and the like used as a company, and as an ordinary word beside a real company |
| `ranking` | 14 | top N by market value and by a metric, sectors and industries, worded differently |
| `growth` | 12 | year-over-year and quarter-over-quarter change, with and without a period, for one and several companies |
| `clarify` | 14 | ambiguous metric words (ADR 0004) and a change with no base |
| `refusal` | 14 | unknown metrics, segments, advice, funds, future periods, off-topic |
| `other` | 12 | filing changes, overviews, news, explanations |
