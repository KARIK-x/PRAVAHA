# KRONOS TRAINING DATA REMEDIATION — PHASE 2 REPORT
Date: 2026-10-17 | Audit-only | No training performed

## 1. Pipeline Trace

### Source
- Database: data/dev/release/processed/megatool_market.duckdb (copy: /tmp/market_copy.duckdb)
- Table: price_bars
- Columns: id, symbol, trading_date, open, high, low, close, volume, turnover, percent_change, transactions, source, source_url, retrieved_at, validation_status, adjustment_status, flags
- Rows: 515,327 | Symbols: 372 | Date range: 1995-07-20 to 2026-10-15

### Original Pipeline (scripts/kronos_data_prep.py)
- Loads all symbols from price_bars
- Converts to Kronos schema (open, high, low, close, vol, amt)
- amt = (O+H+L+C)/4 * vol
- Sorts by datetime, drops exact duplicates
- Drops rows with NaN in required fields
- Filters symbols with < 101 bars
- Creates chronological splits (train/val/test)
- Serializes as pickle (protocol default)
- Output: data/dev/release/kronos_experiment/

### Issues Found
1. No OHLC validation before including rows
2. No quality filtering (includes suspect + invalid)
3. No placeholder/synthetic detection
4. Pickle incompatibility with current pandas
5. Split overlap (intentional Kronos pattern)

## 2. Quality Classification

### Classification Rules (evidence-backed)
- ELIGIBLE: structurally valid AND validation_status='valid' AND OHLC consistent AND prices > 0
- SUSPECT: flat candles (O=H=L=C), OHLC inconsistent, or validation_status='suspect'
- INVALID: non-positive prices, negative volume, validation_status='invalid'
- Quarantine: suspect records held separately, not in eligible dataset

### Results
| Classification | Count | % |
|---|---|---|
| ELIGIBLE | 451,184 | 87.5% |
| SUSPECT (quarantined) | 64,124 | 12.4% |
| INVALID (excluded) | 19 | 0.004% |
| Total | 515,327 | 100% |

### Quarantine Breakdown
| Reason | Count |
|---|---|
| source_suspect | 10,917 |
| ohlc_inconsistent | 40,554 |
| flat_candle | 12,653 |

### Exclusion Breakdown
| Reason | Count |
|---|---|
| non_positive_price | 19 |

## 3. Data Semantics

- Volume = shares traded (from price_bars.volume, not turnover)
- Turnover = monetary value (separate column, never used as volume)
- OHLC = genuine stock prices (not index data)
- No close-only records in price_bars (all have OHLCV)
- No index data mixed into stock training data

## 4. Isolated Data Artifact

### Output Directory
data/kronos_audit/v2/

### Files Created
| File | Size | Description |
|---|---|---|
| train_data.pkl | 12.2 MB | 351 symbols, 214,760 bars |
| val_data.pkl | 5.7 MB | 351 symbols, 98,022 bars |
| test_data.pkl | 4.6 MB | 351 symbols, 78,690 bars |
| prep_report.json | 1.1 KB | Counts, date ranges, quality |
| quarantined_summary.json | 5.4 KB | Per-symbol quarantine counts |
| checksums.json | 353 B | SHA256 of all artifacts |
| prepare.py | 9.5 KB | Reproducible pipeline script |

### Pickle Compatibility
- Protocol: 4 (compatible with current pandas 2.2.3)
- Round-trip verified: all 3 files load successfully
- Columns: open, high, low, close, vol, amt
- Index: datetime

## 5. Split Audit

| Split | Symbols | Bars | Date Range |
|---|---|---|---|
| Train | 351 | 214,760 | 2010-01-03 to 2022-12-29 |
| Val | 351 | 98,022 | 2022-09-01 to 2024-06-30 |
| Test | 351 | 78,690 | 2024-04-01 to 2025-06-30 |

### Integrity Checks
- Chronological ordering: OK (all symbols sorted)
- No null values: OK (0 nulls)
- OHLC consistency in prepared data: OK (0 inconsistent)
- Feature columns: OK (open, high, low, close, vol, amt)
- Symbol separation: OK (no cross-symbol mixing)
- Train/val overlap: 224 symbols (intentional Kronos pattern with lookback buffers)
- Val/test overlap: ~3 months (intentional Kronos pattern)

### Leakage Assessment
- Overlap is by design (official Kronos split pattern)
- Input windows use lookback=90 bars
- Forecast horizon = 10 bars
- No future target leakage within sequences

## 6. Source Verification

- Source: Community-maintained GitHub dataset (nepse-data-repo)
- Provenance: source, source_url, retrieved_at, validation_status, flags columns
- No independent source comparison performed (would require original NEPSE data)
- License: Not explicitly stated

## 7. Original Files Preserved

- Original DB: data/dev/release/processed/megatool_market.duckdb (untouched)
- Original prep script: scripts/kronos_data_prep.py (untouched)
- Original pickle: data/dev/release/kronos_experiment/ (untouched, incompatible)
- Original prep report: data/dev/release/kronos_experiment/prep_report.json (untouched)

## 8. Test Results

| Check | Result |
|---|---|
| Pickle round-trip (train) | OK (351 symbols, 214,760 bars) |
| Pickle round-trip (val) | OK (351 symbols, 98,022 bars) |
| Pickle round-trip (test) | OK (351 symbols, 78,690 bars) |
| Chronological ordering | OK (all symbols) |
| No null values | OK (0 nulls) |
| OHLC consistency | OK (0 inconsistent) |
| Feature columns | OK |
| Symbol separation | OK |
| Full test suite | 2,370 passed (exit 0) |

## 9. Remaining Blockers

1. **Pickle compatibility**: Resolved (protocol 4, current pandas 2.2.3)
2. **Quality filtering**: Implemented (excludes 19 invalid, quarantines 64,124 suspect)
3. **OHLC validation**: Implemented (0 inconsistent in prepared data)
4. **Source reconciliation**: NOT DONE (no independent source available)
5. **Split overlap**: Documented (intentional Kronos pattern)
6. **Corporate actions**: Not handled (prices unadjusted)
7. **Trading calendar**: Not available (gap checks approximate)

## 10. Final Decision

READY_FOR_INDEPENDENT_REVIEW (with caveats)

The data pipeline has been remediated:
- Quality classification implemented (ELIGIBLE/SUSPECT/INVALID)
- Invalid rows excluded (19)
- Suspect rows quarantined (64,124)
- Pickle compatibility resolved (protocol 4)
- OHLC consistency verified (0 inconsistent in prepared data)
- No fabricated data
- No close-only converted to OHLC
- Turnover not used as volume

Remaining blockers for actual training:
- Source reconciliation not performed (no independent source)
- Split overlap not resolved (intentional pattern, needs documentation)
- Corporate actions not handled
- Trading calendar not available
