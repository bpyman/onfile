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

**Status:** ready-for-agent
