# What the fifth held-out set found

The [planner comparison](planner-comparison.md) of 7 October 2026 ran the rules
planner, the LLM planner (`gpt-5.6-terra`) and the cascade, three runs each, on
the 160 cases of [`planner-cases-held-out-5.json`](planner-cases-held-out-5.json),
written by Grok 4.7 from the [frozen brief](held-out-5-brief.md) and checked by a
blind second labeller (159 of 160 agreed on every field; the one difference was
settled before the run). The run followed [the plan](held-out-5-plan.md) as
committed. This is what each failure was, read after the run. No label was
changed.

## Scores

| Planner | Held out (95% CI) | Familiar (46) | Novel (114) | Set 4, for reference |
| --- | ---: | ---: | ---: | ---: |
| Rules planner | 96% (91%–98%) | 98% | 95% | 85% |
| LLM planner | 94% (90%–97%) | 97% | 93% | 88% |
| Cascade | 97% (93%–99%) | 99% | 96% | 88% |

Set 4 is a different set, written by a different model, so the last column is a
description, not a comparison. No difference between planners is significant
(McNemar: rules vs LLM p = 0.73, rules vs cascade p = 0.50, LLM vs cascade
p = 0.22). The cascade sent 36 of 549 planner calls (7%) to the LLM planner and
cost $0.13; the LLM planner alone cost $1.93.

Fifteen cases failed at least one planner.

## Every planner failed: 3 cases

Each planner failed these the same way, so the mistake is in the code all three
share after planning.

| Case | Question | What happened | Expected |
| --- | --- | --- | --- |
| `h5_gr_gs_both` | Sequentially or versus last year, Goldman net interest income | Sequential change only | Both changes, as the README says naming both bases does |
| `h5_ow_intel_word` | Palantir operating income, intel aside | Intel added beside Palantir | Palantir alone: "intel" is the ordinary word |
| `h5_ow_micron_measure` | Broadcom gross margin to the micron | Micron added beside Broadcom | Broadcom alone: "to the micron" is the ordinary word |

## Only the rules planner, or the cascade through it: 4 cases

| Case | Question | What happened |
| --- | --- | --- |
| `h5_mw_iphone` | iPhone sales | Refused for no company: the segment names Apple. The cascade sent it on and the LLM planner answered Apple's revenue. |
| `h5_rk_banks_ni` | 5 banks by net income | Refused: a group by a metric with a leading count is not read as a ranking. The cascade sent it on, and the LLM planner ranked. |
| `h5_rk_drugs_gm` | Over the past year, the top 3 drugmakers by gross margin | Refused: the leading window hides the ranking. The cascade sent it on (see the next section for its period). |
| `h5_ow_micron_unit` | NVIDIA revenue to the nearest micron | Micron added beside NVIDIA. The rules planner was sure of it, so the cascade kept it; the LLM planner read it right. |

## Only the LLM planner: 7 cases, and one the cascade sent to it

| Case | Question | What the LLM planner did |
| --- | --- | --- |
| `h5_cl_drop`, `h5_cl_fall` | Why did NVIDIA's revenue drop? / What caused Pfizer's earnings to fall? | On one run of three, read it as news, refused on the recorded runtime, instead of asking against what |
| `h5_co_buyback`, `h5_co_volatile` | How does Apple's buyback affect its EPS? / Why is Goldman's revenue so volatile? | An explanation, though a company is named; the README says a named company's question is its figure. The shared typing re-types an explanation only when no company is named. |
| `h5_ow_apple_idiom`, `h5_ow_oracle_word` | "the apple of the drug group" / "an oracle for the equipment group" | Added Apple or peers, or Oracle, on some runs |
| `h5_rk_worth` | which companies are worth the most? | Refused |
| `h5_gr_fast_avgo` | How fast is Broadcom growing? | Refused on some runs. The rules planner reads it right (growth with no metric is revenue), but proposes no metric, so the cascade sends it on and fails with it. |

## A label the observation does not reach: 1 case

`h5_rk_drugs_gm` also fails the LLM planner and the cascade on its period. Both
rank the three drugmakers by gross margin and, as the README says, show each
company's latest quarter with a note that a ranking's window is not shown; the
label says the latest quarter, as the brief's rule does. But the analysis
records the window asked for (4 quarters), and the evaluation reads the period
from the analysis. The label and the screen agree; the record does not.

## Fixed since the run

`h5_gr_gs_both` showed the sequential change only because a quarter-over-quarter
view adds the year-over-year change only where the year-earlier quarter is on
screen, and the recording holds four Goldman quarters, so none was. Where the
bases sat made no difference: "Goldman net interest income, sequentially or
versus last year" failed the same way, and "Sequentially or versus last year,
Cisco revenue" passed, on the one year-over-year row its five quarters allow.
Naming both bases now carries a `sequential` operation beside `year_over_year`,
so every quarter shown has both changes, year over year from its own
comparative (held-out-5-findings ticket 01). The rules planner also no longer
reads "Sequentially" or "QoQ and YoY" as names it could not find, so the
cascade keeps its plan. Set 5 is development data from here on.

## What follows

- The planners do not differ significantly on 160 cases. The cascade is the most
  accurate, as on set 4, at 7% of the LLM planner's calls.
- **The shared defects** (both bases asked together, two ordinary-word idioms) and
  **the rules planner's misses** are worth fixing whichever planner runs, as is
  the cascade's routing of "How fast is X growing?" and a ranking's recorded
  period.
- **The LLM planner's misses** with a company named ("How does Apple's buyback
  affect its EPS?") can be caught by the shared typing, as ticket 09 did for a
  figure with no company.
- Novel cases score 3 to 4 points below familiar ones for every planner: about how
  much the app is tuned to wording it has already seen.
- Fixing any of these makes set 5 development data, so the next comparison needs
  a sixth held-out set.

`h5_ow_intel_word`, `h5_ow_micron_measure` and `h5_ow_micron_unit` added the
company an everyday word names: the index read "intel" in `intel aside` as
Intel, and "micron" is not an everyday word in 10-Q text, so `to the micron`
was always Micron. The issuer index now reads some uses of such a word as the
word (`intel aside`, `any intel`, `to the micron`, `a micron`, `the apple of`,
`an oracle for`), and the shared reading both planners pass through drops a
company proposed from one unless the question names it as well, so the LLM
planner's Apple in `h5_ow_apple_idiom` and Oracle in `h5_ow_oracle_word` go
too (held-out-5-findings ticket 02). One LLM run of `h5_ow_apple_idiom` added
three drugmakers for "the drug group"; those come from no everyday word, and
this rule leaves them.
