# Session Handoff

This file exists so the next session (or the owner) can pick the project up without
re-deriving anything. It records **what was executed and observed**, not what was intended.

Last updated: 2026-10-12.

---

## 1. How to run it

```bash
cd "Downloads/AI trading NEPSE"
uv sync                     # dependencies into ./.venv (Python 3.12.3)
uv run megatool init        # create/upgrade the local databases
uv run megatool fetch       # download real NEPSE history (network)
uv run megatool serve       # web terminal at http://127.0.0.1:8710
uv run pytest               # 406 tests, ~20 s
```

The server binds `127.0.0.1` only. Nothing listens on the network interface.

## 2. What exists now

| Layer | Files |
| --- | --- |
| Data | `megatool/config.py`, `db.py` (SQLite, schema v2), `market_store.py` (DuckDB), `quality.py`, `datasources/`, `ingest.py` |
| Indicators | `megatool/ta/` — 28 indicators, decorator registry, per-output warm-up |
| Analysis | `scanner.py`, `backtest.py`, `forecast.py`, `research.py`, `floorsheet.py` |
| Personal state | `portfolio.py` (ledger-derived), `journal.py`, `planning.py` |
| Interface | `api.py` (FastAPI, ~40 routes), `cli.py`, `web/static/` |
| Tests | `tests/` — 406 tests across 10 files |
| Docs | `docs/ARCHITECTURE.md`, `DATA_SOURCES.md`, `TECH_STACK_DECISIONS.md`, `RESEARCH_REGISTER.md`, `PROJECT_STATUS.md`, this file |

### Data actually in the store

- **89,580 real daily bars, 60 symbols**, coverage 1995-07-20 → 2026-10-09.
- Source: `github.com/Aabishkar2/nepse-data` (372 symbols available; **no LICENSE file**,
  so: personal local use, per-row attribution, `data/` git-ignored, nothing redistributed).
- Official NEPSE API is **BLOCKED** (HTTP 401 on all 11 probed endpoints) — see
  `docs/DATA_SOURCES.md` §2.1. `megatool/datasources/nepalstock_official.py` keeps a
  `probe()` so the block can be re-checked, not re-argued.
- Quality sweep of the real rows: `open` outside the day range in ~15% of rows, `close`
  outside in 2 of 9,561, overall suspect rate 1.31%, AHPC has 9 `high_low_inverted` rows.
  Problems are **flagged, never deleted**.

## 3. Commits this session

| Commit | Contents |
| --- | --- |
| `3e02461` | Phase 0–5: config, SQLite schema, DuckDB store, quality checks, 3 source adapters, ingest |
| `b84ffa5` | Indicator engine, 28 indicators |
| `16156cc` | Scanner, HTTP API, CLI, web UI |
| `6ee4f27` | Architecture / data-source / decision / research-register docs |
| `361eb22` | Backtesting Lab |
| `56f369b` | Portfolio ledger, trading journal, trade planning |
| `e33680b` | Forecasting Lab and Research Assistant |
| `e94baa0` | Floor-sheet import and analysis |
| `f2e644f` | Web UI: Research, Portfolio and Journal tabs; two silent-data-loss fixes |

## 4. Decisions worth not re-litigating

1. **DuckDB access is serialised with an `RLock`.** Empirically necessary: 8 concurrent
   threads without it produced 95 bad reads out of 3,200; with it, zero.
2. **`get_bars(limit=N)` means the most recent N bars**, returned ascending.
3. **Indicators align to price by trading date, never by array index.** The index-aligned
   version plotted an SMA across ~1,600 points against a 857-point price series.
4. **Positions are derived from the transaction ledger.** `portfolio_positions` exists
   only for holdings that predate the tool and have no trade history; a conflict is
   flagged, and the ledger wins.
5. **The Research Assistant is a rules engine, not an LLM.** No key exists in this
   project and no local model fits 8 GB RAM. Shipping anything that called itself an AI
   would be dishonest labelling.
6. **Forecasting leads with the naive baseline.** A smooth projected line is easy to
   produce and easy to misread, so the headline number is the RMSE ratio against "use
   yesterday's close", and a model at or above 1.0 says `NO DEMONSTRATED SKILL`.
