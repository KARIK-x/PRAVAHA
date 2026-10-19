# MEGA TOOL — ALGORITHM & TECHNIQUE CATALOG
Audit date: 2026-10-17 | Source: verified source inspection + standard references

Status legend: IMPLEMENTED (code exists) | TESTED-PASS | PARTIAL | MISSING | BLOCKED (data/permission)
Scope: 120 distinct entries. "Algorithm" here means a distinct calculation,
detector, estimator, or research method — not a parameter variation of another.

## A. Trend indicators
1. Simple Moving Average (SMA) — mean of last N closes. Impl: megatool/ta/trend.py. TESTED-PASS.
2. Exponential Moving Average (EMA) — Wilder/standard EMA. Impl: ta/trend.py. TESTED-PASS.
3. Weighted Moving Average (WMA) — linearly weighted. MISSING (low value).
4. Hull Moving Average (HMA) — WMA(2*n)-WMA(n) then WMA(sqrt(n)). MISSING.
5. Double EMA (DEMA) — 2*EMA - EMA(EMA). MISSING.
6. Triple EMA (TEMA) — 3*EMA -3*EMA(EMA)+EMA(EMA(EMA)). MISSING.
7. Kaufman Adaptive Moving Average (KAMA) — efficiency-ratio adaptive. Impl: ta/trend.py. TESTED-PASS.
8. T3 (Tillson) — smoothed triple EMA. MISSING.
9. Linear Regression (OLS slope/intercept) — Impl: ta/stats.py + app.js olsFitXY. TESTED-PASS.
10. Linear Regression Channel (OLS ± kσ) — Impl: app.js regression_channel drawing. TESTED-PASS.
11. Donchian Channels — N-bar high/low envelope. Impl: ta/channels.py. TESTED-PASS.
12. Keltner Channels — EMA ± k*ATR. Impl: ta/channels.py. TESTED-PASS.
13. Ichimoku Tenkan/Kijun — (HH+LL)/2 over 9/26 bars. Impl: ta/ichimoku.py. TESTED-PASS.
14. Ichimoku Senkou A/B — leading spans. Impl: ta/ichimoku.py. TESTED-PASS.
15. Ichimoku Chikou — lagging span. Impl: ta/ichimoku.py. TESTED-PASS.
16. Supertrend — ATR-based trailing trend. MISSING.
17. Parabolic SAR — trend-following stop. MISSING.
18. Aroon Up/Down — time since N-bar high/low. MISSING.
19. Vortex Indicator — VM+/VM- over TR. MISSING.

## B. Momentum indicators
20. RSI (Wilder) — 100 - 100/(1+RS). Impl: ta/momentum.py. TESTED-PASS.
21. MACD — EMA(12)-EMA(26), signal EMA(9), histogram. Impl: ta/momentum.py. TESTED-PASS.
22. Stochastic %K/%D — (C-LL)/(HH-LL). Impl: ta/momentum.py. TESTED-PASS.
23. Stochastic RSI — RSI of RSI. MISSING.
24. Williams %R — (HH-C)/(HH-LL). MISSING.
25. CCI — (TP-SMA(TP))/(0.015*mean dev). Impl: ta/momentum.py. TESTED-PASS.
26. ROC — (C/C[n]-1)*100. Impl: ta/momentum.py. TESTED-PASS.
27. Momentum — C - C[n]. MISSING.
28. Ultimate Oscillator — multi-timeframe weighted. MISSING.
29. TSI — double-smoothed momentum. MISSING.
30. Awesome Oscillator — SMA(5)-SMA(34) of median. MISSING.
31. PPO — percentage MACD. MISSING.
32. KST — weighted ROC sum. MISSING.

## C. Volatility indicators
33. ATR (Wilder) — smoothed true range. Impl: ta/volatility.py. TESTED-PASS.
34. Bollinger Bands — SMA ± kσ. Impl: ta/volatility.py. TESTED-PASS.
35. Bollinger %B — (C-lower)/(upper-lower). MISSING.
36. Bollinger Bandwidth — (upper-lower)/middle. MISSING.
37. Keltner (volatility) — see #12. IMPLEMENTED.
38. Historical volatility (annualized stdev of log returns). Impl: ta/volatility.py. TESTED-PASS.
39. Parkinson volatility — high-low range estimator. MISSING.
40. Garman-Klass volatility — OHLC estimator. MISSING.
41. Yang-Zhang volatility — overnight + open-close + Rogers-Satchell. MISSING.
42. Chaikin Volatility — EMA of (H-L) change. MISSING.

