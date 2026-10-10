# Essay evaluation: brief for question writers

You are writing questions to test the written answers of Onfile, a research assistant for analysts that answers questions about US public companies from their SEC filings. Read the README, `CONTEXT.md` and `docs/evaluation/essay-rubric.md` for context. Do not read the application's code or its prompts.

Write questions only. Do not write answers, and do not try to predict what the app will say.

## What to write

Thirty cases: ten of each kind below. Return one JSON file in the format at the end.

### Explain (10)

A conceptual question an analyst might ask: accounting, valuation, how a metric behaves, how an industry works, how a macro factor reaches a company's results. One turn. It names no company figure, though it may name a company as an example.

Examples of the kind: "How does a share buyback affect EPS?", "Why do banks care about net interest margin?"

### Analysis (10)

Two turns. The first asks for figures the app answers with a table; the second asks for interpretation of that table. The first turn must use only these companies, whose filings the test runtime holds: Abbott, AbbVie, Alphabet, AMD, Amgen, Apple, Applied Materials, Broadcom, Cisco, Danaher, Eli Lilly, General Motors, Gilead, Goldman Sachs, Intel, Johnson & Johnson, JPMorgan, Merck, Micron, Microsoft, Nvidia, Oracle, Palantir, Pfizer, Tesla, Thermo Fisher, UnitedHealth, Wells Fargo. Metrics include revenue, net income, gross, operating and net margin, EPS, R&D, cash flow, cash and equity; a window of quarters or a comparison of two to four companies works well.

Example of the kind: "Compare Eli Lilly and Pfizer revenue over the last eight quarters" → "What explains the divergence?"

### News (10)

A current-events question about a named company, an industry or a theme, answerable from news published in the past week. One turn. The app searches the news once, and the essay may use only what the results say.

Example of the kind: "What is driving the latest news about Intel's foundry business?"

## Spread

Across each kind, vary:

- **Difficulty.** Some questions with a clear answer; some that need caveats; at least two whose grounding can only partly answer them.
- **Phrasing.** Terse and conversational as well as formal, as real analysts write.
- **Edges.** In each kind, one question that invites something the app should not do: a price prediction, a buy or sell recommendation, or a claim the grounding cannot support.

## Format

```json
{
  "writer": "<model name>",
  "cases": [
    {"id": "<writer>_explain_01", "kind": "explain", "turns": ["..."], "note": "what this case tests"},
    {"id": "<writer>_analysis_01", "kind": "analysis", "turns": ["...", "..."], "note": "..."},
    {"id": "<writer>_news_01", "kind": "news", "turns": ["..."], "note": "..."}
  ]
}
```
