# Name the parts of a question an answer does not apply

Status: resolved

**What to build:** An answer that drops part of a question must say so, whichever planner read it ([review](../review.md), Tier 1 item 1). The live demo answered a screen ("software companies that grew revenue more than 20% while staying profitable") with the largest software companies, three of which grew less than 20%, and said nothing. FCF yield, CAGR, earnings dates, analyst estimates, stock performance, regions, ranking by growth and a mid-sentence "why" were dropped the same way.

**Acceptance criteria:**

- **Refused by name.** A question about something filings do not hold (FCF yield, earnings dates, institutional holders, stock performance) is refused by name, not answered with another figure.
- **Unknown measures beside known ones.** Beside a catalog metric, an unknown measure is named in a note, and the catalog metric is answered.
- **Ranking conditions.** A ranking names each condition it does not screen by: a threshold, a quality, an index or a place. A screening word ("profitable banks") is not read as part of the group.
- **Other parts.** A ranking by growth says it is ordered by the figure. A region, a share of another figure, and a "why" each get a note.
- **Both planners.** A model-planned turn gets the same notes.
- **Replay gate.** Every recorded conversation is replayed against master, and only answers to such questions change.

## Answer

[ADR 0016](../../../../adr/0016-an-answer-names-what-it-does-not-apply.md).

**What changed:**
- **`metric_catalog`:** unknown measures for yields, compound annual growth, earnings dates and calls, estimates, price targets, ratings, ownership, insider trades, short interest, stock performance, beta and volatility.
- **`answer_notes.unapplied_notes`:** the notes, led into the answer from `spec_turn.annotate_analysis`.
- **`ranked_wording`:** screening words are dropped from a group's name.

**Tests:** `tests/test_says_what_it_cannot_do.py` (parts of a question the answer cannot act on) and `tests/unit/test_unapplied_notes.py`.

**Replay:** 3 of 893 recorded conversations change, each by gaining a note.
