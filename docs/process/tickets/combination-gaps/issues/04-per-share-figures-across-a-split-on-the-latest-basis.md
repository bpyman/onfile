# 04 — Per-share figures across a stock split are shown on the latest basis

**What to build:** Found live (6 October 2026). `NVIDIA diluted EPS over the last 10 quarters` shows the quarter ended 28 April 2024 at $5.98, its diluted EPS as first filed, before the ten-for-one split of June 2024, and the next quarter at $0.67. A note says the quarter is shown before the split (`presentation.restated_banners`), but the chart still falls 90%, and a sort by EPS ranks that quarter first. Decided: show every per-share level on the basis after the latest split, as the company itself and ASC 260 do. ADR 0009's revision note records it.

- **Which figures:** the per-share metrics, `PER_SHARE_METRICS` (`eps_diluted`, `eps_basic`, `dividends_per_share`). Amounts, ratios, margins and market figures are unchanged. A restatement that is not a split keeps ADR 0009's rule: shown as first filed, with its note.
- **The ratio is reported, not inferred:** `us-gaap:StockholdersEquityNoteStockSplitConversionRatio1` (a pure number: 10 for NVIDIA's 2024 split, 4 for its 2021 one; below 1 for a reverse split). `READ_CONCEPTS` reads it, and the SEC recording and `tests/fixtures/sec/nvda.json` hold NVIDIA's facts for it (prep commit).
- **When the split took effect:** the facts' periods are untidy (NVIDIA tags its 2024 split with periods ending 31 May and 30 June 2024, in filings of August 2024 to May 2025). A per-share fact needs adjusting when its filing was filed before the split took effect; the filings after a split already restate every period they present. Use the earliest end date reported for that ratio as the effective date, and treat two reports of the same ratio within about 90 days of each other as one split.
- **Cross-check with the reported restated figure:** where a later filing reports the same quarter as a comparative (NVIDIA's $0.60 for the quarter ended 28 April 2024, in the 10-Q of May 2025), the adjusted value must agree with it within rounding (half a cent). If it does not, do not adjust that company's series; keep today's first-filed value and its note. This is the guard against a misread date or ratio.
- **Several splits compound:** a quarter before both of NVIDIA's splits is divided by 40.
- **Provenance:** an adjusted cell's evidence keeps the filing that first reported the figure, and says how it was adjusted: "$5.98 as first filed, ÷ 10 for the ten-for-one split of June 2024". The inspector shows both, as a derived quarter shows its subtraction (ADR 0007). The table and chart show the adjusted value; the CSV and Markdown copy carry the same value and the same source line.
- **What changes downstream:** the per-share split note in `restated_banners` no longer fires for a split that was adjusted (the levels now compare), and a quarter-over-quarter change may cross an adjusted split. A year-over-year change still reads the comparative (ADR 0009); on adjusted levels the two agree.

**Acceptance:**

- On `tests/fixtures/sec/nvda.json` (fake facts in a unit test are fine too), diluted EPS for the quarter ended 28 April 2024 is $0.60 (5.98 ÷ 10, rounded as the window rounds), its evidence names the May 2024 10-Q and the ratio, and no split note is shown for it.
- A quarter before both splits is divided by 40.
- A reverse split (ratio below 1) multiplies.
- A disagreement with the reported comparative leaves the series as first filed, with today's note.
- A company with no split, and every amount metric, is unchanged: `uv run python scripts/compare_answers.py` names every conversation whose answer changes, and each change is a per-share level across a split.
- `uv run python -m pytest` passes.

**Blocked by:** None — can start immediately (after the prep commit)

**Status:** ready-for-agent
