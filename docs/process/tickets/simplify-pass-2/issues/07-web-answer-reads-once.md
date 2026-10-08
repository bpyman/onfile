# Compute the web answer's filings, rows and order once

From a parallel `/simplify` review of the whole codebase (7 October 2026): seven read-only reviewers, one per area plus one across areas; 84 findings, consolidated into 12 tickets that never share a file. Cleanup only: **no behaviour may change**.

**Files (this ticket only):** `web/lib/notes.ts`, `web/lib/answer-text.ts`, `web/components/answer-chart.tsx`, `web/lib/chart-data.ts`, `web/components/answer.tsx`, `web/components/data-table.tsx`, `web/lib/table-sort.ts`, `web/components/filing-changes.tsx`, `web/lib/diff-view.ts`

**What to build:** The answer view computes the same things several times and keeps two copies of a few rules: which filings an answer read, a chart's rows, the table's sort order, the diff ranking, the snapshot help text and the external filing link. Compute each once and keep one copy. Nothing may render, copy or save differently.

1. **Which filings an answer read, two walks.** `filingLinks` (answer-text.ts:168-187) re-implements `answerFilings` (notes.ts:34-49). Have notes.ts own the walk: export `eachFiling(presentation, label: (source) => string): {url, label}[]`, where `source` is `{url, company, form, accession, fallback, side?: "older" | "newer"}`. `answerFilings` passes `filingLabel(...) || hostname` with its Previous/Current wording. answer-text passes `plain(filingLabel(...) || fallback)` with `Older/Newer filing <acc>`, and maps the result to `- [label](destination(url))`. Both outputs must stay byte for byte the same.
2. **Chart rows built three or four times** (answer-chart.tsx:71-75, 140-160, 245-247). Build `lineRows`/`lineSeries` once in AnswerChart with `useMemo(..., [chart])`, derive `derived` from them, and pass rows and series to TrendChart and ChartSummary as props. Do the same for `barRows`, which ChartSummary and ComparisonChart each build.
3. **The table sorted three times** (answer.tsx:95-96, data-table.tsx:46, table-sort.ts:69-72). Pass `rowOrder` from Answer to DataTable, which uses `rowOrder ?? identity` instead of calling `sortedRowIndices`. Derive the chart's keys as `!pivoted && rowOrder && shown.row_keys?.length ? rowOrder.map(r => shown.row_keys[r] ?? "") : null`. Keep the `!pivoted` condition: it matches today's `sortedRowKeys`, which returns null when unsorted. Delete `sortedRowKeys` if nothing else uses it.
4. **Diff figures scanned up to four times.** In `orderChanges` (diff-view.ts:57-59), rank with one figures check: `item.change_kind !== "changed" ? 1 : changesFigures(item) ? 0 : 2`. Split substantive from wording inside FilingChanges' existing `useMemo` (filing-changes.tsx:26-28), for example by having a sibling helper return `{substantive, wording}`. Rank-2 items are already the sorted tail.
5. **`Marked` copies `Runs`** (filing-changes.tsx:318-336 and 227-251). Delete `Marked`. FilingSide renders `<Runs pieces={pieces.map(p => ({text: p.text, kind: !p.changed ? "same" : current ? "added" : "removed"}))} />` with `strike` left false, which produces the same ins and del classes.
6. **The external filing link written twice.** `FilingLink` (filing-changes.tsx:211-224) and the table's "Filing" cell (data-table.tsx:363-374) re-implement ui.tsx's `ExternalLink`. Replace both with `safeHref(href) && <ExternalLink href={href} className="gap-0.5 font-medium">…</ExternalLink>`, adding `rounded text-xs` for the cell. The `safeHref` guard keeps today's "render nothing when unsafe"; ExternalLink alone would render a span. ExternalLink's icon also carries `shrink-0`; confirm in the browser that the links look the same.
7. **Two pasted copies** (answer-chart.tsx:125, 552-555; answer.tsx:295-296; chart-data.ts:208-211). Move `SNAPSHOT_HELP` into lib/notes.ts next to its SNAPSHOT prefix and import it in both components; answer-chart cannot import answer.tsx. In chart-data, export `splitPeriod(period): [day, year]`, define `tickLine` as `splitPeriod(p)[0]`, and have PeriodTick use `splitPeriod`.

**Acceptance:** `npm test`, `npm run lint` and `npx tsc --noEmit` pass in web/; the copied Markdown and CSV for a recorded ranking, a trend and a filing change are byte for byte the same as before; a sorted ranking's table, chart bars, inspector and copied text agree on row order.

