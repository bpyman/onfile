# 06 — "How fast is Broadcom growing?" stays with the rules planner

**What to build:** Found by the fifth held-out set's run (7 October 2026; [findings](../../../../evaluation/held-out-5-findings.md)). Fixing it makes set 5 development data, as every set before it became after its run. `How fast is Broadcom growing?` (`h5_gr_fast_avgo`): the rules planner's reading is right (growth with no metric is revenue, README), but it proposes no metric, so the cascade sends the turn to the LLM planner, which refused it on some runs. As the overview was (probe review, 6 October), make the rules planner propose what the shared reading implies (revenue, for growth with no metric) so the cascade keeps its plan. The cascade's `unsure_reason` is unchanged.

Case: `h5_gr_fast_avgo` under the cascade with a fake LLM planner that refuses; phrase coverage's `SENT_TO_MODEL` no longer lists a growth question with no metric.

**Acceptance:** `uv run python -m pytest` passes; `uv run python scripts/compare_answers.py` names every conversation whose answer changes, and each change is intended; the case named is read right by the planner(s) that failed it (rules planner and the shared code: on the recorded runtime; the LLM planner: with a fake LLM planner proposing what the run's observation shows, so no test calls OpenAI).

**Blocked by:** None — can start immediately

**Status:** resolved

## Answer

Shipped 7 October 2026. The rules planner proposes revenue for growth with no metric
(`implied_metrics` gives `("revenue",)` beside a named company), as it proposes the overview for
"How is Apple doing?", so `unsure_reason` finds nothing and the cascade keeps the plan;
`unsure_reason` is unchanged.

Planning revenue exposed a shared refusal: `bind_metrics_from_message` refused any catalog slug
the wording does not name, even one the wording implies, so a plan of revenue for "How fast is
Broadcom growing?" was refused "Unknown metric 'unknown'". That is what the LLM planner's
refusing run shows too. The shared reading now keeps a planner's metrics when the wording
implies them all; a slug the wording does not imply is still the planner's alone and refused.

- Tests: `h5_gr_fast_avgo` under the cascade with a refusing LLM planner (the rules plan is kept
  and passes every field), with an LLM planner proposing Broadcom revenue, and the rules plan
  for three growth wordings.
- Phrase coverage: +5 `GROWTH_NO_METRIC_QUESTIONS`, all read right and none sent to the model;
  `SENT_TO_MODEL` unchanged.
- compare_answers: `0 of 360 conversations differ` (+2 added: "How fast is Broadcom growing?",
  "Is Apple growing?"); the rules planner already answered these through the shared reading.
