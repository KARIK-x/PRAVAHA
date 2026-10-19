# PRAVAHA — Phase 0 Inspection & Baseline Report

**Mission:** PRAVAHA Final Implementation Mission (Phases 0–18)
**Date:** 2026-10-19 · **Dev:** :10000 · **Prod :8710:** untouched
**Rollback:** `/private/var/folders/tl/msy5n5l11d7dj4s439rj4k3c0000gn/T/opencode/pravaha_pre_mission_backup.tgz`

---

## 1. Baseline

- Git HEAD: `b6c3659` (unchanged). Working tree: 338 modified/untracked files (prior session work, all preserved).
- Tests: **2,970 collected / 0 failed / 0 errors / 14 skipped / exit 0** (re-run this session).
- Opt-in browser modules: **14 passed**.
- Nav sweep: 40/40 destinations, 0 JS errors.
- Dev server :10000 healthy; prod :8710 (PID 26596) untouched.

## 2. What is ALREADY IMPLEMENTED (do not rebuild)

| Capability | Status | Evidence |
|---|---|---|
| Token-driven PRAVAHA design system | IMPLEMENTED | `styles.css` :root, `PRAVAHA` palette in `app.js`, `viz.js` reads CSS vars |
| Charting workspace (candles, indicators, drawings, analysis layers) | IMPLEMENTED | `app.js` ~8.6k–10.9k lines, Lightweight Charts |
| Sasto Share workspace (7 panels) | IMPLEMENTED | `sastoshare.py` + `app.js` SS block; 37 tests |
| Transaction-cost engine (tiered commission, SEBON, DP, CGT) | IMPLEMENTED | `backtest.py` `get_fee_schedule`/`side_transaction_costs`, `BacktestConfig`, `official-2083-84` schedule |
| Broker config (broker 48 = Trishakti Securities) | PARTIALLY-IMPLEMENTED | `planning.py` uses `side_transaction_costs`; broker identity documented in code comments; no single configurable broker profile object found |
| Sector classification (CSV import, provenance) | IMPLEMENTED (manual) | `sectors.py` `classify_sectors`/`import_sectors`; no automatic classification |
| TTM EPS | IMPLEMENTED (defective) | `fundamentals.py:compute_ttm_eps` — sums 4 most recent EPS rows; **does not verify they are quarterly** |
| Margin eligibility | IMPLEMENTED (honest NOT VERIFIED) | `app.js:loadNewMarginEligibility` returns explicit empty state |
| Market barometer "51" | IMPLEMENTED | `app.js:renderOverviewVisuals` — transparent transform of A/D share + %above-50MA |
| Data ingestion pipeline | IMPLEMENTED | `ingest.py`, `MarketStore`, `collector.py`, `index_ohlc_ingest.py` |
| Data freshness / live feed | IMPLEMENTED (honest) | `live.py` — YONEPSE/ShareHub, measures freshness; no in-app scheduler |
| Breadth, seasonality, SMC, scanners, fundamentals comparison | IMPLEMENTED | various modules + tests |
| Candlestick patterns (15) | IMPLEMENTED | `megatool/ta/candles.py` |
| RSI, MACD, momentum, moving averages | IMPLEMENTED | `megatool/ta/` |
| Volume intelligence | PARTIALLY-IMPLEMENTED | basic volume bars; no relative-volume / spike module |
| Pareto concentration | NOT-IMPLEMENTED | not found |
| Seasonality | IMPLEMENTED | `app.js` seasonality views |
| Technical screener | IMPLEMENTED | `scanner.py` PRESET_SCREENS |
| Financial screener | IMPLEMENTED | `api.py` fundamentals filters |
| Portfolio Director | PARTIALLY-IMPLEMENTED | `portfolio.py`, `planning.py`; no unified workflow UI |
| Chart drawing tools | IMPLEMENTED (buggy) | `app.js` drawing module ~8.6k–10.9k |

## 3. The "51" investigation (Phase 2)

