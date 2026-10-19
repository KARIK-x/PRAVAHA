# MEGA TOOL — API AND DATA FLOW
# Audit date: 2026-10-14 | Source: verified source inspection
# Status: SUBSTANTIAL — endpoints documented, actual flows verified

## DATA SOURCE -> API FLOW (VERIFIED)
Market data (github.com/Aabishkar2/nepse-data, 514,018 bars / 372 symbols) -> data/processed/megatool_market.duckdb -> market_store.py (get_bars excludes invalid by default) -> quality.py (validation_status: valid/suspect/invalid) -> multitimeframe aggregation -> FastAPI -> frontend

## API ENDPOINTS (ACTUAL FROM api.py)
GET /api/status — server status; verified live (200 OK)
GET /api/bars/{symbol} — daily; verified live
GET /api/bars/{symbol}/weekly — weekly agg; verified 200 OK ADBL
GET /api/bars/{symbol}/monthly — monthly agg; verified (route exists, test 2/2; server needs restart for full live)
GET /api/bars/{symbol}/fibonacci — Fibonacci levels; verified 200 OK
GET /api/bars/{symbol}/levels — S/R zones; verified
GET /api/bars/{symbol}/structure — Swing points; verified
POST /api/rank — Ranking; verified
POST /api/walk-forward — Walk-forward (B-22 timeout ~58-80s documented)
POST /api/fundamentals/import — Import only; 0 real records
GET /api/research/workspace/{symbol} — Research (workspace.py 24/24)

## DATA QUALITY PATH
price_bars -> validate_bar (quality.py) -> flags (F_NON_POSITIVE review, F_ZERO_PRICE hard, etc.) -> _NOT_INVALID excludes invalid; suspect retained -> get_bars -> API include_flagged opt-in -> workspace data_quality -> frontend

## MULTI-TIMEFRAME FLOW
Daily store -> multitimeframe.aggregate -> /weekly or /monthly -> loadChart(tf-select) -> chart

## LIMITATIONS
Browser end-to-end NOT performed (honest).
Full chart overlay coordinate mapping partial.
Real-store /monthly requires server restart for full verification.
B-11 fees placeholder documented (not invented).
B-10 index data unavailable.
T-11 sectors missing; T-12 fees missing; T-13 floor missing.
