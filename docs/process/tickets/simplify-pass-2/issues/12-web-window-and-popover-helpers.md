# Share the analyst window's thread steps, popover wiring and API readers

From a parallel `/simplify` review of the whole codebase (7 October 2026): seven read-only reviewers, one per area plus one across areas; 84 findings, consolidated into 12 tickets that never share a file. Cleanup only: **no behaviour may change**.

**Files (this ticket only):** `web/components/analyst-window.tsx`, `web/components/header.tsx`, `web/components/status-line.tsx`, `web/components/runtime-guide.tsx`, `web/lib/browser.ts`, `web/lib/api.ts`, `web/lib/proxy.ts`, `web/app/api/[...path]/route.ts`

**What to build:** The analyst window repeats its thread-switch steps by hand, three popovers copy the same wiring, and the defensive API readers and the proxy each keep two copies of a rule. Give each rule one place. Nothing may behave or render differently.

1. **Thread switching in about eight places** (analyst-window.tsx:223-226, 291-302, 330-331, 366-370, 404-417, 427-433, 476-481, 486-489, 570-572). Add three local helpers:
   - `showThread(view, notice?: string | null)` for the sequence `shownTurns.current = 0; setView(v); if (notice) setNotice({kind: "info", text})`, which is written five times;
   - `loadIfCurrent(id): Promise<ThreadView | null>`, which wraps `getThread(id)` with the `isCurrentThread(store, id)` check used in follow, the moved branch and refresh;
   - `retryResume()` for `setBooted(false); setResumeAttempt(a => a + 1)`, written twice.
   Each site keeps its own dispatch and notice text. Delete the stale first of the two doc comments stacked on `ask()`.
2. **Popover wiring, three copies** (header.tsx:120-135, status-line.tsx:219-232, runtime-guide.tsx:29-35). Add a `useAnchoredPopover(place: (panel, anchor: DOMRect) => void)` hook in lib/browser.ts next to `placeBelow`. It returns `{id, button, panel, onBeforeToggle, close(then)}`. `onBeforeToggle` returns early unless the new state is "open" and then measures the button; `close` hides the popover before running the action. AddMenu and RuntimeGuide pass `(p, a) => placeBelow(p, a, width, gap, gutter)`; PhoneMenu passes its right-edge placement.
3. **Defensive readers copied** (api.ts:367-387 `readTable`, 435-451 `readChart`). Add `textRows(value): string[][]`, for `raw` and `raw_percent` only (`rows` deliberately filters out non-arrays, so leave it), and `recordOf<T>(value, guard: (v) => v is T): Record<string, T>` for `amounts` (string) and `evidence` (isIndex). The conditional spreads stay as they are.
4. **The proxy route re-derives proxy.ts's decisions** (route.ts:20, 32-39; proxy.ts:33, 62, 74). `method !== "GET" && method !== "HEAD"` is written three times, and the 413 detail "That request is too large for the analysis service." twice. Export `hasBody(request)` and `TOO_LARGE` from lib/proxy.ts and use them in `upstreamRequestHeaders`, `refusal` and route.ts.

**Acceptance:** `npm test`, `npm run lint` and `npx tsc --noEmit` pass in web/; `npm run test:e2e` passes. By hand: switch threads, resume after a reload, and open and close each of the three menus by click and by keyboard; focus and placement must match today's.

**Findings covered:**
- web/simplification: AnalystWindow repeats thread-switch, load-if-current and retry-resume sequences
- web/simplification: three native-popover components hand-roll the same wiring
- web/simplification: api.ts readTable and readChart copy nested-array and record parsing
- web/simplification: proxy route re-derives the has-body rule and the 413 detail

**Acceptance:** `npx --prefix web vitest run`, `npm --prefix web run lint` and `npm --prefix web run build` pass, and the Playwright browser check is unchanged. If a step would change behaviour, or needs a file outside this ticket's list, leave it and say so in the Answer.

**Blocked by:** None — can start immediately

**Status:** resolved

## Answer

Shipped 8 October 2026. Each rule has one place; no answer, response, focus or placement changes.

1. **Thread switching** (`analyst-window.tsx`). `showThread(next, notice?)` is the one `shownTurns.current = 0; setView; info notice` sequence, used at the locked-runtime restart, both branches of the other-tab follow, the lost-thread restart inside `ask`, the moved-thread branch and `startOver`. `retryResume()` is the one `setBooted(false); setResumeAttempt(+1)`, used by `startOver`'s failure path and the notice's Try again button. `loadIfCurrent(store, threadId)` is `getThread` plus the `isCurrentThread` check, used by the follow, the moved branch and `refresh`. It lives at module level and takes the store rather than closing over it as the ticket's `loadIfCurrent(id)` would: the follow effect calls it, and a component-scoped closure there made `react-hooks/exhaustive-deps` ask for it as a dependency (which would re-subscribe the storage listener on every render). The stale first doc comment on `ask()` is deleted. One ordering note: in the other-tab follow, `shownTurns` is now zeroed when the loaded thread arrives (inside `showThread`) rather than when the storage event fires. The two agree unless the reset of a failed turn re-renders between the event and the load, when the old code could leave `shownTurns` at the old turn count and skip the scroll to the newly shown thread's last turn; zeroing at show time is what the sequence means everywhere else, and no test or browser check distinguishes the two.
2. **Popover wiring** (`lib/browser.ts`). `useAnchoredPopover(place)` returns `{id, button, panel, onBeforeToggle, close}`: `onBeforeToggle` returns unless the new state is "open" and then calls `place(panel, buttonRect)`; `close(then)` hides the panel, then runs the action. `PhoneMenu` passes its right-edge placement, `AddMenu` `placeBelow(menu, anchor, 288, 6)` and `RuntimeGuide` `placeBelow(panel, anchor, PANEL_WIDTH, 8, GUTTER)`; `RuntimeGuide` takes only `id`, `button` and `onBeforeToggle`, as it had no panel ref before. `PhoneTheme`'s `onDone` still hides through the panel ref. Each component's own `useId`/`useRef`/`ToggleEvent` imports are gone (the header keeps `useId` for its tooltip).
3. **Defensive readers** (`lib/api.ts`). `textRows(value)` reads `raw` and `raw_percent`; `recordOf(value, guard)` reads a line chart's `amounts` (with `isText`) and `evidence` (with `isIndex`). `rows`, `numbers` and the conditional spreads are as they were; `period_labels`/`series_labels` use `map(text)` rather than `texts` (which filters), so they are also left.
4. **Proxy** (`lib/proxy.ts`, `route.ts`). `hasBody(request)` and `TOO_LARGE` are exported and used in `upstreamRequestHeaders`, `refusal` and the route's chunked-body refusal.

Tests: `lib/browser.test.tsx` (new, 3: one id links button and panel; placement runs on open with the button's rectangle and not on close; close hides before the action runs), `lib/proxy.test.ts` (+1 `hasBody`, the 413 case now checks `TOO_LARGE` and pins its words), `lib/api.test.ts` (+2, pinning a table's `raw`/`raw_percent` reading and a line chart's `amounts`/`evidence` filtering; both passed before the change). In `web/`: `npx vitest run` 219 pass, `npm run lint` and `npx tsc --noEmit` clean, `npm run build` ok, `npm run test:e2e` 46 pass (thread switching, resume after reload, Start over, the phone menu by click and Escape, the Add menu and the runtimes guide are among its cases). The by-hand pass of the three menus by click and keyboard was not done (unattended run); the hook keeps each panel's native `popover="auto"`, roles and placement call unchanged.