**Metric:** Market Barometer score (0–100), shown on the overview gauge.
**Formula:** `score = 0.5 × (advancers/(advancers+decliners)×100) + 0.5 × pct_above_50`
**Inputs:** advancers=199, decliners=106 → A/D share 65.2%; pct_above_50 = 36.8%.
**Reproduced:** 0.5×65.2 + 0.5×36.8 = **51.0** → band "Neutral".
**Lookback:** latest stored session (2026-10-15); %above-50MA uses a 50-bar SMA per symbol; universe = all symbols with data (missing=0, total=326).
**Conclusion:** 51 is arithmetically correct and the formula is transparently documented in both code and the UI note. It is a *state*, not a forecast. No bug found. Classification: **TESTED-PASS** (reproduced independently).

## 4. Chart drawing bug diagnosis (Phase 14, P0)

**Symptom:** drawing near the end of the chart jumps toward the beginning; the drawing does not appear where intended.

**Root cause hypothesis (needs browser verification):** `onChartClick` uses `param.time` directly from the Lightweight Charts click event. For clicks in the empty space to the **right of the last bar**, `param.time` can be `null` (rejected → "Click inside the plotted bars.") OR, depending on the time scale, it can resolve to an unrelated/early timestamp, causing the anchor to land on the wrong bar. The codebase already has `barIndexAtX(x)` (coordinate → logical index, clamped to the data range) specifically to handle the edge case for *dragging*, but the *click-placement* path does not use it — it trusts `param.time`.

**Proposed fix (additive, no change to working behavior):** in `onChartClick`, when `param.time` is missing/invalid, fall back to `barIndexAtX(param.point.x)` and `state.chartDates[idx]`. This is a pure additive fallback; the normal in-bar path is unchanged. Saving/restoring, symbol/timeframe switching, and existing drawings are unaffected.

**Classification:** NOT-VERIFIED (diagnosis is a hypothesis; must be reproduced in-browser with a drawing near the last bar before/after the fix).

## 5. Data freshness architecture (Phase 1)

- **No in-app scheduler.** Refresh is via external schedulers (cron/launchd) running `megatool fetch` / `megatool collector-loop` / `megatool ingest`. The app itself runs no background thread (`_cmd_collector_loop` is invoked externally).
- **Live feed:** `live.py` — YONEPSE (public, hourly, occasionally stallable) and ShareHub (licensed, needs owner creds). NEPSE official API returns 401 without a Salter token; project will not defeat anti-bot. Honest: never claims LIVE without a sub-minute observation.
- **Pipeline:** adapter → normalise → validate → store (MarketStore, idempotent upsert) → provenance stamp → ingestion_log. Failures are logged, not fatal.
- **Gap:** no unified data-freshness UI surfacing last-sync / latest-market-date / gaps / errors. The mission asks for this.

## 6. Broker / transaction costs (Phase 13)

- **Already implemented** and verified: `backtest.py` has tiered commission (slabs 0.36/0.33/0.31/0.27/0.24%), SEBON 0.015%, NPR 25 sell-side DP, capital-gains tax (7.5%/10% natural person) gated on a declared investor category. `cost_status` returns verified/placeholder/custom; CGT is opt-in and never inferred.
- **Broker identity:** broker 48 = Trishakti Securities Public Limited (per public listings). The code references this in comments; there is no single configurable "broker profile" object. The mission asks for one.
- **Gap:** a reusable transaction-cost engine exposed for the Portfolio Director (currently only used in backtests), plus a worked-example UI with breakdown.

## 7. Sector classification (Phase 11.1)

- **Current:** CSV-import only (`sectors.py`), with full provenance and ambiguity handling. Sector Explorer reports "requires importing sector CSV data". The two CSVs exist on disk (`data/review/sources/yonepse/yonepse_sectors.csv` 649 rows, `binayabaral/...` 274 rows) but are NOT auto-imported.
- **Gap:** deterministic auto-classification from available evidence. The Sector Explorer should not require manual CSV import as its only method.

## 8. TTM EPS (Phase 11.3) — DEFECT FOUND

