# 14 — Read a filing change's submissions table once

**What to build:** `filing_change._primary_document`, `_year_apart_quarterlies`, `_filing_date` and `_form_of` each walk the raw `recent` submissions dict, each checking its lists differently (raising, returning `None`, `""` or falling back to `[]`); `_order_accessions` runs twice on the explicit-pair path. Read `recent` into rows once (accession, form, report date, filing date, primary document) and look rows up by accession.

A malformed payload then fails when the rows are read rather than at `_primary_document`: keep its error a `ProviderRefusal` with the same message.

**Acceptance:** `uv run python scripts/compare_answers.py` reports `0 of N conversations differ`: what the recorded demo answers does not change.

Found by the 2026-10-04 simplify review of master (#67), which left it out as larger than a cleanup.

**Blocked by:** None — can start immediately

**Status:** ready-for-agent
