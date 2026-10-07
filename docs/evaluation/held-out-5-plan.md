# Plan: the fifth held-out set's run

This plan is committed before any set-5 case exists, as the cascade and the
significance test were before set 4's run. It fixes what will be run, what will
be reported, and in what order, so nothing is chosen after seeing a result. A
change to it after the cases exist is listed at the end with the reason, and
says whether any result had been seen.

## Before the cases are written

1. **Probe rounds.** Rounds 1 and 2 ran on 6 October 2026: 30 throwaway probes
   each, labelled blind from the draft brief. The app agreed with 26 and then 24
   of them; each round's doubts and disagreements went into the brief, the
   README's "How a question is read", and tickets (`brief-5-probe-gaps`). A third
   round runs on the brief as it will be frozen, in two parts, each in a folder
   holding only the files the brief lets a writer read:
   - **The brief's clarity:** the case writer (Grok 4.7) writes probes and its
     doubts about the rules. Only the doubts are read, to make the brief and the
     README clearer; its probe questions are not scored against the app, so no fix
     is tuned to the phrasing of the model that writes the set.
   - **App gaps:** another lab's model (Claude, which wrote rounds 1 and 2) writes
     probes that are scored against the app, and the gaps they find are fixed
     before the freeze.

   It stops the probing if it finds no error in the brief and at most two app
   gaps; otherwise the brief's unclear parts are rewritten before freezing, not
   probed again. The Protocol records how many probe rounds ran, which model wrote
   them, and what they changed. The probes are discarded, and none is a case.

   Round 3 ran on 7 October 2026. Grok 4.7 wrote 30 probes and 62 doubts (the
   probes unscored); Claude wrote 30 probes, of which the app agreed with 28, and
   27 doubts. The doubts found four contradictions between the brief and the
   README (segments, periods before 2015 against `since` windows, an overview's
   period, a trailing-year figure's period), so the stopping rule ended the
   probing: the brief and the README were rewritten, with about 15 rules the app
   already followed written down, and the app gaps the round found were fixed
   (`probe-round-3-gaps`, eleven tickets, #94).
2. **Freeze.** The draft note is removed from
   [`held-out-5-brief.md`](held-out-5-brief.md); that commit is the frozen prompt.
   No planner or reading code changes from the freeze until the run. Frozen on 7
   October 2026, in the commit titled "Freeze the fifth held-out brief".
3. **Writer** (decided 6 October 2026): **Grok 4.7** (`grok-4.7-high`), xAI's,
   through the Cursor agent CLI, writes and labels all 150 to 170 cases from the
   frozen brief alone, and names itself in the file's `writer`. It is a third
   lab's model: sets 1 to 4 were written by Claude, whose models also wrote the
   rules planner, and the LLM planner is OpenAI's, so neither planner shares the
   writer's habits of phrasing. It runs in a folder holding only the frozen brief
   and the files the brief lets a writer read, so it cannot search the
   repository. Set 5 is therefore not written like set 4, which is one more reason
   the two sets are compared only descriptively (step 10).

## After the cases, before any planner runs

4. **Commit the cases** to `planner-cases-held-out-5.json`, with `cases_commit`
   left to be set by the next step's commit. The engineer checks format and counts
   only.
5. **Second labeller.** A blind Claude session labels the same questions from the
   frozen brief alone, in the same kind of isolated folder, without seeing the
   first labels. `uv run python -m
   financial_analyst_agent.held_out_overlap --labels <cases> <second labels>`
   compares the two field by field. Where they disagree, a person settles the
   label against the README, `CONTEXT.md` and the ADRs as committed at the freeze,
   records each settled label in the case file's `label_changes` with "settled
   before the run" and the rule, and reports the agreement rate per field. This is
   a check on the labels, not an adjudication: no planner has run.
6. **Overlap.** `uv run python -m financial_analyst_agent.held_out_overlap
   --probes <round-3 probe files>` writes `held-out-5-overlap.json` and `.md`:
   the cases that share a template with development cases, phrase coverage or the
   probes. Nothing is removed.
7. **Commit** the settled labels and the overlap report together; that commit is
   the file's `cases_commit`. Set 4 becomes development data from here
   (`planner_evaluation.current_held_out`).

The person settling labels in step 5 reads those cases; this is why no planner or
reading code may change between the freeze and the run.

## The run

8. **Estimate.** `uv run python -m financial_analyst_agent.planner_evaluation
   --estimate --runs 3 --input-price 2 --output-price 12 --paid-split held_out
   --no-write`; only the cost line is read.
9. **Run** the rules planner on every case, and the LLM planner (`gpt-5.6-terra`)
   and the cascade on the held-out cases, three runs each:
   `--planners rules,llm,cascade --runs 3 --input-price 2 --output-price 12
   --budget-usd 5 --paid-split held_out`. A budget that runs out leaves the
   incomplete run out, as the report already does.

## What is reported

10. **Primary:** each planner's held-out accuracy as labelled, with its 95%
    Wilson interval. It is set beside set 4's (rules planner 85%, 74%–92%; LLM
    planner and cascade 88%, 78%–94%, on 66 cases) as a description only: the
    sets hold different questions, so no test is run across them.
11. **Between planners:** the exact McNemar test for each pair on the held-out
    cases as labelled, a case counting once (passed in at least half its runs).
12. **Secondary, never in place of the primary:**
    - after adjudication, under the Protocol's rule (a product rule committed
      before the cases, quoted with its commit and file, checked by
      `check_rule_history`);
    - familiar and novel cases (step 6);
    - field accuracy, agreement across runs, time and cost;
    - the label agreement rate (step 5).
13. **Findings.** Every case that failed at least one planner is read after the
    run and written up in `held-out-5-findings.md` as set 4's were: planning
    error, shared defect, or a label that disagrees with a design decision. No
    label changes to fit a result; adjudications follow the Protocol.

After the run, set 5 is development data like every set before it.

## Changes to this plan

- After the run (7 October 2026), the report gained a line showing the held-out
  scores by group (familiar and novel). The figures were computed by the
  evaluation code committed before the cases; only their rendering was missing,
  and no planner was run again (`--from-json`). Results had been seen.