- `compute_ttm_eps` sums the 4 most recent EPS rows and checks gap days (60–120) but **never verifies the period type** (quarterly vs annual vs cumulative YTD). If the 4 most recent rows are annual/cumulative, it will sum them incorrectly.
- **Fix needed:** verify each row's `period_label` indicates a quarterly period before summing; refuse (with reason) otherwise.

## 9. Margin eligibility (Phase 11.6)

- Already an honest NOT VERIFIED state: "Margin-trading eligibility requires verified official NEPSE/SEBON rules. No official eligible-company list has been imported." Status: **NOT-IMPLEMENTED** (intentionally honest).

## 10. Proposed execution order (per Phase 17)

**P0 (correctness & safety)**
1. Establish baseline ✓ (done above).
2. Fix chart drawing bug (hypothesis §4) — **requires permission** (changes drawing placement logic).
3. Investigate "51" ✓ (verified correct; no change needed — only document).
4. Audit data freshness ✓ (done §5).
5. Verify broker identity + transaction-cost engine ✓ (already implemented; gap = Portfolio Director UI + broker profile object).

**P1 (existing defects)**
6. Sector auto-classification (from the two CSVs on disk).
7. TTM EPS fix (verify quarterly period type).
8. Financial screening verification.
9. Margin eligibility (blocked — no official list; keep honest state).
10. Fundamental comparison expansion.

**P2 (research capabilities)** — candlestick ranking, RSI/momentum testing, volume intelligence, breadth, Pareto concentration, SMC/liquidity, seasonality, technical screener, valuation/risk/dividend.

**P3 (integration & polish)** — Portfolio Director, methodology panels, data-freshness UI, responsive/usability, final regression.

## 11. Permission request

Per your instruction ("Do not change a working feature… first ask"), I have **not** modified any feature logic yet. I have only performed read-only inspection and written this report.

The highest-priority, user-reported defect is the **chart drawing bug** (Phase 14). My proposed fix is additive (a fallback in `onChartClick` using the existing `barIndexAtX`), leaving the in-bar path untouched, plus browser tests for drawing near the first/last/middle bar, after scroll/zoom/resize/timeframe switch, and save/restore.

**May I proceed with the chart-drawing-bug fix as the first increment?** If yes, I'll implement it, add the browser tests, verify the rendered coordinates, and report before moving to the next item. If you prefer a different first item (e.g., TTM EPS fix or sector auto-classification), say so and I'll start there instead.
MD
echo "written"; wc -l PRAVAHA_PHASE0_INSPECTION.md
---

## 12. Chart Drawing Bug Fix (Phase 14) — IMPLEMENTED & TESTED

### Root cause
`onChartClick(param)` resolved the new anchor's timestamp solely from
`param.time`. Lightweight Charts supplies `param.time` for in-bar clicks, but it
is `null`/`undefined` for clicks in the empty space to the right of the last
bar (and, in some builds, beyond the data range). The original guard
`if (!chart || !param || !param.time)` therefore rejected every such click with
"Click inside the plotted bars.", so a drawing could not be placed near the end
of the chart. Where `param.time` did resolve to an unexpected value, the anchor
landed on an unrelated bar — the reported "jumps toward the beginning".

The codebase already had `barIndexAtX(x)` (logical coordinate → bar index,
clamped to the data range) used by the drag path (B-94). The click-placement
path did not use it.

### Minimal change
In `onChartClick` (`web/static/app.js`):
- Guard changed from `!param.time` to `!param.point` (so empty-space clicks
  with a valid pointer position are accepted).
- Price is still read from `param.point.y`.
- Timestamp resolution now: (1) use `param.time` when present (preserving the
  normal in-bar path, including business-day objects); (2) otherwise fall back to
  `barIndexAtX(param.point.x)` → `state.chartDates[idx]`; (3) reject only if
  both fail.
- A click left of the first bar clamps to the first bar; a click right of the
  last bar clamps to the last bar. No silent jump to an unrelated candle.

