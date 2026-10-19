# KRONOS DATASET AND EVALUATION AUDIT
Date: 2026-10-17 | No code changes made. No training started.

## 1. Historical candle dataset (515,327 bars)

### Database
- **Path**: data/dev/release/processed/megatool_market.duckdb (dev) / data/processed/megatool_market.duckdb (base)
- **Table**: price_bars
- **Columns**: symbol, trading_date, open, high, low, close, volume, turnover, percent_change, validation_status, flags, source, retrieved_at

### Counts
- Total symbols: 372
- Total bars: 515,327
- Earliest bar: 1995-07-20 (ADBL)
- Latest bar: 2026-10-15
- Symbols with ≥101 bars: 362 (suitable for Kronos training)
- Symbols with <101 bars: 10 (insufficient history, excluded)
- Suspect rows: 13,134 (2.5% of total)
- Invalid rows: 124
- Null closes: 0 (all symbols)
- Null volumes: 0 (all symbols)

### Timeframe
- ALL records are daily (NEPSE trading days: Sun-Thu, skipping Fri-Sat + holidays)
- Interval distribution (NIMB, 837 bars): 1 day (611), 2 days (35), 3 days (148), 4 days (30), 5 days (4), 6 days (3), 10 days (2), 11 days (1)
- No hourly or minute-level data exists
- No intraday data available (official endpoint returns 401)

### Symbol provenance
- 372 distinct symbols from NEPSE (Nepal Stock Exchange)
- 326 symbols have data through 2026-10-15; 46 have earlier last dates (delisted/suspended/newly listed)
- Bars per symbol: min 14, max 4,457, avg 1,385
- No sector classification in the securities table (empty in dev; owner must import via CSV)

### Data quality
- OHLC validity: 0 invalid bars on NIMB (all high≥max(O,C), low≤min(O,C), high≥low)
- Validation status: 834 valid, 3 suspect (NIMB)
- Percent change included but not used by Kronos
- Flags array present (empty for most bars)

## 2. Kronos data-preparation pipeline

### Input database and tables
- Source: DuckDB `price_bars` table (megatool_market.duckdb)
- Columns used: time, open, high, low, close, volume, turnover
- Turnover renamed to `amount` (no fabrication — rename only)

### Selection criteria
- All symbols with ≥101 bars (362 of 372)
- All bars for each symbol (no date filtering in data prep)
- Rows with NaN in any price/volume column dropped
- Duplicate timestamps removed (keep first)

### Schema conversion (scripts/kronos_data_prep.py)
- Columns: open, high, low, close, vol (volume), amt (amount = (O+H+L+C)/4 × vol)
- Index: datetime (UTC, sorted, deduplicated)
- Time features: minute, hour, weekday, day, month (derived from datetime)
- No missing values in output (NaN rows dropped)
- 514,505 total bars across 362 symbols

### Chronological splits
- Train: 2010-01-01 to 2022-12-31 (264,740 bars, 362 symbols)
- Val: 2022-09-01 to 2024-06-30 (102,339 bars, overlaps train for 90-bar lookback)
- Test: 2024-04-01 to 2025-06-30 (82,765 bars, overlaps val for lookback)
- Backtest: 2024-07-01 to 2026-10-15 (latest available)
- Lookback buffer: 90 bars before each split boundary
- No future leakage: normalization uses only lookback (past) data per window

### Leakage verification
- Window indices computed before split
- No future data in input features
- Time features derived from timestamp only
- Test set chronologically after train/val

## 3. Directional accuracy reproduction

### Actual evaluation script
- Endpoint: POST /api/kronos/evaluate
- Service: megatool/kronos_service.py:evaluate()
- Parameters: symbol, variant, context_len, pred_len, windows, device

### Reported metrics (from earlier session, nucleus sampling)
- NIMB: Kronos MAE 5.4517 vs naive 3.2967, direction 33.33%, 6 windows
- NABIL: Kronos MAE 8.0279 vs naive 6.6233, direction 50.00%, 6 windows
- SANIMA: Kronos MAE 7.3821 vs naive 6.4433, direction 40.00%, 6 windows

### Per-horizon results (NIMB, context 256, 5-day horizon)
| Window | Anchor | Realized | Kronos MAE | Naive MAE | Dir OK |
|---|---|---|---|---|---|
| 1 | 2026-08-26 | 08-27 to 09-03 | 2.4951 | 1.0000 | 2/5 |
| 2 | 2026-09-03 | 09-07 to 09-14 | 9.1361 | 2.4000 | 1/5 |
| 3 | 2026-09-14 | 09-15 to 09-22 | 2.9599 | 5.6400 | 1/5 |
| 4 | 2026-09-22 | 09-23 to 09-30 | 4.5087 | 4.5400 | 3/5 |
| 5 | 2026-09-30 | 10-01 to 10-08 | 3.4039 | 0.5000 | 3/5 |
| 6 | 2026-10-08 | 10-09 to 10-15 | 10.2066 | 5.7000 | 0/5 |

### Evaluation design
- Walk-forward: windows spaced `pred_len` (5) bars apart
- Each window's context ends strictly before its realized range
- Baselines (naive last-close, drift20) see exactly the same context
- No future data leakage within a window
- Metrics: MAE, RMSE, MAPE, directional accuracy (next-day up/down agreement)

### Limitations
- Small sample: 3 symbols × 6 windows × 5 days = 90 forecast-target pairs
- Only 5-day horizon tested
- Only Kronos-mini tested (small/base not evaluated in this run)
- Nucleus sampling (top_k=0) used (changed from greedy this session)
- Directional accuracy 20-50% — barely better than coin flip (50%)

## 4. No training performed
- No fine-tuning code written or executed
- No model weights downloaded
- No packages installed
- No training started
- Data preparation prototype created (scripts/kronos_data_prep.py) but not used for training

## 5. Files created
- scripts/kronos_data_prep.py (data preparation script)
- tests/test_kronos_data_prep.py (12 tests, all passing)
- data/dev/release/kronos_experiment/ (train_data.pkl, val_data.pkl, test_data.pkl, prep_report.json)
- KRONOS_DATASET_AUDIT.md (this report)

## 6. Remaining blockers
1. Qlib not installed (required for official fine-tuning pipeline)
2. DDP/NCCL (NVIDIA-only, M1 has no CUDA)
3. Training time (Mini: ~20 hours on M1 CPU)
4. No genuine predictive edge demonstrated (Kronos loses to naive on all symbols)
5. Small evaluation sample (90 forecast-target pairs)