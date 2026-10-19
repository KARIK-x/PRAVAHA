# Deploying PRAVAHA on Render

Status: **configuration prepared, not deployed.** This document describes how to
run PRAVAHA as a Render web service. Nothing here has been applied to Render.

PRAVAHA is a single FastAPI process that also serves the static frontend
(`web/static/`). It writes a **DuckDB** market store and a **SQLite** application
store. DuckDB is single-writer, so the service must have exactly **one**
instance and a **persistent disk**.

---

## 1. What `render.yaml` creates

| Piece | Value |
|---|---|
| Service | Web service (`python`) |
| Build command | `pip install -r requirements.txt` |
| Start command | `python -m megatool.cli serve --host 0.0.0.0 --port $PORT` |
| Health check | `GET /api/health` (always public) |
| Disk | `pravaha-data` mounted at `/var/data` (5 GB) |
| Runtime | Python `3.12.3` (`pyproject.toml` requires `>=3.12,<3.14`) |

Apply it from the Render dashboard (**New → Blueprint**) after connecting the
GitHub repository `KARIK-x/PRAVAHA`.

---

## 2. Why this shape

- **Port.** The app reads `MEGATOOL_PORT` (default `8710`) and accepts
  `--port`. The start command passes Render's `$PORT`, so **8710 is never the
  production port** — it is only the local default.
- **Data directory.** `MEGATOOL_DATA_DIR` is set to `/var/data`, matching the
  disk mount. Without it the app would write to an ephemeral path and lose all
  state on every deploy/restart.
- **Single instance.** `duckdb` allows one writer. Do not scale beyond one
  instance. (Render Blueprint sets no scaling.)
- **No build step for the frontend.** `web/static/` is plain HTML/CSS/JS served
  by FastAPI.

---

## 3. Environment variables

### Required

| Variable | Value / source | Why |
|---|---|---|
| `MEGATOOL_HOST` | `0.0.0.0` | Reachable from Render's proxy |
| `MEGATOOL_PORT` | (set by `--port $PORT`) | Render's assigned port |
| `MEGATOOL_DATA_DIR` | `/var/data` | Persistent disk |
| `MEGATOOL_REQUIRE_AUTH` | `1` | Fail closed: the friend boundary is enforced even with no token |
| `MEGATOOL_FRIEND_TOKEN` | `generateValue: true` | Shared read-only token; Render generates and stores it |

### Optional

| Variable | Purpose |
|---|---|
| `MEGATOOL_FRIEND_ORIGIN` | Exact allowed CORS origin if the frontend is hosted separately |
| `MEGATOOL_FRIEND_TRUST_LOOPBACK` | Default `1`; set `0` to stop treating loopback as the owner |
| `MEGATOOL_NEPSE_API_AUTHORIZED` | `1` only to let the collector contact the official NEPSE API |
| `MEGATOOL_INTEGRATION_AUTHORIZED` / `MEGATOOL_INTEGRATION_RULING_REF` | Gate market-store writes |
| `MEGATOOL_AI_PROVIDER` / `MEGATOOL_AI_API_KEY` / `MEGATOOL_AI_MODEL` / `MEGATOOL_AI_ENDPOINT` | Optional hosted LLM |
| `OLLAMA_HOST` | Optional local LLM |
| `MEGATOOL_HEALTH_PATH` | Source-health cache path |
| `MEGATOOL_APP_DB` | Redirect only the SQLite store (inspection tooling) |

Full template: `.env.example`. **Never put a real secret in a tracked file.**

---

## 4. Access control (important)

With `MEGATOOL_REQUIRE_AUTH=1`:

- **Private records** (`/api/portfolio`, `/api/journal`, `/api/written-pdf`,
  `/api/planning`, `/api/alerts`, `/api/watchlists`, `/api/experiments`,
  `/api/screens`, `/api/research`, `/api/agent`, and the import routes) are
  **owner-only**: served to a loopback client only, never to a non-loopback
  client — with or without a token. The Blueprint sets
  `MEGATOOL_FRIEND_TRUST_LOOPBACK=0`, so on Render there is no trusted loopback
  client and these routes are simply **unreachable over HTTP** (which is correct
  — no private data is hosted). Use your local instance for private records.
- **Everything else** requires the friend token from a non-loopback client.
- **`/api/health`** is always public (health checks must not 401).

Because the browser is a non-loopback client, the app will answer **401** until
the token is present. Set it once per browser session (it is kept in
`sessionStorage`, not written to disk):

```js
// Browser console on the deployed site:
sessionStorage.setItem("megatool_friend_token", "<token from the Render dashboard>");
location.reload();
```

The token is visible in the Render dashboard under the service's Environment tab
(Render generated it). Rotate it there if it leaks.

> A small in-app token-entry prompt is a reasonable future improvement; it is
> deliberately not added here to keep this change focused.

---

## 5. Data: what is and is not present after deploy

The repository ships **no market data, no sector CSVs, and no model weights** —
those live under `data/` (git-ignored) and are large/regenerable/private.

| Data | After a fresh deploy | How to supply it |
|---|---|---|
| Market bars (DuckDB `megatool_market.duckdb`) | **Empty** — every view shows an honest "no data" state | Ingest with `megatool fetch` / the collector (needs the NEPSE gate), or copy a prepared `.duckdb` onto the disk |
| App state (SQLite `megatool_state.sqlite`) | Created empty on boot | Populated as you use the app |
| Sector classifications | **Empty** — Sector Explorer shows "No sector classifications available" | Place `data/review/sources/yonepse/yonepse_sectors.csv` and `…/binayabaral/binayabaral_sectors.csv` on the disk (the path is relative to the working directory), or use the sector import tool |
| Kronos AI weights | **Absent** — the AI Forecaster/Kronos views report unavailable | Not shipped (100 MB+, licensed). See §6 |
| Private trading records | **Never** — git-ignored | Do not upload |

The app **boots cleanly with an empty disk**: `ensure_dirs()` creates the
directory tree and both schemas use `CREATE TABLE IF NOT EXISTS`.

---

## 6. Kronos AI

`megatool/kronos_service.py` imports `torch` **lazily** and loads weights from
`data/models/Kronos-base/`. Neither `torch` nor the weights are in the repo, so
Kronos is **non-functional on a fresh deploy** and says so honestly.

To enable it you must, on the persistent disk / build:

1. `pip install torch` (add it to `requirements.txt` or a build step), and
2. place `model.safetensors` + `config.json` under
   `$MEGATOOL_DATA_DIR/models/Kronos-base/`.

Until then, do not expect Kronos output. The `vendor/kronos/requirements.txt`
lists the upstream extras (`torch`, `einops`, `huggingface_hub`, `safetensors`).

---

## 7. Optional: data collection

The collector (`scripts/ingest_*.py`, `scripts/check_source_health.py`) is a
**separate process** and is gated by `MEGATOOL_NEPSE_API_AUTHORIZED=1`. Because
DuckDB is single-writer it must run on the **same host** as the web service, so
on Render it belongs in a **Background Worker** or a **Cron Job** sharing the
same disk — never a second web instance.

---

## 8. Pre-deploy checklist

- [ ] Repository pushed (`KARIK-x/PRAVAHA`, branch `main`).
- [ ] Blueprint applied; disk mounted at `/var/data`.
- [ ] `MEGATOOL_REQUIRE_AUTH=1` and a token generated.
- [ ] Health check green (`/api/health` → 200).
- [ ] Token pasted into `sessionStorage` and the UI loads.
- [ ] (Optional) Market data and sector CSVs placed on the disk.
- [ ] (Optional) Kronos weights + `torch` added.
