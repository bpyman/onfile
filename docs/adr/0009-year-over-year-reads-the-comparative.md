# Year-over-year change reads the newer filing's comparative

> **Extends [ADR 0007](0007-derived-quarters-and-per-share.md).** Levels are still shown as first filed; only the base of a change moves.

A year-over-year change subtracted the year-earlier quarter as first filed from this quarter. After a share split or a restatement the two are on different bases: NVIDIA's diluted EPS for the quarter after its ten-for-one split read -87.3% against the $5.98 first filed, where the same 10-Q reports the year-earlier quarter as $0.60 (+26.7%); Chipotle's read -97.8% for +7.7%; Bank of America's revenue +19.3% for +15.0% against its restated figure.

## Decision

Every 10-Q and 10-K reports the same income-statement and cash-flow line a year earlier beside the current one, on the current basis (a 10-Q's balance sheet is compared with the fiscal year-end instead). That **comparative** (same concept, same filing, ending a year earlier within a week, of the same length within a week) is the base of a year-over-year change. A derived quarter's comparative is the same subtraction over each part's own comparative; a formula's is the formula over its components' comparatives. The year-earlier row as first filed is the base only when the filing reports no comparative. A fact card's year-over-year chip follows the same order, fetching the year-earlier quarter when there is no comparative, and its title says which base it used.

When the analyst asks for year over year alone, every quarter in the window gets its change from its own comparative, so an eight-quarter window no longer leaves its older half blank. Otherwise a change is shown only where the year-earlier quarter is in the window, as before.

So year over year adds no rows to a window the analyst chose: "amgen and gilead revenue, last 6 quarters" then "show that year over year" shows the same 6 quarters, each with its change. Only a question that names no window gets a default: 8 quarters for year over year (once four quarters and the year before each) and 5 for growth (once four quarters and the newest one's year-earlier base). A sequential change still needs the quarter before the oldest one shown, so it can widen a window to 5.

The table keeps each quarter as first filed, so a note says where a level differs from the base a change used: a restatement, or a share split. A split also shows as weighted diluted shares moving by half again or more between two quarters; no quarter-over-quarter per-share change crosses it.

## Considered options

- **Show every level as most recently restated.** Rejected: a quarter's figure would change under the analyst as new filings arrive, and the filing cited would no longer be the one that first reported it.
- **Split-adjust per-share levels by a ratio.** Rejected: the ratio would be inferred, not reported; the comparative is reported.
