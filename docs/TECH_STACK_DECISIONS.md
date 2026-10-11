# Tech Stack Decisions

Format: decision → alternatives considered → why → what would change it.
Honesty note: these are **reasoned choices, not benchmarks**. No performance bake-off was
run unless a measurement is quoted.

---

## 1. Python 3.12 (not 3.13/3.14)

`uv` initially resolved to 3.14. Pinned back with `.python-version` and
`requires-python = ">=3.12,<3.14"` because the numeric stack (NumPy/pandas/DuckDB wheels)
is best validated on 3.12, and this machine has no toolchain budget for compiling.

- Alternative: 3.14 — rejected, wheel availability risk.
- Alternative: system Python — rejected, not reproducible across machines.

## 2. FastAPI + Uvicorn, bound to `127.0.0.1`

Chosen for typed request/response models and automatic validation errors.
The server binds loopback only; CORS allows GET only.

- Alternative: Streamlit — rejected: re-runs the script per interaction, awkward for a
  chart terminal, and hides what is happening (this project needs visible provenance).
- Alternative: Flask — no built-in schema validation.

## 3. DuckDB for market data, SQLite for app state

See `ARCHITECTURE.md` §1. Both are embedded — no server process on an 8 GB machine.

- Alternative: PostgreSQL/MySQL — rejected: a daemon, more RAM, more to break.
- Alternative: one SQLite store for everything — workable, but date-range scans over
  millions of bars are what a columnar store is for; also keeps app state separate from
  market data so market data can be dropped and re-fetched.
- Alternative: Parquet files only — rejected: no transactional upsert; would need a
  catalog. Parquet remains a good *export* target.

**Concurrency caveat (measured):** one DuckDB connection must not be shared across
threads. Fixed with a store-level `RLock` — 95/3,200 bad reads unlocked vs 0 locked.

## 4. Data source: public GitHub dataset, not a paid feed

Paid feeds were excluded by the brief (no paid feeds). The official NEPSE API is
**BLOCKED** (401, authenticated session required) — see `DATA_SOURCES.md` §2.1.

- Chosen: `github.com/Aabishkar2/nepse-data` — free, no key, daily, 372 symbols, deep
  history. **No LICENSE file published** (risk recorded in `DATA_SOURCES.md` §1.1).
- Rejected: scraping third-party HTML sites — brittle, and unclear terms.
- Rejected: using the owner's broker/Mero Share session — Rule 9, no exceptions.
- Fallback: local CSV import, which always works offline.

## 5. Own indicator engine (not TA-Lib, not pandas-ta)

28 indicators implemented directly in NumPy (`megatool/ta/`), registered by decorator with
declared warm-up.

- **TA-Lib** — rejected: C extension that must compile on this machine; the wrapper's
  wheel matrix is unreliable, and a failed build would block everything downstream.
- **pandas-ta** — rejected: effectively unmaintained and its annotations/imports break on
  current pandas versions.
- **VectorBT / backtesting.py** — rejected for now: heavy dependencies and their own
  backtest semantics, which would hide costs/assumptions. The plan is a small transparent
  engine where every rule is visible (see `ARCHITECTURE.md` §8).

Cost of this choice: we must validate our own maths. Mitigation: RSI checked against
Wilder's published worked example (first two values match exactly).

## 6. TradingView Lightweight Charts 4.2.3, vendored

Apache 2.0, ~150 KB, canvas-rendered, no build step. Vendored into
`web/static/vendor/` **with its licence file** so the app works offline.

- Alternative: Plotly — much heavier bundle, slower with thousands of candles.
- Alternative: ECharts/Highcharts — larger, or non-open licence.
- Alternative: D3 from scratch — weeks of work for what this library already does.

The Apache 2.0 licence file is committed alongside the script, and the UI carries
attribution ("Charting by TradingView Lightweight Charts™").

## 7. Vanilla JS single page, no bundler

No npm install, no build output, no `node_modules` on a disk with ~9.7 GB free.
The UI is `index.html` + `styles.css` + `app.js` served by FastAPI.

- Alternative: React + Vite + TypeScript — better for a large team/UI; rejected here
  because it adds a build step and a dependency tree for four tabs.

Cost of this choice: no type checking in the front end, and no front-end test harness —
which is exactly why the UI is verified in a real browser (Playwright) instead.

## 8. SQLite via a fresh connection per operation

`db.py` opens a connection per call (WAL, `timeout=15`, foreign keys on). Simple and
thread-safe without shared-state reasoning.

- Alternative: a pooled/shared connection — rejected: `sqlite3` connections are
  thread-affine by default and would need `check_same_thread=False` plus locking.

## 9. Testing: pytest + ruff, 175 tests

`uv run pytest` (unit + API tests via `fastapi.testclient`), `ruff check` + `ruff format`.
No network in tests: fixtures are synthetic and labelled, written to `tmp_path`.

- Alternative: Hypothesis — good future addition for indicator properties; not added yet
  (dependency budget).
- Note: assertions are never disabled and failures are never skipped to go green.

## 10. Disk and memory budget

Machine: MacBook M1 (arm64), 8 GB RAM, ~9.7 GB free at start.

| Measure | Why |
| --- | --- |
| embedded DuckDB + SQLite, no daemon | no extra resident process |
| `limit` capped at 5,000 bars per request | bounds a single response |
| `data/` git-ignored (currently 4.0 MB) | keeps the repo small; no market data committed |
| no local LLM / no GPU code | brief: unavailable |
| own indicator code, few dependencies | keeps `.venv` small and auditable |
