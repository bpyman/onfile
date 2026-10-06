# Rules to review

Rules an agent met while working a ticket that looked incorrect or misleading: product rules in the README, `CONTEXT.md` or an ADR, a ticket's acceptance, a test's or an evaluation case's expectation, or a code comment. The agent records them here rather than following them into a wrong answer or changing them on its own judgement ([Ralph's prompt](ralph/prompt.md), "Rules that look wrong"). A person decides each one: change the rule, or say why it stands, and mark the entry decided.

Each entry: date, ticket, where, the rule, why it looks wrong, what the agent did.

## 2026-10-06 — phrase-coverage-gaps 01: "fee income" is noninterest income

- **Where:** `docs/process/tickets/phrase-coverage-gaps/issues/01-a-longer-phrase-is-not-its-ambiguous-word.md`, What to build; `METRIC_PHRASES` in `src/financial_analyst_agent/phrase_coverage.py`.
- **The rule:** "`fee income` → `noninterest_income`".
- **Why it looks wrong:** a bank's noninterest income (`NoninterestIncome`) is fees plus trading, investment gains and other income. Fee income is only part of it, so "JPMorgan's fee income" shows a larger figure than the analyst asked for, labelled "Noninterest income".
- **What you did:** followed it. "fee income" is a unique phrase for `noninterest_income`, and the window's label says which figure is shown.
- **Decided (2026-10-06):** the rule was wrong. No single XBRL field is a bank's fee income: banks tag different fee lines (`BrokerageCommissionsRevenue`, `FeesAndCommissionsMortgageBankingAndServicing`, `InvestmentBankingAdvisoryBrokerageAndUnderwritingFeesAndCommissions`, servicing fees), so a sum would not compare across banks. "Fee income" no longer names noninterest income; it asks which income is meant.

## 2026-10-06 — phrase-coverage-gaps 01: "total equity" is shareholders' equity

- **Where:** the same ticket's What to build; `METRIC_PHRASES` in `phrase_coverage.py`.
- **The rule:** "`total equity` → `shareholders_equity`".
- **Why it looks wrong:** on a balance sheet "total equity" includes noncontrolling interests. `shareholders_equity` reads `StockholdersEquity` first, the parent's share, and only falls back to the figure including noncontrolling interests. For a company with large minority interests the two differ.
- **What you did:** followed it. The window labels the figure "Shareholders' equity".
- **Decided (2026-10-06):** the rule was wrong. `StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest` is its own field (Wells Fargo, Citigroup, PNC, Truist, US Bancorp report it). "Total equity" now names a new metric, `total_equity`, which reads that field and falls back to `StockholdersEquity` for a company with no noncontrolling interests (Apple).
