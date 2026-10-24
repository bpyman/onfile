# Management's explanation: evaluation

Written by `uv run python -m financial_analyst_agent.explanation_evaluation score`. Labels by claude-opus-5-5. The cases are `explanation-cases.json`; the paragraphs labelled are `explanation-candidates.json`; the judge's brief is `explanation-rubric.md`.

Precision at k: of the cases shown at least one paragraph, the share where one of the first k states a cause of the metric's move. The baseline shows the MD&A's first paragraph that names the metric, so its precision at 1 and at 3 are the same. "Nothing found" is right when the judge found no cause anywhere in the MD&A.

Bar: precision at 3 of 0.8 or better for the scoring, with no first-place paragraph about another metric.

## dev

| Method | Shown | Precision at 1 | Precision at 3 | Nothing found right |
| --- | --- | --- | --- | --- |
| scoring | 13 of 20 | 0.23 (3 of 13) | 0.23 (3 of 13) | 0.57 (4 of 7) |
| baseline | 17 of 20 | 0.12 (2 of 17) | 0.12 (2 of 17) | 0.67 (2 of 3) |

First-place paragraphs about another metric (by code's reading):

- None.

## held-out

| Method | Shown | Precision at 1 | Precision at 3 | Nothing found right |
| --- | --- | --- | --- | --- |
| scoring | 15 of 20 | 0.27 (4 of 15) | 0.40 (6 of 15) | 0.80 (4 of 5) |
| baseline | 16 of 20 | 0.00 (0 of 16) | 0.00 (0 of 16) | 0.75 (3 of 4) |

First-place paragraphs about another metric (by code's reading):

- None.

## all

| Method | Shown | Precision at 1 | Precision at 3 | Nothing found right |
| --- | --- | --- | --- | --- |
| scoring | 28 of 40 | 0.25 (7 of 28) | 0.32 (9 of 28) | 0.67 (8 of 12) |
| baseline | 33 of 40 | 0.06 (2 of 33) | 0.06 (2 of 33) | 0.71 (5 of 7) |

First-place paragraphs about another metric (by code's reading):

- None.

