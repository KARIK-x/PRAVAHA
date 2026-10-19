# PRAVAHA — Advanced Chart Analysis Verification Report

**Date:** 2026-10-19 · **Dev:** :10000 · **Prod :8710:** untouched (PID 26596)
**Mode:** Verification only. No code modified.

---

## 1. Implementation status of all 10 analysis categories

### Existing 5 (implemented as LAYER_DEFS entries + plot functions)

| # | Category | LAYER_DEFS | Plot function | Backend endpoint | Scale handling | Status |
|---|---|---|---|---|---|---|
| 1 | Market Structure & Liquidity | `structure` ✅ | `plotMarketStructure()` | `/api/bars/{symbol}/structure` | Price scale (markers + lines) | IMPLEMENTED |
| 2 | Trend Strength & Regime | `trend` ✅ | `plotTrendStrength()` | `/api/bars/{symbol}/indicator` (adx, supertrend, parabolic_sar) | Price scale (overlay lines + markers) | IMPLEMENTED |
| 3 | Momentum, Divergence & Relative Strength | `momentum` ✅ | `plotMomentumDivergence()` | `/api/bars/{symbol}/indicator` (rsi) + `/api/bars/{symbol}/relative-strength` | Price scale (markers + RS line) | IMPLEMENTED |
| 4 | Volatility & Breakout | `volatility` ✅ | `plotVolatilityBreakout()` | `/api/bars/{symbol}/indicator` (bollinger, keltner, atr) | Price scale (BB/KC lines + breakout markers) | IMPLEMENTED |
| 5 | Volume & Accumulation | `volume` ✅ | `plotVolumeAccumulation()` | `/api/bars/{symbol}/indicator` (obv, cmf, ad_line, relative_volume) | **Separate scale** (`volacc`, visible:false) | IMPLEMENTED (fixed) |

### Additional 5 (proposed in mission — status check)

| # | Category | Status | Evidence |
|---|---|---|---|
| 6 | Market Breadth & Participation | **NOT a separate analysis category** — exists as the Market Battery meter on the overview dashboard + the Breadth view | IMPLEMENTED (elsewhere) |
| 7 | Support, Resistance & Price Levels | **Same as #1** (Market Structure) — the "Support & resistance" layer (sr) already exists as a separate LAYER_DEFS entry | IMPLEMENTED (as `sr` layer) |
| 8 | Multi-Timeframe Trend Consensus | **NOT IMPLEMENTED** — Trend Strength uses daily data only; no weekly/monthly consensus | NOT-IMPLEMENTED |
| 9 | Risk & Volatility Analyzer | **NOT a separate analysis category** — volatility metrics exist in the Volatility & Breakout layer + Sasto Share risk panel | IMPLEMENTED (elsewhere) |
| 10 | Volume-Price Relationship & Accumulation | **Same as #5** (Volume & Accumulation) | IMPLEMENTED (as `volume` layer) |

**Conclusion:** The 5 "additional" categories are NOT 5 new analysis drawer entries. They are capabilities that exist in the codebase but are accessed through different UI surfaces (dashboard, Sasto Share, existing layers). Only categories 1-5 are implemented as analysis drawer layers.

---

## 2. Volume & Accumulation rendering fix

### Root cause (confirmed)
OBV, CMF, and A/D are cumulative/oscillator indicators with values in billions (OBV) or -1 to 1 (CMF). They were plotted as `LineSeries` on the **main price scale** (same as price candles, range 500-600). This caused the price scale to auto-adjust to the indicator's range, making price candles invisible — the "huge line" bug.

### Fix
Assigned OBV, CMF, and A/D to a **separate price scale** (`priceScaleId: "volacc"`) with `visible: false` and independent auto-scaling. Price candles remain on the main scale. Verified: on=true, nSeries=3, nMarkers=7, 0 console errors, price candles visible.

### Status: IMPLEMENTED, TESTED-PASS

---

## 3. Scale and alignment verification

| Category | Scale handling | Date alignment | Verified |
|---|---|---|---|
| Market Structure | Price scale (markers + horizontal lines) | Uses `bars[i]` by index | ✅ |
| Trend Strength | Price scale (Supertrend line, SAR markers) | `alignIndicatorToBars` (by date) | ✅ |
| Momentum | Price scale (RS line + divergence markers) | `alignIndicatorToBars` (by date) | ✅ |
| Volatility | Price scale (BB/KC lines + breakout markers) | `alignIndicatorToBars` (by date) | ✅ |
| Volume | **Separate scale** (`volacc`) for OBV/CMF/A/D; markers on price scale | `alignIndicatorToBars` (by date) | ✅ |

All indicators now use `alignIndicatorToBars()` which maps by trading date (inner join), preventing the positional indexing bug where the indicator's full history (3,517 bars) was indexed positionally against the chart's 120 bars.

---

## 4. Toggle, symbol change, timeframe change verification

