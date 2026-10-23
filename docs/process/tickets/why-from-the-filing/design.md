# Why, from the filing: design

Status: proposed, 23 October 2026. Awaiting decisions (end of this file) before any ticket.

## The problem

"Why?" is the most common follow-up to a figure, and the app does not answer it:

- Asked "Why did Target's gross margin jump last quarter?", the live demo shows the change. Then it says "Filings report what changed, not why… Management explains the quarter in the 10-Q's MD&A". It does not open the MD&A.
- A bare "why?" gets the same advice from the guide.
- Since ADR 0016, a mid-sentence "why" gets a note saying it is not answered.

Every one of those replies points at the place the answer sits, a few paragraphs of the filing the figure came from, and stops there.

## What we are building

**Management's explanation**: the paragraphs of a filing's MD&A that explain a figure's move. They are quoted verbatim from the same filing the figure came from, with a link to the passage. The model may summarise them, but it may not change, add to or paraphrase what is quoted.

This extends two locks the app already has:
- **The numeral lock** says a figure in prose must be in the grounding.
- **The quote lock** says a quoted sentence must be in the filing, word for word.

## Phases

Each phase ships on its own and is useful without the next.

### A. Quoted paragraphs, no model

- **When:** a question asks why a figure moved, or what drove or caused it, or a bare "why?" follows a figures answer.
- **What the answer shows:** the figures as today, then a panel headed "Management's explanation", holding:
  - **Source:** the 10-Q (or 10-K) that the latest row's figure came from, by accession number. That is the same filing the evidence inspector already links, so the explanation and the number share a source.
  - **Section:** MD&A, extracted with `filing_change.extract_section` and split with `_paragraphs`. Both already exist, and the recorded runtime already holds the latest 10-Q and the year-earlier one for 21 companies.
  - **Choice:** the top one to three paragraphs, scored by code:
    - the metric's own words, from the catalog: "gross margin", "gross profit", "cost of sales";
    - causal wording: "primarily due to", "driven by", "offset by", "as a result of";
    - change wording;
    - and, where the question names one, the comparison basis: year over year matches "compared to the same period"; sequential matches "from the second quarter" and "sequentially".
  - **Display:** each paragraph verbatim, with its causal clause highlighted and an anchor link into the filing (`filing_anchor_url`, which the filing diff uses).
- **When nothing scores:** "The MD&A in this 10-Q does not discuss gross margin in words I can find", with a link to the section. It is never silence and never a guess.
- **Several companies:** each company's latest filing, one paragraph each, up to four companies.
- **Cost:** none in model calls.

A prototype on the recorded 10-Qs, with no tuning, put a paragraph that states the cause first:
- Apple's gross margin: "primarily due to a different mix of products and tariff refunds, partially offset by higher costs, including memory".
- Micron's gross margin.
- Pfizer's revenue.
- Nvidia's data-center revenue (second).

It missed AMD's gross margin, where paragraphs about operating income ranked first, and Tesla's operating income. The evaluation below measures how often that happens.

### B. A short explanation over the quoted paragraphs

- **Where:** above the paragraphs, a two-to-four-sentence explanation by the essay model, marked as the model's.
- **What it is given:** only the paragraphs Phase A chose, plus the figures on screen.
- **The quote lock, in code:**
  - Every quotation in it must appear verbatim in one of those paragraphs, allowing for whitespace and curly quotes.
  - Every figure must pass the numeral lock.
  - Any failure withholds the explanation, with a line saying why, and the Phase A paragraphs still show.
- **The prompt:** written as a brief, per the essay evaluation's lessons. I would draft it and you would review it before any run.

### C. Questions about a filing's text

- **The question:** "What does Nvidia's 10-Q say about export restrictions to China?" Today it gets a filing diff.
- **The answer:** the MD&A and Risk Factors paragraphs that match the question's own words, quoted as in Phase A, with Phase B's explanation if it has landed.
- **What it needs:** a ninth intent, which changes the planner schema and prompt. Both need your review.

## Evaluation (before Phase A ships)

**The set:**
- 40 "why" questions over the recorded companies.
- Metrics: revenue, gross margin, operating income, net income, R&D, operating cash flow.
- Bases: both year over year and sequential.
- About a quarter of the questions are about a figure whose MD&A says nothing, so the "nothing found" reply is tested too.

**The label:** does the first paragraph shown, or any of the three, state a cause of that metric's move in that quarter?

**What it reports:**
- precision at 1 and at 3;
- how often "nothing found" is right;
- the same figures for a baseline that shows the first paragraph mentioning the metric.

**Bar:** precision at 3 of 0.8 or better, with no paragraph about a different metric in first place. Below it, tune the scoring on a development half, then measure on the held-out half.

**Phase B** is measured as the essays were:
- quote-lock pass rate;
- a judge's faithfulness score, with both orders;
- the explanation against the paragraphs alone, on held-out questions.

## What changes elsewhere

- **PRD:** the out-of-scope line "filing full-text search … open-ended 10-K vs 10-Q analysis" narrows. Quoting MD&A paragraphs that explain a figure, and (Phase C) paragraphs that match a question, are in scope. Open-ended analysis across filings stays out.
- **ADR 0016:** the "why" note becomes the panel wherever a filing is at hand, and stays as the note where none is (a figure from the snapshot, a filing that cannot be read).
- **Guide:** the bare "why?" reply becomes the panel when a figures answer is on screen.
- **MCP:** a `get_explanation` tool, in Phase A or later.
- **Recorded runtime:** eight recorded companies have no filing text: JPMorgan, Wells Fargo, Goldman Sachs, Johnson & Johnson, AbbVie, Merck, Abbott and Intel. Recording their two latest 10-Qs uses SEC only, at no cost.

## Decisions I need from you

1. **Phasing.** Ship A alone first, then B, then C? (Recommended: yes. A is useful, free and auditable on its own.)
2. **Who labels the Phase A set?** You, an LLM judge, or the judge with you spot-checking ten? If a judge, which model? Your default is Opus.
3. **When the panel shows.** On every "why" question and the bare "why?" follow-up, or only when asked ("show management's explanation")? (Recommended: on every why question; never on a plain lookup.)
4. **The panel's name.** "Management's explanation" or "In the filing"?
5. **Recording the eight missing companies' 10-Qs.** This uses SEC only and adds about 2 MB to the recordings. (Recommended: yes.)
