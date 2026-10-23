# The explanation evaluation: cases and a harness that writes what the judge labels

Spec: `design.md` "Evaluation (before Phase A ships)". The labels themselves come from a claude-opus-5-5 judge run by a person (ticket 03), never by this ticket: no model is called here.

**Files (this ticket only):**
- `docs/evaluation/explanation-cases.json` (new);
- `src/financial_analyst_agent/explanation_evaluation.py` (new), with the subcommands below;
- `tests/unit/test_explanation_evaluation.py` (new).

**What to build:**

1. **Cases chosen by code, not by hand.**
   - Start from every recorded company whose latest 10-Q is in `filing_documents`, crossed with the metrics `explanation.py` has words for.
   - Draw 40 pairs with a fixed seed. Give each a basis (half year over year, half sequential) and a question in everyday wording, from a few templates: "Why did {company}'s {metric} {rise/fall} last quarter?", "What drove {company}'s {metric} this quarter?", and "What caused …".
   - Pick the verb from the recorded figures' actual direction where the recorded facts give it, so a question never asks why something rose when it fell.
   - Split the cases 20 development and 20 held-out (field `set`), and write them to the JSON with the seed.
2. **`explanation_evaluation candidates`** writes `docs/evaluation/explanation-candidates.json`:
   - for each case, the top three paragraphs `explanation.py` returns, with their scores;
   - the baseline: the first MD&A paragraph that mentions the metric's words;
   - the accession number.

   It is deterministic and offline.
3. **`explanation_evaluation score --labels <file>`** reads judge labels: for each case and each paragraph, `explains` true or false, and for each case `nothing_to_find` true or false. It writes `docs/evaluation/explanation.md` with:
   - precision at 1 and at 3, for the scoring and for the baseline, per set;
   - how often "nothing found" was right;
   - every first-place paragraph that is about another metric.
4. **`explanation_evaluation brief`** prints the judge's instructions, built from `docs/evaluation/explanation-rubric.md`. Write that rubric too. It should be a short brief to a careful equity analyst:
   - The judge sees the question, the metric, the basis and one paragraph.
   - It answers whether the paragraph states a cause of that metric's move in that quarter on that basis. Restating the change without a cause is no.
   - It answers in JSON.

   The rubric is shown to Blake before any judge run (ticket 03).

**Acceptance:**
- Unit tests: the case draw is reproducible from the seed; no question's verb contradicts its recorded direction; `score` computes precision at 1 and 3 correctly on a small hand-made label file.
- `candidates` runs offline, and its output is committed.
- pytest, ruff and mypy are clean; `compare_answers.py` reports 0 differences.

**Blocked by:** 01

**Status:** ready-for-agent
