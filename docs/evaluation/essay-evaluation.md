# Essay evaluation

Onfile writes three kinds of prose for analysts: explanations of financial concepts, commentary on a table of reported figures, and briefs on the past week's news. This evaluation measured whether rewritten instructions produce better answers, judged blind against a [fixed rubric](essay-rubric.md), without weakening the safeguards the app depends on.

**Findings**

- **The revised instructions won 26 of 30 held-out questions and lost 2** (p < 0.001) against the original instructions on the same model. The questions were written by another lab's model and were not seen during development.
- **They gave no investment advice in 60 essays**, against 4 in 60 for the original, and no essay was withheld for an unsupported figure.
- **The model matters too.** On the original instructions, `gpt-6.1-sol` beat `gpt-5.6-terra` in all 30 held-out cases. The app now uses both the revised instructions and `gpt-6.1-sol`.
- **The gain costs some clarity.** Revised answers run about 40 words longer at the median, and the judge found the originals clearer in 22 cases to 7.
- **A second judge from another lab agreed.** Grok 4.7 preferred the revised answer in 18 of 20 pairs and the original in none.

| Held-out results | Original, `gpt-5.6-terra` (before) | Original, `gpt-6.1-sol` | **Revised, `gpt-6.1-sol` (now)** |
| --- | ---: | ---: | ---: |
| Analytical value (1 to 5) | 3.07 | 3.42 | **3.90** |
| Calibration | 3.90 | 4.40 | **4.80** |
| Accuracy | 4.10 | 4.50 | **4.55** |
| Clarity | 4.08 | **4.25** | 3.98 |
| No investment advice | 92% | 93% | **100%** |
| Passed the numeral lock | 100% | 97% | **100%** |
| Essays failing any safeguard (of 60) | 9 | 10 | **4** |
| Median length, words | 197 | 229 | 267 |

## What was compared

**Instructions and models.** Three configurations wrote two essays for each question: the original instructions on `gpt-5.6-terra` (the app before this work), the original instructions on `gpt-6.1-sol`, and the final revision on `gpt-6.1-sol`. The first pair isolates the model; the second isolates the instructions.

**Questions.** Claude wrote 30 development questions and Grok 4.7 wrote 30 held-out questions from the same [brief](essay-brief.md): ten explanations, ten follow-ups to a table, and ten news questions, some about specific stories from the week of 5 October 2026 and some general ("any news on Apple this week?"). Each question's material was captured once and reused by every configuration: the table from the recorded filings, or the news search results.

**Judging.** A Claude judge (`claude-sonnet-5-5`) compared the two essays for each question and sample without knowing their source, in both orders; a preference counted only when it held both ways. It also scored every essay from 1 to 5 on the rubric's five criteria and checked four safeguards: the numeral lock, citations, no advice, and faithfulness to the material. No model judged its own writing. Grok 4.7 judged 20 of the pairs independently.

**Statistics.** A question counts as a win when one configuration wins more of its two pairs. Significance is a two-sided sign test over questions; rubric means carry 95% bootstrap intervals over questions.

## Held-out results

**Revised against original instructions, both on `gpt-6.1-sol`**

| Criterion | Revised | Original | Even | p |
| --- | ---: | ---: | ---: | ---: |
| **Overall** | **26** | **2** | 2 | **< 0.001** |
| Analytical value | 28 | 2 | 0 | < 0.001 |
| Calibration | 16 | 2 | 12 | 0.001 |
| Accuracy | 6 | 1 | 23 | 0.13 |
| Answers the question | 5 | 5 | 20 | 1.0 |
| Clarity | 7 | 22 | 1 | 0.008 |

The gain held across all three kinds of question: 8 of 10 explanations (none lost), 9 of 10 table follow-ups and 9 of 10 news briefs.

**Safeguards.** Advice is the boundary that matters most at a bank. The original instructions let a buy, sell or wait recommendation through in 4 to 5 of 60 essays on either model; the revision, in none. Its four remaining failures were all news briefs, with a citation that points to the wrong result in three and a claim stated beyond the reports in three. News citation accuracy did not improve on held-out questions: 3 of 20 briefs failed under both sets of instructions.

**Agreement between judges.** On the 20 pairs both judges assessed, Grok 4.7 preferred the revision 18 times, the original never, and called 2 even; the Claude judge, 15, 2 and 3. They gave opposite verdicts on 2 pairs. By criterion they agreed most on accuracy and analytical value (17 of 20) and least on calibration (9 of 20).

## Development

