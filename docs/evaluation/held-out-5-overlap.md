# Held-out set 5: overlap with earlier data

46 of 160 held-out cases share a template with one of 833 earlier questions (development cases, phrase-coverage phrasings and probes): companies and numbers replaced, their words overlapping by 80% or more. None is removed: the planner comparison scores the set as familiar and novel beside the whole (`held_out_overlap`).

| Case | Question | Nearest earlier | Similarity |
| --- | --- | --- | ---: |
| `h5_mw_topline` | `What's NVIDIA's top line?` | coverage metric:top line:question: `What was Apple's top line?` | 0.80 |
| `h5_mw_sales` | `AbbVie sales` | coverage metric:sales:terse: `apple sales` | 1.00 |
| `h5_mw_bottom` | `Microsoft's bottom line` | coverage metric:bottom line:terse: `apple bottom line` | 1.00 |
| `h5_mw_cogs` | `Micron cogs` | coverage metric:COGS:terse: `apple COGS` | 1.00 |
| `h5_mw_divyield_beside` | `Apple revenue and dividend yield` | probe p5r3_fable_unknown_beside_known: `Pfizer dividend yield and revenue` | 1.00 |
| `h5_mw_sga` | `Cisco SG&A` | coverage metric:SG&A:terse: `apple SG&A` | 1.00 |
| `h5_mw_margins` | `Pfizer margins` | probe p5r3_fable_abbvie_margins: `abbvie margins` | 1.00 |
| `h5_mw_sga_pct` | `SG&A as a percentage of sales for Amgen` | coverage metric:SG&A as a percentage of sales:terse: `apple SG&A as a percentage of sales` | 0.88 |
| `h5_mw_rd_pct` | `R&D as a percentage of revenue, Gilead` | coverage metric:R&D as a percentage of revenue:terse: `apple R&D as a percentage of revenue` | 1.00 |
| `h5_per_six_quarters` | `six quarters of Apple revenue` | coverage window:6 quarters: `Apple revenue 6 quarters` | 0.80 |
| `h5_per_fifteen_months` | `Micron revenue, 15 months` | coverage window:18 months: `Apple revenue 18 months` | 1.00 |
| `h5_per_since_2024` | `AMD revenue since 2024` | coverage window:since 2024: `Apple revenue since 2024` | 1.00 |
| `h5_per_since_fiscal` | `AbbVie revenue since the start of fiscal 2025` | coverage window:since the start of fiscal 2025: `Apple revenue since the start of fiscal 2025` | 1.00 |
| `h5_per_last_twelve_ni` | `last twelve months net income for Palantir` | coverage metric:last twelve months net income:terse: `apple last twelve months net income` | 0.86 |
| `h5_per_ltm_ni` | `LTM net income for Broadcom` | coverage metric:LTM net income:terse: `apple LTM net income` | 0.80 |
| `h5_per_ni_over_twelve` | `Gilead net income over the last twelve months` | coverage window:pfizer net income over the last twelve months: `pfizer net income over the last twelve months` | 1.00 |
| `h5_co_bofa` | `bofa revenue` | coverage metric:revenue:terse: `apple revenue` | 1.00 |
| `h5_co_unh_ocf` | `UnitedHealth's operating cash flow` | coverage metric:operating cash flow:terse: `apple operating cash flow` | 1.00 |
| `h5_fu_avgo_add` | `NVIDIA operating margin over the last 4 quarters → add Broadcom` | case follow_up_metric_and_company: `Microsoft revenue over the last four quarters → add Apple → now add operating margin` | 0.80 |
| `h5_fu_make_8` | `Apple's revenue → make it the last 8 quarters` | case h4_fu_cisco_window_eight: `CSCO revenue last 4 quarters → make it the last 8 quarters` | 1.00 |
| `h5_ow_apple` | `apple revenue` | coverage metric:revenue:terse: `apple revenue` | 1.00 |
| `h5_ow_oracle` | `oracle free cash flow` | coverage metric:free cash flow:terse: `apple free cash flow` | 1.00 |
| `h5_rk_banks_ni` | `5 banks by net income` | case h4_rank_banks_net_income: `top 3 banks by net income?` | 0.83 |
| `h5_gr_fast_csco` | `How fast is Cisco's revenue growing?` | case h4_growth_nvda_how_fast: `How fast is Nvidia's revenue growing?` | 1.00 |
| `h5_gr_fast_avgo` | `How fast is Broadcom growing?` | probe p5r3_fable_how_fast_growing_no_metric: `how fast is Broadcom growing` | 1.00 |
| `h5_gr_nvda_yoy` | `NVIDIA revenue year over year` | case growth_chart: `Microsoft revenue year over year` | 1.00 |
| `h5_gr_gild_2q` | `Gilead revenue over the last 2 quarters, quarter over quarter` | case window_four_quarters: `Microsoft revenue over the last four quarters` | 0.86 |
| `h5_gr_amgn_ebitda` | `How did Amgen's EBITDA change over the past year?` | coverage window_change:How did AMD's EBITDA change over the past year?: `How did AMD's EBITDA change over the past year?` | 1.00 |
| `h5_gr_orcl_10` | `Over the past 10 quarters, how has Oracle revenue moved?` | case h3_tmo_rev_past_ten: `Over the past 10 quarters, how has Thermo Fisher's revenue moved?` | 0.90 |
| `h5_gr_jnj_since` | `Johnson & Johnson revenue since 2025, year over year` | coverage since_change:Apple revenue since 2025 year over year: `Apple revenue since 2025 year over year` | 0.86 |
| `h5_cl_margin` | `Broadcom margin` | case h4_clarify_pfizer_margin: `Pfizer margin?` | 1.00 |
| `h5_cl_drop` | `Why did NVIDIA's revenue drop?` | coverage no_base:Why did Apple revenue drop?: `Why did Apple revenue drop?` | 1.00 |
| `h5_cl_change` | `How much did Merck's revenue change?` | case h4_clarify_intel_change_no_base: `How much did Intel's revenue change?` | 1.00 |
| `h5_cl_fall` | `What caused Pfizer's earnings to fall?` | coverage no_base:What caused Pfizer's earnings to fall?: `What caused Pfizer's earnings to fall?` | 1.00 |
| `h5_rf_advice` | `Should I buy Lilly?` | case advice_declined: `Should I buy Nvidia stock?` | 0.80 |
| `h5_rf_spy` | `SPY revenue` | case fund_is_not_a_company: `SPY revenue` | 1.00 |
| `h5_rf_2030` | `Apple revenue in 2030` | coverage window:in Q2 2025: `Apple revenue in Q2 2025` | 0.80 |
| `h5_rf_2012` | `Pfizer revenue in fiscal 2012` | coverage window:in fiscal 2025: `Apple revenue in fiscal 2025` | 1.00 |
| `h5_rf_stock_perf` | `Apple stock performance` | coverage unknown:Apple's stock performance: `Apple's stock performance` | 1.00 |
| `h5_ot_nvda_10q` | `What changed in NVIDIA's latest 10-Q?` | case filing_change_latest: `What changed in Microsoft's latest 10-Q?` | 1.00 |
| `h5_ot_mrk_annual` | `what's new in Merck's annual report` | probe p5r3_fable_whats_new_annual_report: `what's new in Apple's annual report` | 1.00 |
| `h5_ot_what_eps` | `What is EPS?` | coverage general:What is EPS?: `What is EPS?` | 1.00 |
| `h5_ot_buyback` | `How does a buyback affect EPS?` | coverage general:How does a buyback affect EPS?: `How does a buyback affect EPS?` | 1.00 |
| `h5_ot_ai_banking` | `How might AI change banking?` | coverage general:How might AI change banking?: `How might AI change banking?` | 1.00 |
| `h5_ot_wfc_doing` | `How is Wells Fargo doing?` | case overview_with_trends: `How is Nvidia doing?` | 0.80 |
| `h5_ot_dhr_perf` | `Danaher's performance over the last 4 quarters` | coverage overview:Apple's performance over the last 4 quarters: `Apple's performance over the last 4 quarters` | 1.00 |
