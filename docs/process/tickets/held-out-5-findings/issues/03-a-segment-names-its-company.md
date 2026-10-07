# 03 — "iPhone sales" is Apple's revenue, with the segment note

**What to build:** Found by the fifth held-out set's run (7 October 2026; [findings](../../../../evaluation/held-out-5-findings.md)). Fixing it makes set 5 development data, as every set before it became after its run. The rules planner refuses `iPhone sales` (`h5_mw_iphone`) for naming no company; the cascade sends it on and the LLM planner answers Apple's revenue. A segment the catalog knows belongs to one company (`iPhone`, `iPad`, `Mac` to Apple; `AWS` to Amazon; `Azure`, `Xbox` to Microsoft; `Google Cloud`, `YouTube` to Alphabet; `Instagram`, `WhatsApp` to Meta): with no company named, the segment names it, and the answer is that company's company-wide figure with the segment note (README, a segment row). In the shared reading, so both planners agree and the cascade need not ask.

Cases: `h5_mw_iphone`; phrase-coverage cases with no company named for the segments of recorded companies (Apple, Microsoft, Alphabet); Amazon and Meta are not in the recording, so test theirs with fake facts.

**Acceptance:** `uv run python -m pytest` passes; `uv run python scripts/compare_answers.py` names every conversation whose answer changes, and each change is intended; the case named is read right by the planner(s) that failed it (rules planner and the shared code: on the recorded runtime; the LLM planner: with a fake LLM planner proposing what the run's observation shows, so no test calls OpenAI).

**Blocked by:** None — can start immediately

**Status:** resolved

## Answer

Shipped 7 October 2026. `segment_companies` (metric catalog) reads the company a segment belongs to: `iPhone`, `iPad`, `Mac` to Apple; `AWS`, `Amazon Web Services` to Amazon; `Azure`, `Xbox` to Microsoft; `Google Cloud`, `YouTube` to Alphabet; `Instagram`, `WhatsApp` to Meta. The rules planner uses it when a question names no company, so its plan names the company and the cascade keeps it; the shared reading (`refine_patch_from_message`, first turn) adds it to any patch that names no company and ranks no group, so an LLM plan with no company reads the same. A company named beside a segment stays ("Microsoft iPhone sales" is Microsoft). The segment note moved from the rules planner's plan to the shared answer notes (`segment_notes`), shown first, so both planners show it.

Tests: `h5_mw_iphone` with the rules planner and with the LLM planner's observed plan; six recorded segment questions (Apple, Microsoft, Alphabet) with both planners; the cascade keeping the rules plan; AWS, Instagram and WhatsApp with fake facts; 7 phrase-coverage cases (`SEGMENT_QUESTIONS`).

compare_answers: 3 of 352 conversations differ, all added here: "iPhone sales" and "Azure revenue" were refused for no company and now show Apple's and Microsoft's revenue with the segment note; "Apple revenue" then "what about iPhone sales?" shows the same revenue and now gains the segment note, which the rules planner's follow-up path never added. "Apple iPhone revenue" does not differ.
