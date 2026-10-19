# Indicator catalogue

Generated 2026-10-18 from the live registry (`megatool.ta.available()`), the same data `GET /api/indicators` serves to the chart drawer. **92 registered indicators** (27 trend, 25 momentum, 16 volatility, 14 volume, 10 other). Every row carries its own formula and citation in the registry; this table is the navigation index over them.

Most recent batch added 2026-10-18 (`megatool/ta/extra.py`, 11 indicators): `vortex`, `ma_cross`, `chande_kroll_stop`, `bollinger_width`, `percent_b`, `chaikin_volatility`, `relative_volatility_index`, `average_price`, `price_correlation`, `williams_fractal`, `zigzag`. Each has an independently written numeric reference test (see **Verification** below).

## Verification

Derived by scanning the test suite (`scripts/generate_indicator_info.py`, reproducible):

| Level | Count | Meaning |
|---|---|---|
| `reference` | **49** | Compared inside a test against an independently written formula (literal re-implementation, hand-computed value or published worked example). |
| `invariants` | **41** | Exercised only against structural guarantees (no look-ahead via full-vs-prefix equality, NaN warm-up, warm-up not over-declared, short-series safety). This is a floor, **not** numeric proof. |
| `sparse` | **2** | `williams_fractal`, `zigzag`. Their output is a pivot price on the bar the pivot belongs to: sparse by construction and (for `zigzag`) repainting. They are **deliberately excluded** from the two warm-up invariants, which assume a dense series, and are covered instead by dedicated property tests that assert the repainting rather than hide it. The excluded set is declared in `tests/test_indicators.py` as `SPARSE_PIVOT_INDICATORS`, so an exclusion can never be silent. |
| `none` | **0** | — |

No indicator is claimed to be "validated" beyond this. A `reference` test checks the arithmetic against the documented formula; it does not validate the indicator as a trading signal on NEPSE.

