# 03 — One company left on screen is a lookup

**What to build:** Found reviewing probe round 3's doubts (7 October 2026): a question a doubt raised, asked on the recorded runtime, does not do what the README's "How a question is read" now says. The fix belongs in the shared reading of words both planners pass through (ADR 0010, 0011), except where the ticket says otherwise. `SPY and Apple revenue` drops SPY (a fund) and answers Apple's revenue, but its intent is `compare`. The README (and the brief's labelling rule) say the intent follows the companies on screen: one is a lookup, several a comparison. `compare Google and Alphabet revenue` already collapses to one company and is a lookup. Make a comparison that ends with one company on screen, after unresolved or dropped names, a lookup.

**Acceptance:** `SPY and Apple revenue` is intent `lookup` with AAPL; `Apple and Microsoft revenue` is still `compare`. `uv run python -m pytest` passes; `uv run python scripts/compare_answers.py` names every conversation whose answer changes, and each change is intended.

**Blocked by:** None — can start immediately

**Status:** resolved

## Answer

Shipped 7 October 2026. The intent follows the companies on screen once names are resolved and
the cells are in: a comparison that ends with one company on screen is a lookup.

- `_one_company_left` in `graph/spec_turn.py`, applied in `merge_analysis` right after the task
  results are merged, so both planners pass through it (ADR 0010, 0011). A row whose reason is
  `company_not_found` or `not_operating_company` is a name the answer says it left out, so it is
  not on screen; a merely missing fact, or an unavailable source, keeps the company on screen.
  Exactly one company left makes a lookup; none left keeps the comparison asked for.
- `SPY and Apple revenue` is intent `lookup` with AAPL's figure; `Apple and Microsoft revenue` is
  still `compare`. `compare GOOG and GOOGL operating margins` with no index, where the two share
  classes collapse to one Alphabet row only in the facts lookup, is now a lookup too: its test
  expected `compare` from before the README's rule and was updated.
- The follow-up wording tests' fake facts gave every company but Google Microsoft's CIK, so Google
  and Apple were one company on screen; the fake now keeps the CIK it is asked by.
- ADR 0010's "One resolver" paragraph states the rule. `README.md` already did.
- compare_answers: `1 of 252 conversations differ from HEAD`, the new `SPY and Apple revenue`
  conversation: intent `compare` → `lookup`, label "Comparison" → "Quarterly lookup".
- Recorded for review in `docs/process/rules-to-review.md`: the README says a fund beside a
  company is "left out with a note", but the SPY row stays in the table reading "Company not
  found", with a note that names the fund without saying it is one.
