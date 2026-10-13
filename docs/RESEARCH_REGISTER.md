# Research Register

Every entry records what was **actually observed**, with the date it was checked and how it
changed the design. Nothing here is inferred from memory: entries that could not be
verified are marked `FAILED` / `NOT VERIFIED` and are listed as gaps rather than
paraphrased as findings.

Register compiled 2026-10-11 / 2026-10-12.

---

## A. External sources — verified by direct fetch

| # | Source / URL | Date | What was actually observed | Design influence |
| --- | --- | --- | --- | --- |
| A1 | `https://www.nepalstock.com/` | 2026-10-11 | HTTP 200, 2,830-byte Angular SPA shell ("Nepal Stock Exchange"). No server-rendered data. | Official market data cannot be read from the public HTML; must go through their API. |
| A2 | `https://www.nepalstock.com/api/nots/*` (11 endpoints enumerated from `main.*.js`) | 2026-10-11 | **Every probe returned HTTP 401** + `WARNING: UNAUTHORIZED ACCESS`. Token comes from `storageService.getCurrentUser().accessToken`, refreshed via `authenticate/refresh-token`. | Official adapter implemented but marked **BLOCKED**; `fetch()` raises `SourceUnavailable`. No index/sector values are shown anywhere rather than faked. No credential use, no token reverse-engineering (Rule 9). |
| A3 | `https://github.com/Aabishkar2/nepse-data` | 2026-10-11 | Repository reachable; ~**372** symbols; per-symbol daily CSVs; newest rows dated **2026-10-09**; history to 1995. **No LICENSE file.** | Chosen as the primary real-data path; attribution stamped per row and in the UI; redistribution avoided (`data/` git-ignored); licensing risk recorded in `DATA_SOURCES.md` §1.1. |
| A4 | raw CSVs for NMB / NICL / NABIL from A3 | 2026-10-11 | Fetched successfully; column layout confirmed (OHLCV + turnover + %change). | Fixed the canonical `price_bars` schema and the normaliser's column mapping. |
| A5 | `https://www.sebon.gov.np/` | 2026-10-12 | HTTP 200. Regulator portal: acts/regulations/circulars, IPO-FPO lists, right-share & bonus-share registers, prospectuses, "Quarterly Statistics" and annual reports as **publications**. Mostly Nepali. No machine-readable market API observed. | Fundamentals Lab must accept manual/CSV import with per-field provenance instead of promising automatic disclosure sync. |
| A6 | `https://www.nrb.org.np/` | 2026-10-12 | HTTP 200, 199,746 bytes, "Nepal Rastra Bank (NRB) — the official site of the Central Bank of Nepal". | Confirmed as the authoritative source for macro/policy-rate context; no API integration attempted — macro context would be manual. |
| A7 | `https://merolagani.com/` | 2026-10-12 | HTTP 200. Title advertises "News, Live Trading, Live Floorsheet, Indices, Company Announcements and Report". **No `/api/…` URLs referenced in the homepage HTML.** | Confirms floor-sheet and index analysis are considered valuable by the market — and that a public API is not advertised on the front page. We do **not** scrape it: floor-sheet analysis is import-based. |
| A8 | `https://www.sharesansar.com/` | 2026-10-12 | HTTP 200, "No.1 online financial portal of Nepal". **No `/api/…` URLs in homepage HTML** (only a GTM iframe). | Same conclusion as A7: competitor data is presented as pages, not a documented API. |
| A9 | `https://duckdb.org/docs/current/connect/concurrency.html` | 2026-10-12 | DuckDB docs: read-write mode = **one process**; in-process concurrency supports concurrent writes only when they don't conflict (MVCC + optimistic control); conflicts raise transaction errors; multi-process writes are beta (Quack) until DuckDB 2.0. | Backs the single-store + store-lock design; we serialise at the store level rather than relying on engine-level conflict handling. |
| A10 | `github.com/tradingview/lightweight-charts` licence | 2026-10-11 | **Apache License 2.0** confirmed; v4.2.3 standalone bundle vendored with the licence text. | Vendoring is legally clean; UI carries visible attribution. |
| A11 | `https://www.cdsc.com.np/` | 2026-10-12 | **FAILED** — HTTP fetch timed out. | none. CDSC data must not be assumed available. |