The instructions went through four revisions on the development questions. Each revision was reviewed before it ran, judged against the original, and diagnosed from the judge's reasons before the next was written.

| Revision | Change | Why |
| --- | --- | --- |
| 1 | The original: one to three sentences per kind, mostly prohibitions | — |
| 2 | Described the reader and what a strong answer does; set out the material each kind may use, with a reason for each limit | The original gave advice, quoted raw database values and referred to "the supplied JSON" |
| 3 | Added style guidance, and stated the numeral lock outright, with examples of figures that pass and fail | Revision 2 answers ran to 400 words with headings, and the numeral lock withheld 8 of 60, mostly for computed figures |
| 4 | Directed words to analysis rather than background, and paired each possible explanation with the disclosure that would settle it | Revision 3 lost analytical value to revision 2, 5 cases to 17 |
| 5 | Stated the advice boundary explicitly; noted that every quarter in a table has been filed; set 200 to 300 words | Revision 4 twice offered its own view on buying, and once doubted a filed quarter |

**Revision 5 head to head, development questions**

| Revision 5 against | Overall | Analytical value | Clarity | Calibration | Accuracy |
| --- | --- | --- | --- | --- | --- |
| Revision 1 | **25–1** (p < 0.001) | 26–1 | 9–16 | 15–0 | 6–0 (p = 0.03) |
| Revision 2 | 9–7 (p = 0.80) | 10–15 | 15–10 | 4–2 | 3–2 |
| Revision 4 | 7–8 (p = 1.0) | 3–16 | 18–2 | 3–3 | 4–3 |

**All revisions, development questions**

| | Rev. 1 | Rev. 2 | Rev. 3 | Rev. 4 | **Rev. 5** |
| --- | ---: | ---: | ---: | ---: | ---: |
| Overall against revision 1 | — | 26–1 | 22–2 | 23–3 | **25–1** |
| Clarity against revision 1 | — | 2–22 | 12–13 | 5–20 | **9–16** |
| Accuracy (1 to 5) | 4.33 | 4.48 | **4.60** | 4.50 | 4.57 |
| Analytical value | 3.43 | 3.82 | 3.85 | **3.90** | 3.83 |
| Calibration | 4.40 | **4.73** | 4.70 | 4.68 | 4.72 |
| Passed the numeral lock | 97% | 87% | 100% | 100% | **100%** |
| News citations correct | 16/20 | 19/20 | 15/20 | 18/20 | **19/20** |
| No investment advice | 95% | 100% | 100% | 97% | **100%** |
| Faithful to the material | 100% | 98% | 100% | 98% | **100%** |
| Essays failing any safeguard (of 60) | 8 | 10 | 5 | 5 | **1** |

Revision 5 was chosen over revision 4, which it matched overall, because it traded some analytical depth for clarity and passed every safeguard but one.

**What the development showed**

- **Describing a good answer works better than forbidding bad ones.** The jump from revision 1 to revision 2, which replaced prohibitions with a description of the reader and the answer, produced most of the gain.
- **Hard constraints must be stated as constraints.** Revision 2 wrote better answers but was withheld by the numeral lock four times as often as the original. Only when the lock itself was explained, with examples of what fails, did withholding fall to zero.
- **Depth and clarity trade off, and length is the lever.** Each change to length moved analytical value and clarity in opposite directions; the final range is a deliberate choice between them.

The instructions are in [`essay.py`](../../src/financial_analyst_agent/essay.py) and quoted in full in [Prompts and controls](../prompts-and-controls.md).

## Limits

- **Clarity.** The revised answers are longer and judged less clear; an analyst who values brevity above depth may prefer the original's length.
- **News citations.** Development gains in citation accuracy did not carry to held-out questions. Citations need a check in code, as figures have, rather than more instruction.
- **Model judges.** Both judges are language models, which tend to favour longer, more structured answers. The clarity result runs against that bias; the analytical-value result may benefit from it.
- **One week of news.** News questions and their results come from a single week.

## Reproducing

```text
uv run python -m financial_analyst_agent.essay_evaluation generate --arm v5@gpt-6.1-sol --set held-out --samples 2 --estimate
uv run python -m financial_analyst_agent.essay_evaluation judge --a v5@gpt-6.1-sol --b v1@gpt-6.1-sol --set held-out
uv run python -m financial_analyst_agent.essay_evaluation report --a v5@gpt-6.1-sol --b v1@gpt-6.1-sol --set held-out
```

Essays, judgements and scores are in [`essays/`](essays/). The evaluation cost about $9 in OpenAI usage; judging ran on existing Claude and Cursor subscriptions.
