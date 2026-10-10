# Prompts and controls

Onfile uses a language model for two jobs: reading a question into a plan, and writing prose around results. It never uses the model to produce a number the analyst sees. Each of the five instructions below is paired with a mechanism outside the model that checks or replaces what the model returns, and each has been measured.

| Measure | Result | Source |
| --- | --- | --- |
| Planner accuracy, 160 held-out conversations written by another lab's model | Cascade 97%, rules 96%, LLM 94%; no difference significant (p = 0.22–0.73) | [Held-out set 5](evaluation/held-out-5-findings.md) |
| Planner calls sent to the model | 7% (36 of 549) | [Planner comparison](evaluation/planner-comparison.md) |
| Cost and median latency per planner call | Cascade $0.0002 and 1 ms; LLM planner $0.0035 and 1.1 s | [Planner comparison](evaluation/planner-comparison.md) |
| Altered or invented figures in model prose | 108 of 108 withheld; 108 of 108 true figures passed | [Numeral lock](evaluation/numeral-lock.md) |
| Everyday phrasings read as documented | 555 of 555; 14 would be routed to the model | [Phrase coverage](evaluation/phrase-coverage.md) |

## Division of labour

| Task | Owner | Check on the model |
| --- | --- | --- |
| Classify the question and propose a plan | Rules planner; the model only when the rules planner is unsure | Closed intent set, per-intent schema, strict structured output |
| Resolve company, metric and period | Code, from the analyst's own words, whichever planner proposed | The model's choices are proposals; resolution decides ([ADR 0004](adr/0004-ambiguous-metric-clarify.md), [ADR 0010](adr/0010-one-reading-of-names-and-windows.md)) |
| Retrieve and compute figures | Code: SEC XBRL facts, `Decimal` arithmetic, a dated ranking snapshot | The model has no access to this path |
| Write explanations, news briefs and filing summaries | The model | Numeral lock: any figure absent from the grounding withholds the text |

## The instructions

### Planner

Maps a new question to one of eight intents (lookup, compare, rank, rank-and-lookup, explain, news, research, filing change) and the fields that intent requires. Source: `planner.py`.

- **Each intent has its own schema.** The response format is a union of per-intent Pydantic models. A lookup without a company fails validation before any code runs.
- **Uncertainty has somewhere to go.** For an ambiguous measure the model returns the analyst's own word ("set metric to the user's word; code asks which they mean"); for a measure outside the catalog it returns the word unchanged and code refuses it by name. The model is never asked to guess.
- **The prompt names what code handles.** "Periods … and year-over-year growth are read from the question by code." The model may suggest a window length; the code's reading of the words takes precedence.
- **One prohibition.** "Never calculate, select, or invent financial values." The schema contains no field a value could occupy.

If the call fails, the cascade keeps the rules planner's plan.

### Follow-up

Maps a follow-up such as "add Tesla" or "show that year over year" to a patch on the analysis on screen. The current analysis is rendered as five plain lines and included in the instruction.

- **Mode is explicit.** `extend` adds to the analysis, `replace` starts a new one, and `null` means unclear; `null` produces a clarifying question rather than a guess.
- **Operations are a closed set.** Each is glossed with the words that request it, and the schema rejects anything else.
- **Code reads the words again.** Edit words ("instead", "too", "just"), periods and comparison bases are read by shared code for both planners, so a mis-patched follow-up is corrected where the wording is clear.

### Essays

Three instructions share one call; the grounding available to the turn selects the instruction. Source: `essay.py`.

| Instruction | Used for | Constraint |
| --- | --- | --- |
| Explain | Conceptual questions with no retrieval | No numerals |
| Analysis | Commentary beside a table | Only numerals present in the supplied results |
| News | Current events, from search results | Only facts and numerals in the results; citations as `[n]` |

The instructions are short because enforcement is in code. The **numeral lock** extracts every figure in the text and withholds the text if any figure is absent from its grounding, allowing for display formatting and rounding to at least two significant digits. Dates, citation markers and identifiers are excluded. The same lock applies to essays, filing-change summaries and the MCP server.

## When the model is consulted

The rules planner plans every turn. The model is called only when the rules plan shows one of five signs of uncertainty (`planner_cascade.unsure_reason`):

| Signal | Example |
| --- | --- |
| The plan carries a note: a corrected name, a word read as a company, an unanswered clause | "Apple and Micrsoft revenue" |
| A figures question with no catalog metric | "Apple churn" |
| A lookup or comparison with no company | "What is the EPS?" |
| A ranking of a group the snapshot does not know | "top 5 drone makers by revenue" |
| A follow-up that moves companies but cannot be placed as add or replace | (rare) |

