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
- **Decided (2026-10-06):** the README is right. A "since" window is capped at 40 quarters, as every window is (`MAX_SINCE_QUARTERS = MAX_QUARTERS_ASKED`), and its note says 40.

## 2026-10-06 — review-69-90 01: the acceptance expects no missing-quarter note for `since 2024`

- **Where:** `docs/process/tickets/review-69-90/issues/01-a-since-window-counts-from-the-latest-quarter.md`, What to build ("it holds every quarter since 2024") and Acceptance ("shows every recorded quarter since January 2024 and no 'only N of M' note").
- **The rule:** on the recorded runtime, `Apple revenue since 2024` should show no "only N of M" note, because the recording holds every quarter since 2024.
- **Why it looks wrong:** the recording's oldest Apple quarter ended 29 June 2024. Ten quarters ended between 1 January 2024 and the latest filed quarter (27 June 2026); the recording holds nine, and the quarter ended 30 March 2024 is inside the span. The ticket's own rule ("a window note says a quarter is missing only when the filings lack one inside the span") then calls for a note, and silence would tell the analyst that Apple's first quarter of 2024 ended in June.
- **What you did:** followed the rule over the example. The answer says "The filings here hold only 9 of the 10 quarters since 2024" (counted from the filings, so it no longer drifts with the calendar); `since 2025`, where the recording holds every quarter, shows no note. The recorded-runtime test pins the 9-of-10 note rather than its absence.
- **Decided (2026-10-06):** the agent is right; the ticket's example was wrong. The recording lacks Apple's quarter ended 30 March 2024, so the 9-of-10 note is true.

## 2026-10-06 — review-69-90 03: a code comment still says a sequential change widens the window

- **Where:** `src/financial_analyst_agent/request_wording.py`, `bind_periods_from_message`, the comment on the `count = 5` branch ("A sequential change needs the quarter before the oldest one shown"), and the docstring of the "show that year over year" extend step ("A sequential change still needs the quarter before the oldest one shown").
- **The rule:** both read as if the base quarter were shown, which is what ADR 0009's withdrawn sentence said.
- **Why it looks wrong:** a window with quarter over quarter returns earlier in the binder with `count = asked + 1` and `asked` set, and with no window `count` is already 5, so the branch the comment explains never changes a sequential window; `Apple revenue growth last 4 quarters` keeps 4 too (growth counts as explicit year over year). The base quarter is read and not shown (combination-gaps 01).
- **What you did:** left both as they are; this ticket changes documentation only, and the branch's behaviour is unchanged. ADR 0009's Decision now states the revised rule.
- **Decided (2026-10-06):** the comments were wrong. Both now say the base quarter is read and not shown; the `count = 5` branch's comment says it is reached only by a change that names no base.

## 2026-10-07 — probe-round-3-gaps 03: the README says a fund beside a company is "left out with a note"

- **Where:** `README.md`, "How a question is read", the "A company's other names" row.
- **The rule:** "A fund beside a company (`SPY and Apple revenue`) is left out with a note; one company left on screen is a lookup."
- **Why it looks wrong:** the fund is not left out of the table. On the recorded runtime `SPY and Apple revenue` shows two rows, SPY reading "Company not found" and Apple's figure, and the only note is "Showing SPDR S&P 500 ETF TRUST for “SPY”", which names the fund without saying it is one or that it is left out. On the live runtime SEC identifies SPY and the row would read "not an operating company" instead. A name no company matched (`Apple and Acme Widgets revenue`) is what the README describes: no row, and a note saying it is left out.
- **What you did:** followed the ticket, which asks only that the intent follow the companies on screen: the answer is now a lookup, and a row that says the company was not found or is not an operating company does not count as on screen. The SPY row and its note are unchanged; whether the fund's row should go, with a note saying SPY is a fund, is for a person to decide.
- **Decided (2026-10-07):** the README is right. A fund (or anything the snapshot marks as not an operating company) beside a company is left out of the table, with a note saying it is a fund and left out; "Showing SPDR S&P 500 ETF TRUST for 'SPY'" reads as if it were shown. Ticket probe-round-3-gaps 08.

## 2026-10-07 — probe-round-3-gaps 05: the acceptance says "no year-over-year" after `sequential instead`

