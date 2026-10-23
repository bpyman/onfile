# "Apple 10-K" is about the filing, not a metric called "K"

From the product review (follow-up bugs). On the recorded runtime, "Apple 10-K" and "Apple's latest 10-K" are refused: "I can't look up “K” yet. I answer from 10-Q figures such as…". The form name was split, "10" read as a number and "K" as the unknown measure (`rules_planner._unknown_term`).

**Files (this ticket only):** `src/financial_analyst_agent/rules_planner.py`, `src/financial_analyst_agent/request_wording.py` if the form words belong there, tests (`tests/test_says_what_it_cannot_do.py`, `tests/unit/test_planner_rules.py`).

**What to build:** A form name (`10-K`, `10-Q`, `8-K`, `20-F`, `annual report`, `quarterly report`) is never read as a metric or an unknown measure.

- A company plus a form name with no metric and no change words ("Apple 10-K", "Apple's latest 10-K", "show me Microsoft's 10-Q") should get an answer that helps. Prefer the guide's suggestions for that company, naming what it can show from that filing: "what changed in Apple's latest 10-K", its revenue, an overview. Use whatever reply mechanism `guide.py` already has. Do not invent a new intent.
- An 8-K or 20-F, which the app does not read, says so plainly.
- "What changed in Apple's latest 10-K" keeps its filing-change answer.

**Acceptance:**
- "Apple 10-K" and "Apple's latest 10-K" no longer mention “K”, pinned by tests.
- "What changed in Apple's latest 10-K" is unchanged.
- `compare_answers.py --against master` shows only form-name conversations changing; name them in the Answer.

**Blocked by:** None — can start immediately

**Status:** ready-for-agent
