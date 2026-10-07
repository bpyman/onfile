# 01 — "Sequentially or versus last year, …" shows both changes

**What to build:** Found by the fifth held-out set's run (7 October 2026; [findings](../../../../evaluation/held-out-5-findings.md)). Fixing it makes set 5 development data, as every set before it became after its run. Every planner failed `h5_gr_gs_both`: `Sequentially or versus last year, Goldman net interest income` shows only the sequential change. The README says naming both bases shows both changes, and `Did Cisco's revenue grow sequentially or versus last year?` already does; with the bases leading the question (and `versus last year` before the company), the year-over-year half is lost in the shared reading of words (`request_wording.py`, the comparison and change-base reading). Read both bases wherever they sit in the question.

Case: `h5_gr_gs_both` (both `sequential` and `year_over_year`); add phrase-coverage cases with the bases leading and trailing.

**Acceptance:** `uv run python -m pytest` passes; `uv run python scripts/compare_answers.py` names every conversation whose answer changes, and each change is intended; the case named is read right by the planner(s) that failed it (rules planner and the shared code: on the recorded runtime; the LLM planner: with a fake LLM planner proposing what the run's observation shows, so no test calls OpenAI).

**Blocked by:** None — can start immediately

**Status:** ready-for-agent
