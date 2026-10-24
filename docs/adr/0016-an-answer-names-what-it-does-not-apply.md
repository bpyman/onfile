# An answer names the parts of a question it does not apply

A product review on 23 October 2026 asked the public demo "Which software companies grew revenue more than 20% year over year while staying profitable?". It answered with the ten largest software companies by market value and their revenue growth. Three grew less than 20%, and nothing said the conditions had been dropped. Offline, about 165 analyst questions found the same pattern elsewhere:

- "Microsoft FCF yield" showed free cash flow.
- "Broadcom 5-year revenue CAGR" showed one quarter's revenue.
- "Nvidia's next earnings date" showed net income.
- "Apple EPS analyst estimates" showed reported EPS.
- "How has Nvidia stock performed this year" showed an overview.
- "Share of Apple revenue from China" showed total revenue.
- "Rank semis by revenue growth" was ordered by revenue.
- "…and tell me why it grew" dropped the why.

Each looked like a full answer. The cascade (ADR 0012) did not help, because the rules plan looked complete. And where a question did reach the model, the plan has no field for a condition, so the model could not express it either.

## Decision

- **What filings do not hold is an unknown measure, refused by name (ADR 0004).** The catalog's unknown measures now include:
  - **figures built on a catalog metric that are not that metric:** free cash flow yield, earnings yield, compound annual growth;
  - **figures not in a 10-Q at all:** earnings dates and calls, analyst estimates, price targets and ratings, institutional ownership, insider trades, short interest, stock performance, beta, volatility.

  Asked alone, each is refused by name, as "debt" already was. The longest phrase wins, so "FCF yield" is not "FCF". Each phrase must say what it is by itself: "analyst estimates" and "stock beta", not "estimate" or "beta", which are ordinary words ("estimate Apple's revenue", "beta products").
- **Words the answer cannot act on are named in a note above it, in the analyst's own words, whichever planner read the question.** `answer_notes.unapplied_notes` reads the message against the resolved spec. Its notes lead the answer, as a corrected company name's does. It names:
  - **an unknown measure beside one the catalog has** ("Apple revenue and dividend yield" is revenue, and says dividend yield was left out);
  - **conditions on a ranking:**
    - a threshold ("above 20%", "between $5B and $20B");
    - a quality ("profitable", "pay dividends", "small-cap");
    - an index ("S&P 500");
    - a place;
  - **a ranking asked to be ordered by growth**, which is ordered by the figure;
  - **one figure as a share of another**, outside the catalog's ratios;
  - **a region**, outside a ranking;
  - **a "why"** inside a figures question.
- **A screening word is not part of a ranking's group.** "Profitable banks" ranks banks, and the note names "profitable". The planner no longer refuses it as a group the snapshot does not know. "Large-cap" is dropped with no note, because the largest companies are what a ranking shows.
- **The note is not a reason to call the model.** The cascade's unsure reasons are unchanged. The LLM planner cannot express a condition either, so it would cost a call to reach the same plan.

## Consequences

- A visitor sees what was not done before reading what was. Replaying every recorded conversation against master, three of 893 change, each by gaining a note:
  - "How does Apple's buyback affect its EPS?" now says buybacks are left out.
  - "top 5 banks by revenue growth" says it is ordered by revenue.
  - "What caused Apple's revenue to fall since 2023?" says the why is not answered.
- Four questions that answered with the wrong figure now refuse instead: FCF yield, earnings dates, institutional ownership and stock performance.
- The words are read by patterns, as the rest of the shared reading is (ADR 0010). A condition phrased in a way no pattern knows is still dropped without a note. Those found should be added to the patterns.
- Screening, ordering by growth, regions, and figures divided outside the catalog's ratios remain unbuilt. Each, once built, removes its note.

## Considered options

- **Send any question with leftover words to the LLM planner.** It costs a call per question, and the plan contract has no place for a condition, so the model's plan drops it too.
- **Refuse any question with a condition.** It is honest, but it withholds the figures a visitor can use. The largest companies with their growth, with the condition named, is a usable answer to "which grew more than 20%?".
- **One general "words I did not use" check that subtracts every word a plan accounts for.** It would catch phrasings the patterns miss. But the rules planner does not record which words it used, and the model planner cannot. An approximation would flag ordinary wording on most answers, and a note on every answer stops being read.