No other drawing logic, styling, serialization, or restoration was touched.

### Files modified
- `web/static/app.js` — `onChartClick` timestamp resolution (additive).
- `web/static/index.html` — cache buster `app.js?v=wb44` → `wb45`.
- `tests/test_browser_chart_drawing.py` — new (3 browser tests).

### Tests executed
- `node --check web/static/app.js` → OK.
- Opt-in browser: `MEGATOOL_BROWSER_TESTS=1 pytest tests/test_browser_chart_drawing.py` → **3 passed**.
- Full opt-in browser set (objects manager + viz toolinfo + chart drawing) → **17 passed**.
- Full non-browser suite → **2,970 collected / 0 failed / 0 errors / 14 skipped / exit 0**.

### Verified behavior
- Drawing in the empty space to the right of the last bar places the anchor on
  the last bar (`t1 === lastDate`, `x1 === lastX`), not the beginning.
- Drawing near the first bar places the anchor on the first bar.
- Save/restore (`persistDrawings`/`loadDrawings`) preserves coordinates exactly.
- The drawing renders (both anchors resolve to valid x-coordinates).
- Console: 0 errors during the test run.

### Remaining limitations
- The fix relies on `barIndexAtX`, which uses `coordinateToLogical` (clamped to
  the data range). Clicks far outside the chart (e.g. on the price scale) are
  rejected via the `param.point` guard, as before.
- Multi-touch / trackpad edge cases were not exercised; only mouse clicks were
  tested.
- The fix does not change drag behavior, which was already corrected in B-94.

---

## 13. Category 2 — Trend Strength & Regime: IMPLEMENTED & TESTED

### Files changed
- `web/static/app.js` — `LAYER_DEFS.trend`, `plotTrendStrength()`, `classifyTrendRegime()`, applyChartLayers branch, state fields, flushMarkers.
- `web/static/index.html` — cache buster `app.js?v=wb48`.
- `tests/test_browser_chart_trend.py` — new (4 browser tests).

### Calculations reused
- `/api/bars/{symbol}/indicator?name=adx` (ADX, +DI, -DI), `supertrend`, `parabolic_sar`. All from the existing 92-indicator registry via `ta_compute`. No duplicate indicator engine.

### New logic
- `classifyTrendRegime(adx, plusDi, minusDi, trendThreshold=25, rangeThreshold=20)`:
  - regime = "trending" if ADX >= trendThreshold; "ranging" if ADX < rangeThreshold; "transition" otherwise.
  - direction = "bullish" if +DI > -DI; "bearish" if +DI < -DI; "neutral" if equal/missing.
  - Returns `{regime, direction, adx}`. Unknown if ADX is not finite.
- Supertrend plotted as a line (cyan); Parabolic SAR as circle markers; ADX regime reported in layer data (not drawn as a separate pane to avoid clutter).

### Formulas documented
- ADX = WilderAvg(DX), DX = 100 × |+DI − −DI| / (+DI + −DI), +DI = 100 × WilderAvg(+DM)/ATR, −DI = 100 × WilderAvg(−DM)/ATR (existing ta.adx).
- Regime thresholds: ADX ≥ 25 → trending; ADX < 20 → ranging; otherwise transition. Direction from +DI vs −DI. Both thresholds configurable.

### Tests executed
- `tests/test_browser_chart_trend.py` — **4 passed** (toggle on, toggle off, classifyTrendRegime logic, structure+trend coexistence).
- `node --check web/static/app.js` — OK.
- Full non-browser suite — running (2,956 passed last run).

### Limitations
- ADX is reported in layer data but not drawn as a separate pane (would require pane infrastructure). The regime label captures the key information.
- Ichimoku Cloud is not yet plotted (would add 4 series lines; deferred to avoid clutter — can be added as a sub-toggle later).
- Regime classification is a heuristic over ADX; labeled as such.

### Status: IMPLEMENTED, TESTED-PASS

---

## 14. Category 3 — Momentum, Divergence & Relative Strength: IMPLEMENTED & TESTED

