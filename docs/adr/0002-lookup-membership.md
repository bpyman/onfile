# Lookup and compare use membership rules, not freeze presence

Ranking membership is the common share of an operating company, as defined in ADR 0001. Lookup and compare apply that same rule to each named company. Freeze presence is not required: an operating company listed after this freeze can still be looked up. A named company that fails the rule is a typed miss when asked on its own; named beside an operating company (`SPY and Apple revenue`), it is left out of the table with a note saying it is a fund, and the companies left decide the intent. News does not apply the gate.

Ares Capital is excluded because it is a BDC, not an operating company. It is on the ineligible CIK list because Asset Management also contains operators (Ares Management). Absence from the freeze is not the reason.

## Considered Options

- **Gate lookup on freeze presence** — rejected: an operating company the freeze has not yet captured would be unlookable for a non-membership reason.
- **Any SEC filer** — rejected: would look up funds, BDCs, preferreds, and other non-operating listings.
- **Whole-turn refuse when one compare name fails** — rejected: keep the row that passed.
- **Gate news the same way** — rejected: news may name companies that are not operating companies.

## Consequences

Lookup identity is SEC, not the FMP vendor row ADR 0001’s `isEtf`/`isFund` and industry filters run on. A name already in the freeze has been judged. A name not in the freeze is judged with what SEC identity can see — listing-title tokens and the ineligible CIK list. Ticker suffixes are not used for lookup: an operating utility or insurer whose only listed shares are preferreds (Southern California Edison, Consumers Energy) files 10-Qs and is looked up like any other operating company. A snapshot member whose CIK is added to the ineligible list is refused at once, before the snapshot is rebuilt. The rules planner finds a company outside the freeze by its full SEC name from `data/sec_filer_names.json` (listed operating filers the freeze leaves out, such as Southern California Edison); `scripts/build_sec_filer_names.py` rebuilds it with the snapshot. A residual BDC not yet on that list can leak into lookup until its CIK is appended; that does not change the rules.

Snapshot metrics (`market_cap`) are an exception: the number lives on the freeze, so lookup requires freeze presence. XBRL reported facts and formulas still do not.
