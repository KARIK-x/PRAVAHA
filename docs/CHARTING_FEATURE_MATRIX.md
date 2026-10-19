# Charting feature matrix — session 19 (2026-10-17)

Status labels: IMPLEMENTED / TESTED-PASS / TESTED-FAIL / PARTIALLY IMPLEMENTED / NOT-TESTED / BLOCKED / MISSING.
Honesty rule: a button that renders but has no handler is MISSING, not IMPLEMENTED.
Source of truth for what ships: `web/static/app.js`, `web/static/index.html`, `megatool/api.py`.

| # | Group | Status | Key source | Data dependency | Notes |
|---|---|---|---|---|---|
| 1 | Chart controls (symbol, tf, range, style) | TESTED-PASS | app.js loadChart, #chart-type | stored bars | daily/weekly/monthly; 4 render styles now |
| 2 | Drawing tools (47) | TESTED-PASS | RAIL_GROUPS, renderDrawings | chart bars | 9 categories + search; undo/redo unified |
| 3 | Technical indicators | PARTIALLY IMPLEMENTED | #ind-* + catalog | stored bars | 7 quick + catalog (formula-documented); no templates until s19 |
| 4 | Trend analysis | IMPLEMENTED | applyChartLayers (opt-in) | stored bars | layers start off |
| 5 | Support/resistance | IMPLEMENTED | plotSupportResistance | stored bars | opt-in layer |
| 6 | Price action | PARTIALLY IMPLEMENTED | candle detection module | stored bars | candle patterns view exists |
| 7 | Candlestick patterns | IMPLEMENTED | candle-run | stored bars | trend-context aware |
| 8 | Chart patterns | IMPLEMENTED | pattern overlay + panel | stored bars | caps are render-time only |
| 9 | Harmonic patterns | IMPLEMENTED | harmonic layer | stored bars | XABCD/ABCD/3-drives tools |
| 10 | Elliott Wave | PARTIALLY IMPLEMENTED | elliott layer + tools | stored bars | manual counts only; no auto-certainty claim |
| 11 | Fibonacci analysis | IMPLEMENTED | fib_* tools + api fib | stored bars | retr/ext/timezones/fan/channel/TBE |
| 12 | Market structure / SMC | PARTIALLY IMPLEMENTED | /api layers (order blocks etc.) | stored bars | endpoints exist; not all wired to chart |
| 13 | Trendline breakout | PARTIALLY IMPLEMENTED | breakout layer | stored bars | endpoint + layer |
| 14 | Volume analysis | IMPLEMENTED | vol histogram + OBV/VWAP | stored bars | volume pane + indicators |
| 15 | Relative strength | PARTIALLY IMPLEMENTED | rs overlay + panel | stored bars | RS vs Nifty where data exists |
| 16 | Multi-timeframe analysis | PARTIALLY IMPLEMENTED | tf-select | stored bars | no side-by-side MTF pane yet |
| 17 | Seasonality | IMPLEMENTED | seasonality view | stored bars | endpoint + view |
| 18 | Swing trading research | IMPLEMENTED | swing view | stored bars | dedicated view |
| 19 | Stock scanners | IMPLEMENTED | screener + more scanners views | stored bars | endpoints + views |
| 20 | Stock heatmap | IMPLEMENTED | heatmap view | stored bars | view exists |
| 21 | Watchlists & alerts | IMPLEMENTED | watchlists + alerts views | stored bars | endpoints + views |
| 22 | Fundamental analysis | IMPLEMENTED | fundamentals view | fundamentals CSV | ratios + growth |
| 23 | Chart comparison | PARTIALLY IMPLEMENTED | benchmark overlay | stored bars | benchmark toggle |
| 24 | Replay | IMPLEMENTED (s19) | #pop-replay | stored bars | bars only up to cursor |
| 25 | Footprint / order flow | BLOCKED | — | tick data | no tick data available |
| 26 | AI-assisted analysis | PARTIALLY IMPLEMENTED | research view | stored bars | structured report, no single score |
| 27 | Forecasting & model eval | TESTED-PASS | Kronos chart + forecaster | stored bars + weights | mini/small/base, walk-forward eval |
| 28 | Research results & audit trails | IMPLEMENTED | research view + experiments | stored bars | experiments persist backend |

P0 (correctness / broken interactions) — done in s19:
- Kronos buttons (tf guard, stale guard, symbol guard, loading feedback).
- Forecast rendering (bullish/bearish bodies + amber edges + chip).
- OHLC hover correctness (per-bar values + timeframe + change).
- Drawing menu alignment/spacing (left-aligned two-line popover).
- Hide/show drawings (master + per-drawing, both non-destructive).
- Broken chart-state transitions (seq guards on load + Kronos).
- Calculation bugs (OLS extracted + fixtures; fib seam).

P1 (core chart usability) — done in s19:
- Toolbar organization (replay/settings popovers, chart styles).
- Timeframes and chart styles (bars/area added).
- Indicator browser + favourites + templates.
- Full-screen workspace (view-scoped).
- Autosave controls (explicit switch).
- Replay (honest, leak-free).
- Forecast workflow integration (Forecaster → chart).

P2 (advanced TA) — partially:
- Additional drawing tools: Schiff pitchfork + Gann fan (s19); arcs/spirals/ellipse/circle/H&S still BLOCKED on LWC 4.2.3.
- Pattern recognition, harmonic, Elliott, S/R, MTF, scanners, seasonality, RS: IMPLEMENTED/PARTIAL as above.
P3 (broader research) — fundamental panels, heatmaps, comparison, model comparison, UI refinements: as above.

Blocked items (unchanged policy):
- Intraday/NEPSE official API (/api/nots/* 401) — no permitted source.
- Footprint/order-flow — needs tick data that is not collected.
- Tick charts — same block.