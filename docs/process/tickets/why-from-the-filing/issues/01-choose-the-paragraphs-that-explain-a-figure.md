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

**Status:** ready-for-agent
