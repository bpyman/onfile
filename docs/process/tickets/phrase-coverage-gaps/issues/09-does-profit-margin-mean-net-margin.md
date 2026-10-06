# 09 — Does "profit margin" mean net margin?

**Decide:** `What was Apple's profit margin?` asks which margin was meant. ADR 0004 makes "margin" alone ambiguous; "profit margin" is commonly net margin, and phrase coverage expects `net_margin`. If net margin is right, read it so and say so in ADR 0004; if asking is right, change the phrase coverage case to expect the question and take it off `KNOWN_GAPS`.

Found by phrase coverage ([report](../../../../evaluation/phrase-coverage.md), `src/financial_analyst_agent/phrase_coverage.py`), judged by the README's [How a question is read](../../../../../README.md#how-a-question-is-read). The fix belongs in the shared reading of words both planners pass through (ADR 0010, 0011), not in the rules planner alone.

**Acceptance:** the cases below are read right and taken off `KNOWN_GAPS`; `uv run python -m pytest tests/unit/test_phrase_coverage.py` passes; `uv run python scripts/compare_answers.py` names every conversation whose answer changes, and each change is intended.

**Blocked by:** None — can start immediately

**Status:** resolved

## Answer

Net margin, with a note (decided 2026-10-06). Corporate Finance Institute gives net profit margin as "also known as 'Profit Margin'", and Yahoo Finance's "Profit Margin" is net income ÷ revenue; asking which margin was meant made the analyst answer a question with a settled everyday reading. The answer says "Profit margin here is net margin: net income as a share of revenue. Ask for gross or operating margin to see one of those." `margin` alone still asks. ADR 0004 records it.
