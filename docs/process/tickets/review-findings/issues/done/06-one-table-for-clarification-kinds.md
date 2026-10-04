# 06 — One table for what each clarification kind does

**What to build:** The same four-way branch on `ambiguous_metric`, `ambiguous_mode`, `ambiguous_company` and `ambiguous_comparison` appears in `graph/clarify.py` (reading the answer, resuming the question, asking again) and in `presentation.py` (the prompt). Adding a fifth kind means editing every branch. Gather each kind's prompt, answer reader, resume and "ask again" note in one place keyed by kind.

Found by the 2026-10-03 review of PRs #45–#58 (Standards: repeated switches).

Spec: ADR 0004, ADR 0005, ADR 0010.

**Blocked by:** None — can start immediately

**Status:** done

## Answer

Each kind of clarification is one entry in `graph/clarify.CLARIFY_KINDS`: its prompt, the hint said when an answer is out of range, the reader of its answer, and how the held question resumes. `clarification_reply`, `resumed_request` and `ask_again` look the kind up instead of branching on it, and the presentation reads its prompt through `clarify_prompt`. A new kind is one entry, and a test checks every `ClarifyKind` has one. In passing, the scope question ("Add to the current analysis, or start a new one?") had borrowed the metric question's hint, "or type the metric's name"; it now says "or type “extend” or “replace”", the answers its reader takes.
