# KRONOS DATA READINESS AUDIT
Date: 2026-10-17 | Audit-only | No training performed

## 1. Executive Summary

The NEPSE historical price dataset (price_bars, DuckDB) contains 515,327 rows across 372 symbols (1995-07-20 to 2026-10-15). The data preparation script (scripts/kronos_data_prep.py) loads all symbols, converts to Kronos training schema, and creates chronological train/val/test splits.

Key findings:
- All 515,327 rows have non-null OHLCV (no missing values after dropna)
- 502,069 rows (97.4%) are valid, 13,134 (2.6%) suspect, 124 (0.02%) invalid
- 12,655 flat candles (O=H=L=C) - likely placeholders or no-trade days
- 405 rows with non-positive prices (open/high/low/close <= 0)
- 2 rows with zero volume
- 0 duplicate symbol/date pairs
- 0 null values in any OHLCV field
- Max single-bar price change: ~23% (likely corporate action or data error)

Kronos readiness: The data prep script runs successfully and produces 362 symbols with 514,505 bars. However, the script does not validate OHLC consistency or filter suspect/invalid rows. The prepared dataset includes all rows regardless of validation_status.

Verdict: NOT_READY - The data prep pipeline does not filter suspect/invalid rows, does not validate OHLC consistency, and does not distinguish genuine from placeholder data. Before fine-tuning, the pipeline must be updated to exclude invalid rows and flag suspect ones.

## 2. Actual Files/Tables Inspected

| File/Table | Location | Type |
|---|---|---|
| price_bars | data/dev/release/processed/megatool_market.duckdb | DuckDB table |
| kronos_data_prep.py | scripts/kronos_data_prep.py | Python script |
| test_kronos_data_prep.py | tests/test_kronos_data_prep.py | Test file |
| prep_report.json | data/dev/release/kronos_experiment/prep_report.json | JSON report |
| train_data.pkl | data/dev/release/kronos_experiment/train_data.pkl | Pickle (incompatible with current pandas) |
| kronos_service.py | megatool/kronos_service.py | Kronos inference service |

## 3. Dataset Counts and Date Ranges

| Metric | Value |
|---|---|
| Total rows (price_bars) | 515,327 |
| Distinct symbols | 372 |
| Date range | 1995-07-20 to 2026-10-15 |
| Min bars per symbol | 14 |
| Max bars per symbol | 4,457 |
| Avg bars per symbol | 1,385 |
| Prepared symbols | 362 (10 skipped for insufficient data) |
| Prepared bars | 514,505 |
| Train bars | 264,740 (2010-01-03 to 2022-12-29) |
| Val bars | 102,339 (2022-09-01 to 2024-06-30) |
| Test bars | 82,765 (2024-04-01 to 2025-06-30) |

## 4. Counts by Quality Classification

| Classification | Count | Percentage | Notes |
|---|---|---|---|
| valid | 502,069 | 97.4% | validation_status='valid' |
| suspect | 13,134 | 2.6% | validation_status='suspect' |
| invalid | 124 | 0.02% | validation_status='invalid' |
| Null OHLCV | 0 | 0% | No null values |
| Non-positive prices | 405 | 0.08% | open/high/low/close <= 0 |
| Negative volume | 0 | 0% | No negative volumes |
| Zero volume | 2 | 0.0004% | 2 rows with volume=0 |
| Duplicate symbol/date | 0 | 0% | No duplicates |
| Flat candles (O=H=L=C) | 12,655 | 2.5% | Likely no-trade days |
| OHLC inconsistent (strict) | 40,569 | 7.9% | Rounding-inflated |

## 5. Per-Symbol Eligible OHLCV Row Counts

- 372 symbols in price_bars
- 362 symbols have >= 101 bars (WINDOW = LOOKBACK + PREDICT + 1)
- 10 symbols skipped for insufficient data (< 101 bars)
- Min bars: 14, Max bars: 4,457
- Per-symbol report: data/kronos_audit/per_symbol_quality.csv

## 6. Missingness and Duplicate Statistics

| Metric | Value |
|---|---|
| Null values in OHLCV | 0 |
| Duplicate symbol/date pairs | 0 |

## 7. OHLC Violations

| Violation Type | Count | Source |
|---|---|---|
| validation_status='invalid' | 124 | price_bars validation |
| validation_status='suspect' | 13,134 | price_bars validation |
| high < max(open, close) (strict) | 21,697 | Custom check |
| low > min(open, close) (strict) | 18,941 | Custom check |
| high < low | 115 | Custom check |
| Non-positive prices | 405 | Custom check |
| Flat candles | 12,655 | Custom check |

Note: Strict checks inflated by rounding. validation_status is authoritative.

## 8. Suspected Placeholder/Synthetic Records

