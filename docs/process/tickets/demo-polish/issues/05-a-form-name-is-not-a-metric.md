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

**Status:** resolved

## Answer

The form words live in `request_wording`: `FORM_NAME` (10-K, 10-Q, 8-K, 20-F, with or without the
hyphen, and "annual report" / "quarterly report"), `form_label` (the form as the SEC writes it; an
annual report is a 10-K, a quarterly report a 10-Q) and `reads_form` (not 8-K or 20-F).

- `rules_planner._unknown_term` drops form names before it looks for the unknown measure, so no
  question reads "K", "Q" or "F" as a metric (`tests/unit/test_planner_rules.py`,
  `test_a_form_name_is_not_an_unknown_measure`).
- `guide.guide_reply` gets one branch (`_form_reply`), with the guide's existing reply mechanism
  (no new intent), before either planner reads the question:
  - A company and a 10-K or 10-Q with nothing else asked ("Apple 10-K", "Apple's latest 10-K",
    "show me Microsoft's 10-Q", "Apple annual report"): "I don't show a 10-K on its own, but I can
    read Apple's filings: what changed in its latest 10-K, the figures it reports such as revenue,
    or an overview of how it is doing.", suggesting "What changed in Apple's latest 10-K?", "Apple
    revenue last 4 quarters" and "How is Apple doing?". Words beyond the company, the form and
    filler ("show me", "latest", …) leave the question to the planner.
  - An 8-K or 20-F with no figure asked: "I don't read 8-Ks. I answer from 10-Q and 10-K filings,
    the quarterly and annual reports US companies file with the SEC.", with the company's
    suggestions where the index names one.
  - "What changed in Apple's latest 10-K" is untouched (it names a change), pinned by
    `test_what_changed_in_a_10_k_keeps_its_filing_change_answer`.

Pinned in `tests/test_says_what_it_cannot_do.py` (`test_a_form_name_is_about_the_filing_not_a_metric`,
`test_a_form_the_app_does_not_read_says_so` for "Apple 8-K" and "Toyota 20-F").

"Apple quarterly report" changes too: it showed the overview, and now gets the same reply as "Apple
10-Q", as a form name with nothing else asked.

`compare_answers.py` (against HEAD, the previous commit): 0 of 893 conversations differ; none of the
replayed conversations names a form without a change.
