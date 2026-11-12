# Choose the MD&A paragraphs that explain a figure's move

Spec: `docs/process/tickets/why-from-the-filing/design.md` (phase A) and `docs/adr/0017-management-explanation-is-quoted-from-the-filing.md`. Glossary term to add to `CONTEXT.md`: **Management's explanation**.

**Files (this ticket only):** `src/financial_analyst_agent/explanation.py` (new), `src/financial_analyst_agent/filing_change.py` (only to make `extract_section` / `_paragraphs` public under clear names if needed, with no change to their behaviour), `tests/unit/test_explanation.py` (new), `CONTEXT.md`.

**What to build:** a module with no model and no network that, given a filing's HTML, a catalog metric and the comparison basis asked for (`year_over_year`, `sequential` or none), returns Management's explanation:

- **Paragraphs:** up to three paragraphs of the filing's MD&A, in score order. Each carries:
  - its text, verbatim as `_paragraphs` yields it;
  - its score;
  - the span of its first causal clause;
  - a link built with `filing_anchor_url(source_url, paragraph)`.
- **Scoring**, by code only (the scratchpad prototype in the design is a starting point):
  - The metric's own words. Add an `mda_words` (or similar) field to the catalog entry or a table in this module for at least revenue, gross margin and gross profit, operating income and margin, net income, R&D, SG&A, operating cash flow, capex and free cash flow. A metric without words gets no explanation.
  - Causal wording: "primarily due to", "driven by", "as a result of", "attributable to", "offset by", "reflecting".
  - Change wording.
  - The basis: year over year favours "compared to the same period", "from a year ago" and "prior year period"; sequential favours "sequentially" and "from the [ordinal] quarter".
  - A paragraph must name the metric to be chosen. A paragraph naming a different metric's words more than this one's ranks below one that names this metric.
- **Nothing found:** an empty result with a reason ("not discussed", or "MD&A not found" when `extract_section` returns nothing). It never falls back to an arbitrary paragraph.

**Acceptance (tests on the recorded documents in `sec_fixture_recordings.json`, offline):**
- **First-paragraph cases:**
  - Apple's latest 10-Q, gross margin: the first paragraph contains "different mix of products".
  - Micron's latest 10-Q, gross margin: the first paragraph contains "improvements in margins for both DRAM and NAND".
  - Pfizer's latest 10-Q, revenue: the first paragraph contains "Total revenues increased".
- **AMD gross margin:** no paragraph about operating income is first unless it also names gross margin. Pin whatever the scoring returns, and say in the Answer whether it found the cause.
- **No MD&A text:** a document with no MD&A text returns the "MD&A not found" reason.
- **Determinism:** the result does not depend on dict or set ordering.
- **No regressions:** `compare_answers.py` reports 0 differences (nothing is wired into a turn yet). pytest, ruff and mypy are clean.

**Blocked by:** None — can start immediately

**Status:** resolved

## Answer

Shipped `explanation.management_explanation(html, metric, basis, source_url)`, which returns a
`ManagementExplanation`: up to three `ExplainingParagraph`s (verbatim text from
`filing_change.section_paragraphs`, integer score, the span of the first causal clause, and
`filing_anchor_url(source_url, text)`), or none and a reason: `mda_not_found`, `not_discussed`,
or `metric_not_covered` for a metric with no words. No model, no network.

- **Words** live in a table in `explanation.py`, by family, so related catalog metrics share them:
  revenue; gross margin / gross profit / cost of revenue; operating income / operating margin;
  net income / net margin; R&D / R&D to sales; SG&A / SG&A ratio; operating cash flow; capex;
  free cash flow. Overlaps go to the longer phrase ("cost of sales" is gross margin, "sales,
  general and administrative" is SG&A), and "non-operating income" is not operating income.
- **Eligible** only when a sentence naming the metric, or the one after it, has change or causal
  wording. A definition, or a paragraph that names the metric and talks about something else,
  is not chosen (Tesla's operating income is now `not_discussed`, where the prototype showed a
  paragraph about the auto cycle).
- **Subject**: `is_about_another_metric` is true when another metric's words outnumber this
  one's, tie and come first, or the opening sentence names another metric and not this one.
  Those paragraphs rank below every paragraph about this metric.
- **Score**: mentions, causal and change wording (each capped), a bonus when a causal clause sits
  in a sentence naming the metric (more when that sentence is about the quarter, not only the
  year to date), the basis asked (wording, plus the quarters named: "third quarter of 2026 …
  third quarter of 2025" is year over year, "… second quarter of 2026" sequential), a quarter
  mention, opening on the company-wide figure, and penalties for outlook and definitions. Ties
  keep filing order; the result does not depend on hash order (a test runs it under two
  `PYTHONHASHSEED`s).
- `filing_change._paragraphs` is renamed `section_paragraphs`, with no change in behaviour.

First paragraphs on the recorded 10-Qs:
- Apple gross margin: "Products gross margin and gross margin percentage increased … primarily
  due to a different mix of products and tariff refunds". States the cause.
- Micron gross margin: "Consolidated Gross Margin: … increased to 85% … from 74% for the second
  quarter of 2026 as a result of improvements in margins for both DRAM and NAND products".
  States the cause (sequential; asking year over year puts the 38% → 85% paragraph first).
- Pfizer revenue: "Total revenues increased $381 million, or 3%, in the second quarter … reflecting
  an operational increase … and a favorable impact of foreign exchange". States the cause.
- **AMD gross margin** (pinned): "Gross margin for the three months ended June 27, 2026 was 54%
  compared to … 40% … primarily driven by the absence of inventory and related charges associated
  with the U.S. government export control on AMD Instinct MI308 … and a favorable product mix".
  It found the cause; the operating-income paragraph the prototype put first is now third.
- Nvidia revenue: Data Center revenue ("driven by the ramp of our Blackwell Ultra
  infrastructure"), then "Revenue growth … was driven by data center products". The first states a
  cause of the largest segment's move, not total revenue's; the second states total revenue's.

Known weaknesses for the evaluation (ticket 02/03) to measure: a segment's paragraph often
outranks the total's where the total paragraph has no causal wording (Apple iPad, AMD Client,
Cisco Services revenue); cash-flow and capex questions often land on liquidity boilerplate.

compare_answers reports 0 of 893 conversations differ (nothing is wired into a turn yet).
