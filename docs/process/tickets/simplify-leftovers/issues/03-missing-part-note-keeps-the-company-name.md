# The missing-part note keeps a company name that ends in a parenthesis

**This ticket changes one note, on purpose.** Decided 8 October 2026 (`docs/process/rules-to-review.md`, entry of 2026-10-07 for simplify-pass-2 02, revisited).

**Files (this ticket only):** `src/financial_analyst_agent/answer_notes.py`, `docs/process/rules-to-review.md`, and the test file that covers `missing_component_notes` (find it; add one if none exists)

**What to build:** `answer_notes.missing_component_notes` says which part of a formula the filings lack ("Apple's EBITDA is missing for the quarter ended …: no standalone quarterly depreciation and amortization was found …"). It formats each company as `"Name (date and date)"` and then, when one company is missing the part, parses that string back with `endswith(")")` and `partition(" (")` to get the name and the dates. Eleven snapshot short names end in ")": "Jerash Holdings (US)", "ZTO Express (Cayman)", "Telefonaktiebolaget LM Ericsson (publ)", "Banco Santander (Brasil) S.A." among them. For any of them alone, with the part missing in every quarter, the note reads the parenthesis as dates:

> Jerash Holdings' EBITDA is missing for US: no standalone quarterly depreciation and amortization was found for that quarter, which EBITDA needs.

Keep the companies as `(short name, dates)` pairs instead of formatting and parsing back, as simplify-pass-2 ticket 02 step 8 described: the dates are present only where today's `(company, metric) in shown and dates` holds; the parentheses are added only for the several-company sentence; for one company, `when` is built from the joined, formatted dates, with "that quarter" or "those quarters" from the number of dates. For every name not ending in ")" the output must be the same, character for character. For Jerash Holdings alone, the note then reads as for any company with no dates:

> Jerash Holdings (US)' EBITDA is missing: no standalone quarterly depreciation and amortization was found in its filings, which EBITDA needs.

(whatever `possessive` makes of a name ending in ")", unchanged.)

Add a test with one of the eleven names that pins the corrected note, and one that pins today's note for an ordinary name with dates, so both branches are covered. Below the 2026-10-07 entry's "Decided" line in `rules-to-review.md`, add: "**Revisited (2026-10-08):** take the fix; the parse-back misreads eleven names, and a wrong note is a bug. Ticket simplify-leftovers 03."

**Acceptance:** `uv run python -m pytest` passes; ruff and mypy are clean; `uv run python scripts/compare_answers.py --against master` reports `0 of N conversations differ`, or, if any conversation differs, every difference is this note for a name ending in ")" and the Answer lists them; the parse-back (`endswith(")")`, `partition(" (")`) no longer exists in `answer_notes.py`.

**Blocked by:** 02 (both edit `answer_notes.py`)

**Status:** resolved

## Answer

Shipped 8 October 2026.

- `missing_component_notes` keeps each company as a `(short name, quarters)` pair: the quarters are
  the formatted dates where today's `(company, metric) in shown` held, else empty. The one-company
  sentence builds `when` from `joined(quarters)` and picks "that quarter" or "those quarters" by
  `len(quarters)`; the several-company sentence adds the parentheses itself. The parse-back
  (`endswith(")")`, `partition(" (")`) is gone from `answer_notes.py`.
- For a name not ending in ")" the output is the same character for character: `joined` of
  formatted dates contains " and " exactly when there are two or more, which is what the old
  `" and " not in dates_shown` test read.
- New test `test_a_name_ending_in_a_parenthesis_is_not_read_as_dates` pins Jerash Holdings (US)
  alone with the part missing in every quarter: "Jerash Holdings (US)'s EBITDA is missing: no
  standalone quarterly depreciation and amortization was found in its filings, which EBITDA needs."
  (`possessive` adds "'s" to a name ending in ")", unchanged.) Today's note for an ordinary name
  with dates was already pinned by `test_a_formula_missing_in_some_quarters_names_them`, so no
  second test was added.
- `rules-to-review.md` carries the Revisited line under the 2026-10-07 simplify-pass-2 02 entry.
- 2,537 tests pass (1 new); ruff and mypy clean; `compare_answers.py --against master` reports
  `0 of 893 conversations differ`: no recorded demo conversation asks about one of the eleven
  names with a formula's part missing.
