# Deployment Architecture

Status: **recommendation + local scaffolding only.** Nothing in this document has
been deployed, published or exposed. The persistent services and the DuckDB store
stay on an always-on host owned by you, and the NEPSE collector stays **gated off**
until you make the authorization ruling.

---

## 1. Component flow

```
 ┌─────────────────────────────┐        ┌──────────────────────────────────────────┐
 │  Friend's browser           │        │  Your browser (owner)                    │
 │  https://<site>.netlify.app │        │  http://127.0.0.1:8710                   │
 │  (static frontend)          │        │  (same app, same origin as the API)      │
 └──────────────┬──────────────┘        └───────────────────┬──────────────────────┘
                │  HTTPS + X-Friend-Token                    │  loopback, no token
                ▼                                            ▼
        ┌────────────────────────────  edge  ────────────────────────────┐
        │  Authenticated tunnel / reverse proxy (Cloudflare Tunnel, TLS)  │
        └───────────────────────────────┬─────────────────────────────────┘
                                        │  forwards to 127.0.0.1:8710
                                        ▼
                       ┌────────────────────────────────────────────┐
                       │  ALWAYS-ON HOST                            │
                       │                                            │
                       │  uvicorn  megatool.api:app                 │
                       │    ├─ FriendAccessMiddleware  (deny-by-default)
                       │    ├─ CORSMiddleware          (Netlify origin only)
                       │    └─ /api/*  read-mostly market routes     │
                       │                                            │
                       │  Collector (gated, systemd timer / launchd)│
                       │    scripts/benchmark_market_hours.py       │
                       │    scripts/ingest_nepse_official_quotes.py │
                       │    scripts/check_source_health.py          │
                       │           │ writes                         │
                       │           ▼                                │
                       │  data/processed/megatool_market.duckdb     │  ← system of record
                       │  data/processed/megatool_state.sqlite      │
                       │  data/health/source_health.json            │  ← cert/circuit cache
                       └────────────────────────────────────────────┘

 Netlify:  serves web/static only.  It never sees the token, the database or a secret.
```

The collector and the API **must be co-located** on the same host: the collector
writes the DuckDB file the API reads, and DuckDB is single-writer. They are two
processes on one machine, not two services.

---

## 2. Why the backend cannot run on Netlify

Netlify is a static host plus short-lived serverless functions. That is a poor fit
for this backend for four concrete reasons:

1. **No persistent process.** The app is a long-lived uvicorn server with a warm
   in-process store; serverless invocations are cold-started and discarded.
2. **No durable local disk.** DuckDB needs a writable, persistent local file. A
   serverless filesystem is ephemeral and per-instance.
3. **Single-writer database.** DuckDB permits one writer; the collector and API
   depend on co-location that serverless cannot provide.
4. **Gated environment.** The collector refuses to run without
   `MEGATOOL_NEPSE_API_AUTHORIZED=1`, and that flag plus future tokens belong in a
   controlled server environment, not a public build.

Netlify is used **only** for the static frontend, which needs no build step
(`web/static/`).

---

## 3. Hosting options

| Option | Cost / mo | Uptime | Maintenance | Notes |
|---|---|---|---|---|
| **A. Your always-on machine + Cloudflare Tunnel** *(recommended default)* | $0 | Home uptime | Lowest effort; the store never leaves your house | You already run the server here. A named tunnel gives a stable HTTPS hostname with no open inbound ports. |
| **B. Small VPS (Hetzner/DO, 2 GB)** | ~$5–7 | ~99.9% | You own patching, backups, TLS | Best uptime and reachability; the market store lives off-site. |
| **C. Raspberry Pi on your LAN** | ~$0 (+ hardware) | Home uptime | Moderate | Cheap and private, but SD-card reliability and ISP reachability are weaker. |

**Recommended default: A first.** It is the smallest change from today (the server
already runs on this machine), costs nothing, keeps the DuckDB file local, and
through a tunnel gives a real HTTPS origin for the Netlify frontend. Move to B if
uptime becomes a requirement; the code is unchanged because the boundary lives in
the app, not in the host.

---

## 4. Network boundary and authentication

* **Owner** = a request from a loopback address (`127.0.0.1`, `::1`, `localhost`).
  The owner is never challenged and sees every route, exactly as today.
* **Friend** = every other client. A friend must send a valid shared read-only
  token, and may only touch the routes in the allowlist (§6). Anything else is
  denied by default.

Implementation: `megatool/friend_access.py`.

