# Deploying PRAVAHA (Netlify frontend + Render backend)

Status: **configuration prepared, not deployed.** This documents the split
deployment actually in use:

| Piece | URL | Serves |
|---|---|---|
| Frontend | https://pravahanepse.netlify.app | `web/static/` (static, no build step) |
| Backend | https://pravaha-hkwt.onrender.com | FastAPI API **and** a copy of the frontend |

The Render backend also serves the whole app at its own URL; the Netlify copy
exists so the UI can live on a CDN. Both talk to the same API.

---

## 1. Netlify ↔ Render connectivity

The frontend's API base is `<meta name="megatool-api-base" content="">` in
`web/static/index.html` — **empty means same-origin**. On Netlify that would
send `fetch("/api/…")` to Netlify itself (404), so `netlify.toml` proxies it:

```toml
[[redirects]]
  from = "/api/*"
  to = "https://pravaha-hkwt.onrender.com/api/:splat"
  status = 200
  force = false
```

This is a **server-side proxy**, so the browser sees one origin and CORS is not
involved; request headers (including `X-Friend-Token`) are forwarded.

> If the Render URL changes, update `to` here. If you would rather call the API
> directly (cross-origin), set `MEGATOOL_FRIEND_ORIGIN` on Render to the Netlify
> origin and set the meta tag to the Render URL — but then local development
> would also call Render, so the proxy is preferred.

---

## 2. Render service (Free plan)

`render.yaml` defines **one web service, no persistent disk**:

| Field | Value |
|---|---|
| Plan | `free` |
| Build | `pip install -r requirements.txt` then the seed steps below |
| Start | `python -m megatool.cli serve --host 0.0.0.0 --port $PORT` |
| Health check | `GET /api/health` (always public) |
| Runtime | Python `3.12.3` |

`MEGATOOL_HOST=0.0.0.0`; **`MEGATOOL_DATA_DIR` is deliberately unset** so it
defaults to `<repo>/data`, which is where the build seeds data. **Port 8710 is
never used in production** — it is only the local default.

### Runtime data seeding (no build download)

On the Free plan the database starts empty, so the app seeds itself from the
**same public sources the CLI uses**, in a **background thread at startup**
(`megatool/deploy_seed.py`):

```
Aabishkar2/nepse-data        → price_bars            (372 symbols, ~515k bars)
binayabaral/nepal-market-data→ index_series + index_ohlc_history
shubhamnpk/yonepse           → security_master.sector
```

Why at runtime rather than in the build: a ~5-minute, ~80 MB download in the
build can time out and fail the deploy, and it only works if the build command
is set exactly right. The runtime seed:

* lets the app **serve immediately** (the health check never waits on a download);
* runs **at most once per deploy** (a marker in the app DB) and is **idempotent**;
* is **off for loopback binds**, so local development and the test client never
  start a download (`MEGATOOL_AUTO_SEED=1` forces it, `=0` disables it);
* caps with `MEGATOOL_SEED_LIMIT=N` if the host is slow;
* reports every failure instead of swallowing it, and never sets the marker if
  the price-bar step failed (so the next boot retries).

The CLI equivalents (`python -m megatool.cli fetch|fetch-index|fetch-sectors`)
remain available for manual seeding and are what the tests exercise.

---

## 3. Environment variables

### Required

| Variable | Value / source |
|---|---|
| `MEGATOOL_HOST` | `0.0.0.0` |
| `MEGATOOL_REQUIRE_AUTH` | `1` (fail closed on a hosted host) |
| `MEGATOOL_FRIEND_TOKEN` | `generateValue: true` (Render generates it) |
| `PYTHON_VERSION` | `3.12.3` |

### Optional

| Variable | Purpose |
|---|---|
| `MEGATOOL_FRIEND_ORIGIN` | Exact allowed CORS origin (only for direct cross-origin calls) |
| `MEGATOOL_FRIEND_TRUST_LOOPBACK` | `0` on a hosted deployment |
| `MEGATOOL_DATA_DIR` | Only if you attach a persistent disk (paid) |
| `MEGATOOL_NEPSE_API_AUTHORIZED` / `MEGATOOL_INTEGRATION_AUTHORIZED` | Gates for the official collector / market-store writes |
| `MEGATOOL_AI_*`, `OLLAMA_HOST` | Optional LLM |

Full template: `.env.example`. **Never put a real secret in a tracked file.**

---

## 4. Access control

With `MEGATOOL_REQUIRE_AUTH=1`:

- **Static frontend is public** (`index.html`, JS/CSS, assets) — gating it would
  401 the whole site.
- **`/api/health` is public** (health checks must not 401).
- **Public research surface** — dashboard, charts, screeners, workbench,
  fundamentals, Sasto Share, catalogue, ideas, corporate events, market
  intelligence and bounded read-only compute — requires the friend token.
- **Private records** (portfolio, journal, PDF journal, watchlists, saved
  screens, experiments, snapshots, query history, templates, research
  workspace, agent, reconciliation, research desk) are **owner-only**: never
  served to a non-loopback client, with or without a token.
- **Deny-by-default**: any route not on the allowlist is refused.

The browser prompts for the token on the first 401, keeps it in `sessionStorage`
(per-tab, never written to disk) and reloads once. It is visible only in the
Render dashboard. The token grants read-only allowlisted access.

---

## 5. Storage and data (Free plan)

The Free filesystem is **ephemeral across deploys**. Data is re-seeded on every
build, so:

| Data | Source | Persists across restarts? | Across deploys? |
|---|---|---|---|
| Market bars (`price_bars`) | runtime seed (Aabishkar2/nepse-data) | yes (same deploy) | re-seeded |
| NEPSE index (`index_series`) | runtime seed (binayabaral) | yes | re-seeded |
| NEPSE index OHLC (`index_ohlc_history`) | runtime seed (binayabaral) | yes | re-seeded |
| Sectors (`security_master.sector`) | runtime seed (yonepse) | yes | re-seeded |
| App state (journal, portfolio, …) | user input | yes | **lost** |
| Sector-index OHLC, fundamentals, corporate events | not seeded | — | — |
| Kronos weights | not shipped | — | — |

The first boot after a deploy has no data for ~5 minutes (the seed runs in the
background). Reload the page after that; the dashboard and charts then show real
history.

> App state (journal/portfolio/watchlists) is **not durable on Free**. For
> durable state, attach a persistent disk on a paid instance and set
> `MEGATOOL_DATA_DIR` to the mount path (the seed then becomes optional).

---

## 6. Pre-deploy checklist

- [ ] Repository pushed (`KARIK-x/PRAVAHA`, branch `main`).
- [ ] Render service rebuilt (build runs the seed steps).
- [ ] `MEGATOOL_REQUIRE_AUTH=1` and a token generated.
- [ ] Health check green (`/api/health` → 200).
- [ ] `GET /api/status` shows a real `data_as_of`, not `null`.
- [ ] Netlify redeployed so `netlify.toml`'s `/api/*` proxy applies.
- [ ] Token entered once per browser session.