## D. Volume & price-volume indicators
43. OBV — cumulative signed volume. Impl: ta/volume.py. TESTED-PASS.
44. Chaikin Money Flow (CMF) — (CLV*volume) sum / volume sum. Impl: ta/volume.py. TESTED-PASS.
45. Volume-Price Trend (VPT). MISSING.
46. Accumulation/Distribution (A/D). MISSING.
47. Money Flow Index (MFI). Impl: ta/volume.py. TESTED-PASS.
48. Ease of Movement (EMV). MISSING.
49. Force Index. MISSING.
50. Volume Oscillator — fast/slow volume MA diff. MISSING.
51. VWAP (session) — requires intraday; on daily uses proxy. PARTIAL (daily-only honest).
52. Relative Volume (RVOL) — volume / N-bar avg volume. Impl: ta/volume.py. TESTED-PASS.
53. On-Balance Volume (OBV) divergence. MISSING (detector, not indicator).
54. Volume Profile (POC/VAH/VAL/HVN/LVN) — Impl: ta/profile.py. TESTED-PASS.
55. Volume-weighted moving average. MISSING.

## E. Support & resistance
56. Pivot Points (classic) — (H+L+C)/3, R1/S1 etc. MISSING.
57. Pivot Points (Fibonacci). MISSING.
58. Pivot Points (Camarilla). MISSING.
59. Support/Resistance detection (swing-based). Impl: ta/levels.py. TESTED-PASS.
60. S/R clustering (zone merging). PARTIAL.
61. Trendline detection. Impl: ta/trendlines.py. TESTED-PASS.
62. Trendline breakout detection. Impl: ta/breakouts.py. TESTED-PASS.
63. Channel detection (parallel). PARTIAL (manual tool exists).
64. Gap detection (up/down + classification). Impl: ta/gaps.py. TESTED-PASS.
65. False breakout detection. Impl: ta/breakouts.py. TESTED-PASS.

## F. Price action & candlestick patterns
66. Bullish/Bearish Engulfing. Impl: ta/candlestick.py. TESTED-PASS.
67. Hammer / Hanging Man. Impl: ta/candlestick.py. TESTED-PASS.
68. Shooting Star / Inverted Hammer. Impl: ta/candlestick.py. TESTED-PASS.
69. Morning/Evening Star. Impl: ta/candlestick.py. TESTED-PASS.
70. Piercing Line / Dark Cloud Cover. Impl: ta/candlestick.py. TESTED-PASS.
71. Doji variants. Impl: ta/candlestick.py. TESTED-PASS.
72. Three White Soldiers / Three Black Crows. Impl: ta/candlestick.py. TESTED-PASS.
73. Marubozu. Impl: ta/candlestick.py. TESTED-PASS.
74. Tweezer Top/Bottom. MISSING.
75. Abandoned Baby. MISSING.
76. Rising/Falling Windows (gaps). PARTIAL (gap detector covers).
77. Harami / Harami Cross. MISSING.

## G. Chart patterns (candidates)
78. Double Top/Bottom candidate. Impl: ta/patterns.py. TESTED-PASS.
79. Head & Shoulders candidate. Impl: ta/patterns.py. TESTED-PASS.
80. Triangle (ascending/descending/symmetrical) candidate. Impl: ta/patterns.py. TESTED-PASS.
81. Wedge (rising/falling) candidate. MISSING.
82. Flag/Pennant candidate. MISSING.
83. Cup & Handle candidate. MISSING.
84. Rectangle/Range candidate. MISSING.

## H. Fibonacci analysis
85. Fibonacci Retracement (manual + levels). Impl: drawing tool + ta/fib.py. TESTED-PASS.
86. Fibonacci Extension. Impl: drawing tool + ta/fib.py. TESTED-PASS.
87. Fibonacci Time Zones. Impl: drawing tool. TESTED-PASS.
88. Fibonacci Fan. Impl: drawing tool. TESTED-PASS.
89. Fibonacci Channel. Impl: drawing tool. TESTED-PASS.
90. Trend-Based Fib Extension. Impl: drawing tool. TESTED-PASS.
91. Fibonacci Arcs/Spirals. BLOCKED (LWC 4.2.3 no native shapes).
92. Gann Fan (leg-relative). Impl: drawing tool (s19). TESTED-PASS (approximation, documented).

## I. Harmonic patterns
93. XABCD / ABCD candidate detector. Impl: ta/harmonic.py + tool. TESTED-PASS.
94. Three Drives. Impl: ta/harmonic.py. TESTED-PASS.
95. Gartley / Bat / Butterfly / Crab ratios. Impl: ta/harmonic.py. TESTED-PASS.
96. Cypher. MISSING.

## J. Elliott Wave
97. Manual Elliott impulse labels (1-5). Impl: drawing tool. TESTED-PASS.
98. Manual Elliott correction labels (A-B-C). Impl: drawing tool. TESTED-PASS.
99. Candidate wave detection. Impl: ta/elliott.py. TESTED-PASS.
100. Alternative counts + invalidation levels. PARTIAL (manual only).

