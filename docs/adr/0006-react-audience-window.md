# A Next.js audience window over a thin HTTP seam, not Streamlit

> **Revised (28 September 2026, hosting):** the API moved from Render's free web service to the `starter` plan ($7/month, 512 MB of RAM, half a CPU; `render.yaml`). It is always on: no sleep after idle minutes and no minute-long wake, so the first visitor no longer waits. The window's "Waking the analysis service…" message and its `/api/health` ping on load stay; the message now covers a redeploy or a slow reply. The free-tier reasoning below is kept as it was decided.

The audience window moves from Streamlit to a React/Next.js app (`web/`) that talks to the Python core through a small FastAPI service (`financial_analyst_agent.api`). The API is a transport over seams that already exist: `run_conversation_turn` for a turn, `present_turn` for display records, `LocalThreadStore` for thread state, `SessionBudget` for public quotas, `runtime_for` for the recorded versus live runtime. It adds no financial logic, and the browser receives the `Presentation` mapping as JSON — formatted strings, chart records, evidence items, traces — so the client never formats a number.

This supersedes PRD story 34 ("Streamlit to be the only audience window") and the audience-window ticket's out-of-scope line "Leaving Streamlit". It does not touch ADRs 0001–0005: membership, lookup gating, the quarterly fact module, clarify rules, and the stateful graph run underneath, unchanged.

## Locked

- **Presentation stays in Python.** `present_turn` is the only place a `Decimal` becomes a string. The client may choose chart axis tick formats from `chart_value_kind`, but amounts shown as text come from the server.
- **One turn endpoint, streamed.** `POST /api/threads/{thread_id}/turns` returns server-sent events: `progress` (`done`, `total` compiled cells), then exactly one `thread` (the whole thread view) or `error` (a public message — `ConfigurationError`, `SessionQuotaError`, and `RuntimeMismatchError` text, otherwise a generic failure).
- **One thread per browser, plus Start over.** The thread identifier is a server-minted UUID kept in `localStorage`; a reload resumes it until `THREAD_TTL_SECONDS` expires it. No thread list, no accounts (ADR 0005).
- **A thread is bound to one runtime, enforced by the conversation seam.** A thread picks the recorded or live runtime when it is created (`POST /api/threads {runtime}`); turns carry no runtime flag. `Runtime` carries which one it is, and `run_conversation_turn` refuses a turn whose runtime differs from the thread's with a typed error, so every caller — API, Streamlit until cutover, MCP, tests — gets the rule, not only the HTTP front door. Switching runtime in the window is Start over on the other runtime. When `PUBLIC_DEMO=true` and `DEMO_LIVE_SEC=false`, a request for a live thread is created recorded and the response says so; the window shows a disabled switch with a lock and "Live runtime is off on the public demo". (Streamlit let the switch flip mid-thread; that is the behaviour this replaces.)
- **Threads saved before runtime binding** bind to whichever runtime their next turn uses.
- **Glossary words in code and config.** Python identifiers take the glossary's names (`runtime_for`, `recorded_runtime()`), and `APP_MODE` accepts `recorded`, keeping `fixture` as a deprecated alias so existing `.env` files and deploy notes still work. Test fixtures and data files keep "fixture", which is testing vocabulary there, not the domain term.
- **Glossary words on screen.** The window labels the runtimes "Recorded" and "Live", and the recorded banner opens "Recorded runtime — captured SEC filings, not a live EDGAR pull." "Guided demo data" is retired.
- **Threads may be lost on restart.** The hosted thread store is a plain local disk, as it already was on Streamlit Community Cloud; threads also expire after `THREAD_TTL_SECONDS`. When a stored thread comes back empty, the window says so and starts fresh.
- **The API accepts only proxied calls.** The Vercel proxy sends a shared secret header (`X-Proxy-Token`); when `API_PROXY_TOKEN` is set, the API refuses requests without it (401, constant-time compare; `/api/health` stays open for wake-up and platform checks), so the Python origin is not a second public entry point. Local runs leave it unset and need no secrets; the API logs a startup warning when `PUBLIC_DEMO=true` and the token is missing.
- **Turns are admitted, not queued.** Only a thread the API created takes a turn: an unknown or expired id gets 404 before anything runs, and the window then starts a fresh thread on the same runtime and asks again. At most `MAX_CONCURRENT_TURNS` turns (default 4) run at once across the process; one more gets 429 with `Retry-After`, again before any work starts. A turn keeps its slot until it ends, even if its reader has gone, or until `TURN_TIMEOUT_SECONDS` (default 150) pass: then the API ends it with an error event, frees its thread and slot, and drops whatever the still-running worker writes later. Refused turns (unknown thread, a turn already running, a thread at its turn limit, a full house) do not count against the visitor's hourly turns. Expiry re-reads the checkpoint under the thread store's lock and spares a thread whose turn is in flight, so it never deletes a checkpoint or evidence saved after it decided.
- **Clarify answers are messages.** A candidate button sends its catalog slug as the next analyst message, as before; only the last turn's candidates are live, and only while the thread holds a pending clarification.
- **Streamed progress stays.** Progress events are worth the proxy-buffering care: a ranked ten-company lookup otherwise looks hung.
- **Browser never calls Python directly.** A Next.js route handler proxies `/api/*` to `API_ORIGIN`, so there is no CORS surface and the Python host can move without a client rebuild.

