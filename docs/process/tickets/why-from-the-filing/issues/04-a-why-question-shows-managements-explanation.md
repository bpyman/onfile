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

**Status:** ready-for-agent
