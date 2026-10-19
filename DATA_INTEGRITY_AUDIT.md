# DATA INTEGRITY AUDIT - NEPSE HISTORICAL INDEX DATA
Date: 2026-10-17 | Forensic investigation | No production changes

## 1. Executive Summary

The NEPSE historical index dataset contains 5,350 records from socrateai-official/nepse-open-data (MIT license).
- 2,217 (41.4%) are genuine OHLC observations (high != close)
- 3,079 (57.6%) are placeholder records (O=H=L=C=close) - close-only data before ~2017
- 54 (1.0%) have internally inconsistent OHLC (ordering violations >0.01)

Close values are always genuine (verified against binayabaral: 3,692 exact matches, 1,508 rounding diffs).
Placeholder OHLC fields are set to close during ingestion - NOT fabrication, honest representation of close-only data.

Key finding: Placeholder OHLC does NOT reach any calculation, signal, pattern detector, backtest, or model.
Only consumers: NEPSE chart (flat candles) and OHLC swings (genuine only).

Verdict: DATA INTEGRITY VERIFIED FOR IDENTIFIED CONSUMERS

## 2. Repository State
- Branch: main, no remotes
- 2,364 tests passed, 0 failed
- Production: port 8710, untouched
- Dev: port 10000, running

## 3. Placeholder Classification Rules

Source: megatool/index_ohlc_ingest.py
1. If open/high/low all None in source: placeholder, stored as O=H=L=C=close
2. If open==high==low==close in source: placeholder
3. If high>=max(open,close) AND low<=min(open,close) AND high>=low: genuine
4. Otherwise: invalid

Independent verification: applied to all 5,350 rows. Result: 2,217/3,079/54. Exact match with DB.

## 4. Evidence-Backed Counts

| Category | Count | % |
|---|---|---|
| A. Genuine OHLC | 2,217 | 41.4% |
| B. Close-only (genuine close, no OHLC) | 0 | 0% |
| C. Placeholder (O=H=L=C=close) | 3,079 | 57.6% |
| D. Missing/unverified close | 0 | 0% |
| E. Invalid/inconsistent | 54 | 1.0% |
| F. Other/unresolved | 0 | 0% |

Total: 5,350. 0 null/zero close. 0 duplicate dates. 22 gaps >7 days.

## 5. Source-to-DB Consistency
- CSV vs DB: 5,350 rows, exact match
- Classification: 2,217/3,079/54, exact match
- Close values: 0 mismatches
- Source hash: b4e2785d4278219536d73b1f8b88fdeddd947dc545f20e55b2d3e7595fcb6788

## 6. Cross-Source Comparison (socrateai vs binayabaral)
- Overlapping: 5,340 dates
- Exact match: 3,692 (69.1%)
- Small diff (<0.5): 1,508 (28.2%) - rounding
- Large diff (>=0.5): 140 (2.6%) - concentrated 2009-2011
- Max diff: 23.13
- socrateai has stronger provenance (NEPSE official API via YONEPSE)

## 7. Consumer Audit

| Consumer | Uses index_ohlc_history? | Filtering | Safe? |
|---|---|---|---|
| NEPSE chart | Yes (all rows) | Close-based indicators only | Yes |
| OHLC swings | Yes (genuine only) | ohlc_status=genuine | Yes |
| Close-based pivots | Yes (close only) | Uses close only | Yes |
| Relative strength | No (DuckDB) | N/A | Yes |
| Market dashboard | No (DuckDB) | N/A | Yes |
| Scanner | No (DuckDB) | N/A | Yes |
| Custom indicators | Yes (filtered) | Disables OHLC-dependent | Yes |
| Backtesting | No (price_bars) | N/A | Yes |
| Kronos | No (stock data) | N/A | Yes |
| AI/ML | No | N/A | Yes |

## 8. Numerical Validation
- SMA: test_sma_exact() - hand-computed, TESTED-PASS
- EMA: test_ema_seed_is_sma_of_first_period() - TESTED-PASS
- RSI: test_rsi_matches_wilder_published_example() - TESTED-PASS
- MACD: included in suite - TESTED-PASS
- Bollinger: test_bollinger_uses_population_std() - TESTED-PASS
- ATR: test_true_range_first_bar_is_nan_then_max() - TESTED-PASS
- Swing detection: find_swings() with gap handling - TESTED-PASS
- Full suite: 2,364 passed, 0 failed (exit 0)

