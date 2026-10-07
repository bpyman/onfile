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

`h5_mw_iphone` was refused by the rules planner for naming no company. A
segment only one company reports now names it when the question names none
(`iPhone`, `iPad`, `Mac` to Apple; `AWS` to Amazon; `Azure`, `Xbox` to
Microsoft; `Google Cloud`, `YouTube` to Alphabet; `Instagram`, `WhatsApp` to
Meta), in the rules planner's plan and in the shared reading, so the cascade
keeps the rules plan and an LLM plan with no company gets the same company. The
segment note moved from the rules planner's plan to the answer's shared notes,
so it shows whichever planner planned (held-out-5-findings ticket 03).

`h5_rk_banks_ni` and `h5_rk_drugs_gm` were refused by the rules planner: a
count before a group `by` a metric ("5 banks by net income") was not read as a
group, and a leading window ("Over the past year, the top 3 drugmakers by …")
was read as the group's name. The rules planner now reads a ranking whatever
comes first: a leading count is its length, and a clause before the first comma
that names no measure and ranks nothing is set aside for the ranking (the window
is still read from the whole question). Both are ranked by the rules planner,
so the cascade keeps its plan. `h5_rk_drugs_gm`'s recorded period is ticket 05's
(held-out-5-findings ticket 04).

`h5_rk_drugs_gm`'s period: a ranking now records the latest quarter it shows,
whichever planner planned it. The window asked for is said only in the
ranking's note, so the "four latest quarters" banner no longer sits beside a
ranking that shows one, and "add Pfizer" after it compares the latest quarter.
A ranking's growth needs no window: each company's latest quarter is set
against the comparative its filing reports (held-out-5-findings ticket 05).

`h5_gr_fast_avgo` was read right by the rules planner, but its plan named no
metric, so the cascade sent it on, and the LLM planner's run that refused
proposed revenue: the shared reading refused a catalog metric the question
does not name in words, even one its words imply. The rules planner now
proposes what the shared reading implies (revenue, for growth with no metric),
so the cascade keeps its plan, and the shared reading keeps a planner's metric
when the wording implies it ("How fast is Broadcom growing?" as revenue), so a
plan of revenue is answered whichever planner made it. A metric the wording
does not imply is still refused (held-out-5-findings ticket 06).

`h5_co_buyback` and `h5_co_volatile` were read by the LLM planner as general
explanations, and the shared typing re-typed an explanation as a lookup only
when no company was named. It now re-types one whose question names a recorded
company and a catalog metric as that company's figure, with the why note where
the question asks why, so "How does Apple's buyback affect its EPS?" is Apple's
diluted EPS and "Why is Goldman's revenue so volatile?" Goldman's revenue
whichever planner reads them. A company and no metric ("How might AI change
Goldman Sachs's business?") stays an explanation (held-out-5-findings ticket 07).
A question about what could happen ("How might AI change Apple's revenue?",
"How could tariffs affect Nvidia's gross margin?") is an explanation even when it
names a company and a catalog metric, whichever planner reads it and whichever
intent it proposed; the shared reading (`asks_speculatively`) decides, and the
rules planner reads it too. Held-out-4's `h4_other_explain_ai_drug_discovery`
("How might generative AI change drug discovery?") is now the explanation its
case expects (held-out-5-findings ticket 10).

`h5_cl_drop` and `h5_cl_fall` were read by the LLM planner as news on one run of
three, and the shared typing kept any news proposal as news. It now types a
question that asks about a change but not against what as the figure it names,
whatever intent the planner proposed, so "Why did NVIDIA's revenue drop?" and
"What caused Pfizer's earnings to fall?" ask year over year or sequential
whichever planner reads them, and "Why did revenue drop?" asks which company. A
question that asks for news by name ("What's the news on why NVIDIA's revenue
dropped?") stays news (held-out-5-findings ticket 08).

`h5_rk_worth` was proposed by the LLM planner as a ranking with no industry,
which the shared resolution refused as an unknown industry. A ranking with no
group now ranks every company in the snapshot by market value, whichever
planner left the group out, as the rules planner's does (held-out-5-findings
ticket 09).
When a planner leaves the group out, the shared typing reads the question for one
as the rules planner does (`ranked_group`), so a group the snapshot does not know
("top 10 companies in AI", "top 10 AI companies by revenue") is refused as an
unknown industry whichever planner proposed the ranking; only words that name no
group rank every company (held-out-5-findings ticket 11).
