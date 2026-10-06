# 05 — Read the filing change's form, sections and accessions once

**What to build:** `filing_change.run_filing_change` re-reads the raw question: accession numbers override the plan's (`_accessions_from_query`), the question's sections override the plan's (`requested_sections`, else `parse_sections` substring-matches the plan's free-text section), and the form (10-K or 10-Q) comes only from the question (`_form_asked`). `FilingChangeRequest` has no form field, so the LLM planner cannot express one; it works only because the question is read again.

Bind typed `sections`, `form` and accessions once, in `turn_graph.request_from_proposal`, from the shared wording (ADR 0010, 0011); give `WorkflowPlan` and the LLM's filing-change action a `form`; the workflow reads the request only.

**Why a person:** it changes the LLM planner's schema and prompt, so it needs a paid LLM check of the filing-change cases.

**Acceptance:** filing-change questions answer as before on both planners; `uv run python scripts/compare_answers.py` reports `0 of N conversations differ`: what the recorded demo answers does not change.

Found by the 2026-10-04 simplify review of master (#67), which left it out as larger than a cleanup.

Spec: ADR 0010, ADR 0011.

**Blocked by:** None — can start immediately

**Status:** resolved

## Answer

Shipped 2026-10-05. `filing_change.bind_filing_change` builds the
`FilingChangeRequest` once, in `turn_graph.request_from_proposal`, from the
planner's plan and the question's words, words first (ADR 0010):

- `older_accession` / `newer_accession` and `named_accessions`: the accession
  numbers the question gives (a plan's own are used only without a question,
  as an MCP call has none);
- `sections`: `requested_sections(question)`, else the plan's section text;
- `form`: `form_named(question)` (10-K or annual report; 10-Q or quarterly
  report), else the plan's `form`, else 10-Q.

`run_filing_change(request, runtime)` reads only the request, and its refusals
read `named_accessions`. `WorkflowPlan` and the LLM planner's filing-change
action gain `form`, and the LLM prompt says to set it to 10-K for an annual
report. The rules planner sets it with the same `form_named`.

Paid check (about $0.07): eight filing-change questions on both planners, on
master and on this change: latest 10-Q, latest 10-K, "differs from the one
before", MD&A between two accessions, risk factors in a quarterly report, a
summary, an annual report, and MD&A excluding risk factors. 15 of 16 answers
were identical. The one difference was the LLM planner asking for a summary
on master and not here, for "What changed in Pfizer's risk factors in its
latest quarterly report?"; asked three times more, it set `summarize`
inconsistently on master too (no, yes, yes; here yes, yes, yes). That is the
model's own variance on a field this change does not touch; the live
cascade plans this question with the rules planner, which asks for a summary
only when the question says so.

Checks: 1,821 tests pass; ruff and mypy pass; `compare_answers.py` reports
`0 of 244 conversations differ`.
