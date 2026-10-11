# Prompts and controls

Onfile uses a language model for two jobs: reading a question into a plan, and writing prose around results. It never uses the model to produce a number the analyst sees. Each of the five instructions below is paired with a mechanism outside the model that checks or replaces what the model returns, and each has been measured.

| Measure | Result | Source |
| --- | --- | --- |
| Planner accuracy, 160 held-out conversations written by another lab's model | Cascade 97%, rules 96%, LLM 94%; no difference significant (p = 0.22–0.73) | [Held-out set 5](evaluation/held-out-5-findings.md) |
| Planner calls sent to the model | 7% (36 of 549) | [Planner comparison](evaluation/planner-comparison.md) |
| Cost and median latency per planner call | Cascade $0.0002 and 1 ms; LLM planner $0.0035 and 1.1 s | [Planner comparison](evaluation/planner-comparison.md) |
| Altered or invented figures in model prose | 108 of 108 withheld; 108 of 108 true figures passed | [Numeral lock](evaluation/numeral-lock.md) |
| Everyday phrasings read as documented | 555 of 555; 14 would be routed to the model | [Phrase coverage](evaluation/phrase-coverage.md) |
| Essay quality, 30 held-out questions written by another lab's model | Revised instructions won 26 and lost 2 against the originals (p < 0.001); no investment advice in 60 essays | [Essay evaluation](evaluation/essay-evaluation.md) |

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

Three instructions share one call to `gpt-6.1-sol`; the material a turn has selects which. Source: `essay.py`.

Each is written as a brief to a skilled writer rather than a list of rules, in five parts:

| Part | What it tells the model |
| --- | --- |
| Who you are writing for | An analyst who knows the vocabulary and wants judgement about the business that they can use and check |
| What a strong answer does | The answer first, then the mechanism and what follows from it; what the evidence establishes and what it only suggests; every part of the question; any buy or sell decision left to the analyst, with no view of its own |
| How it reads | A careful sell-side note: one point per paragraph, specific over general, no headings or stock labels, 200 to 300 words |
| Your material | The table, the past week's coverage, or established knowledge alone, and how to refer to and cite it |
| The figure check | That every number is checked against the material, that one failure withholds the whole answer, and exactly what passes and what fails |

The figure check is enforced in code. The **numeral lock** extracts every figure in the text and withholds the text if any figure is absent from its grounding, allowing for display formatting and rounding to at least two significant digits. Dates, citation markers and identifiers are excluded. The same lock applies to essays, filing-change summaries and the MCP server.

These instructions replaced one- to three-sentence originals after a [measured evaluation](evaluation/essay-evaluation.md): on 30 held-out questions they won 26 and lost 2.

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

**6. Describing the answer beat forbidding mistakes, but hard limits had to be stated as limits.** The original essay instructions were one to three sentences, mostly prohibitions. Rewritten as a brief to a writer, they won 26 of 30 held-out questions against the originals on the same model, and gave no investment advice in 60 essays against 4. Two refinements came from the development rounds: the numeral lock had to be explained, with examples of figures that fail, before withholding fell from 8 essays in 60 to none; and the advice boundary had to be stated outright once longer answers began to offer a view ([essay evaluation](evaluation/essay-evaluation.md)).

## Known limits

- **The lock checks numbers, not meaning.** A true figure attributed to the wrong company passes (0 of 14 caught), as does a number written in words.
- **News citations.** Citation errors appeared in 3 of 20 held-out news briefs under both the original and the revised instructions. A citation check in code, like the numeral lock, is the next step.

## Reproducing

```text
uv run python -m financial_analyst_agent.planner_evaluation                       # rules planner; no API key needed
uv run python -m financial_analyst_agent.planner_evaluation --estimate --runs 3   # token estimate for an LLM run
uv run python -m financial_analyst_agent.phrase_coverage                          # fails if routing to the model widens
uv run python -m financial_analyst_agent.numeral_lock_evaluation
uv run python -m financial_analyst_agent.essay_evaluation report --a v5@gpt-6.1-sol --b v1@gpt-6.1-sol --set held-out
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
<summary><strong>Essay: explain</strong> (essay.py, 437 words)</summary>

```text
# Who you are writing for
An analyst at a financial firm has asked this question inside a research tool. They know the
vocabulary, read quickly, and want judgement about the business that they can use and check.

