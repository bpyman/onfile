Status: ready-for-agent

# Financial analyst agent

This repo is a portfolio project with no deadline. The stories and decisions below are the proof of concept that shipped; deadline and kill-order language is historical. Architectural locks (no LLM math, closed intents, XBRL as quarterly truth) still stand unless a later ADR replaces them. [ADR 0007](../adr/0007-derived-quarters-and-per-share.md) replaced the YTD-subtraction lock with two labelled derivations.

## Problem Statement

The original brief was a technical exercise: a working financial-analyst agent plus a short system design. The brief asks the agent to extract quarterly financials, rank public companies by industry market size, and answer qualitative questions (including AI disruption), routing tools from the user prompt — including prompts that need more than one tool.

The agent should be a well-structured system with a visible process (typed graph, MCP tools, traces), while remaining reliable: numbers must come from real filings and a real ranking snapshot, not from the model. A prior attempt (v1) proved the XBRL fact path but was too narrow (toy universe, no UI, no graph/MCP, no comparisons or news). This repo is the v2 POC locked in grilling.

## Solution

A local Streamlit app that sends each question through one interface, `run_turn`. A typed planner picks a closed intent. Deterministic tools (served over local MCP HTTP, also callable in-process) fetch SEC quarterly facts, rank from a dated universe snapshot, compare period-aligned metrics, search news via Tavily, or write a labeled essay. Structured questions render as tables with provenance. Essays cannot invent numbers. The UI shows intent, tool cards, and the answer in one window. A 2–4 page design doc with one diagram is the other original deliverable.

Live APIs are the default; a fixture kill-switch uses the same renderer if the network fails.

*([ADR 0006](../adr/0006-react-audience-window.md) replaces the Streamlit app: the audience window is now a Next.js app in `web/` over a thin FastAPI seam, and Streamlit is deleted. The rest of this solution stands.)*

## User Stories

