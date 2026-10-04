# Issue tracker: Local Markdown

The product PRD lives at `docs/process/prd.md`. Implementation tickets live as markdown files in `docs/process/tickets/`.

When a skill says “the spec,” read `docs/process/prd.md`. (`/to-spec` produced that document; it is this repo’s PRD.)

## Conventions

- Product PRD: `docs/process/prd.md`
- One feature’s tickets per directory: `docs/process/tickets/<feature-slug>/`
- Implementation issues are one file per ticket at `docs/process/tickets/<feature-slug>/issues/<NN>-<slug>.md`, numbered from `01` — never a single combined tickets file
- Triage state is recorded as a `Status:` line near the top of each issue file (see `triage-labels.md` for the role strings)
- Comments and conversation history append to the bottom of the file under a `## Comments` heading
- A finished ticket has `Status: resolved` (or `done`) and an `## Answer` section; it may move to `issues/done/`, which counts as resolved for `Blocked by:`
- Only `ready-for-agent` tickets are picked up by the Ralph loop; `ready-for-human` and `needs-info` wait for a person

## When a skill says "publish to the issue tracker"

Create a new file under `docs/process/tickets/<feature-slug>/` (creating the directory if needed).

## When a skill says "fetch the relevant ticket"

Read the file at the referenced path. The user will normally pass the path or the issue number directly.

## Wayfinding operations

Used by `/wayfinder`. The **map** is a file with one **child** file per ticket.

- **Map**: `docs/process/tickets/<effort>/map.md` — the Notes / Decisions-so-far / Fog body.
- **Child ticket**: `docs/process/tickets/<effort>/issues/NN-<slug>.md`, numbered from `01`, with the question in the body. A `Type:` line records the ticket type (`research`/`prototype`/`grilling`/`task`); a `Status:` line records `claimed`/`resolved`.
- **Blocking**: a `Blocked by: NN, NN` line near the top. A ticket is unblocked when every file it lists is `resolved`.
- **Frontier**: scan `docs/process/tickets/<effort>/issues/` for files that are open, unblocked, and unclaimed; first by number wins.
- **Claim**: set `Status: claimed` and save before any work.
- **Resolve**: append the answer under an `## Answer` heading, set `Status: resolved`, then append a context pointer (gist + link) to the map's Decisions-so-far in `map.md`.
