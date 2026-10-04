# Ambiguous metric phrases clarify; they do not fetch

> **Revised by [ADR 0005](0005-stateful-analysis-graph.md):** the candidate-set rule and the phrase table below stand unchanged. What changes is the mechanism — clarify is no longer a dead end. On a conversation thread it is a LangGraph `interrupt` holding a pending analysis spec, checkpointed in the thread record, so answering the one open question resumes the planned work (`Command(resume=...)`) instead of requiring a retype. The "hold a pending plan" option below was rejected on a one-shot premise that no longer holds.
>
> **Revised (several metrics answered together):** a question that names two or more catalog metrics ("Amgen's revenue and net income") is answered with all of them, one analysis per metric. Each name is unique, so nothing is ambiguous. The earlier rule that clarified instead is withdrawn. The derived figures the catalog has since gained (EBITDA, return on equity, P/E, free cash flow, ADR 0008) are catalog metrics like any other, so "ROE" and "EBITDA" are no longer unknown.
>
> **Revised again (chips accepted):** the audience window shows each candidate as a button. A button sends its catalog slug as the next analyst message ([ADR 0006](0006-react-audience-window.md)), so it is the same answer the analyst could type, matched against the same closed candidate set; only the latest clarification's candidates are live, and only while the thread holds a pending clarification. Typing the metric still works.

A metric phrase is taken from the **user question**, not from `plan.metric`. Longest closed-table span wins (word boundaries). An exact catalog name or unique alias may run tools. An **ambiguous metric** returns `RendererKind.CLARIFY` with only those humanized names, no tools, same planned intent; the analyst answers by typing or clicking one of those names. An **unknown metric** still refuses with the full catalog. `parse_metric` unknown strings become `UnknownMetricError` — that error is not the clarify path. “Reported income” is left ambiguous on purpose: operating income is reported too. The phrase table grows when the catalog grows; it is not inferred from stems (`operating` is not a metric). Trusting the planner’s slug was rejected: the model will guess `net_income` for “income” and skip the pane.

## Phrase table

The catalog owns the phrases: `services/metric_catalog.py` holds them, and `resolve_metric_phrase` reads them. It also holds each metric's label and kind of value (`METRIC_DISPLAY`), which the window reads. This ADR records the rules and the ambiguous set, not every alias.

**Unique** phrases name one metric, longest span first: catalog names and slugs, abbreviations (`cogs`, `sg&a`, `r&d`, `opex`, `ebit`, `ebitda`, `roe`, `p/e`, `fcf`), and everyday wording (`top line` and `sales` → revenue, `bottom line` and `earnings` → net income, `market value` and `worth` → market cap, `net worth` → shareholders' equity, `share price` → price). A unique phrase that names a group names every member: `margins` is gross, operating and net margin.

**Several metrics** named in one question are each answered: "revenue and net income", "Apple revenue and net margin", "revenue, net income and free cash flow".

**Ambiguous** phrases, only where no unique span matched:

| Phrase | Candidates |
| --- | --- |
| `profit margin`, `margin` | Gross margin, Operating margin, Net margin |
| `profit` | Gross profit, Operating income, Net income |
| `income` | Net income, Operating income |
| `gross` | Gross profit, Gross margin |
| `net` | Net income, Net margin |
| `cash flow` | Operating cash flow, Free cash flow |
| `interest` | Interest expense, Interest coverage |
| `tax` | Income tax expense, Effective tax rate |
| `dividend`, `dividends` | Dividends per share, Dividends paid |
| `equity` | Shareholders' equity, Return on equity |
| `money` | Revenue, Net income |
| `expense`, `expenses` | Cost of revenue, Operating expenses |

**Unknown:** a measure the catalog lacks (`costs`, `debt`, `customer acquisition cost`) refuses and names it, with the catalog. `costs` stays unknown rather than ambiguous because it could mean any expense line.

A clarification answer may name several candidates ("gross and net"), all of them ("all", "both"), or another catalog metric outright. A period on its own ("last 4 quarters") is held for the open question rather than read as a new one.

## Considered Options

- **LLM writes a clarifying question** — rejected: the catalog owns the candidate set.
- **Hold a pending plan / chips** — rejected *at the time*: `run_turn` was one-shot with no multi-turn state. Superseded by ADR 0005, which persists the analysis spec on a thread and resumes it after the answer. Chips are now accepted too: a candidate button only sends its slug as the next message, so it adds no path the typed answer lacks.
- **Match `plan.metric` only** — rejected: live OpenAI resolves collisions silently.
- **Alias `reported income` → net income** — rejected: operating income is also reported.
- **Treat `operating` as ambiguous** — rejected: the word appears in non-metric questions.
- **Clarify when two catalog metrics are named** — withdrawn: each name is unique, so asking which one adds a step without resolving any doubt. Both are answered.
