# pravaha-edge — Minimal Cloudflare Worker for PRAVAHA

Read-through cache + proxy in front of the existing Render backend
(`https://pravaha-hkwt.onrender.com`), plus a scheduled public-data refresh and
a static deployment of the same frontend.

**Live:** <https://pravaha-edge.aadarshakarki.workers.dev>

**Additive only:** the Python backend remains authoritative, the Netlify site
keeps its own working `/api/*` proxy, and Render authentication is unchanged.

## Deployment modes

| URL | Frontend | API path |
|---|---|---|
| `https://pravaha-edge.aadarshakarki.workers.dev` | served by `[assets]` from `web/static` | same-origin Worker → Render (allowlisted GETs cached) |
| `https://pravahanepse.netlify.app` | Netlify publishes `web/static` | Netlify `/api/*` proxy → Render |

Both use the same files and the same friend-token boundary. The Worker never
stores private records or report artifacts; jobs and downloads stay on Render.

## What it does

- Proxies every request to the Render backend, preserving `X-Friend-Token` /
  `Authorization` and all other headers.
- Caches **only** allowlisted public read-only market-data `GET`s (subset of
  `megatool/friend_access.py` `FRIEND_ROUTES`), and only when a friend token
  is present on the request.
- Never caches: private/owner-only routes (`FRIEND_DENIED_PREFIXES`), POSTs,
  `/api/health`, file exports, non-200 responses, or `no-store`/`private`/
  `Set-Cookie` responses.
- Serves the static frontend from the Worker's asset bundle. `/api/*` and
  `/edge/*` are never served from assets, so an API 404 stays a JSON 404.
- Handles CORS for the Netlify origin and any loopback development origin;
  preflight is answered at the edge.
- Caches the public BABA selection metadata and range forecasts
  (`/api/baba/components`, `/api/baba/research/catalog`,
  `/api/baba/volatility/<symbol>`) with a longer TTL. Report jobs, exports and
  downloads are matched by neither cache rule and therefore always pass through
  with `Cache-Control: no-store`.

## Configure

Edit `wrangler.toml` `[vars]`:

