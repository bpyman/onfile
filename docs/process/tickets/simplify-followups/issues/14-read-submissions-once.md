# 14 — Read a filing change's submissions table once

**What to build:** `filing_change._primary_document`, `_year_apart_quarterlies`, `_filing_date` and `_form_of` each walk the raw `recent` submissions dict, each checking its lists differently (raising, returning `None`, `""` or falling back to `[]`); `_order_accessions` runs twice on the explicit-pair path. Read `recent` into rows once (accession, form, report date, filing date, primary document) and look rows up by accession.

A malformed payload then fails when the rows are read rather than at `_primary_document`: keep its error a `ProviderRefusal` with the same message.

**Acceptance:** `uv run python scripts/compare_answers.py` reports `0 of N conversations differ`: what the recorded demo answers does not change.

Found by the 2026-10-04 simplify review of master (#67), which left it out as larger than a cleanup.

**Blocked by:** None — can start immediately

**Status:** resolved

## Answer

Shipped 2026-10-04. `filing_change._read_filings` reads `filings.recent` once
into `_Filing` rows (accession, form, report date, primary document), keyed by
accession. `_primary_document`, `_year_apart_quarterlies`, `_report_date` (was
`_filing_date`), `_form_of`, `_check_reviewable`, `_chosen_pair_banner` and
`_too_few_message` look rows up instead of walking the columns.

- A malformed table (columns missing or of different lengths) now fails when
  the rows are read, on both paths, with the same error and message as before.
  That error was a `ProviderError`, not the `ProviderRefusal` the ticket names;
  it stays a `ProviderError`. The latest-10-Q path used to answer "fewer than
  two 10-Q filings" for a table without the columns; it now gives the same
  malformed-table refusal as the given-accessions path.
- The report date falls back to the filing date only when the payload has no
  `reportDate` column, as `_filing_date` did. Rows carry no separate filing
  date: nothing reads one.
- `_order_accessions` runs once, on the given-accessions path only. The
  year-apart pair already comes back older first.
- `scripts/record_sec_fixtures.py` looks the primary document up from the rows.

`uv run python scripts/compare_answers.py`: 0 of 244 conversations differ.
