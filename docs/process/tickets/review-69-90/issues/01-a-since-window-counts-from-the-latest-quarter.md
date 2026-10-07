# 01 — A "since" window counts the quarters filed, not the calendar

**What to build:** Found by the two-axis review of PRs #69-#90 (6 October 2026), spec axis. The README says `since 2024` is "every quarter since that calendar year began". `since_quarters` (`request_wording.py`, about line 742) counts from `date.today()`, so on 6 October 2026 `since 2024` asks for 12 quarters, though the latest filed quarter ends in June 2026. On the recorded runtime, `Apple revenue since 2024` then says "The filings here hold only 9 of the 12 quarters asked for", which is false: it holds every quarter since 2024. The count also moves with the calendar, so recorded answers drift from day to day, and no test fixes the date.

Read a `since` window as every filed quarter that ended on or after 1 January of that year, resolved where the companies' report dates are known (as a named period is), not as a count fixed when the words are read. Keep the 40-quarter cap and its note. A window note says a quarter is missing only when the filings lack one inside the span.

**Acceptance:** `Apple revenue since 2024` on the recorded runtime shows every recorded quarter since January 2024 and no "only N of M" note; the same question gives the same quarters whatever today's date is (a test that sets the date to two different days); `since 2000` is capped at 40 with its note. `uv run python -m pytest` passes; `uv run python scripts/compare_answers.py` names every conversation whose answer changes, and each change is intended.

**Blocked by:** None — can start immediately

**Status:** ready-for-agent
