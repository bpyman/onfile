# 02 — "Intel aside", "to the micron", "the apple of", "an oracle for" name no company

**What to build:** Found by the fifth held-out set's run (7 October 2026; [findings](../../../../evaluation/held-out-5-findings.md)). Fixing it makes set 5 development data, as every set before it became after its run. An everyday-word company name used as the word adds the company:

- every planner: `Palantir operating income, intel aside` adds Intel (`h5_ow_intel_word`); `Broadcom gross margin to the micron` adds Micron (`h5_ow_micron_measure`);
- the rules planner, kept by the cascade: `NVIDIA revenue to the nearest micron` adds Micron (`h5_ow_micron_unit`);
- the LLM planner, on some runs: `On revenue, AbbVie is the apple of the drug group` adds Apple or peers (`h5_ow_apple_idiom`); `Cisco cash, an oracle for the equipment group` adds Oracle (`h5_ow_oracle_word`).

CONTEXT.md: an everyday-word name names the company only where a question uses it as one. Apply that in the shared reading both planners pass through, so a company a planner proposes from an everyday word used as the word is dropped whichever planner proposed it: `intel` as information (`intel aside`, `some intel on`, `any intel`), `micron` as a unit (`to the micron`, `to the nearest micron`, `a micron`), `the apple of`, `an oracle (for|of)`, alongside the idioms probe-round-3 fixed (`apples to apples`). A named company beside the word stays (`Intel and Palantir operating income`).

Cases: the five above; add an ordinary-word idiom phrase-coverage group.

**Acceptance:** `uv run python -m pytest` passes; `uv run python scripts/compare_answers.py` names every conversation whose answer changes, and each change is intended; the case named is read right by the planner(s) that failed it (rules planner and the shared code: on the recorded runtime; the LLM planner: with a fake LLM planner proposing what the run's observation shows, so no test calls OpenAI).

**Blocked by:** None — can start immediately

**Status:** ready-for-agent
