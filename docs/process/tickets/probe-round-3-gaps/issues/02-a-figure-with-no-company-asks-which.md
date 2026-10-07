# 02 — "What was net income this quarter?" asks which company

**What to build:** Found by the set-5 brief's probe round 3 (7 October 2026): Claude's probes, written blind from the brief and scored against the recorded runtime. Judged by the README's "How a question is read". The fix belongs in the shared reading of words both planners pass through (ADR 0010, 0011), not in the rules planner alone, except where the ticket says the rules planner. `what was net income this quarter?` is refused: "Company not found for query 'net'". The rules planner's lookup fallback (`_lookup_company` and `_issuer_from_lookup_query` in `rules_planner.py`) takes a word of the metric phrase for a company name. The README says a figure with no company asks which company, and `free cash flow last quarter?` and `what's the operating margin?` already do: "I couldn't tell which company you mean. Name one or its ticker". A word that belongs to the question's metric phrase (`net` in `net income`, `free` in `free cash flow`, `operating` in `operating margin`) is never a company name; with no other company named, the turn asks which company.

**Acceptance:** `what was net income this quarter?`, `net margin last quarter?` and `what was net interest income?` ask which company, as `free cash flow last quarter?` does, on the recorded runtime; a question that does name a company (`Apple net income`) is unchanged; add them to phrase coverage's no-company cases. `uv run python -m pytest` passes; `uv run python scripts/compare_answers.py` names every conversation whose answer changes, and each change is intended.

**Blocked by:** None — can start immediately

**Status:** ready-for-agent