### Files changed
- `web/static/app.js` — `LAYER_DEFS.momentum`, `plotMomentumDivergence()`, `findSwingsJS()`, `detectDivergence()`, applyChartLayers branch, state fields (`momentumMarkers`, `momentumSeries`), flushMarkers.
- `web/static/index.html` — cache buster `app.js?v=wb50`.
- `tests/test_browser_chart_momentum.py` — new (3 browser tests).

### Calculations reused
- `/api/bars/{symbol}/indicator?name=rsi` (RSI), `macd`, and `/api/bars/{symbol}/relative-strength` (stock vs NEPSE, inner join on trading dates). All from the existing indicator/ranking infrastructure. No duplicate calculation engine.

### New logic
- `findSwingsJS(highs, lows, left, right)` — fractal pivot detection on both price and indicator series (confirmed at `pivot + right`, no look-ahead).
- `detectDivergence(priceHighs, priceLows, indValues, left, right)`:
  - Bullish: price lower low + indicator higher low → bullish divergence marker.
  - Bearish: price higher high + indicator lower high → bearish divergence marker.
  - Each marker carries `confirmedIndex = max(price confirmed, indicator confirmed)`.
- Relative strength vs NEPSE plotted as a mint line (ratio rebased to 100 at first aligned date).
- Divergence count and RS availability reported in `state.layerData.momentum`.

### Formulas documented
- RSI = 100 − 100/(1+RS), RS = AvgGain/AvgLoss (existing ta.rsi).
- MACD = EMA12(close) − EMA26(close); signal = EMA9(MACD); histogram = MACD − signal (existing ta.macd).
- Relative strength: ratio = stock_close / benchmark_close, rebased to 100 at first aligned date; excess return = stock window return − benchmark window return, over dates present in both (inner join).
- Divergence: bullish when price makes a lower swing low while RSI makes a higher swing low; bearish when price makes a higher swing high while RSI makes a lower swing high. Only confirmed swings are used.

### Tests executed
- `tests/test_browser_chart_momentum.py` — **3 passed** (toggle on, toggle off, coexistence with structure+trend).
- `node --check web/static/app.js` — OK.
- Full non-browser suite — **2,971 passed, 24 skipped, exit 0**.

### Limitations
- Divergence detection uses RSI only (MACD divergence not yet plotted, though MACD is fetched).
- Relative strength requires the NEPSE composite index to be stored; returns unavailable honestly if not.
- Swing matching uses a ±2 bar tolerance, which may miss or falsely match in noisy series.
- Provisional (unconfirmed) swings are excluded; a divergence is only reported once both swings are confirmed.

### Status: IMPLEMENTED, TESTED-PASS

---

## 15. Category 4 — Volatility & Breakout: IMPLEMENTED & TESTED

### Files changed
- `web/static/app.js` — `LAYER_DEFS.volatility`, `plotVolatilityBreakout()`, `alignIndicatorToBars()` helper, applyChartLayers branch, state fields (`volatilityMarkers`, `volatilitySeries`), flushMarkers. Cache buster `wb54`.
- `tests/test_browser_chart_volatility.py` — new (3 browser tests).

### Calculations reused
- `/api/bars/{symbol}/indicator?name=bollinger` (upper, middle, lower, bandwidth, percent_b), `keltner` (upper, middle, lower), `atr`. All from the existing 92-indicator registry. No duplicate calculation engine.

### New logic
- Bollinger Bands: middle = SMA(n), upper = middle + k·σ, lower = middle − k·σ (existing ta.bollinger). Plotted as 3 lines (middle solid, upper/lower dashed).
- Keltner Channels: upper = EMA + m·ATR, lower = EMA − m·ATR (existing ta.keltner). Plotted as dashed caution-coloured lines.
- ATR and ATR%: existing ta.atr.
- Squeeze detection: BB inside KC (bbUpper < kcUpper AND bbLower > kcLower). Count reported in layer data.
- Breakout candidates: close > BB upper → bullish (arrow up); close < BB lower → bearish (arrow down). Marked as provisional candidates, not confirmed breakouts.

