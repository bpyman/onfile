# Essay rubric

How Onfile's written answers are judged. Frozen before any essay in the evaluation is generated; any later change is recorded at the end with its date and reason.

Onfile writes three kinds of essay, each for an analyst at a financial firm:

| Kind | Asked | Grounding the essay may use |
| --- | --- | --- |
| Explain | A conceptual question ("How does a buyback affect EPS?") | None. No numerals are allowed |
| Analysis | A follow-up to a table ("What explains the gap?") | The table's rows |
| News | A current-events question | Up to five search results from the past week |

## Gates

Pass or fail. A failed gate is reported on its own and is not averaged into the scores.

| Gate | Fails when | Judged by |
| --- | --- | --- |
| Numeral lock | The essay quotes a figure its grounding does not hold | Code (`numeral_lock`) |
| Citations | News only: a `[n]` marker points to a result that does not support the sentence it ends, or a sentence stating a reported fact has no marker | Judge |
| No advice | The essay recommends buying, selling or holding a security, or tells the reader what to do with their money | Judge |
| Faithfulness | Analysis and news: a claim about the company or the events goes beyond the grounding and is stated as fact. Explain: a claim about a specific company is stated as fact without being widely established | Judge |

## Scores

Each criterion is scored 1 to 5. The anchors define 1, 3 and 5; 2 and 4 fall between.

**Answers the question**
- 5: The opening sentence answers what was asked.
- 3: The answer is present but partial, or comes after background.
- 1: The essay does not answer the question.

**Accuracy**
- 5: Every claim is correct and traceable to the grounding or to settled financial knowledge.
- 3: One imprecision that would not mislead a reader.
- 1: A material error.

**Analytical value**
- 5: Explains the mechanism or cause, draws the implication an analyst would want, and says what the grounding cannot show.
- 3: Correct but mostly restates the grounding or a textbook definition.
- 1: Generic text that could answer many questions.

**Clarity**
- 5: Plain, well-ordered and as short as the content allows.
- 3: Readable, with some padding, repetition or unexplained jargon.
- 1: Hard to follow, or padded to several times the length needed.

**Calibration**
- 5: Certainty matches the evidence; limits and alternative explanations are stated where they matter.
- 3: Occasional overstatement or needless hedging.
- 1: Speculation stated as fact, or so hedged it says nothing.

## Pairwise judgement

To compare two prompts, the judge sees the question, the grounding and two essays labelled A and B, in random order, without knowing which prompt wrote which. For each criterion, and overall, it answers A, B or tie, with one sentence of reasons. Every pair is judged twice with the order reversed. A preference counts only if it survives the swap; otherwise the pair is a tie.

## Changes

None yet.
