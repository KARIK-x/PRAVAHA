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

### Data seeding at startup (snapshot first, network as fallback)

Render Free has **no persistent disk**, and its runtime filesystem is discarded
when the instance is recycled (spin-down/wake or restart) — so data written at
runtime does **not** survive. Two things fix that:

**1. A committed market-data snapshot** (`seed/pravaha_market_seed.parquet`,
~8.9 MB) — a frozen copy of the public `Aabishkar2/nepse-data` dataset
(372 symbols, 515,648 daily bars, 1995-07-20 → 2026-10-16, provenance and
`retrieved_at` per row). It ships **inside the deploy image**, so it is present
on every boot and loads via DuckDB `read_parquet` in **~4 seconds** — no network,
no build timeout.

**2. A background seeder at startup** (`megatool/deploy_seed.py`) that loads the
snapshot and then fetches the two small live sources:

```
seed/pravaha_market_seed.parquet → price_bars  (offline, ~4 s)
binayabaral/nepal-market-data    → index_series + index_ohlc_history
shubhamnpk/yonepse               → security_master.sector
```

If the snapshot is ever missing, it falls back to the full network fetch
(`Aabishkar2/nepse-data`) — slower but complete. The whole seed takes ~10 s.

Properties: the app **serves immediately** (the health check never waits); it
runs **at most once per deploy** (a marker in the app DB) and is **idempotent**;
it is **off for loopback binds** so local development and the test client never
seed (`MEGATOOL_AUTO_SEED=1` forces it, `=0` disables it); `MEGATOOL_SEED_LIMIT=N`
caps the network fallback; every failure is reported, and the marker is not set
if the price bars did not land (so the next boot retries).

To refresh the snapshot with newer data:

```bash
python -m megatool.cli fetch --quiet          # downloads the public dataset
python - <<'PY'
import duckdb
duckdb.connect("data/processed/megatool_market.duckdb", read_only=True).execute(
    "COPY (SELECT symbol,trading_date,open,high,low,close,volume,turnover,"
    "percent_change,transactions,source,source_url,retrieved_at,validation_status,"
    "adjustment_status,flags FROM price_bars ORDER BY symbol,trading_date) "
    "TO 'seed/pravaha_market_seed.parquet' (FORMAT PARQUET, COMPRESSION zstd)")
PY
```

The CLI commands (`fetch` / `fetch-index` / `fetch-sectors`) remain available for
manual seeding.

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

| Data | Source | Survives restart? | Survives redeploy? |
|---|---|---|---|
| Market bars (`price_bars`) | committed snapshot (`seed/*.parquet`) | **yes** (in the image) | yes |
| NEPSE index (`index_series`) | network seed (binayabaral, ~5 s) | re-fetched | re-fetched |
| NEPSE index OHLC (`index_ohlc_history`) | network seed (binayabaral) | re-fetched | re-fetched |
| Sectors (`security_master.sector`) | network seed (yonepse, ~3 s) | re-fetched | re-fetched |
| App state (journal, portfolio, …) | user input | **lost on restart** | **lost** |
| Sector-index OHLC, fundamentals, corporate events | not seeded | — | — |
| Kronos weights | not shipped | — | — |

So charts and the dashboard have real data within ~10 seconds of a cold start,
with no network dependency for the price bars. **User-owned state is still
ephemeral** — durable journal/portfolio needs a paid instance with a persistent
disk and `MEGATOOL_DATA_DIR` set to the mount path.

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