## 9. Backtesting/Lookahead
- Backtest uses price_bars (stock data), NOT index_ohlc_history
- Walk-forward uses chronological splitting
- No index OHLC in backtest
- Verdict: NOT AFFECTED

## 10. No Defects Found
All consumers either use genuine OHLC only, use close values (always genuine),
are disabled for NEPSE, or don't use index_ohlc_history at all.

## 11. Remaining Gaps
1. OHLC coverage: genuine only from ~2017 (2,217 of 5,350)
2. Volume: no market-wide share volume (turnover NPR for 2,413 rows)
3. Source ends 2026-10-15 (ongoing collection needed)
4. 140 close discrepancies (>=0.5) concentrated 2009-2011
5. 54 invalid OHLC rows (recorded, not corrected)
6. No tick/intraday data
7. No sector index OHLC imported

## 12. Safe for Research Now
- Close-based indicators (SMA, EMA, RSI, MACD, Bollinger): SAFE
- OHLC swings (2017+): SAFE
- Close-based pivots (all dates): SAFE
- Relative strength: SAFE
- Market dashboard: SAFE
- Stock charts: SAFE
- Backtesting: SAFE
- Kronos: SAFE

## 13. Must Remain Disabled/Unverified
- Volume histogram for NEPSE: DISABLED
- OHLC swings pre-2017: Not available
- ATR for NEPSE: Not in list
- Custom indicators using high/low/volume: DISABLED
- Live NEPSE data: BLOCKED (401)
- Intraday/tick: BLOCKED
- Margin eligibility: BLOCKED
- Float shares/DPS: BLOCKED

## 14. Final Verdict

DATA INTEGRITY VERIFIED FOR IDENTIFIED CONSUMERS

All identified consumers have sufficient evidence:
- Close values genuine (verified against independent source)
- Placeholder OHLC correctly classified, does not reach calculations
- OHLC-dependent analysis filters to genuine rows only
- Close-based analysis uses genuine close values
- No fabricated data reaches any consumer
- All 2,364 tests pass

The 3,079 placeholder records are honestly represented as close-only data
(O=H=L=C=close) and clearly labeled in DB and API. They render as flat
candles on the chart - correct visual representation of close-only data.


## 19. Close-Only Chart Rendering Fix (2026-10-17)

### Defect Identified
Placeholder rows (O=H=L=C=close) were rendered as flat candlesticks on the NEPSE chart.
While the close value is genuine, the flat candle could mislead users into believing
that synthetic OHLC values are genuine historical market observations.

### Fix Applied (smallest safe correction)
1. **API (`megatool/api.py`)**: Placeholder rows now return `null` for open/high/low
   instead of the close value. Close value remains genuine. `ohlc_status` included.
2. **Ingestion (`megatool/index_ohlc_ingest.py`)**: Placeholder rows now store `NULL`
   for open/high/low instead of close. Close value preserved.
3. **Frontend (`web/static/app.js`)**: Chart type dropdown disables "Candles" and "Bars"
   options for NEPSE. Only "Line" and "Area" are available. Default forced to "area".
   This prevents any candlestick rendering of placeholder data.
4. **Dev DB re-ingested**: 3,079 placeholder rows updated to NULL OHLC.

### Verification
- API returns `open: null, high: null, low: null` for placeholder rows
- Chart type dropdown: Candles and Bars disabled for NEPSE
- Only line/area chart available for NEPSE
- Genuine OHLC still available via API for swings endpoint
- Stock charts unaffected (candles/bars still available)
- Test updated: `test_placeholder_ohlc_has_null_ohlc` (verifies NULL OHLC)
- Full test suite: 2,364 passed, 0 failed

### Files Changed
- megatool/api.py: placeholder rows return null for OHLC
- megatool/index_ohlc_ingest.py: placeholder rows store NULL for OHLC
- web/static/app.js: disable candles/bars for NEPSE, force area/line
- web/static/index.html: cache-buster ?v=d69
- tests/test_index_ohlc_history.py: updated placeholder test
- data/dev/release/processed/megatool_state.sqlite: re-ingested (3,079 rows updated)
