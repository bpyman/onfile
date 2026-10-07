# 05 — An adjudication proves its rule predates the cases

**What to build:** Found by the two-axis review of PRs #69-#90 (6 October 2026), spec axis. The planner comparison's Protocol (PR #86) says a label may be adjudicated only against "a product rule … as committed before the case was written". `load_adjudications` (`planner_evaluation.py`) checks only that `rule` and `why` are non-empty text, so nothing enforces "before".

- Each adjudication names the commit that holds its rule (`rule_commit`, a full SHA) and the file it is in (`rule_file`); each case file that has adjudications names the commit that added its cases (`cases_commit`).
- `load_adjudications` requires the fields and their shape.
- A unit test checks, where the git history is present, that each `rule_commit` is an ancestor of its file's `cases_commit`, and that the quoted rule text appears in `rule_file` at `rule_commit`. Skip with a clear reason when the checkout is shallow (CI's default checkout fetches one commit): the test runs locally and in a full clone.
- Fill the fields for the two set-4 adjudications: rule commit `54a0e22`, rule file `README.md`, cases commit `bc237f0` (resolve to full SHAs).

**Acceptance:** a fixture adjudication citing a commit after its cases fails the test; the set-4 adjudications pass; `--from-json` still renders. `uv run python -m pytest` passes; `uv run python scripts/compare_answers.py` names every conversation whose answer changes, and each change is intended.

**Blocked by:** None — can start immediately

**Status:** ready-for-agent
