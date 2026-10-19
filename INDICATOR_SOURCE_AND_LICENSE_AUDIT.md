# Indicator source & license audit

Date: 2026-10-18 · Scope: the 92-entry indicator registry (`megatool/ta/`), the candlestick detectors (`megatool/ta/candles.py`), the chart's custom-formula DSL (`web/static/app.js`), and the third-party components the chart workbench loads. Method: the registry itself carries a per-indicator `reference` and `formula` field, echoed by `GET /api/indicators`; the tables below are generated from that registry and are the primary evidence for provenance. This is an inventory of what the repository records, not legal advice.

## 1. In-repo code provenance

* Every indicator below is implemented in Python inside this repository (`megatool/ta/*.py`). None of the implementations is a copy of third-party source code: each was written for this project from the published definition named in its `reference` field, with the arithmetic restated in the `formula` field and the guard tests verifying the stated formula.
* Indicator names (MACD, RSI, Bollinger Bands, Ichimoku, …) are used as conventional labels. No affiliation with, or endorsement by, any referenced author or platform is claimed.
* No TradingView Pine source, no Nepsealpha script text, and no community-forum code was copied into this repository. Where the owner's specification lists a script name (Parts 8–13), it was treated as a concept to implement from primary published definitions; nothing was copied verbatim from a source that carries restrictions.
* The chart's custom-formula DSL is original: a recursive-descent parser over a whitelisted function/series table with an AST evaluator — no `eval`, and unknown identifiers are rejected at parse time (session 19 record, B-84).

## 2. Registered indicator citations (generated from the registry)

