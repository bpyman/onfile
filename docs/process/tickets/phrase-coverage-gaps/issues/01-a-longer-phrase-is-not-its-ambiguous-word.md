# 01 — A longer phrase names its metric, not its ambiguous word

**What to build:** A phrase that contains an ambiguous word (ADR 0004: income, expenses, interest) but names one catalog metric as a whole asks which metric was meant. "Net interest income" was fixed this way (held-out-4 findings 01); these still ask:

- `income from operations` → `operating_income`
- `income taxes` → `income_tax_expense`
- `income before taxes`, `earnings before tax` → `pretax_income`
- `noninterest income`, `non-interest income`, `fee income` → `noninterest_income`, which also needs to be askable as a metric, as `net_interest_income` now is
- `selling, general and administrative expenses` → `selling_general_and_administrative`
- `total equity` → `shareholders_equity`
- `times interest earned` → `interest_coverage`

The longest phrase that names one metric wins over the ambiguous word inside it; the word alone still asks.

Found by phrase coverage ([report](../../../../evaluation/phrase-coverage.md), `src/financial_analyst_agent/phrase_coverage.py`), judged by the README's [How a question is read](../../../../../README.md#how-a-question-is-read). The fix belongs in the shared reading of words both planners pass through (ADR 0010, 0011), not in the rules planner alone.

**Acceptance:** the cases below are read right and taken off `KNOWN_GAPS`; `uv run python -m pytest tests/unit/test_phrase_coverage.py` passes; `uv run python scripts/compare_answers.py` names every conversation whose answer changes, and each change is intended.

**Blocked by:** None — can start immediately

**Status:** ready-for-agent
