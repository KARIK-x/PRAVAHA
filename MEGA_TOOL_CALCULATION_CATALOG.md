# MEGA TOOL — CALCULATION CATALOG
Audit date: 2026-10-14 (append 2026-10-17, session 24) | Source: verified source inspection

## SESSION 24 ADDITIONS (2026-10-17)

Multi-timeframe relative strength (megatool/rs_timeframes.py: timeframe_rows)
- Formula: identical single-window arithmetic reused per lookback L on the
  SAME aligned series: stock=(c[t]/c[t-L]−1)·100, bench ditto, excess=stock−bench
  (a difference of percentage returns — never annualised, never labelled alpha)
- Inputs: aligned stock/bench frame (inner join); lookback list 2..2000, ≤6 unique
- Edge: shorter history → available:false with the exact reason (never shortened silently); nonpositive/nonfinite close → unavailable
- Tests: tests/test_rs_timeframes.py (20) — exact percentages, sign cases, tie/dedup, 400-rejection matrix, endpoint contract + old-shape backward compat
- API: /api/bars/{symbol}/relative-strength?lookbacks=20,60,120,250
- Status: IMPLEMENTED + TESTED-PASS; UI table + configurable lookback set in index.html (browser-verified, NIMB 4.48/3.07/2.49/0.03 pp matched API exactly)

Volume profile (megatool/ta/profile.py: volume_profile)
- Formula: bins over [min low, max high]; each bar's volume spread across touched bins proportional to overlap length (half-open convention; top bin closed right); POC = max bin (tie → lower price); value area = classic two-sided expansion from POC until ≥70%; HVN/LVN = strict local peak/trough (plateaus skipped)
- Edge: single-price window → honest 1-bin flat profile; unusable rows skipped & counted, never estimated; bin_count==1 branch returns price-exact landmarks
- Tests: tests/test_volume_profile.py (11) — hand-set exact POC/VA arithmetic; a pointer-vs-edge-label mixing bug in the value-area expansion was caught by these tests and fixed before shipping
- API: /api/bars/{symbol}/volume-profile (bins 10..200)
- Status: IMPLEMENTED + TESTED-PASS; chart Analysis layer with POC/VAH/VAL lines browser-verified on NIMB ("3 found", 192/210/189)

Trailing stops (megatool/ta/trailing.py: trailing_stop)
- Formula: chandelier = HH(N) − k·ATR(N) (Wilder); swing = lowest low of last M bars; pct = peak close × (1 − pct/100); shared ratchet stop[t]=max(stop[t−1], rule) — up only
- Causality: stop[t] uses bars ≤ t; exit needs a LATER bar's low ≤ stop; fill = stop level (no open price claimed); rule values ≥ current close are recorded but never applied; malformed bar ends the chain, never bridged
- Tests: tests/test_trailing_stop.py (12) — hand-recomputed Wilder ATR values, monotone ratchet, warmup Nones, gap-chain integrity
- API: /api/bars/{symbol}/trailing-stop; advanced-analysis card verified in browser on NIMB (837 bars, stop 259.70, exit bar 36 @ 183.04)
- Status: IMPLEMENTED + TESTED-PASS. NOT an exit recommendation or execution.

Gaps & false breakouts (megatool/ta/gaps.py)
- Gaps: fact = low[t] > high[t−1] (up) or high[t] < low[t−1] (down); class rule over ATR(14) scale + trend context → common/runaway/breakaway/exhaustion with stated basis; closed_within_bars computed post hoc and flagged as such; data holes never fabricate gaps
- False breakouts: breakout = close beyond prior N-bar extreme by ≥ min_frac; false when a later close returns across the level within confirm_bars; otherwise true, or unconfirmed at window end; run-beyond-level measured; no S/R clustering claimed (that is ta/levels)
- Tests: tests/test_gaps_breakouts.py (13) + endpoint contracts
- API: /api/bars/{symbol}/gaps, /api/bars/{symbol}/breakouts — live-verified on NIMB (4 gaps, 4 breakouts)
- Status: IMPLEMENTED + TESTED-PASS. Class labels describe shape by rule; not predictions.

## CALCULATIONS DOCUMENTED (FROM ACTUAL SOURCE)

RSI (megatool/ta/momentum.py: rsi function)
- Formula: Wilder smoothing — average gain / average loss over period; RSI = 100 - 100/(1+RS)
- Inputs: close series; period=14 default
- Outputs: IndicatorResult with values {"rsi": np.ndarray}
- Edge: n < period+1 -> insufficient_data=True; flat series (avg_gain==0 and avg_loss==0) -> NaN (B-23 fix: avg_gain>0 required for 100); strictly rising -> 100; strictly falling -> 0
- Tests: test_indicators (26 regression for B-23); reference _naive_wilder_rsi verified
- API: /api/indicators?name=rsi — verified
- Status: IMPLEMENTED + TESTED-PASS

MFI (megatool/ta/volume.py: mfi function)
- Formula: MFR = positive_flow / negative_flow; MFI = 100 - 100/(1+MFR)
- Inputs: typical_price * volume; period=14
- Edge: both flow sums = 0 (constant price + zero vol) -> NaN (B-24 fix: p > 0 else np.nan); rising -> 100; falling -> 0
- Tests: 17 regression (test_indicators + test_summary)
- Status: IMPLEMENTED + TESTED-PASS

