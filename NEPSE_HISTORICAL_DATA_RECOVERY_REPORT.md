# NEPSE HISTORICAL DATA RECOVERY REPORT
Date: 2026-10-17 | No commits, pushes, or deployments made.

## 1. Sources investigated

### Candidate 1: YONEPSE (shubhamnpk/yonepse)
- Type: GitHub Pages snapshot (near-live, delayed 30-70 min)
- License: Not explicitly stated; data is a compilation of NEPSE official API data
- Fields: Per-security OHLCV + index snapshots (close, high, low, previousClose) - current session only
- Historical?: NO - single snapshot per session, not archived historically
- Verdict: Useful for near-live data only. Not suitable for historical recovery.

### Candidate 2: binayabaral/nepal-market-data (MIT license)
- Type: Daily-updated CSV in git
- License: MIT (verified via GitHub API)
- Fields: published_date, open, high, low, close, per_change, traded_quantity, traded_amount, status
- Historical?: YES - 6,718 rows (1997-07-20 to 2026-10-15)
- OHLC: Genuine from 2016-06-06 (2,374 rows); placeholder (O=H=L=C) before that (4,344 rows)
- Volume: traded_quantity is EMPTY for ALL rows (0/6,718) - no volume data
- Turnover: traded_amount has 2,385 non-zero rows (35%, from 2016-05-29)
- Verdict: Useful for OHLC from 2016+ and turnover. No volume. Already available locally.

### Candidate 3: socrateai-official/nepse-open-data (MIT license)
- Type: Per-day CSV files in git (5,350 files)
- License: MIT (verified via LICENSE file)
- Fields: timestamp, open, high, low, close, volume, symbol, date_unix, date
- Historical?: YES - 5,350 daily files (2003-07-17 to 2026-10-15), 16 indices per file
- OHLC: Genuine from ~2017-2018 (2,217 rows); placeholder (O=H=L=C) before that (3,079 rows)
- Volume: volume field present for 2,413 rows (from 2016-04-17). Values are in billions NPR = market-wide turnover, not share volume
- Verdict: BEST source. Genuine OHLC from ~2017, market-wide turnover from 2016. MIT licensed.

### Candidate 4: sssss0008/Nepse-Data-Analysis-From-1997--2022
- Type: Not accessible (repo not found via GitHub API)
- Verdict: Could not investigate. No data acquired.

### Candidate 5: ShareSansarScraper (omitnomis.github.io)
- Type: Documentation site, no downloadable dataset
- Verdict: Not a data source. No data acquired.

## 2. Data actually retrieved

- Source: socrateai-official/nepse-open-data (MIT license)
- Retrieved: 5,350 daily CSV files, extracted NEPSE_index rows only
- Staging location: data/staging/socrateai_nepse_index/nepse_index_ohlc.csv
- Rows: 5,350 (2003-07-17 to 2026-10-15)
- Unique dates: 5,350 (no duplicates)
- File hash (SHA256): b4e2785d4278219536d73b1f8b88fdeddd947dc545f20e55b2d3e7595fcb6788
- Retrieval timestamp: 2026-10-17

## 3. Exact field definitions

| Field | Definition | Source | Units |
|---|---|---|---|
| trading_date | Session date | socrateai CSV filename | ISO date |
| open | Opening index value | socrateai | NEPSE points |
| high | Session high index value | socrateai | NEPSE points |
| low | Session low index value | socrateai | NEPSE points |
| close | Closing index value | socrateai | NEPSE points |
| volume | Market-wide turnover in NPR (not share volume) | socrateai | NPR (billions) |
| ohlc_status | genuine (high!=close), placeholder (O=H=L=C), invalid (OHLC inconsistent) | Derived | categorical |

## 4. Historical coverage and row counts