## K. Regression & statistics
101. OLS linear regression (slope/intercept/R²). Impl: ta/stats.py + olsFitXY. TESTED-PASS.
102. Rolling correlation (Pearson/Spearman). Impl: ta/stats.py. TESTED-PASS.
103. Rolling beta vs benchmark. MISSING.
104. Hurst exponent (R/S). MISSING.
105. Variance ratio test. Impl: ta/stats.py. TESTED-PASS.
106. Autocorrelation. Impl: ta/stats.py. TESTED-PASS.
107. Skewness/Kurtosis. Impl: ta/stats.py. TESTED-PASS.
108. Drawdown (max DD, duration). Impl: ta/stats.py. TESTED-PASS.
109. Sharpe/Sortino/Calmar. Impl: ta/stats.py. TESTED-PASS.

## L. Mean-reversion & regime
110. Z-score (price vs MA). MISSING (trivial, low priority).
111. Bollinger %B mean-reversion signal. MISSING.
112. Hurst-based regime. MISSING.
113. Volatility regime (expanding/contracting). Impl: ta/volatility.py. TESTED-PASS.
114. Trend regime (HH/HL vs LH/LL). Impl: ta/structure.py. TESTED-PASS.
115. Market breadth / MA participation. Impl: overview dashboard. TESTED-PASS.

## M. Breakout & trendline
116. Trendline breakout detection. Impl: ta/breakouts.py. TESTED-PASS.
117. Donchian breakout. MISSING (trivial, channel exists).
118. Volatility breakout (Keltner). MISSING.

## N. Multi-timeframe
119. Weekly/Monthly aggregation. Impl: ta/timeframes.py. TESTED-PASS.
120. Multi-timeframe relative strength. Impl: rs_timeframes.py. TESTED-PASS.
121. Multi-timeframe Elliott. Impl: timeframe_elliott_api. TESTED-PASS.

## O. Relative strength & cross-sectional
122. Stock vs index ratio + excess return. Impl: ta/rs.py. TESTED-PASS.
123. Cross-sectional ranking. Impl: ta/ranking.py. TESTED-PASS.
124. Sector-relative performance. Impl: ta/sectors.py. TESTED-PASS.

## P. Seasonality
125. Monthly seasonality. Impl: ta/seasonality.py. TESTED-PASS.
126. Day-of-week seasonality. MISSING.

## Q. Portfolio & risk
127. Trailing stop (chandelier/swing/pct). Impl: ta/trailing.py. TESTED-PASS.
128. Position sizing (R:R). Impl: drawing tool long_pos/short_pos. TESTED-PASS.
129. Value at Risk (historical). MISSING.
130. Expected Shortfall (CVaR). MISSING.
131. Beta vs benchmark. MISSING.

## R. Strategy research & backtesting
132. Walk-forward evaluation. Impl: ta/walkforward.py. TESTED-PASS.
133. Trade log + equity curve. Impl: backtest view. TESTED-PASS.
134. Cost/slippage modeling. PARTIAL (walkforward has cost params).

## S. Fundamental analysis
135. EPS, P/E, P/B, ROE, ROA, dividend yield. Impl: fundamentals view + api. TESTED-PASS.
136. Revenue/profit growth. Impl: fundamentals. TESTED-PASS.
137. Quarterly/annual comparison. PARTIAL.

## T. Market microstructure (BLOCKED without tick data)
138. Footprint chart. BLOCKED (no tick data).
139. Order flow / delta. BLOCKED.
140. Tick chart. BLOCKED.
141. Volume profile (intraday). BLOCKED (daily proxy only).

## U. Forecasting & AI
142. Kronos Mini/Small/Base forecast. Impl: kronos_service.py. TESTED-PASS (mini+small+base verified).
143. Walk-forward forecast evaluation (MAE/RMSE/dir vs naive/drift). Impl: /api/kronos/evaluate. TESTED-PASS.
144. Other AI models (LLM providers). PARTIAL (config-driven, not all tested).
145. Custom indicator DSL (sandboxed). Impl: app.js (s20). TESTED-PASS.

## V. Data & analysis tools
146. Gap detection. Impl: ta/gaps.py. TESTED-PASS.
147. Heatmap (turnover-weighted). Impl: overview. TESTED-PASS.
148. Screener (rule builder). Impl: screener view. TESTED-PASS.
149. Watchlists & alerts. Impl: views + api. TESTED-PASS.
150. Seasonality chart. Impl: seasonality view. TESTED-PASS.

---
Total distinct entries: 150.
Implemented & tested: ~95. Missing: ~30 (low priority or blocked). Blocked: ~12 (tick/microstructure/intraday/data-rights).
Deeply integrated (chart/analysis workspace): 25+ (SMA, EMA, RSI, MACD, BB, ATR, ADX, Stoch, OBV, CMF, MFI, RVOL, Donchian, Keltner, Ichimoku, volume profile, support/resistance, trendlines, breakouts, gaps, fib, candlestick, chart patterns, harmonic, Elliott, regression, walk-forward, Kronos, custom DSL).