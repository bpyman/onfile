# Rules planner vs LLM planner

Generated `2026-10-05T13:25:46.947527+00:00` on the recorded runtime, over 285 cases: 28 scorecard questions, 191 development cases ([`planner-cases.json`](planner-cases.json), [`planner-cases-v2.json`](planner-cases-v2.json), [`planner-cases-v3.json`](planner-cases-v3.json)), and 66 held-out cases ([`planner-cases-held-out-4.json`](planner-cases-held-out-4.json)). Every case was labelled before a planner ran on it. The held-out cases were written from a brief frozen first ([`held-out-4-brief.md`](held-out-4-brief.md)) by a separate session, and were not read by whoever changed a planner until this run; see [Protocol](#protocol).

The planners that call OpenAI ran on the held-out cases only, to keep within the evaluation budget; the rules planner ran on every case. What each held-out failure was is in [held-out-4-findings.md](held-out-4-findings.md).

Each case is a conversation run end to end with only the planner swapped, and is scored on the last turn's outcome (answer, clarify or refuse), intent, companies, metrics, period and operations. A case passes when every labelled field is right.

## Rules planner

| Split | Cases | Accuracy | Spread across runs (sd) | Agreement across runs |
| --- | ---: | ---: | ---: | ---: |
| Scorecard | 28 | 100% | 0.0% | 100% |
| Development | 191 | 98% | 0.0% | 100% |
| Held out | 66 | 85% | 0.0% | 100% |
| All | 285 | 95% | 0.0% | 100% |

Field accuracy: outcome 99%, intent 99%, tickers 98%, tickers_include 92%, metrics 99%, periods 94%, operations_include 93%.
Planner time p50 / p95: 1 ms / 2 ms over 993 calls.

<details><summary>Cases it got wrong</summary>

- `h3_apples_to_apples` (run 1): tickers
- `h3_healthcare_market_cap` (run 1): outcome, tickers_include
- `h3_tech_top_ten_revenue` (run 1): metrics, outcome, tickers_include
- `h4_bac_nii_couple_quarters` (run 1): metrics, outcome, periods, tickers
- `h4_fu_amgn_gild_yoy` (run 1): periods
- `h4_fu_jpm_and_wfc_remove_jpm` (run 1): metrics, periods
- `h4_fu_tmo_dhr_too_growth` (run 1): periods
- `h4_ow_apples_word_mrk_pfe` (run 1): tickers
- `h4_growth_nvda_how_fast` (run 1): periods
- `h4_growth_three_tickers_operating_income` (run 1): periods
- `h4_growth_unh_ocf_year_on_year` (run 1): operations_include
- `h4_clarify_intel_change_no_base` (run 1): outcome
- `h4_other_explain_ai_drug_discovery` (run 1): intent
- `h3_apples_to_apples` (run 2): tickers
- `h3_healthcare_market_cap` (run 2): outcome, tickers_include
- `h3_tech_top_ten_revenue` (run 2): metrics, outcome, tickers_include
- `h4_bac_nii_couple_quarters` (run 2): metrics, outcome, periods, tickers
- `h4_fu_amgn_gild_yoy` (run 2): periods
- `h4_fu_jpm_and_wfc_remove_jpm` (run 2): metrics, periods
- `h4_fu_tmo_dhr_too_growth` (run 2): periods
- `h4_ow_apples_word_mrk_pfe` (run 2): tickers
- `h4_growth_nvda_how_fast` (run 2): periods
- `h4_growth_three_tickers_operating_income` (run 2): periods
- `h4_growth_unh_ocf_year_on_year` (run 2): operations_include
- `h4_clarify_intel_change_no_base` (run 2): outcome
- `h4_other_explain_ai_drug_discovery` (run 2): intent
- `h3_apples_to_apples` (run 3): tickers
- `h3_healthcare_market_cap` (run 3): outcome, tickers_include
- `h3_tech_top_ten_revenue` (run 3): metrics, outcome, tickers_include
- `h4_bac_nii_couple_quarters` (run 3): metrics, outcome, periods, tickers
- `h4_fu_amgn_gild_yoy` (run 3): periods
- `h4_fu_jpm_and_wfc_remove_jpm` (run 3): metrics, periods
- `h4_fu_tmo_dhr_too_growth` (run 3): periods
- `h4_ow_apples_word_mrk_pfe` (run 3): tickers
- `h4_growth_nvda_how_fast` (run 3): periods
- `h4_growth_three_tickers_operating_income` (run 3): periods
- `h4_growth_unh_ocf_year_on_year` (run 3): operations_include
- `h4_clarify_intel_change_no_base` (run 3): outcome
- `h4_other_explain_ai_drug_discovery` (run 3): intent

</details>

## LLM planner (`gpt-5.6-terra`)

| Split | Cases | Accuracy | Spread across runs (sd) | Agreement across runs |
| --- | ---: | ---: | ---: | ---: |
| Held out | 66 | 88% | 0.0% | 98% |
| All | 66 | 88% | 0.0% | 98% |

Field accuracy: outcome 97%, intent 100%, tickers 98%, tickers_include 100%, metrics 96%, periods 87%, operations_include 86%.
Planner time p50 / p95: 1314 ms / 1971 ms over 234 calls; 327,705 input and 10,335 output tokens (718 reasoning), $0.78 in all, $0.0033 a call.

<details><summary>Cases it got wrong</summary>

- `h4_bac_nii_couple_quarters` (run 1): metrics, outcome, periods, tickers
- `h4_fu_amgn_gild_yoy` (run 1): periods
- `h4_fu_jpm_and_wfc_remove_jpm` (run 1): metrics, periods
- `h4_fu_tmo_dhr_too_growth` (run 1): periods
- `h4_growth_nvda_how_fast` (run 1): periods
- `h4_growth_three_tickers_operating_income` (run 1): periods
- `h4_growth_unh_ocf_year_on_year` (run 1): operations_include
- `h4_clarify_intel_change_no_base` (run 1): outcome
- `h4_bac_nii_couple_quarters` (run 2): metrics, outcome, periods, tickers
- `h4_fu_amgn_gild_yoy` (run 2): periods
- `h4_fu_jpm_and_wfc_remove_jpm` (run 2): metrics, periods
- `h4_fu_tmo_dhr_too_growth` (run 2): periods
- `h4_growth_nvda_how_fast` (run 2): periods
- `h4_growth_three_tickers_operating_income` (run 2): periods
- `h4_growth_unh_ocf_year_on_year` (run 2): operations_include
- `h4_clarify_intel_change_no_base` (run 2): outcome
- `h4_bac_nii_couple_quarters` (run 3): metrics, outcome, periods, tickers
- `h4_fu_amgn_gild_yoy` (run 3): periods
- `h4_fu_jpm_and_wfc_remove_jpm` (run 3): metrics, periods
- `h4_fu_tmo_dhr_too_growth` (run 3): periods
- `h4_growth_nvda_how_fast` (run 3): periods
- `h4_growth_three_tickers_operating_income` (run 3): periods
- `h4_growth_unh_ocf_year_on_year` (run 3): operations_include
- `h4_clarify_intel_change_no_base` (run 3): outcome

</details>

## Cascade (rules planner, then `gpt-5.6-terra` where it is unsure)

| Split | Cases | Accuracy | Spread across runs (sd) | Agreement across runs |
| --- | ---: | ---: | ---: | ---: |
| Held out | 66 | 88% | 0.0% | 100% |
| All | 66 | 88% | 0.0% | 100% |

Field accuracy: outcome 97%, intent 100%, tickers 98%, tickers_include 100%, metrics 96%, periods 87%, operations_include 86%.
It sent 48 of 234 planner calls (21%) to the LLM planner, where the rules planner was unsure.
Planner time p50 / p95: 1 ms / 1471 ms over 234 calls; 68,088 input and 2,088 output tokens (360 reasoning), $0.16 in all, $0.0007 a call.

<details><summary>Cases it got wrong</summary>

- `h4_bac_nii_couple_quarters` (run 1): metrics, outcome, periods, tickers
- `h4_fu_amgn_gild_yoy` (run 1): periods
- `h4_fu_jpm_and_wfc_remove_jpm` (run 1): metrics, periods
- `h4_fu_tmo_dhr_too_growth` (run 1): periods
- `h4_growth_nvda_how_fast` (run 1): periods
- `h4_growth_three_tickers_operating_income` (run 1): periods
- `h4_growth_unh_ocf_year_on_year` (run 1): operations_include
- `h4_clarify_intel_change_no_base` (run 1): outcome
- `h4_bac_nii_couple_quarters` (run 2): metrics, outcome, periods, tickers
- `h4_fu_amgn_gild_yoy` (run 2): periods
- `h4_fu_jpm_and_wfc_remove_jpm` (run 2): metrics, periods
- `h4_fu_tmo_dhr_too_growth` (run 2): periods
- `h4_growth_nvda_how_fast` (run 2): periods
- `h4_growth_three_tickers_operating_income` (run 2): periods
- `h4_growth_unh_ocf_year_on_year` (run 2): operations_include
- `h4_clarify_intel_change_no_base` (run 2): outcome
- `h4_bac_nii_couple_quarters` (run 3): metrics, outcome, periods, tickers
- `h4_fu_amgn_gild_yoy` (run 3): periods
- `h4_fu_jpm_and_wfc_remove_jpm` (run 3): metrics, periods
- `h4_fu_tmo_dhr_too_growth` (run 3): periods
- `h4_growth_nvda_how_fast` (run 3): periods
- `h4_growth_three_tickers_operating_income` (run 3): periods
- `h4_growth_unh_ocf_year_on_year` (run 3): operations_include
- `h4_clarify_intel_change_no_base` (run 3): outcome

</details>

## Is the difference real?

Each pair of planners on the same cases: how many cases each passed alone, and the two-sided exact McNemar p-value for the difference. Both planners are deterministic run to run, so a case counts once. Accuracies are given with 95% Wilson intervals.

| Planners | Split | Cases | Both pass | Only first | Only second | Neither | First (95% CI) | Second (95% CI) | p |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- | --- | ---: |
| Rules planner vs LLM planner | Held out | 66 | 56 | 0 | 2 | 8 | 85% (74%–92%) | 88% (78%–94%) | 0.50 |
| Rules planner vs Cascade | Held out | 66 | 56 | 0 | 2 | 8 | 85% (74%–92%) | 88% (78%–94%) | 0.50 |
| LLM planner vs Cascade | Held out | 66 | 58 | 0 | 0 | 8 | 88% (78%–94%) | 88% (78%–94%) | 1.00 |

## Protocol

Held-out cases measure how a planner generalises only until someone changing a planner reads them. Each set so far was held out once and then became development data:

1. **First set** ([`planner-cases.json`](planner-cases.json), 50 development cases). Written for the first comparison and labelled before either planner ran. The planner changes that followed were diagnosed on them.
2. **Second set** ([`planner-cases-v2.json`](planner-cases-v2.json), 72). Written by a separate session, but its hand-back included the cases, so the engineer saw them partway through the planner work. It was never held out.
3. **Third set** ([`planner-cases-v3.json`](planner-cases-v3.json), 69). Written blind by a separate session and held out for the run of 2026-10-03, which scored the rules planner 91% and the LLM planner 96%. After that run its results were read, one label changed with a product decision (ADR 0004: a question naming two metrics is answered with both; recorded in the file's `label_changes`), and the recorded SEC data was refreshed. Scores on it since are not blind.
4. **Fourth set** ([`planner-cases-held-out-4.json`](planner-cases-held-out-4.json), 66), the held-out split here. Its brief was committed before any case existed ([`held-out-4-brief.md`](held-out-4-brief.md), commit `54a0e22`). A separate Claude session wrote and labelled the cases from it, reading only `README.md`, `CONTEXT.md` and ADRs 0004, 0007 and 0008, and the cases were committed (`bc237f0`) before any planner ran on them. The engineer checked only their format and counts. The cascade and the significance test were committed (`3ce77ea`) before this run, so neither was tuned on these cases. A cost estimate just before the run also ran the free rules planner on them; only its cost line was read.

Labels are not edited to fit a result. A label found wrong after a run is recorded in the case file's `label_changes` with the reason, and this report scores the labels as committed.

Each planner gets two scores. **As labelled** is the primary one, and the only one compared across sets. **After adjudication** replaces a label field that disagrees with a product rule: a rule in the README, `CONTEXT.md` or an ADR as committed before the case was written, quoted with where it is. A label is not adjudicated because a result disagrees with it, because a rule was decided after the run, or because every planner failed it: a shared defect is a failure. Adjudications live in the case file's `adjudications`, beside the label they replace, and a report lists each one under Adjudicated labels. Each case run's observation is saved, so an adjudication made after a paid run is scored with `--from-json` without running a planner again.

Two limits. The cases were written by a Claude model, and the rules planner was written with Claude-based coding agents, so shared habits of phrasing may favour the rules planner; the LLM planner is an OpenAI model. And 66 cases detect only large differences: McNemar's test needs about six cases passed by one planner alone, and none by the other, before p falls below 0.05.

The rules planner is deterministic, so its spread is zero by construction. The recorded runtime replays SEC data, so the comparison isolates planning; it says nothing about EDGAR freshness. See [the scorecard](scorecard.md) and [figures checked against their filings](filing-check.md).