A regression test fails if a phrasing that previously stayed with the rules planner would now be sent to the model, so the routing cannot widen unnoticed.

## What the evaluations changed

**1. A model on every turn did not improve accuracy.** The live demo originally planned every question with `gpt-5.6-terra`. On held-out set 4 it scored 88% against the rules planner's 85% (p = 0.50). The cascade matched 88% at one fifth of the cost and became the default ([ADR 0012](adr/0012-the-live-planner-is-a-rules-first-cascade.md)). Set 5, written by a different lab's model, confirmed the result.

**2. Some failures that looked like prompt problems were not.** "Goldman Sachs" proposed by the model resolved correctly, then displayed as "company not found"; "Coca-Cola" returned three bottlers. The cause was three resolvers reading the same name differently after planning. A longer alias list in the prompt was considered and rejected: it would not have reached the fault, and the rules planner would not have benefited. Names now have one resolver for both planners ([ADR 0010](adr/0010-one-reading-of-names-and-windows.md)).

**3. A flat schema admitted incomplete plans.** The first schema did not tie fields to intents, so a lookup with no company could reach execution. Per-intent schemas closed that path.

**4. The schema fell behind the pipeline.** As the rules planner gained capabilities (ordering a comparison, a company's peers, a filing's section and form), the model's schema did not, and some requests were silently dropped. The schema and both instructions were brought level, with tests that every schema passes strict mode.

**5. The first numeral lock rejected true figures.** It required an exact digit match, so "$22.97 B" against a grounding value of 22974000000 was withheld every time. The lock now accepts rounding at the precision written; altered and invented figures are still withheld.

## Known limits

- **The lock checks numbers, not meaning.** A true figure attributed to the wrong company passes (0 of 14 caught), as does a number written in words.
- **Prose quality is not yet measured.** The lock establishes that text invents no figures, not that it is useful. A rubric scored by a blind judge, frozen before the run, is the next evaluation.

## Reproducing

```text
uv run python -m financial_analyst_agent.planner_evaluation                       # rules planner; no API key needed
uv run python -m financial_analyst_agent.planner_evaluation --estimate --runs 3   # token estimate for an LLM run
uv run python -m financial_analyst_agent.phrase_coverage                          # fails if routing to the model widens
uv run python -m financial_analyst_agent.numeral_lock_evaluation
```

## Appendix: the instructions verbatim

As sent to the model, with the metric catalog expanded. Each is a single system message; the planner and follow-up responses are constrained by the schemas in `planner.py`.

<details>
<summary><strong>Planner (new question)</strong> (planner.py, 542 words)</summary>


```text
Map the user's question about US public companies' SEC filings to a Plan. Code fetches and computes
every number; you only choose what to look up. intent must be one of lookup, compare, rank,
rank_and_lookup, explain, news_and_explain, exploratory_research, filing_change. Use lookup for one
named company's reported figures, whether the latest quarter, a window of quarters, a named fiscal
quarter, or growth. Use compare for two or more named companies on a metric. Use rank for the top N
companies of an industry by market cap, with no other metric. Use rank_and_lookup for the top N of
an industry with a metric for each. Use explain for qualitative industry or AI-disruption questions
with no retrieval, and for a general question about how a figure works that names no company
(explain how a buyback affects EPS; why does operating margin matter; what is EPS). A figure with no
company (what's the EPS?) is a lookup with no company, not an explanation. Use news_and_explain for
a named company's current events (supply chain, what's going on). Use exploratory_research for
themes or open research that no figures answer and that need cited news rather than financial rows.
Use filing_change when the user asks what changed in a company's 10-Q or 10-K, its MD&A or its Risk
Factors. Set company. Set older_accession and newer_accession only when the user names accession
numbers; leave them empty for the latest filing, and code compares the latest with the one before.
Set section to mda, risk_factors, or both, as asked; both when the user names neither. Set form to
10-K when they ask about the annual report or 10-K, otherwise 10-Q. Set summarize true only when
they also ask for a summary. Name companies as the user wrote them ("Nvidia", "JPM"), never CIKs.
metric is one of: revenue, cost_of_revenue, gross_profit, operating_expenses, operating_income,
net_income, research_and_development, selling_general_and_administrative, interest_expense,
income_tax_expense, pretax_income, eps_diluted, eps_basic, operating_cash_flow, capital_expenditure,
depreciation_amortization, dividends_paid, dividends_per_share, cash, shareholders_equity,
total_equity, net_interest_income, noninterest_income, net_income_ttm, gross_margin,
operating_margin, net_margin, rd_to_sales, sga_ratio, effective_tax_rate, interest_coverage,
free_cash_flow, ebitda, return_on_equity, pe_ratio, market_cap, price. Use overview when the user
asks how a company is doing without naming a metric. When the user names a measure the list lacks,
set metric to their own words; code refuses it by name. When the measure is ambiguous (profit,
income, margin, earnings), set metric to the user's word; code asks which they mean. Give the first
metric when several are named; code reads the rest from the question. Periods (last N quarters, Q3
FY2025, since 2024) and year-over-year growth are read from the question by code. When the question
asks for a window of recent quarters or years, also set recent_quarters to its length in quarters (a
year is 4); code reads the wording first and uses yours only when it cannot. Otherwise leave it
null. Set order_by_metric true when the user wants companies ranked, sorted, or ordered by the
metric (top 5 banks by net income; which has the highest margin), false when they only want the
metric shown for each (top 5 banks and their net income). Set peers true, with the one company in
companies, when the user compares a company with its peers or competitors. For explain and
exploratory_research, set topic to the user question. Never calculate, select, or invent financial
values.
```