1. As Blake, I want a working POC I can demo in 25 minutes, so that a reviewer can see the solution instead of only hearing about it.
2. As Blake, I want a short system-design document with one diagram, so that I can walk the architecture before the live prompts.
3. As Blake, I want the agent's process to be visible (intent, tool traces, MCP tools), so that a reviewer can see how each answer was produced without sacrificing reliability.
4. As a reviewer, I want to ask “What was Google’s net income based on their latest quarterly report?”, so that I can see a real 10-Q fact with provenance.
5. As a reviewer, I want to ask for the top 10 companies in healthcare, so that ranking looks like a real industry sort, not four hand-picked names.
6. As a reviewer, I want to ask for the top 10 healthcare companies and the net income for each, so that I can see multi-tool composition that does not mistype tickers.
7. As a reviewer, I want to ask to compare Microsoft and Google operating margins, so that I can see derived math that is period-aligned and not LLM arithmetic.
8. As a reviewer, I want to ask how AI can disrupt healthcare, so that I can see a qualitative answer that is clearly model analysis and does not invent dollar amounts.
9. As a reviewer, I want to optionally ask about NVIDIA supply-chain issues, so that I can see news-grounded discussion or an honest refuse if search returns nothing usable.
10. As an analyst, I want to look up a named company’s latest quarterly revenue, net income, cost of revenue, gross profit, operating expenses, or operating income, so that I can read reported 10-Q facts.
11. As an analyst, I want those facts selected from SEC companyfacts XBRL, so that the number matches a filing rather than a PDF scrape or a vendor restatement.
12. As an analyst, I want each fact to show accession, form, period start/end, concept, taxonomy, and source URL, so that I can verify the number against EDGAR.
13. As an analyst, I want unknown metrics refused with the allowed list, so that the agent does not guess “costs” or ROE from the wrong statement.
13a. As an analyst, I want an ambiguous metric phrase (`profit`, `profit margin`, `income`) to show a clarify pane listing only the colliding humanized catalog names, so that I retype a unique phrase before any fact tool runs.
13b. As an analyst, I want that phrase taken from my question even when the planner already emitted a catalog slug, so that “income” cannot proceed as guessed net income.
14. As an analyst, I want operating, gross, and net margin computed by a deterministic formula from matched-period reported facts, so that a compare question is answerable without a second source of truth.
15. As an analyst, I want a compare of two companies on a reported metric or allowed formula to fail or go partial when periods do not align, so that I am not shown Microsoft’s quarter against Google’s different quarter as if they were the same.
16. As an analyst, I want Alphabet to appear once (one CIK), so that GOOG and GOOGL do not double-count in ranks or compares.
17. As an analyst, I want rank-and-lookup to pass CIKs from the ranking table into fact lookup, so that the model cannot drop or invent a constituent.
18. As an analyst, I want industry queries like “finance” and “healthcare” to resolve through a closed alias table, so that the brief’s examples work without an LLM guessing a sector.
19. As an analyst, I want unknown industry strings (including “AI”) refused with the allowed names, so that membership stays a data contract.
20. As an analyst, I want ranking membership to come from a dated universe snapshot of US exchange-listed operating companies, so that “top 10” is reproducible and not a live screener surprise.
21. As an analyst, I want ETFs and funds excluded from that snapshot, so that a healthcare ranking is companies, not products.
22. As an analyst, I want the snapshot timestamp visible, so that I know I am looking at a freeze, not “all public companies on earth.”
23. As Blake, I want a build script that can regenerate the snapshot from FMP sector membership and batch caps, so that I can refresh the freeze without changing demo code.
24. As a reviewer, I want ranking to still work if a sector has fewer than 10 operating companies after filters, so that the UI tells me it returned what exists rather than padding.
25. As an analyst, I want qualitative industry/AI questions answered as a labeled model essay with no retrieval, so that think-pieces are possible without pretending they were cited.
26. As an analyst, I want named-company current-event questions to run news-and-explain, so that “what’s going on with NVIDIA” is grounded in search hits.
27. As an analyst, I want news search to take the user query (not only latest headlines by ticker), so that “supply chain” actually searches.
28. As an analyst, I want news hits to include title and URL (and date when present), so that I can open the source.
29. As an analyst, I want empty or unusable news hits to refuse rather than fall back to training data, so that the agent does not hallucinate a supply-chain brief.
30. As an analyst, I want the essay renderer to allow only numbers that already appear in tool JSON, so that the model cannot invent $29.8B.
31. As an analyst, I want structured lookup/compare/rank answers rendered from tool fields as tables, so that a chatty paragraph cannot rewrite the numbers.
32. As a reviewer, I want to see the closed intent on screen, so that I know whether this turn was lookup, compare, rank, rank-and-lookup, explain, or news-and-explain.
33. As a reviewer, I want tool-call cards with arguments and provenance, so that the graph/MCP design is visible without opening a second window.
34. ~~As Blake, I want Streamlit to be the only audience window, so that I do not split attention across Studio or Inspector.~~ *(Superseded by [ADR 0006](../adr/0006-react-audience-window.md): the Next.js window is the only audience window. The intent stands: one window, no Studio or Inspector.)*
35. As Blake, I want a fixture/replay kill-switch that uses the same renderer, so that a network failure does not kill the 25 minutes.
36. As Blake, I want to say out loud when the kill-switch is on, so that I do not pretend a cassette is live EDGAR.
37. As Blake, I want gold coverage of the demo script prompts, so that I do not discover a wrong Microsoft/Tesla/Apple number in a live demo.
38. As a developer, I want `run_turn` to accept a runtime of adapters (facts, snapshot ranking, news, LLM completer), so that tests and the kill-switch do not require live SEC/FMP/Tavily/OpenAI.
39. As a developer, I want MCP HTTP to expose the same five tools the graph uses, so that the design deliverable (tools as a service boundary) is real, not slideware.
40. As a developer, I want the graph to call those tools without depending on stdio subprocesses, so that a hung MCP child process cannot take down the app.
41. As a developer, I want to port v1’s SEC fact selector rather than rewrite XBRL selection, so that directly-reported quarterly duration rules stay intact.
42. As a developer, I want Decimal — not float — for money and ratios, so that provenance-carrying math does not pick up binary junk.
43. As a developer, I want a fiscal fourth quarter or cash-flow quarter derived only by the two subtractions ADR 0007 allows, labelled and with both filings as evidence, and per-share figures never derived, so that nothing is invented. (Revised by ADR 0007; originally: YTD subtraction and Q4 derivation forbidden.)
44. As a reviewer, I want a refuse for an unknown metric or industry to be typed and listed, so that I can see the system’s honesty under a bad prompt.
45. As a reviewer, I want partial compare/rank-and-lookup rows when one issuer’s fact is missing, so that nine good rows are not thrown away.
46. As Blake, I want PDF extraction left as a later fallback with warnings, so that I can defend XBRL in Q&A without shipping an unevaluated parser.
47. As Blake, I want FMP ratios and edgartools out of the live number path, so that “latest quarterly report” is not silently TTM or a statement parse.
48. As Blake, I want news to stay a backup prompt, so that the scripted 25 minutes still hits the brief’s examples plus the margin compare.
49. As an analyst, I want “banks” and “software” aliases only if the snapshot actually distinguishes those sets from their parent sectors, so that I am not shown a duplicate of technology labeled as software.
50. As Blake, I want the design doc to list the locked ADRs (XBRL primary, no LLM math, closed aliases, Tavily wrapper, numeral lock, snapshot ranking), so that Q&A has a written trail.
51. As a reviewer, I want to brainstorm production next steps from those ADRs (PDF verify-against-XBRL, vendor TTM as a labeled column, broader catalog review), so that the remaining 35 minutes is about judgment, not missing demo features.
52. As a developer, I want Streamlit to display the model-analysis banner on `explain` and news citations on `news_and_explain`, so that qualitative provenance is as visible as XBRL provenance. *([ADR 0006](../adr/0006-react-audience-window.md): the Next.js window displays them.)*
53. As a developer, I want Tavily extract/map/crawl hidden from the graph, so that the model cannot wander the web in a demo turn.
54. As Blake, I want local Python, OpenAI structured outputs (as in v1), FMP for snapshot/caps, Tavily for news, and SEC for facts, so that I can run the demo on my machine with keys I already have.
55. As a developer, I want identity resolution (ticker/name → CIK, preferred ticker) inside tools, so that the planner never has to emit a separate resolve step that can desync.
56. As a reviewer, I want Google accepted as an issuer alias for Alphabet, so that the brief’s example prompt works.
57. As an analyst, I want lookup of a company that has no standalone quarterly fact to error clearly, so that I do not get a silently derived quarter.
58. As Blake, I want the three live prompts rehearsed against live APIs the same day, so that kill-switch remains a fallback rather than the plan.
59. As a developer, I want gold tests to replay recorded MCP/tool results, so that CI does not need network.
60. As Blake, if a slice has to shrink, I want news and UI chrome to die before XBRL correctness, snapshot top-N, the composed healthcare prompt, and on-screen provenance, so that a demo still shows a reliable system.

