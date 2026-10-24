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

**Status:** resolved

## Answer

Shipped 2026-10-23.

- "What you can ask" shows every capability the API sends. The first three lines show as before. A "Show N more" button below the list (a native button with `aria-expanded` and `aria-controls` on the list) reveals the rest and then reads "Show fewer". With the recorded API's five capabilities, it reads "Show 2 more" and reveals the qualitative line and the follow-up line.
- Every example of a line is in the DOM. From `sm` up, all of them show, wrapped. On a phone, the first three show and a "+N" chip reveals the rest. The chip is a disclosure button with `aria-expanded`, `aria-controls` and the label "Show 1 more example". It is hidden from `sm` up. The check was made at 375 px against the recorded API. The lookup line with three examples already takes three rows: its long examples take a row each. Showing all four would add a fourth row, so it gets "+1". The follow-up line fits in two rows as three examples plus "+1"; all four would take three rows.
- The comment's promise is now true: `EXAMPLES_SHOWN` became `EXAMPLES_SHOWN_ON_A_PHONE`, and the comment says what each control reveals.
- New `web/components/landing.test.tsx`: with five capabilities from `meta`, three lines show and the button reveals the other two. Every example is a reachable button. The lookup line's fourth example sits behind its "+1" chip until the chip is pressed, and pressing it drafts the question.
- Layout at 800×600, checked against the recorded API in a dev browser: the page has no horizontal scroll (scroll width 785 inside the 800 px window, after the vertical scrollbar), and neither does the composer's textarea (scrollWidth equals clientWidth). When the page is scrolled to the end, the last content sits about 50 px above the composer's 128 px fixed box. That box comes from `main`'s `pb-44` (176 px) in `web/components/analyst-window.tsx`, not from `landing.tsx`. At the top of the page, the fixed composer overlays the lower part of the guided stories. That comes with a pinned composer, and the stories scroll clear of it. I could not reproduce the horizontal scrollbar from the review. If it returns, the cause is in the composer: its textarea is `overflow: auto`. Nothing in `landing.tsx` was changed for this, and the composer was left alone.
- `web/scripts/capture-portfolio.ts` does not depend on the cut, so it was not changed. Portfolio images of the landing page predate the "Show 2 more" button and were not re-captured: the capture script needs a running app. Re-capture them when convenient.
- A possible follow-up, outside this ticket's files: the API lists the follow-up line fifth (`storefront.CAPABILITIES`), so it stays behind "Show 2 more". Moving it up would show it on the first screen.
- Checks: pytest (2,602), ruff and mypy pass; compare_answers reports 0 of 893 conversations differ; lint, tsc and vitest (230) pass; `npm run build` passes from PowerShell.