## B. Failed tooling (recorded so gaps aren't mistaken for findings)

| # | Attempt | Result |
| --- | --- | --- |
| B1 | Web search — "NEPSE forecasting paper S2666827022000706" | **FAILED** ×1 (`Web search cancelled`) |
| B2 | Web search — "NEPSE price prediction machine learning paper" | **FAILED** ×2 |
| B3 | Web search — broader retry | **FAILED** ×3 |

**Consequence:** the NEPSE forecasting paper named in the project brief was **not**
retrieved this session, so no claim in this repository is based on it. The Forecasting
Lab must cite its own sources when it is built. Retry when the search tool recovers.

## C. Environment and dependencies — verified by inspection

| # | Item | Observed value |
| --- | --- | --- |
| C1 | Python | 3.12.3 |
| C2 | FastAPI / Starlette / Uvicorn | 0.143.0 / 1.7.0 / 0.54.0 |
| C3 | Pydantic | 2.14.0 |
| C4 | pandas | **3.0.6** (major version — reinforces rejecting pandas-ta) |
| C5 | NumPy | 2.5.4 |
| C6 | DuckDB | 1.5.6 |
| C7 | pytest / ruff | 9.1.1 / 0.17.0 |
| C8 | TradingView Lightweight Charts | 4.2.3 (Apache-2.0, vendored) |
| C9 | Machine | MacBook M1 arm64, 8 GB RAM, ~9.3 GB free disk after setup |
| C10 | Project footprint | `.venv` 287 MB, `data/` 4.0 MB, `.git` 888 KB |
| C11 | Installed tooling (Phase 0) | uv 0.12.10, git 2.39, node 24 |

## D. Method validation