## Implementation Decisions

- **Primary seam:** one application interface, `run_turn(query, runtime) → TurnResult`. Streamlit, tests, and the fixture kill-switch all call this. *([ADR 0006](../adr/0006-react-audience-window.md): the FastAPI seam the Next.js window calls takes Streamlit's place.)* FastMCP HTTP, LangGraph internals, Tavily, FMP, and SEC HTTP are adapters behind it, not additional feature seams. *(ADR 0005 adds one conversation seam above this — thread id + message + runtime. `run_turn` stays as a compatibility wrapper and remains the gold-test surface.)*
- **Runtime adapters:** fact lookup (SEC XBRL, ported from v1), ranking over a checked-in universe snapshot (optional live cap refresh must not change membership), news search (Tavily behind the news tool), LLM completer (structured intent plus essay). Fixture runtime swaps all of these for recorded adapters.
- **Closed intents:** `lookup` | `compare` | `rank` | `rank_and_lookup` | `explain` | `news_and_explain` | `exploratory_research` | `filing_change`. The planner may only emit this enum (plus parameters). No open ReAct. One user prompt maps to one intent; composition is inside `rank_and_lookup` and `news_and_explain`, not by the model chaining tools. *(ADR 0005 supersedes the one-prompt-one-intent rule: composition moves into a patchable analysis spec over companies × metrics × periods × operations. "No open ReAct" on the number path stands.)* `exploratory_research` shares the news-grounded essay helper with `news_and_explain` (same search → numeral-lock flow) but keeps its own intent and `exploratory-research` banner for thematic/open questions with cited news and no structured rows.
- **TurnResult (decision shape from grilling):** intent; ordered tool traces (tool name, args, provenance/source ids); renderer kind (`table` | `essay` | `refuse` | `clarify`); table rows or essay text; banners (`model-analysis`, `exploratory-research`, and/or news citations); numeral-lock extras if any (must be empty on success). Clarify lists colliding humanized metric names only; it is not `st.error` and it does not call tools.
- **Five MCP tools:** `rank_companies`, `get_financials`, `compare_metrics`, `explain_topic`, `search_news`. Identity resolution is inside those tools. Local FastMCP over HTTP; the app uses the same tool implementations in-process or over that HTTP — not stdio as the only path. A second MCP client (Inspector/Cursor) is design-optional, not a live requirement.
- **Port v1 fact engine:** companyfacts JSON, submissions, ticker/CIK identity, 70–110 day standalone quarterly duration, accession + end date + form + unit filters, `AmbiguousFactError` rather than picking silently, Decimal money, no YTD subtraction (since revised by ADR 0007). Expand the reported metric catalog; do not replace the selector with edgartools or FMP statements.
- **Reported metrics:** `revenue`, `cost_of_revenue`, `gross_profit`, `operating_expenses`, `operating_income`, `net_income`, `research_and_development`, `selling_general_and_administrative`, `interest_expense`, `income_tax_expense`, `pretax_income`. **Formulas:** `gross_margin`, `operating_margin`, `net_margin`, `rd_to_sales`, `sga_ratio`, `effective_tax_rate` as Decimal division of named components; `interest_coverage` as operating income over interest expense. **Snapshot metrics:** `market_cap` from the dated FMP universe freeze (not a 10-Q fact; freeze presence is required). Metric phrases are a closed table on the user question (ADR 0004): unique name/alias → proceed; ambiguous metric → clarify pane; unknown metric → refuse with the full list. No balance-sheet/instant ratios in this PRD. The phrase table may grow when the catalog grows.
- **`compare_metrics`:** one tool; issuers list + metric or formula; resolve to CIKs; fetch components; same `start`/`end` or do not compute; partial rows with typed reasons; share-class consolidation (one row per CIK).
- **`rank_and_lookup`:** executor runs rank, then batched `get_financials` on CIKs taken from ranking state. The LLM never types the constituent list.
- **`news_and_explain`:** executor runs `search_news(query)` then the essay renderer on those hits only. `explain` never calls Tavily. Named-company current events without usable hits → refuse, not a memory essay.
- **`exploratory_research`:** same news-grounded essay helper as `news_and_explain` (constrained `search_news(query)` → essay → numeral lock, no fact/ranking tools, no structured rows). Used for thematic/open questions no analysis spec expresses. Empty hits → refuse. Carries the `exploratory-research` banner.
- **`filing_change`:** accession-pinned MD&A / Risk Factors comparison between two named 10-Q or 10-K accessions. Deterministic section extraction by Item heading plus paragraph diff; the model does not pick filings or rewrite diffs. With no accessions named, deterministic code compares the company's latest 10-Q with its 10-Q for the same quarter a year earlier and says which filings it chose; one accession alone, or unresolvable ones → refuse. Local workflow (not an MCP tool); summary sentence only when asked.
- **`search_news`:** Tavily Search with `topic=news`, week or month time range, max 5 results; drop hits missing title or URL; return title, URL, snippet, score, published time if present. Do not expose extract/crawl. Do not use FMP ticker-only news as the search tool. Do not use keyless DuckDuckGo as the live search backend.
- **Universe snapshot:** offline build from FMP sector/industry membership + batch market caps; drop ETFs/funds; consolidate share classes by CIK; write a dated snapshot the app reads. Membership does not change during a demo turn. Closed alias table maps finance/healthcare/technology and canonical FMP sector names; banks/software only if membership differs from the parent. “AI” is not an industry.
- **Ranking scope:** US exchange-listed operating companies in the snapshot. Do not claim global or complete coverage of all public companies.
- **Renderers:** lookup/compare/rank/rank-and-lookup always table (or refuse/partial table/clarify). Ambiguous metric → clarify pane, same intent, no tools. explain → essay with model-analysis banner and numeral lock. news-and-explain → essay with citations from hits and numeral lock (news JSON tokens are allowed). exploratory-research → essay with citations plus `exploratory-research` banner and numeral lock. filing-change → table/cards of deterministic disclosure diffs (or refuse). Never mix unsourced dollars into a bannered essay.
- **LLM:** official OpenAI structured outputs for intent (same family as v1). Essay generation is a second structured/plain completion that is then numeral-locked. Missing OpenAI config is a typed configuration error, not a regex planner. *(Revised: without an OpenAI key, or where the public demo does not allow it, the live runtime plans with the deterministic rules planner (`rules_planner.py`) over the same closed intents and catalogs. Written answers and news search then replay only the recorded demo's captured answers, labelled as replayed; any other news or essay question is refused as switched off, never answered as if a live search ran.)*
- **UI:** one Streamlit app — storefront landing plus query, intent chip, tool cards, answer, with guided first-run and trend visuals. Kill-switch toggles fixture runtime. Public demo uses per-thread session quotas (turn and live-SEC caps) and a snapshot freeze copy; no cross-thread memory. Gold set is not shown as a second product UI. *(Superseded by [ADR 0006](../adr/0006-react-audience-window.md): one Next.js window over a FastAPI seam, with the same storefront, quotas, and snapshot copy. The runtime switch starts a new thread on the other runtime.)*
- **Design deliverable:** 2–4 page doc + one diagram (user → intent → MCP tools → structured vs essay renderer) + ADR list of the locks above. This is audience material, separate from this PRD.
- **Kill order if a slice has to shrink:** extra polish, then news, then UI chrome. Last to die: correct XBRL, correct snapshot top-N, composed healthcare prompt, provenance on screen.
- **Sibling prior art:** v1 at the adjacent `financial-analyst-agent` repo is the source of the fact engine and of test style (offline default, network-marked live tests, captured SEC fixtures). Do not treat v1’s closed four-name universe, missing UI, or “no LangGraph/MCP/PDF” non-goals as v2 constraints except where this PRD restates them (PDF still out; MCP/graph now in).

## Testing Decisions

- **Good tests** assert `run_turn` external behavior: given a query and a runtime, the TurnResult intent, traces, renderer, payload values, provenance fields, banners, and refuses. They do not assert LangGraph node names, MCP wire JSON, Streamlit widget state, or Tavily HTTP.
- **The one feature seam is `run_turn`.** *(ADR 0005: new multi-turn behaviour is asserted at the conversation seam; these gold tests stay on `run_turn` with no assertion changes.)* Gold tests (the original brief's script; keep green):
  1. Microsoft pre-tax income — `lookup`; 10-Q `pretax_income` value and provenance from the fact adapter; table renderer.
  2. TSLA vs GM revenue — `compare`; two issuers on a reported line; same period, or each issuer's own latest quarter with an explicit note that the periods differ (`period_mismatch` stays for a formula whose components cover different periods).
  3. Top 10 tech companies R&D spend — `rank_and_lookup`; CIKs from ranking state; `research_and_development` per row; snapshot membership, not a live screener; partial row if a fact is missing.
  4. Effects of recent Strait of Hormuz closures on Exxon — `news_and_explain`; essay grounded in fixture hits, or refuse if search is empty.
- Additional `run_turn` cases: `explain` on an industry/AI prompt shows model-analysis banner and no novel numerals; `news_and_explain` with fixture hits cites only those hits; `news_and_explain` with empty hits refuses; unknown “AI” industry rank refuses; share-class consolidation; compare across different issuer quarters (values kept, periods-differ note, never blended); ambiguous metric (`profit`, `profit margin`, `income`) clarifies with the colliding names only and no tools.
- **Fixture runtime** is how gold tests and the kill-switch run. Recorded tool results / captured SEC fixtures are allowed inside adapters. Default unit/integration suite is offline (same posture as v1: no network unless marked).
- **Fixture evaluation scorecard** (`evaluation.py` → `docs/evaluation/scorecard.md/.json`) rehearses intent routing and numeral-lock cases on the fixture runtime and publishes pass/fail. It is portfolio evidence, not a second test seam.
- **Inherited fact-selector tests** travel with the v1 port (duration bounds, accession filters, ambiguity). They are not redesigned; regressions there fail the port. New metric names need catalog/selector coverage, still through existing fact-selection behavior plus `run_turn`.
- **Snapshot builder** is not a second product seam. Ranking tests inject a checked-in snapshot. If the builder is tested at all, it is only that filters (ETF/fund/share class) applied to a stub vendor dump produce a snapshot the rank adapter can read — not live FMP in CI.
- **Prior art:** v1’s pytest layout, `respx` for HTTP adapters, captured Apple companyfacts fixtures, Decimal assertions, and “LLM never appears in executor tests.” v2 gold tests should inject a fake structured completer for intent rather than calling OpenAI in the default suite.

## Out of Scope

- PDF / 10-Q document parse (later fallback with warnings only; not in the original proof of concept).
- FMP ratios or edgartools as the source of quarterly facts or live compare margins.
- Global listings; claiming a complete catalog of all public companies.
- Open/LLM industry mapping; SIC-from-EDGAR as the rank taxonomy.
- Balance-sheet and instant metrics (current ratio, D/E, ROE). Operating cash flow, capital expenditure, free cash flow and EPS are in scope since ADR 0007.
- YTD subtraction and Q4 derivation beyond the two ADR 0007 rules; shares×price market cap.
- LangGraph Studio as the audience view; Claude Desktop as a required second client; stdio-only MCP.
- Authentication, cloud deploy, streaming-as-a-product. Multi-turn thread state is now in scope per ADR 0005 (persisted analysis spec, resumable clarification); per-thread public-demo quotas and deploy docs for the portfolio demo are in scope; cross-thread long-term memory and personalization stay out.
- Rewriting the v1 XBRL selector from scratch.
- Extra analyst tools (peers, filing full-text search) beyond the five MCP tools and eight intents above. Accession-pinned MD&A / Risk Factors filing-change diffs are in scope; open-ended 10-K vs 10-Q analysis is not.
- Tavily extract/map/crawl, keyless DuckDuckGo, or a second search vendor.

## Further Notes

- Origin: a proof of concept built to a technical brief (August 2026). There is no remaining deadline; this is a portfolio project. The brief’s “reported income” wording is an ambiguous metric; the demo asks named catalog lines.
- v2 folder is the presentation repo; v1 remains the fact-engine donor. Do not require v1 to stay running as an HTTP backend.
- Glossary is `CONTEXT.md`; ADRs are under `docs/adr/`. This PRD remains the product spec for the shipped POC.
- The test seam was proposed as a single `run_turn` interface (snapshot builder not a second feature seam). Publishing proceeds on that basis after skills setup; implementation should not add HTTP/MCP/UI seams as the gold-test surface.
