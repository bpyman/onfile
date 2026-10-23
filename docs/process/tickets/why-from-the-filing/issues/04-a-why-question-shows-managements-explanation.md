# A why question shows Management's explanation

Spec: `design.md` phase A and ADR 0017. Build this after the evaluation clears its bar (ticket 03), so the panel ships with measured precision.

**Files (this ticket only):**
- `src/financial_analyst_agent/contracts.py`: an `explanation` field on `TurnResult`;
- `src/financial_analyst_agent/graph/spec_turn.py` and/or `turn_graph.py`: where a figures answer is annotated;
- `src/financial_analyst_agent/presentation.py`: the presentation contract;
- `src/financial_analyst_agent/api.py`, if the contract needs it;
- `src/financial_analyst_agent/guide.py`: the bare "why?" reply;
- `src/financial_analyst_agent/answer_notes.py`: the why notes;
- `web/lib/types.ts`;
- `web/components/explanation.tsx` (new) and `web/components/answer.tsx`;
- tests on both sides.

**What to build:**

**When it shows:**
- The message asks why a figure moved: `WHY_CHANGE`, or the `_ASKS_WHY` wording in `answer_notes`.
- A bare "why?" (or "why is that?", "how come?") follows a figures answer that is on screen.

**For each company in the answer, up to four:**
- Find the latest row's filing: `accession_number` and `source_url`, read with the runtime's `filings.get_filing_document`, which is cached and recorded.
- Run `explanation.explain` with the answer's first metric and the comparison basis in the spec.

**In the answer:**
- The panel replaces `WHY_CHANGE_BANNER` and `WHY_NOT_ANSWERED_NOTE` wherever it has a paragraph to show. Where nothing is found, it says so in one line and links the MD&A, in place of the note.
- A figure with no filing behind it (market cap, price), or a filing that cannot be read, keeps ADR 0016's note.

**The web panel** follows the existing answer card styles:
- headed "Management's explanation";
- a source line: "Quoted from {short name}'s 10-Q for the quarter ended {date} · MD&A";
- each paragraph verbatim in a quotation style, its causal clause highlighted, with a "Read in the filing" link;
- on a phone, collapsed to the first paragraph, with "Show N more".

**SEC failures:**
- A filing fetch counts against the turn's SEC budget.
- A failure never fails the turn: the figures still show, with the note.

**Acceptance:**
- **Conversation tests on the recorded runtime:**
  - "Why did Apple's gross margin rise last quarter?" shows the figures and the panel, with Apple's mix-and-tariff paragraph first.
  - "Apple gross margin" then "why?" shows the panel.
  - "Apple gross margin" alone shows no panel.
  - A why question about market cap keeps the note.
- **Web:** vitest for the panel; lint, tsc, vitest and the build pass. Run `npm run build` from PowerShell on this machine, because Git Bash fails with Turbopack error 0xc0000142.
- **Replay:** `compare_answers.py --against master` changes only why conversations; list them in the Answer.
- **README:** "How a question is read" updates the why row, and the Limitations section mentions that the paragraphs are chosen by wording rules.

**Blocked by:** 03

**Status:** ready-for-agent
