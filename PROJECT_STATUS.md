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

Test suite: **466 passed, 0 failed** (`uv run pytest`, 2026-10-12). `ruff check` and
`ruff format` clean. Live server verified in a real browser via Playwright.

---

## 1. Feature matrix

| # | Module | Status | Evidence |
| --- | --- | --- | --- |
| 1 | **Data foundation** (ingest, canonical schema, provenance, quality flags) | `TESTED-PASS` | 9,561→**89,580 real rows / 60 symbols** stored; idempotent re-ingest inserts 0 duplicates; quality sweep flags (never deletes) 1.31% suspect rows; `open` outside the day range in ~15% of source rows, recorded not hidden |
| 2 | **Market Dashboard** | `TESTED-PASS` | Breadth/movers/most-active render in the browser; the response carries `is_live: false` and shows **no index value** because no index source is available |
| 3 | **Charting Terminal** | `TESTED-PASS` | Candles + volume + 28 indicators; verified in-browser against pandas (SMA 1014.485 / 877.87 matched exactly) |
| 4 | **Stock Scanner** | `TESTED-PASS` | 19 metrics, 4 presets, filter-tree validation with plain-English 400s; 21 scanner tests + 65 API tests |
| 5 | **Multi-Factor Engine** | `PARTIAL` | The scanner's filter tree **is** the multi-factor engine (AND/OR composition, 19 metrics). A ranked/scored factor model with normalisation and weights is **not built** |
| 6 | **Fundamentals Lab** | `NOT-IMPLEMENTED` | SEBON publishes fundamentals as publications, not an API (research register A5). Design is CSV/manual import with per-field provenance. **No fundamental data has ever been fetched**, so no ratio is computed anywhere |
| 7 | **News / Events** | `NOT-IMPLEMENTED` | No machine-readable news source was found (A7/A8). Nothing is scraped |
| 8 | **AI Research Assistant** | `TESTED-PASS` (as a rules engine) | **There is no LLM** — no key, and no local model fits 8 GB RAM. What ships is a deterministic rules engine that cites the window and definition behind every number, and **refuses** predictive/prescriptive questions. 28 unit + 6 API tests |
| 9 | **Forecasting Lab** | `TESTED-PASS` | 6 models, all scored on an unseen hold-out against the naive baseline, with a plain-words verdict (`NO DEMONSTRATED SKILL` where true). 29 unit + 5 API tests |
| 10 | **Backtesting Lab** | `TESTED-PASS` | Long/flat engine, next-bar-open fills, shorting refused, fees+slippage, benchmark and assumptions in every response. 32 tests + a real-data run (ADBL sma_cross 20/50, 3,659 bars, +223.48% vs buy-and-hold +168.95%, maxDD −54.41%, Sharpe 0.43, 44 trades, 9 assumptions) |
| 11 | **Portfolio Intelligence** | `TESTED-PASS` | Positions **derived from the transaction ledger** (the two can never disagree); manual holdings allowed only where no ledger exists; valuation marks to the latest *stored* close and leaves unpriced symbols unvalued and flagged. 29 unit + 8 API tests, plus a live smoke test |
| 12 | **Trade Planning / Risk** | `TESTED-PASS` | R multiples, risk:reward, position size for a fixed fractional risk (rounded down, affordability-capped). A stop above the entry is rejected — NEPSE has no retail shorting. 21 unit + 4 API tests |
| 13 | **Trading Journal** | `TESTED-PASS` | CRUD, win rate, R multiples, plan adherence, per-strategy breakdown; trades without a complete plan are counted in win rate but excluded from R stats **and both are reported**. 30 unit + 5 API tests |
| 14 | **Floor-sheet Intelligence** | `PARTIAL` | Import, validation and analysis are **implemented and tested** (25 unit + 5 API + 9 CLI tests). Reachable two ways: `megatool floor import FILE --date YYYY-MM-DD` / `megatool floor summary`, and `POST /api/floorsheet/import`. Verified end-to-end against an **isolated** database (second server instance and a throwaway `MEGATOOL_DATA_DIR`), so the owner's store stayed clean. It has **never been run on a real floor sheet** — only on synthetic CSVs — and there is **no web tab** for it yet |
| 15 | **Bounded Research Agent** | `NOT-IMPLEMENTED` | The web-search tool failed on every attempt this session (register B1–B3). No autonomous agent loop was built; the deterministic Research Assistant (#8) is what exists instead |
| 16 | **PDF records (Written Data.pdf)** | `PARTIAL` | The 52-page handwritten journal is located and OCR-ready (PyMuPDF + tesseract). Extraction is **in progress** — see `docs/WRITTEN_DATA_PDF_AUDIT.md`. No PDF record has yet been imported into the portfolio or journal |

## 2. Web UI

Eight tabs, all exercised in a real browser (Playwright) with **0 console errors**.
Screenshots in `docs/screenshots/`.

| Tab | Status |
| --- | --- |
| Overview, Charts, Screener, Backtest, Data | `TESTED-PASS` — earlier browser run; screenshot evidence committed |
| Research | `TESTED-PASS` — cited report rendered for ADBL (33 findings, every row showing value + window + definition, no `[object Object]`, no `undefined`); a predictive question is refused verbatim and does **not** fall back to the full report; forecast comparison shows `NO DEMONSTRATED SKILL` on every model at or above 1.0 |
| Portfolio | `TESTED-PASS` — empty state explicit; a buy valued at the latest stored close with that stated on screen; **oversell rejected with the server's plain-English message** ("cannot sell 500 of ADBL: only 10 held in the ledger"); a symbol with no stored price shows as unvalued with a warning rather than being carried at cost |
| Journal | `TESTED-PASS` — with no closed trades the win rate, avg R and adherence render as **"—", never as 0%**; with real entries, stats/per-strategy/grading work and an ungradable entry shows the server's explanation; the planner returns risk/share, R:R, units, cash used and actual risk |

Test rows created during browser verification were deleted through the UI and the API:
the owner's journal, ledger and floor-sheet tables are empty.

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
5. **Fundamentals and News/Events do not exist** (rows 6 and 7), and the **floor sheet
   has never been run on real data** — it is unit-tested against synthetic CSVs only.
   Nothing about real published floor-sheet headers has been proven.
6. **Backtest fills are optimistic at the bar level.** Next-bar-open is honest about
   *when* you could trade, but it assumes the open was available in full size. Liquidity
   and impact are not modelled.
7. **The relative-strength ranking compares only the 60 locally stored symbols**, not
   NEPSE. The UI states this.
8. **PDF extraction is incomplete.** The 52-page handwritten journal has been located
   and is OCR-ready, but no page has been fully extracted and validated yet. See
   `docs/WRITTEN_DATA_PDF_AUDIT.md`.

## 5. Verification log

Evidence, not assertions. Everything below was executed and observed.

| What | How | Result |
| --- | --- | --- |
| Full test suite | `uv run pytest` | **466 passed, 0 failed**, ~20 s |
| Lint / format | `ruff check .`, `ruff format .` | clean |
| Real data in the store | `GET /api/status` on the running server | 89,580 bars, 60 symbols, 1995-07-20 → 2026-10-09 |
| Every browser tab | Playwright, clicking through all 8 tabs | **0 console errors** |
| Research assistant honesty | Asked "will ADBL go up tomorrow?" | Refused verbatim, listed what it can answer instead, showed no numbers |
| Research citations | Read the rendered table from the DOM | 33 findings for ADBL, every row carrying value + unit + window + definition; zero `undefined`, zero `[object Object]` |
| Portfolio oversell | Sold 500 ADBL while holding 10 | Rejected: "cannot sell 500 of ADBL: only 10 held in the ledger" |
| Journal empty state | Read the stats cells with no closed trades | "—" for win rate, avg R and adherence — not 0% |
| Planning | entry 300 / stop 285 / target 340, 100,000 at 1% | risk/share 15.00, R:R 2.6667, 66 units, 19,800 cash, 990 actual risk (0.99%) |
| Backtest on real data | ADBL sma_cross(20,50), 3,659 bars | +223.48% vs buy-and-hold +168.95%, maxDD −54.41%, Sharpe 0.43, 44 trades, 9 assumptions listed |
| Floor-sheet analysis | Second server instance with `MEGATOOL_DATA_DIR` pointing at a throwaway directory | import 3 rows, re-import adds 0, HHI 5000.0 / 7222.22 **matching the hand calculation**, bad file → 400 naming the missing columns |
| Database isolation | Inspected the real SQLite after every test run and every browser session | journal, ledger, positions and floor-sheet tables all empty |
| CLI under a running server | `megatool init` while `serve` holds the DuckDB lock | friendly explanation instead of a traceback, exit code 1 |
| Journal stats on a legal thesis-only entry | POST then GET /api/journal/stats | **200** with `closed_without_entry_price` and an explanatory warning (was HTTP 500) |
| Counterparty share denominator | 12 buyers × 100 + one × 700, top=10 | BIG reads **36.84%** (was 43.75%); shown shares sum to 84.21%, not a forced 100% |
| Currency-prefixed rate | `Rs. 1,000` in a floor-sheet CSV | parsed as 1000, amount 100,000 (was 0.1 → 10,000) |
| Impossible exit | exit_price −5 and NaN | 400 naming the field (was graded as a real stop) |
| Backdated sell | sell dated before its funding buy | 400 with the reason (was accepted, corrupting realised P&L) |
| Typo'd journal field | `entry_prc` | 400 listing the unknown field (was 200, data silently dropped) |

## 6. How to run it

```bash
cd "Downloads/AI trading NEPSE"
uv sync
uv run megatool init      # create the databases
uv run megatool fetch     # download real history (network)
uv run megatool serve     # http://127.0.0.1:8710
uv run pytest             # 466 tests
```
