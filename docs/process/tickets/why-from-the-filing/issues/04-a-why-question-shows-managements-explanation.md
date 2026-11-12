# A why question shows Management's explanation

Spec: `design.md` and ADR 0017, including its 11 November 2026 revision. Phase B (ticket 07) is what ships:
- code offers up to eight MD&A paragraphs;
- gpt-6.1-sol chooses the ones that state the cause and explains them in management's words;
- the quote lock and the numeral lock check every answer.

Its evaluation cleared the bar on an unseen final set (`docs/evaluation/explanation.md`, phase B final).

**Files (this ticket only):**
- `src/financial_analyst_agent/contracts.py`: an `explanation` field on `TurnResult`, and a `Runtime` slot for the explanation completer if one is needed;
- `src/financial_analyst_agent/runtime.py`: the live completer through the shared spend cap, and a recorded one;
- `src/financial_analyst_agent/graph/spec_turn.py` and/or `turn_graph.py`: where a figures answer is annotated;
- `src/financial_analyst_agent/presentation.py`: the presentation contract;
- `src/financial_analyst_agent/api.py`, if needed;
- `src/financial_analyst_agent/guide.py`: the bare "why?" reply;
- `src/financial_analyst_agent/answer_notes.py`: the why notes;
- `src/financial_analyst_agent/data/explanation_recordings.json` (new);
- `web/lib/types.ts`;
- `web/components/explanation.tsx` (new) and `web/components/answer.tsx`;
- `README.md` and `docs/prompts-and-controls.md`;
- tests on both sides.

**What to build:**

**When it shows:**
- A why question about a figure in phase A's scope (`explanation.covers`: a year-over-year question about a covered amount): "why", "what drove" or "what caused" (`WHY_CHANGE` or `answer_notes._ASKS_WHY`).
- A bare "why?" ("why is that?", "how come?") after such a figures answer on screen.
- A plain lookup never shows it.

**What the turn does:**
- For each company in the answer, up to four, take the latest row's filing (`accession_number`, `source_url`). Read it with `runtime.filings.get_filing_document`, which is cached, counts against the turn's SEC budget and is recorded.
- Call `explanation.model_explanation` with the answer's first metric and the year-over-year basis.
- A failure of any kind (SEC, model, a lock) never fails the turn. The figures still show, and the panel says what happened.

**Out of scope:**
- **A sequential why question** keeps the year-over-year route: the panel says "This 10-Q explains the change against a year earlier, not the quarter before" and shows the year-over-year explanation.
- **A metric outside the scope** (other margins, ratios, cash flow) keeps ADR 0016's note.
- **A figure with no filing** (market cap, price) keeps ADR 0016's note.

**Runtimes:**
- **Live:** the OpenAI essay client through the shared `DailySpendCap`. With OpenAI off (no key, or public OpenAI disabled) or the cap reached, the panel says management's explanation needs the language model, which is unavailable here, and links the MD&A.
- **Recorded:** replay the model's answers from the evaluation runs (`docs/evaluation/explanation-model-*.json`), keyed by CIK, accession and metric. Copy the ones for recorded filings into `data/explanation_recordings.json`, with a small script or a function in `explanation_evaluation`. Replay them through the same checks. With no recording, the panel says the recorded demo has no explanation for that question.

**In the answer:**
- The panel replaces `WHY_CHANGE_BANNER` and `WHY_NOT_ANSWERED_NOTE` where it shows.
- Where nothing qualifies or an answer is withheld, it shows `explanation.NOT_FOUND_MESSAGE` with a link to the MD&A, in place of the note.

**The web panel**, in the existing answer-card style:
- headed "Management's explanation";
- a source line: "From {short name}'s 10-Q for the quarter ended {date} · MD&A";
- the model's explanation, marked as written by the model from the quoted paragraphs;
- then each chosen paragraph verbatim, in a quotation style, with a "Read in the filing" anchor link;
- on a phone, the explanation shows with "Show the paragraphs".

