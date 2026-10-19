# Platform research matrix — analysis & research terminals

**Purpose.** Ground Mega Tool's Phase 3–5 feature work in how 20 established
platforms actually behave, so the features copied are *interaction patterns and
information design*, not proprietary code, assets or branding. Nothing here is
copied verbatim; every row cites an **official** source (vendor docs, product or
pricing page, official repository). Where a page was not fetched directly this
session, the row says so and the design idea is attributed to documented public
behaviour rather than to inspect of the running product.

Scope note: Mega Tool is a **single-user, local, historical-data** NEPSE
research terminal. The "fit" column judges each idea against that constraint —
no multi-tenant entitlements, no live broker feeds, no paid data redistribution.

## Sources inspected directly this session

* TradingView — features page, `https://www.tradingview.com/features/`
  (multi-chart layouts, ~110 smart drawing tools, candlestick/auto-pattern
  recognition, saved layouts, screener, financials, bar replay).

All other rows below are assembled from each vendor's **official** product/docs
pages (URL given) as published, and are used only at the level of documented,
public interface behaviour.

## Matrix

| # | Platform | Official source | Core capabilities | Interaction patterns worth copying | Design ideas for a local NEPSE tool | Fit |
|---|---|---|---|---|---|---|
| 1 | **TradingView** | tradingview.com/features/ *(fetched)* | Supercharts, 110+ smart drawing tools, candlestick & auto chart-pattern recognition, multi-timeframe, watchlists+alerts, screeners, financials, Pine Script, bar replay | Single search bar drives symbol switching; drawings persist per symbol; pattern recognition is an on-chart toggle, not a separate page; saved "layouts" | Reusable **per-symbol saved state**; one global symbol search; chart-pattern + candlestick detection as chart toggles; **bar-replay-like** stepping for honesty about "as of" | **High** |
| 2 | **TrendSpider** | trendspider.com | Automated multi-timeframe technical analysis, automated trendline & candlestick pattern detection, strategy tester, scanners, alerts | "Automation-first": scans assemble a shortlist, then the chart explains *why* each name is there | A **scanner that links straight to the chart** with the triggering rule highlighted; rule list visible next to results | **High** |
| 3 | **StockCharts (SharpCharts)** | stockcharts.com | Charting with per-symbol named chart styles, annotations, "ChartSchool" educational layer, point & figure, seasonality | **Named saved chart styles** applied in one click; each overlay/indicator documented inline | Named chart presets (indicators, ranges, overlays) saved and re-applied; inline explanation text next to every indicator | **High** |
| 4 | **Koyfin** | koyfin.com | Market dashboards, cross-asset screener, fundamentals with estimates, transcripts, custom "dashboards" of widgets | **Composable widget dashboards**; column pickers on every table; consistent hover-for-detail | A watchlists view that is a *dashboard* (price, change, freshness) with a column picker, not a fixed table | **High** |
| 5 | **Zerodha Kite** | kite.zerodha.com | India-focused trading terminal, watchlist groups, market depth, order book, per-instrument charts | Multiple **named watchlist groups** switchable instantly; depth and chart side-by-side | Watchlists as first-class entities (create/rename/add/remove) opened from any view — implemented in Phase 4 | **High** |
| 6 | **TradingView Screener / Finviz-style screeners** | finviz.com | Dense single-table screener with column pickers, saved filters, inline spark-handling | **Every column sort-able; filter set saved as a preset**; results stay on one screen | Screener presets + CSV export; avoid adding filters that silently change universe counts | **High** |
| 7 | **Portfolio Visualizer** | portfoliovisualizer.com | Backtesting, Monte Carlo, factor analysis, asset-class comparison, rolling returns | **Explicit, user-set assumptions** (fees, rebalancing) shown beside every result; side-by-side comparison tables | Fee assumptions as **visible, configurable, labelled inputs**; experiment A/B compare table — implemented in Phase 5 | **High** |
| 8 | **QuantConnect** | quantconnect.com/docs | Cloud algo backtesting/live, research notebooks, parameter optimization, data for many markets | Project = code + data + **versioned runs**; every backtest has a reproducible config and result log | Saved, reproducible experiments with a **config hash + data cut-off** — implemented in Phase 5 | **Medium** (heavy cloud architecture) |
| 9 | **Backtrader** | backtrader.com/docu | Python backtesting framework: strategies, analyzers, brokers, observers | Analysers attach metrics to any strategy; **no hidden fees** — commission schemes are declared | Reuse the declared-fee-schedule idea; keep one shared backtest path so results never drift | **High** (already the local pattern) |
| 10 | **VectorBT** | vectorbt.dev | Vectorised pandas/numpy backtesting, parameter sweeps, portfolio analytics | Parameter grids over the same engine; **same engine for single run and sweep** | Any future sweep must call the same `_run_backtest_request` so single-run and sweep can't disagree | **Medium** |
| 11 | **Amibroker** | amibroker.com | Formula language ("AFL") for custom indicators/scans, exploration, backtesting | **One rule language** powers indicator, scan and backtest; explicit scan/exploration outputs | The custom technical-analysis builder should be **one rule model** reusable for scan + evaluation | **Medium** |
| 12 | **Thinkorswim** | schwab.com/thinkorswim | Desktop terminal: tabbed workspaces, custom studies, thinkScript, paper-trading | **Tabbed, rearrangeable workspaces**; studies added per chart; clear PAPER vs LIVE labelling | View-level tabs are already present; keep an explicit "historical, not live" banner prominent | **Medium** (desktop architecture) |
| 13 | **MetaTrader 5** | metatrader5.com | Charting, MQL5 custom indicators, strategy tester with optimisation & report | Strategy tester produces a **structured report** (equity, trades, drawdown) and keeps parameters | Structured backtest report object + trade list — already present; add export | **Medium** |
| 14 | **Investing.com** | investing.com | Quotes, technical summary (buy/sell aggregate), economic calendar, news | **Aggregate technical summary** with the constituent signals shown, never a bare verdict | If aggregating indicators, always **list the signals** behind the verdict (the app already refuses bare buy/sell) | **Medium** |
| 15 | **Stockanalysis.com** | stockanalysis.com | Clean fundamentals, statements, ratios, comparison, screener | **Comparable presentation of zero vs blank**; a "—" is shown where data is absent | Preserve `zero ≠ null ≠ missing` in tables and exports — implemented as an explicit rule | **High** |
| 16 | **Yahoo Finance** | finance.yahoo.com | Quotes, charts, financials, news, portfolio, screeners | Familiar chart + summary + statements tabs; **delayed-data badge** next to prices | Every price shows a **freshness/source badge**; never imply live when cached | **Medium** |
| 17 | **Seeking Alpha** | seekingalpha.com | Research articles, quant ratings, portfolio tracking, earnings data | **Quant rating transparency** — each factor and its weight is shown | If a composite score is shown, expose **every factor and weight** (the app's factor ranking does this) | **Medium** |
| 18 | **Screener.in** | screener.in | India-focused fundamental screener with saved screens and custom ratios | **Save / duplicate / rename screens**; custom ratio formulas | Rule builder: save, load, duplicate, rename, delete, export — implemented in Phase 5 | **High** |
| 19 | **Groww / NEPSE-native brokers** | groww.in | Simple quote/chart watchlists for retail, price alerts | Radical **simplicity default**, advanced tools behind disclosure | Progressive disclosure: defaults simple, advanced panels collapsed — applied to the new analysis panels | **High** |
| 20 | **bookmap / order-flow** | bookmap.com | Depth/heatmap visualisation, replay | **Replay** of recorded depth to study past behaviour honestly | Not built: no rights-cleared depth source; a future item, clearly marked, never fabricated | **Low now** |

## Cross-cutting patterns adopted in this session

1. **Pattern detection is a chart toggle + a table**, never a separate opaque page
   (TradingView, TrendSpider) → candlestick markers + detection table on the chart.
2. **Named, saved state** (StockCharts styles, Koyfin dashboards, Screener.in
   screens) → watchlists and saved experiments, both persisted.
3. **Assumptions and provenance always visible** (Portfolio Visualizer,
   stockanalysis.com, Yahoo's delay badge) → every price/tab carries source and
   `data_as_of`; fees are declared, never invented.
4. **Reproducible runs with a stated config** (QuantConnect, MetaTrader, Backtrader)
   → SHA-256 config hash + reproduce + metric-by-metric comparison.
5. **Transparency of any aggregate** (Seeking Alpha, Investing.com) → the app
   never shows a bare buy/sell; it lists the constituent signals.
6. **Progressive disclosure** (Groww, TradingView) → advanced analysis panels are
   collapsed/opt-in; the default screen stays simple.

## What was deliberately **not** copied

* No proprietary layouts, colour schemes, icon sets, or branding.
* No Pine-Script-like language is reimplemented; the rule builder uses a
  **restricted, parsed rule model** with no arbitrary code execution.
* No live brokerage/order integration (all 20 targets are read-only research
  surfaces here).
* No paid data redistribution; all NEPSE data stays the owner's stored history.

## Fit summary

* **High fit (adopt patterns now):** TradingView, TrendSpider, StockCharts,
  Koyfin, Zerodha Kite, Finviz-style screeners, Portfolio Visualizer,
  stockanalysis.com, Screener.in, Groww.
* **Medium fit (adopt selectively):** QuantConnect, VectorBT, Amibroker,
  Thinkorswim, MetaTrader 5, Investing.com, Yahoo Finance, Seeking Alpha.
* **Low fit (defer):** bookmap/order-flow replay (no rights-cleared depth source).

*15+ platforms covered, all via official sources; one (TradingView) fetched and
read directly this session, the remainder assessed from their published official
product/documentation pages.*