| Test | Method | Result |
|---|---|---|
| Toggle on | Browser eval (synthetic) | ✅ All 5 categories toggle on |
| Toggle off | Browser eval (synthetic) | ✅ All markers/series cleared |
| Symbol change (NABIL → NICA) | Browser eval | ✅ No stale data, no errors |
| Timeframe change (120 → 250) | Browser eval | ✅ Re-renders correctly |
| Chart reload | Browser eval | ✅ State resets, layers re-apply |
| All 12 layers coexist | Browser eval | ✅ 0 console errors |
| Toggle rapid (150ms) | Browser eval | ✅ State consistent |

---

## 5. Independent calculation verification

| Calculation | File | Independent reference | Test input | Expected | Actual | Tolerance | Result |
|---|---|---|---|---|---|---|---|
| Swing detection | `swings.py:96` | Hand-built zigzag (32 tests) | Peaks/troughs 5 bars apart | 6 swings | 6 swings | exact | TESTED-PASS |
| FVG detection | `swings.py` | 8 hand-built tests | 5-bar series with known gap | 1 FVG | 1 FVG | exact | TESTED-PASS |
| Equal H/L | `swings.py` | 3 hand-built tests | Two highs at 100.0/100.05, tol 0.001 | 1 pair | 1 pair | exact | TESTED-PASS |
| Regime classification | `app.js` | 4 browser eval tests | ADX=30,+DI=25,-DI=15 | trending/bullish | trending/bullish | exact | TESTED-PASS |
| Divergence detection | `app.js` | 3 browser tests | NABIL 120 bars | 2 divergences | 2 divergences | exact | TESTED-PASS |
| Market barometer | `app.js:12006` | Reproduced from API data | adv=199, dec=106, pctAbove50=36.8 | 51.0 | 51.0 | exact | TESTED-PASS |
| TTM EPS (old) | `fundamentals.py:1014` | Sum vs annual across 324 pairs | NABIL FY2024-25 | Should ≈ annual (21.89) | 101.53 (4.65×) | 5% | TESTED-FAIL (fixed) |
| TTM EPS (new) | `fundamentals.py:1014` | N/A (honest unavailable) | Any symbol with EPS records | `None` | `None` | N/A | IMPLEMENTED, TESTED-PASS |
| Backtest costs | `backtest.py` | SEBON PDF (published 2025-07-20) | NPR 100k buy | NPR 360 + NPR 15 | As computed | N/A | UNVERIFIED (rates not reconciled) |

**Note:** Technical indicators (RSI, MACD, Bollinger, ATR, ADX, etc.) are implemented per standard formulas but NOT independently cross-checked against a reference library. Covered by structural invariants only.

---

## 6. Test results

### Full non-browser suite
- **2,971 passed, 33 skipped, exit 0** (118.90s).

### Browser tests
- **47 passed** (19 new + 28 pre-existing):
  - `test_browser_chart_structure.py` — 3 (toggle on, toggle off, symbol switch)
  - `test_browser_chart_trend.py` — 4 (toggle on, toggle off, classifyTrendRegime, coexistence)
  - `test_browser_chart_momentum.py` — 3 (toggle on, toggle off, coexistence)
  - `test_browser_chart_volatility.py` — 3 (toggle on, toggle off, coexistence)
  - `test_browser_chart_volume.py` — 3 (toggle on, toggle off, coexistence)
  - `test_browser_chart_drawing.py` — 3 (last bar, first bar, save/restore)
  - `test_browser_objects_manager.py` — 14 (pre-existing)
  - `test_browser_viz_toolinfo.py` — 14 (pre-existing)

### JS syntax
- `node --check`: OK on app.js, viz.js, kronos_ui.js, indicator_info.js.

### Ruff
- Clean on touched files. 18 pre-existing findings in api.py.

---

## 7. Confirmed bugs and fixes

| ID | Bug | Status |
|---|---|---|
| V1 | Vertical lines slanted (LWC limitation) | FIXED (custom primitive, fillRect) |
| V2 | Chart panning during drawing | FIXED (pressedMouseMove toggle) |
| V3 | Viewport jump on result selection | FIXED (removed scrollToRealTime) |
| V4 | Price reading garbage for out-of-range y | FIXED (bar OHLC fallback) |
| V5 | Volume indicators on price scale (huge line) | FIXED (separate volacc scale) |
| V6 | TTM EPS summed 4 quarters without basis check | FIXED (returns None with reason) |
| V7 | Scanner auto-execution on selection | FIXED (split select/run) |
| V8 | Info modal hidden inside view-charts | FIXED (moved to shell level) |
| V9 | KIMI Breadth tab empty | FIXED (prior session) |
| V10 | P/E chart dominated by near-zero EPS | FIXED (prior session) |
| V11 | Sector rotation dropped entire sector | FIXED (prior session) |

---

## 8. Remaining limitations

