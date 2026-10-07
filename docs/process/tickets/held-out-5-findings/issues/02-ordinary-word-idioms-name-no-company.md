# 02 — "Intel aside", "to the micron", "the apple of", "an oracle for" name no company

**What to build:** Found by the fifth held-out set's run (7 October 2026; [findings](../../../../evaluation/held-out-5-findings.md)). Fixing it makes set 5 development data, as every set before it became after its run. An everyday-word company name used as the word adds the company:

- every planner: `Palantir operating income, intel aside` adds Intel (`h5_ow_intel_word`); `Broadcom gross margin to the micron` adds Micron (`h5_ow_micron_measure`);
- the rules planner, kept by the cascade: `NVIDIA revenue to the nearest micron` adds Micron (`h5_ow_micron_unit`);
- the LLM planner, on some runs: `On revenue, AbbVie is the apple of the drug group` adds Apple or peers (`h5_ow_apple_idiom`); `Cisco cash, an oracle for the equipment group` adds Oracle (`h5_ow_oracle_word`).

CONTEXT.md: an everyday-word name names the company only where a question uses it as one. Apply that in the shared reading both planners pass through, so a company a planner proposes from an everyday word used as the word is dropped whichever planner proposed it: `intel` as information (`intel aside`, `some intel on`, `any intel`), `micron` as a unit (`to the micron`, `to the nearest micron`, `a micron`), `the apple of`, `an oracle (for|of)`, alongside the idioms probe-round-3 fixed (`apples to apples`). A named company beside the word stays (`Intel and Palantir operating income`).

Cases: the five above; add an ordinary-word idiom phrase-coverage group.

**Acceptance:** `uv run python -m pytest` passes; `uv run python scripts/compare_answers.py` names every conversation whose answer changes, and each change is intended; the case named is read right by the planner(s) that failed it (rules planner and the shared code: on the recorded runtime; the LLM planner: with a fake LLM planner proposing what the run's observation shows, so no test calls OpenAI).

**Blocked by:** None — can start immediately

**Status:** resolved

## Answer

Resolved 7 October 2026.

`Palantir operating income, intel aside`, `Broadcom gross margin to the micron` and `NVIDIA revenue to the nearest micron` show the named company alone with every planner, and the LLM planner's Apple in `On revenue, AbbVie is the apple of the drug group` and Oracle in `Cisco cash, an oracle for the equipment group` are dropped.

- The rules planner's misreading was in the issuer index: "intel" with no word before it counted as Intel, and "micron" is not an everyday word in 10-Q text at all, so every "micron" was Micron. `_WORD_USES` in `issuer_index.py` reads `intel aside`, `some|any|more|no intel`, `to the (nearest) micron`, `nearest|a micron`, `the apple of` and `an oracle for|of` as the word, whatever the case; `find` skips those words (not for a planner's company field), and a company named beside the word stays (`Micron and Broadcom gross margin, to the micron`).
- The shared step: `word_uses` returns the names a question uses as the word, `apples to apples` included, and `_without_word_uses` in `request_wording.py`, the first step of `refine_patch_from_message` that every planner's patch passes through, drops a proposed company one of them names unless the index finds it in the question too. One company left is a lookup, as before.
- One LLM run of the apple idiom proposed three drugmakers for "the drug group", not Apple; they come from no everyday word and stay (recorded in `docs/process/rules-to-review.md`).
- Tests: the five cases pass with the rules planner on the recorded runtime, and four with a stand-in proposing what the LLM planner did (`tests/test_held_out_5_findings.py`), plus a named company beside the word kept with either planner; `find` on 12 wordings (`tests/unit/test_planner_wording.py`). Phrase coverage gains "Everyday-word names used as the word" (7 cases).
- README (Companies), CONTEXT.md (Everyday-word name), ADR 0010 and the findings doc say the rule.

`compare_answers` reports 3 of 348 conversations differ from HEAD, three of the four added here: `Palantir operating income, intel aside`, `Broadcom gross margin to the micron` and `NVIDIA revenue to the nearest micron` showed a comparison with Intel or Micron and now show the named company alone. `Intel and Palantir operating income` does not differ.