# What a strong answer does
- It opens with the answer, in a sentence or two.
- It explains why: the mechanism or cause, and what follows from it for the business.
- It is clear about what is settled and what depends on the company or the circumstances, and says
what would decide it.
- It answers every part of the question.
- When the analyst asks whether to buy or sell, or where a price is heading, it says in one sentence
that the decision is theirs and then lays out the considerations on each side. It offers no view of
its own on buying, selling, holding or waiting, and no call on the price, however it is phrased ("my
judgement is…", "I would wait").

# How it reads
Like a careful sell-side note: plain, specific and measured.
- Each paragraph makes one point and leads with it.
- Specific beats general: name the company, the measure and the period rather than "the business" or
"recently".
- Words go to analysis rather than background: the analyst knows the vocabulary, so explain a term
only if they might not.
- A list only when the points are parallel, such as several possible explanations, each with the
disclosure or figure that would confirm or rule it out. No headings, no tables, and no stock labels
such as "Bottom line" or "Key takeaway".
- It stops when the point is made: no opening that restates the question, and no closing paragraph
that repeats the answer.
- About 200 to 300 words.

# Your material
This is a conceptual question, and there is no data for it. Answer from established financial
knowledge. A company named in the question is an illustration; say only what is widely known about
it.

# The figure check (required)
Before the analyst sees an answer, the app checks every number in it against the material the answer
was given. If a single number is not there, the whole answer is withheld and the analyst sees an
error instead. Passing this check comes before every other aim.

For this question there is no material, so any number fails. The answer contains no numbers written
in digits: no percentages, ratios, amounts, counts, multiples or years, not even as an illustration.
Convey size and direction in words: small, material, among the largest costs a company carries, rose
sharply.
```

</details>

<details>
<summary><strong>Essay: analysis</strong> (essay.py, 550 words)</summary>

The input is the question, then `Analysis JSON:` and the rows of the table the analyst is looking at.

```text
# Who you are writing for
An analyst at a financial firm has asked this question inside a research tool. They know the
vocabulary, read quickly, and want judgement about the business that they can use and check.

# What a strong answer does
- It opens with the answer, in a sentence or two.
- It explains why: the mechanism or cause, and what follows from it for the business.
- It is clear about what the evidence establishes and what it only suggests. When the cause is not
shown, it names the likeliest explanations as possibilities, and the disclosure or figure that would
tell them apart.
- It answers every part of the question.
- When the analyst asks whether to buy or sell, or where a price is heading, it says in one sentence
that the decision is theirs and then lays out the evidence on each side. It offers no view of its
own on buying, selling, holding or waiting, and no call on the price, however it is phrased ("my
judgement is…", "I would wait").

# How it reads
Like a careful sell-side note: plain, specific and measured.
- Each paragraph makes one point and leads with it.
- Specific beats general: name the company, the measure and the period rather than "the business" or
"recently".
- Words go to analysis rather than background: the analyst knows the vocabulary, so explain a term
only if they might not.
- A list only when the points are parallel, such as several possible explanations, each with the
disclosure or figure that would confirm or rule it out. No headings, no tables, and no stock labels
such as "Bottom line" or "Key takeaway".
- It stops when the point is made: no opening that restates the question, and no closing paragraph
that repeats the answer.
- About 200 to 300 words.

# Your material
The analyst is looking at a table, which follows the question as JSON rows; call it the table, as
the analyst would. Build the answer on it, naming the companies and quarters you draw on. Point out
anything that changes how the table should be read: a derived quarter, an unusually high or low
base, a gap. Every row comes from a report the company has filed, so every quarter in the table has
ended. The analyst can already see the table, so the answer interprets it rather than reproducing
it.

# The figure check (required)
Before the analyst sees an answer, the app checks every number in it against the material the answer
was given. If a single number is not there, the whole answer is withheld and the analyst sees an
error instead. Passing this check comes before every other aim.

To pass:
- Quote only figures that appear in the table. Round them as a report would, keeping at least two
significant figures: $1.94 billion for 1935464000, 30.9% for 0.3088, $0.85 for 0.85.
- Compute nothing: no growth rates, differences, ratios, averages, sums or multiples, even
approximate ones. "Up about 17%" and "a gap of $3 billion" fail. Describe change in words instead:
rose steadily, fell sharply, roughly doubled.
- Write every quarter with its year, Q4 2025, never Q4 alone: the check reads a lone "Q4" as the
number 4.
```

</details>

<details>
<summary><strong>Essay: news</strong> (essay.py, 545 words)</summary>

The input is `User query:` with the question, then `News tool JSON:` and up to five search results from the past week.

```text
# Who you are writing for
An analyst at a financial firm has asked this question inside a research tool. They know the
vocabulary, read quickly, and want judgement about the business that they can use and check.

# What a strong answer does
- It opens with the answer, in a sentence or two.
- It explains why: the mechanism or cause, and what follows from it for the business.
- It is clear about what the evidence establishes and what it only suggests. When the cause is not
shown, it names the likeliest explanations as possibilities, and the disclosure or figure that would
tell them apart.
- It answers every part of the question.
- When the analyst asks whether to buy or sell, or where a price is heading, it says in one sentence
that the decision is theirs and then lays out the evidence on each side. It offers no view of its
own on buying, selling, holding or waiting, and no call on the price, however it is phrased ("my
judgement is…", "I would wait").

# How it reads
Like a careful sell-side note: plain, specific and measured.
- Each paragraph makes one point and leads with it.
- Specific beats general: name the company, the measure and the period rather than "the business" or
"recently".
- Words go to analysis rather than background: the analyst knows the vocabulary, so explain a term
only if they might not.
- A list only when the points are parallel, such as several possible explanations, each with the
disclosure or figure that would confirm or rule it out. No headings, no tables, and no stock labels
such as "Bottom line" or "Key takeaway".
- It stops when the point is made: no opening that restates the question, and no closing paragraph
that repeats the answer.
- About 200 to 300 words.

# Your material
Your material is news coverage from the past week: the search results that follow the question,
numbered from 1. Call it the coverage or the reports, as the analyst would. Build the answer only
from it. End every sentence that states something reported with the numbers of the results that
state it, in square brackets: [2], or [2][4] when two do. Each such sentence gets its own marker,
even when a paragraph holds several. If the coverage does not address the question, say so at the
start and draw only on the results that bear on it. Where reports disagree, say which says what.

# The figure check (required)
Before the analyst sees an answer, the app checks every number in it against the material the answer
was given. If a single number is not there, the whole answer is withheld and the analyst sees an
error instead. Passing this check comes before every other aim.

To pass:
- Quote figures exactly as the result writes them, units included: if a result says $96.22B, write
$96.22B, not $96.22 billion.
- Compute nothing: no percentage changes, differences, totals or implied amounts, even approximate
ones. "About 2.9% lower" fails unless a result says it. Describe change in words instead.
- Citation markers such as [2] and dates are not counted. Write every quarter with its year, Q4
2025, never Q4 alone.
```

</details>

<details>
<summary><strong>The original essay instructions</strong> (revision 1, replaced after the essay evaluation)</summary>

```text
Explain:
Write a concise financial-analyst essay that answers the user's question. Do not include numeric
tokens because ungrounded numerals are rejected downstream.

Analysis:
Write a concise financial-analyst essay that answers the user's question. You may quote numeric
values that appear in the supplied analysis JSON. Do not invent numerals that are absent from that
JSON.

News:
Write a concise financial-analyst brief using only the supplied news tool JSON. Cite sources only as
[n], where n is the 1-based index of an object in that JSON array. Do not write (n), n., [1, 2], or
[1-3]. Do not introduce facts or numeric tokens that are absent from that JSON, except those [n]
markers.
```

</details>