| Situation | Result |
|---|---|
| Loopback, no token | `200` (owner) |
| Non-loopback, no token | `401` |
| Non-loopback, wrong token | `401` |
| Non-loopback, valid token, allowlisted route | routed normally |
| Non-loopback, valid token, **unlisted** route | `403` |
| `OPTIONS` (CORS preflight) | passed to `CORSMiddleware` (carries no data) |

Rules that make this a real boundary:

* **CORS is not authentication.** CORS is limited to `http://127.0.0.1`,
  `http://localhost`, and the exact `MEGATOOL_FRIEND_ORIGIN`; the token and the
  allowlist are what actually authenticate and authorise.
* The token is compared **server-side** with `hmac.compare_digest`, is never
  logged, never echoed in an error body, and **rotates** whenever you change the
  env var.
* The boundary activates only when `MEGATOOL_FRIEND_TOKEN` is set. Until then the
  process is owner-only and must stay bound to `127.0.0.1`.
* **Never expose the local dev server directly to the internet.** Use the tunnel.
* If you later want per-person accounts, replace the shared token with a small
  user table and the same middleware — the allowlist and route table do not change.

---

## 5. Storage, what syncs, and backups

* **System of record:** `data/processed/megatool_market.duckdb` (market bars,
  quotes, indices, floorsheet) plus `data/processed/megatool_state.sqlite`
  (app state). These **stay local to the always-on host.**
* **`data/health/source_health.json`** is a small runtime cache (last certificate
  and circuit check) read by `/api/sources`. It is never the source of truth.
* **Nothing personal syncs to the friend.** Journals, ledgers, the portfolio,
  planning and everything under `AI Trading Nipsy/` never leave the host and are
  not on the friend allowlist. There is no friend-facing datastore — the friend
  reads the same read-only market views the owner does.
* **Backup (before enabling any future integration):**
  1. Stop the API *and* the collector so no writer is active.
  2. `cp data/processed/megatool_market.duckdb "backups/market-$(date +%F).duckdb"`
     (also copy `megatool_state.sqlite`).
  3. Verify the copy opens read-only and row counts look right.
  4. `data/raw/` is re-downloadable and regenerable; it does not need backing up.

---

## 6. Routes exposed to a friend (explicit allowlist)

Deny-by-default: **only** these are reachable by a friend token. Everything else —
including every personal, write and admin route — is `403`.

| Method | Route |
|---|---|
| GET | `/api/health`, `/api/status`, `/api/sources` |
| GET | `/api/quotes`, `/api/securities` |
| GET | `/api/dashboard`, `/api/quality`, `/api/regime`, `/api/regime/history` |
| GET | `/api/bars/{symbol}` and `/weekly`, `/monthly`, `/indicator`, `/structure`, `/fibonacci`, `/levels`, `/elliott`, `/harmonic` |
| GET | `/api/indicators` |
| GET | `/api/screen/presets`, `/api/screen/export.csv` |
| POST | `/api/screen`, `/api/rank`, `/api/backtest`, `/api/walk-forward` |
| GET | `/api/strategies` |
| GET | `/api/fundamentals/summary`, `/api/fundamentals/compare`, `/api/fundamentals/{symbol}`, `/api/fundamentals/{symbol}/ratios` |
| GET | `/api/floorsheet/sessions`, `/api/floorsheet/summary`, `/api/floorsheet/trend` |
| GET | `/api/forecast/models` |

**Explicitly denied to friends** (personal, write, or admin): `/api/portfolio*`,
`/api/journal*`, `/api/planning*`, `/api/alerts*`, `/api/written-pdf*`,
`/api/research*` (this includes the personal research workspace), `/api/agent*`,
`/api/news/import`, `/api/fundamentals/import`, `/api/floorsheet/import`, and every
other unlisted route. Likewise, nothing outside `/api` is served to a friend.

---

## 7. Transport: how freshness reaches the UI

The dashboard already **polls** via a single `api()` helper in
`web/static/app.js`. **Keep polling.** It is the smallest change, needs no new
server code, survives the Netlify/backend split without CORS complications, and is
sufficient for data that updates on the order of seconds to minutes.

* SSE or WebSocket would be a **redesign** and would add a stateful connection for
  no measured benefit at this cadence. Revisit only if the market-hours benchmark
  shows the source updates faster than the polling interval can usefully show.
* Freshness is already explicit: `/api/quotes` returns `freshness_class`
  (`fresh` / `delayed` / `stale` / `unknown`) and `age_minutes` **per quote**, plus
  a summary; a quote can never be shown without its class. `?max_age_minutes=`
  filters stale rows out entirely.
* Recommended UI states map straight from that data: `fresh` → live, `delayed` →
  delayed, `stale` → stale, a failed request → **disconnected**, and
  `available: false`/no rows → **unavailable**. "Unavailable" is never rendered as
  a `0`.