**Placement** is where the chart draws the indicator by default: `overlay` on the price chart, `pane` in its own synced panel below. The rule mirrors `indPlacement()` in `web/static/app.js` (category defaults + named exceptions; momentum/volume to panes; trend overlays except ADX/Aroon/linreg-slope/supertrend; volatility overlays only for pure upper+middle+lower band groups; Bollinger's ratio outputs keep it in a pane so they cannot wreck the price scale). The matrix was browser-verified 2026-10-18: 33 overlay / 59 pane.

## Registered indicators

| Indicator | Label | Category | Outputs | Placement | Default parameters | Source |
|---|---|---|---|---|---|---|
| `adx` | Average Directional Index | trend | adx, plus_di, minus_di | pane | {"period": 14} | J. Welles Wilder (1978). Trend-strength, not direction. |
| `alligator` | Williams Alligator | trend | jaw, teeth, lips | overlay | {"jaw_period": 13, "jaw_offset": 8, "teeth_period": 8, "teeth_offset": 5, "lips_period": 5, "lips_offset": 3} | Bill Williams, Trading Chaos (1995). |
| `alma` | Arnaud Legoux Moving Average | trend | alma | overlay | {"period": 9, "offset": 0.85, "sigma": 6.0} | Arnaud Legoux & Dimitrios Kouzis-Loukas, ALMA (2009). |
| `aroon` | Aroon | trend | aroon_up, aroon_down, aroon_osc | pane | {"period": 14} | Tushar Chande, 1995. |
| `chande_kroll_stop` | Chande Kroll Stop | trend | stop_long, stop_short, initial_long, initial_short | overlay | {"period": 10, "multiplier": 1.0, "atr_period": 10, "trail": 3.0} | Tushar Chande & Stanley Kroll (1995), 'The New Technical Trader'. |
| `dema` | Double Exponential Moving Average | trend | dema | overlay | {"period": 20} | Patrick Mulloy, 1994. |
| `ema` | Exponential Moving Average | trend | ema | overlay | {"period": 20} | Seeded with SMA of the first `period` values. |
| `envelopes` | Moving Average Envelopes | trend | upper, middle, lower | overlay | {"period": 20, "percent": 1.0} | Standard MA-envelope construction (percent bands around an SMA). |
| `gmma` | Guppy Multiple Moving Average | trend | sma_3, sma_5, sma_8, sma_10, sma_12, sma_15, sma_30, sma_35, sma_40, sma_45, sma_50, sma_60 | overlay | {} | Daryl Guppy, 'Trading Tactics' (1998). |
| `hma` | Hull Moving Average | trend | hma | overlay | {"period": 16} | Alan Hull, 2005. Reduces lag while keeping smoothness. |
| `ichimoku` | Ichimoku Kinko Hyo | trend | tenkan, kijun, senkou_a, senkou_b | overlay | {"tenkan": 9, "kijun": 26, "senkou_b": 52} | Goichi Hosoda, 1930s. |
| `kama` | Kaufman Adaptive Moving Average | trend | kama | overlay | {"period": 10, "fast": 2, "slow": 30} | Perry Kaufman, Trading Systems and Methods (1995/2013). |
| `linreg_slope` | Linear Regression Slope | trend | slope | pane | {"period": 20} | Standard OLS; slope of the rolling linear-regression fit. |
| `lsma` | Least Squares Moving Average | trend | lsma | overlay | {"period": 25} | Oldest recorded use: R. B. Barnaby / 'time series forecast' (1936); popularised as LSMA on TradingView. |
| `ma_cross` | Moving Average Cross (fast vs slow SMA) | trend | fast, slow, diff, state | overlay | {"fast": 20, "slow": 50} | Classic dual-moving-average crossover (Gardner; widely published). |
| `mcginley_dynamic` | McGinley Dynamic | trend | md | overlay | {"period": 14} | John R. McGinley, 'The McGinley Dynamic' (1990s). |
| `parabolic_sar` | Parabolic Stop and Reverse | trend | sar | overlay | {"step": 0.02, "maximum": 0.2} | J. Welles Wilder, New Concepts in Technical Trading Systems (1978). |
| `sma` | Simple Moving Average | trend | sma | overlay | {"period": 20} | Arithmetic mean of the last `period` closes. |
| `smma` | Smoothed Moving Average (Wilder) | trend | smma | overlay | {"period": 20} | J. Welles Wilder, New Concepts in Technical Trading Systems (1978). |
| `supertrend` | Supertrend | trend | supertrend, direction | pane | {"period": 10, "multiplier": 3.0} | Commonly used in Indian/South-Asian technical analysis. |
| `t3` | T3 Moving Average | trend | t3 | overlay | {"period": 5, "volume_factor": 0.7} | Tim Tillson, 'Smoothing Techniques for More Accurate Signals', TASC 1998. |
| `tema` | Triple Exponential Moving Average | trend | tema | overlay | {"period": 20} | Patrick Mulloy, 1994. |
| `vidya` | Variable Index Dynamic Average | trend | vidya | overlay | {"period": 14, "short_period": 2} | Tushar Chande, 'Chande's Variable Index Dynamic Average', TASC 1992. |
| `vortex` | Vortex Indicator | trend | vi_plus, vi_minus | pane | {"period": 14} | Etienne Botes & Douglas Siepman, 2009 (published in Technical Analysis of Stocks & Commodities, 2010). |
| `vwma` | Volume-Weighted Moving Average | trend | vwma | overlay | {"period": 20} | A simple average whose observations are each weighted by that bar's volume. |
| `wma` | Weighted Moving Average | trend | wma | overlay | {"period": 20} | Linear weights, most recent observation weighted highest. |
| `zlema` | Zero-Lag Exponential Moving Average | trend | zlema | overlay | {"period": 20} | Ehlers-style lag compensation; popularised by John Ehlers. |
| `accelerator_oscillator` | Accelerator Oscillator | momentum | ac | pane | {"fast": 5, "slow": 34, "smooth": 5} | Bill Williams, New Trading Dimensions (1998). |
| `awesome_oscillator` | Awesome Oscillator | momentum | ao | pane | {"fast": 5, "slow": 34} | Bill Williams, New Trading Dimensions (1998). |
| `balance_of_power` | Balance of Power | momentum | bop | pane | {} | Igor Livshin, 'Balance of Power' (2001). |
| `cci` | Commodity Channel Index | momentum | cci | pane | {"period": 20} | Donald Lambert, 1980. |
| `cmo` | Chande Momentum Oscillator | momentum | cmo | pane | {"period": 14} | Tushar Chande, The New Technical Trader (1994). |
| `connors_rsi` | Connors RSI | momentum | crsi | pane | {"rsi_period": 3, "streak_period": 2, "rank_period": 100} | Larry Connors & Cesar Alvarez, 'An Introduction to ConnorsRSI' (2012). |
| `coppock_curve` | Coppock Curve | momentum | coppock | pane | {"long": 14, "short": 11, "wma_period": 10} | Edwin Sedgwick Coppock, Barron's (1962); WMA smoothing added by later implementations. |
| `dpo` | Detrended Price Oscillator | momentum | dpo | pane | {"period": 21} | Walt Bressert / 'Cycles' literature; popularised by Investor's Business Daily. |
| `fisher_transform` | Fisher Transform | momentum | fisher, trigger | pane | {"period": 9} | John Ehlers, 'Using the Fisher Transform', TASC 2002. |
| `force_index` | Elder Force Index | momentum | efi, efi_ema | pane | {"period": 13} | Alexander Elder, Trading for a Living (1993). |
| `kst` | Know Sure Thing | momentum | kst, signal | pane | {"signal": 9} | Martin Pring, 'Summed Rate of Change' — KST (1992). |
| `macd` | Moving Average Convergence Divergence | momentum | macd, signal, histogram | pane | {"fast": 12, "slow": 26, "signal": 9} | Gerald Appel, 1979. |
| `momentum` | Momentum | momentum | momentum | pane | {"period": 10} | Standard momentum measure. |
| `ppo` | Percentage Price Oscillator | momentum | ppo, signal, histogram | pane | {"fast": 12, "slow": 26, "signal": 9} | Gerald Appel: the MACD expressed as a percentage of the slow EMA. |
| `price_oscillator` | Price Oscillator | momentum | price_osc | pane | {"fast": 10, "slow": 21} | Classic percentage price oscillator with SIMPLE moving averages. |
| `roc` | Rate of Change | momentum | roc | pane | {"period": 12} | Standard momentum measure. |
| `rsi` | Relative Strength Index | momentum | rsi | pane | {"period": 14} | J. Welles Wilder, New Concepts in Technical Trading Systems (1978). |
| `rvi` | Relative Vigor Index | momentum | rvi, signal | pane | {"period": 10} | John Ehlers, 'The Relative Vigor Index', TASC 2002. |
| `smi` | Stochastic Momentum Index | momentum | smi, signal | pane | {"period": 14, "smooth1": 3, "smooth2": 3, "signal": 3} | William Blau, Momentum, Direction and Divergence (1993). |
| `stochastic` | Stochastic Oscillator | momentum | k, d | pane | {"k_period": 14, "d_period": 3, "smooth": 3} | George Lane, 1950s. |
| `stochastic_rsi` | Stochastic RSI | momentum | stoch_rsi | pane | {"rsi_period": 14, "stoch_period": 14} | Tushar Chande & Stanley Kroll, The New Technical Trader (1994). |
| `trix` | TRIX | momentum | trix, signal | pane | {"period": 15, "signal": 9} | Jack Hutson, 1980s. |
| `tsi` | True Strength Index | momentum | tsi | pane | {"long": 25, "short": 13} | William Blau, Momentum, Direction and Divergence (1995). |
| `ultimate_oscillator` | Ultimate Oscillator | momentum | uo | pane | {"short": 7, "medium": 14, "long": 28} | Larry Williams, 'Ultimate Oscillator', TASC 1985. |
| `williams_r` | Williams %R | momentum | williams_r | pane | {"period": 14} | Larry Williams, 1973. |
| `atr` | Average True Range | volatility | atr | pane | {"period": 14} | J. Welles Wilder, New Concepts in Technical Trading Systems (1978). |
| `bollinger` | Bollinger Bands | volatility | upper, middle, lower, bandwidth, percent_b | pane | {"period": 20, "std_dev": 2.0} | John Bollinger, 1980s. |
| `bollinger_width` | Bollinger Band Width (percent) | volatility | width_pct | pane | {"period": 20, "std_dev": 2.0} | John Bollinger, 1980s (band-width presentation). |
| `chaikin_volatility` | Chaikin Volatility | volatility | chaikin_vol | pane | {"ema_period": 10, "roc_period": 10} | Marc Chaikin (published in Technical Analysis of Stocks & Commodities). |
| `choppiness` | Choppiness Index | volatility | chop | pane | {"period": 14} | E. W. Dreiss, 'The Choppiness Index', TASC 1993. |
| `donchian` | Donchian Channel | volatility | upper, middle, lower | overlay | {"period": 20} | Richard Donchian; popularised by the Turtle Traders. |
| `garman_klass` | Garman-Klass Volatility | volatility | gk_vol | pane | {"period": 20, "annualize": 252} | Garman & Klass, 'On the Estimation of Security Price Volatilities from Historical Data', Journal of Business (1980). |
| `historical_volatility` | Historical Volatility (annualised) | volatility | hv | pane | {"period": 20, "trading_days": 250} | Standard close-to-close realised volatility. |
| `keltner` | Keltner Channel | volatility | upper, middle, lower | overlay | {"period": 20, "atr_period": 10, "multiplier": 2.0} | Chester Keltner, 1960; ATR variant popularised by Linda Raschke. |
| `mass_index` | Mass Index | volatility | mass | pane | {"period": 9, "sum_period": 25} | Donald Dorsey, 'The Mass Index', TASC 1992. |
| `percent_b` | Bollinger %B | volatility | percent_b | pane | {"period": 20, "std_dev": 2.0} | John Bollinger, 1980s. |
| `relative_volatility_index` | Relative Volatility Index | volatility | rvi, signal | pane | {"period": 10, "signal": 14} | Donald Dorsey, 1993 (Technical Analysis of Stocks & Commodities). |
| `standard_error` | Standard Error (of regression) | volatility | se | pane | {"period": 14} | Standard OLS residual standard error. |
| `standard_error_bands` | Standard Error Bands | volatility | upper, middle, lower | overlay | {"period": 14, "mult": 2.0} | Jon Anderson, 'Standard Error Bands', TASC 1996. |
| `true_range` | True Range | volatility | true_range | pane | {} | J. Welles Wilder (1978). |
| `volatility_zero_trend` | Volatility (Zero Trend) | volatility | vzt | pane | {"period": 20} | 'Zero-trend' volatility: mean absolute close-to-close change without assuming any drift. |
| `ad_line` | Accumulation / Distribution Line | volume | ad, clv | pane | {} | Chaikin, 1960s. |
| `chaikin_oscillator` | Chaikin Oscillator | volume | chaikin_oscillator | pane | {"fast": 3, "slow": 10} | Marc Chaikin: the MACD of the Accumulation/Distribution line. |
| `cmf` | Chaikin Money Flow | volume | cmf | pane | {"period": 20} | Marc Chaikin. |
| `ease_of_movement` | Ease of Movement | volume | emv | pane | {"period": 14} | Richard Arms, 'Volume Adjusted Moving Averages' (1960s). |
| `klinger` | Klinger Volume Oscillator | volume | kvo, signal | pane | {"short": 34, "long": 55, "signal": 13} | Stephen Klinger, 'Volume Oscillator Confirms Price Movements', TASC 1997. |
| `mfi` | Money Flow Index | volume | mfi | pane | {"period": 14} | Quinn and Weigand, 1990s. |
| `net_volume` | Net Volume | volume | net_volume | pane | {} | Per-bar signed volume (up/down volume decomposition). |
| `obv` | On-Balance Volume | volume | obv | pane | {} | Joseph Granville, 1963. |
| `pvt` | Price Volume Trend | volume | pvt | pane | {} | Classic Price Volume Trend (PVT), described in most volume-analysis texts. |
| `relative_volume` | Relative Volume | volume | rvol | pane | {"baseline": 20} | volume[t] / mean(volume over trailing baseline window) |
| `volume_oscillator` | Volume Oscillator | volume | volume_osc | pane | {"short": 14, "long": 28} | Standard volume-oscillator construction (percentage difference of two volume EMAs). |
| `volume_roc` | Volume Rate of Change | volume | volume_roc | pane | {"period": 14} | Percentage change in volume against `period` bars earlier. |
| `volume_sma` | Volume Moving Average | volume | volume_sma | pane | {"period": 20} | Simple moving average of volume. |
| `vwap_bands` | VWAP-style rolling band | volume | vwap | overlay | {"period": 20} | Rolling volume-weighted average price over `period` bars. |
| `average_price` | Average Price (OHLC/4) | other | average_price | overlay | {} | Common OHLC mean; used by several platforms as 'AvgPrice'. |
| `median_price` | Median Price | other | median_price | overlay | {} |  |
| `pivot_points` | Classic Floor Pivot Points | other | pivot, r1, r2, r3, s1, s2, s3 | overlay | {} | Traditional trading-floor pivot calculation. |
| `price_correlation` | Rolling Price Correlation (with time) | other | corr | pane | {"period": 20} | Pearson product-moment correlation, applied to (bar index, close). |
| `standard_deviation` | Rolling Standard Deviation | other | std | pane | {"period": 20, "ddof": 1} |  |
| `typical_price` | Typical Price | other | typical_price | overlay | {} |  |
| `weighted_close` | Weighted Close | other | weighted_close | overlay | {} |  |
| `williams_fractal` | Williams Fractal | other | fractal_up, fractal_down | overlay | {"window": 2} | Bill Williams, 'Trading Chaos' (1995). |
| `zigzag` | Zig Zag (percent threshold) | other | zigzag | overlay | {"threshold_pct": 5.0} | Common chartist construction (percent-reversal swing filter). |
| `zscore` | Z-Score | other | zscore | pane | {"period": 20, "ddof": 1} |  |

## Quick layers (chart toolbar checkboxes)

Preserved from the original chart toolbar; they are chart-level toggles, not instances of the registry: SMA(50), EMA(20), Bollinger(20, 2σ), volume bars, RSI(14) pane, MACD(12, 26, 9) pane, and swing markers (fractal pivots).

## Candlestick patterns (Part 14)

The detector in `megatool/ta/candles.py` implements **18 named patterns** (one-bar, two-bar and three-bar rules, all documented in that module and exposed via `GET /api/bars/{symbol}/candles`):

`doji`, `hammer`, `inverted_hammer`, `shooting_star`, `spinning_top`, `marubozu`, `bullish_engulfing`, `bearish_engulfing`, `harami`, `harami_cross`, `piercing_pattern`, `dark_cloud_cover`, `tweezer_bottom`, `tweezer_top`, `morning_star`, `evening_star`, `three_white_soldiers`, `three_black_crows`.

The Part 14 checklist in the owner's specification names 33 patterns; the remaining names are not present in the repository snapshot, so they are tracked as backlog in `REMAINING_BLOCKERS.md` rather than guessed here.

## Coverage boundaries (Parts 8–13)

The Part 8–13 script/indicator name lists (~350 names: built-ins, Nepsealpha customs, community scripts, breadth, additional scripts) live in the owner's specification text, which is not in this repository. This catalogue therefore records exactly what the registry implements — 92 registered indicators plus the 18 candle patterns above — and makes no coverage claim against a list it cannot read. Adding a checklist file with the exact names would allow a line-by-line cross-off; see `REMAINING_BLOCKERS.md` item 3.

## How to verify

```bash
# registry (all 92, with formulas and references):
curl -s http://127.0.0.1:10000/api/indicators | .venv/bin/python -m json.tool | head
# this catalogue is reproducible from the registry:
#   (regenerate with scripts/generate_indicator_reports.py; the placement mirror is asserted 33/59)
# formula guards + per-indicator reference tests:
.venv/bin/python -m pytest tests/test_indicators.py tests/test_indicators2.py -q
# regenerate the info metadata + verification map:
.venv/bin/python scripts/generate_indicator_info.py
```
