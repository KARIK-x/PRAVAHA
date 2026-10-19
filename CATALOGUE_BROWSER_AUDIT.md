# Catalogue Browser Audit

**Date:** 2026-10-19

**Method:** playwright-cli against the live dev server `127.0.0.1:10000`, KIMI → **Catalogues** tab. For **every** entry in every family the ⓘ information button was clicked and the detail panel was polled until it displayed that entry's own **stable id** *and* its **name**; the panel was additionally checked for a **Limitations** section and the row for a **Run** action. No family was sampled and no entry was skipped.


## Totals

| Family | Listed | Opened | Verified (id+name) | Limitations | Run action |
|---|---|---|---|---|---|
| Scanners | 124 | 124 | 124 | 124 | 124 |
| Algorithms | 77 | 77 | 77 | 77 | 77 |
| Fundamental tools | 32 | 32 | 32 | 32 | 32 |
| **Total** | **233** | **233** | **233** | **233** | **233** |

Reported counts from the UI (`#kimi-cat-count`): Scanners: 124 of 124 scanners match.; Algorithms: 77 of 77 algorithms match.; Fundamental tools: 32 of 32 fundamentals match..


## Entry-by-entry


### Scanners (124 entries)

| # | Stable id | Name | Panel opened (id+name) | Limitations | Run |
|---|---|---|---|---|---|
| 1 | `scan.oversold_rsi` | Oversold momentum | yes | yes | yes |
| 2 | `scan.volume_surge` | Unusual volume | yes | yes | yes |
| 3 | `scan.near_52w_high` | Within 5% of 250-bar high | yes | yes | yes |
| 4 | `scan.above_sma50` | Above 50-day SMA | yes | yes | yes |
| 5 | `scan.rsi_overbought` | Overbought momentum | yes | yes | yes |
| 6 | `scan.macd_bullish_cross` | MACD bullish cross | yes | yes | yes |
| 7 | `scan.macd_bearish_cross` | MACD bearish cross | yes | yes | yes |
| 8 | `scan.above_sma20` | Above 20-day SMA | yes | yes | yes |
| 9 | `scan.above_sma200` | Above 200-day SMA | yes | yes | yes |
| 10 | `scan.sma5_above_sma20` | SMA5 above SMA20 | yes | yes | yes |
| 11 | `scan.bollinger_lower_band` | At the lower Bollinger Band | yes | yes | yes |
| 12 | `scan.bollinger_upper_band` | At the upper Bollinger Band | yes | yes | yes |
| 13 | `scan.bollinger_squeeze` | Bollinger squeeze | yes | yes | yes |
| 14 | `scan.stochastic_oversold` | Stochastic oversold | yes | yes | yes |
| 15 | `scan.stochastic_overbought` | Stochastic overbought | yes | yes | yes |
| 16 | `scan.mfi_oversold` | Money Flow oversold | yes | yes | yes |
| 17 | `scan.donchian_breakout_up` | Donchian channel breakout (up) | yes | yes | yes |
| 18 | `scan.breakout_with_volume` | Channel breakout with volume | yes | yes | yes |
| 19 | `scan.near_52w_low` | Within 5% of 250-bar low | yes | yes | yes |
| 20 | `scan.momentum_20d` | 20-day momentum | yes | yes | yes |
| 21 | `scan.strong_trend_adx` | Strong trend (ADX) | yes | yes | yes |
| 22 | `scan.low_volatility` | Low volatility | yes | yes | yes |
| 23 | `scan.liquid_turnover` | Liquid by turnover | yes | yes | yes |
| 24 | `scan.volume_dryup` | Volume dry-up (quiet coiling) | yes | yes | yes |
| 25 | `scan.accumulation_20d` | 20-session accumulation | yes | yes | yes |
| 26 | `scan.distribution_20d` | 20-session distribution | yes | yes | yes |
| 27 | `scan.pocket_pivot` | Pocket pivot day | yes | yes | yes |
| 28 | `scan.obv_accumulation_20d` | OBV accumulation (20 sessions) | yes | yes | yes |
| 29 | `scan.volume_climax` | Volume climax (5 vs 20) | yes | yes | yes |
| 30 | `scan.biggest_volume_20d` | Biggest volume in 20 sessions, up day | yes | yes | yes |
| 31 | `scan.unusual_volume_50` | Unusual volume vs 50-bar baseline | yes | yes | yes |
| 32 | `scan.ret_1d_up` | Positive day | yes | yes | yes |
| 33 | `scan.ret_1d_down` | Negative day | yes | yes | yes |
| 34 | `scan.ret_5d_up` | Positive week | yes | yes | yes |
| 35 | `scan.ret_5d_down` | Negative week | yes | yes | yes |
| 36 | `scan.ret_20d_strong` | Strong month | yes | yes | yes |
| 37 | `scan.ret_20d_weak` | Weak month | yes | yes | yes |
| 38 | `scan.ret_60d_strong` | Strong quarter | yes | yes | yes |
| 39 | `scan.ret_60d_weak` | Weak quarter | yes | yes | yes |
| 40 | `scan.ret_120d_strong` | Strong half-year | yes | yes | yes |
| 41 | `scan.ret_120d_weak` | Weak half-year | yes | yes | yes |
| 42 | `scan.flat_week` | Flat week | yes | yes | yes |
| 43 | `scan.long_history` | Long trading history | yes | yes | yes |
| 44 | `scan.new_listing` | Recently listed | yes | yes | yes |
| 45 | `scan.low_price` | Low nominal price | yes | yes | yes |
| 46 | `scan.high_price` | High nominal price | yes | yes | yes |
| 47 | `scan.near_52w_high_strict` | Within 1% of 250-bar high | yes | yes | yes |
| 48 | `scan.near_52w_low_10` | Within 10% of 250-bar low | yes | yes | yes |
| 49 | `scan.below_sma20` | Below 20-day SMA | yes | yes | yes |
| 50 | `scan.below_sma50` | Below 50-day SMA | yes | yes | yes |
| 51 | `scan.below_sma200` | Below 200-day SMA | yes | yes | yes |
| 52 | `scan.far_above_sma50` | Far above 50-day SMA | yes | yes | yes |
| 53 | `scan.far_below_sma50` | Far below 50-day SMA | yes | yes | yes |
| 54 | `scan.sma50_above_sma200` | 50-day above 200-day | yes | yes | yes |
| 55 | `scan.sma20_below_sma50` | 20-day below 50-day | yes | yes | yes |
| 56 | `scan.adx_very_strong` | Very strong trend | yes | yes | yes |
| 57 | `scan.adx_weak` | Weak / no trend | yes | yes | yes |
| 58 | `scan.adx_mid` | Moderate trend | yes | yes | yes |
| 59 | `scan.rsi_mid_bull` | RSI bullish zone | yes | yes | yes |
| 60 | `scan.rsi_neutral` | RSI neutral | yes | yes | yes |
| 61 | `scan.rsi_extreme_oversold` | RSI deeply oversold | yes | yes | yes |
| 62 | `scan.macd_hist_positive` | MACD histogram positive | yes | yes | yes |
| 63 | `scan.macd_hist_negative` | MACD histogram negative | yes | yes | yes |
| 64 | `scan.macd_above_zero` | MACD above zero | yes | yes | yes |
| 65 | `scan.macd_below_zero` | MACD below zero | yes | yes | yes |
| 66 | `scan.stoch_mid` | Stochastic centred | yes | yes | yes |
| 67 | `scan.mfi_strong` | Money-flow strong | yes | yes | yes |
| 68 | `scan.mfi_weak` | Money-flow weak | yes | yes | yes |
| 69 | `scan.roc_positive` | Positive 20-day ROC | yes | yes | yes |
| 70 | `scan.atr_high` | High ATR | yes | yes | yes |
| 71 | `scan.atr_low` | Low ATR | yes | yes | yes |
| 72 | `scan.hv_high` | High historical volatility | yes | yes | yes |
| 73 | `scan.hv_low` | Low historical volatility | yes | yes | yes |
| 74 | `scan.bb_expansion` | Bollinger expansion | yes | yes | yes |
| 75 | `scan.bb_squeeze_tight` | Tight Bollinger squeeze | yes | yes | yes |
| 76 | `scan.bb_near_upper` | At upper Bollinger band | yes | yes | yes |
| 77 | `scan.bb_near_lower` | At lower Bollinger band | yes | yes | yes |
| 78 | `scan.range_expansion` | Range expansion | yes | yes | yes |
| 79 | `scan.range_contraction` | Range contraction | yes | yes | yes |
| 80 | `scan.turnover_high` | High turnover (liquid) | yes | yes | yes |
| 81 | `scan.turnover_surge` | Turnover surge | yes | yes | yes |
| 82 | `scan.turnover_dryup` | Turnover dry-up | yes | yes | yes |
| 83 | `scan.rvol_high` | Relative volume high | yes | yes | yes |
| 84 | `scan.rvol_low` | Relative volume low | yes | yes | yes |
| 85 | `scan.vol_ratio50_high` | Volume above 50-day base | yes | yes | yes |
| 86 | `scan.vol_ratio50_low` | Volume below 50-day base | yes | yes | yes |
| 87 | `scan.updown_volume_bull` | Up-volume dominant | yes | yes | yes |
| 88 | `scan.updown_volume_bear` | Down-volume dominant | yes | yes | yes |
| 89 | `scan.obv_strong_distribution` | OBV distribution | yes | yes | yes |
| 90 | `scan.vol_biggest_20d` | Biggest volume of 20 sessions | yes | yes | yes |
| 91 | `scan.vol_climax_high` | Volume climax | yes | yes | yes |
| 92 | `scan.donchian_top` | Near Donchian top | yes | yes | yes |
| 93 | `scan.donchian_bottom` | Near Donchian bottom | yes | yes | yes |
| 94 | `scan.donchian_mid` | Mid-channel | yes | yes | yes |
| 95 | `scan.breakout_fresh` | Fresh channel breakout | yes | yes | yes |
| 96 | `scan.breakdown_fresh` | Fresh channel breakdown | yes | yes | yes |
| 97 | `scan.breakout_volume_strong` | Breakout with strong volume | yes | yes | yes |
| 98 | `scan.high_vol_breakout` | High-ATR breakout | yes | yes | yes |
| 99 | `scan.near_high_with_volume` | Near high on volume | yes | yes | yes |
| 100 | `scan.rs_strong` | Beating the index by 10% | yes | yes | yes |
| 101 | `scan.rs_weak` | Lagging the index by 10% | yes | yes | yes |
| 102 | `scan.rs_positive` | Outperforming the index | yes | yes | yes |
| 103 | `scan.rs_negative` | Underperforming the index | yes | yes | yes |
| 104 | `scan.rs_strong_short` | Beating the index by 5% (20d) | yes | yes | yes |
| 105 | `scan.mr_rsi_mild` | Mildly oversold (RSI<40) | yes | yes | yes |
| 106 | `scan.mr_near_lower_band` | Near lower band in uptrend | yes | yes | yes |
| 107 | `scan.mr_stoch_extreme` | Stochastic deeply oversold | yes | yes | yes |
| 108 | `scan.mr_atr_pullback` | Sharp single-day fall | yes | yes | yes |
| 109 | `scan.liq_very_illiquid` | Illiquid | yes | yes | yes |
| 110 | `scan.liq_active` | Active trading | yes | yes | yes |
| 111 | `scan.liq_quiet_liquid` | Quiet but liquid | yes | yes | yes |
| 112 | `scan.combo_momentum_volume` | Momentum + volume | yes | yes | yes |
| 113 | `scan.combo_oversold_volume` | Oversold + volume | yes | yes | yes |
| 114 | `scan.combo_trend_pullback` | Uptrend pullback | yes | yes | yes |
| 115 | `scan.combo_downtrend_bounce` | Downtrend bounce | yes | yes | yes |
| 116 | `scan.combo_squeeze_momentum` | Squeeze + momentum | yes | yes | yes |
| 117 | `scan.combo_trend_continuation` | Trend continuation | yes | yes | yes |
| 118 | `scan.combo_range_reversal` | Range overbought | yes | yes | yes |
| 119 | `scan.combo_liquid_momentum` | Liquid momentum | yes | yes | yes |
| 120 | `scan.combo_quiet_coil` | Quiet coil | yes | yes | yes |
| 121 | `scan.combo_golden_volume` | Golden regime + volume | yes | yes | yes |
| 122 | `scan.combo_value_trend` | Cheap and turning up | yes | yes | yes |
| 123 | `scan.combo_accumulation_trend` | Accumulation in uptrend | yes | yes | yes |
| 124 | `scan.combo_distribution_downtrend` | Distribution in downtrend | yes | yes | yes |

