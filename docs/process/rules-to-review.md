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

## 2026-10-06 — combination-gaps 02: ADR 0009 on the quarters a change adds

- **Where:** `docs/adr/0009-year-over-year-reads-the-comparative.md`, Decision, third and second paragraphs.
- **The rule:** "A sequential change still needs the quarter before the oldest one shown, so it can widen a window to 5", and "Otherwise a change is shown only where the year-earlier quarter is in the window, as before."
- **Why it looks wrong:** the README's "How a question is read" now says a window with quarter over quarter shows that many quarters (combination-gaps 01), and a named period with a change shows those quarters, each with its change (this ticket). Neither widens what is shown: the quarter before is read as the base and not shown, and a named period's year-over-year change reads its own comparative, with no year-earlier quarter added. The ADR still describes the widening.
- **What you did:** followed the README and the ticket; left the ADR as it is for a person to amend.
- **Decided (2026-10-06):** the README is right. ADR 0009 has a revision note saying a change no longer widens what is shown.

## 2026-10-06 — brief-5-probe-gaps 01: the README's window cap and the "since" cap disagree

- **Where:** `README.md`, "How a question is read", the window row; `MAX_SINCE_QUARTERS` in `src/financial_analyst_agent/request_wording.py` and the note in `_window_notes` in `answer_notes.py`.
- **The rule:** the window row says a window is "at most 40" quarters, and names `since 2024` and `since the start of 2024` in that row. The code caps a `since` window at 20 quarters, and its note says "a window shows at most 20, so this asks for the latest 20".
- **Why it looks wrong:** `the past decade` shows 40 quarters (a phrase-coverage case), so a plain window does go to 40, but `revenue since 2000` shows 20 and tells the analyst a window shows at most 20. One of the two numbers is wrong, and the README and the answer's note say different things to the same analyst.
- **What you did:** left both as they are. This ticket only widens which "since" wordings are read as a window; the cap is untouched and `test_window_copy.py` still expects 20.