**Acceptance:**
- **Conversation tests on the recorded runtime:**
  - a why question with a recording shows the panel with its paragraphs;
  - "{figure}" then "why?" shows it;
  - a plain lookup shows none;
  - a why question about market cap keeps the note;
  - a sequential why shows the year-over-year route;
  - a recorded answer that fails the quote lock (a test fixture) shows the not-found line.
- **Live path:** unit tests with a fake completer, including the spend cap reached and OpenAI off.
- **Web:** vitest for the panel; lint, tsc, vitest and the build pass. Run `npm run build` from PowerShell on this machine, because Git Bash fails with Turbopack error 0xc0000142. The Playwright suite also passes: `npx playwright test` from PowerShell in `web/`.
- **Replay:** `compare_answers.py --against origin/master` changes only why conversations; list them in the Answer.
- **Docs:**
  - the README's "How a question is read" updates the why row;
  - Limitations says the explanation covers year-over-year questions about amounts, chosen by the model from code's candidates and held to the filing's words;
  - `docs/prompts-and-controls.md` gains the explanation prompt and the quote lock.

**Blocked by:** 07

**Status:** resolved

## Answer

Shipped. No model was called: the recorded explanations are the committed evaluation runs, and the live path is tested with fakes.

**The turn** (`graph/spec_turn.add_explanation`, a new `explain` step after `annotate` in the structured subgraph):
- **When:** `answer_notes.asks_why` ("why", "how come", "what drove", "what caused" and the rest of ADR 0016's why words) on a table answer whose first metric `explanation.explained_metrics()` covers, with named companies, not a ranking.
- **Bare "why?":** `guide.explains_bare_why` ("why?", "why is that?", "how come?" after figures it can explain). `turn_graph._interpret` then re-runs the analysis on screen (an empty extend patch, from the thread's evidence) with the panel. Any other bare "why?" keeps `WHY_MESSAGE`.
- **Which filing:** each company's latest level row for the metric, up to four. Its accession and URL are the row's, or for a formula (gross margin) its first part's. Only a 10-Q: a figure from a 10-K (a fiscal fourth quarter, so Microsoft's and Cisco's latest quarters on the recorded demo) keeps ADR 0016's note, as a figure with no filing does. The ticket did not say; a 10-K's MD&A explains the year, not the quarter.
- **The call:** `runtime.filings.get_filing_document`, then `model_explanation(..., "year_over_year", ...)` with a `WhyQuestion` (short name, the question, or one written for a bare why, the quarter end, and the direction from the year-over-year change on screen when there is one).
- **Failures never fail the turn.** Each sets the company's `unavailable` line, and the figures show:
  - a withheld or empty answer, or no candidates: `NOT_FOUND_MESSAGE`;
  - OpenAI off, or `SpendCapReached`: `MODEL_UNAVAILABLE_MESSAGE`;
  - the recorded demo with no recording, or no filing text: `NOT_RECORDED_MESSAGE`;
  - SEC failing on the live runtime: `FILING_UNREADABLE_MESSAGE`;
  - any other model error: `MODEL_FAILED_MESSAGE`.
- **Sequential:** an analysis whose change is on the quarter before (`across_periods` or `sequential`, no `year_over_year`) gets `YEAR_OVER_YEAR_ONLY_NOTE` above the year-over-year explanation.
- **Notes:** `WHY_CHANGE_BANNER` and `WHY_NOT_ANSWERED_NOTE` (`answer_notes.WHY_NOTES`) are dropped where the panel shows.

**Contracts:** `TurnResult.explanation` (`Explanation`: metric, note, a `CompanyExplanation` per company with filing and MD&A links, explanation, `ExplanationQuote`s, `unavailable` and `reason`). `Runtime.explanations` is an `ExplanationsPort`: `completer(cik, accession, metric)`. Without it, or without `filings`, the notes stay as before.

**Runtimes** (`runtime.py`):
- **`LiveExplanations`:** `explanation_completer` over the shared `DailySpendCap`, built once. With OpenAI off it returns a completer that raises `ExplanationUnavailable` when asked.
- **`RecordedExplanations`:** replays `data/explanation_recordings.json`, keyed by CIK, accession and metric, through `checked_answer` like a live reply. Each recording carries a digest of the numbered paragraphs it was asked about (`explanation.offered_digest`). A replay for other paragraphs counts as no recording.
- **The recordings:** `explanation_evaluation recordings` writes 41, one per evaluation case the model was asked about, from the tuning and final runs. It checks each case's candidates are unchanged, and a test holds the file to a fresh build.

**Presentation and web:**
- `Presentation.explanation` is a `DisplayExplanation`. Each company has a source line ("From Alphabet's 10-Q for the quarter ended Jun 30, 2026 · MD&A"), links, the explanation, `DisplayQuote`s and the `unavailable` line.
- `web/lib/api.ts` reads it.
- `web/components/explanation.tsx` (`ManagementExplanation`) draws the panel below the figures:
  - the heading and the source line, with MD&A linked;
  - the explanation, marked "Written by the model from the quoted paragraphs";
  - each paragraph in a blockquote with "Read in the filing";
  - on a phone, "Show the paragraphs";
  - otherwise the line, then "Read the MD&A".

**On the recorded demo,** with the panel's paragraphs: Alphabet's revenue, cost of revenue and R&D; Amgen's, Applied Materials', Broadcom's, Gilead's, Palantir's and Thermo Fisher's revenue; AMD's gross margin, operating income and R&D; Broadcom's gross margin, operating income and SG&A; NVIDIA's operating income and SG&A; Apple's, Eli Lilly's and Gilead's R&D; Gilead's SG&A; Micron's gross profit; Tesla's cost of revenue. Good for a screenshot:
- "What caused Alphabet's cost of revenue to rise year over year last quarter?" (three paragraphs);
- "What drove AMD's gross margin year over year?" (two).

Others recorded show the not-found line (the model found nothing). Unrecorded ones say the demo has none.

**Replay** (`compare_answers.py`):
- **Against HEAD:** 2 of 893 differ, both why conversations that now show the panel in place of the note:
  - `extra:Why is Goldman's revenue so volatile?`: no filing text is recorded for Goldman, so the panel says the demo has no explanation;
  - `phrase:since_change:What caused Apple's revenue to fall since 2023?`: Apple's revenue is not recorded.
- **Against origin/master:** 84 of 893 differ. They are the same 2, and 82 headline-only differences from master's ten commits this branch does not have ("A comparison over several quarters says where each company went", "A quarter-over-quarter question gets a quarter-over-quarter headline"). None of the 82 touches a why.

**Tests:**
- `tests/test_management_explanation.py` covers:
  - the recorded conversations: a recording shows paragraphs; figure then "why?", "why is that?" and "how come?"; a plain lookup shows none; market cap keeps the note, and its bare why the guide; operating margin and Cisco's 10-K quarter keep the note; sequential, both ways; a quote-lock failure fixture; nothing found; no recording; a recording for other paragraphs; two companies;
  - the live path with fakes: the completer is asked for the figure's filing; spend cap reached and OpenAI off say the model is unavailable and link the MD&A; the real `LiveExplanations` charges the shared cap and stops at it; an unreadable filing on both runtimes; `live_runtime` wires it.
- Updated for the new behaviour:
  - `test_says_what_it_cannot_do` and `test_held_out_5_findings`: the why note is now pinned on an uncovered margin, and the covered amount gets the panel;
  - `test_api`'s presentation keys;
  - the structured subgraph's steps;
  - `web/lib/demo-answers.json`, regenerated.
- Web: vitest for the panel and the reader. Two Playwright tests: the desktop panel, and on a phone "Show the paragraphs" after "why?".

**Docs:**
- README: the why rows of "How a question is read", the follow-ups paragraph, Limitations, and a sixth instruction under "Prompts and controls".
- `docs/prompts-and-controls.md`: a Management's explanation section (the quote lock), its evaluation row, division of labour, known limits, reproducing, and the prompt verbatim.
- `CONTEXT.md`: the Management's explanation entry now describes phase B, which ships.

**For review** (`rules-to-review.md`, 2026-11-11): `phase-b-prompt.md` still calls itself a draft no model may run. The comment in `explanation.py` now says it is the prompt the runs used.