| # | Check | Result | Influence |
| --- | --- | --- | --- |
| D1 | Wilder's published RSI worked example | first two published values (70.46, 66.25) **match exactly**; later values drift <0.1 due to rounding in the published table | indicator engine keeps full precision; test documents the drift instead of fudging constants |
| D2 | Idempotent upsert on real data | 9,561 real rows re-ingested → **0 inserted** | re-running `fetch` is safe |
| D3 | Data-quality sweep of 9,561 real rows | `open` outside day range in **~15%** of rows; `close` outside in **2 of 9,561**; overall suspect rate **1.31%**; AHPC has 9 `high_low_inverted` rows | `open_outside_range` demoted to severity `info`; invalid rows retained and flagged, never deleted |
| D4 | DuckDB connection shared across API threads | unlocked: **95 bad reads / 3,200**; locked: **0** | store-level `RLock` (`ARCHITECTURE.md` §4) |
| D5 | Browser verification (Playwright) | 4 tabs loaded, **0 console errors**; screenshots committed under `docs/screenshots/` | front end is verified by execution, not by reading code — this is how the chart-range and indicator-alignment defects were found |
| D6 | Test isolation — real database pollution found | a journal-test helper omitted its `db_path`, so **14 synthetic rows** were written into the owner's real `megatool_state.sqlite` during a normal test run | rows identified (single-letter symbols, identical thesis, identical timestamp) and deleted; the helper now requires the path; an **autouse fixture** redirects both databases to `tmp_path` for every test. A full suite run afterwards leaves the real DB empty — verified, not assumed |
| D7 | Duplicate route found by lint | a stub `GET /api/portfolio` from an earlier session was still registered **before** the real implementation, so it silently answered instead of it (FastAPI matches in registration order). Ruff F811 caught it | stub deleted; the route table in `ARCHITECTURE.md` §5 now records that literal paths must precede `{param}` patterns for the same reason |
| D8 | Seasonal-naive guard bug | the minimum-data guard was computed from the **full** series length, so it passed and the fit then raised `IndexError` once the hold-out was sliced off | requirement is now `period + holdout` (the training window must still contain a whole cycle) and the function raises a clear `ForecastError`. A defensive check was added inside the routine as well |
| D9 | Relative-strength window bug | the 3-month ranking measured each symbol's return from its **first stored value**, silently turning a 3-month figure into a lifetime figure | now measured from the first valid value **inside** the ranking window; a regression test asserts a stock that doubled long ago but is flat over the window reports ~0% |
| D10 | Expectations that encoded a wrong model of the code | five forecast tests assumed the *future* projection equalled the *hold-out* prediction; the future fit legitimately uses all data | tests corrected to assert both windows separately, which is what makes the distinction testable at all |
| D11 | **Walk-forward validation of the ranking** (T-16) | The momentum-heavy ranking's top quartile **underperformed its bottom quartile in every window tested**. Mean spread: Q 1995–2007 **−11.80%**, Q 2008–2017 **−0.16%**, Q 2018–2026 **−2.96%**, Q 1995–2026 **−3.19%**, M 2015–2026 **−1.37%**. The long portfolio underperformed the equal-weight benchmark in every window (e.g. Q 1995–2026: **194.9% vs 1458.0%** cumulative). The observed spread sits at or below the **5th percentile of the random-selection distribution in 4 of 5 windows** — the ranking is significantly *worse* than chance, not merely noise. | The ranking is **not** validated as a signal. It is kept because it is transparent and decomposable, but it must not be presented as predictive. `megatool/walkforward.py` + `scripts/walk_forward_report.py` reproduce this; `POST /api/walk-forward` and `megatool walk-forward` expose it. The finding is recorded with its caveats (survivorship bias, no costs, price/volume factors only) and is **not** evidence of future returns. |
| D12 | **Defect + factor attribution audit of the ranking** (Priority Two) | Two findings. **(a) Defect:** 20.3% of ranked symbol-periods had a start price older than 30 days (p90 gap **692 days**, max 3,402 days) — suspended symbols were ranked on stale momentum and their "forward return" was measured from a price the portfolio never held. **Fixed** with a tradeability gate (exclude if last bar > 30d before T). **The fix made the result worse** (Q 1995–2026: −3.19% → **−3.71%**), which is the integrity signal — it was not result-shopping. **(b) Attribution:** ranking each factor alone, 4 of 5 are negative (momentum_3m −1.95%, momentum_6m −3.00%, volume_trend −1.84%, near_52w_high −1.64%); only **low-volatility is positive (+0.85%)**. Tested across other windows, low-vol is negative in 3 of 4 (including **−7.44%** in 2008–2017) and positive only in 2018–2026 — the window it was selected on. | **No method passed validation.** Low-vol is a candidate hypothesis, not a validated strategy: there is no untouched hold-out (2018–2026 was examined before the hypothesis was nominated), so selecting the best of 6 weightings × 5 windows is multiple-comparisons in-sample selection. Full analysis in `docs/RANKING_VALIDATION_REPORT.md`. |

---

## E. Gaps (planned but NOT inspected)

These were named in the brief. They are listed so nobody later mistakes them for
researched items.

| Source | Status |
| --- | --- |
| NEPSE forecasting paper `S2666827022000706` | **NOT VERIFIED** — search tool failed (B1–B3) |
| `cdsc.com.np` | **FAILED** — timeout (A11) |
| Floor-sheet endpoints of third-party sites | not inspected — we do not scrape them |
| `nchartpro`, `nepsetrading`, `nepal-share`, `sharehubnepal`, `merocharts`, `nepsestock`, `nepsezai`, `punji` | **NOT INSPECTED** |
| `nepalstock.com` `/floor-sheet` and `/company` data payloads | unreachable (A2), not inspected |
| Reddit r/NepalStock | **NOT INSPECTED** |
| lawcommission.gov.np | **NOT INSPECTED** |
| TA-Lib / pandas-ta / VectorBT / backtesting.py packaging | **NOT TESTED empirically** — rejected from documented reasoning in `TECH_STACK_DECISIONS.md` §5, not from measured failures |