The only frontend edit made for deployment is that `api()` prefixes requests with
`API_BASE` (empty by default = same origin), read from
`<meta name="megatool-api-base">` or `window.MEGATOOL_API_BASE`, and attaches a
runtime-supplied friend token from `sessionStorage` when present.

---

## 8. Environment variables

See `.env.example`. Summary of the ones that matter for deployment:

| Variable | Purpose | Safe default |
|---|---|---|
| `MEGATOOL_HOST` / `MEGATOOL_PORT` | Bind address | `127.0.0.1` / `8710` |
| `MEGATOOL_DATA_DIR` | Store location | `./data` |
| `MEGATOOL_NEPSE_API_AUTHORIZED` | Enables the NEPSE collector | `0` (off) |
| `MEGATOOL_INTEGRATION_AUTHORIZED` | Enables store writes | `0` (off) |
| `MEGATOOL_FRIEND_TOKEN` | Enables the friend boundary | empty (owner-only) |
| `MEGATOOL_FRIEND_ORIGIN` | Exact CORS origin of the Netlify site | empty |
| `MEGATOOL_FRIEND_TRUST_LOOPBACK` | Treat loopback as owner | `1` |
| `MEGATOOL_HEALTH_PATH` | Health cache path | `data/health/source_health.json` |

**Secrets never land in the frontend.** `.env` is git-ignored; API keys and the
friend token are read only by the server. There are no build-time public variables
and no secret in `web/static/`. The friend token is entered at runtime and kept in
`sessionStorage`.

---

## 9. Deployment and rollback

### Deploy (always-on host)

1. Back up the DuckDB and SQLite files (§5).
2. `git pull` (or copy the tree) — **do not** rebuild the frontend; it is static.
3. `cp .env.example .env`, set `MEGATOOL_HOST=127.0.0.1`, a strong
   `MEGATOOL_FRIEND_TOKEN`, and `MEGATOOL_FRIEND_ORIGIN`.
4. Start the API: `megatool serve` (binds `127.0.0.1:8710`).
5. Start the tunnel pointing at `127.0.0.1:8710`; the tunnel is the only public
   ingress.
6. Frontend: connect the repo to Netlify (publish `web/static`), then set the
   backend URL in `web/static/index.html`'s `<meta name="megatool-api-base">` and
   deploy.
7. Smoke test: owner loopback gets `200`; a friend origin without a token gets
   `401`; with the token, `/api/quotes` returns `200` and `/api/journal/entries`
   returns `403`.

### Rollback

* **Frontend:** Netlify → *Deploys* → publish a previous deploy (instant, no code).
* **Backend:** stop uvicorn, `git checkout <previous-tag>`, restore the DuckDB
  backup if a schema write occurred, restart. The boundary lives in the app, so
  rolling back the code rolls back the security posture with it.
* **Emergency stop for friends:** clear `MEGATOOL_FRIEND_TOKEN` and restart — the
  boundary reverts to owner-only (loopback) immediately.

---

## 10. Monitoring and failure recovery

* **Server liveness:** poll `GET /api/health` from an uptime monitor or a launchd
  `KeepAlive`/systemd `Restart=always`.
* **Certificate expiry:** the client records the peer certificate
  (`notAfter`, `days_remaining`) on its first authorized fetch; `/api/sources`
  shows the **last recorded** value and a warning at ≤30 days. The known
  exchange certificate expires **2026-12-10**. This is a *last check*, not a
  continuous monitor — run `scripts/check_source_health.py` on a schedule to keep
  it fresh.
* **Source failure:** the NEPSE client wraps every call in a circuit breaker
  (open after N consecutive failures → one half-open probe → close on success)
  with bounded exponential backoff, jitter and `Retry-After` support. An open
  breaker refuses calls instead of hammering the exchange; authorization failures
  (`401`/`403`) are never retried.
* **Stale data:** covered by `freshness_class` + `max_age_minutes`; a stopped
  source degrades to `stale`, never to a fresh-looking number.
* **Collector:** run the benchmark/collector as a scheduled job (cron/launchd/
  systemd timer) during market hours; it refuses to start a second concurrent
  instance for the same source.

---

## 11. What remains gated

* The NEPSE official collector does nothing until you set
  `MEGATOOL_NEPSE_API_AUTHORIZED=1`.
* Store writes require `MEGATOOL_INTEGRATION_AUTHORIZED=1` as well.
* Friend exposure does nothing until you set `MEGATOOL_FRIEND_TOKEN`.
* No deployment, publish or DNS change is part of this work.