### Algorithms (77 entries)

| # | Stable id | Name | Panel opened (id+name) | Limitations | Run |
|---|---|---|---|---|---|
| 1 | `algo.sma_cross` | SMA crossover | yes | yes | yes |
| 2 | `algo.rsi_threshold` | RSI mean-reversion | yes | yes | yes |
| 3 | `algo.ma_slope_trend` | Long-trend filter | yes | yes | yes |
| 4 | `algo.always_in` | Buy and hold | yes | yes | yes |
| 5 | `algo.donchian_breakout` | Donchian breakout | yes | yes | yes |
| 6 | `algo.bollinger_revert` | Bollinger mean reversion | yes | yes | yes |
| 7 | `algo.macd_trend` | MACD trend | yes | yes | yes |
| 8 | `algo.momentum_90d` | N-day momentum | yes | yes | yes |
| 9 | `algo.rsi2_reversion` | RSI(2) dip reversion | yes | yes | yes |
| 10 | `algo.trend200_filter` | 200-day regime filter | yes | yes | yes |
| 11 | `algo.vol_regime` | Calm-volatility regime | yes | yes | yes |
| 12 | `algo.atr_channel` | ATR channel breakout | yes | yes | yes |
| 13 | `algo.ema_ribbon` | EMA ribbon stack | yes | yes | yes |
| 14 | `algo.rate_of_change` | Rate-of-change floor | yes | yes | yes |
| 15 | `algo.stochastic_revert` | Stochastic reversion | yes | yes | yes |
| 16 | `algo.cci_trend` | CCI trend | yes | yes | yes |
| 17 | `algo.accum_dist_trend` | Accumulation / distribution trend | yes | yes | yes |
| 18 | `algo.obv_trend` | On-balance-volume trend | yes | yes | yes |
| 19 | `algo.golden_cross` | Golden cross | yes | yes | yes |
| 20 | `algo.range_rider` | Range rider | yes | yes | yes |
| 21 | `algo.ema_cross` | EMA crossover | yes | yes | yes |
| 22 | `algo.triple_ma` | Triple moving-average stack | yes | yes | yes |
| 23 | `algo.price_above_rising_sma` | Price above rising SMA | yes | yes | yes |
| 24 | `algo.adx_di_trend` | ADX/+DI trend | yes | yes | yes |
| 25 | `algo.linreg_slope_trend` | Linear-regression slope | yes | yes | yes |
| 26 | `algo.turtle_55` | Turtle 55/20 | yes | yes | yes |
| 27 | `algo.channel_midpoint_trend` | Channel-midpoint trend | yes | yes | yes |
| 28 | `algo.supertrend` | Supertrend (ATR trailing) | yes | yes | yes |
| 29 | `algo.roc_momentum` | Rate-of-change (N-day) | yes | yes | yes |
| 30 | `algo.momentum_with_vol_filter` | Momentum + volatility filter | yes | yes | yes |
| 31 | `algo.momentum_12_1` | 12-1 momentum | yes | yes | yes |
| 32 | `algo.momentum_acceleration` | Momentum acceleration | yes | yes | yes |
| 33 | `algo.macd_zero_cross` | MACD above zero | yes | yes | yes |
| 34 | `algo.stochastic_momentum` | Stochastic momentum | yes | yes | yes |
| 35 | `algo.williams_momentum` | Williams %R momentum | yes | yes | yes |
| 36 | `algo.rsi_trend_filter` | RSI trend filter | yes | yes | yes |
| 37 | `algo.cmf_trend` | Chaikin money-flow trend | yes | yes | yes |
| 38 | `algo.zscore_revert` | Z-score reversion | yes | yes | yes |
| 39 | `algo.percent_b_revert` | Bollinger %B reversion | yes | yes | yes |
| 40 | `algo.distance_ma_revert` | Distance-from-MA reversion | yes | yes | yes |
| 41 | `algo.keltner_revert` | Keltner reversion | yes | yes | yes |
| 42 | `algo.rsi4_reversion` | RSI(4) reversion | yes | yes | yes |
| 43 | `algo.williams_revert` | Williams %R reversion | yes | yes | yes |
| 44 | `algo.cci_revert` | CCI reversion | yes | yes | yes |
| 45 | `algo.gap_reversion` | Gap-down reversion | yes | yes | yes |
| 46 | `algo.breakout_pullback` | Breakout + pullback | yes | yes | yes |
| 47 | `algo.nr7_breakout` | NR7 breakout | yes | yes | yes |
| 48 | `algo.inside_bar_breakout` | Inside-bar breakout | yes | yes | yes |
| 49 | `algo.high_52w_breakout` | 52-week-high breakout | yes | yes | yes |
| 50 | `algo.range_expansion_breakout` | Range-expansion breakout | yes | yes | yes |
| 51 | `algo.volatility_breakout` | Volatility breakout (ATR) | yes | yes | yes |
| 52 | `algo.volume_breakout` | Volume-confirmed breakout | yes | yes | yes |
| 53 | `algo.atr_trailing_stop_trend` | ATR trailing-stop trend | yes | yes | yes |
| 54 | `algo.drawdown_guard` | Drawdown guard | yes | yes | yes |
| 55 | `algo.volatility_target_trend` | Volatility-filtered trend | yes | yes | yes |
| 56 | `algo.trend_with_stop` | Trend with fixed stop | yes | yes | yes |
| 57 | `algo.obv_breakout` | OBV breakout | yes | yes | yes |
| 58 | `algo.pocket_pivot_volume` | Pocket-pivot volume rule | yes | yes | yes |
| 59 | `algo.technical_rating` | Technical rating (confluence score) | yes | yes | yes |
| 60 | `algo.mtf_confluence` | Multi-timeframe confluence | yes | yes | yes |
| 61 | `algo.rolling_beta` | Rolling beta vs index | yes | yes | yes |
| 62 | `algo.volatility_percentile` | Volatility percentile | yes | yes | yes |
| 63 | `algo.correlation_matrix` | Return correlation matrix | yes | yes | yes |
| 64 | `algo.efficient_frontier` | Efficient frontier (mean-variance) | yes | yes | yes |
| 65 | `algo.monte_carlo` | Monte Carlo (GBM / bootstrap) | yes | yes | yes |
| 66 | `algo.risk_of_ruin` | Risk of ruin / losing streak | yes | yes | yes |
| 67 | `algo.signal_outcomes` | Signal outcome study | yes | yes | yes |
| 68 | `algo.dcf_valuation` | Discounted cash-flow valuation | yes | yes | yes |
| 69 | `algo.reverse_dcf` | Reverse DCF (implied growth) | yes | yes | yes |
| 70 | `algo.hrp_portfolio` | Hierarchical risk parity (HRP) | yes | yes | yes |
| 71 | `algo.deflated_sharpe` | Deflated Sharpe ratio | yes | yes | yes |
| 72 | `algo.stress_test` | Market-shock stress test | yes | yes | yes |
| 73 | `algo.event_study` | Event study (abnormal returns) | yes | yes | yes |
| 74 | `algo.liquidity_drought` | Liquidity drought & unusual activity | yes | yes | yes |
| 75 | `algo.fundamental_forensics` | Financial statement forensics | yes | yes | yes |
| 76 | `algo.factor_snapshot` | Cross-sectional factor snapshot | yes | yes | yes |
| 77 | `algo.coverage_explorer` | Data coverage & feasibility explorer | yes | yes | yes |

