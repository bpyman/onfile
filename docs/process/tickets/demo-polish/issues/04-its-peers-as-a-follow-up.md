# "Compare to its peers" as a follow-up adds the peers, not a company called "its peers"

From the product review (follow-up bugs). On the recorded runtime:

- "Nvidia revenue" then "compare to its peers" shows Nvidia, plus a row named "its peers" reading "Company not found".
- "Nvidia gross margin" then "compare it with its peers" is refused: "I couldn't find a metric I can look up in that question…".

Asked fresh, "Compare Nvidia to its peers" works: the rules planner sets `peers=True` (`rules_planner.py`, `_PEERS`), and the conversation adds the largest companies in Nvidia's industry (`graph/turn_graph.py`, `with_peers`).

**Files (this ticket only):** `src/financial_analyst_agent/rules_planner.py` (the follow-up path, `_follow_up`, and `_PEERS`), `src/financial_analyst_agent/graph/turn_graph.py` if the peers expansion needs to reach a follow-up, `src/financial_analyst_agent/planner.py` only if the follow-up schema needs a peers field (no prompt wording change; if one looks needed, hand back as needs-info), tests.

**What to build:** A follow-up that asks for a company's peers ("compare to its peers", "compare it with its peers", "add its peers", "how does it stack up against peers?"), with one company on screen, adds that company's peers to the analysis on screen. It keeps the metric and window, as "add Microsoft" would. With several companies on screen, say which one's peers is unclear and ask, or hand back as needs-info if that needs a design decision. "Peers" must never be read as a company name.

**Acceptance:**
- Both conversations above end with Nvidia and its peers on the same metric, pinned by conversation tests in `tests/test_says_what_it_cannot_do.py` beside `test_compare_to_peers_adds_peers`.
- No row named "its peers" or "peers" can appear (a test).
- `compare_answers.py --against master` lists only peers follow-ups; name them in the Answer.

**Blocked by:** None — can start immediately

**Status:** ready-for-agent
