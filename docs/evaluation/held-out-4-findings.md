# What the fourth held-out set found

The [planner comparison](planner-comparison.md) of 5 October 2026 ran the rules
planner, the LLM planner (`gpt-5.6-terra`) and the cascade on the 66 cases of
[`planner-cases-held-out-4.json`](planner-cases-held-out-4.json). Ten cases failed
at least one planner. This is what each was, read after the run. No label was
changed.

## Only the rules planner failed: 2 cases

Both are planning errors, and the cascade's unsure signals sent both to the LLM
planner, which planned them right.

| Case | Question | What the rules planner did |
| --- | --- | --- |
| `h4_other_explain_ai_drug_discovery` | How might generative AI change drug discovery? | Read a figures lookup with no metric, not an explanation. Unsure: no catalog metric. |
| `h4_ow_apples_word_mrk_pfe` | comparing apples to apples, how do Merck and Pfizer stack up on net income? | Added Apple for "apples". Unsure: it noted the correction. |

## Every planner failed: 8 cases

Each planner failed these in the same way, so none is a planning error: the
mistake is in the code all three share after planning, or in the label.

Defects in the shared code (6):

| Case | Question | What happened | Expected |
| --- | --- | --- | --- |
| `h4_bac_nii_couple_quarters` | Give me Bank of America's net interest income for the last couple of quarters | Asked which metric was meant | Net interest income, last 2 quarters |
| `h4_growth_unh_ocf_year_on_year` | is unitedhealth's operating cash flow up year on year | Latest quarter, no year-over-year change | "Year on year" read as year over year |
| `h4_clarify_intel_change_no_base` | How much did Intel's revenue change? | Answered the latest revenue | Ask what to compare against, as "why did revenue drop?" does |
| `h4_fu_jpm_and_wfc_remove_jpm` | JPMorgan net interest income for the last 4 quarters → and Wells Fargo → remove JPMorgan | Wells Fargo's overview: the metric and window were lost | Wells Fargo net interest income, last 4 quarters |
| `h4_fu_amgn_gild_yoy` | amgen and gilead revenue, last 6 quarters → show that year over year | The window grew to 8 quarters | 6 quarters, with year-over-year change |
| `h4_fu_tmo_dhr_too_growth` | Thermo Fisher revenue last 4 quarters → Danaher too → as growth | The window grew to 5 quarters | 4 quarters, with year-over-year change |

A label that disagrees with a design decision (2):

| Case | Question | What happened | Label |
| --- | --- | --- | --- |
| `h4_growth_nvda_how_fast` | How fast is Nvidia's revenue growing? | Five quarters of year-over-year growth | The latest quarter |
| `h4_growth_three_tickers_operating_income` | $AVGO $AMD $INTC operating income growth | Five quarters of year-over-year growth | The latest quarter |

A growth question that names no period shows recent quarters' growth by design
(the README's "charts the growth rates"); the brief told the writer that a
question naming no period is the latest quarter, without that exception. Scored
as labelled, both count as failures for every planner.

`h4_growth_unh_ocf_year_on_year` is a shared defect and also has a period label
that disagrees with the design. Once "year on year" is read, it answers as
"year over year" does. A year-over-year question that names no period shows two
years of quarters, but the label says the latest quarter.

`h4_fu_jpm_and_wfc_remove_jpm` had the same cause as `h4_bac_nii_couple_quarters`.
The first turn asked which "interest" was meant. "and Wells Fargo" did not answer
that question, so it discarded the pending clarification and showed Wells Fargo's
overview. "remove JPMorgan" then had nothing to remove. Once "net interest income"
was read as one metric, the removal kept the metric and window, as it already did
for revenue.

`h4_fu_amgn_gild_yoy` and `h4_fu_tmo_dhr_too_growth` widened the window because
the defaults for a question that names none (8 quarters for year over year, 5 for
growth) were also applied to a follow-up. Both defaults date from before each
quarter's change read its own filing's comparative (ADR 0009), when the
year-earlier quarters had to be rows. A year-over-year follow-up now keeps the
window on screen.

## What follows

- The difference between the planners is two cases on 66, both planning errors
  the cascade routes to the LLM planner (p = 0.50).
- The six shared defects are worth fixing whichever planner runs. Fixing them
  turns this set into development data, so the next comparison needs a fifth
  held-out set, written the same way.
