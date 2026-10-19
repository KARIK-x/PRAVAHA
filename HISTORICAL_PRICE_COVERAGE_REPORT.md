# HISTORICAL PRICE COVERAGE REPORT
Date: 2026-10-17 | Source: code inspection + database queries

## Index Coverage (NEPSE Composite)

### Source: socrateai-official/nepse-open-data (MIT license)
- **Records**: 5,350 (2003-07-17 to 2026-10-15)
- **Genuine OHLC**: 2,217 (41.4%) - from 2016-11-28
- **Placeholder (close-only)**: 3,079 (57.6%) - 2003-07-17 to ~2016-11-27
- **Invalid**: 54 (1.0%) - OHLC ordering violations >0.01
- **With turnover**: 2,413 (45.1%) - 2016-04-17 onwards
- **Without turnover**: 2,937 (54.9%) - pre-2016
- **Null/zero close**: 0
- **Duplicate dates**: 0
- **Gaps >7 days**: 22 (holidays/weekends)

### Source: binayabaral/nepal-market-data (MIT license)
- **Records**: 6,718 (1997-07-20 to 2026-10-15)
- **Genuine OHLC**: 2,374 (35.3%) - from 2016-06-06
- **Placeholder**: 4,344 (64.7%) - 1997-07-20 to 2016-06-05
- **Volume**: traded_quantity EMPTY for ALL rows (0/6,718)
- **Turnover**: traded_amount non-zero for 2,385 rows (35%)

### Cross-Source Comparison
- Overlapping dates: 5,340
- Exact close match: 3,692 (69.1%)
- Small diff (<0.5): 1,508 (28.2%) - rounding
- Large diff (>=0.5): 140 (2.6%) - concentrated 2009-2011

## Individual-Stock Coverage

### Price Bars (DuckDB)
- **Symbols**: 372 (from existing data)
- **Total bars**: ~515,327 (1995-2026)
- **Date range**: varies by symbol
- **Genuine OHLC**: All price_bars have OHLCV (verified per-symbol)
- **Adjustment status**: Unadjusted (bonus/split not accounted for)

### Data Quality
- All price_bars have validation_status field
- Quality flags: suspect, invalid, missing
- Source provenance: source, retrieved_at, source_url

## Genuine OHLC vs Close-Only

### Index (NEPSE)
- Genuine OHLC: 2,217 rows (2016-11-28 to 2026-10-15)
- Close-only: 3,079 rows (2003-07-17 to ~2016-11-27)
- Invalid: 54 rows

### Individual Stocks
- All 372 symbols have genuine OHLCV in price_bars
- No close-only stock records (all have OHLC)

## Historical Highs/Lows Availability
- **Period high/low**: Available for genuine OHLC rows only
- **52-week high/low**: Available for stocks (from price_bars)
- **Historical range**: Available for stocks
- **Swing highs/lows**: Available for genuine OHLC rows only
- **Close-based swings**: Available for all rows (separate method)

## Data Provenance
- socrateai: NEPSE official API (via YONEPSE), MIT license
- binayabaral: published NEPSE index files, MIT license
- YONEPSE: near-live snapshot (delayed 30-70 min), no explicit license
- price_bars: community-maintained GitHub dataset

## Missing Date Ranges
- 22 gaps >7 days in NEPSE index (holidays, weekends, market closures)
- Expected for trading data

## Invalid Records
- 54 rows with OHLC ordering violations >0.01
- Recorded but not corrected
- Classified as 'invalid' in database

## Historical Highs/Lows Calculation
- Genuine daily high/low: requires verified source data (available for stocks, 2017+ for index)
- Closing price cannot establish true daily high/low
- Close-based swing analysis: separate method, clearly labeled
- Support/resistance: from genuine OHLC only