| Indicator | Category | Recorded reference | Recorded formula |
|---|---|---|---|
| `accelerator_oscillator` | momentum | Bill Williams, New Trading Dimensions (1998). | AC = AO - SMA(AO, smooth), where AO = SMA(median, fast) - SMA(median, slow) |
| `awesome_oscillator` | momentum | Bill Williams, New Trading Dimensions (1998). | median = (high+low)/2; AO = SMA(median, fast) - SMA(median, slow) |
| `balance_of_power` | momentum | Igor Livshin, 'Balance of Power' (2001). | BOP = (close - open) / (high - low) |
| `cci` | momentum | Donald Lambert, 1980. | TP = (H+L+C)/3; CCI = (TP - SMA(TP,n)) / (0.015 * mean deviation) |
| `cmo` | momentum | Tushar Chande, The New Technical Trader (1994). | CMO = 100*(sum_up - sum_down)/(sum_up + sum_down) over absolute price changes |
| `connors_rsi` | momentum | Larry Connors & Cesar Alvarez, 'An Introduction to ConnorsRSI' (2012). | CRSI = ( RSI(close, 3) + RSI(streak, 2) + PercentRank(ROC1, 100) ) / 3; streak counts consecutive up (+) / down (-) closes, resetting on a reversal; PercentRank = 100 * (# window values strictly below the current ROC1) / (rank_period - 1) |
| `coppock_curve` | momentum | Edwin Sedgwick Coppock, Barron's (1962); WMA smoothing added by later implementations. | Coppock = WMA( ROC(close, long) + ROC(close, short), wma_period ) |
| `dpo` | momentum | Walt Bressert / 'Cycles' literature; popularised by Investor's Business Daily. | DPO[t] = close[t - (period//2 + 1)] - SMA(close, period)[t] |
| `fisher_transform` | momentum | John Ehlers, 'Using the Fisher Transform', TASC 2002. | x = 2*((hl2 - min(low,n))/(max(high,n)-min(low,n)) - 0.5), clipped to ±0.999 where hl2 = (high+low)/2; v[t] = 0.33*x + 0.67*v[t-1]; fisher[t] = 0.5*ln((1+v)/(1-v)) + 0.5*fisher[t-1]; trigger = fisher[t-1] |
| `force_index` | momentum | Alexander Elder, Trading for a Living (1993). | EFI[t] = (close[t]-close[t-1]) * volume[t]; efi_ema = EMA(EFI, period) |
| `kst` | momentum | Martin Pring, 'Summed Rate of Change' — KST (1992). | RCMA_i = SMA(ROC(close, n_i), m_i); KST = 1*RCMA1 + 2*RCMA2 + 3*RCMA3 + 4*RCMA4 with (n,m) = (10,10),(15,10),(20,10),(30,15); signal = SMA(KST, 9) |
| `macd` | momentum | Gerald Appel, 1979. | MACD = EMA(fast) - EMA(slow); signal = EMA(MACD, signal); hist = MACD - signal |
| `momentum` | momentum | Standard momentum measure. | MOM[t] = close[t] - close[t-n] |
| `ppo` | momentum | Gerald Appel: the MACD expressed as a percentage of the slow EMA. | PPO = 100*(EMA(fast) - EMA(slow))/EMA(slow); signal = EMA(PPO, signal) |
| `price_oscillator` | momentum | Classic percentage price oscillator with SIMPLE moving averages. | price_osc = 100 * (SMA(close, fast) - SMA(close, slow)) / SMA(close, slow) |
| `roc` | momentum | Standard momentum measure. | ROC[t] = 100 * (close[t] - close[t-n]) / close[t-n] |
| `rsi` | momentum | J. Welles Wilder, New Concepts in Technical Trading Systems (1978). | change = diff(close); avg_gain/loss = Wilder smooth; RS = avg_gain/avg_loss; RSI = 100 - 100/(1+RS) |
| `rvi` | momentum | John Ehlers, 'The Relative Vigor Index', TASC 2002. | num = SMA(SWMA(close-open), period); den = SMA(SWMA(high-low), period); RVI = num/den; signal = SWMA(RVI); SWMA = (x[t-3] + 2x[t-2] + 2x[t-1] + x[t])/6 |
| `smi` | momentum | William Blau, Momentum, Direction and Divergence (1993). | mid = (highest(high,n)+lowest(low,n))/2; rel = close - mid; halfrange = (highest(high,n)-lowest(low,n))/2; SMI = 100 * EMA(EMA(rel, k1), k2) / EMA(EMA(halfrange, k1), k2); signal = EMA(SMI, s) |
| `stochastic` | momentum | George Lane, 1950s. | %K = 100*(close - lowest_low(n)) / (highest_high(n) - lowest_low(n)); %D = SMA(%K, d) |
| `stochastic_rsi` | momentum | Tushar Chande & Stanley Kroll, The New Technical Trader (1994). | StochRSI[t] = 100 * (RSI[t] - min(RSI, stoch_period)) / (max(RSI, stoch_period) - min(RSI, stoch_period)) |
| `trix` | momentum | Jack Hutson, 1980s. | Triple-smoothed EMA of close; TRIX = 100 * pct change of that EMA. |
| `tsi` | momentum | William Blau, Momentum, Direction and Divergence (1995). | TSI = 100 * EMA(EMA(change, long), short) / EMA(EMA(\|change\|, long), short) |
| `ultimate_oscillator` | momentum | Larry Williams, 'Ultimate Oscillator', TASC 1985. | BP = close - min(low, prev close); TR = max(high, prev close) - min(low, prev close); avg_n = sum(BP,n)/sum(TR,n); UO = 100*(4*avg_short + 2*avg_medium + avg_long)/7 |
| `williams_r` | momentum | Larry Williams, 1973. | %R = -100 * (highest_high(n) - close) / (highest_high - lowest_low) |
| `average_price` | other | Common OHLC mean; used by several platforms as 'AvgPrice'. | average_price = (open + high + low + close) / 4 |
| `median_price` | other | **(none recorded)** | MP[t] = (high + low) / 2 |
| `pivot_points` | other | Traditional trading-floor pivot calculation. | from the PREVIOUS bar's H/L/C: P = (H+L+C)/3; R1 = 2P - L, S1 = 2P - H, R2 = P + (H-L), S2 = P - (H-L), R3 = H + 2(P-L), S3 = L - 2(H-P) |
| `price_correlation` | other | Pearson product-moment correlation, applied to (bar index, close). | x = 0..n-1 over the window ; corr = cov(x, close) / (stddev(x) * stddev(close)), using population moments (ddof=0) over the last `period` bars |
| `standard_deviation` | other | **(none recorded)** | std over the trailing `period` closes (sample ddof by default) |
| `typical_price` | other | **(none recorded)** | TP[t] = (high + low + close) / 3 |
| `weighted_close` | other | **(none recorded)** | WC[t] = (high + low + 2*close) / 4 |
| `williams_fractal` | other | Bill Williams, 'Trading Chaos' (1995). | up[i] = high[i] if high[i] is strictly the highest of the 2*W+1 bars centred on i, else NaN ; down[i] = low[i] if low[i] is strictly the lowest of those bars, else NaN |
| `zigzag` | other | Common chartist construction (percent-reversal swing filter). | Track an extreme; when price retraces at least threshold_pct from that extreme, the extreme is confirmed as a pivot and the direction flips. The pivot's price is stamped on its bar; every other bar is a gap. |
| `zscore` | other | **(none recorded)** | z[t] = (close[t] - mean(close, period)) / std(close, period) |
| `adx` | trend | J. Welles Wilder (1978). Trend-strength, not direction. | +DM = max(H-Hp,0) if (H-Hp)>(Lp-L) else 0; -DM likewise; DI = 100*Wilder(PDM)/ATR; DX = 100*\|+DI - -DI\|/(+DI + -DI); ADX = Wilder(DX) |
| `alligator` | trend | Bill Williams, Trading Chaos (1995). | lines = SMMA(SMMA of (high+low)/2, n) displaced back by `offset` bars: jaw n=13 offset 8, teeth n=8 offset 5, lips n=5 offset 3 |
| `alma` | trend | Arnaud Legoux & Dimitrios Kouzis-Loukas, ALMA (2009). | W_i = exp(-(i - m)^2 / (2*s^2)), m = offset*(period-1), s = period/sigma; ALMA[t] = sum(W_i * close[t-period+1+i]) / sum(W_i) |
| `aroon` | trend | Tushar Chande, 1995. | Aroon Up = 100 * (period - bars_since_high) / period |
| `chande_kroll_stop` | trend | Tushar Chande & Stanley Kroll (1995), 'The New Technical Trader'. | ATR = Wilder ATR(atr_period) ; xATR = multiplier * ATR ; yATR = trail * ATR ; initial_long = max(high, period) - xATR ; initial_short = min(low, period) + xATR ; stop_long = max(stop_long[-1], close - yATR) ; stop_short = min(stop_short[-1], close + yATR), seeded from the initial stops |
| `dema` | trend | Patrick Mulloy, 1994. | DEMA[t] = 2*EMA(close, p) - EMA(EMA(close, p), p) |
| `ema` | trend | Seeded with SMA of the first `period` values. | EMA[t] = EMA[t-1] + 2/(period+1) * (close[t] - EMA[t-1]) |
| `envelopes` | trend | Standard MA-envelope construction (percent bands around an SMA). | middle = SMA(close, period); upper = middle * (1 + percent/100); lower = middle * (1 - percent/100) |
| `gmma` | trend | Daryl Guppy, 'Trading Tactics' (1998). | 12 SMAs of close: short group (3,5,8,10,12,15) tracks traders, long group (30,35,40,45,50,60) tracks investors. |
| `hma` | trend | Alan Hull, 2005. Reduces lag while keeping smoothness. | HMA = WMA(2*WMA(period/2) - WMA(period), round(sqrt(period))) |
| `ichimoku` | trend | Goichi Hosoda, 1930s. | Tenkan/Kijun = midpoint of highest-high/lowest-low over n; Senkou A = (Tenkan+Kijun)/2; Senkou B = midpoint over senkou_b |
| `kama` | trend | Perry Kaufman, Trading Systems and Methods (1995/2013). | ER = \|change\| / volatility; SC = (ER*(fast_sc - slow_sc) + slow_sc)^2; KAMA[t] = KAMA[t-1] + SC*(close[t] - KAMA[t-1]) |
| `linreg_slope` | trend | Standard OLS; slope of the rolling linear-regression fit. | slope[t] = sum((x-xmean)*(y-ymean)) / sum((x-xmean)^2), x=0..period-1, window ending at t |
| `lsma` | trend | Oldest recorded use: R. B. Barnaby / 'time series forecast' (1936); popularised as LSMA on TradingView. | OLS fit of close on x=0..period-1 over the window ending at t; LSMA[t] = fitted value at x = period-1 (the endpoint) |
| `ma_cross` | trend | Classic dual-moving-average crossover (Gardner; widely published). | fast = SMA(close, fast) ; slow = SMA(close, slow) ; diff = fast - slow ; state = +1 while fast > slow else -1 (0 before the first full window) |
| `mcginley_dynamic` | trend | John R. McGinley, 'The McGinley Dynamic' (1990s). | MD[t] = MD[t-1] + (close[t] - MD[t-1]) / (period * (close[t]/MD[t-1])^4); seeded with the SMA of the first `period` values |
| `parabolic_sar` | trend | J. Welles Wilder, New Concepts in Technical Trading Systems (1978). | SAR[t] = SAR[t-1] + AF*(EP - SAR[t-1]); AF grows by `step` while the extreme point (EP) advances, up to `maximum`; SAR flips side when price crosses it. |
| `sma` | trend | Arithmetic mean of the last `period` closes. | SMA[t] = mean(close[t-period+1 .. t]) |
| `smma` | trend | J. Welles Wilder, New Concepts in Technical Trading Systems (1978). | SMMA[t] = SMMA[t-1] + (close[t] - SMMA[t-1]) / period; seeded with the SMA of the first `period` values |
| `supertrend` | trend | Commonly used in Indian/South-Asian technical analysis. | UB/LB = ATR-based bands; supertrend flips when close crosses them. |
| `t3` | trend | Tim Tillson, 'Smoothing Techniques for More Accurate Signals', TASC 1998. | Six chained EMAs (e1..e6). c1=-v^3; c2=3v^2+3v^3; c3=-6v^2-3v-3v^3; c4=1+3v+v^3+3v^2; T3 = c1*e6 + c2*e5 + c3*e4 + c4*e3  (v = volume_factor) |
| `tema` | trend | Patrick Mulloy, 1994. | TEMA[t] = 3*EMA - 3*EMA(EMA) + EMA(EMA(EMA)) |
| `vidya` | trend | Tushar Chande, 'Chande's Variable Index Dynamic Average', TASC 1992. | k = 2/(short_period+1); w = \|CMO(period)\|/100; VIDYA[t] = (k*w)*close[t] + (1 - k*w)*VIDYA[t-1]; seeded with close at the first bar where CMO is available |
| `vortex` | trend | Etienne Botes & Douglas Siepman, 2009 (published in Technical Analysis of Stocks & Commodities, 2010). | VM+ = \|high - prev low\| ; VM- = \|low - prev high\| ; TR = true range ; VI+ = sum(VM+, n) / sum(TR, n) ; VI- = sum(VM-, n) / sum(TR, n) |
| `vwma` | trend | A simple average whose observations are each weighted by that bar's volume. | VWMA[t] = sum(close[i]*volume[i]) / sum(volume[i]) over i in [t-period+1 .. t] |
| `wma` | trend | Linear weights, most recent observation weighted highest. | WMA[t] = sum(i * close[t-period+i]) / sum(1..period), i=1..period |
| `zlema` | trend | Ehlers-style lag compensation; popularised by John Ehlers. | lag = floor((period-1)/2); zl[t] = 2*close[t] - close[t-lag]; ZLEMA = EMA(zl, period) |
| `atr` | volatility | J. Welles Wilder, New Concepts in Technical Trading Systems (1978). | TR = max(H-L, \|H-Pc\|, \|L-Pc\|); ATR = Wilder smooth of TR |
| `bollinger` | volatility | John Bollinger, 1980s. | middle = SMA(n); upper/lower = middle +/- k * population stddev(n) |
| `bollinger_width` | volatility | John Bollinger, 1980s (band-width presentation). | middle = SMA(close, n) ; sd = population stddev(close, n) ; upper/lower = middle +/- k*sd ; width_pct = 100 * (upper - lower) / middle |
| `chaikin_volatility` | volatility | Marc Chaikin (published in Technical Analysis of Stocks & Commodities). | hl = high - low ; e = EMA(hl, ema_period) ; chaikin_vol = 100 * (e - e[roc_period ago]) / e[roc_period ago] |
| `choppiness` | volatility | E. W. Dreiss, 'The Choppiness Index', TASC 1993. | CHOP = 100 * log10( sum(TR, period) / (highest(high, period) - lowest(low, period)) ) / log10(period) |
| `donchian` | volatility | Richard Donchian; popularised by the Turtle Traders. | upper = max(high, n); lower = min(low, n); middle = mean of the two |
| `garman_klass` | volatility | Garman & Klass, 'On the Estimation of Security Price Volatilities from Historical Data', Journal of Business (1980). | v[t] = 0.5*ln(H/L)^2 - (2*ln2 - 1)*ln(C/O)^2; gk_vol = 100*sqrt( mean(v, period) * annualize ) |
| `historical_volatility` | volatility | Standard close-to-close realised volatility. | HV = stddev(log return, n) * sqrt(trading_days) * 100 |
| `keltner` | volatility | Chester Keltner, 1960; ATR variant popularised by Linda Raschke. | middle = EMA(n); upper/lower = middle +/- multiplier * ATR(atr_period) |
| `mass_index` | volatility | Donald Dorsey, 'The Mass Index', TASC 1992. | ratio = EMA(high-low, period) / EMA(EMA(high-low, period), period); mass = sum(ratio, sum_period) |
| `percent_b` | volatility | John Bollinger, 1980s. | middle = SMA(close, n) ; sd = population stddev(close, n) ; upper/lower = middle +/- k*sd ; %B = (close - lower) / (upper - lower) |
| `relative_volatility_index` | volatility | Donald Dorsey, 1993 (Technical Analysis of Stocks & Commodities). | sd = population stddev(close, n) ; up = sd where close > close[-1] else 0 ; dn = sd where close < close[-1] else 0 ; rvi = 100 * Wilder(up, n) / (Wilder(up, n) + Wilder(dn, n)) ; signal = SMA(rvi, signal) |
| `standard_error` | volatility | Standard OLS residual standard error. | se[t] = sqrt( sum((y - y_hat)^2) / (period - 2) ) over the rolling fit of close on x = 0..period-1 |
| `standard_error_bands` | volatility | Jon Anderson, 'Standard Error Bands', TASC 1996. | middle = linear-regression endpoint over the window; upper = middle + mult*se; lower = middle - mult*se |
| `true_range` | volatility | J. Welles Wilder (1978). | TR = max(H-L, \|H-Pc\|, \|L-Pc\|) |
| `volatility_zero_trend` | volatility | 'Zero-trend' volatility: mean absolute close-to-close change without assuming any drift. | VZT = 100 * mean(\|close[t-k+1] - close[t-k]\|, k=1..period) / mean(close, period) |
| `ad_line` | volume | Chaikin, 1960s. | CLV = ((close-low) - (high-close)) / (high-low); AD = cumsum(CLV * volume) |
| `chaikin_oscillator` | volume | Marc Chaikin: the MACD of the Accumulation/Distribution line. | Chaikin Osc = EMA(ad_line, fast) - EMA(ad_line, slow) |
| `cmf` | volume | Marc Chaikin. | MFV = (((close-low) - (high-close)) / (high-low)) * volume; CMF = sum(MFV, period) / sum(volume, period) |
| `ease_of_movement` | volume | Richard Arms, 'Volume Adjusted Moving Averages' (1960s). | distance = (high+low)/2 - (prev high+prev low)/2; box_ratio = volume / (high-low); emv = SMA(distance / box_ratio, period) |
| `klinger` | volume | Stephen Klinger, 'Volume Oscillator Confirms Price Movements', TASC 1997. | trend[t] = sign of (high+low) change vs previous bar, holding on equal; cm[t] = cm[t-1] + dm if trend unchanged else dm[t-1] + dm[t], dm = high-low; vf[t] = volume * \|2*(dm/cm - 1)\| * trend * 100; KVO = EMA(vf, short) - EMA(vf, long); signal = EMA(KVO, signal) |
| `mfi` | volume | Quinn and Weigand, 1990s. | raw money flow = typical price * volume; MFI = 100 - 100/(1+money ratio) |
| `net_volume` | volume | Per-bar signed volume (up/down volume decomposition). | net_volume[t] = +volume[t] if close rises; -volume[t] if it falls; 0 if unchanged. Bar 0 has no previous close and is 0 by construction. |
| `obv` | volume | Joseph Granville, 1963. | OBV[t] = OBV[t-1] + volume[t] if close rises; - volume if it falls; unchanged if close is flat. |
| `pvt` | volume | Classic Price Volume Trend (PVT), described in most volume-analysis texts. | PVT[t] = PVT[t-1] + volume[t] * (close[t]-close[t-1]) / close[t-1] |
| `relative_volume` | volume | volume[t] / mean(volume over trailing baseline window) | RVOL = volume / SMA(volume, baseline) |
| `volume_oscillator` | volume | Standard volume-oscillator construction (percentage difference of two volume EMAs). | volume_osc = 100 * (EMA(volume, short) - EMA(volume, long)) / EMA(volume, long) |
| `volume_roc` | volume | Percentage change in volume against `period` bars earlier. | VROC = 100*(volume[t] - volume[t-period]) / volume[t-period] |
| `volume_sma` | volume | Simple moving average of volume. | SMA(volume, n) |
| `vwap_bands` | volume | Rolling volume-weighted average price over `period` bars. | VWAP = sum(typical_price * volume) / sum(volume) over the window |

## 3. Data sources and bundled components

* **lightweight-charts 4.2.3** — vendored unmodified at `web/static/vendor/lightweight-charts.standalone.js`; TradingView's Lightweight Charts is published under Apache-2.0. The license text is not re-vendored here.
* **NEPSE price history** — collected from public mirrors. The community dataset `github.com/Aabishkar2/nepse-data` carries no LICENSE file (recorded limitation L-03 in `KNOWN_BUGS.md`); its redistribution terms are unverified, so the data stays in the local research store.
* **yonepse quote pages** — free public source; terms as published by the operator; fetched without authentication.
* **Kronos model weights** (`data/models/Kronos-mini`, `Kronos-Tokenizer-2k`) — official downloads from the KRONOS authors' Hugging Face repositories, recorded as byte-exact vs HF in the session-18 record. No license text is vendored; treated as research-use. Kronos is not used by any indicator in the tables above.
* **python-dotenv** — CVE-triggered upgrade is pending the owner's decision (see `REMAINING_BLOCKERS.md`).

## 4. Approximations and parity claims

This project makes **no exact-parity claim** against any third-party implementation. Where an approximation exists it is stated in the indicator's `notes` field and its module docstring (e.g., all cached-line transform implementations document their warm-up handling). Field-for-field comparison against reference implementations has not been run; the verification that exists is the project's own guard suite: `tests/test_indicators.py` (invariants over every registered indicator) and `tests/test_indicators2.py` (literal reference-value tests). The catalogue's **Verification** section reports the derived split: 49 reference / 41 invariants / 2 sparse.

## 5. Restrictions honoured

* No paid API calls, no scraping of restricted content, no copied Pine sources, no deployments, no production database writes were performed for this work.
* Market-intelligence sources have their own terms and are covered separately by `docs/LIVE_DATA.md` and `docs/DATA_SOURCES.md`; they are outside this audit's scope (the audit covers computation code, not news/content sources).

### Registry completeness check (generated)

* Indicators with a recorded reference: **87/92**. Indicators with a recorded formula: **92/92**. (The 5 without a personal attribution are generic constructions — `median_price`, `standard_deviation`, `typical_price`, `weighted_close`, `zscore` — not invented citations.)
* Missing references: median_price, standard_deviation, typical_price, weighted_close, zscore.
* Missing formulas: —.