MACD (ta/momentum or ta/summary)
- Formula: MACD = EMA(12) - EMA(26); Signal = EMA(9); Histogram = MACD - Signal
- Inputs: close series
- Status: IMPLEMENTED (existing correct)

SMA/EMA (ta/summary or ta/indicator module)
- Formula: SMA = mean over period; EMA = alpha * today + (1-alpha) * prev (alpha=2/(period+1))
- Status: IMPLEMENTED + TESTED-PASS

Fibonacci (megatool/ta/fibonacci.py)
- Formula: range = end - start (signed); retracement = end - range * r; extension = end + range * r
- Inputs: confirmed swing anchors (start/end prices)
- Outputs: levels with formula; 50% labeled family="convention"
- Edge: equal anchors -> raise; direction from range sign
- Tests: 38 unit + 8 API; live verified ADBL (61.8% = 311.7666; 161.8% = 281.1334)
- Status: IMPLEMENTED + TESTED-PASS

S/R (megatool/ta/levels.py)
- Formula: sort by price; join when within tolerance of running center; center = running mean
- Inputs: swing points from swings.py
- Outputs: zones with price, center, width, tolerance, touches
- Status: IMPLEMENTED + TESTED-PASS (24+5)

Swing (megatool/ta/swings.py)
- Formula: fractal — strictly above left window, >= right; alternating HH/HL/LH/LL
- Inputs: OHLCV series; left/right windows
- Outputs: swings with confirmed_index >= index (look-ahead prevented)
- Status: IMPLEMENTED + TESTED-PASS (17+5)

ATR / Volatility (ta/ta module — existing)
- Formula: ATR = mean of true ranges; Historical vol = std(log returns)
- Status: IMPLEMENTED

Bollinger (ta/)
- Formula: SMA +/- 2 * stddev
- Status: IMPLEMENTED

Volume indicators (OBV, MFI, volume profile approximations)
- Status: PARTIAL (MFI complete; others basic)

Multi-timeframe aggregation (megatool/ta/multitimeframe.py)
- Weekly: groupby week; open=first, high=max, low=min, close=last, vol=sum
- Monthly: groupby month; same convention
- Status: IMPLEMENTED + TESTED-PASS

Backtest metrics (megatool/backtest.py)
- Returns: from next-bar-open fill; benchmark = buy-and-hold; max drawdown; Sharpe
- Fees: PLACEHOLDER (B-11 documented; not invented)
- Status: IMPLEMENTED (limitations documented)

Forecast metrics (megatool/forecast.py)
- MAE/RMSE vs naive baseline; plain-words verdict (NO DEMONSTRATED SKILL where true)
- Status: IMPLEMENTED + HONESTLY REPORTED

Not implemented or blocked:
- Elliott Wave full visualization (megatool/ta/elliott.py bounded only)
- Harmonic patterns (no file; needs XABCD ratios)
- Classical chart patterns (only candlestick)
- Sector-relative ranking (B-07: sector=NULL)
- Index-relative ranking (B-10: index unavailable)

---

## 2026-10-15 additions (Phase 2 run)

Chart patterns (megatool/ta/patterns.py) — see docs/PHASES_2_6_PROGRESS.md §4
- double/triple top & bottom, H&S + inverse, ascending/descending/symmetrical
  triangles, rising/falling wedges, bull/bear flags, channel breakout
- Inputs: high/low/close; Outputs: PatternMatch{pattern, direction, pivots,
  status, breakout/invalidation/target, quality, evidence}
- Edge: < min_bars -> available=false + reason; non-finite -> refused;
  unconfirmed trigger -> status "forming"
- Tests: tests/test_chart_patterns.py (14) + tests/test_patterns_stats_api.py
- API: GET /api/bars/{symbol}/patterns

Statistics (megatool/stats.py) — pure numpy/math, scipy NOT imported
- descriptive, return_statistics, pearson, spearman, ols, rolling_correlation,
  autocorrelation, variance_ratio, correlation_matrix
- Edge: undefined -> None (never NaN/invented); zero variance -> no Sharpe;
  exact Student-t p-values via the regularised incomplete beta
- Tests: tests/test_stats.py (18) + API tests
- API: GET /api/bars/{symbol}/statistics, GET /api/stats/correlation

New indicators (46 registered, was 28) — all covered by the dynamic
look-ahead / warm-up harness in tests/test_indicators.py:
- trend.py: vwma, dema, tema, kama, parabolic_sar
- momentum.py: stochastic_rsi, ppo, cmo, tsi
- volume.py: cmf, chaikin_oscillator, volume_roc
- ta/other.py (new): typical_price, median_price, weighted_close,
  standard_deviation, zscore, pivot_points
- Tests: independent literal references for every one (engine-free), plus
  structural tests (SAR stays below the low in a clean uptrend; pivots are
  computed from the previous bar).

**Defect found and fixed by the new independent references (B-45):**
`kama` volatility used `np.diff` over a `period`-bar window, which yields
`period - 1` changes and silently drops the most recent one, understating
volatility and therefore the efficiency ratio. Fixed to use a `period + 1` bar
window (the published `period` absolute changes). Other KAMA behaviour was
already correct; the fix is verified by a literal independent recomputation.
