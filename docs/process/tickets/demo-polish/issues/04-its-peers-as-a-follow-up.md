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

**Status:** resolved

## Answer

A peers follow-up adds the peers to the analysis on screen, keeping its metric and window, whichever
planner read the words:

- The peers wording moved from `rules_planner._PEERS` to `request_wording.PEERS`, shared by the
  rules planner, the turn graph, the edit reading and the guide.
- `rules_planner._follow_up`: peers wording that names no company, with companies on screen, is an
  extend edit (no longer a compare plan with no company, refused for its metric, or a company called
  "its peers"). "Compare NVIDIA to its peers" is planned as it is fresh.
- `turn_graph.with_peers(proposal, ranking, message, spec)`: with companies on screen and peers
  wording, `_peers_follow_up` turns the proposal into an extend patch adding the largest companies
  in the industry (three, as fresh) of the one company on screen, or of the one company the words
  name when it is on screen or the proposal is already an edit. A new question naming a company not
  on screen ("Apple revenue", then "Compare Nvidia to its peers") stays the fresh peers question.
- `request_wording._refine_against`: peers wording never reads a company from the words ("compare
  to its peers", "add its peers"); a company the planner proposed whose name is peers wording is
  dropped. The mode is kept.
- Several companies on screen and none named ("Nvidia and AMD revenue", then "compare to their
  peers"): the guide asks whose peers, with one suggestion per company ("compare NVIDIA to its
  peers", …), each of which adds that company's peers to the table (`guide.PEERS_MESSAGE`).

Outside the file list: `request_wording.py` (where "compare to X" and "add X" read X as a company)
and `guide.py` (the whose-peers reply); recorded in `docs/process/rules-to-review.md`. No planner
schema or prompt changed.

Tests in `tests/test_says_what_it_cannot_do.py` beside `test_compare_to_peers_adds_peers`:
`test_its_peers_as_a_follow_up_adds_the_peers` (both conversations of the ticket, plus "add its
peers", "how does it stack up against peers?" over 4 quarters and "compare to peers": the same
tickers as the fresh question, the metric and window on screen, no row named "its peers" or "peers",
no "Company not found") and `test_peers_with_several_companies_on_screen_asks_whose`.

`compare_answers.py` (against HEAD, the previous commit): 0 of 893 conversations differ; none of the
replayed conversations is a peers follow-up.