### Fundamental tools (32 entries)

| # | Stable id | Name | Panel opened (id+name) | Limitations | Run |
|---|---|---|---|---|---|
| 1 | `fund.pe_ratio` | Price / earnings (P/E) | yes | yes | yes |
| 2 | `fund.earnings_yield` | Earnings yield | yes | yes | yes |
| 3 | `fund.pb_ratio` | Price / book (P/B) | yes | yes | yes |
| 4 | `fund.book_to_price` | Book-to-price | yes | yes | yes |
| 5 | `fund.net_worth_yield` | Net-worth yield | yes | yes | yes |
| 6 | `fund.peg_proxy` | PEG proxy | yes | yes | yes |
| 7 | `fund.pe_vs_universe` | P/E vs universe median | yes | yes | yes |
| 8 | `fund.pb_vs_universe` | P/B vs universe median | yes | yes | yes |
| 9 | `fund.historical_pe_percentile` | Historical P/E percentile | yes | yes | yes |
| 10 | `fund.market_cap_proxy` | Market capitalisation (proxy) | yes | yes | yes |
| 11 | `fund.equity_proxy` | Book equity (proxy) | yes | yes | yes |
| 12 | `fund.eps` | Earnings per share | yes | yes | yes |
| 13 | `fund.net_worth_per_share` | Net worth per share | yes | yes | yes |
| 14 | `fund.profit` | Reported profit | yes | yes | yes |
| 15 | `fund.roe` | Return on equity (proxy) | yes | yes | yes |
| 16 | `fund.profit_per_capital` | Profit per unit capital | yes | yes | yes |
| 17 | `fund.paid_up_capital` | Paid-up capital | yes | yes | yes |
| 18 | `fund.capital_growth` | Paid-up capital growth | yes | yes | yes |
| 19 | `fund.book_value_growth` | Book-value growth | yes | yes | yes |
| 20 | `fund.earnings_volatility` | Earnings volatility | yes | yes | yes |
| 21 | `fund.eps_growth` | EPS growth | yes | yes | yes |
| 22 | `fund.eps_growth_consistency` | EPS growth consistency | yes | yes | yes |
| 23 | `fund.eps_cagr` | EPS CAGR (stored periods) | yes | yes | yes |
| 24 | `fund.earnings_rank` | EPS ranking | yes | yes | yes |
| 25 | `fund.value_rank` | Value ranking (low P/E) | yes | yes | yes |
| 26 | `fund.quality_rank` | Quality ranking (ROE proxy) | yes | yes | yes |
| 27 | `fund.growth_rank` | Growth ranking (EPS) | yes | yes | yes |
| 28 | `fund.composite_rank` | Composite value + quality rank | yes | yes | yes |
| 29 | `fund.cheap_quality_screen` | Cheap and high-quality screen | yes | yes | yes |
| 30 | `fund.negative_eps_flag` | Negative-earnings flag | yes | yes | yes |
| 31 | `fund.valuation_anomaly` | Valuation anomaly flag | yes | yes | yes |
| 32 | `fund.dividend_yield` | Dividend yield | yes | yes | yes |

## Verification

* Every entry above was opened through the real UI path; the panel was accepted only when it contained both the entry's stable id and its name, so a stale or wrong panel would fail the check.

* 0 entries failed; 0 families were sampled.

* Each panel exposes formula/parameters/tags/data-needs/limitations, per the shared information-panel contract.


## Honesty notes

* 'Limitations' is present on every entry; where an entry's real limitation is a data gap (e.g. promoter/public holdings, revenue, DPS), the panel says so instead of implying the number exists.

* The 233 total is 124 scanners + 77 algorithms + 32 fundamental tools, matching `catalog_health()` (`ok: true, tools: 233`). The fundamental count is not inflated; several fundamental tools honestly report a blocked/missing-data state.

* This audit verifies that the *catalogue entries and their panels* work. It is not a claim that every engine returns a value for every symbol — engine execution is covered by `tests/test_catalog.py` (52 tests) and the per-engine test suites.

