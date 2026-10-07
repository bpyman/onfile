# Onfile

A demo agent that looks up reported quarterly facts for operating companies, ranks snapshot members from a dated freeze, and answers qualitative questions without inventing numbers.

## Language

**Universe snapshot**:
A dated freeze of US exchange-listed common shares of operating companies. Ranking reads this freeze; it does not rescreen the market. Lookup of a quarterly fact does not require freeze presence. Lookup of a snapshot metric (`market_cap`) does. News does not use it.
_Avoid_: live screener, universe, catalog

**Snapshot member**:
An operating company whose common share is present in this universe snapshot.
_Avoid_: SEC filer, listed company, issuer

**Operating company**:
A company that runs a business, as opposed to a shell, SPAC, fund, BDC, or other financing vehicle.
_Avoid_: issuer (unqualified), name, entity

**Common share**:
The ordinary equity listing of an operating company, not a preferred, unit, warrant, right, or listed note.
_Avoid_: security, ticker, listing (unqualified)

**Ineligible issuer**:
An operating-company lookalike identified by CIK after security type and industry are not enough to tell it apart. It is not a snapshot member and cannot be looked up or compared: asked alone it is refused, and named beside an operating company it is left out with a note saying it is a fund.
_Avoid_: blocklist entry, banned ticker

**Quarterly fact**:
A directly reported standalone-quarter amount from a 10-Q, with provenance.
_Avoid_: TTM, derived quarter, restatement

**Derived quarter**:
A quarter the filings report only inside a longer period, computed by one of the two subtractions in ADR 0007 (fiscal year minus nine months; year to date minus the previous year to date), labelled, with both reported facts as provenance. Per-share figures are never derived.
_Avoid_: estimate, implied quarter, TTM

**Trailing year**:
The four quarters ending on a report date as one amount: the 10-K's fiscal year, or after a 10-Q the last fiscal year plus this year to date minus the same months a year earlier (ADR 0008). Return on equity and P/E use it.
_Avoid_: annualised quarter, TTM sum of four rows

**Comparative**:
The same line a year earlier as a filing reports it beside the current period, on that filing's basis after a restatement or share split. A year-over-year change starts from it, not from the year-earlier quarter as first filed (ADR 0009).
_Avoid_: prior-year value, restated row

**Split-adjusted level**:
A per-share figure filed before a stock split, shown divided by the split ratio the company reports (compounded over several splits), as the company's later filings restate it. Its evidence keeps the filing that first reported it and says how it was adjusted (ADR 0009).
_Avoid_: restated EPS, adjusted EPS

**Balance-sheet amount**:
An amount a filing reports at its report date rather than over the quarter (cash, shareholders' equity, total equity), shown "At" that date.
_Avoid_: quarterly cash, period balance

**Named period**:
A fiscal quarter or year the analyst names ("Q3 2024", "fiscal 2025"), read as each company's own fiscal calendar from the fiscal year and period its filings declare; "calendar" names a calendar quarter instead.
_Avoid_: date range, calendar quarter (unqualified)

**Ambiguous metric**:
A user metric phrase that matches more than one name in the closed catalog.
_Avoid_: metric collision, unknown metric

**Unknown metric**:
A user metric phrase that names nothing in the closed catalog.
_Avoid_: ambiguous metric

**Shared name**:
A company name two or more snapshot members answer to ("Lincoln"). The analyst is asked which one; the largest is not assumed (ADR 0010).
_Avoid_: ambiguous company (in prose), alias collision

**Everyday-word name**:
A company name that 10-Q filings write in lower case mid-sentence as an ordinary word ("Target", "Block"). It names the company only where a question uses it as one (ADR 0010): not "intel aside", "to the micron", "the apple of" or "an oracle for", whichever planner proposed the company.
_Avoid_: common-word company, stopword name

**Segment**:
A part of a company that the filings' structured data does not report on its own ("iPhone", "AWS", "Azure"). Its figure is the company-wide one, with a note saying so. A question that names no company but names a segment only one company reports is about that company ("iPhone sales" is Apple's revenue), whichever planner read it.
_Avoid_: product line, business unit (unqualified)

**Comparison base**:
What a change is measured against: the same quarter a year earlier (year over year) or the quarter before (sequential). Growth is year over year unless the analyst says sequential; a change that names neither is asked about (ADR 0010). Naming both shows both changes on every quarter, wherever the bases sit in the question.
_Avoid_: delta, period-over-period (unqualified)

**Window**:
A count of recent quarters the analyst asks for ("past six quarters", "last two years"), read by one grammar whichever planner proposed the analysis (ADR 0010). A "since" window ("since 2024") is every filed quarter that ended on or after 1 January of that year, as each company's filings date them, at most the window cap; it is not a count fixed by today's date. Named as a fiscal year ("since fiscal 2025", "since FY2025"), it is every quarter of each company's own fiscal year and after, read where its fiscal periods are listed, as a named period is. A change asked over a "since" window is year over year over it, as over any window.
_Avoid_: lookback, range

**Conversation thread**:
One analyst investigation, identified and persisted. It carries the analysis spec, any pending clarification, the last result, and evidence references, and is bound to one runtime for its whole life. Threads do not share state.
_Avoid_: session, chat, conversation history, memory

**Recorded runtime**:
The provider set that replays captured SEC, news, and model responses. Orchestration and presentation are the same as live; only the providers differ. A thread started on it never takes a live turn.
_Avoid_: kill-switch, fixture mode, guided demo data, cassette

**Live runtime**:
The provider set that calls SEC EDGAR, the news search, and the model provider. A thread started on it never takes a recorded turn.
_Avoid_: production mode, real mode

**Analysis spec**:
The typed, resolved statement of the analyst's current quantitative question: companies or constituents, closed-catalog metrics, period selection, operations, and requested presentation. Resolved means CIKs and catalog slugs, so it can execute: a company's CIK comes from the market snapshot, or SEC's ticker map for one the snapshot leaves out, and every lookup and every per-company date asks by it. A name neither knows stays a name, and its cells say it was not found. It is the thing a follow-up edits.
_Avoid_: query, plan, intent, request

**Spec patch**:
The model's proposed edit to an analysis spec — additions, removals, replacements, and whether this turn extends or replaces the current analysis. Deterministic code resolves and validates it; a patch is never executed as given.
_Avoid_: plan, tool call, spec (unqualified)

**Pending clarification**:
An analysis spec held on a thread, awaiting the analyst's answer to one open question. Nothing has been fetched. Answering resumes it; asking something unrelated discards it.
_Avoid_: clarify pane, pending plan, interrupt

**Exploratory research**:
A labelled, cited, read-only answer for questions that no analysis spec expresses. It cannot produce reported facts, structured rows, or computed values.
_Avoid_: analysis, essay, explain
