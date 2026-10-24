# Judge the explanation set, spot-check it, and tune on the development half

A person's ticket: it runs a model judge and needs Blake's review.

**What to do:**

1. Show Blake the rubric and the judge brief (`explanation_evaluation brief`) in full. Run nothing until he approves (standing rule: review prompts before running).
2. claude-opus-5-5 labels every paragraph in `explanation-candidates.json`, both the scored paragraphs and the baseline, one paragraph per call, in a fresh context. Blake chose Opus.
3. Blake spot-checks ten labels, chosen at random with a fixed seed. Record agreement in `explanation.md`. If he disagrees with more than two, revise the rubric and judge again before going on.
4. Tune the scoring on the development half only. Measure the held-out half once, and report it as it comes out.
5. Commit the labels, the report and any scoring change. The bar (ADR 0017) is precision at 3 of 0.8 or better on held-out, with no other-metric paragraph first. If it is missed, say so and stop before ticket 04.

**Blocked by:** 02

**Status:** resolved

## Answer

First run, 24 October 2026: 127 judgements by claude-opus-5-5 (`docs/evaluation/explanation-labels.json`), report `docs/evaluation/explanation.md`. Blake spot-checked the ten labels drawn with the fixed seed and agreed with all ten. The bar was missed: precision at 3 was 0.32 (9 of 28 cases shown), against the baseline's 0.06. Most of the miss was sequential questions (17 of 20 MD&As state no sequential cause) and cash-flow questions landing on cash-balance paragraphs. Tuning continues in ticket 05, on the development half, with a fresh held-out set, because the failures were read from both halves.
