# 02 — Type workflow plans and ranked requests

**What to build:** Workflow plans are one frozen type instead of `SimpleNamespace` objects read with `getattr`. `graph/spec_turn.execute_compiled_task`, `DemoCompleter`/`rules_planner`, and the turn workflows in `turn.py` (`plan.company`, `getattr(plan, "report_date", None)`, `getattr(plan, "section", ...)` in `filing_change`) all build or read the same handful of fields, so a typo in a field name silently becomes `None` today.

In the same pass, replace `SpecPatch.ranked_request` / `SpecDraft.ranked_request` (`tuple[str, int]`) with the existing `RankedSet`-shaped request type. `SpecPatch` is persisted inside a thread's `PendingClarification`, so read the old tuple shape for one release (threads expire after the TTL) or migrate on load.

Found by the 2026-10-01 PRD/ADR review (Standards S5: plans as untyped objects; `ranked_request` duplicating `RankedSet`).

Spec: ADR 0005 (closed workflows, typed tasks).

**Blocked by:** None — can start immediately

**Status:** done

## Answer

A planner's one-shot reading of a question is `contracts.WorkflowPlan`, a frozen model, and the `Completer` port returns `WorkflowPlan | SpecPatch`. The rules planner builds one instead of a `SimpleNamespace` (edits go through `model_copy`), and the LLM planner converts its response schema at its edge (`Plan.workflow_plan`), so `spec_turn.plan_to_spec_patch`, the `is_*_proposal` checks and `turn_graph.request_from_proposal` and `with_peers` read fields rather than `getattr`. The compiled tasks the turn workflows run were already typed (`CompiledTask`), and `run_filing_change` was typed by ticket 04. `SpecPatch.ranked_request` and `SpecDraft.ranked_request` are `analysis_spec.RankedRequest` (industry, limit, as on `RankedSet`), and a clarification held with the old ("banks", 5) pair still loads. The tests' 31 plan stand-ins are `WorkflowPlan`s too, which dropped two fields nothing read (`issuers`, and the news plan's `query`). The rules planner scores the same on all 219 evaluation cases.
