# The rules planner is the keyless and test planner; accuracy work goes to the shared layers

> **Builds on [ADR 0010](0010-one-reading-of-names-and-windows.md).**
> **Superseded in part by [ADR 0012](0012-the-live-planner-is-a-rules-first-cascade.md):** where a key is set, the live runtime plans with a rules-first cascade, not the LLM planner on every turn.

Onfile has two planners that propose the same thing: a spec patch, an essay request, or a filing comparison. The LLM planner (`planner.py`) runs whenever an OpenAI key is set and allowed, which on the public demo means live turns. The rules planner (`rules_planner.py`, about a thousand lines of wording rules) runs everywhere else.

The planner comparison showed where accuracy comes from. On the held-out cases, in the blind run, the rules planner scored 91% and the LLM 96% (the rules planner reaches 96% after the product decisions and refreshed recording that followed, a figure no longer blind). Every gain in ADR 0010 came from code both planners share, not from either planner: the issuer index and company resolver, the window grammar, follow-up edits, and spec resolution. Improving the rules planner to match the LLM would mean writing a rule for every new phrasing, and chasing a model the product already has.

## Decision

- **The LLM planner is the product's planner** wherever a key is set. Planner accuracy work goes into the shared deterministic layers, which both planners pass through, and into the LLM's prompt and schema.
- **The rules planner stays, in a fixed role.** It is:
  - the planner for keyless runs: a fresh clone, the Docker image as shipped, a deployment without a key or with public OpenAI turned off;
  - the planner the test suite, the scorecard and the recorded demo answers run on. It is free and deterministic, so tests can pin exact figures and CI needs no key;
  - the baseline the planner comparison measures the LLM against.
- **The rules planner changes only when one of those roles needs it.** That means a shared test, a scorecard case, a guided story, or a keyless visitor's question it misreads. Its held-out accuracy is reported, not chased.
- **Each fix goes in the shared layers when it can.** A wording problem the rules planner shares with the LLM is fixed in the shared layers, not in the rules planner.

## Considered options

- **Remove the rules planner, and replay recorded LLM plans in tests.** Rejected. A recorded plan breaks whenever the prompt or schema changes, so every prompt edit would re-record the suite. Keyless runs would stop working, and tests could no longer pin figures without a model behind them.
- **Keep improving the rules planner toward the LLM.** Rejected. Every phrasing becomes a rule to maintain, the held-out gap would close slowly if at all, and the same effort in the shared layers improves both planners.
- **Fall back from the LLM to the rules planner on a model error.** Not adopted here. A failed model call is reported, so a visitor knows which planner answered. This is worth revisiting if model errors become common.
