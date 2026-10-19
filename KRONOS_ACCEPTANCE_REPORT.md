# MEGA TOOL — KRONOS ACCEPTANCE REPORT
Audit date: 2026-10-17

## Variants
- Mini: Kronos-mini (16,440,776 B) + Kronos-Tokenizer-2k (15,842,376 B). ctx max 2048. MPS inference verified (NABIL ctx 2000 = 0.59s; ctx 4000 rejected).
- Small: Kronos-small + Tokenizer-base. ctx max 512. Verified.
- Base: Kronos-base + Tokenizer-base. ctx max 512. Verified.

## End-to-end workflow (verified in browser)
1. Select symbol (NABIL) — OK.
2. Load valid historical data (120 daily bars) — OK.
3. Validate input OHLCV bars — service validates; invalid rejected.
4. Select model (base/small/mini) — OK; availability check disables missing weights.
5. Select horizon (1-64) — OK.
6. Submit forecast request — OK.
7. Real model inference — verified (MPS, 4.8s for mini ctx 128).
8. Validate response — OK (rows, context, device, inference_seconds).
9. Display on main chart — OK (amber-outlined bullish/bearish candles, #kf-chip "PREDICTED").
10. Distinguish predicted vs observed — OK (chip + status text + body colors).
11. Inspect metadata — OK (context bars, history span, last close, device, inference, load).
12. Compare with observed — evaluate endpoint (MAE/RMSE/dir vs naive/drift20).

## Guards (verified)
- Stale response: kronosSeq token; stale dropped with status message.
- Symbol mismatch: drawForecastOverlay rejects.
- Timeframe: daily-only enforced (weekly/monthly → honest BLOCKED message).
- Missing weights: mini/small/base disabled with BLOCKED_MISSING_WEIGHTS message.

## Forecaster → chart sharing
- "View last forecast on chart" button copies the exact rows (no re-run), stamps origin. Verified: chip shows "PREDICTED · Kronos-mini · 10 candles".

## Limitations
- Forecast-position drawing overlay (plan-vs-outcome tracking): NOT IMPLEMENTED.
- Deeper multi-window evaluation export: PARTIAL (evaluate returns windows_detail).
- Forecast experiments table in drawer: NOT IMPLEMENTED (backend persists).
- Intraday forecast: BLOCKED (no intraday data).