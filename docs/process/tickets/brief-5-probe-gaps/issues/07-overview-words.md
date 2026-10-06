# 07 — "The rundown" and "how is X performing" ask for the overview

**What to build:** `Give me the rundown on how Wells Fargo is performing` is refused as an unknown metric ("rundown"). `How is X doing?` gives the overview; so should `how is X performing`, `how has X been performing`, `the rundown on X`, `a quick read on X` and `X's performance` (README, overview row). `_OVERVIEW` in `request_wording.py` holds the overview words.

Add these as phrase-coverage cases expecting the overview's metrics for the company.

Found by the set-5 brief's probe dry-run (6 October 2026, second round): a blind session labelled 30 throwaway probes from the draft brief and the README, and the app disagreed. Judged by the README's [How a question is read](../../../../../README.md#how-a-question-is-read). The fix belongs in the shared reading of words both planners pass through (ADR 0010, 0011), not in the rules planner alone, except where the ticket says the rules planner.

**Acceptance:** the cases below are read right; any phrase-coverage case named is taken off `KNOWN_GAPS`; `uv run python -m pytest` passes; `uv run python scripts/compare_answers.py` names every conversation whose answer changes, and each change is intended.

**Blocked by:** None — can start immediately

**Status:** resolved

## Answer

Shipped 2026-10-06.

`_OVERVIEW` in `request_wording.py`, the shared reading of words that ask how a company is doing, gains `rundown` (and `run-down`), `quick read`/`quick look`/`quick take`, `perform`/`performs`/`performed`/`performing`/`performance`, and `how has`/`how have`/`how were` beside `how is`/`how are`/`how was`. `Give me the rundown on how Wells Fargo is performing`, `How has Wells Fargo been performing?`, `the rundown on Apple`, `a quick read on Apple` and `Wells Fargo's performance` all give the overview (revenue, net income and three margins for the latest quarter); `Apple's performance over the last 4 quarters` gives it for those quarters. The rules planner's unknown-word reading (`_unknown_term`) already defers to the shared words, so it no longer names `rundown` or `quick read` as the metric; the rules planner itself is unchanged.

Two guards came with the words:

- `bind_metrics_from_message` implies no metrics when the catalog names a measure it lacks (`resolved.term`), so `Apple's stock performance` is still refused by name, whether the planner proposed `stock performance` or nothing. Before, a three-word question with an unknown measure got the overview from the short-message rule when the planner proposed nothing.
- `_UNKNOWN_MEASURES` in the catalog gains `remaining performance obligations` (and `remaining performance obligation`, `RPO`), so `Oracle remaining performance obligations` is refused naming the measure rather than read as an overview through `performance`. Its refusal now comes from the guide and names the full measure (before: "remaining obligations", from the rules planner's leftover words).

Phrase coverage gains the group "Overviews" (`OVERVIEW_QUESTIONS`, 10 cases: the ticket's phrasings for Wells Fargo and Apple, a two-company rundown, and the windowed form), each expecting the five overview metrics for the named companies. These are listed in `SENT_TO_MODEL`: an overview lookup names no catalog metric, so the rules planner is unsure of it and the live cascade sends it to the LLM planner, as it already did for `How is Apple doing?`; the shared reading gives the overview whichever planner proposed no metric, and the LLM planner's prompt tells it to propose `overview` for one. `UNKNOWN_MEASURE_QUESTIONS` gains `Apple's stock performance`, `Oracle remaining performance obligations` and `Oracle RPO`. Nothing was on `KNOWN_GAPS` for this ticket; it stays empty.

Checks: 2,006 tests pass; ruff and mypy pass. `compare_answers` reports 1 of 244 conversations differ, intended: `case:h3_orcl_rpo` (`Oracle remaining performance obligations`) still refuses, now naming "remaining performance obligations" through the guide with Oracle's own suggestions, where before it said "remaining obligations". Its evaluation label (refuse) holds.

Also read as an overview now, with no recorded conversation affected: `Apple segment performance` (before: refused the unknown metric "segment"), and `How is Apple's stock performing?` (unchanged: `how is` already gave the overview).