1. **Real-browser click testing:** BLOCKED (Playwright doesn't trigger LWC's subscribeClick).
2. **Multi-Timeframe Trend Consensus:** NOT-IMPLEMENTED (only daily data; no weekly/monthly consensus).
3. **Market Breadth & Participation as separate analysis category:** NOT-IMPLEMENTED (exists as dashboard meter + Breadth view).
4. **Risk & Volatility Analyzer as separate analysis category:** NOT-IMPLEMENTED (exists in Volatility layer + Sasto Share).
5. **Volume-Price Relationship as separate analysis category:** NOT-IMPLEMENTED (exists as Volume layer).
6. **TTM EPS computation:** BLOCKED (source basis undocumented).
7. **Sector auto-classification:** NOT-IMPLEMENTED (manual CSV only).
8. **Dividend analysis:** BLOCKED (no DPS data).
9. **Live NEPSE feed:** BLOCKED (401, no credentials).
10. **Technical indicators (numerical):** NOT-TESTED independently.
11. **Transaction costs (rates):** UNVERIFIED (not reconciled against contract notes).
12. **Crossline vertical component:** NOT-FIXED (still slanted, deferred).
13. **Per-tool styling controls:** NOT-TESTED.
14. **Fonts:** Degrade to system families (offline-first).

---

## 9. Files changed (this session)

### Modified
- `web/static/app.js` — volume scale fix (priceScaleId: "volacc"), LAYER_DEFS entries, plot functions, state management, flushMarkers, alignIndicatorToBars helper, TTM EPS hint.
- `web/static/index.html` — cache busters, #ov-battery-breakdown container, #tool-info relocation, #screen-stale banner.
- `megatool/fundamentals.py` — TTM EPS safety fix.
- `megatool/api.py` — FastAPI title/description.
- `megatool/ta/swings.py` — detect_equal_highs_lows, detect_fvgs.
- `tests/test_api.py` — brand assertion.
- `tests/test_swings.py` — 8 new tests.
- `MASTER_MISSION_CHECKLIST.md` — §10 appended.
- `web/static/styles.css` — token system, brand layer, indicator name wrapping.

### New
- `tests/test_ttm_eps.py` — 8 tests.
- `tests/test_browser_chart_drawing.py` — 3 tests.
- `tests/test_browser_chart_structure.py` — 3 tests.
- `tests/test_browser_chart_trend.py` — 4 tests.
- `tests/test_browser_chart_momentum.py` — 3 tests.
- `tests/test_browser_chart_volatility.py` — 3 tests.
- `tests/test_browser_chart_volume.py` — 3 tests.
- `web/static/brand/*.png` — 6 brand assets.
- Multiple report files (PRAVAHA_REBRAND_REPORT.md, PRAVAHA_PHASE0_INSPECTION.md, etc.)

---

## 10. Production safety

- **Port 8710:** PID 26596 (unchanged). Not modified.
- **No commits, push, or deploy.**
- **No destructive Git operations.**
- **All work on dev port 10000.**

---

## 11. Status labels

| Area | Status |
|---|---|
| PRAVAHA rebrand | IMPLEMENTED, TESTED-PASS |
| TTM EPS safety | IMPLEMENTED, TESTED-PASS |
| Indicator readability | IMPLEMENTED, TESTED-PASS |
| Chart drawing (timestamp, panning, viewport, hit-test) | IMPLEMENTED, TESTED-PASS |
| Vertical-line primitive | IMPLEMENTED, TESTED-PASS (canvas pixel) |
| 5 analysis categories (1-5) | IMPLEMENTED, TESTED-PASS |
| Additional 5 categories (6-10) | NOT-IMPLEMENTED (capabilities exist elsewhere) |
| More Scanners selection/execution | IMPLEMENTED, TESTED-PASS |
| Contextual Info modal | IMPLEMENTED, TESTED-PASS |
| Scanner auto-execution fix | IMPLEMENTED, TESTED-PASS |
| Real-browser click testing | BLOCKED (Playwright/LWC limitation) |
| TTM EPS computation | BLOCKED (source basis undocumented) |
| Sector auto-classification | NOT-IMPLEMENTED (manual CSV only) |
| Dividend analysis | BLOCKED (no DPS data) |
| Live NEPSE feed | BLOCKED (401, no credentials) |
| Technical indicators (numerical) | NOT-TESTED (structural invariants only) |
| Transaction costs (rates) | UNVERIFIED (not reconciled) |
| Backtesting (numerical) | NOT-TESTED (independently) |
| Fibonacci (numerical) | NOT-TESTED (structural invariants only) |
| Real-browser interaction | BLOCKED (Playwright limitation) |

---

## 12. Recommended next steps (highest priority)

1. **Obtain real-browser testing capability** (Selenium/Puppeteer with native input, or a test-only click hook with approval).
2. **Fix crossline vertical component** (same primitive approach as vline).
3. **Auto-import sector CSVs** (649 + 274 rows available on disk).
4. **Investigate `priceToCoordinate` fix** (LWC v4.2.3 bug; may need LWC upgrade).
5. **Add TTM EPS tests** for the new "unavailable" contract.
6. **Reconcile broker commission rates** against actual contract notes.
7. **Implement multi-timeframe trend consensus** (weekly/monthly aggregation).
8. **Implement Market Breadth as a dedicated analysis category** (currently only on dashboard).

**Verification complete.** No code modified during this verification. Awaiting your next instruction.
MD
echo "written"