# The landing page shows every capability, or a way to see the rest

From the product review (presentation fixes). `web/components/landing.tsx` cuts "What you can ask" to `CAPABILITIES_SHOWN = 3` lines and each line to `EXAMPLES_SHOWN = 3` examples. Its comment says "the rest stays a click away", but nothing opens the rest. With news enabled the API sends five capabilities (`storefront.capabilities_for`), so the hosted demo never shows:
- the qualitative and news line;
- the follow-up line ("add Apple", "show year-over-year"), which is how a visitor learns that a thread can be extended;
- the fourth lookup example ("How is Nvidia doing?").

**Files (this ticket only):** `web/components/landing.tsx`, its tests, and `web/scripts/capture-portfolio.ts` only if a captured image's layout depends on the cut.

**What to build:** Show every capability the API sends. Keep the first screen compact: show the first three lines as now, then a "Show N more" button (an accessible disclosure, keyboard-operable, `aria-expanded`) that reveals the rest. Inside each line, show every example, wrapped, rather than cutting at three. If that makes a line taller than about two rows on a phone (375 px), keep three examples with a "+N" chip that reveals the rest. Remove the comment's promise or make it true.

Also check the layout seen in the review: at an 800×600 window the fixed question box covered the guided stories, and the composer showed a horizontal scrollbar. Fix it if the cause is in `landing.tsx`'s spacing (bottom padding at least the composer's height). If it is in the composer, say so in the Answer and leave it.

**Acceptance:**
- Vitest: with five capabilities from `meta`, three show and the button reveals the other two. Every example of a line is reachable.
- `npm run lint`, `npx tsc --noEmit`, `npx vitest run` and `npm run build` pass. On this Windows machine run `npm run build` from PowerShell (`powershell -Command "cd web; npm run build"`), because Git Bash fails with Turbopack error 0xc0000142.
- The Python answers are untouched: `compare_answers.py` reports 0 differences.

**Blocked by:** None — can start immediately

**Status:** ready-for-agent
