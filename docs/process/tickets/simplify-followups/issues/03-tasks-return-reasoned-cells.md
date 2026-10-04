# 03 — A failed lookup is a reasoned cell, not refusal → cell → refusal

**What to build:** `turn.lookup_task` returns a REFUSE result when one company's lookup fails. `spec_turn.merge_task_results` turns that into a cell (`_lookup_refuse_as_partial`, reading the error code back out of the trace), and `_not_operating_once` turns the cells back into a refusal, rewriting the "not an operating company" sentence on the way.

Have the lookup workflow return a reasoned cell, as its per-share path already does, with the reason from `turn.reason_for`. Make one rule in `merge_analysis`: when every cell of a one-company analysis has the same reason, the answer is a refusal worded from that reason (the copy from ticket 02). Remove `_lookup_refuse_as_partial` and the sentence rewrite.

**Acceptance:** `uv run python scripts/compare_answers.py` reports `0 of N conversations differ`: what the recorded demo answers does not change.

Found by the 2026-10-04 simplify review of master (#67), which left it out as larger than a cleanup.

Spec: ADR 0002 (a refused cell keeps its reason).

**Blocked by:** 02

**Status:** ready-for-agent