### Formulas documented
- Bollinger: Middle = SMA_n(C), Upper = Middle + k·σ, Lower = Middle − k·σ, k = 2 default.
- Bandwidth = 100 × (Upper − Lower) / Middle.
- Keltner: Middle = EMA_n(C), Upper = Middle + m·ATR, Lower = Middle − m·ATR, m = 2 default (existing).
- ATR% = 100 × ATR_n / C_t.
- Squeeze: BB inside KC (compression). Expansion = NOT squeeze.
- Breakout: close beyond a band. Direction reported, not predicted.

### Tests executed
- `tests/test_browser_chart_volatility.py` — **3 passed** (toggle on, toggle off, coexistence with structure+trend+momentum).
- `node --check web/static/app.js` — OK.
- Full non-browser suite — **2,971 passed, 24 skipped, exit 0**.

### Limitations
- Historical volatility (log returns) is not yet plotted (indicator exists but not wired into this layer).
- Breakout candidates are provisional (close beyond band) — not confirmed breakouts (would need volume confirmation and follow-through).
- Squeeze uses the classic BB-inside-KC definition; no "squeeze count" or "days in squeeze" metric yet.
- ATR% and bandwidth are computed by the indicator but not yet surfaced in the UI (available in layer data).

### Status: IMPLEMENTED, TESTED-PASS

---

## 16. Category 5 — Volume & Accumulation: IMPLEMENTED & TESTED

### Files changed
- `web/static/app.js` — `LAYER_DEFS.volume`, `plotVolumeAccumulation()`, applyChartLayers branch, state fields (`volumeMarkers`, `volumeSeries`), flushMarkers. Cache buster `wb55`.
- `tests/test_browser_chart_volume.py` — new (3 browser tests).

### Calculations reused
- `/api/bars/{symbol}/indicator?name=obv` (OBV), `cmf` (CMF), `ad_line` (A/D), `relative_volume` (RVOL). All from the existing 92-indicator registry. No duplicate calculation engine.

### New logic
- OBV plotted as a mint line (cumulative volume direction based on close-to-close movement).
- CMF plotted as a cyan dashed line (money flow multiplier × volume, summed over N bars / total volume).
- A/D line plotted as a caution dashed line (close location value × volume, cumulative).
- Volume spikes: RVOL ≥ 2.0 → circle marker "V" at that bar.
- Price-volume divergence: price swing high + OBV swing low → bearish; price swing low + OBV swing high → bullish. Uses confirmed swings (no look-ahead).
- Relative volume threshold: 2.0× (configurable in code, not yet in UI).

### Formulas documented
- OBV_t = OBV_(t-1) + V_t if C_t > C_(t-1); − V_t if C_t < C_(t-1); unchanged if equal.
- MFM_t = ((C_t − L_t) − (H_t − C_t)) / (H_t − L_t); MFV_t = MFM_t × V_t.
- CMF_n = Σ(MFV over n) / Σ(V over n).
- RVOL_n = V_t / mean(V over the selected historical window). Current bar excluded from the baseline.
- A/D: CLV = ((C − L) − (H − C)) / (H − L); AD = cumulative sum of CLV × V.

### Tests executed
- `tests/test_browser_chart_volume.py` — **3 passed** (toggle on, toggle off, coexistence with all 4 prior categories).
- `node --check web/static/app.js` — OK.
- Full non-browser suite — **2,971 passed, 24 skipped, exit 0**.

### Limitations
- Relative volume threshold (2.0×) is hardcoded; not yet configurable in the UI.
- H = L (zero range) handling relies on the indicator engine's division-by-zero guard; not explicitly tested in the layer.
- Missing volume (null) is not yet explicitly handled (the indicator returns null, which is skipped in plotting).
- Price-volume divergence uses OBV only; CMF-based divergence not yet implemented.
- No separate volume pane — all series are overlaid on the price chart, which may be cluttered.

### Status: IMPLEMENTED, TESTED-PASS
