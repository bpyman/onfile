# Audience window

The Next.js window for Onfile (ADR 0006,
`docs/adr/0006-react-audience-window.md`). The browser only ever calls this
app's `/api/*`; the route handler in `app/api/[...path]/route.ts` proxies each
call to the Python API.

## Run locally

```bash
# repo root: the API on port 8000, recorded runtime
APP_MODE=recorded uv run serve-api

# web/
npm install
npm run dev   # http://localhost:3000
```

No secrets are needed locally. Open http://localhost:3000 and click "Verify a
quarterly fact" for the Microsoft pretax-income fact card.

## How the window behaves

- One thread per browser. Its id is kept in `localStorage`, so a reload resumes
  it; an expired thread is dropped with a quiet notice.
- Start over starts a new thread on the same runtime, then clears the old one; it
  asks first in the page (in-app browsers never show `window.confirm`) and works
  while an answer is still running or a saved thread is still loading. Flipping
  the Recorded / Live switch is Start over on the other runtime. On a locked
  public demo the switch is disabled and its tooltip says why.
- The landing page renders its guided stories without the API, pings
  `/api/health` on load, and a turn that shows no progress after about 3 seconds
  says "Waking the analysis service…". While the API is slow to answer (a
  redeploy, say), a guided story shows its recorded answer at once
  (`lib/demo-answers.json`, written by `scripts/record_demo_answers.py`), marked
  "Demo data".
- One malformed answer is contained to its own card (an error boundary per
  answer, and `app/error.tsx` for the page), and replies are validated in
  `lib/api.ts` before they render.
- `/?q=<question>&rt=recorded|live` asks the question once on load in a new
  thread; Copy link writes that URL for the answer on screen.
- Every amount shown as text comes from the API's presentation mapping; the
  browser formats nothing but chart axis ticks.

## Environment

Both variables are read by the proxy route on the server; neither is
`NEXT_PUBLIC_`, so neither is bundled for the browser. See `.env.example`.

| Variable | Default | Purpose |
| --- | --- | --- |
| `API_ORIGIN` | `http://127.0.0.1:8000` | Base URL of the Python API. |
| `API_PROXY_TOKEN` | unset | Shared secret sent upstream as `X-Proxy-Token`. Set it to the API's `API_PROXY_TOKEN` on a hosted deploy; the API then refuses any call but `/api/health` that did not come through this proxy. Unset, no header is sent. |

On Vercel the project's Root Directory is `web/`. `vercel.json` turns on Fluid
compute, pins functions to `iad1`, and runs `scripts/ignore-build.sh` as the Ignored
Build Step, which skips the build when nothing under `web/` changed. See
[`docs/deploy.md`](../docs/deploy.md).

## Checks

```bash
npm run lint && npm test && npm run build && npx tsc --noEmit
```

CI (`.github/workflows/ci.yml`, job `web`, Node 22 from `.nvmrc`) runs these,
then the browser check.

## Browser check

`e2e/` is a Playwright suite that drives the window the way an analyst does:
each guided story (fact card, chart, table, filing changes), compare four
quarters then "add Apple", a clarify-button round trip, and reload plus Start
over. Selectors are roles and accessible names only.

```bash
npm run build
npm run test:e2e
```

With `PLAYWRIGHT_BASE_URL` unset, it starts the Python API on the recorded
runtime (port 8100, from the repo root with `uv run serve-api`) and the built
app (`npm start`, port 3100), reusing either if it is already running outside
CI. Set `PLAYWRIGHT_BASE_URL` to run the same suite against a deployed window
instead, for example the hosted demo:

```bash
PLAYWRIGHT_BASE_URL=https://<your-deploy>.vercel.app npm run test:e2e
```

`@playwright/test` is pinned to 1.56.1. CI installs its own Chromium with
`npx playwright install --with-deps chromium`.

## Portfolio capture

`scripts/capture-portfolio.ts` re-captures the README's images in
`docs/portfolio/images/` from this window (ADR 0006 cutover criteria). It is a
Playwright script with its own config (`playwright.capture.config.ts`) that
starts, or reuses, the same recorded API and built app as the browser check. It
takes the stills on one fresh thread at 2x, records the compare four quarters →
"add Apple" → inspect the 10-Q source walkthrough on another, and converts the
recording to MP4 and GIF with ffmpeg (`$FFMPEG`, or `ffmpeg` on `PATH`; the run
stops before opening a browser if neither works).

```bash
npm run build
npm run capture
```

`PORTFOLIO_DIR` writes the files somewhere else, for a look before committing.
