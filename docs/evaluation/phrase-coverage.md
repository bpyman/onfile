# Phrase coverage

Generated `2026-10-06T07:02:39.678468+00:00` on the recorded runtime with the rules planner. 273 everyday phrasings of a metric, a window, a change or a follow-up, each asked as a whole question and judged by the README's [How a question is read](../../README.md#how-a-question-is-read). No network and no model. **236 of 273 (86%) are read right.**

| Group | Phrasings | Read right |
| --- | ---: | ---: |
| Metrics | 204 | 172 (84%) |
| Ambiguous metric words | 7 | 7 (100%) |
| Windows | 24 | 23 (96%) |
| Year over year | 11 | 9 (82%) |
| Quarter over quarter | 4 | 4 (100%) |
| Changes with no base | 4 | 3 (75%) |
| Follow-ups | 19 | 18 (95%) |

## Not read right

| Question | Expected | Got |
| --- | --- | --- |
| `What was Apple's income from operations?` | `operating_income` | clarify; latest_quarter |
| `apple income from operations` | `operating_income` | clarify; latest_quarter |
| `What was Apple's selling, general and administrative expenses?` | `selling_general_and_administrative` | clarify; latest_quarter |
| `apple selling, general and administrative expenses` | `selling_general_and_administrative` | clarify; latest_quarter |
| `What was Apple's income taxes?` | `income_tax_expense` | clarify; latest_quarter |
| `apple income taxes` | `income_tax_expense` | clarify; latest_quarter |
| `What was Apple's income before taxes?` | `pretax_income` | clarify; latest_quarter |
| `apple income before taxes` | `pretax_income` | clarify; latest_quarter |
| `What was Apple's earnings before tax?` | `pretax_income` | clarify; latest_quarter |
| `apple earnings before tax` | `pretax_income` | clarify; latest_quarter |
| `What was Apple's total equity?` | `shareholders_equity` | clarify; latest_quarter |
| `apple total equity` | `shareholders_equity` | clarify; latest_quarter |
| `What was Apple's trailing twelve month net income?` | `net_income_ttm` | answer; metrics net_income; companies AAPL; last_n_quarters 4 |
| `apple trailing twelve month net income` | `net_income_ttm` | answer; metrics net_income; companies AAPL; last_n_quarters 4 |
| `What was Apple's TTM net income?` | `net_income_ttm` | answer; metrics net_income; companies AAPL; last_n_quarters 4 |
| `apple TTM net income` | `net_income_ttm` | answer; metrics net_income; companies AAPL; last_n_quarters 4 |
| `What was JPMorgan's NII?` | `net_interest_income` | refuse; latest_quarter; “Unknown metric 'NII'. Allowed: revenue, cost_of_revenue, gross_profit, operating” |
| `jpmorgan NII` | `net_interest_income` | refuse; latest_quarter; “Unknown metric 'NII'. Allowed: revenue, cost_of_revenue, gross_profit, operating” |
| `What was JPMorgan's noninterest income?` | `noninterest_income` | clarify; latest_quarter |
| `jpmorgan noninterest income` | `noninterest_income` | clarify; latest_quarter |
| `What was JPMorgan's non-interest income?` | `noninterest_income` | clarify; latest_quarter |
| `jpmorgan non-interest income` | `noninterest_income` | clarify; latest_quarter |
| `What was JPMorgan's fee income?` | `noninterest_income` | clarify; latest_quarter |
| `jpmorgan fee income` | `noninterest_income` | clarify; latest_quarter |
| `What was Apple's profit margin?` | `net_margin` | clarify; latest_quarter |
| `apple profit margin` | `net_margin` | clarify; latest_quarter |
| `What was Apple's R&D as a percentage of revenue?` | `rd_to_sales` | answer; metrics research_and_development, revenue; companies AAPL; latest_quarter |
| `apple R&D as a percentage of revenue` | `rd_to_sales` | answer; metrics research_and_development, revenue; companies AAPL; latest_quarter |
| `What was Apple's SG&A as a percentage of sales?` | `sga_ratio` | answer; metrics revenue, selling_general_and_administrative; companies AAPL; latest_quarter |
| `apple SG&A as a percentage of sales` | `sga_ratio` | answer; metrics revenue, selling_general_and_administrative; companies AAPL; latest_quarter |
| `What was Apple's times interest earned?` | `interest_coverage` | clarify; latest_quarter |
| `apple times interest earned` | `interest_coverage` | clarify; latest_quarter |
| `Apple revenue over the past decade` | last_n_quarters 40 | answer; metrics revenue; companies AAPL; latest_quarter |
| `Apple revenue compared with the same quarter last year` | year-over-year rows | answer; metrics revenue; companies AAPL; last_n_quarters 4 |
| `Is Apple's revenue up from a year earlier?` | year-over-year rows | answer; metrics revenue; companies AAPL; latest_quarter |
| `What drove the change in Apple's revenue?` | asks | answer; metrics revenue; companies AAPL; latest_quarter |
| `Compare Apple and Microsoft revenue over the last 4 quarters` → `take out Microsoft` | Apple alone | refuse; metrics revenue; companies AAPL, MSFT; last_n_quarters 4; “Unknown metric 'take out'. Allowed: revenue, cost_of_revenue, gross_profit, oper” |

Each miss is a gap in the shared reading of words, which every planner passes through (ADR 0010, 0011); `KNOWN_GAPS` in `phrase_coverage.py` lists them, and the test fails when a phrasing outside it is misread, or one on it starts being read right.