| Metric | Value |
|---|---|
| Total rows | 5,350 |
| Date range | 2003-07-17 to 2026-10-15 |
| Genuine OHLC | 2,217 (41.4%) - from ~2017-2018 |
| Placeholder OHLC | 3,079 (57.6%) - O=H=L=C=close (pre-2017) |
| Invalid OHLC | 54 (1.0%) - OHLC ordering violated by >0.01 |
| With turnover (volume) | 2,413 (45.1%) - from 2016-04-17 |
| Without turnover | 2,937 (54.9%) - pre-2016 |
| Null/zero close | 0 |
| Duplicate dates | 0 |

## 5. Data quality and placeholder findings

- Placeholder OHLC: 3,079 rows (57.6%) have O=H=L=C=close. These are NOT genuine OHLC observations. The NEPSE index only published closing values before ~2017. These are flagged as 'placeholder' in the database and clearly labeled in the API.
- Invalid OHLC: 54 rows have OHLC ordering violations >0.01 tolerance. These are recorded as 'invalid' but not removed.
- Rounding artefacts: Many genuine rows have close slightly above high or below low by <0.01 due to mixed 2-3 decimal publishing. These are classified as 'genuine' (within tolerance).
- Cross-reference: Compared with binayabaral source on 5,340 overlapping dates. 72.1% exact match (1,490 small mismatches, avg 0.32 pts - rounding). 4 large mismatches (>=5 pts) identified but not resolved.
- Gaps: 22 gaps >7 days (holidays, weekends, market closures) - expected for trading data.

## 6. Volume and turnover conclusions

- No genuine market-wide share volume exists for the NEPSE index in any source.
- The socrateai "volume" field is market-wide turnover in NPR (values in billions), not share volume.
- This is stored as volume_type='turnover_npr' and labeled accordingly in the API.
- Individual stock volumes exist in price_bars but cannot be summed to produce index volume (different coverage, double-counting risk).
- Recommendation: Keep volume disabled for NEPSE index chart. Use turnover for historical index turnover analysis only.

## 7. Files created or changed

### New files
- data/staging/socrateai_nepse_index/nepse_index_ohlc.csv - 5,350 rows of NEPSE index OHLC + turnover
- data/staging/socrateai_nepse_index/metadata.json - source provenance and retrieval metadata
- tests/test_index_ohlc_history.py - 18 focused tests
- NEPSE_HISTORICAL_DATA_RECOVERY_REPORT.md - this report

### Modified files
- megatool/api.py - added /api/indices/{name}/ohlc endpoint (serves historical OHLC from SQLite)
- web/static/app.js - updated NEPSE chart to fetch OHLC data; updated meta line and tooltips
- web/static/index.html - cache-buster ?v=d67

### Database changes
- data/dev/release/processed/megatool_state.sqlite - new table index_ohlc_history (5,350 rows)
- No changes to DuckDB (market_db) - remains locked and untouched
- No changes to production database

## 8. Where newly acquired data is stored

- Raw staging: data/staging/socrateai_nepse_index/nepse_index_ohlc.csv (5,350 rows)
- Normalized DB: index_ohlc_history table in SQLite app DB (5,350 rows)
- Source metadata: data/staging/socrateai_nepse_index/metadata.json

## 9. Whether existing application data was changed

- index_series table (DuckDB): NOT modified - remains close-only (6,720 rows)
- price_bars table (DuckDB): NOT modified
- Existing API endpoints: NOT modified - /api/indices/{name} still returns close-only data
- New table: index_ohlc_history added to SQLite app DB (additive, no existing data changed)
- New endpoint: /api/indices/{name}/ohlc added (additive)

## 10. Features integrated successfully

