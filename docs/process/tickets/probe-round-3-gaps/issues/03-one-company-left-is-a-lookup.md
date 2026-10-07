# 03 — One company left on screen is a lookup

**What to build:** Found reviewing probe round 3's doubts (7 October 2026): a question a doubt raised, asked on the recorded runtime, does not do what the README's "How a question is read" now says. The fix belongs in the shared reading of words both planners pass through (ADR 0010, 0011), except where the ticket says otherwise. `SPY and Apple revenue` drops SPY (a fund) and answers Apple's revenue, but its intent is `compare`. The README (and the brief's labelling rule) say the intent follows the companies on screen: one is a lookup, several a comparison. `compare Google and Alphabet revenue` already collapses to one company and is a lookup. Make a comparison that ends with one company on screen, after unresolved or dropped names, a lookup.

**Acceptance:** `SPY and Apple revenue` is intent `lookup` with AAPL; `Apple and Microsoft revenue` is still `compare`. `uv run python -m pytest` passes; `uv run python scripts/compare_answers.py` names every conversation whose answer changes, and each change is intended.

**Blocked by:** None — can start immediately

**Status:** ready-for-agent