| Var | Default | Purpose |
|-----|---------|---------|
| `ORIGIN_URL` | `https://pravaha-hkwt.onrender.com` | Render backend |
| `FRONTEND_ORIGIN` | `https://pravahanepse.netlify.app` | CORS allowlist (must match Render's `MEGATOOL_FRIEND_ORIGIN`) |
| `EDGE_ORIGIN` | `https://pravaha-edge.aadarshakarki.workers.dev` | The Worker's own origin (allowed when the app is served here) |
| `DEFAULT_CACHE_TTL` | `60` | Fallback edge TTL (seconds) |

Optional hardening:
```
wrangler secret put MEGATOOL_FRIEND_TOKEN
```
If set, the Worker verifies the browser token with a constant-time compare
before serving from cache. Leaving it unset keeps Render as the single source of
truth.

## Scheduled YONEPSE refresh (Cron Trigger)

A Cron Trigger (`*/10 * * * *`) runs two independent jobs on every tick:

1. `runScheduledRefresh()` — the YONEPSE refresh described below.
2. `warmOrigin()` — fetches the always-public `ORIGIN_URL/api/health` with a
   60-second budget so Render's free instance does not spin down after ~15
   minutes of inactivity. This is what removes the 30-60 second cold start;
   the cached GETs alone cannot do that. A failed warm-up is recorded in the
   tick's return value and never treated as an ingestion failure.

The refresh itself is:

- **Market-aware**: outside Mon–Fri 11:00–16:00 NPT the handler returns
  `{skipped:"outside-market-window"}` without any upstream request or KV write.
  The keep-warm ping still runs, because the frontend must stay fast outside
  market hours too.
- **Raw first**: reads `raw.githubusercontent.com/Shubhamnpk/yonepse/main`, then
  the Pages mirror. *Measured 2026-10-19: the Pages mirror served `status.json`
  three days stale (`last_checked` 2026-10-16 vs 2026-10-19 on raw), which made a
  healthy, market-closed source look `stale`. Raw-first fixes that — the run now
  labels it `last-close`.*
- **Validated**: every payload is shape-checked (a status without a boolean
  `is_open`, an empty array, or unparseable JSON is rejected).
- **Never destructive**: a failed critical dataset (`status`, `indices`,
  `quotes`) leaves the last good snapshot untouched and records the failure.
- **Deduplicated**: `retrieved_at` (when we fetched) and `source_updated_at`
  (the newest source stamp) are recorded separately; an unchanged payload is
  recorded as `unchanged` / `closed-unchanged` and the snapshot is **not**
  rewritten.
- **No fabrication**: the LTP board is summarised (counts + timestamps). No
  OHLCV candles are produced and `price_bars` is never touched.

Storage is **KV only for the small public snapshot + metadata** (~3.7 KB
measured). The 515,648-bar historical database is NOT stored here.

### Edge endpoints (public, read-only)

| Route | Returns |
|---|---|
| `GET /edge/yonepse/snapshot` | the last good compact snapshot (`max-age=60`) |
| `GET /edge/yonepse/health` | ingestion metadata: last success/failure, consecutive failures, freshness (`no-store`) |

### Bindings

| Binding | Kind | Notes |
|---|---|---|
| `PRAVAHA_KV` | KV namespace | **required** — create it (below) |
| `ORIGIN_URL` | var | Render backend |
| `FRONTEND_ORIGIN` | var | CORS allowlist |
| `DEFAULT_CACHE_TTL` | var | edge cache fallback (s) |
| `YONEPSE_BASES` | var (optional) | comma-separated override of the base order |

Create the namespace and paste the id into `wrangler.toml`:

```
npx wrangler kv namespace create PRAVAHA_KV
```

No secret is required. `MEGATOOL_FRIEND_TOKEN` is **not** needed by the cron
(the refresh reads public data only).

## Commands

```
npm install
npm run dev          # local preview on http://127.0.0.1:8787
npm run build        # no-op (plain ES module)
npm run deploy       # publish the Worker + 3.2 MB of web/static assets
npm run tail         # live logs
npm test             # unit tests (vitest)
npm run test:integration  # end-to-end smoke test (boots mock origin + wrangler dev)
```

## Frontend wiring (current)

`web/static/index.html` deliberately keeps:

```html
<meta name="megatool-api-base" content="" />
<meta name="megatool-edge-base" content="https://pravaha-edge.aadarshakarki.workers.dev" />
```

- `megatool-api-base` stays **empty**, so the app is same-origin everywhere:
  on Cloudflare it calls the Worker, on Netlify it calls the Netlify proxy, and
  locally it calls the FastAPI server. This is the safest arrangement and the
  one `tests/test_deploy_access.py` enforces.
- `megatool-edge-base` is used only by the public **Data → Scheduled ingestion**
  card, which reads `/edge/yonepse/health`. It is public, read-only metadata.

Opening the workers.dev URL therefore gets the fast static frontend, the cron
refresh and the keep-warm ping without changing Netlify or Render.

## Deploy & verify

```
npm install
npx wrangler kv namespace create PRAVAHA_KV     # paste the id into wrangler.toml
npx wrangler deploy                              # prints the workers.dev URL AND applies the crons in [triggers]
```

`wrangler deploy` applies the `[triggers] crons` automatically; no extra step
is needed. (`wrangler triggers deploy` only exists for `wrangler versions upload`.)

Verify:

```
# 1. the cron is registered (dashboard → Worker → Triggers, or:)
npx wrangler deployments status
# 2. watch a run (a run inside the window logs its result; outside it is a no-op)
npx wrangler tail --format pretty
# 3. what the cron wrote
curl -s https://pravaha-edge.<account>.workers.dev/edge/yonepse/health | jq
curl -s https://pravaha-edge.<account>.workers.dev/edge/yonepse/snapshot \
  | jq '{is_open,quote_count,source_updated_at,retrieved_at,origin}'
# 4. cached vs uncached latency (X-Pravaha-Cache: HIT|MISS|BYPASS)
for i in 1 2; do curl -s -o /dev/null -D- -H "X-Friend-Token: <token>" \
  "https://pravaha-edge.<account>.workers.dev/api/bars/NABIL" \
  | grep -iE "x-pravaha-cache|cf-cache-status"; done   # 1st MISS, 2nd HIT
```

The first scheduled run may take up to 10 minutes to appear. The health route
also reports `runs`, `last_run_reason` and the keep-warm-independent ingestion
result, so a stalled cron is visible instead of silent.

## Rollback

The Worker is **additive**: the Render backend stays authoritative and the
Netlify site keeps working while `megatool-api-base` is empty. To roll back:

1. In `web/static/index.html`, set `megatool-api-base` back to `""` (same-origin
   → Netlify's `/api/*` proxy → Render). Redeploy Netlify.
2. Optionally `npx wrangler delete` (removes the Worker and its cron). The KV
   data is public market metadata only; deleting it loses nothing durable.
3. Render and Netlify configuration are never modified by this Worker.

## Safety notes

- Do not bind Worker routes to the Netlify domain (would interfere with the
  live site). Keep `workers_dev = true`.
- Do not cache private user data or expose tokens. Cached responses are
  token-independent public market data only.
- The keep-warm ping prevents *idle* spin-down; it cannot make the first boot
  after a deploy instant, and it cannot fix OOM. The Worker does not change
  Render's memory limits.
- Backend (Python/FastAPI/DuckDB) is unchanged and remains authoritative.
