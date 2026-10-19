# MEGA TOOL — MATHEMATICAL VALIDATION REPORT
Audit date: 2026-10-17

## Independently verified (hand fixtures / browser)
- OLS: slope 2, intercept 0, sd 0 on (1,2),(2,4),(3,6),(4,8). Verified via window.__mtMath.olsFitXY.
- OLS2: slope 1.5, intercept 5, sd 0.7071 on hand set. Verified.
- Fib retracement: p2 - r*(p2-p1). fibLevel('retracement', 10, 20, 0.5) = 15. Verified.
- Fib extension: p2 + r*(p2-p1). fibLevel('extension', 10, 20, 1.618) = 36.18. Verified.
- Degenerate OLS (zero variance in x) returns null (no fabricated line). Verified.
- RSI matches independent reference (test_summary). Wilder smoothing.
- ATR period-1 = true range (test_summary).
- MACD identity (test_summary).
- Bollinger hand-computed (test_summary).
- MFI independent reference (test_summary).
- Swings pivot detection (test_swings, 16 tests).
- Walk-forward no look-ahead (test_walkforward, 20+ tests).
- Trailing stop ratchet up-only (test_trailing_stop, 12 tests).
- Volume profile POC/VA (test_volume_profile, 11 tests).
- Gap/breakout post-hoc confirmation (test_gaps_breakouts, 13 tests).
- RS timeframes exact percentages (test_rs_timeframes, 20 tests).

## Conventions documented
- RSI: Wilder smoothing (average gain/loss).
- EMA: standard (k=2/(N+1)) with SMA seed.
- ATR: Wilder smoothing.
- Bollinger: population σ (N denominator) for chart; tests use hand values.
- Regression: sample σ (n-1 denominator).
- Fib: retracement p2-r*(p2-p1); extension p2+r*(p2-p1).

## Look-ahead prevention
- All signals use bars ≤ signal timestamp.
- Replay slices the series to bars up to cursor.
- Pattern confirmation requires future candles → labeled as candidate until confirmed.
- Walk-forward uses chronological splits.

## Not independently verified
- ADX/DI (exists, tested in test_summary).
- Stochastic (tested in test_summary).
- Ichimoku (ta tests).
- Harmonic ratios (ta tests).
- Kronos forecast accuracy (small samples; no profitability claims).

## Test counts
- Backend: 2331 passed, 0 failed, 0 errors.
- Frontend: node --check clean on app.js + kronos_ui.js.
- Browser: 0 console/page errors across the sweep.