**Findings covered:**
- web/reuse: answer-text filingLinks re-implements notes answerFilings
- web/efficiency: lineRows/lineSeries/barRows rebuilt three to four times per chart
- web/efficiency: a sorted table is sorted three times (answer, data-table, table-sort)
- web/efficiency: orderChanges and FilingChanges scan figures up to four times
- web/simplification: Marked is a copy of Runs
- web/reuse: FilingLink and the table's Filing cell re-implement ExternalLink
- web/reuse: SNAPSHOT_HELP pasted into answer-chart; PeriodTick re-splits the period like tickLine

**Acceptance:** `npx --prefix web vitest run`, `npm --prefix web run lint` and `npm --prefix web run build` pass, and the Playwright browser check is unchanged. If a step would change behaviour, or needs a file outside this ticket's list, leave it and say so in the Answer.

**Blocked by:** None — can start immediately

**Status:** resolved

## Answer

Shipped 7 October 2026, on `simplify-pass-2`. All seven steps; nothing renders, copies or saves differently.

1. **One filing walk.** `lib/notes.ts` exports `eachFiling(presentation, label)` and the `FilingSource` it hands the label function (`url`, `company`, `form`, `accession`, `fallback`, `side?`). `answerFilings` labels a source `filingLabel(side ? "Previous filing" / "Current filing" : company, form, accession) || hostname`; `answer-text.ts`'s `filingLinks` labels it `plain(side ? fallback : filingLabel(...) || fallback)` with the fallbacks `Older filing <acc>` / `Newer filing <acc>`, the card's metric header and the evidence item's label, and maps to `- [label](destination(url))`. Both outputs are byte for byte as before (tested).
2. **Chart rows once.** `AnswerChart` builds `series`, `rows` (line) and `bars` (bar) with `useMemo(..., [chart])`, reads `derived` from `rows`, and passes them to `TrendChart` (`rows`, `series`), `ComparisonChart` (`bars`) and `ChartSummary` (`bars`, `rows`, `series`; one `<ul>` listing whichever is non-empty, the same markup as the two branches it replaces).
3. **The table sorted once.** `Answer` passes `rowOrder` to `DataTable`, which uses `rowOrder ?? identity`; the chart's `order` is `!pivoted && rowOrder && shown.row_keys?.length ? rowOrder.map(...) : null`, memoised on `[shown, pivoted, rowOrder]`. `sortedRowKeys` and its test are deleted (nothing else used it).
4. **One figures check.** `diff-view.ts`: a private `rank(item)` (`change_kind !== "changed" ? 1 : changesFigures(item) ? 0 : 2`) is the one rule; `isWordingOnly` is `rank(item) === 2`; `ranked(items)` sorts once and serves `orderChanges` and the new `splitChanges(items): {substantive, wording}`, which cuts at the first rank-2 entry (the sorted tail). `FilingChanges` calls `splitChanges` inside its existing `useMemo`.
5. **`Marked` deleted.** `FilingSide` renders `<Runs pieces={pieces.map((piece) => sided(piece, current))} />` with `strike` left false; `sided` maps an unchanged piece to `same`, a changed one to `added` on the current side and `removed` on the previous. Same `ins` and `del` classes; only the class order on the wide side's `del` changes.
6. **One external link.** The phone's Previous / Current filing links and the table's Filing cell are `safeHref(href) && <ExternalLink href className="gap-0.5 font-medium">` (the cell adds `rounded text-xs`); `twMerge` drops the base `gap-1`. Confirmed in the browser (Playwright, computed styles and screenshots): both links keep the 2px gap, 12px / 500 text, primary colour, no underline until hover and a 14px icon; the icon now also carries `shrink-0`, which changes nothing at these widths.
7. **Pasted copies.** `SNAPSHOT_HELP` lives in `lib/notes.ts` beside the SNAPSHOT prefix and is imported by `answer.tsx` and `answer-chart.tsx` (status-line.tsx keeps its own copy: not in this ticket's files). `chart-data.ts` exports `splitPeriod(period): [day, year]`; `tickLine` is `splitPeriod(period)[0]` and `PeriodTick` uses `splitPeriod`.

**Checks.** `npx vitest run` 213 passed (+3: `eachFiling` ×2, `splitChanges`, `splitPeriod`; −1 `sortedRowKeys`), `npm run lint`, `npx tsc --noEmit`, `npm run build` and `npm run test:e2e` (46 passed) all pass. A throwaway harness rendered every recorded demo answer (`lib/demo-answers.json`) with `renderToStaticMarkup`, with each column's sort both ways, plus the sorted chart, the filing changes and a synthetic two-series trend, and its Markdown and CSV: 142 outputs, of which the 36 Markdown and 34 CSV outputs are byte-identical, and the 26 HTML outputs that differ do so only in the class order of the two links and the wide-side `del`, and the icon's `shrink-0` (0 differ once class tokens are sorted). Python: 2,359 tests, ruff, mypy, and `compare_answers` 0 of 375 differ.
