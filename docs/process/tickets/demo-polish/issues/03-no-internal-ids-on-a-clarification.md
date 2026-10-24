# A clarification shows no internal ids

From the product review (presentation fixes). On the live demo, "Why did Target's gross margin jump last quarter?" asked "Compared with what?" with two buttons, "The same quarter a year earlier (year over year)" and "The quarter before (sequential)". Under each label, in small mono type, sat `year_over_year` and `sequential`. The first is an internal id, not words a visitor would type.

**Files (this ticket only):** `web/components/clarify.tsx`, its test, and whatever renders the analyst's message after a button is pressed (`web/components/thread.tsx` or the message component), with tests.

**What to build:** `clarify.tsx` shows the slug under the label when `choice.slug.replaceAll("_", " ")` differs from the whole label. Its comment says the slug is shown because it is "what the button sends", which is useful when the words differ ("net income" under "Net income (NetIncomeLoss)"). Change the rule so a visitor never sees an id:

- Show the slug as words (underscores as spaces).
- Show it only when those words are not already in the label (case-insensitive containment, not equality). "(year over year)" is in the first label, so nothing is shown under it.
- Check what the analyst's own message reads after a button is pressed. If the thread shows `year_over_year` as the visitor's message, show the words ("year over year") instead, without changing what is sent to the API.

**Acceptance:**
- Component tests: a comparison-base clarification shows no slug line, and no underscore appears anywhere in the rendered clarification.
- A metric clarification whose slug words differ from the label still shows them.
- If the message bubble needed a change, a test pins it.
- `npm run lint`, `npx tsc --noEmit`, `npx vitest run` and `npm run build` pass. On this Windows machine `npm run build` fails under Git Bash with Turbopack error 0xc0000142 and passes from PowerShell (`powershell -Command "cd web; npm run build"`), so run it there.
- The Python answers are untouched: `compare_answers.py` reports 0 differences.

**Blocked by:** None — can start immediately

**Status:** resolved

## Answer

Shipped 2026-10-23.

- `web/lib/clarify.ts` gains `slugWords` (underscores as spaces) and `slugNote(slug, label)`: the slug's words, or null when the label already contains them. Containment is case-insensitive and ignores punctuation, so "shareholders equity" is not repeated under "Shareholders' equity" nor "selling general and administrative" under "Selling, general and administrative". A candidate with no server label falls back to the slug's words instead of the raw slug.
- `web/components/clarify.tsx` shows `slugNote` under a label (no line under either comparison-base button; "eps diluted" still shows under "Diluted EPS"). The comment's "what the button sends" moved to the helper's doc; the button still sends the slug.
- The analyst's message bubble already read as the label (`shownMessage`), but its hover title read `Sent as year_over_year`. `web/components/thread.tsx` now titles it only with `slugNote(sent, shown)`: none for the comparison base, "Sent as eps diluted" for Diluted EPS. What is sent to the API is unchanged.
- Tests: `web/components/clarify.test.tsx` (new: no underscore in the rendered comparison clarification, text or title/aria-label; metric slug words shown; slug still sent), `web/lib/clarify.test.ts` (`slugNote`, fallback label), `web/components/thread.test.tsx` (bubble text and title after pressing each kind of button).
- Checks: pytest, ruff, mypy pass; compare_answers reports 0 of 893 conversations differ; lint, tsc, vitest (228) pass; `npm run build` passes from PowerShell. `npx tsc --noEmit` needs Next's generated route types (`LayoutProps`) from a build in a fresh worktree; after the build it passes.