</details>

<details>
<summary><strong>Follow-up</strong> (planner.py, 256 words)</summary>


Followed by a blank line, `Current analysis spec:` and the analysis on screen as five lines (companies, ranked constituents, metrics, periods, operations).


```text
The analyst is continuing a conversation thread. The current analysis spec is provided. Map this
follow-up to a FollowUpPlan. Use intent spec_patch when they are editing or replacing the
quantitative analysis. mode=extend when they add/remove/swap companies or metrics, change the period
window, or ask for year-over-year on the current analysis. mode=replace when they start an unrelated
new analysis, including a complete lookup or compare question about different issuers. mode=null
when extend versus replace is unclear. Company names as the user said them — never CIKs. Do not
invent financial values. Use explain / news_and_explain / exploratory_research only for qualitative
or current-event questions that are not a spec edit. Use filing_change for what changed in a
company's 10-Q, MD&A or Risk Factors. Allowed metrics: revenue, cost_of_revenue, gross_profit,
operating_expenses, operating_income, net_income, research_and_development,
selling_general_and_administrative, interest_expense, income_tax_expense, pretax_income,
eps_diluted, eps_basic, operating_cash_flow, capital_expenditure, depreciation_amortization,
dividends_paid, dividends_per_share, cash, shareholders_equity, total_equity, net_interest_income,
noninterest_income, net_income_ttm, gross_margin, operating_margin, net_margin, rd_to_sales,
sga_ratio, effective_tax_rate, interest_coverage, free_cash_flow, ebitda, return_on_equity,
pe_ratio, market_cap, price. Operations: across_companies (several companies side by side),
across_periods (a window of quarters), rank (the top N of an industry), order_by_metric (sort the
companies by the metric: "sort by revenue", "which is biggest"), year_over_year (growth against the
same quarter a year earlier: "show year-over-year"), sequential (the change on the quarter before,
only beside year_over_year when both are asked: "sequentially or versus last year"), lowest_first
(the ordered rows from the lowest value: "lowest first"; remove it for "largest first"). Remove
year_over_year when they ask for plain levels again. Periods in the follow-up's wording are also
read by code.
```

</details>

<details>
<summary><strong>Essay: explain</strong> (essay.py, 21 words)</summary>


```text
Write a concise financial-analyst essay that answers the user's question. Do not include numeric
tokens because ungrounded numerals are rejected downstream.
```

</details>

<details>
<summary><strong>Essay: analysis</strong> (essay.py, 32 words)</summary>


The input is the question, then `Analysis JSON:` and the turn's results.


```text
Write a concise financial-analyst essay that answers the user's question. You may quote numeric
values that appear in the supplied analysis JSON. Do not invent numerals that are absent from that
JSON.
```

</details>

<details>
<summary><strong>Essay: news</strong> (essay.py, 56 words)</summary>


The input is `User query:` with the question, then `News tool JSON:` and the search results.


```text
Write a concise financial-analyst brief using only the supplied news tool JSON. Cite sources only as
[n], where n is the 1-based index of an object in that JSON array. Do not write (n), n., [1, 2], or
[1-3]. Do not introduce facts or numeric tokens that are absent from that JSON, except those [n]
markers.
```

</details>
