# 05 — An adjudication proves its rule predates the cases

**What to build:** Found by the two-axis review of PRs #69-#90 (6 October 2026), spec axis. The planner comparison's Protocol (PR #86) says a label may be adjudicated only against "a product rule … as committed before the case was written". `load_adjudications` (`planner_evaluation.py`) checks only that `rule` and `why` are non-empty text, so nothing enforces "before".

- Each adjudication names the commit that holds its rule (`rule_commit`, a full SHA) and the file it is in (`rule_file`); each case file that has adjudications names the commit that added its cases (`cases_commit`).
- `load_adjudications` requires the fields and their shape.
- A unit test checks, where the git history is present, that each `rule_commit` is an ancestor of its file's `cases_commit`, and that the quoted rule text appears in `rule_file` at `rule_commit`. Skip with a clear reason when the checkout is shallow (CI's default checkout fetches one commit): the test runs locally and in a full clone.
- Fill the fields for the two set-4 adjudications: rule commit `54a0e22`, rule file `README.md`, cases commit `bc237f0` (resolve to full SHAs).

**Acceptance:** a fixture adjudication citing a commit after its cases fails the test; the set-4 adjudications pass; `--from-json` still renders. `uv run python -m pytest` passes; `uv run python scripts/compare_answers.py` names every conversation whose answer changes, and each change is intended.

**Blocked by:** None — can start immediately

**Status:** resolved

## Answer

Shipped 6 October 2026.

- `Adjudication` (`planner_evaluation.py`) carries `rule_file`, `rule_commit` and `cases_commit`. `load_adjudications` requires a full lower-case 40-hex `cases_commit` on any case file that has adjudications (a file without them needs none), and on each adjudication a non-empty `rule_file` and a full 40-hex `rule_commit`; a short SHA such as `54a0e22` is refused.
- `rule` is now the rule quoted verbatim as `rule_file` has it at `rule_commit`, so the quote can be checked rather than paraphrased. The set-4 adjudications read `` `Compare Microsoft and Apple revenue growth` charts the growth rates `` with `rule_file` `README.md`, `rule_commit` `54a0e227e28d44334144a82d9af18725295cb5cf`, and `cases_commit` `bc237f0a4b568bbcca72dd609351edaea250549c`.
- `check_rule_history(adjudications, repo)` asks git whether each `rule_commit` is a strict ancestor of its `cases_commit` (the same commit is not before) and whether `rule` appears in `rule_file` at `rule_commit`; it returns one line a problem.
- Tests: a throwaway git repository with a rule commit then a cases commit passes; the same adjudication with the commits swapped, with the same commit for both, with the rule misquoted, or with the rule in another file is a problem. The committed adjudications are checked against this repository's history, and the test skips with a reason when git is missing or `git rev-parse --is-shallow-repository` says the checkout is shallow (CI's default checkout fetches one commit).
- The report's Adjudicated labels table shows the rule as `` `README.md` at `54a0e22`: … ``; the Protocol paragraph (code and `planner-comparison.md`) says the fields and the check. `--from-json` renders the saved report unchanged.
- 2,072 tests pass; ruff and mypy pass; compare_answers reports 0 of 247 conversations differ.