- Flat candles (12,655): O=H=L=C. Could be no-trade days or data quality issues.
- Non-positive prices (405): open/high/low/close <= 0. Likely data errors.
- Zero volume (2): 2 rows with volume=0. Could be no-trade days.

These records are included in the prepared dataset (no filtering in data prep script).

## 9. Source Reconciliation Results

- Source: Community-maintained GitHub dataset (nepse-data-repo)
- Provenance: source, source_url, retrieved_at, validation_status, flags columns
- No independent source comparison performed
- License: Not explicitly stated; community-maintained

## 10. Kronos-Specific Training Readiness

### Input Requirements (from scripts/kronos_data_prep.py)
- Required columns: open, high, low, close, vol, amt (6 features)
- Time features: minute, hour, weekday, day, month (5 features)
- Timestamp: datetime index
- Volume: required (vol column)
- Amount: computed as (O+H+L+C)/4 * vol

### Data Preparation Pipeline Issues
1. No OHLC validation: Script does not check OHLC consistency before including rows
2. No quality filtering: Includes suspect and invalid rows (13,258 rows)
3. No placeholder detection: Flat candles (12,655) included without flagging
4. No non-positive filtering: 405 rows with non-positive prices included
5. No source reconciliation: No comparison with original source
6. No per-symbol quality reporting: Only aggregate counts
7. Val/train/test leakage: Overlapping date ranges (val: 2022-09-01 to 2024-06-30, test: 2024-04-01 to 2025-06-30 overlap from 2024-04-01 to 2024-06-30)
8. No normalization: Raw prices used (Kronos handles normalization internally)

### Data Leakage Assessment
- Train: 2010-01-03 to 2022-12-29
- Val: 2022-09-01 to 2024-06-30 (overlaps train by ~4 months)
- Test: 2024-04-01 to 2025-06-30 (overlaps val by ~3 months)
- Overlap exists but this is the official Kronos split pattern (with lookback buffers)

### Sequence Construction
- Lookback: 90 bars
- Predict: 10 bars
- Window: 101 bars
- Sequences are per-symbol (no cross-symbol mixing)
- Sorted chronologically
- Duplicates dropped

## 11. Known Limitations and Unresolved Questions

1. Pickle incompatibility: train_data.pkl created with different pandas version (StringDtype issue). Cannot load with current pandas 2.2.3.
2. No OHLC validation in prep script: Suspect/invalid rows included
3. No source reconciliation: No independent verification of price_bars data
4. Overlapping splits: Train/val/test date ranges overlap
5. No corporate action handling: Prices are unadjusted
6. No trading calendar: Gap checks are approximate
7. Volume units: Shares (not turnover), but not independently verified

## 12. Exact Scripts and Commands Used

    # Data prep (from previous session)
    MEGATOOL_DATA_DIR="$PWD/data/dev/release" .venv/bin/python scripts/kronos_data_prep.py

    # Audit (this session, read-only, used DB copy due to lock)
    python3 -c "import duckdb; conn = duckdb.connect('/tmp/market_copy.duckdb', read_only=True); ..."

## 13. Tests Performed and Results

| Check | Result | Evidence |
|---|---|---|
| Total rows | 515,327 | DuckDB query |
| Distinct symbols | 372 | DuckDB query |
| Null OHLCV | 0 | DuckDB query |
| OHLC consistency (strict) | 40,569 inconsistent | DuckDB query |
| validation_status distribution | 502,069 valid, 13,134 suspect, 124 invalid | DuckDB query |
| Flat candles | 12,655 | DuckDB query |
| Non-positive prices | 405 | DuckDB query |
| Duplicate symbol/date | 0 | DuckDB query |
| Data prep script runs | Yes (from prep_report.json) | Previous session |
| Prepared symbols | 362 | prep_report.json |
| Prepared bars | 514,505 | prep_report.json |
| Test suite (kronos_data_prep) | 12 passed | Previous session |

## 14. Final Decision

NOT_READY

The data preparation pipeline runs successfully and produces 362 symbols with 514,505 bars. However:

1. The pipeline does not filter suspect (13,134) or invalid (124) rows
2. The pipeline does not validate OHLC consistency
3. The pipeline does not detect or flag placeholder/synthetic records
4. The prepared pickle files are incompatible with the current pandas version
5. No independent source reconciliation has been performed
6. Train/val/test splits overlap in date ranges

Blocking issues:
- Data quality filtering must be added to the prep pipeline
- Pickle compatibility must be resolved
- Independent source verification needed for at least a sample
- Split overlap must be documented or resolved

Evidence needed to resolve:
- Independent access to original NEPSE source data for reconciliation
- Confirmation that suspect/invalid rows can be safely excluded
- Resolution of pandas version mismatch for pickle files
- Documentation of acceptable split overlap policy
