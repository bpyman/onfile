# A well-known private company is named as private, not corrected to a listed one

From the product review (follow-up bugs) and the offline probe. With the live snapshot's index (`rules_planner.issuer_index()`, which the live runtime uses), "Stripe revenue" is corrected to Stride ("Showing Stride for “stripe”"), a different, listed company. On the recorded runtime, "Stripe revenue" and "OpenAI revenue" both get "I couldn't tell which company you mean…", which never says why.

**Files (this ticket only):** a new data file `src/financial_analyst_agent/data/private_companies.json`, `src/financial_analyst_agent/issuer_index.py` or `rules_planner.py` (wherever the name correction runs, so the check comes before it), `src/financial_analyst_agent/guide.py` for the reply, tests.

**What to build:** A short, hand-kept list of well-known private companies an analyst might ask about: Stripe, OpenAI, Anthropic, Databricks, ByteDance, Shein, Epic Games, Cargill, Mars, Koch Industries, Bloomberg, Fidelity Investments, Chick-fil-A, Valve, Revolut, Klarna if it is not in the snapshot. Check each against `universe_snapshot.json` and `sec_filer_names.json`: a company in the snapshot is public here and must not be on the list.

When a question names one of them and no listed company, reply in the guide's voice: "Stripe is a private company: it files no reports with the SEC, so there are no figures to show." Add suggestions as the not-found reply does. The name is matched exactly (case-insensitive, word boundaries) before any spelling correction, so "Stripe" is never corrected to Stride. Beside a listed company ("Compare Visa and Stripe revenue"), the listed company is answered and a note names the private one, as a fund beside a company is left out with a note (`answer_notes.fund_note`).

**Acceptance:**
- Tests on the live index (`issuer_index()`, offline) and the recorded runtime cover:
  - "Stripe revenue" → the private reply, never Stride;
  - "OpenAI revenue" → the private reply;
  - "Compare Visa and Stripe revenue" → Visa with a note on the live index; whatever the recorded runtime says of Visa, plus the note.
- No list entry is in the universe snapshot (a test that reads both files).
- `compare_answers.py --against master` lists only conversations naming a listed private company; name them in the Answer.

**Blocked by:** None — can start immediately

**Status:** ready-for-agent
