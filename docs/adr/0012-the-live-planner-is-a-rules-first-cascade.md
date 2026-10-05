# The live planner is a rules-first cascade

> **Supersedes, in part, [ADR 0011](0011-the-rules-planner-is-the-keyless-planner.md):** where a key is set, the LLM planner no longer plans every turn.

ADR 0011 made the LLM planner the product's planner wherever an OpenAI key is set, which on the public demo means every live turn. A fresh held-out set, written from a brief frozen first and read by nobody changing a planner until the run, measured that choice ([planner comparison](../evaluation/planner-comparison.md), 5 October 2026, 66 cases, three runs each):

| Planner | Held-out accuracy (95% CI) | Planner time p50 | Cost a planner call |
| --- | --- | ---: | ---: |
| Rules planner | 85% (74%–92%) | 1 ms | $0 |
| LLM planner (`gpt-5.6-terra`) | 88% (78%–94%) | 1,314 ms | $0.0033 |
| Cascade: rules first, LLM where the rules planner is unsure | 88% (78%–94%) | 1 ms | $0.0007 |

- **The LLM planner is not measurably better than the rules planner.** It passed two cases the rules planner failed and none the other way (exact McNemar p = 0.50).
- **The cascade matched the LLM planner case for case.** It sent 21% of planner calls to the LLM, and the two cases the rules planner failed were both among them.
- **The eight cases every planner failed were not planning errors.** Six are defects in the code all three share after planning, and two are labels that disagree with a design decision ([findings](../evaluation/held-out-4-findings.md)).

## Decision

- **Where a key is set, the live runtime plans with the cascade** (`planner_cascade.CascadeCompleter`). The rules planner plans each turn. Its plan is kept unless the plan shows it was unsure:
  - it carries a note (a corrected name, a word read as a company);
  - it asks for figures with no catalog metric;
  - it is a lookup or comparison with no company;
  - it ranks an industry the snapshot does not know;
  - it is an edit it cannot place as adding or replacing.

  Then the LLM planner plans that turn.
- **If the LLM call fails on an unsure turn, the rules plan stands.** ADR 0011 rejected a fallback for the LLM-first planner, so that a visitor would know which planner answered. In the cascade the rules planner is the primary planner, and its plan still passes through the same guards (clarify, refuse) as any plan.
- **Without a key, or with public OpenAI turned off, the rules planner plans alone**, as before.
- **The rest of ADR 0011 stands.** The rules planner is the test and keyless planner, and accuracy work goes to the shared layers. The six shared defects the held-out set found are the next accuracy work.

## Considered options

- **The rules planner alone, everywhere.** It is free and plans in a millisecond, and its gap to the LLM planner is not significant on 66 cases. Rejected for now: both cases it failed are of a kind it cannot rule out (an ordinary word read as a company, a question outside its rules), and the cascade fixes those at a fifth of the LLM planner's cost.
- **The LLM planner on every turn (ADR 0011).** Rejected: no accuracy gain over the cascade on these cases, five times the cost a planner call, and about 1.3 seconds added to every turn.
- **The LLM planner first, with the rules planner as a fallback.** Not measured. It keeps the LLM planner's cost and latency on every turn for no expected gain.

## Revisit when

- A fifth held-out set is run. This set becomes development data once its shared defects are fixed.
- The cascade's share of LLM calls rises well above a quarter, or the rules planner fails cases its unsure signals do not catch.
