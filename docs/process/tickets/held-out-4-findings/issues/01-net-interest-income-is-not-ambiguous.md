# 01 — "Net interest income" names one metric

**What to build:** "Give me Bank of America's net interest income for the last couple of quarters" asks which metric was meant, as if "interest" were ambiguous. "Net interest income" is the catalog's `net_interest_income`; the whole phrase should resolve before its words are read as ambiguous (ADR 0004). Check "a couple of quarters" reads as 2 once the metric resolves.

Case: `h4_bac_nii_couple_quarters`.

Found by the fourth held-out planner set ([findings](../../../../evaluation/held-out-4-findings.md)): every planner failed it the same way, so the defect is in the code all planners share after planning.

**Acceptance:** the case below answers as expected on the recorded runtime with the rules planner, a test pins it, and `uv run python scripts/compare_answers.py` names every conversation whose answer changes. Fixing it makes the fourth held-out set development data: say so in the case file's `about`, not by editing its labels.

**Blocked by:** None — can start immediately

**Status:** resolved

## Answer

"Net interest income" was not in the phrase table, so the ambiguous word "interest" was all that matched. And `net_interest_income` was in the enum only as an input to a bank's revenue, not an askable metric. Now:

- `services/metric_catalog.py`: "net interest income" and its slug are unique phrases. The longer span wins, so neither "net", "interest" nor "income" is read on its own. "Interest" alone still clarifies.
- `contracts.py`: `net_interest_income` joins `REPORTED_METRICS`, so a spec can ask for it and the catalog legend lists it (34 names). A company that reports none (Apple) is refused as having no such fact.
- The case now answers with Bank of America's net interest income for the last 2 quarters (15,997 and 15,745 million dollars on the recorded runtime). Pinned in `tests/test_held_out_4_findings.py`, which runs a held-out-4 case the way the planner comparison does, with the rules planner. The other tickets in this feature can add their cases there.
- `uv run python scripts/compare_answers.py`: 0 of 244 conversations differ. No recorded demo conversation asks about net interest income.
- `planner-cases-held-out-4.json`'s `about` now says the set is development data. No label was changed.
