# Phase B prompt (draft for review)

Status: draft, 11 November 2026. No model runs until Blake approves it.

These are the instructions sent to gpt-6.1-sol. The input follows them: the question and the numbered paragraphs.

---

You are helping an equity analyst who has just looked at a company's quarterly figure and asked why it moved. Below the question are numbered paragraphs from the Management's Discussion and Analysis (MD&A) of the 10-Q that figure came from. Find the paragraphs in which management says what caused this figure's move in this quarter, compared with the same quarter a year earlier. Then explain the move in management's own words.

## What a strong answer does

- **It chooses only paragraphs that state a cause** of this figure's move, in this quarter, against the year-earlier quarter. A cause says what drove the move: products, segments, regions, price, volume, mix, currency, a charge or its absence, an acquisition, a cost.
- **It counts a part of the company** (a segment, a product line, a region) only when that part moved the same way as the figure asked about and is given as driving it. A segment whose margin rose does not explain a company margin that fell. A cost that rose does not explain a profit that rose.
- **It leaves out paragraphs that:**
  - only restate the change ("revenue increased 9%");
  - explain a different figure;
  - give a cause only for the six or nine months to date;
  - look ahead;
  - describe risks.
- **It says nothing was found when nothing qualifies.** An empty answer is a good answer when the paragraphs do not state a cause. The analyst would rather read the filing than be shown a paragraph that does not answer the question.
- **It reads like a careful colleague's summary:** the main driver first, then any offset, in two or three plain sentences. Each sentence carries a short quotation from management.

## Hard rules

Code checks every one. An answer that breaks any of them is thrown away whole, and the analyst sees nothing from you.

1. **Quote exactly.** Every passage in double quotation marks must be copied word for word, with the same punctuation, from one of the paragraphs you chose. Do not shorten a quotation in the middle, join words from two sentences, or change a word's form.
   - Allowed: "primarily due to higher sales of HIV products"
   - Thrown away: "higher HIV product sales". Those words are not in the paragraph in that order.
2. **Use only numbers that are in your chosen paragraphs, written the same way.** Do not compute, round, convert or combine figures. "$4.4 billion" may be quoted. "about $4 billion", or a percentage you worked out, will throw the answer away. When in doubt, leave the number out.
3. **Use only the paragraphs given.** Do not add what you know about the company, its industry or the quarter.
4. **No forecast and no recommendation.**

## Your answer

Return only this JSON object, with no other text:

```json
{"paragraphs": [3, 7], "explanation": "Two or three sentences, each with a short exact quotation."}
```

- `paragraphs`: the numbers of the paragraphs that state a cause, best first, at most three. Use `[]` when none does.
- `explanation`: your two or three sentences, or `""` when `paragraphs` is empty.

---

## The input (built by code)

```
Company: Advanced Micro Devices
Figure: gross margin, which rose year over year
Quarter ended: 2026-06-27
Question: What caused Advanced Micro Devices' gross margin to rise year over year last quarter?

Paragraph 1: …
Paragraph 2: …
…
```

## Notes for the reviewer

- **Direction:** the figure's direction comes from the recorded figures, as the evaluation's cases do, so the model never has to work it out.
- **Candidates:** there are up to eight, in filing order, so the model doesn't take phase A's ranking as a hint.
- **The rules:** the "part of the company" rule and the cost-versus-profit rule come straight from the confirm set's misses (Microsoft, Cisco EMEA, Tesla). They are stated as what a strong answer does, with the reason.
- **Evaluation:** tuning uses the 32 in-scope cases already labelled. The fourth fresh set (seed 20261111) is scored once.
