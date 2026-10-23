# A quarter-over-quarter question gets a quarter-over-quarter headline

From the product review (Tier 1 item 3). "Microsoft revenue quarter over quarter" shows a table with QoQ and YoY change columns, but its headline is "Year over year, Microsoft's revenue grew 17.7% † in the quarter ended Jun 30, 2026." The analyst asked for the change on the quarter before.

**Files (this ticket only):** `src/financial_analyst_agent/presentation.py` (`growth_headline` and its caller), the conversation tests that pin growth headlines.

**What to build:** When the analysis asks for sequential change (`sequential` in the spec's operations, as `period_selection`/`request_wording` read it), the growth headline states each company's latest change on the quarter before, worded as today's headline is: "Quarter over quarter, Microsoft's revenue grew 8.6% † in the quarter ended Jun 30, 2026." When both bases are asked ("sequentially and year over year"), keep the year-over-year headline and add the sequential change for the same quarter in the same sentence, if that reads naturally; otherwise keep year over year alone. A question that asks for year over year or growth keeps today's headline.

Find how `present_turn` knows which change was asked. If the headline cannot learn that without a new field on the result, add the smallest one and say why in the Answer.

**Acceptance:**
- "Microsoft revenue quarter over quarter" on the recorded runtime gets a headline about the change on the quarter before, pinned by a test.
- "Microsoft revenue year over year" is unchanged.
- `compare_answers.py --against master` shows only sequential-change conversations changing, in `.headline`; list them in the Answer.

**Blocked by:** None — can start immediately

**Status:** resolved

## Answer

`present_turn` could not tell which change was asked: a sequential view's table also carries a
year-over-year change on its latest quarter, and the result had no spec. The smallest field:
`TurnResult.change_bases`, the comparison bases asked, set in `merge_analysis` from the same reading
that turns the sequential change on or off for the table (so the two cannot disagree). It is empty
when no change was asked.

`growth_headline(rows, bases)`:
- Only the sequential change asked: "Quarter over quarter, Microsoft's revenue grew 8.6% † in the
  quarter ended Jun 30, 2026." Several companies read as today ("…, each in its latest quarter").
  Where no sequential change has a percent, it keeps the year-over-year headline.
- Both asked: today's year-over-year headline, and for one company the sequential change of the
  same quarter: "Year over year, Apple's revenue grew 16.4% in the quarter ended Jun 27, 2026;
  quarter over quarter, it fell 1.6%." Several companies keep year over year alone (two sentences
  of clauses do not read naturally in one).
- Year over year or growth: unchanged.

Not as the ticket says: `sequential` is in the spec's operations only when both bases are asked; a
sequential change alone is `across_periods` without `year_over_year`. Recorded in
`docs/process/rules-to-review.md`.

Pinned in `tests/test_says_what_it_cannot_do.py` (`test_a_sequential_question_gets_a_sequential_headline`):
"Microsoft revenue quarter over quarter", "Microsoft revenue year over year" (unchanged), both bases
on Apple, and Apple and Microsoft quarter over quarter.

`compare_answers.py` (against HEAD, the previous commit): 29 of 893 conversations differ, all in a
headline, all asking for a sequential change: the `qoq:` phrase cases (QoQ, quarter over quarter,
sequentially, versus the previous quarter), the `combined:` cases ending "quarter over quarter",
the `switch:` cases whose answer is the sequential view (the first answer of "quarter over quarter |
make it year over year", the last of "year over year | sequential instead" and its phrasings), the
`both_bases:` cases (which gain the one-company sequential clause), and the extras "Apple revenue
since 2025 quarter over quarter" and "Apple revenue over the last 6 quarters | sequentially or
versus last year".
