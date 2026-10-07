# 01 — "Sequentially or versus last year, …" shows both changes

**What to build:** Found by the fifth held-out set's run (7 October 2026; [findings](../../../../evaluation/held-out-5-findings.md)). Fixing it makes set 5 development data, as every set before it became after its run. Every planner failed `h5_gr_gs_both`: `Sequentially or versus last year, Goldman net interest income` shows only the sequential change. The README says naming both bases shows both changes, and `Did Cisco's revenue grow sequentially or versus last year?` already does; with the bases leading the question (and `versus last year` before the company), the year-over-year half is lost in the shared reading of words (`request_wording.py`, the comparison and change-base reading). Read both bases wherever they sit in the question.

Case: `h5_gr_gs_both` (both `sequential` and `year_over_year`); add phrase-coverage cases with the bases leading and trailing.

**Acceptance:** `uv run python -m pytest` passes; `uv run python scripts/compare_answers.py` names every conversation whose answer changes, and each change is intended; the case named is read right by the planner(s) that failed it (rules planner and the shared code: on the recorded runtime; the LLM planner: with a fake LLM planner proposing what the run's observation shows, so no test calls OpenAI).

**Blocked by:** None — can start immediately

**Status:** resolved

## Answer

Shipped 7 October 2026. `h5_gr_gs_both` passes every labelled field with the rules planner and with a stand-in LLM planner proposing what the run's observation shows (`tests/test_held_out_5_findings.py`); no test calls OpenAI.

The cause was not where the bases sat. On the recorded runtime `Goldman net interest income, sequentially or versus last year` failed the same way and `Sequentially or versus last year, Cisco revenue` passed: a question naming both bases was read as a quarter-over-quarter view, which adds the year-over-year change only where the year-earlier quarter is on screen. Cisco's five quarters give its newest one such row; the recording holds four Goldman quarters, so none. Recorded in `docs/process/rules-to-review.md`.

What changed:

- `names_both_bases` in `request_wording.py` reads both bases wherever they sit (`sequentially or versus last year`, `quarter over quarter and year over year`, `QoQ and YoY`); one base `instead of`, `rather than` or `not` the other is that base alone. The binder then adds a new `sequential` operation beside `year_over_year` (`SUPPORTED_OPERATIONS`, the LLM planner's `Operation` and follow-up prompt). With no window, 5 quarters as before.
- `merge_analysis` in `spec_turn.py` keeps the sequential change on when `sequential` is asked beside `year_over_year`, and `across_period_change_rows` takes each quarter's year-over-year change from its own comparative (ADR 0009) whenever year over year was asked, not only where the year-earlier quarter is on screen.
- Follow-ups: `sequentially or versus last year` after a window keeps the quarters on screen, reading the oldest one's base as `sequential instead` does; `year over year instead` drops the sequential change, `sequential instead` the year-over-year one, and `remove year over year` all three operations (`test_removing_year_over_year_takes_the_change_away_and_keeps_the_window` now expects `sequential` removed too).
- The rules planner no longer reads "Sequentially" or "QoQ and YoY" beside a list joiner as names it could not find (`_CHANGE_WORDS` in `_unfound_names`), so the cascade keeps its plan rather than sending the question on.
- Phrase coverage: `BOTH_BASES_QUESTIONS`, six cases under "Both bases" with the bases leading and trailing, each checked for both changes on every quarter; none sent to the model.
- README's changes row, CONTEXT.md's Comparison base entry and ADR 0010 say the rule. Set 5's case file says it is development data since this fix; `held-out-5-findings.md` gains "Fixed since the run"; `HeldOutSet(5)` is marked as having findings.

`uv run pytest`, ruff and mypy pass. `compare_answers` reports `3 of 344 conversations differ from HEAD`, all three added for this ticket: `Did Cisco's revenue grow sequentially or versus last year?` (one year-over-year row before, every quarter's now), `Goldman net interest income, sequentially or versus last year` (sequential only before, both now) and `Apple revenue over the last 6 quarters` then `sequentially or versus last year` (sequential only before, both on all six now). No held-out label was changed.
