# 05 — Read the filing change's form, sections and accessions once

**What to build:** `filing_change.run_filing_change` re-reads the raw question: accession numbers override the plan's (`_accessions_from_query`), the question's sections override the plan's (`requested_sections`, else `parse_sections` substring-matches the plan's free-text section), and the form (10-K or 10-Q) comes only from the question (`_form_asked`). `FilingChangeRequest` has no form field, so the LLM planner cannot express one; it works only because the question is read again.

Bind typed `sections`, `form` and accessions once, in `turn_graph.request_from_proposal`, from the shared wording (ADR 0010, 0011); give `WorkflowPlan` and the LLM's filing-change action a `form`; the workflow reads the request only.

**Why a person:** it changes the LLM planner's schema and prompt, so it needs a paid LLM check of the filing-change cases.

**Acceptance:** filing-change questions answer as before on both planners; `uv run python scripts/compare_answers.py` reports `0 of N conversations differ`: what the recorded demo answers does not change.

Found by the 2026-10-04 simplify review of master (#67), which left it out as larger than a cleanup.

Spec: ADR 0010, ADR 0011.

**Blocked by:** None — can start immediately

**Status:** ready-for-human
