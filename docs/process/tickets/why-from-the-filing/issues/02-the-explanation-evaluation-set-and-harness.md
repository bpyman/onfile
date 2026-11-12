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

**Status:** resolved

## Answer

Shipped `explanation_evaluation.py` with four subcommands, all offline; none calls a model.

- **`cases`** draws the set and writes `docs/evaluation/explanation-cases.json` (seed `20261023`).
  - The pool is every recorded company whose latest 10-Q document is recorded (21), crossed with the 15 metrics `explanation.py` has words for. A pair stays in only where the recorded runtime's facts hold that metric for that quarter, because the panel follows a figures answer: a bank's gross margin is never asked. 40 pairs are drawn from that pool.
  - Bases are shuffled 20 year over year and 20 sequential. Within each basis, the first ten drawn are `dev` and the next ten `held-out`, so each set has 10 of each.
  - The figures come from the recorded runtime's own lookup (`SecFactLookup.get_financials`), through the formula components for ratios. Year over year uses the filing's comparative (ADR 0009); sequential uses the quarter before.
  - The verb follows the recorded direction ("rise"/"up", "fall"/"down"). A case with no direction would get neutral wording, but all 40 drawn have one. Each case stores the latest figure and the one it is compared with.
  - Questions use three templates: "Why did …", "What drove … up/down …" and "What caused … to rise/fall …". Each names the basis ("year over year", "sequentially").
- **`candidates`** writes `docs/evaluation/explanation-candidates.json`. For each case it holds the top three paragraphs from `management_explanation` (score, rank, causal clause, link), the baseline (the MD&A's first paragraph naming the metric), the accession and the reason when nothing is found. Each distinct paragraph gets an id (`e07-p2`), so the judge labels it once; the baseline reuses a scored paragraph's id when it is the same text.
- **`brief`** prints `explanation-rubric.md` without its Changes section. `brief --case e07` prints the filled prompts for one case: one per paragraph, and one with the whole MD&A for `nothing_to_find`. `paragraph_prompt` and `mda_prompt` are there for ticket 03's runner.
- **`score --labels <file>`** reads `{"judge": …, "labels": {case: {"nothing_to_find": bool, "explains": {paragraph id: bool}}}}`. It writes `docs/evaluation/explanation.md` with these figures, per set and overall, for the scoring and the baseline:
  - precision at 1 and at 3;
  - how often "nothing found" was right;
  - every first-place paragraph that code reads as being about another metric.

  A paragraph shown without a label is an error. No report is committed, because there are no labels yet.

Precision at k follows the design's label: of the cases shown at least one paragraph, the share where one of the first k states a cause. It is a hit rate at k, not the precision of the k paragraphs. A reviewer may want the other reading.

What the committed candidates show before any label:
- **Nothing found:** 9 cases (4 dev, 5 held-out), 5 of them sequential.
- **First places code reads as about another metric:** 3 (e05 Micron net margin and e10 Tesla net income, which open on cash-flow paragraphs; e19 AMD net income, which opens on the operating-income paragraph that also says net income rose on operating income). Under the design's bar these fail, which points ticket 03's tuning at whether a demoted paragraph should ever be shown first.

Rubric for review: `docs/evaluation/explanation-rubric.md`.
- The hard constraints are stated outright: answer only from the paragraph shown, restating a change without a cause is no, and only the JSON object comes back.
- Choices the owner should check:
  - A cause given for a segment, product or region, or for one of a figure's parts (operating cash flow for free cash flow), counts as `explains: true` with `scope: "part"`, so the two kinds can be counted apart.
  - A margin and its amount count as one subject.
  - A cause stated only for the other basis or only for the year to date is no.
  - Sequential questions will often have nothing to find, since 10-Q MD&As mostly compare against the year-earlier quarter.

compare_answers reports 0 of 893 conversations differ.
