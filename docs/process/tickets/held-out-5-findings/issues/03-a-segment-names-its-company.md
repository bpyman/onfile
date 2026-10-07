# 03 — "iPhone sales" is Apple's revenue, with the segment note

**What to build:** Found by the fifth held-out set's run (7 October 2026; [findings](../../../../evaluation/held-out-5-findings.md)). Fixing it makes set 5 development data, as every set before it became after its run. The rules planner refuses `iPhone sales` (`h5_mw_iphone`) for naming no company; the cascade sends it on and the LLM planner answers Apple's revenue. A segment the catalog knows belongs to one company (`iPhone`, `iPad`, `Mac` to Apple; `AWS` to Amazon; `Azure`, `Xbox` to Microsoft; `Google Cloud`, `YouTube` to Alphabet; `Instagram`, `WhatsApp` to Meta): with no company named, the segment names it, and the answer is that company's company-wide figure with the segment note (README, a segment row). In the shared reading, so both planners agree and the cascade need not ask.

Cases: `h5_mw_iphone`; phrase-coverage cases with no company named for the segments of recorded companies (Apple, Microsoft, Alphabet); Amazon and Meta are not in the recording, so test theirs with fake facts.

**Acceptance:** `uv run python -m pytest` passes; `uv run python scripts/compare_answers.py` names every conversation whose answer changes, and each change is intended; the case named is read right by the planner(s) that failed it (rules planner and the shared code: on the recorded runtime; the LLM planner: with a fake LLM planner proposing what the run's observation shows, so no test calls OpenAI).

**Blocked by:** None — can start immediately

**Status:** ready-for-agent
