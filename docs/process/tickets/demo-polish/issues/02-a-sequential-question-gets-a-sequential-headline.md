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

**Status:** ready-for-agent
