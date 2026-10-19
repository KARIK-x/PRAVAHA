# NEPSE DELAYED MARKET DATA — INVESTIGATION REPORT
Date: 2026-10-17 | No code changes made. No databases modified.

## 1. Delayed feed trace

### Source: yonepse (shubhamnpk/yonepse)
- **Type**: GitHub Pages snapshot (read-only, public)
- **Base URL**: https://raw.githubusercontent.com/shubhamnpk/yonepse
- **Files**: `data/market/live.json` (per-security quotes), `data/market/indices.json` (index snapshots), `data/market/status.json`
- **Adapter**: `megatool/datasources/yonepse.py`
- **Collection**: `megatool/collector.py` fetches snapshots via `fetch_market_snapshot()`
- **Provenance**: `source="yonepse/market/live.json"`, `retrieved_at` (collection time), `last_updated` (source publication time)

### Fields provided by yonepse
- **Per-security (live.json)**: symbol, ltp, open, high, low, close, volume, turnover, percent_change, last_updated
- **Index (indices.json)**: index name, close, high, low, previousClose, change, perChange, fiftyTwoWeekHigh, fiftyTwoWeekLow, generatedTime
- **Status (status.json)**: is_open, last_checked, etc.

### What the 30-70 minute delay means
- The `last_updated` timestamp in live.json is the source's publication time.
- The `retrieved_at` is when Mega Tool collected it.
- The delay is the difference between these two timestamps.
- This is a **publication delay**, not a polling delay or a cache issue.
- The data is near-live (delayed), not real-time. The UI labels it "DELAYED".

## 2. Data stores

### Historical (DuckDB: megatool_market.duckdb)
- **Table**: `price_bars` — symbol, trading_date, open, high, low, close, volume, turnover, percent_change, validation_status, flags, source, retrieved_at
- **Index table**: `index_series` — index_name, trading_date, close, source, retrieved_at (CLOSE ONLY, no OHLC, no volume)
- **372 symbols, 515,327 bars** (daily, 1995-2026)
- **NEPSE index**: 6,720 rows (1997-07-20 to 2026-10-16), close only

### Market Intelligence (SQLite: market_intelligence.db)
- Sources, articles, sentiment_results, events
- 100 sources imported, 195 articles collected, 195 sentiments

### Live quotes (SQLite: app DB)
- collector_quotes table: per-security near-live quotes from yonepse

## 3. Volume classification

| Series | Type | Definition | Available? |
|---|---|---|---|
| price_bars.volume | Individual stock traded volume | Genuine per-security daily volume | YES (372 symbols) |
| price_bars.turnover | Individual stock turnover | Genuine per-security daily turnover | YES |
| index_series (no volume column) | Market-wide volume | NOT AVAILABLE | NO |
| yonepse indices.json | Current-session index | close, high, low, previousClose (single snapshot) | YES (near-live, 4 indices) |
| Sum of stock volumes | Market-wide approximation | MISLEADING (different coverage, double-counting risk) | NOT RECOMMENDED |

**Conclusion:** No genuine market-wide volume series exists in the historical data. The `index_series` table has no volume column. Individual stock volumes cannot be summed to produce index volume (different coverage, potential double-counting). The yonepse near-live snapshot provides current-session index OHLC but not historical daily OHLC.

## 4. Index OHLC availability

| Field | Historical (index_series) | Near-live (yonepse indices.json) |
|---|---|---|
| Open | NO | NO (has previousClose, close, high, low) |
| High | NO | YES (current session high) |
| Low | NO | YES (current session low) |
| Close | YES (6,720 rows, 1997-2026) | YES (current session close) |
| Volume | NO | NO |

**Conclusion:** Historical NEPSE index has close-only data. Near-live snapshot provides current-session high/low but not historical daily OHLC. No genuine historical OHLC exists for the NEPSE index.

## 5. Why index_series lacks OHLC/volume

The index_series table was designed for the relative-strength benchmark (close-price comparison). It was populated from supplied published index files (binayabaral/NEPSE_INDEX.csv) which contain only closing values. The yonepse near-live snapshot provides current-session OHLC but has not been historically archived.

## 6. Smallest safe implementation path

### For NEPSE index chart (already implemented)
- Close-only area/line chart using actual closing values
- No fabricated OHLC candles
- Close-based pivot detection (clearly labeled as close-based, not OHLC-based)
- No volume panel (no genuine market-wide volume)
- Honest "closes only" label

### For volume (if market-wide volume is needed)
- Option A: Collect daily yonepse index snapshots over time to build a historical volume series (requires ongoing collection, ~months to accumulate)
- Option B: Sum individual stock volumes with explicit coverage documentation (misleading, not recommended)
- Option C: Keep unavailable (current, honest)

### For index OHLC (if needed for conventional swings/ATR)
- Option A: Collect daily yonepse index snapshots to build historical OHLC (requires ongoing collection)
- Option B: Keep close-based pivots (current, honest)
- Option C: Use the existing close-based swing approximation (already implemented)

### Recommended: Keep current implementation (close-only + close-based pivots)
The existing implementation is honest and functional. Collecting daily snapshots would take months to build a meaningful historical series. The close-based pivot alternative provides useful (if approximate) analysis without fabricating data.

## 7. Summary
- **Volume**: BLOCKED (no market-wide volume series; individual stock volumes exist but summing is misleading)
- **Index OHLC**: BLOCKED (historical close-only; near-live snapshot has current-session OHLC only)
- **Close-based pivots**: IMPLEMENTED (honest approximation, clearly labeled)
- **Delayed feed**: yonepse near-live snapshot, 30-70 minute delay, provides per-security OHLCV + index close/high/low (current session only)
- **Historical index**: 6,720 close-only rows (1997-2026), from supplied published files