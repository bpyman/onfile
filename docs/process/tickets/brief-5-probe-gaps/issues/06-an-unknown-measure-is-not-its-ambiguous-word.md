# 06 — An unknown measure is not the ambiguous word inside it

**What to build:** `What's Apple's debt-to-equity ratio?` asks which equity was meant (shareholders' equity or return on equity). Debt-to-equity is not in the catalog, so it should say it cannot look that up yet, naming it, as `debt` alone does (ADR 0004, unknown). The README now says a word inside an unknown measure that would be ambiguous alone does not make it a question. The longest-span rule already lets a longer unique phrase win over an ambiguous word (ADR 0004, 0010); an unknown measure needs the same: `debt-to-equity`, `debt to equity`, `D/E`, `return on assets`, `equity multiplier` are unknown, not ambiguous.

Add phrase-coverage cases for unknown measures (these and a few more), each expecting the refusal that names the measure.

Found by the set-5 brief's probe dry-run (6 October 2026, second round): a blind session labelled 30 throwaway probes from the draft brief and the README, and the app disagreed. Judged by the README's [How a question is read](../../../../../README.md#how-a-question-is-read). The fix belongs in the shared reading of words both planners pass through (ADR 0010, 0011), not in the rules planner alone, except where the ticket says the rules planner.

**Acceptance:** the cases below are read right; any phrase-coverage case named is taken off `KNOWN_GAPS`; `uv run python -m pytest` passes; `uv run python scripts/compare_answers.py` names every conversation whose answer changes, and each change is intended.

**Blocked by:** None — can start immediately

**Status:** resolved

## Answer

Resolved 2026-10-06. `What's Apple's debt-to-equity ratio?` now says "I can't look up debt-to-equity yet", as `debt` alone does, instead of asking which equity was meant.

- The catalog (`services/metric_catalog.py`) gains `_UNKNOWN_MEASURES`: measures analysts ask for that it lacks, each with the name the refusal uses (`debt-to-equity`, `debt to equity`, `D/E`, `equity multiplier`, `return on assets`, `ROA`, `ROIC`, `net interest margin`, `dividend yield`, `payout ratio`, `price to book`, `price to sales`, `EV/EBITDA`, `enterprise value`, `asset turnover`, `inventory turnover`, `current ratio`, `quick ratio`, `working capital`, `tangible book value`, `total assets`, `liabilities`, `net debt`, `debt`, `leverage`, `customer acquisition cost`, `stock performance`, `share buybacks`, `headcount`). They are read in the same longest-span pass as the unique phrases (ADR 0004), so the ambiguous `equity` inside `debt-to-equity`, and the unique `turnover` inside `asset turnover` or `price` inside `price to book`, do not make the question. `MetricPhraseResolution` gains `term`: the measure's name when the kind is unknown. A catalog metric beside an unknown measure is still answered (`Apple revenue and debt-to-equity` is revenue).
- The guide's own regex list of unsupported figures (`_UNSUPPORTED_METRICS`) is gone; `_unsupported_metrics` reads the catalog's names, so there is one owner of the measures the app cannot look up. The reply is unchanged: "I can't look up {name} yet. I answer from reported 10-Q figures such as …".
- The rules planner's `_metric_from_query` and the shared metric guard in `request_wording.bind_metrics_from_message` name the measure from the catalog's reading, so a planner that sees one refuses by its name rather than `costs`, `ratio` or the model's slug.
- Phrase coverage gains the group "Unknown measures" (`UNKNOWN_MEASURE_QUESTIONS`, 16 questions), each expecting a refusal that names the measure. Nothing was on `KNOWN_GAPS`; none of the questions is sent to the LLM planner, since the guide answers first.
- ADR 0004's phrase table records the rule.

compare_answers: 2 of 244 conversations differ, both intended: `case:h2_cac_unknown` now names customer acquisition cost (was `costs`), and `case:h2_current_ratio_unknown` names current ratio (was `ratio`).
