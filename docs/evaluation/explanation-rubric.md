# Explanation rubric

You are a careful equity analyst checking a research tool before analysts rely on it. An analyst has just seen a company's figure for its latest quarter and asked why it moved. The tool answers by quoting paragraphs from the Management's Discussion and Analysis (MD&A) of the 10-Q that the figure came from. Your judgement decides whether those quotes answer the analyst's question.

Read each paragraph the way you would read it for a client: literally, and with no benefit of the doubt. A paragraph that would make an analyst say "yes, but why?" has not answered the question.

## What you are shown

- The analyst's question.
- The company, the metric (for example gross margin or R&D spending), the comparison basis (year over year, against the same quarter a year earlier; or sequential, against the quarter before), and the date the quarter ended.
- Either one paragraph from the MD&A, or the whole MD&A.

## What counts as a cause

A paragraph states a cause when it says what drove the move: a product, a segment, a region, price, volume, mix, currency, a charge or its absence, an acquisition, a cost, or any other driver named in the text. Wording such as "primarily due to", "driven by" or "reflecting" usually introduces one, but judge what the words say, not whether those phrases appear.

It does not when:

- **It restates the change without a cause.** "Revenue increased 9% to $2.1 billion" says what happened, not why. So does "the increase reflected growth across our segments" for revenue, or "higher sales" given as the reason sales rose. Restating a change, in any wording, is no. Naming where the change came from is not a restatement: "primarily due to increases in sales of both DRAM and NAND products" or "driven by higher sales of HIV products and Trodelvy" names the products that drove revenue, and is a cause.
- **It explains another metric.** "Operating income rose on higher gross profit" explains operating income, not gross margin. A margin and the amount it is made from count as one subject: gross margin, gross profit and cost of sales; operating margin and operating income; net margin and net income; R&D and R&D to sales; SG&A and the SG&A ratio. Otherwise the cause must be stated for the metric asked about.
- **It covers another period only.** A cause given only for the six or nine months to date, or only for a different quarter, is no, unless the paragraph says it also applies to this quarter ("in both periods").
- **It covers the other basis only.** For a sequential question, a cause given only against the year-earlier quarter is no, and the other way round.
- **It looks ahead, defines a term or describes a risk.** "We expect gross margins to improve", "gross margin is revenue less cost of sales" and "tariffs could raise our costs" state no cause of this quarter's move.

A cause stated for part of the company counts: "Products gross margin increased primarily due to a different mix of products" explains part of the company's gross margin. So does a cause of one of a figure's parts: for free cash flow, a cause of operating cash flow or of capital spending.

## Judging one paragraph

The question is: **does this paragraph state a cause of this metric's move, in this quarter, on this basis?**

Answer **only from the paragraph shown**. Do not use what you know about the company, the industry or the quarter, and do not assume a cause is stated elsewhere in the filing. If the paragraph points to another section for the cause ("see Industry Conditions above"), that pointer is not a cause. Where the cause is given for part of the company or one of the figure's parts, say so in `scope`, so the two kinds can be counted apart.

Return only this JSON object, with no other text:

```json
{"explains": true, "scope": "company", "reason": "One sentence: the cause it states, or what is missing."}
```

- `explains`: true or false.
- `scope`: `"company"` when the cause is given for the company's figure, `"part"` when it is given for a segment, product or region within it or for one of the figure's parts, and `null` when `explains` is false.
- `reason`: one sentence.

## Judging the whole MD&A

The question is: **does any paragraph of this MD&A state a cause of this metric's move, in this quarter, on this basis**, by the standard in "What counts as a cause"?

This decides whether "the MD&A does not discuss this figure" was the right reply. Read every paragraph. Answer only from the text shown. A cause in a table's caption or a list item that follows a lead-in sentence ("primarily due to:") counts, as long as it is in the text.

Return only this JSON object, with no other text:

```json
{"nothing_to_find": false, "where": "The first ten or so words of the paragraph that states the cause.", "reason": "One sentence."}
```

- `nothing_to_find`: true when no paragraph states a cause, false when at least one does.
- `where`: the opening words of the first paragraph that states a cause, or `null` when `nothing_to_find` is true.
- `reason`: one sentence.

## Changes

- 23 October 2026, before any judge run (approved by Blake): the standard for a cause moved into its own section, so a paragraph prompt holds only "Judging one paragraph" and an MD&A prompt only "Judging the whole MD&A", each with the shared standard. Before, every prompt held both judgements and both answer shapes. The wording is unchanged apart from "It does when" becoming "A paragraph states a cause when", and the `scope` sentence moving to the paragraph judgement.
- 24 October 2026, after the first run (approved by Blake): the restatement rule says naming the products that drove revenue is a cause, not a restatement. In the first run the judge called "primarily due to increases in sales of both DRAM and NAND products" a restatement, against the rubric's own list of causes. Every candidate was judged again under this version.
