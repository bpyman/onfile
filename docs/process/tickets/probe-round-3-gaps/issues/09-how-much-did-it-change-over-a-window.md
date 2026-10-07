# 09 — "How much did revenue change over the last year?" is year over year over that window

**What to build:** Decided in `rules-to-review.md` (2026-10-07, probe-round-3-gaps 07). `How did AMD's EBITDA change over the past year?` shows 4 quarters, each with its year-over-year change (ticket 07), but `How much did Intel's revenue change over the last year?` and `Over the past 10 quarters, how has Thermo Fisher's revenue moved?` show the span's quarters with no change column (`_names_a_span` in `request_wording.py`: "the span is the answer"). Every change asked over a named window is year over year over that window, whatever the change wording (`how much did ... change`, `how has ... moved`, `how did ... change`, `how has ... grown`), as the README's growth row says. With no window, `How much did revenue change?` still asks against what.

Change `test_what_a_change_is_measured_against`'s two expectations for these questions with the reading, and say so in the commit.

**Acceptance:** both questions above show their window's quarters, each with its year-over-year change; `How much did Intel's revenue change?` still asks; phrase-coverage cases for each wording. `uv run python -m pytest` passes; `uv run python scripts/compare_answers.py` names every conversation whose answer changes, and each change is intended.

**Blocked by:** None — can start immediately

**Status:** ready-for-agent
