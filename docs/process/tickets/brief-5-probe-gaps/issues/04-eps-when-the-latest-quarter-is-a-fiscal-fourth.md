# 04 — EPS when the latest quarter is a fiscal fourth quarter

**What to build:** `What are Cisco's earnings per share?` is refused: "Per-share figures for this quarter are reported only for a longer period". Cisco's latest report is its 10-K, whose fourth quarter has no standalone per-share figure, and ADR 0007 does not derive one (annual EPS less nine months' is not the quarter's EPS when the share count moves). The plan was right, and the evaluation now scores this as no data, not a planning failure. But a refusal answers the most ordinary question an analyst asks about a company with nothing, for about a quarter of each year for every company whose fiscal year ended last.

Options:

1. **Show the latest quarter that has a quarterly per-share figure** (recommended), with a note: "Cisco's fiscal fourth quarter (ended 25 July 2026) reports EPS only for the year; this is the third quarter, the latest with its own." The analyst gets the most recent quarterly EPS the filings hold, and the note says why it is not the latest quarter.
2. **Show the fiscal year's EPS** from the 10-K, labelled as the year. It is the latest per-share figure filed, but a year beside other companies' quarters does not compare.
3. **Keep the refusal.**

Applies to a question with no period. A named fiscal fourth quarter (`Cisco EPS in Q4 FY2026`) still says it is reported only for the year. A window shows the fourth quarter as a blank row with its reason, as now.

**Acceptance (option 1):** `What are Cisco's earnings per share?` on the recorded runtime answers Q3 FY2026 with the note; a company whose latest quarter has its own EPS is unchanged.

Found by the set-5 brief's probe dry-run (6 October 2026): a blind session labelled 30 throwaway probes from the draft brief and the README, and the app disagreed. Judged by the README's [How a question is read](../../../../../README.md#how-a-question-is-read). The fix belongs in the shared reading of words both planners pass through (ADR 0010, 0011), not in the rules planner alone, except where the ticket says the rules planner.

**Acceptance:** the cases below are read right; any phrase-coverage case named is taken off `KNOWN_GAPS`; `uv run python -m pytest` passes; `uv run python scripts/compare_answers.py` names every conversation whose answer changes, and each change is intended.

**Blocked by:** None — can start immediately

**Decided (2026-10-06):** option 1, the latest quarter that has its own per-share figure, with the note.

**Status:** resolved

## Answer

Shipped option 1 (2026-10-06). `What are Cisco's earnings per share?` on the recorded runtime answers $0.85 for the quarter ended Apr 25, 2026 (Q3 FY2026), with the note "Cisco Systems' quarter ended Jul 25, 2026 reports diluted EPS only for the year, so Cisco Systems is shown for the quarter ended Apr 25, 2026, the latest with its own." `Apple EPS` is unchanged, with no note.

- `SecFactLookup.get_financials` (`sec_facts.py`): with no report date, a `PerShareNotDerivableError` on a quarter steps on to the next of the four latest report dates, as the lookup already did for a filing SEC's structured data lacks. The fact found carries the stepped-past quarter's end as `year_only_quarter_end` (new on `FinancialFact` and `TableRow`), beside the existing `newer_filing_end`; both can be set. `NoDividendThisQuarterError` does not step back: a quarter with no dividend declared says so, as before.
- A named period still raises (`Cisco EPS in Q4 FY2026` is refused with the same message), and a window still shows the fourth quarter as a blank row with "Reported for the year only".
- `year_only_quarter_banners` (`presentation.py`) writes the note, one per company and metric, after the newer-filing banner. The lookup row and the compare row carry the field, so a compare or a ranking by EPS shows a 10-K filer's latest quarter with its own and the note (Microsoft in `top 3 tech companies by EPS`).
- Dividends per share and basic EPS step back the same way, each with its own wording in the note.
- README "How a question is read" gains the row. `tests/unit/test_planner_evaluation.py` now scores the no-period question as an answer and the named fourth quarter as no data.

`uv run python scripts/compare_answers.py`: 0 of 244 conversations differ. Nothing was on `KNOWN_GAPS` for this ticket.

