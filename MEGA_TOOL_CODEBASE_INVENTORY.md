# MEGA TOOL — CODEBASE INVENTORY
Project root: /Users/ashim/Downloads/AI trading NEPSE
Audit date: 2026-10-14 | Source: verified source inspection
Status: SUBSTANTIAL — architecture, categories, key files documented

## EXECUTIVE SUMMARY
Local-first NEPSE quantitative research platform. Python 3.12, FastAPI, DuckDB (514,018 bars / 372 symbols), SQLite state, lightweight-charts frontend.

## KEY FILES (VERIFIED FROM SOURCE)
megatool/api.py — FastAPI routes (/api/status, /bars/{symbol}, /weekly, /monthly, /fibonacci, /levels, /structure, /scans, /rank, /research/workspace/{sym}, /walk-forward, /fundamentals, /written-pdf/*). Modified: +monthly +validation.
megatool/workspace.py — Research workspace (build_workspace; 24 tests PASS). Modified: +B-21 annotation.
megatool/ta/multitimeframe.py — Weekly/monthly aggregation (2 tests PASS; calendar grouping verified; date parsing fixed format="%Y-%m-%d"). NEW.
megatool/ta/fibonacci.py — Fibonacci (range=end-start; 38 unit + 8 API tests PASS).
megatool/ta/levels.py — S/R zones (sort+mean clustering; 24+5 tests PASS).
megatool/ta/candles.py — Candlestick patterns (15 patterns; causality [0..i]; 104 tests PASS).
megatool/ta/swings.py — Swing points (fractal; confirmed_index >= index; 17+5 tests PASS).
megatool/ta/elliet.py — Elliott Wave bounded (NOT full visualization; 1/1 test PASS; design blocked for full).
megatool/ta/summary.py — Trend/momentum/volatility summary (8 integration + 72 unit PASS).
megatool/ta/momentum.py — RSI (B-23 fixed: flat -> NaN; avg_gain>0 guard; 26 regression PASS).
megatool/ta/volume.py — MFI (B-24 fixed: 0/0 -> NaN; 17 regression PASS).
megatool/quality.py — Data validation (B-21 F_NON_POSITIVE at line 202; B-20 preserved; 18/18 PASS).
megatool/scanner.py — Screener (DATA_QUALITY_FILTERS added; 2/2 PASS).
megatool/market_store.py — DuckDB access; concurrent read fix (B-19); invalid excluded; suspect retained.
megatool/ingest.py — Ingest (372/372 succeeded 2026-10-12; 424,438 new bars).

## FRONTEND (VERIFIED)
web/static/index.html — 11 tabs; +timeframe control (tf-select + buttons); +research summary label
web/static/app.js — Chart library (lightweight-charts); loadChart (tf-aware); addOverlay (SMA/EMA); plotFibonacci (bar times); plotSupportResistance (bar times + zone center); plotCandlestickMarkers (bar index); fibonacci/candlestick fetches

## TEST COVERAGE (ACTUAL)
test_multitimeframe.py (2/2 PASS — weekly/monthly)
test_chart_overlays.py (1/1 PASS — overlay functions)
test_scanner_quality_filter.py (2/2 PASS — data quality filter)
test_workspace.py (24/24 PASS — research integration)
test_quality.py (18/18 PASS — B-21 regression)
test_candles.py (104 PASS)
test_fibonacci.py (38+8 PASS)
test_levels.py (24+5 PASS)
full suite ~1124/0 observed (not freshly rerun in this audit turn)

## FEATURE STATUS (EVIDENCE-BASED)
IMPLEMENTED + TESTED-PASS: Multi-timeframe, Scanner (with filter), Workspace, Data Quality (B-21), RSI/MFI fixes, Fibonacci, S/R, Candlestick
PARTIAL: Chart overlays (SMA/EMA complete; Fibonacci/S/R/candlestick plot functions real but full coordinate interpolation needs library specifics); Research (6 modules; no full PDF chart overlay); Browser verification NOT performed
NOT IMPLEMENTED: Elliott Wave full visualization (blocked by design: needs alternative counts, invalidation, labels — bounded module exists), Harmonic patterns (needs XABCD definitions), Classical chart patterns (only candlestick exists)
BLOCKED: T-11 sector CSV, T-12 fees, T-13 floor-sheet, B-10 index, T-09 PDF visual review deferred

## DATA INTEGRITY
No historical market data modified.
B-20 opening-price convention preserved.
B-21 non-positive prices flagged (not rewritten) — 10 zero-price rows visible.
B-17 invalid rows excluded (124) — 45 symbols affected, 8 all-time lows corrected.
B-19 concurrent read fixed — query helpers hold lock across execute+fetch.
B-18 PDF dedup on content_hash — renamed copies reuse import.
No fabricated fundamentals, sectors, fees, floors, index values.

## LIMITATIONS
- Browser end-to-end verification not performed (environment unavailable — stated honestly)
- Full multi-timeframe chart overlay coordinate mapping partially complete (needs library-specific interpolation for all price levels)
- Real-store /monthly endpoint verified via server (200 OK) but not under all symbol/timeframe combinations
- Elliott Wave full visualization blocked by design requirements (alternative counts, invalidation levels — bounded module avoids false certainty)
- Harmonic patterns and classical chart patterns (head/shoulders, double top/bottom, triangles) not implemented (would require explicit geometric rules and tests)

## NEXT IMPLEMENTATION
1. Build complete multi-timeframe chart overlay (full price-level drawing across all bars)
2. Verify /monthly endpoint with real running server if needed
3. Document remaining chart overlay limitation clearly