## Hosting

Next.js on Vercel Hobby at a `*.vercel.app` subdomain, with `web/` as the project root and an ignored-build step so Python-only commits do not rebuild it. The proxy route runs up to 300s under Fluid Compute, which covers a long streamed turn.

FastAPI in a Docker container on Render's free web service, configured by a checked-in `render.yaml` and deployed from GitHub. One instance is a requirement, not a limit: the file-backed thread store and the per-thread turn lock only work if every request for a thread reaches the same process. The shared proxy token is a Render environment variable (not synced from `render.yaml`) and a Vercel environment variable. Render's free tier gives 0.1 CPU and sleeps after 15 idle minutes with about a minute to wake, so the first visitor after idle waits; the window says "Waking the analysis service…" rather than spinning. The landing page calls `/api/health` as soon as it loads, so the backend usually wakes while the visitor reads the guided stories; no scheduled keep-alive, since GitHub delays scheduled runs and disables them after 60 days without repo activity. That trades speed for no card on file; the same image moves to standard Cloud Run with a new config file if speed matters later.

The service runs in Render's Virginia region, next to Vercel's default `iad1` functions. Render deploys only after GitHub CI passes on the commit (falling back to a deploy hook called from CI if the free tier lacks that setting). Vercel production deploys only after CI too: `web/vercel.json` turns off Vercel's Git deploys of `master`, and a CI job calls a Vercel deploy hook once every other job passes. So a commit that fails lint, types, tests, or the Playwright check never reaches the public demo. Pull request previews still build on push, behind Vercel's login. Vercel preview deployments call the production Render API: previews always run the recorded runtime, and the three-PR order lands API changes before the UI that depends on them.

## Migration

Streamlit stays runnable alongside until cutover (its switch now does Start over on the other runtime, matching the new window), then `app.py`, its tests, and the `streamlit`, `streamlit-shadcn-ui`, `altair`, and `pandas` dependencies are deleted in one follow-up. Two windows exist until then; both call the same seams, so neither can drift on numbers.

Cutover needs all three: the hosted Next.js URL serves the recorded runtime; a Playwright check in CI clicks each guided story and the compare-then-add-Apple walkthrough and finds the expected fact card, chart, table, or disclosure; and the README's portfolio images are re-captured from the new window by a Playwright script (`web/scripts/capture-portfolio.ts`) that drives the same walkthrough, so they can be regenerated whenever the window changes. The Playwright check replaces what `tests/test_app.py` guarded; there are no visual snapshot tests.

At cutover the Community Cloud app is repointed at a `streamlit-redirect` branch holding a single "This demo has moved" page with its own minimal requirements, so links already sent out keep working while `master` sheds every Streamlit dependency.

Delivery is three PRs, tracked as tickets under `docs/process/tickets/react-audience-window/issues/`: parity locally (runtime binding, vocabulary, proxy token, the finished window, the Playwright check in CI); deploy (Dockerfile, `render.yaml`, Vercel config, deploy docs, and a wizard for the account steps only a human can do); cutover (recaptured images, README, redirect branch, Streamlit deletion).

Scope is parity with the Streamlit window plus three display-only additions: copy buttons on identifiers, a turn counter, and a compact/full column switch on tables. CSV export and shareable thread links are out: a share link would reintroduce cross-visitor thread access.

## Considered Options

- **Keep Streamlit, restyle harder** — rejected: the rerun model fights multi-turn chat (turn-in-flight flags, pending-query session keys, full-page reruns on every click), and component styling is capped by what Streamlit exposes.
- **Next.js calls Python via Vercel Python functions** — rejected: no durable disk for threads, cold-start LangGraph imports, per-request process.
- **One container serving a static Next export from FastAPI** — rejected for now: one deploy is simpler, but it gives up Vercel previews and edge caching for the storefront. The API image stays independent so this remains a later option.
- **Port `presentation.py` to TypeScript** — rejected: two formatters would drift, and the numeral-lock story depends on one renderer.
- **Cloud Run Starter Tier** — rejected: it is the target of Google AI Studio's Publish button, with a locked API surface; deploying this repo's Docker image from GitHub with Artifact Registry and Secret Manager does not fit it.
- **Standard Cloud Run** — deferred: faster CPU and keyless CI deploys, but it needs a billing account with no hard spending cap.
- **Koyeb free** — rejected: its 100s HTTP cap would cut long streamed turns.
- **Browser calls FastAPI with CORS** — rejected: exposes the Python origin and couples the client build to it.
- **Delete Streamlit in the same change** — rejected: the README's hosted link would point at nothing until the new host exists.

## Consequences

There are now two runtimes to deploy and a JSON contract between them (`web/lib/types.ts` mirrors `presentation.py`; `tests/test_api.py` pins the shape). A Python dataclass field rename is a client break unless both sides change together. SSE through a proxy needs buffering disabled end to end (`X-Accel-Buffering: no`, no compression on the stream). CI grows a Node job.
