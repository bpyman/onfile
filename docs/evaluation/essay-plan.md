# Essay evaluation: plan

Committed before any essay in the evaluation is generated. Any change after that is listed under "Changes to this plan", with its date and reason.

## Question

Do revised essay instructions write better answers than today's, judged blind against a frozen rubric, without letting more figures through the numeral lock?

A secondary question: how much of any difference comes from the model? Essays move from `gpt-5.6-terra` to `gpt-6.1-sol`, so today's instructions are run on both.

## Arms

| Arm | Instructions | Model | Role |
| --- | --- | --- | --- |
| A0 | Today's (v1) | `gpt-5.6-terra` | Production today |
| A1 | Today's (v1) | `gpt-6.1-sol` | Baseline |
| A2 | Revised (final) | `gpt-6.1-sol` | Treatment |

The planner stays on `gpt-5.6-terra`, the model it was evaluated on; essays get their own model setting.

## Cases

- **Development:** 30 questions written by Claude from [the brief](essay-brief.md), 10 per kind. Revisions are made against these only.
- **Held out:** 30 questions written by Grok 4.7 from the same brief, in a folder holding only the brief, the rubric, the README and the glossary. Used once, for the final comparison.
- **Grounding is frozen.** Analysis cases take their table from the recorded runtime. News cases take up to five search results captured once, for both sets on the same day, and stored with the cases; no arm searches again. Explain cases have none.
- Three explain topics appear in both sets (stock splits and EPS, net interest margin, rates reaching a bank). They stay, and are reported.
- **News questions are a mix.** In each set, 6 are tied to stories from the week of 5 to 9 October 2026 and 4 are general ("any news on Apple this week?"). Grok searched the web while writing; Claude was then asked to do the same, so both sets ask about the same week. One development question that duplicated a held-out story (Intel and Terafab) was replaced before the freeze.
- **Capture.** Tables and news results were captured on 10 October 2026. Every case has grounding; some news cases have only one or two results, or results that miss the question, as live searches do.

## Procedure

1. **Freeze** the rubric, the brief, both case sets, their grounding and this plan, in one commit.
2. **Baseline.** Two essays per development case from A0 and A1.
3. **Develop.** Up to three rounds: read the development failures, revise the instructions, generate two essays per development case, and judge them pairwise against A1. The best round becomes A2. The held-out set is not read or run during development.
4. **Freeze A2.**
5. **Held-out run.** Two essays per held-out case from each of A0, A1 and A2, generated together. A2 is judged pairwise against A1, and A1 against A0; all three get absolute rubric scores.
6. **Report** every result below, whatever its direction.

## Judging

- **Judge:** Claude, through `claude -p`, given the rubric, the question, the grounding and the essays. It is not told which arm wrote which essay. The essay model never judges essays.
- **Pairwise.** Each pair of essays for the same case and sample number is judged in both orders. A preference counts only when both orders agree; otherwise the pair is a tie.
- **Agreement checks.** Grok 4.7 judges 20 held-out pairs. Blake judges 15 held-out pairs blind. Agreement with the Claude judge is reported for each.

## Measures

**Primary.** On the held-out set, A2 against A1, overall preference. Each case scores +1 if A2 wins more of its pairs than A1, −1 if fewer, 0 if equal. Two-sided sign test on the non-zero cases, α = 0.05.

**Secondary.**
- A1 against A0, the same way (the model's effect).
- Per-criterion preferences, A2 against A1.
- Mean rubric score per criterion and arm, with 95% bootstrap intervals over cases.
- Gate pass rates per arm, the numeral lock's withhold rate above all: a revision that wins on quality but quotes figures the lock withholds has not improved the product.
- Essay length per arm.
- Judge agreement: Claude against Grok, and Claude against Blake.

## Budget

At most $14.35 of OpenAI spend for the whole evaluation. Every paid run is priced first (`--estimate`); a run whose estimate would take the total past the cap does not start. Spend is recorded per run. Judging uses the Claude subscription and the Cursor CLI, at no OpenAI cost. News is captured with Tavily, about 20 searches once.

Before the freeze, three essays on questions outside both sets were generated on `gpt-6.1-sol` to calibrate the cost estimate ($0.01).

## Changes to this plan

None yet.
