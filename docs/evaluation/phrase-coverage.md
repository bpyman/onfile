# Phrase coverage

Generated `2026-10-06T18:12:08.743729+00:00` on the recorded runtime with the rules planner. 406 everyday phrasings of a metric, a window, a change or a follow-up, each asked as a whole question and judged by the README's [How a question is read](../../README.md#how-a-question-is-read). No network and no model. **396 of 406 (98%) are read right**; the live app's cascade would send 7 to the LLM planner.

| Group | Phrasings | Read right |
| --- | ---: | ---: |
| Metrics | 204 | 204 (100%) |
| Ambiguous metric words | 7 | 7 (100%) |
| Windows | 24 | 24 (100%) |
| Year over year | 11 | 11 (100%) |
| Quarter over quarter | 4 | 4 (100%) |
| Changes with no base | 4 | 4 (100%) |
| Follow-ups | 19 | 19 (100%) |
| Combinations | 98 | 89 (91%) |
| Follow-up combinations | 35 | 34 (97%) |

## Not read right

| Question | Expected | Got |
| --- | --- | --- |
| `$AAPL earnings over the last 4 quarters quarter over quarter` | AAPL; `net_income`; last_n_quarters 4; sequential rows | answer; metrics net_income; companies AAPL; last_n_quarters 5; changes sequential, year_over_year |
| `Apple and Microsoft gross margin growth in Q2 2025` | AAPL, MSFT; `gross_margin`; named; year_over_year rows | answer; metrics gross_margin; companies AAPL, MSFT; named 1 |
| `AAPL vs MSFT EPS in Q2 2025 year over year` | AAPL, MSFT; `eps_diluted`; named; year_over_year rows | answer; metrics eps_diluted; companies AAPL, MSFT; named 1 |
| `AAPL vs MSFT gross margin for the last couple of quarters quarter over quarter` | AAPL, MSFT; `gross_margin`; last_n_quarters 2; sequential rows | answer; metrics gross_margin; companies AAPL, MSFT; last_n_quarters 5; changes sequential, year_over_year |
| `Apple profit margin in Q2 2025 quarter over quarter` | AAPL; `net_margin`; named; sequential rows | answer; metrics net_margin; companies AAPL; named 1 |
| `Apple R&D for fiscal 2025 quarter over quarter` | AAPL; `research_and_development`; named; sequential rows | answer; metrics research_and_development; companies AAPL; named 4 |
| `AAPL R&D in Q2 2025 year over year` | AAPL; `research_and_development`; named; year_over_year rows | answer; metrics research_and_development; companies AAPL; named 1 |
| `AAPL vs MSFT operating profit margin over the last 4 quarters quarter over quarter` | AAPL, MSFT; `operating_margin`; last_n_quarters 4; sequential rows | answer; metrics operating_margin; companies AAPL, MSFT; last_n_quarters 5; changes sequential, year_over_year |
| `apple D&A over the last 4 quarters quarter over quarter` | AAPL; `depreciation_amortization`; last_n_quarters 4; sequential rows | answer; metrics depreciation_amortization; companies AAPL; last_n_quarters 5; changes sequential, year_over_year |
| `Apple revenue for fiscal 2025` → `show that year over year` | AAPL; `revenue`; named; year_over_year rows | answer; metrics revenue; companies AAPL; last_n_quarters 8; changes year_over_year |

Each miss is a gap in the shared reading of words, which every planner passes through (ADR 0010, 0011); `KNOWN_GAPS` in `phrase_coverage.py` lists them, and the test fails when a phrasing outside it is misread, or one on it starts being read right.

## Sent to the LLM planner

The live app plans with the cascade (ADR 0012): the rules planner, and the LLM planner on a turn the rules planner is unsure of. Here a stand-in that declines takes the LLM planner's place, so every answer above is the rules planner's. These are the phrasings the live app would send on, and so could read differently from this report.

| Question | Why the rules planner is unsure | Read right here |
| --- | --- | --- |
| `What was Apple's profit?` | no catalog metric | yes |
| `What was Apple's income?` | no catalog metric | yes |
| `What was Apple's margin?` | no catalog metric | yes |
| `What was Apple's cash flow?` | no catalog metric | yes |
| `What was Apple's interest?` | no catalog metric | yes |
| `What was Apple's expenses?` | no catalog metric | yes |
| `What was Apple's dividends?` | no catalog metric | yes |

`SENT_TO_MODEL` in `phrase_coverage.py` lists them with the reason each is expected, and the test fails when the list and the cascade disagree.
