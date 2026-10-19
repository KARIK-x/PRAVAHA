# NOTEBOOK FEATURE AUDIT — Mega Tool
Date: 2026-10-17 | Source: direct code inspection

## Company universe and ticker identity
- **Existing implementation:** `megatool/db.py` securities table (symbol, name, sector, instrument_type, delisted, source, first_seen, last_updated). `megatool/sectors.py` provides CSV import with provenance.
- **Data:** 372 symbols in market store (DuckDB). Securities table empty in dev (owner must import via CSV).
- **Status:** PARTIAL — table exists, import works, but dev DB has 0 securities rows. Sector data available in `data/review/sources/yonepse/yonepse_sectors.csv` (649 rows) and `data/review/sources/binayabaral/binayabaral_sectors.csv` (274 rows) but not imported.

## Sector classification
- **Existing:** `megatool/sectors.py` (classify_sectors, import_sectors, read_sectors_csv) with provenance tracking.
- **Status:** IMPLEMENTED but NOT-TESTED in dev (no sector data imported). The `sector` column exists in securities table.

## Quarterly/annual/TTM EPS
- **Existing:** `megatool/fundamentals.py` stores EPS with period_end, period_label, unit, source, verification. 21,698 records, 307 symbols, 5 fields (eps, net_worth_per_share, paid_up_capital, pe, profit). 36 distinct period labels.
- **TTM EPS:** NOT IMPLEMENTED (no TTM calculation exists).
- **Status:** PARTIAL — EPS stored with periods, but no TTM calculation.

## EPS growth and historical comparisons
- **Existing:** No EPS growth calculation found. Fundamentals module has period_gap_days helper but no growth function.
- **Status:** MISSING.

## Price, EPS, net worth, float, DPS
- **Existing:** fundamentals table has eps, net_worth_per_share, paid_up_capital, pe, profit. No float shares, no DPS, no book value per share (can be derived: net_worth_per_share exists).
- **Status:** PARTIAL — EPS, net worth, PE, profit available. Float and DPS missing.

## Company profiles
- **Existing:** `/api/fundamentals/{symbol}/ratios` returns PE, PB, dividend yield. `/api/fundamentals/{symbol}` returns all records. Frontend has fundamentals view with load/import.
- **Status:** IMPLEMENTED (ratios + query). No dedicated profile page.

## Side-by-side comparison
- **Existing:** `/api/fundamentals/compare?symbols=...` returns side-by-side ratios. Frontend has no comparison UI for fundamentals.
- **Status:** PARTIAL — API exists, no frontend comparison view.

## Margin-trading eligibility
- **Existing:** None. No eligibility module, no official rules, no eligibility table.
- **Status:** MISSING. Would need verified official NEPSE/SEBON criteria.

## Filtering, sorting, exports
- **Existing:** Fundamentals import (CSV), query by symbol, summary endpoint. Screener (`/api/screen`) with rule builder. CSV export for screens.
- **Status:** IMPLEMENTED (screening + CSV export). XLSX/PDF export added for screens. No fundamental-specific export.

## Company universe
- **Existing:** 372 symbols in market store (DuckDB). Securities table empty in dev. Sector data available in CSV files but not imported.
- **Status:** PARTIAL — price data exists for 372 symbols; sector classification not imported.

## Sector classification
- **Existing:** `megatool/sectors.py` with classify_sectors, import_sectors, read_sectors_csv. Provenance tracking. Securities table has sector column.
- **Status:** IMPLEMENTED but NOT-TESTED in dev (no sector data imported). Sector CSVs exist (yonepse: 649 rows, binayabaral: 274 rows).

## EPS rankings
- **Existing:** `/api/fundamentals/eps-rankings` endpoint (added this session). Returns 307 symbols with latest EPS, sorted desc.
- **Status:** IMPLEMENTED + TESTED (endpoint returns correct data). No frontend EPS ranking view.

## Company profiles
- **Existing:** `/api/fundamentals/{symbol}` returns all records. `/api/fundamentals/{symbol}/ratios` returns PE, PB, dividend yield.
- **Status:** IMPLEMENTED (API). No dedicated frontend profile page beyond fundamentals view.

## Margin eligibility
- **Existing:** None.
- **Status:** MISSING. Would need verified official NEPSE/SEBON criteria. Handwritten notebook criteria are unverified.

## Filtering, sorting, exports
- **Existing:** Screener with rule builder, CSV/XLSX/PDF export for screens. Fundamentals import/export via CSV.
- **Status:** IMPLEMENTED (screening + CSV/XLSX/PDF export for screens).

## Summary table
| Requirement | Status | Evidence |
|---|---|---|
| Master company universe | PARTIAL | 372 symbols in DuckDB; securities table empty in dev |
| Sector classification | IMPLEMENTED (not tested in dev) | sectors.py with CSV import; sector CSVs exist |
| Quarterly/annual EPS | IMPLEMENTED | fundamentals table: 21,698 records, 307 symbols, 36 periods |
| TTM EPS | MISSING | No TTM calculation |
| EPS growth | MISSING | No growth calculation |
| Price/EPS/net worth/float/DPS | PARTIAL | EPS, net_worth, PE, profit available; float and DPS missing |
| Company profiles | PARTIAL | API exists (/api/fundamentals/{symbol}); no dedicated frontend page |
| EPS rankings | IMPLEMENTED | /api/fundamentals/eps-rankings returns 307 symbols |
| Company comparison | IMPLEMENTED (API) | /api/fundamentals/compare exists |
| Margin eligibility | MISSING | No eligibility module; handwritten criteria unverified |
| Fundamental screener | IMPLEMENTED | /api/screen with rule builder |
| Exports (CSV/XLSX/PDF) | IMPLEMENTED | /api/screen/export.csv/.xlsx/.pdf all work |
| Data provenance | IMPLEMENTED | period_end, period_label, source, source_ref, retrieved_at, verification, notes |
| Data quality | IMPLEMENTED | verification gate (extracted vs reviewed) |

## Known blockers
1. Securities table empty in dev — sector import not run. Sector CSVs available.
2. TTM EPS not calculated — needs quarterly EPS aggregation logic.
3. EPS growth not calculated — needs period-over-period comparison.
4. Float shares and DPS not stored — no data source.
5. Margin eligibility needs verified official rules — handwritten criteria unverified.
6. Company profile page not built — API exists, frontend view is basic.

## Next highest-value work
1. Import sector CSV into securities table (using existing sectors.py).
2. Add TTM EPS calculation to fundamentals module.
3. Add EPS growth calculation.
4. Build company profile frontend view.
5. Implement margin eligibility scaffold with configurable rules (unverified status).