- **Where:** `docs/process/tickets/probe-round-3-gaps/issues/05-sequential-instead.md`, Acceptance ("that conversation ends with 6 quarters and sequential changes, no year-over-year").
- **The rule:** after `sequential instead`, the answer shows no year-over-year change.
- **Why it looks wrong:** the quarter-over-quarter view as shipped shows a "QoQ change" column and, beside it, a "YoY change" column for every quarter whose year-earlier quarter is also on screen (`across_period_change_rows` computes both from the levels shown). `Apple revenue over the last 6 quarters quarter over quarter`, asked directly, shows both columns for the three newest quarters. If the switch dropped the year-over-year column, `sequential instead` would end on a different view from the direct question, which the README's row does not ask for.
- **What you did:** read "no year-over-year" as the year-over-year operation and chip: the switch removes them, and the answer is the view the direct quarter-over-quarter question gives, column for column (the recorded-runtime test pins that equality). Whether a quarter-over-quarter view should show the year-over-year column at all is for a person to decide; it is not changed here.
- **Decided (2026-10-07):** the agent's reading is right. A quarter-over-quarter view also shows the year-over-year change where the year-earlier quarter is on screen; it costs nothing and the README's quarter-over-quarter row now says so.

## 2026-10-07 — probe-round-3-gaps 07: "how much did X change over the last year?" shows the quarters with no change

- **Where:** `tests/unit/test_planner_wording.py`, `test_what_a_change_is_measured_against` (`("How much did Intel's revenue change over the last year?", None)` and `("Over the past 10 quarters, how has Thermo Fisher's revenue moved?", None)`), and `_names_a_span` in `src/financial_analyst_agent/request_wording.py` ("The span's first quarter is the change's base, so the span is the answer").
- **The rule:** a change asked about over a span of quarters, in wording the year-over-year pattern does not catch, shows the span's quarters with no change column: the analyst reads the change from the first quarter to the last.
- **Why it looks wrong:** the README's growth row says a change over a named window (`How did EBITDA change over the past year?`) is year over year over that window, and this ticket makes `How did AMD's EBITDA change over the past year?` and `How has Tesla's revenue changed over the last year?` four quarters, each with its year-over-year change. `How much did Intel's revenue change over the last year?` asks the same thing in other words and still shows four quarters with no change column, because the year-over-year pattern reads "how did ... change" but not "how much did ... change". Two wordings of one question end on different views.
- **What you did:** followed the tests and left both wordings as they are; the ticket names only the growth default over a named window. Whether every change over a span should be year over year over it, or the span's quarters alone are the answer, is for a person to decide.
- **Decided (2026-10-07):** every change over a named span is year over year over it. Two wordings of one question should not end on different views, and a span with no change column leaves the analyst to do the subtraction. Ticket probe-round-3-gaps 09; the two test expectations change with it.

## 2026-10-07 — probe-round-3-gaps 09: a change over a "since" window still shows the quarters alone

- **Where:** `docs/process/tickets/probe-round-3-gaps/issues/09-how-much-did-it-change-over-a-window.md`, What to build ("Every change asked over a named window is year over year over that window, whatever the change wording"; "Change `test_what_a_change_is_measured_against`'s two expectations"), and `tests/unit/test_planner_wording.py`, `test_what_a_change_is_measured_against` (`("How much did Intel's revenue change since 2023?", None)`, `("What caused Apple's revenue to fall since 2023?", None)`).
- **The rule:** the ticket changes only the two expectations it names, so a change asked over a "since" window (`How much did Intel's revenue change since 2023?`) keeps showing every quarter since 2023 with no change column.
- **Why it looks wrong:** `CONTEXT.md`'s Window entry calls "since 2024" a window, and the ticket's own reason for the rule ("two wordings of one question should not end on different views", "a span with no change column leaves the analyst to do the subtraction") applies to it as much as to "over the last year". `How much did Intel's revenue change since 2023?` and `How much did Intel's revenue change over the last 2 years?` now end on different views.
- **What you did:** followed the ticket's explicit scope: a counted window or "the past year" is a named window for this rule; a "since" window and several named periods are left as they were, and their tests still pass. Making a "since" window year over year also needs the window grammar to carry the change (today `Apple revenue since 2025 year over year` reads 2025 as a count, as probe-round-3-gaps 05 noted), so it is a ticket of its own if a person decides so.
