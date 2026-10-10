# How this was built

Onfile has been built largely by coding agents working under my direction since 17 August 2026. This folder keeps the working files that drove that process. Nothing in the app reads them.

## How the pieces fit

1. **PRD.** [`prd.md`](prd.md) states the product: who it is for, user stories, the closed intents, and what is out of scope. It is the spec a ticket is checked against.
2. **ADRs.** [`docs/adr/`](../adr/) records each decision that constrains the code, with the options rejected. When a decision changes, the ADR is revised in place and says what it supersedes. ADR 0007, for example, revises ADR 0003's ban on derived quarters.
3. **Tickets.** [`tickets/<feature>/issues/NN-*.md`](tickets/) breaks a feature into vertical slices, each with acceptance criteria, a `Blocked by` line and a `Status`. The conventions are in [`agents/issue-tracker.md`](agents/issue-tracker.md) and [`agents/triage-labels.md`](agents/triage-labels.md).
4. **Ralph loop and agent sessions.** [`ralph/`](ralph/) runs an agent on the next open, unblocked ticket: `once.sh` for one ticket, `afk.sh` to repeat until none are left. The agent is Claude Code, run on a Claude subscription; `RALPH_AGENT=cursor` runs Cursor's agent instead, which ran the loop until October 2026. When the agent meets a rule in a ticket or an ADR it thinks is wrong, it writes the case to [`rules-to-review.md`](rules-to-review.md) and leaves the step undone; I decide each one there. `afk-parallel.sh` runs several workers at once, each in its own worktree, landing on an integration branch one at a time through `integrate.sh`, which rebases, runs the checks and the answer comparison, and pushes. [`ralph/prompt.md`](ralph/prompt.md) tells the agent to read the PRD, progress log and glossary, implement one ticket, run the checks, commit, and append to [`progress.txt`](progress.txt). Larger or open-ended work ran in interactive Claude Code sessions instead: local ones, and cloud ones on `claude/*` branches.
5. **Pull requests.** Work lands on `master` through PRs. Of the 105 merged PRs, 49 came from cloud sessions' `claude/...` branches, one from a Cursor branch, and 55 from local branches worked in Claude Code sessions and the Ralph loop. Since October, a PR that changes anything an answer could show also replays every recorded conversation (`scripts/compare_answers.py`, 893 conversations) and reports how many differ; a restructure must report none.
6. **CI.** [`.github/workflows/ci.yml`](../../.github/workflows/ci.yml) runs on every push and PR: ruff, strict mypy and pytest; a Docker image build with a smoke test; and in `web/`, lint, unit tests, a build, a type check and a Playwright browser check against the recorded API. A deploy job fires only for the commit at the tip of `master` after every check passes.
7. **Human review and merge.** I merged all 52 PRs. How I review them is in my account below.

## Who wrote the commits

At 8 October 2026, `master` held 566 commits:

| Author | Commits | Of which |
| --- | ---: | --- |
| Claude (cloud sessions) | 199 | 11 merge commits |
| Blake Pyman (`Blake Pyman` and `bpyman`) | 367 | 81 PR merge commits. Of the other 286: 203 carry a `Co-Authored-By: Claude` trailer (local Claude Code sessions and, since October, the Ralph loop), 82 a `Co-authored-by: Cursor` trailer (the Ralph loop and Cursor sessions until October), and 1 neither. |

So nearly every change on `master` was written by an agent. My part is in the decisions, the reviews and the merges.

## What I decided, how I caught mistakes, and how I review

**What I decided.** The agents wrote the code; what the product is, and the rules it must never break, were my calls. The central one runs through the first ADRs and the [design doc](../design.md): a language model may read the question, but deterministic code owns every number. That means SEC XBRL facts, `Decimal` arithmetic, rankings from a dated snapshot, and a numeral lock on anything the model writes. I also decided when evidence meant a rule had to change, rather than defending it:
- the PRD's ban on derived quarters gave way to two labelled derivations ([ADR 0007](../adr/0007-derived-quarters-and-per-share.md));
- the Streamlit window gave way to a React window ([ADR 0006](../adr/0006-react-audience-window.md)).

And I decided what the project is not: no open agent loop on the number path ([ADR 0005](../adr/0005-stateful-analysis-graph.md)), and no paid API runs without a budget agreed first.

**How I caught mistakes.** I don't take an agent's report as proof. Every PR runs CI, and before merging I have the branch reviewed separately against the PRD, the ADRs and the coding standards, with each finding reproduced. Two examples:

- [#39](https://github.com/bpyman/onfile/pull/39), a large cleanup, came back from review with six problems, two of them blocking:
  - the numeral lock had started treating any bare number from 1900 to 2099 as a year, so "hire 2000 engineers" in an essay went unchecked;
  - a ranking by "income" lost its order after the clarifying answer.

  A new rule also refused Southern California Edison as a fund. I merged [#40](https://github.com/bpyman/onfile/pull/40), the fixes with a regression test each, instead of #39 as it stood.
- The second red-team round found numbers that were plainly wrong, each confirmed against the filing before it was fixed ([#48](https://github.com/bpyman/onfile/pull/48), [ADR 0009](../adr/0009-year-over-year-reads-the-comparative.md)):
  - Verra Mobility's revenue came out as $25.83M, one tagged line, instead of the $263.59M total;
  - NVIDIA's EPS growth across its stock split read −87.3% instead of +26.7%.

**How I review.** A change starts as a ticket with acceptance criteria tied to the PRD. An agent implements it on a branch and opens a PR whose description shows the evidence: before and after, and what was checked. CI must be green. Then a second review checks the branch against the spec, and I either merge it or send it back with what to fix. I open every PR myself after reviewing the branch and arm it to merge when CI passes; nothing reaches `master` without that review.
