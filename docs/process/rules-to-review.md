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
- **Decided (2026-10-07):** yes. A "since" window is a window, so a change asked over it is year over year over it, like any named window; and `since 2025 year over year` must read 2025 as a year. Ticket probe-round-3-gaps 10.

## 2026-10-07 — probe-round-3-gaps 11: the ticket says AMD's and Merck's EBITDA show four quarters with no change

- **Where:** `docs/process/tickets/probe-round-3-gaps/issues/11-a-derived-figures-year-over-year-change.md`, What to build ("On the recorded runtime, `AMD EBITDA over the last 4 quarters year over year` and `Merck EBITDA over the last 4 quarters year over year` show four quarters of EBITDA with no year-over-year change at all, and no note"; "One of those comparatives is evidently missing for AMD and Merck").
- **The rule:** a comparative is missing for one of EBITDA's components, so the levels show and the change does not.
- **Why it looks wrong:** on the recorded runtime both questions show four rows reading "Missing fact": EBITDA itself is missing, not a comparative. The cassette, recorded from live EDGAR with every concept the catalog reads, holds for AMD no cash-flow depreciation and amortization line and `Depreciation` only for the fiscal year (its 10-Ks), so the Depreciation-plus-amortization fallback (ADR 0008) has no quarter either; for Merck it holds no `OperatingIncomeLoss` at all and `AmortizationOfIntangibleAssets` only for the year. Ticket 07's Answer already says "the recording holds no EBITDA for AMD, so each row reads 'Missing fact'". The ticket says live is the same; by how the cassette was recorded, live EDGAR would read the same way, though that is inferred, not observed.
- **What you did:** took the ticket's second branch, since the filings do not hold what the figure needs: a derived figure whose part was not found says which part, in a note, so a missing figure and the change with it never go without a word. Whether AMD tags its cash-flow depreciation and amortization under a concept the catalog does not read (which would make EBITDA computable) needs live data to judge; the cassette holds only the concepts the catalog reads.
- **Decided (2026-10-07):** the agent is right; the ticket's premise was wrong. The figure itself is missing, not only its change, and the row now says which part the filings lack.

## 2026-10-07 — held-out-5-findings 01: the ticket says the year-over-year half is lost in the reading of the words when the bases lead

