# Management's explanation is quoted from the filing a figure came from

"Why?" is the most common follow-up to a figure, and the app answered it by saying where the answer is: the 10-Q's MD&A (ADR 0016, `guide.WHY_MESSAGE`). It did not show it. A product review on 23 October 2026 ranked answering it as the largest gain in usefulness left. A prototype on the recorded 10-Qs found a paragraph stating the cause, using only code, for Apple's and Micron's gross margin and Pfizer's and Nvidia's revenue.

## Decision

- **A why question about a figure is answered with Management's explanation:** the MD&A paragraphs that explain the figure's move, quoted verbatim from the filing the figure came from (the same accession the evidence inspector links), with a link to each passage. "Why", "what drove" or "what caused" about a figure, and a bare "why?" after a figures answer, all show it. A plain lookup never does.
- **Code chooses the paragraphs.** A paragraph is scored on:
  - the metric's own words, from the catalog;
  - causal and change wording;
  - the comparison basis asked for.

  The panel shows up to three paragraphs. Where none scores, it says the MD&A does not discuss the figure in words it can find, and links the section.
- **A model may later explain the paragraphs, but never stands in for them** (phase B). Its explanation must pass a quote lock in code, under which every quotation appears verbatim in the chosen paragraphs, and the numeral lock. Otherwise it is withheld, and the paragraphs still show.
- **Questions about a filing's text** ("what does the 10-Q say about China") come last (phase C). They need a ninth intent, and so a planner prompt change reviewed before it runs.
- **The PRD's out-of-scope line narrows.** Quoting MD&A paragraphs that explain a figure, or that match a question, is in scope. Open-ended analysis across filings stays out.

## Consequences

- Phase A calls no model. Its cost is the filing document, which filing changes already fetch and cache, and which the recorded runtime already holds for 21 companies.
- Before phase A ships, a set of 40 why questions is labelled by claude-opus-5-5 and spot-checked by a person. The bar is precision at 3 of 0.8 or better, with no paragraph about another metric in first place.
- A filing that cannot be read, or a figure with no filing behind it (market cap, price), keeps ADR 0016's note.
- Paragraph scoring is wording rules, so it can miss an explanation phrased in a way they do not know. The evaluation measures how often, and the "nothing found" reply says so rather than guessing.

## Considered options

- **Send the whole MD&A to the model and let it find the answer.** That costs a call per question, and the model's choice of passage cannot be audited before it is shown. Code choosing first keeps the passages checkable, and gives the model, later, less to misread.
- **Show the MD&A's first paragraph that mentions the metric.** That is simpler, but it often picks a definition or a forward-looking paragraph. It stays in the evaluation as the baseline the scoring must beat.
- **Keep pointing at the MD&A** (ADR 0016's note). That is honest, but it leaves the most common follow-up unanswered when the answer is a few paragraphs away in a document the app already reads.
