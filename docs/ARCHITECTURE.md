# Mega Tool — Architecture

Status: IMPLEMENTED (data, indicators, scanner, API, CLI, web UI) — remaining modules
(fundamentals, floor-sheet, news, AI assistant, forecasting, backtesting, portfolio,
journal) are **NOT IMPLEMENTED**. See `PROJECT_STATUS.md` for the per-feature matrix.

---

## 1. Shape of the system

```
                      ┌──────────────────────────────────────────────┐
   sources            │                 megatool (Python 3.12)       │
 ────────────────────►│                                              │
  GitHub nepse-data   │  datasources/  ── raw frame ──► ingest.py    │
  (public, daily)     │      │                              │        │
  Official NEPSE API  │      │ (BLOCKED, see below)         ▼        │
  (401, not used)     │      │                        quality.py     │
  Local CSV import    │      │                    (flag, never drop) │
                      │      ▼                              │        │
                      │  source adapters                validated   │
                      │  (uniform interface)                │        │
                      │                                     ▼        │
                      │            ┌────────────────────────────┐   │
                      │            │  DuckDB: price_bars        │   │
                      │            │  (symbol, trading_date) PK │   │
                      │            └────────────────────────────┘   │
                      │                     │        ▲              │
                      │        ta/ (28 ind.) │        │ user data    │
                      │        scanner.py    │        │              │
                      │                     ▼        │              │
                      │            ┌────────────────────────────┐   │
                      │            │  SQLite: app state         │   │
                      │            │  (journal, plans, runs)    │   │
                      │            └────────────────────────────┘   │
                      │                     │                       │
                      │                  api.py (FastAPI)           │
                      └─────────────────────┼────────────────────────┘
                                            │  127.0.0.1:8710
                                            ▼
                      web/static (vanilla JS + TradingView
                      Lightweight Charts, vendored, offline)
```

### Why two databases

| Store | File | Holds | Why |
| --- | --- | --- | --- |
| DuckDB | `data/processed/megatool_market.duckdb` | `price_bars`, `security_master` | Read-heavy columnar scans over date ranges; compressed; in-process (no server on an 8 GB machine) |
| SQLite | `data/processed/megatool_state.sqlite` | app state (journal, plans, experiment runs, settings) | Row-oriented writes, transactions, WAL, zero operational overhead |

Market data is **never** written to SQLite and app state is **never** written to DuckDB.
Local databases and all downloads are git-ignored (`data/`, `*.duckdb`, `*.sqlite`).

---

## 2. Canonical price schema (`price_bars`)

Primary key: `(symbol, trading_date)`. Upsert is idempotent — re-ingesting the same bar
updates it in place (verified: 9,561 rows re-ingested → 0 inserted).

| Column | Type | Notes |
| --- | --- | --- |
| `symbol` | VARCHAR | normalised upper-case on write |
| `trading_date` | DATE | exchange trading day, not a fetch timestamp |
| `open`, `high`, `low`, `close` | DOUBLE | may be NULL if the source omits them |
| `volume` | BIGINT | |
| `turnover` | DOUBLE | |
| `percent_change` | DOUBLE | as published by the source |
| `transactions` | BIGINT | optional |
| `source` | VARCHAR **NOT NULL** | provenance label, one per row |
| `source_url` | VARCHAR | |
| `retrieved_at` | TIMESTAMP **NOT NULL** | when *we* fetched it |
| `validation_status` | VARCHAR | `valid` / `suspect` / `invalid` |
| `adjustment_status` | VARCHAR | currently always `unadjusted` |
| `flags` | VARCHAR | JSON list of quality flags on that row |

**Provenance rule:** no row can exist without `source` and `retrieved_at`. Test fixtures
are labelled `SYNTHETIC-TEST-FIXTURE` and live in throwaway databases — they are never
written to the real store.

**Honest labelling rule:** `adjustment_status = unadjusted` is surfaced in the UI chart
header ("prices unadjusted (not adjusted for bonus/split)"). NEPSE companies issue bonus
shares and rights regularly; historical prices in this dataset are **not** split/bonus
adjusted, so long-horizon returns computed from them are not total returns.

---

## 3. Data flow stages

1. **Adapter** (`megatool/datasources/`) — pulls a source into a standardised frame.
   Three adapters exist: `nepse_data_repo` (verified live), `local_file` (CSV/Parquet),
   `nepalstock_official` (implemented, BLOCKED — returns `SourceUnavailable`).
2. **Raw → normalise** — column mapping, symbol/date normalisation, provenance stamped.
3. **Validate** (`quality.py`) — flags, **never deletes**. Severities:
   - `info` — a known characteristic of the source (e.g. `open_outside_range`)
   - `review` — worth a human look (e.g. `price_jump`, `volume_spike`)
   - `invalid` — physically impossible (e.g. `high_low_inverted`, close outside [low, high])
