# Essay evaluation

Onfile writes three kinds of prose for an analyst: explanations of financial concepts, commentary on a table of figures, and briefs on the past week's news. This evaluation asked whether better instructions write better answers, judged blind against a [frozen rubric](essay-rubric.md), without letting more invented figures through the numeral lock. The [plan](essay-plan.md) was committed before any essay was generated.

**Result.** On 30 held-out questions written by another lab's model, the revised instructions (revision 5) beat the original ones in **26 of 30 cases, losing 2** (p < 0.001), on the same model. They gave no investment advice in any of 60 essays (the original: 4 of 60), and no essay was withheld by the numeral lock. The price is clarity: the revised answers are longer, and the judge found the originals clearer in 22 cases to 7. A second judge from another lab, Grok 4.7, preferred the revision in 18 of 20 pairs and the original in none.

| Held-out measure | Original on terra (the app today) | Original on sol | **Revision 5 on sol** |
| --- | ---: | ---: | ---: |
| Cases won against the original on sol | 0 of 30 | — | **26 of 30** |
| Analytical value (mean, 1 to 5) | 3.07 | 3.42 | **3.90** |
| Calibration | 3.90 | 4.40 | **4.80** |
| Accuracy | 4.10 | 4.50 | **4.55** |
| Clarity | 4.08 | **4.25** | 3.98 |
| Gave no investment advice | 92% | 93% | **100%** |
| Passed the numeral lock | 100% | 97% | **100%** |
| Essays failing any gate (of 60) | 9 | 10 | **4** |
| Median words (explain / analysis / news) | 220 / 224 / 130 | 217 / 240 / 160 | 271 / 274 / 252 |

## Design

- **Arms.** The original instructions on `gpt-5.6-terra` (the app today), the original instructions on `gpt-6.1-sol` (the baseline), and revision 5 on `gpt-6.1-sol`. Comparing the first two isolates the model; comparing the last two isolates the instructions.
- **Questions.** 30 development questions written by Claude and 30 held-out questions written by Grok 4.7, each from the same [brief](essay-brief.md), ten of each kind. News questions mix stories from the week of 5 to 9 October 2026 with general ones ("any news on Apple this week?"). Each question's material was captured once and frozen: an analysis case's table from the recorded runtime, a news case's search results.
- **Judging.** The Claude judge (`claude-sonnet-5-5`) compared every pair of essays for the same question and sample, in both orders; a preference counted only if it survived the swap. It also scored every essay on the rubric's five criteria and four gates. The essay model never judged essays. Grok 4.7 judged 20 held-out pairs with the same prompt, as an independent check.
- **Statistics.** Each case scores +1 when revision 5 wins more of its two pairs, −1 when it wins fewer, 0 when equal; two-sided sign test on the non-zero cases. Rubric means carry 95% bootstrap intervals over cases.

## Held-out results

**Revision 5 against the original, both on sol**

| Criterion | Revision 5 | Original | Even | p |
| --- | ---: | ---: | ---: | ---: |
| **Overall** | **26** | **2** | 2 | **< 0.001** |
| Analytical value | 28 | 2 | 0 | < 0.001 |
| Calibration | 16 | 2 | 12 | 0.001 |
| Accuracy | 6 | 1 | 23 | 0.13 |
| Answers the question | 5 | 5 | 20 | 1.0 |
| Clarity | 7 | 22 | 1 | 0.008 |

By kind, revision 5 won 8 of 10 explanations (none lost), 9 of 10 analyses and 9 of 10 news briefs.

**The model alone.** On the original instructions, `gpt-6.1-sol` beat `gpt-5.6-terra` in all 30 held-out cases, with large gains in accuracy, analytical value and calibration. The instructions and the model each account for a large, separate share of the improvement.

**Gates.** Advice is the gate that matters most at a bank: the original instructions let a buy, sell or wait recommendation through in 5 of 60 essays on terra and 4 on sol; revision 5 in none. Revision 5's four gate failures were all news briefs: three carry a citation to a result that does not support the sentence, or does not exist, and three state a claim beyond what the results say. News citation accuracy did not improve on held-out questions (3 of 20 briefs failing, as for the original on sol).

## Judge agreement

On the 20 pairs both judges saw:

| | Revision 5 preferred | Original preferred | Tie |
| --- | ---: | ---: | ---: |
| Grok 4.7 | 18 | 0 | 2 |
| Claude judge | 15 | 2 | 3 |

The judges gave the same overall verdict on 13 pairs and opposite verdicts on 2. By criterion they agreed on 17 of 20 for accuracy and for analytical value, 13 for clarity, and 9 for calibration. The result does not rest on one lab's model judging instructions written with that lab's model.

## How the instructions changed

Each revision was run on the development set and judged against the original on sol before the next was written. The held-out set was not read or run until revision 5 was frozen.

| Revision | What it added | Development: cases won–lost against the original | Gate failures (of 60) |
| --- | --- | ---: | ---: |
| 1 (original) | One or two sentences per kind, mostly prohibitions | — | 8 |
| 2 | Who the reader is and what a strong answer does; the material each kind may use, with the reason for each limit | 26–1 | 10 |
| 3 | Style guidance; the numeral lock stated outright, with what passes and what fails | 22–2 | 5 |
| 4 | Words directed to analysis rather than background; explanations paired with the evidence that would settle them | 23–3 | 5 |
| 5 | The advice boundary stated explicitly; every quarter in a table marked as filed; 200 to 300 words | 25–1 | 1 |

Two lessons carry beyond this app. First, a revision that described the answer well (revision 2) won decisively but was withheld by the numeral lock four times as often as the original, until the lock itself was explained to the model with failing examples; the app's hard constraints had to be stated as constraints, not left to good writing. Second, guidance on length and style traded analytical value for clarity in a measurable way, and the final length was a deliberate choice between them. The instructions themselves are in [`essay.py`](../../src/financial_analyst_agent/essay.py) and quoted in full in [Prompts and controls](../prompts-and-controls.md).

## Limits

- **Clarity.** The revision is longer, and the judge found it less clear; an analyst who wants the shortest answer may prefer the original's length.
- **News citations.** The development gains did not hold on held-out news briefs; citation accuracy needs a check in code, as figures have, rather than more instruction.
- **LLM judges.** Both judges are language models, which tend to favour longer, more structured answers; the clarity result cuts against that bias, the analytical-value result may benefit from it.
- **One week of news.** News questions and their results come from a single week, captured once.

## Reproducing

```text
uv run python -m financial_analyst_agent.essay_evaluation generate --arm v5@gpt-6.1-sol --set held-out --samples 2 --estimate
uv run python -m financial_analyst_agent.essay_evaluation judge --a v5@gpt-6.1-sol --b v1@gpt-6.1-sol --set held-out
uv run python -m financial_analyst_agent.essay_evaluation report --a v5@gpt-6.1-sol --b v1@gpt-6.1-sol --set held-out
```

Essays, judgements and scores are in [`essays/`](essays/). The full evaluation cost about $9 of OpenAI spend; judging ran on the Claude and Cursor subscriptions.