| Feature | Status | Notes |
|---|---|---|
| Historical OHLC API endpoint | IMPLEMENTED + TESTED-PASS | 5,350 rows, 2,217 genuine |
| NEPSE chart uses OHLC data | IMPLEMENTED + TESTED-PASS | Candlesticks render genuine OHLC; placeholder rows use close |
| Chart meta line shows OHLC coverage | IMPLEMENTED + TESTED-PASS | "2217 OHLC / 3079 close-only" |
| Volume/turnover correctly classified | IMPLEMENTED + TESTED-PASS | Labeled as "market-wide turnover in NPR" |
| Close-based pivots (existing) | IMPLEMENTED + TESTED-PASS | Still works, unchanged |
| OHLC-based swings | BLOCKED | Needs dedicated endpoint using index_ohlc_history data; deferred |
| Genuine index volume | BLOCKED | No market-wide share volume exists in any source |

## 11. Tests executed and actual results

- tests/test_index_ohlc_history.py: 18 passed, 0 failed (0.60s)
  - Staging CSV validation (columns, row count, metadata)
  - DB schema and data validation (row count, no duplicates, OHLC status, volume type, date range)
  - API endpoint tests (status, structure, genuine-only filter, 404)
  - OHLC validity tests (placeholder equality, genuine ordering, volume magnitude)
- Full test suite: 2,361 passed, 0 failed, 0 errors, 0 skipped (57.6s). Exit 0.
- Frontend: node --check clean
- Browser: NEPSE chart loads with OHLC data, 0 console errors

## 12. Attribution and data-rights considerations

- socrateai-official/nepse-open-data: MIT License (Copyright 2025 SocrateAI). Permission to use, copy, modify, merge, publish, distribute, sublicense. Attribution required: copyright notice and permission notice must be included in all copies.
- binayabaral/nepal-market-data: MIT License. Same terms.
- YONEPSE: Derived from NEPSE official API. No explicit license; used for near-live data only.
- Data rights: All data is derived from publicly published NEPSE figures. No authentication bypassed. No private trading records accessed. No secrets exposed.
- Redistribution: The socrateai data is stored locally for research use only. The original repository is not copied into the application.

## 13. Remaining blockers and recommended next steps

1. OHLC-based swings for NEPSE: Implement a dedicated endpoint that computes swings from index_ohlc_history (genuine rows only). Currently, OHLC swings checkbox is disabled for index; close-based pivots remain available.
2. Historical OHLC in DuckDB: The index_series table in DuckDB remains close-only. When the dev server is stopped, migrate index_ohlc_history data into DuckDB by adding open, high, low columns to index_series. This would unify the data model.
3. Sector index OHLC: The socrateai data contains 15 sector indices with OHLCV. These could be imported into a sector_index_ohlc table for sector-relative analysis.
4. Volume (share volume): Still BLOCKED. No market-wide share volume exists. The turnover field (NPR) can be used for historical index turnover analysis.
5. Close mismatch resolution: 4 large close mismatches between socrateai and binayabaral should be investigated (likely data errors in one source).
6. Data freshness: The socrateai data ends 2026-10-15. Ongoing collection needed to keep it current.
7. Dependency CVE audit: Not yet performed (pip audit).
8. Rate limiting: Still opt-in (MEGATOOL_RATE_LIMIT).

## Summary

| Item | Status |
|---|---|
| Historical OHLC data acquisition | IMPLEMENTED - 5,350 rows from socrateai (MIT) |
| Data validation | TESTED-PASS - 2,217 genuine, 3,079 placeholder, 54 invalid |
| Database integration | IMPLEMENTED + TESTED-PASS - new SQLite table, 5,350 rows |
| API endpoint | IMPLEMENTED + TESTED-PASS - /api/indices/{name}/ohlc |
| Frontend chart integration | IMPLEMENTED + TESTED-PASS - candlesticks + meta line |
| Volume (share volume) | BLOCKED - no market-wide share volume in any source |
| Turnover (NPR) | IMPLEMENTED + TESTED-PASS - 2,413 rows, correctly labeled |
| OHLC-based swings | BLOCKED - needs dedicated endpoint (deferred) |
| Close-based pivots | IMPLEMENTED + TESTED-PASS - existing, unchanged |
| Full test suite | TESTED-PASS - 2,361 passed, 0 failed |
