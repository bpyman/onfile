# Management's explanation: evaluation

Written by `uv run python -m financial_analyst_agent.explanation_evaluation score`. Labels by claude-opus-5-5. The cases are `explanation-cases.json`; the paragraphs labelled are `explanation-candidates.json`; the judge's brief is `explanation-rubric.md`.

Precision at k: of the cases shown at least one paragraph, the share where one of the first k states a cause of the metric's move. The baseline shows the MD&A's first paragraph that names the metric, so its precision at 1 and at 3 are the same. "Nothing found" is right when the judge found no cause anywhere in the MD&A.

Bar: precision at 3 of 0.8 or better for the scoring, with no first-place paragraph about another metric. From the confirm set on, the bar is held against the strict row, which counts only causes the judge gave for the company's figure: the confirm spot-check found the judge counting a segment that moved the other way as "part" of the cause.

Scope: phase A now covers year-over-year questions about amounts and gross margin (ticket 06). Only those cases are counted below. **The dev and held-out figures predate this narrowing:** both sets were drawn under the wider scope (margins, ratios and sequential questions), and the narrowing was chosen after reading the held-out set, so their figures on it are a hypothesis, not a result. The confirm set was drawn after the narrowing, from the narrowed scope, and is the measure.

## dev

Drawn under the wider scope and tuned on (ticket 05). Counted: 6 of 16 cases; the rest are outside the narrowed scope.

| Method | Shown | Precision at 1 | Precision at 3 | Nothing found right |
| --- | --- | --- | --- | --- |
| scoring | 4 of 6 | 0.75 (3 of 4) | 0.75 (3 of 4) | 0.00 (0 of 2) |
| scoring, company-wide causes only | 4 of 6 | 0.50 (2 of 4) | 0.50 (2 of 4) | 0.00 (0 of 2) |
| baseline | 5 of 6 | 0.40 (2 of 5) | 0.40 (2 of 5) | 0.00 (0 of 1) |

First-place paragraphs about another metric (by code's reading):

- None.

## held-out

Drawn under the wider scope; read before the narrowing (ticket 06). Counted: 6 of 20 cases; the rest are outside the narrowed scope.

| Method | Shown | Precision at 1 | Precision at 3 | Nothing found right |
| --- | --- | --- | --- | --- |
| scoring | 6 of 6 | 0.67 (4 of 6) | 1.00 (6 of 6) | n/a (0 of 0) |
| scoring, company-wide causes only | 6 of 6 | 0.67 (4 of 6) | 0.67 (4 of 6) | n/a (0 of 0) |
| baseline | 6 of 6 | 0.33 (2 of 6) | 0.33 (2 of 6) | n/a (0 of 0) |

First-place paragraphs about another metric (by code's reading):

- None.

## confirm

Drawn under the narrowed scope (ticket 06), unseen. Counted: 20 of 20 cases; the rest are outside the narrowed scope.

| Method | Shown | Precision at 1 | Precision at 3 | Nothing found right |
| --- | --- | --- | --- | --- |
| scoring | 14 of 20 | 0.71 (10 of 14) | 0.86 (12 of 14) | 0.17 (1 of 6) |
| scoring, company-wide causes only | 14 of 20 | 0.50 (7 of 14) | 0.57 (8 of 14) | 0.17 (1 of 6) |
| baseline | 17 of 20 | 0.35 (6 of 17) | 0.35 (6 of 17) | 0.00 (0 of 3) |

First-place paragraphs about another metric (by code's reading):

- None.