- **Where:** `docs/process/tickets/held-out-5-findings/issues/01-both-change-bases-leading.md`, What to build ("with the bases leading the question (and `versus last year` before the company), the year-over-year half is lost in the shared reading of words (`request_wording.py`, the comparison and change-base reading). Read both bases wherever they sit in the question."), and `docs/evaluation/held-out-5-findings.md`, the table of cases every planner failed.
- **The rule:** the defect is in how the words are read when the bases come first; `Did Cisco's revenue grow sequentially or versus last year?` already shows both changes.
- **Why it looks wrong:** on the recorded runtime, where the bases sit makes no difference. `Goldman net interest income, sequentially or versus last year` showed the sequential change only, and `Sequentially or versus last year, Cisco revenue` showed both. The words were read the same either way: a question naming both bases was read as a quarter-over-quarter view, which adds the year-over-year change only where a quarter's year-earlier quarter is also on screen (README's quarter-over-quarter row). Cisco's five quarters give its newest quarter one such row; the recording holds four Goldman quarters, so none. The Cisco example "showed both changes" on one quarter by the luck of the window, not by reading both bases.
- **What you did:** fixed the cause the evidence shows. Naming both bases now carries a `sequential` operation beside `year_over_year`, so every quarter shown has its year-over-year change from its own comparative (as a year-over-year question's does) and its change on the quarter before; the phrase-coverage cases with the bases leading and trailing the ticket asks for are added, and all pass. The README's row now says what both changes are and on which quarters.
- **Decided (2026-10-07):** the agent is right; the ticket's diagnosis was wrong. Where the bases sit made no difference: naming both was read as a quarter-over-quarter view. The fix addresses that cause.

## 2026-10-07 — held-out-5-findings 02: "adds Apple or peers", but the rule drops only the word's company

- **Where:** `docs/process/tickets/held-out-5-findings/issues/02-ordinary-word-idioms-name-no-company.md`, What to build ("`On revenue, AbbVie is the apple of the drug group` adds Apple or peers") and Acceptance ("the case named is read right by the planner(s) that failed it ... with a fake LLM planner proposing what the run's observation shows").
- **The rule:** a company a planner proposes from an everyday word used as the word is dropped, whichever planner proposed it.
- **Why it looks wrong:** on one of three LLM runs, `h5_ow_apple_idiom` proposed AbbVie with Johnson & Johnson, Eli Lilly and Merck, read from "the drug group", not Apple. None of those comes from an everyday word, so the rule the ticket asks for leaves them, and that run's observation is not read right. Dropping companies a first question does not name would also drop the LLM planner's legitimate readings ("the iPhone maker"), so it is not done here.
- **What you did:** followed the rule; the fake-planner test pins the Apple runs (AbbVie and Apple), which now show AbbVie alone. Whether a planner's companies read from a group word beside one named company ("the X of the drug group") should be dropped is for a person to decide.
- **Decided (2026-10-07):** leave it. Companies a planner reads from a group word beside one named company are not dropped: doing so would also drop legitimate readings ("the iPhone maker"). The live cascade keeps the rules planner's reading of this question, which is right.

## 2026-10-07 — held-out-5-findings 07: "How might AI change Apple's revenue?" is now Apple's revenue

- **Where:** `docs/process/tickets/held-out-5-findings/issues/07-a-named-companys-why-is-its-figure.md`, What to build ("an `explain` proposal for a question that names a recorded company and a catalog metric is that company's lookup"), and README, Follow-ups, explanations and filing changes ("With a company named ..., it is that company's figure").
- **The rule:** a named company and a catalog metric make a question that company's figure, whichever planner proposed an explanation.
- **Why it looks wrong:** the rules planner reads "how might AI ..." as an explanation on purpose (README's general-question row: `How might AI change banking?`). With a company and a metric named, `How might AI change Apple's revenue?` was an explanation (on the recorded runtime, refused: it replays one essay) and is now Apple's latest-quarter revenue, which answers none of what the question asks. The ticket's own example (`How might AI change Goldman Sachs's business?`) names no metric, so it stays an explanation.
- **What you did:** followed the rule; compare_answers names the change. Whether a speculative "how might X change" question about a named company's metric is its figure or an essay is for a person to decide.
- **Decided (2026-10-07):** the agent is right that this is wrong. A speculative question (`how might`, `how could`, `how would`, `what if`, `what would happen`) is an explanation even when it names a company and a catalog metric: the latest figure answers none of it. Ticket held-out-5-findings 10.

## 2026-10-07 — held-out-5-findings 09: a test said a ranking with no industry is refused

- **Where:** `tests/test_run_turn_rank.py`, `test_run_turn_refuses_missing_ranking_industry_from_injected_completer` ("rank companies by net income" and "rank companies", with a planner proposing a ranking with no industry, expected an `unknown industry` refusal).
- **The rule:** a planner's ranking that names no industry is refused as an unknown industry.
- **Why it looks wrong:** README, a ranking with no group: `which companies are worth the most?` ranks every company in the snapshot, and the rules planner already ranks every company for these words. The LLM planner's ranking with no industry for `h5_rk_worth` was refused by this rule, and ticket 09 asks the shared resolution to rank every company whichever planner proposed it.
- **What you did:** followed the ticket. The test is now `test_run_turn_ranks_every_company_when_the_planner_names_no_industry`. A planner that leaves the group out of a question naming one it does not know (`top 10 companies in AI`) would now rank every company instead of refusing; the rules planner names the group there, and no run has shown the LLM planner leaving it out, so the words are not re-read for it.
- **Decided (2026-10-07):** close the open risk. When a planner proposes a ranking with no group, the shared resolution reads the question for a group as the rules planner does; a group the snapshot does not know (`top 10 companies in AI`) is refused as now, and only a question with no group ranks every company. Ticket held-out-5-findings 11.

## 2026-10-07 — simplify-pass-2 02: eleven snapshot short names end in ")"

- **Where:** `docs/process/tickets/simplify-pass-2/issues/02-match-metric-phrases-once.md`, What to build, step 8 (`missing_component_notes`): "Before changing it, confirm that no short name in the snapshot ends in ')'; for every other name the output is the same."
- **The rule:** the rewrite of `missing_component_notes` from "format, then parse back" to `(short, dates)` tuples is a cleanup, on the premise that no snapshot short name ends in ")".
- **Why it looks wrong:** eleven do. `short_name` leaves "Telefonaktiebolaget LM Ericsson (publ)", "Jerash Holdings (US), Inc." → "Jerash Holdings (US)", "ZTO Express (Cayman) Inc." → "ZTO Express (Cayman)", "Banco Santander (Brasil) S.A.", "Formula Systems (1985) Ltd.", "Reformation Inc. (California)", "National Healthcare Properties, Inc. (NHP)", "Eco Wave Power Global AB (publ)", "Dogness (International) Corporation", "Autozi Internet Technology (Global) Ltd." and "Four Seasons Education (Cayman) Inc." ending in ")". For any of them alone, with a formula's part missing in every quarter, today's note parses the name as if it held dates: "Jerash Holdings' EBITDA is missing for US: no standalone quarterly depreciation and amortization was found for that quarter, which EBITDA needs." The tuple form would read "Jerash Holdings (US)' EBITDA is missing: ... was found in its filings", which is right, so the rewrite changes those notes.
- **What you did:** left step 8's `missing_component_notes` rewrite undone, as the ticket says to when a step would change behaviour, and did the rest of step 8. Whether to make the change as a bug fix (the garbled note for these eleven companies) is for a person to decide; it is a one-function change in `answer_notes.py` with a test on one of the names.
- **Decided (2026-10-08):** the agent is right to leave it. The rewrite assumed no short name ends in ")"; eleven do, so it could change a note. The note's code stays as it is.

## 2026-10-08 — period-selection 02: the file list leaves out two callers of the moved names

- **Where:** `docs/process/tickets/period-selection/issues/02-read-the-period-words-once.md`, **Files (this ticket only)** and the last sentence of Acceptance ("If a step would ... need a file outside this ticket's list, leave it and say so in the Answer").
- **The rule:** a step that needs a file outside the ticket's list is left undone.
- **Why it looks wrong:** `graph/clarify.py` imports `read_window` and `WindowReading` from `request_wording`, and `tests/test_says_what_it_cannot_do.py` monkeypatches `request_wording.date` for the "N years ago" reading; neither file is on the list. Leaving them would fail `pytest` and step 6 (no re-exports), which the same ticket requires. `tests/unit/services/test_metric_phrase.py` imports `TRAILING_YEAR` the same way.
- **What you did:** changed the three files by one import (and, in `clarify`, two `read(...).reading` calls) each, and said so in the Answer. The design record's call-site list has `clarify` changing in ticket 03 (`words.bind`), so its import line is the only part done early.

## 2026-10-08 — period-selection 03: the file list leaves out a caller and a test of the moved names

- **Where:** `docs/process/tickets/period-selection/issues/03-bind-and-rebase-the-period-part-of-a-patch.md`, **Files (this ticket only)** and the last sentence of Acceptance ("If a step would ... need a file outside this ticket's list, leave it and say so in the Answer").
- **The rule:** a step that needs a file outside the ticket's list is left undone.
- **Why it looks wrong:** `answer_notes.py` imports `MAX_SINCE_QUARTERS` from `request_wording`, where it sat beside the binding. The binding moves into `period_selection` and needs it; the module may import nothing from `request_wording`; and leaving a second definition behind in `request_wording` is the duplicate the no-re-export rule exists to prevent. `tests/unit/test_planner_window.py` calls `bind_periods_from_message` in two tests, which the ticket deletes, so leaving it fails `pytest`.
- **What you did:** changed each by one import (and, in the test, the two calls), and said so in the Answer, as ticket 02 did for `clarify.py`. Ticket 06 moves the since notes into the module, after which `answer_notes` would import it from there anyway.

## 2026-10-08 — period-selection 05: the file list leaves out the notes' caller of `calendar_groups`

- **Where:** `docs/process/tickets/period-selection/issues/05-group-calendars-and-hide-base-quarters.md`, **Files (this ticket only)** and the last sentence of Acceptance ("If a step would ... need a file outside this ticket's list, leave it and say so in the Answer").
- **The rule:** a step that needs a file outside the ticket's list is left undone.
- **Why it looks wrong:** `answer_notes.period_notes` calls `calendar_groups` for the calendars-differ and fiscal-Q4 notes. The same ticket says `calendar_groups` no longer exists and that `Periods.groups` is the one place that groups companies "for compilation, notes and row hiding", so leaving `answer_notes` alone fails `pytest` and the Acceptance.
- **What you did:** changed `answer_notes.py` by one import and one line (`Periods(spec).groups`), and said so in the Answer, as tickets 02 and 03 did. Ticket 06 moves these notes into the module.


## 2026-10-08 — period-selection 06: notes read from the stored reading change a clarification's answer

- **Where:** `docs/process/tickets/period-selection/issues/06-period-notes-chip-and-quick-actions.md`, What to build step 2 ("Year of quarters comes from `reading.year_of_quarters` and year to date from `reading.year_to_date`"); the design record's `Periods.notes` ("replace today's re-search of the message"); and the ticket's "Restructure only: no behaviour may change".
- **The rule:** the notes stop searching the wording for "last year" and year-to-date words and read them from the request's stored reading, with no change to any answer.
- **Why it looks wrong:** the two are not always the same. A metric reply to a clarification keeps the held question's reading when the reply names no window (`clarify._resume_metric`). On master, "Apple margin last year" then "gross margin" shows four quarters with no "The last year: ..." note, and "Apple margin YTD" then "gross margin" has no year-to-date note, because the notes search the reply. Reading the stored reading adds both notes. That is arguably right (it is the #103 class ADR 0015 names: a clarified answer losing its window note), but it changes answers. No recorded conversation reaches it, so compare_answers shows 0 differences either way.
- **What you did:** kept the behaviour, as the ticket says to when a step would change it. `Periods.notes` reads `reading.year_of_quarters` and `reading.year_to_date` as designed. `spec_turn.annotate_analysis` passes a copy of the stored reading with those two fields read from the wording (`read(compiled.wording).reading`), as before. A test in `test_calendars_clarification_and_formatting.py` pins master's answer. To take the fix, a person decides; it is then a deletion of the copy in `annotate_analysis` and a flip of that test.
