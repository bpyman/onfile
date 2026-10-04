# ISSUES

Read `docs/process/prd.md`, `docs/process/progress.txt`, and `CONTEXT.md`. Tracker conventions live in `docs/process/agents/issue-tracker.md`. An issue **index** (path, status, blockers) is provided above. Open the chosen ticket file on disk; do not expect full bodies in this prompt.

A ticket is **actionable** when all of these hold:

- `Status:` is `ready-for-agent` (a missing Status counts as ready-for-agent when the file is still in `issues/`, not `issues/done/`). `ready-for-human`, `needs-info`, `needs-triage` and `wontfix` tickets are never actionable: leave them as they are
- it is on the **frontier**: every ticket in `Blocked by:` is `Status: resolved` or lives under `issues/done/` — confirm on disk if the index is ambiguous
- it is an implementation ticket (`**What to build:**` is present). A parent spec (user stories / implementation decisions, no What to build) stays put while numbered implementation tickets exist

Among the frontier, lowest number in that feature wins, then the priority order below.

If nothing is actionable, output <promise>NO MORE TASKS</promise> and stop.

# TASK SELECTION

Pick one ticket, in this order:

1. Critical bugfixes
2. Development infrastructure (tests, types, seams the next tracer needs)
3. Tracer bullets — a thin vertical slice through every layer, demoable on its own
4. Polish and quick wins
5. Refactors

# EXPLORATION

Read the chosen ticket, any spec it names, `CONTEXT.md`, and the ADRs it cites. Then the code. Name things with the glossary in `CONTEXT.md`.

# IMPLEMENTATION

Follow the TDD skill: red, then green, at the seams the ticket names. One ticket only.

# FEEDBACK LOOPS

Before committing, from the repo root:

- `uv run pytest`
- `uv run ruff check src tests scripts`
- `uv run mypy`
- `uv run python scripts/compare_answers.py`: what the recorded demo answers, compared with the last commit. A ticket that should leave the answers alone must report `0 of N conversations differ`. One meant to change them must show only the conversations it means to change; name each, and why, in the commit message and the ticket's Answer. An unexplained difference is a regression: fix the code, never the comparison.

If the ticket touches `web/`, also run, from `web/`:

- `npm run lint`
- `npx tsc --noEmit`
- `npx vitest run`
- `npm run build`

All of these must pass. Tests stay offline: `pytest` already excludes `network`, and network tests are not run.

# LIMITS

- Never call paid services (OpenAI, Tavily), and never read, print or set API keys. The LLM planner is checked through its fake-client tests; a ticket that needs a paid run is a person's.
- Do not push, open pull requests or merge. Commit on the current branch.
- Do not commit regenerated evaluation reports under `docs/evaluation/` unless the ticket asks for them; the scorecard rewrites its timings on every run (`git checkout -- docs/evaluation/` restores them).

# COMMIT

Commit this ticket's work. The message says why, then:

1. Key decisions
2. Files changed
3. Blockers or notes for the next iteration

# CLOSE THE TICKET

Append a dated entry to `docs/process/progress.txt`: ticket path, key decisions, files changed, blockers / next.

If the ticket is done: set `Status: resolved` and append `## Answer` with what shipped. A finished ticket may also move to `issues/done/`, which counts as resolved.

If the ticket is not done: append `## Comments` with what changed and what remains; leave `Status: ready-for-agent`.

If the ticket turns out to need a decision the ticket does not make, a paid run, or live data to judge: set `Status: needs-info` (with the question) or `ready-for-human` (with why) under `## Comments`, commit nothing else, and stop.

# FINAL RULES

Work a single ticket.

You run unattended: nobody will answer a question or approve a design. The ticket is the approved design, so a skill that asks for approval before building takes the ticket as that approval and goes on. Never end your turn waiting for input. If the ticket really needs a decision it does not make, hand it back as `needs-info` (see CLOSE THE TICKET).
