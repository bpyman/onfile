# Deploy notes

The hosted demo has two services (ADR 0006, "Hosting"):

```text
browser ──> Vercel: Next.js window (web/) ──/api/*──> Render: analysis API (Docker)
              proxy route adds X-Proxy-Token            refuses calls without it
```

The browser only talks to Vercel. The route handler `web/app/api/[...path]/route.ts`
forwards `/api/*` to `API_ORIGIN` and sends the shared secret. When the API has
`API_PROXY_TOKEN` set, it answers only proxied calls. `/api/health` stays open for
wake-up pings and Render's health check.

Everything a host reads is checked in: `render.yaml`, `Dockerfile`, `web/vercel.json`,
and `web/scripts/ignore-build.sh`, plus the `deploy` job in `.github/workflows/ci.yml`.
A person only connects accounts, pastes one secret into both hosts, and stores
Vercel's deploy hook for CI. `tests/test_deploy_config.py` pins that configuration.

Neither host puts a commit on the public demo before CI passes on it (ADR 0006,
"Hosting"): Render waits for GitHub's checks, and Vercel production deploys only
when CI calls its deploy hook. See [production waits for CI](#production-waits-for-ci).

The Streamlit window is gone from `master`. The old Community Cloud URL shows a
["This demo has moved" page](#repointing-the-streamlit-app) that links to the new window.

## Going live: the wizard

```text
scripts/deploy_wizard.sh           # walk through going live, stage by stage
scripts/deploy_wizard.sh --check   # re-verify the saved deploy, no prompts
```

The account steps only a person can do are in `scripts/deploy_wizard.sh`. It runs on
macOS, Linux, or WSL and needs `bash` and `curl`. Python 3.8+ runs the guided-story
checks, and npm runs the browser check. `gh` is optional. Its nine stages:

1. **Before you start**: checks the tools, and that `master` has `render.yaml`,
   the `Dockerfile`, and `web/`. Both hosts build `master`, so the parity and deploy
   PRs must be merged first. If the Render CLI is installed, it runs
   `render blueprints validate`.
2. **Proxy token**: generates `API_PROXY_TOKEN` (`openssl rand -hex 32`). Re-runs
   keep the saved token, so Render and Vercel stay in step.
3. **Render**: New → Blueprint → the repo → `master`, and the token pasted into the
   field the Blueprint asks for. The wizard then waits for `/api/health`, checks that
   `/api/meta` without the token answers 401, and takes a guided story with the token.
4. **Render Auto-Deploy**: confirms that Settings → Auto-Deploy reads "After CI
   Checks Pass". If the free plan does not offer it, the wizard captures the
   deploy hook and sets the `RENDER_DEPLOY_HOOK_URL` secret with `gh`
   ([fallback](#fallback-deploy-hook-from-ci)). You then set
   `autoDeployTrigger: off` yourself.
5. **Vercel**: imports the repo with Root Directory `web`, then checks that the
   production `*.vercel.app` domain loads.
6. **Vercel Deploy Hook**: creates a Deploy Hook for `master` (Settings → Git →
   Deploy Hooks) and stores it as the `VERCEL_DEPLOY_HOOK_URL` secret with `gh`, or
   says where to paste it on github.com. It can call the hook once, which deploys
   `master` and proves the URL works. Its `curl` reads the URL from stdin, so the
   hook's key stays out of the process list.
7. **Vercel variables**: sets `API_ORIGIN` and `API_PROXY_TOKEN` (Sensitive) for
   Production and Preview, and redeploys. It then checks the health route and a
   guided story through the proxy.
8. **Proxy check**: runs every check again, as for `--check`.
9. **Browser check**: runs `PLAYWRIGHT_BASE_URL=<vercel url> npm run test:e2e`.

Values go to `.env.deploy`, which is gitignored: the token, both URLs, and the hook
URLs. They never go to `.env`, because the API reads `.env`, and a token
there would make the local API refuse the local window. A stage whose result already
checks out says so and moves on, so re-running after a partial run is safe.
`--check` exits 1 if any check fails. It does not look for the GitHub secrets;
`gh secret list` shows them.

Where the wizard names a dashboard control it could not confirm, it says what to
look for instead. See [what was checked](#what-was-checked-against-current-docs).

## Environment variables

| Service | Variable | Value | Where it is set |
| --- | --- | --- | --- |
| Render (API) | `APP_MODE` | `live` | `render.yaml` |
| Render (API) | `PUBLIC_DEMO` | `true` | `render.yaml` |
| Render (API) | `DEMO_LIVE_SEC` | `true` | `render.yaml` |
| Render (API) | `ALLOW_PUBLIC_OPENAI` | `true` | `render.yaml` |
| Render (API) | `ALLOW_PUBLIC_TAVILY` | `true` | `render.yaml` |
| Render (API) | `SEC_USER_AGENT` | app name and contact email, e.g. `FinancialAnalystAgent (you@example.com)` | Render dashboard (`sync: false`). Without it the live runtime is locked: every thread runs on the recorded runtime, the window says "Live runtime is off on this server", and the API logs a warning at startup. |
| Render (API) | `OPENAI_API_KEY` | an OpenAI key | Render dashboard (`sync: false`). Optional: with it the rules planner asks the LLM planner about the turns it is unsure of ([ADR 0012](adr/0012-the-live-planner-is-a-rules-first-cascade.md)) and essays are written live; without it the rules planner plans alone and essays are recorded. |
| Render (API) | `TAVILY_API_KEY` | a Tavily key | Render dashboard (`sync: false`). Optional: without it the live runtime replays the recorded news. |
| Render (API) | `API_PROXY_TOKEN` | a random secret (for example `openssl rand -hex 32`) | Render dashboard. `render.yaml` declares it with `sync: false`, so the Blueprint prompts for it on first sync and never stores it. |
| Render (API) | `PORT` | `10000` by default | Render sets it. The image listens on `$PORT`. |
| Render (API) | `HOST`, `PYTHONUNBUFFERED` | `0.0.0.0`, `1` | `Dockerfile` |
| Vercel (window) | `API_ORIGIN` | `https://<render service>.onrender.com` (no trailing slash) | Vercel dashboard, Production **and** Preview |
| Vercel (window) | `API_PROXY_TOKEN` | the same secret as on Render | Vercel dashboard, Production **and** Preview, marked Sensitive |
| GitHub Actions | `VERCEL_DEPLOY_HOOK_URL` | Vercel's Deploy Hook URL for `master` | Repository secret. Required: without it, merges to `master` never reach the hosted window. |
| GitHub Actions | `RENDER_DEPLOY_HOOK_URL` | Render's deploy hook URL | Repository secret. Only for the [fallback](#fallback-deploy-hook-from-ci); leave unset otherwise. |

Neither Vercel variable is `NEXT_PUBLIC_`, so neither reaches the browser bundle.
Every other API setting keeps the default in `config.py` (thread TTL 7200 s, 25 turns
per thread, 150 live SEC requests per thread, and per visitor 30 new threads and 120
turns an hour). The public demo lands on the live
runtime, and visitors can switch to the recorded runtime, which needs no keys. Nothing caps
total OpenAI spend across threads, so set a monthly budget in the OpenAI dashboard.

The live runtime bounds what a slow or failing SEC can cost, also with defaults in
`config.py` (see `.env.example`):

| Setting | Default | What it bounds |
| --- | --- | --- |
| `SEC_TIMEOUT_SECONDS` | 10 | One connect or read. A timed-out request is not retried. |
| `SEC_REQUEST_DEADLINE_SECONDS` | 30 | One SEC request, body included, however slowly it arrives. A cache fill waits this long for another turn fetching the same file. |
| `SEC_MAX_RESPONSE_BYTES` | 64 MiB | One response after decompression. |
| `SEC_TURN_BUDGET_SECONDS` | 90 | A turn's SEC time in all. Companies not read by then show "Source unavailable" and the turn answers with the rest. |
| `TURN_TIMEOUT_SECONDS` | 150 | A whole turn. Past it the API ends the turn with an error and frees its thread and slot. |
| `SEC_BLOCK_PAUSE_SECONDS` | 600 | How long SEC requests stop after SEC's "Undeclared Automated Tool" page. A request during the pause is refused at once and its cells read "Source unavailable"; only a pause of 5 seconds or less, within the turn's time, is waited out. A `Retry-After` pauses requests the same way. |
| `SEC_CACHE_MAX_BYTES` | 1 GiB | The SEC disk cache, trimmed oldest files first. |
| `SEC_FILING_WATCH_SECONDS` | 300 | How often the API reads SEC's latest 10-Q and 10-K filings (two requests). A company's cached data then lasts until it files again, up to a week ([ADR 0013](adr/0013-cached-sec-data-lasts-until-the-company-files.md)). `0` turns it off, and cached data is fetched again after an hour. Only the API server starts it; a script or an MCP server keeps the hour. The watch needs the process to stay up: after a restart, cached data falls back to the hour until the watch has polled. |
| `SEC_WARM_COMPANIES` | 250 | With the filing watch on, the largest companies' SEC data is fetched in the background before anyone asks, largest first ([ADR 0014](adr/0014-a-warm-set-of-company-digests.md)). After a deploy the set fills in about four minutes; `0` turns it off. |
| `SEC_WARM_REQUESTS_PER_SECOND` | 2 | The warm-up's share of the SEC request rate. It also waits while any visitor's request is queued. |

**Who a visitor is.** The per-visitor limits count by client address. With
`API_PROXY_TOKEN` set, the API answers only the proxy and reads the visitor's address
from the proxy's `X-Client-IP` header. Without the token it trusts no header: uvicorn
runs with `proxy_headers` off, so `X-Forwarded-For` is ignored and the client is the
socket's peer. A local run is then counted per caller, but an API behind a proxy that
does not send the token sees every visitor as the proxy, and they share one set of
limits.

Render prompts for `sync: false` values only when a Blueprint is first created. On an
existing service, add `SEC_USER_AGENT` (and the optional keys) under the service's
**Environment** tab before the `render.yaml` change syncs, so the first live request
does not fail for want of it.

## Render: the analysis API

`render.yaml` is a Blueprint with one service:

| Field | Value | Why |
| --- | --- | --- |
| `type` / `runtime` | `web` / `docker` | Builds the repo's `Dockerfile` (context `.`). Both are fixed once the service exists. |
| `plan` | `starter` | $7/month (upgraded from `free` on 28 September 2026). 512 MB of RAM and half a CPU. Always on: no idle sleep, so no minute-long wake. Keep this in step with the dashboard, because a Blueprint sync applies it. |
| `region` | `virginia` | Next to Vercel's `iad1` functions. Fixed once the service exists. |
| `branch` | `master` | Deploys only `master`, the default branch. |
| `healthCheckPath` | `/api/health` | Open without the proxy token. |
| `numInstances` | `1` | Required: the file-backed thread store and per-thread turn lock need one process. |
| `autoDeployTrigger` | `checksPass` | Deploys a commit only after all its GitHub checks pass. |
| `buildFilter.paths` | `Dockerfile`, `.dockerignore`, `pyproject.toml`, `uv.lock`, `src/**` | Commits that change only `web/`, docs, or tests do not rebuild the API. |

Create it once: Render dashboard → **New** → **Blueprint** → connect the GitHub repo →
pick `master`. Render reads `render.yaml`, asks for `API_PROXY_TOKEN`, and creates
`financial-analyst-api`. Later edits to `render.yaml` sync on push.
[The wizard](#going-live-the-wizard) walks through each click.

### Deploys wait for CI

With `autoDeployTrigger: checksPass`, Render waits for every GitHub check on the
commit: the `check`, `image`, `web`, and `deploy` jobs in `.github/workflows/ci.yml`,
plus any check another app posts (Vercel's, on pull request branches). Render counts a check as passed when it ends in
success, neutral, or skipped. A commit with **no** checks is never auto-deployed, and
neither is one where any check fails. A commit message containing `[skip render]`
skips the deploy.

### Fallback: deploy hook from CI

If `checksPass` is not offered for the free instance, CI can deploy instead:

1. Render → the service → **Settings** → **Deploy Hook**: copy the URL.
2. GitHub → **Settings** → **Secrets and variables** → **Actions**: add
   `RENDER_DEPLOY_HOOK_URL`.
3. In `render.yaml`, set `autoDeployTrigger: off`, so a commit is not deployed twice.

The `deploy` job in CI then POSTs to the hook on pushes to `master`, after `check`,
`image`, and `web` pass, before it calls Vercel's. Without the secret, it skips that
step.

## Vercel: the window

| Setting | Value | Where |
| --- | --- | --- |
| Framework preset | Next.js | Detected |
| Root Directory | `web` | Vercel dashboard → Project → **Settings** → **Build and Deployment** (asked when importing the repo) |
| Node.js | 22.x | `web/package.json` `engines`, matching `.nvmrc` |
| Ignored Build Step | `sh scripts/ignore-build.sh` | `web/vercel.json` `ignoreCommand`, which overrides the dashboard field |
| Git deploys of `master` | off | `web/vercel.json` `git.deploymentEnabled` `{"master": false}`. Production deploys through the Deploy Hook; other branches still get previews. |
| Deploy Hook | `ci-master`, branch `master` | Vercel dashboard → Project → **Settings** → **Git** → **Deploy Hooks**; its URL is the `VERCEL_DEPLOY_HOOK_URL` secret |
| Fluid compute | on | `web/vercel.json` `"fluid": true`. It is already the default for new projects. |
| Function region | `iad1` (Washington, D.C.) | `web/vercel.json` `regions`. Hobby runs functions in one region, and `iad1` is its default. |
| Proxy duration | 300 s | `export const maxDuration = 300` in the proxy route. That is the Hobby maximum under Fluid compute, enough for a long streamed turn. |
| Environment variables | `API_ORIGIN`, `API_PROXY_TOKEN` | See [the table above](#environment-variables) |

Vercel reads `vercel.json` from the Root Directory, so it lives at `web/vercel.json`.

**Ignored build step.** Vercel runs `web/scripts/ignore-build.sh` from `web/` before
each build. It compares `HEAD` with `VERCEL_GIT_PREVIOUS_SHA`, the commit of the
branch's last successful deployment, and skips the build (exit 0) only when nothing
under `web/` changed. Python-only commits therefore do not rebuild the window. It
builds (exit 1) when that is unknown: a branch's first deployment, or a previous commit
outside Vercel's shallow clone. Production builds come from the deploy hook, and users
report Vercel runs this step for them too. The comparison is still with `master`'s
last successful deployment, not the parent commit, so a `web/` change from a commit
whose CI failed ships with the next commit that passes. A hook call after
Python-only commits is skipped, and production keeps serving the same window. To
rebuild anyway, use **Redeploy** on the production deployment.

**Previews call the production API.** Set `API_ORIGIN` and `API_PROXY_TOKEN` for the
Preview environment too, with the same values. A preview then talks to the production
Render service. That is safe because every hosted thread runs the recorded runtime, and
the three-PR order lands API changes before the UI that depends on them. Previews
still build on push, before CI finishes; they sit behind Vercel's login (Deployment
Protection) and are not the public demo.

### Production waits for CI

`web/vercel.json` sets `"git": {"deploymentEnabled": {"master": false}}`, so a push to
`master` does not deploy the window. Instead, the `deploy` job in
`.github/workflows/ci.yml` runs on pushes to `master` once `check`, `image`, and `web`
pass (lint, types, tests, the image smoke test, and the Playwright check), and POSTs
to the `VERCEL_DEPLOY_HOOK_URL` secret. Vercel then builds `master` as a production
deployment. One job calls both hooks: Render's (only in the
[fallback](#fallback-deploy-hook-from-ci)) and then Vercel's, so one gate decides
when the API and then the window go out.

A deploy hook builds the branch's latest commit, not a given one. The job therefore
first checks that its commit is still the tip of `master`. If a newer commit has
landed, it calls no hook, and the newer commit's own run deploys once its checks
pass. A push that lands in the seconds between that check and the POST can still
ship before its own CI finishes; nothing on Vercel's side closes that gap without a
deploy token in CI.

The per-branch form matters. A plain `"deploymentEnabled": false` would also turn
off previews, and one user reports it blocked a production Deploy Hook as well.

Until `VERCEL_DEPLOY_HOOK_URL` is set, the job skips that step and merges to
`master` do not reach the hosted window. Stage 6 of the wizard sets it.

## Checking a deploy

```text
# the API, directly: health is open, everything else needs the token
curl -sS https://<render service>.onrender.com/api/health
curl -sS -o /dev/null -w "%{http_code}\n" https://<render service>.onrender.com/api/meta   # 401
SMOKE_PROXY_TOKEN=<token> python3 scripts/smoke_api_image.py --base-url https://<render service>.onrender.com

# through the window's proxy (no token: the proxy adds it)
curl -sS https://<project>.vercel.app/api/health
python3 scripts/smoke_api_image.py --base-url https://<project>.vercel.app

# the browser check against the hosted window
cd web && PLAYWRIGHT_BASE_URL=https://<project>.vercel.app npm run test:e2e
```

The smoke script reads the token from `SMOKE_PROXY_TOKEN`, so it stays out of the
process list; `--proxy-token <token>` also works and wins when both are given.

The first call after 15 idle minutes waits about a minute while Render wakes the
service. The window says "Waking the analysis service…" in the meantime.

## What was checked against current docs

### Verified at go-live (25 September 2026)

Going live settled several of the open points below against the real services:

- **Blueprint schema.** `render blueprints validate` (Render CLI, built from
  render-oss/cli) accepts `render.yaml`. Its only complaint was a missing `repo:`,
  which the dashboard fills in when you import a Blueprint from a repo; the file now
  names it so the standalone validator passes too.
- **"After CI Checks Pass" on the free plan.** Render's API accepted
  `autoDeployTrigger: checksPass` for the free web service. The `deploy` job still
  skips the Render hook while `RENDER_DEPLOY_HOOK_URL` is unset.
- **How the service was created.** The API service was created through Render's REST
  API with the Blueprint's settings, not through a Blueprint sync. `render.yaml` stays
  the record of those settings.
- **Auto-deploy needs Render's GitHub App.** Created from the public repo URL, the
  service built its first deploy but received no pushes: merging the cutover
  (`3516afd`) left Render on the previous commit, with no event for the push. Render
  hears about pushes through its GitHub App. The dashboard's Blueprint flow has you
  connect GitHub; creating the service through the REST API skipped that step. The
  app was then installed on this repository (**Only select repositories**), and the
  missed commit was deployed by hand (`POST /v1/services/<id>/deploys` with its
  `commitId`, or **Manual Deploy** in the dashboard). If Render still misses a push that touches the build filter, set
  `RENDER_DEPLOY_HOOK_URL` so CI's `deploy` job triggers it.
- **Vercel production through a deploy hook.** With `git.deploymentEnabled.master:
  false`, a Deploy Hook for `master` produced a `production` deployment that became
  the live domain. Production deploys therefore need the `VERCEL_DEPLOY_HOOK_URL`
  repository secret for CI's `deploy` job.
- **Deployment Protection.** The project's default protection
  (`all_except_custom_domains`) protects preview and per-deployment URLs. The
  production domains, `onfile-analyst.vercel.app` (added 30 September 2026 with the
  Onfile rename) and the original `financial-analyst-agent-ten.vercel.app`, are public
  (200 without a login). The unsuffixed `financial-analyst-agent.vercel.app` belongs to another
  project.
- **End to end.** The API refuses calls without the proxy token (401). A guided story
  runs through the Vercel proxy, and the Playwright suite can run against the hosted URL
  with `PLAYWRIGHT_BASE_URL`.


This configuration was written on 25 September 2026. render.com and vercel.com were not
reachable from the build environment, so the fields were checked against these
sources:

- **Render Blueprint fields** (`runtime: docker`, `plan: free`, the `virginia` region,
  `healthCheckPath`, `numInstances`, `buildFilter.paths`, `envVars` with `sync: false`,
  and `autoDeployTrigger` with `commit` / `checksPass` / `off`, which replaces the
  deprecated `autoDeploy`) come from Render's own agent skills (render-oss/skills,
  `render-blueprints` and its field reference, MIT). They were cross-checked with
  search excerpts of render.com/docs/blueprint-spec. `tests/test_deploy_config.py`
  checks `render.yaml` against that field list. The official schema at
  `https://render.com/schema/render.yaml.json` was unreachable, so it was **not**
  validated against it. Run `render blueprints validate` (Render CLI 2.7+) or let the
  Blueprint sync report errors.
- **"After CI Checks Pass"** comes from search excerpts of render.com/docs/deploys and
  Render's changelog: success, neutral, and skipped count as passed, and a commit with
  zero checks is not deployed. No source said whether the free instance offers it,
  which is why the deploy hook fallback exists.
- **Render free-instance limits**: sleep after 15 idle minutes and about a minute to
  wake are from ADR 0006. The CPU share was not confirmed: ADR 0006 says 0.1 CPU, and
  one secondary reference (OpenAI's `render-deploy` skill) lists 0.5. Check Render's
  pricing page if it matters.
- **Vercel production gated on CI** (checked 25 September 2026, from search excerpts
  of vercel.com/docs/project-configuration/git-configuration and
  vercel.com/docs/deploy-hooks, plus public GitHub pull requests; vercel.com and
  community.vercel.com were blocked): `git.deploymentEnabled` takes `false` or an
  object of branch names or globs, and `{"<branch>": false}` turns off automatic
  deploys of that branch only. Deploy Hooks live under Settings → Git → Deploy
  Hooks, are bound to one branch, accept GET or POST with no payload, and build the
  branch's latest commit. `vercel deploy-hooks create <name> --ref <branch>` exists
  in Vercel CLI 60.0.1 (its `--help` was run). A September 2026 pull request
  (VNCHub/nossa-conta#19) reports that the object form `{"main": false}` kept a
  production Deploy Hook working while the global `false` blocked it. **Not
  verified**: that a hook build of the production branch becomes the production
  deployment (docs imply it but excerpts did not say so outright); whether the
  project import's first deploy runs despite the setting (the wizard handles both);
  and what `VERCEL_GIT_PREVIOUS_SHA` holds in a hook build. Forum reports say the
  Ignored Build Step runs for hook builds; `ignore-build.sh` builds whenever that
  variable is empty or unknown, so the worst case is an unneeded build. Vercel CLI's
  config validator accepts any `git` value, and the published schema
  (openapi.vercel.sh) was unreachable, so `git.deploymentEnabled` was **not**
  schema-validated.
- **Vercel**: from search excerpts of vercel.com docs and changelogs. Fluid compute on
  Hobby has a 300 s default and maximum duration. `"fluid": true` in `vercel.json` turns
  it on per deployment, and it is the default for new projects since 23 April 2025.
  `ignoreCommand` skips the build on exit 0 and builds on 1. `VERCEL_GIT_PREVIOUS_SHA`
  is set only when an Ignored Build Step is configured, and it is empty on a branch's
  first deployment. `web/vercel.json` passes the config validator in Vercel CLI 60.0.1,
  but that validator does not check `fluid`, `regions`, or `ignoreCommand` at the top
  level.
- **Dashboard steps in the wizard** come from search excerpts of Render's Blueprint
  and deploy docs and Vercel's monorepo, environment-variable, and
  deployment-protection docs, not from the dashboards themselves. These are: New →
  Blueprint → Connect → Deploy Blueprint; the `sync: false` prompt on first creation;
  Settings → Auto-Deploy and Deploy Hook; Import → Root Directory → Edit; Settings →
  Git → Deploy Hooks; Settings → Environment Variables with the Sensitive switch;
  Redeploy. Each step the wizard
  could not confirm also says where else to look.
- **Deployment Protection**: Standard Protection is on by default and puts deployment
  URLs behind a Vercel login. Sources disagree on whether the project's own
  `<name>.vercel.app` production domain stays public: a July 2025 changelog says
  Standard Protection now covers "all except production custom domains". If the
  window answers 401 or 403, the wizard names the Deployment Protection setting to
  change.

## Repointing the Streamlit app

Links to the old URL,
[financial-analyst-agent-project.streamlit.app](https://financial-analyst-agent-project.streamlit.app),
keep working after cutover. The orphan `streamlit-redirect` branch holds one page,
`streamlit_app.py`, that says "This demo has moved", with a button to the new window.
It also holds its own `requirements.txt` (Streamlit only), the dark theme in
`.streamlit/config.toml`, and a README. It shares no history with `master` and is never
merged. The button opens the `DEMO_URL` secret. Until that is set, or if it is not an
`https://` URL, the button opens the GitHub repo and the page says the new address is
not live yet.

**When:** after the Next.js window is live (ticket 11) and **before** the PR that
deletes Streamlit (ticket 14) is merged. Community Cloud redeploys on every push to the
app's branch, so an app still on `master` would break when `app.py` is deleted.

Community Cloud cannot change a deployed app's branch or main file. You delete the app
and deploy it again with the same subdomain:

1. Check that `streamlit-redirect` is on GitHub:
   `git ls-remote origin streamlit-redirect` prints one line.
2. Open [share.streamlit.io](https://share.streamlit.io). On the
   `financial-analyst-agent-project` app, open the **⋮** menu → **Delete**, and confirm.
   The old app's secrets are not needed again.
3. **Create app** → deploy a public app from GitHub, and fill in:
   - Repository: `bpyman/financial-analyst-agent`
   - Branch: `streamlit-redirect`
   - Main file path: `streamlit_app.py`
   - App URL: `financial-analyst-agent-project`
4. **Advanced settings** → **Secrets**: paste the hosted window's URL as a quoted
   top-level string, then **Save** and **Deploy**:

   ```toml
   DEMO_URL = "https://<project>.vercel.app"
   ```

5. Open the old URL. It should say "This demo has moved", and **Open the new demo**
   should land on the Next.js window. If the button reads **View the project on
   GitHub** instead, `DEMO_URL` is missing, unquoted, or not `https://`.

If the App URL field says the subdomain is taken, the deleted app has not released it
yet. Deploy under any name, wait a few minutes, then set it in the app's **Settings** →
**General**. The subdomain can be changed at any time. To change the address later,
edit `DEMO_URL` in the app's **Settings** → **Secrets**. If the page still shows the
old value after a minute, **Reboot** the app from the **⋮** menu.

The page is a free Community Cloud app too, so after a long idle spell a visitor may
first see the button that wakes it.

These steps come from search excerpts of Streamlit's Community Cloud docs ("Rename or
change your app's GitHub coordinates": delete, change, redeploy; subdomains can be
changed at any time), because docs.streamlit.io was not reachable from the build
environment. To run the page locally, see the branch's README.

**Done on 25 September 2026.** The steps above worked as written. The deleted app's
subdomain was free at once, so the fallback was not needed. **Advanced settings**
defaulted to Python 3.14; the redirect was deployed on 3.12, the old app's version.
`DEMO_URL` is `https://financial-analyst-agent-ten.vercel.app`, and the old URL's
**Open the new demo** button opens it.
