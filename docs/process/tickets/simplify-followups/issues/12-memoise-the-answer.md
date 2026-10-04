# 12 — Re-render only the answer that changed

**What to build:** `web/components/thread.tsx` passes each `Answer` fresh `conversation` and `clarify` props on every render, and `Answer` is not memoised, so every progress event re-renders every earlier answer and re-lays-out its charts.

Make the props stable (memoise them in `thread.tsx`) and wrap `Answer` in `React.memo`.

**Acceptance:** the web checks pass (`npm run lint`, `npx tsc --noEmit`, `npx vitest run`, `npm run build`), and earlier answers stay correct after a follow-up, a clarification and a sort (Playwright: `npx playwright test`); `uv run python scripts/compare_answers.py` reports `0 of N conversations differ`: what the recorded demo answers does not change.

Found by the 2026-10-04 simplify review of master (#67), which left it out as larger than a cleanup.

**Blocked by:** None — can start immediately

**Status:** resolved

## Answer

Shipped on 2026-10-04.

- `Thread` now gives completed answers stable conversation, clarification, and
  send-callback props while progress events re-render their parent.
- `Answer` is wrapped in `React.memo`, so an unchanged answer keeps its chart
  and table render intact.
- Focused component tests pin both the stable progress-event behaviour and the
  memoised export.
- All 1,657 Python tests, 210 Vitest tests, and 46 Playwright tests pass. Ruff,
  mypy, ESLint, TypeScript, and the production build pass. The answer
  comparison reports `0 of 244 conversations differ from HEAD`.
