# Project Status

Every row below is labelled with what was **actually executed and observed**. Nothing is
marked working because the code exists. The labels mean:

| Label | Meaning |
| --- | --- |
| `TESTED-PASS` | Feature exists, its tests were run and passed, and it was exercised end-to-end |
| `PARTIAL` | Some of the module works and is tested; a named part of it does not exist |
| `BLOCKED` | Cannot be completed here for a reason outside this codebase |
| `NOT-IMPLEMENTED` | Deliberately not built. The reason is stated |
| `NOT-TESTED` | Code exists but has not been executed/observed |

Test suite: **376 passed, 0 failed** (`uv run pytest`, 2026-10-12). `ruff check` and
`ruff format` clean. Live server verified in a real browser via Playwright.

---

## 1. Feature matrix

| # | Module | Status | Evidence |
| --- | --- | --- | --- |
| 1 | **Data foundation** (ingest, canonical schema, provenance, quality flags) | `TESTED-PASS` | 9,561→**89,580 real rows / 60 symbols** stored; idempotent re-ingest inserts 0 duplicates; quality sweep flags (never deletes) 1.31% suspect rows; `open` outside the day range in ~15% of source rows, recorded not hidden |
| 2 | **Market Dashboard** | `TESTED-PASS` | Breadth/movers/most-active render in the browser; the response carries `is_live: false` and shows **no index value** because no index source is available |
| 3 | **Charting Terminal** | `TESTED-PASS` | Candles + volume + 28 indicators; verified in-browser against pandas (SMA 1014.485 / 877.87 matched exactly) |
| 4 | **Stock Scanner** | `TESTED-PASS` | 19 metrics, 4 presets, filter-tree validation with plain-English 400s; 21 scanner tests + 58 API tests |
| 5 | **Multi-Factor Engine** | `PARTIAL` | The scanner's filter tree **is** the multi-factor engine (AND/OR composition, 19 metrics). A ranked/scored factor model with normalisation and weights is **not built** |
| 6 | **Fundamentals Lab** | `NOT-IMPLEMENTED` | SEBON publishes fundamentals as publications, not an API (research register A5). Design is CSV/manual import with per-field provenance. **No fundamental data has ever been fetched**, so no ratio is computed anywhere |
| 7 | **News / Events** | `NOT-IMPLEMENTED` | No machine-readable news source was found (A7/A8). Nothing is scraped |
| 8 | **AI Research Assistant** | `TESTED-PASS` (as a rules engine) | **There is no LLM** — no key, and no local model fits 8 GB RAM. What ships is a deterministic rules engine that cites the window and definition behind every number, and **refuses** predictive/prescriptive questions. 28 unit + 6 API tests |
| 9 | **Forecasting Lab** | `TESTED-PASS` | 6 models, all scored on an unseen hold-out against the naive baseline, with a plain-words verdict (`NO DEMONSTRATED SKILL` where true). 28 unit + 5 API tests |
| 10 | **Backtesting Lab** | `TESTED-PASS` | Long/flat engine, next-bar-open fills, shorting refused, fees+slippage, benchmark and assumptions in every response. 32 tests + a real-data run (ADBL sma_cross 20/50, 3,659 bars, +223.48% vs buy-and-hold +168.95%, maxDD −54.41%, Sharpe 0.43, 44 trades, 9 assumptions) |
| 11 | **Portfolio Intelligence** | `TESTED-PASS` | Positions **derived from the transaction ledger** (the two can never disagree); manual holdings allowed only where no ledger exists; valuation marks to the latest *stored* close and leaves unpriced symbols unvalued and flagged. 29 unit + 8 API tests, plus a live smoke test |
| 12 | **Trade Planning / Risk** | `TESTED-PASS` | R multiples, risk:reward, position size for a fixed fractional risk (rounded down, affordability-capped). A stop above the entry is rejected — NEPSE has no retail shorting. 21 unit + 4 API tests |
| 13 | **Trading Journal** | `TESTED-PASS` | CRUD, win rate, R multiples, plan adherence, per-strategy breakdown; trades without a complete plan are counted in win rate but excluded from R stats **and both are reported**. 27 unit + 5 API tests |
| 14 | **Floor-sheet Intelligence** | `NOT-IMPLEMENTED` | Design is import-based (no public API is advertised by the aggregator sites, A7/A8). No floor-sheet file has ever been imported, so nothing is analysed |
| 15 | **Bounded Research Agent** | `NOT-IMPLEMENTED` | The web-search tool failed on every attempt this session (register B1–B3). No autonomous agent loop was built; the deterministic Research Assistant (#8) is what exists instead |

## 2. Web UI

| Tab | Status |
| --- | --- |
| Dashboard, Chart, Scanner, Backtest | `TESTED-PASS` — exercised in a real browser, 0 console errors, screenshots in `docs/screenshots/` |
| Research, Portfolio, Journal | see §6 *Verification log* below — status recorded after browser verification |

## 3. Data sources

| Source | Status |
| --- | --- |
| Official NEPSE API (`nepalstock.com/api/nots/*`) | **BLOCKED** — HTTP 401 on all 11 probed endpoints; a logged-in session is required. No credential use, no token reverse-engineering |
| `github.com/Aabishkar2/nepse-data` | **IN USE** — 372 symbols available, 60 imported (89,580 rows, 1995-07-20 → 2026-10-09). **No LICENSE file**: personal local use with per-row attribution only; `data/` is git-ignored so nothing is redistributed |
| Local CSV import | **AVAILABLE** — the guaranteed fallback, documented in `docs/DATA_SOURCES.md` §1.2 |
| NEPSE index / sector indices | **UNAVAILABLE** — the dashboard deliberately shows no index figure rather than a stale or invented one |
| SEBON / NRB / merolagani / sharesansar | **INSPECTED, NOT WIRED** — reachable, but publish pages and publications, not documented APIs |
| `cdsc.com.np` | **FAILED** — fetch timed out |

## 4. Known issues, in priority order

1. **Only 60 of 372 available symbols are imported.** Coverage is wide in time (back to
   995 for some names) but narrow across the market. *Fix:* `uv run megatool fetch --all`
   when disk/time allows, or import the CSVs directly.
2. **Third-party data licensing is unresolved.** The dataset has no LICENSE file. This is
   acceptable for personal local analysis with attribution and is the reason `data/` is
   git-ignored — but it is not resolved, and the data must not be redistributed.
3. **No live feed, no index.** Everything is end-of-day and delayed by whatever the source
   publishes. The UI says so on every surface that shows a price.
4. **Prices are unadjusted** for bonus and rights issues, so every "return" in the
   Forecasting Lab, Research Assistant and scanner is a *price* change, not a total return.
   NEPSE corporate actions are not available in the imported data.
5. **Fundamentals and floor-sheet analysis do not exist yet** (rows 6 and 14). They are
   import-based by design; no real file has ever been imported, so they are untested.
6. **Backtest fills are optimistic at the bar level.** Next-bar-open is honest about
   *when* you could trade, but it assumes the open was available in full size. Liquidity
   and impact are not modelled.
7. **The relative-strength ranking compares only the 60 locally stored symbols**, not
   NEPSE. The UI states this.

## 5. Verification log

*(recorded after the browser verification run — see `SESSION_HANDOFF.md` for the session
that produced it)*

## 6. How to run it

```bash
cd "Downloads/AI trading NEPSE"
uv sync
uv run megatool init      # create the databases
uv run megatool fetch     # download real history (network)
uv run megatool serve     # http://127.0.0.1:8710
uv run pytest             # 376 tests
```