4. **Store** — DuckDB upsert; counts returned as `inserted / updated / total`.
5. **Derive** (`ta/`, `scanner.py`) — indicators and screen metrics computed on read,
   from the store, with explicit warm-up.
6. **Serve** (`api.py`) — JSON over HTTP, GET-only CORS, bound to `127.0.0.1`.

Nothing is auto-corrected. A suspect bar stays in the store with its flags so the user can
decide.

---

## 4. Threading and concurrency (a real defect, fixed)

FastAPI runs `def` endpoints in a threadpool, so several requests are in flight at once
sharing **one** DuckDB connection. DuckDB's Python connection is not safe for that:

- Symptom: `/api/status` intermittently returned 500 —
  `ValueError: zip() argument 2 is shorter than argument 1` in `global_coverage()`.
- Reproduced directly: 8 threads, one unlocked connection, 3,200 reads → **95 bad reads**.
  With the store lock → **0 bad reads**.
- Fix: `MarketStore._lock` (an `RLock`) plus `MarketStore.execute()`; multi-statement
  sequences (`upsert_bars`, `upsert_securities`, `close`) hold the lock throughout —
  `upsert_bars` also registers a replacement name (`staging_bars`) that would otherwise be
  clobbered by a concurrent writer.

SQLite is unaffected: `db.py` opens a fresh connection per operation (WAL, `timeout=15`).

---

## 5. HTTP API (`megatool/api.py`)

Bound to `127.0.0.1` (never `0.0.0.0`). CORS allows **GET** only. No write endpoints that
could move money — the application places no orders, by design.

| Route | Purpose |
| --- | --- |
| `GET /api/health` | liveness, DB open, bar count, disclaimer |
| `GET /api/status` | coverage, `live_feed_connected`, `data_as_of` |
| `GET /api/sources` | source register incl. the blocked official API |
| `GET /api/securities` | search the symbol master |
| `GET /api/bars/{symbol}` | OHLCV window (`start`, `end`, `limit`) |
| `GET /api/bars/{symbol}/indicator` | one indicator, optional JSON `params` |
| `GET /api/indicators` | catalog: formula, reference, warm-up per output |
| `POST /api/screen` | run a filter tree (400 on an invalid definition) |
| `GET /api/screen/presets` | built-in screens |
| `GET /api/screen/export.csv` | CSV export of a screen |
| `GET /api/dashboard` | breadth, movers, most active — explicitly `is_live: false` |
| `GET /api/quality` | per-symbol validation reports |
| `GET /api/portfolio` | positions (empty by default) |

Two contracts worth knowing:

- **`limit` means the most recent N bars**, still returned ascending. It previously
  returned the *oldest* N, which made every chart range show decade-old history.
- **Indicators are computed over full history** (so warm-up is correct) and the client
  aligns them to the visible window **by trading date**, never by array index.

---

## 6. Indicator engine (`megatool/ta/`)

- Own NumPy implementations, registered by decorator → 28 indicators across
  trend / momentum / volatility / volume.
- Each declares `warmup` and, where it differs, a per-output `output_warmup`
  (e.g. MACD line vs signal vs histogram). Warm-up values are `null` in responses,
  never back-filled or faked.
- Formulas carry a `reference` (source of the definition) in the catalog.
- Validated against Wilder's published RSI example: the first two published values
  (70.46, 66.25) match exactly; later values drift <0.1 because the published table
  rounds intermediate steps. The implementation is full-precision.

---

## 7. Front end (`web/static/`)

No build step: plain HTML/CSS/JS served by FastAPI's `StaticFiles`.

- TradingView Lightweight Charts **4.2.3** is vendored into `web/static/vendor/` with its
  Apache 2.0 licence file, so the chart works fully offline.
- Four tabs: Overview (dashboard), Charts, Screener, Data & Quality.
- Every data panel carries its own `data_as_of` and an explicit "not a live feed" note;
  the footer states the tool stores no broker credentials and places no orders.
- Verified in a real browser (Playwright): **0 console errors**; screenshots in
  `docs/screenshots/`.

---

## 8. Rules encoded in the design

| Rule | Where it shows up |
| --- | --- |
| Evidence over assertion | tests are executed, not assumed; UI verified in a browser |
| Never overwrite user work | git checkpoints; `data/` git-ignored, never deleted |
| Flag, don't delete | `quality.py` severities; invalid rows retained with flags |
| Honest data labelling | `source`, `retrieved_at`, `is_live: false`, `unadjusted` |
| No profit promises | no forecast/backtest exists yet; when added they must carry assumptions |
| No autonomous trading | no order endpoints, no credentials, no broker integration |
| Bounded resources | embedded DBs, no server process, `limit` capped at 5,000 |