7. **Backtesting fills at the next bar's open by default** and refuses shorting (NEPSE
   has no retail shorting). A `same_close` mode exists but is labelled optimistic.
8. **Both databases are redirected to a throwaway path for every test** by an autouse
   fixture in `tests/conftest.py`.

## 5. Defects found and fixed (all observed, not theorised)

| # | Defect | How it surfaced | Fix |
| --- | --- | --- | --- |
| 1 | A test helper omitted its `db_path`, so **14 synthetic journal rows were written into the owner's real database** during a normal test run | `test_journal.py` failures led to inspecting the real DB | Rows identified and deleted; the helper now requires the path; an autouse fixture makes the whole class of mistake impossible. A full suite run afterwards leaves the real DB empty — verified |
| 2 | A stub `GET /api/portfolio` was still registered **before** the real implementation and silently answered instead of it | ruff F811, then reading the route order | Stub deleted; the route table in `ARCHITECTURE.md` §5 records that literal paths must precede `{param}` patterns |
| 3 | Indicator values were aligned to the visible window **by array index** | browser check against pandas | aligned by trading date (`web/static/app.js` `alignedSeries`) |
| 4 | `get_bars(limit=N)` returned the **oldest** N bars, so every chart range showed decade-old history | browser verification | semantics changed to most-recent N |
| 5 | 8 threads sharing one DuckDB connection: **95 bad reads / 3,200** | concurrency test | store-level `RLock` |
| 6 | Seasonal-naive minimum-data guard was computed from the **full** series, so it passed and then crashed once the hold-out was sliced off | forecast test | requirement is now `period + holdout`; clear `ForecastError` |
| 7 | The 3-month relative-strength figure was measured from each symbol's **first stored value**, silently turning it into a lifetime figure | research test | measured from the first valid value inside the window; regression test added |
| 8 | `update_entry` raised on a missing id instead of returning `False` | journal test | returns `False`; the API maps it to 404 |
| 9 | Backtest POST without a `Content-Type` returned a 422 that the UI rendered as `[object Object]` | browser | request sets the header; errors are flattened for display |

## 6. Known gaps — the honest list

1. **60 of 372 available symbols are imported.** Wide in time, narrow across the market.
2. **Fundamentals Lab and News/Events are not implemented.** SEBON publishes fundamentals
   as publications, not an API (research register A5), and no machine-readable news source
   was found. The design is CSV/manual import with per-field provenance; no real file has
   ever been imported, so nothing is tested.
3. **Floor-sheet analysis is implemented but has never been run on a real sheet** — it is
   unit-tested against synthetic CSVs only. Import a real session to exercise it.
4. **Bounded Research Agent not implemented** — the web-search tool failed on all three
   attempts this session (register B1–B3).
5. **Multi-factor ranking is not built** — the scanner's filter tree is the multi-factor
   engine; there is no normalised/weighted factor score.
6. **No index or sector data anywhere**, because no source is available. The dashboard
   deliberately shows no index value.
7. **Prices are unadjusted** for bonus and rights issues, so every "return" in the
   forecast, research and scanner output is a price change, not a total return.
8. **The third-party dataset licence is unresolved.**

## 7. Verification evidence

- `uv run pytest` — **412 passed, 0 failed** (2026-10-12).
- `ruff check` and `ruff format` — clean.
- All eight web tabs exercised in a real browser (Playwright) with **0 console errors**;
  the refusal path, the oversell rejection and the empty-journal "—" were each read back
  from the DOM. Screenshots in `docs/screenshots/`.
- Floor-sheet analysis verified end-to-end against a **throwaway** `MEGATOOL_DATA_DIR`
  (second server instance), so the owner's store stayed clean.
- Live endpoints exercised with `curl` against the running server. Full evidence table in
  `PROJECT_STATUS.md` §5.

## 8. What the next session should do, in order

1. Import a real floor sheet and check the analysis against the published page.
2. Import fundamentals CSVs (SEBON quarterly statistics) and compute P/E, P/B, ROE and
   dividend yield **with per-field provenance**.
3. Widen coverage to all 372 symbols when disk/time allows (`uv run megatool fetch --all`).
4. Add a normalised multi-factor score on top of the existing scanner filter tree.
5. Re-check the official NEPSE API block with `probe()` occasionally — do not work around
   it, and never store credentials.
