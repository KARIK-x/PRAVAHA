| Method | Path | Purpose | Class | Tests | Status |
|---|---|---|---|---|---|
| POST | `/api/agent/run` | Agent Run | read-only | agent, friend_access | TEST |
| GET | `/api/agent/tools` | Agent Tools | read-only | agent | TEST |
| POST | `/api/alerts/acknowledge` | Alerts Acknowledge | mutating | alerts, friend_access | TEST |
| DELETE | `/api/alerts/clear` | Alerts Clear | mutating | alerts | TEST |
| POST | `/api/alerts/evaluate` | Alerts Evaluate | read-only | alerts | TEST |
| GET | `/api/alerts/history` | Alerts History | read-only | alerts, friend_access | TEST |
| POST | `/api/analysis/run` | Analysis Run | read-only | catalog | TEST |
| POST | `/api/backtest` | Backtest | read-only | api, experiments | TEST |
| GET | `/api/bars/{symbol}` | Bars | read-only | analysis_window_api, api, candles_api, friend_access, gaps_breakouts, harmonic, index_consumer, patterns_stats_api, rs_timeframes, timeframe_elliott_api, trailing_stop, volume_profile | TEST |
| GET | `/api/bars/{symbol}/breakouts` | Breakouts Endpoint | read-only | analysis_window_api, api, candles_api, friend_access, gaps_breakouts, harmonic, index_consumer, patterns_stats_api, rs_timeframes, timeframe_elliott_api, trailing_stop, volume_profile | TEST |
| GET | `/api/bars/{symbol}/candles` | Candlestick Patterns | read-only | analysis_window_api, api, candles_api, friend_access, gaps_breakouts, harmonic, index_consumer, patterns_stats_api, rs_timeframes, timeframe_elliott_api, trailing_stop, volume_profile | TEST |
| GET | `/api/bars/{symbol}/elliott` | Elliott Aggregate | read-only | analysis_window_api, api, candles_api, friend_access, gaps_breakouts, harmonic, index_consumer, patterns_stats_api, rs_timeframes, timeframe_elliott_api, trailing_stop, volume_profile | TEST |
| GET | `/api/bars/{symbol}/fibonacci` | Fibonacci | read-only | analysis_window_api, api, candles_api, friend_access, gaps_breakouts, harmonic, index_consumer, patterns_stats_api, rs_timeframes, timeframe_elliott_api, trailing_stop, volume_profile | TEST |
| GET | `/api/bars/{symbol}/gaps` | Gaps Endpoint | read-only | analysis_window_api, api, candles_api, friend_access, gaps_breakouts, harmonic, index_consumer, patterns_stats_api, rs_timeframes, timeframe_elliott_api, trailing_stop, volume_profile | TEST |
| GET | `/api/bars/{symbol}/harmonic` | Harmonic Candidates | read-only | analysis_window_api, api, candles_api, friend_access, gaps_breakouts, harmonic, index_consumer, patterns_stats_api, rs_timeframes, timeframe_elliott_api, trailing_stop, volume_profile | TEST |
| GET | `/api/bars/{symbol}/indicator` | Indicator | read-only | analysis_window_api, api, candles_api, friend_access, gaps_breakouts, harmonic, index_consumer, patterns_stats_api, rs_timeframes, timeframe_elliott_api, trailing_stop, volume_profile | TEST |
| GET | `/api/bars/{symbol}/levels` | Levels | read-only | analysis_window_api, api, candles_api, friend_access, gaps_breakouts, harmonic, index_consumer, patterns_stats_api, rs_timeframes, timeframe_elliott_api, trailing_stop, volume_profile | TEST |
| GET | `/api/bars/{symbol}/monthly` | Monthly Aggregate | read-only | analysis_window_api, api, candles_api, friend_access, gaps_breakouts, harmonic, index_consumer, patterns_stats_api, rs_timeframes, timeframe_elliott_api, trailing_stop, volume_profile | TEST |
| GET | `/api/bars/{symbol}/patterns` | Chart Patterns | read-only | analysis_window_api, api, candles_api, friend_access, gaps_breakouts, harmonic, index_consumer, patterns_stats_api, rs_timeframes, timeframe_elliott_api, trailing_stop, volume_profile | TEST |
| GET | `/api/bars/{symbol}/relative-strength` | Relative Strength | read-only | analysis_window_api, api, candles_api, friend_access, gaps_breakouts, harmonic, index_consumer, patterns_stats_api, rs_timeframes, timeframe_elliott_api, trailing_stop, volume_profile | TEST |
| GET | `/api/bars/{symbol}/statistics` | Bar Statistics | read-only | analysis_window_api, api, candles_api, friend_access, gaps_breakouts, harmonic, index_consumer, patterns_stats_api, rs_timeframes, timeframe_elliott_api, trailing_stop, volume_profile | TEST |
| GET | `/api/bars/{symbol}/structure` | Structure | read-only | analysis_window_api, api, candles_api, friend_access, gaps_breakouts, harmonic, index_consumer, patterns_stats_api, rs_timeframes, timeframe_elliott_api, trailing_stop, volume_profile | TEST |
| GET | `/api/bars/{symbol}/swing-workbench` | Swing Workbench Route | read-only | analysis_window_api, api, candles_api, friend_access, gaps_breakouts, harmonic, index_consumer, patterns_stats_api, rs_timeframes, timeframe_elliott_api, trailing_stop, volume_profile | TEST |
| GET | `/api/bars/{symbol}/trailing-stop` | Trailing Stop Endpoint | read-only | analysis_window_api, api, candles_api, friend_access, gaps_breakouts, harmonic, index_consumer, patterns_stats_api, rs_timeframes, timeframe_elliott_api, trailing_stop, volume_profile | TEST |
| GET | `/api/bars/{symbol}/volume-profile` | Volume Profile Endpoint | read-only | analysis_window_api, api, candles_api, friend_access, gaps_breakouts, harmonic, index_consumer, patterns_stats_api, rs_timeframes, timeframe_elliott_api, trailing_stop, volume_profile | TEST |
| GET | `/api/bars/{symbol}/weekly` | Weekly Aggregate | read-only | analysis_window_api, api, candles_api, friend_access, gaps_breakouts, harmonic, index_consumer, patterns_stats_api, rs_timeframes, timeframe_elliott_api, trailing_stop, volume_profile | TEST |
| GET | `/api/breadth/history` | Breadth History Route | read-only | api | TEST |
| GET | `/api/catalog/summary` | Catalog Summary | read-only | catalog | TEST |
| GET | `/api/catalog/tool/{tool_id}` | Catalog Tool | read-only | catalog | TEST |
| GET | `/api/catalog/{kind}` | Catalog Kind | read-only | catalog | TEST |
| GET | `/api/collector/status` | Collector Status | read-only | api | TEST |
| GET | `/api/corporate-events` | Corporate Events List | read-only | — | NONE |
| GET | `/api/corporate-events/calendar` | Corporate Events Calendar | read-only | — | NONE |
| GET | `/api/corporate-events/coverage` | Corporate Events Coverage | read-only | — | NONE |
| POST | `/api/corporate-events/import` | Corporate Events Import | read-only | — | NONE |
| GET | `/api/dashboard` | Dashboard | read-only | api, audit_a_fixes | TEST |
| GET | `/api/experiments` | Experiments List | read-only | experiments | TEST |
| POST | `/api/experiments` | Experiments Save | mutating | experiments | TEST |
| GET | `/api/experiments/compare` | Experiments Compare | read-only | experiments | TEST |
| DELETE | `/api/experiments/{exp_id}` | Experiments Delete | mutating | experiments | TEST |
| GET | `/api/experiments/{exp_id}` | Experiments Get | read-only | experiments | TEST |
| GET | `/api/experiments/{exp_id}/export` | Experiments Export | read-only | experiments | TEST |
| POST | `/api/experiments/{exp_id}/reproduce` | Experiments Reproduce | read-only | experiments | TEST |
| POST | `/api/floorsheet/import` | Floorsheet Import Route | mutating | api | TEST |
| GET | `/api/floorsheet/sessions` | Floorsheet Session List | read-only | api | TEST |
| GET | `/api/floorsheet/summary` | Floorsheet Summary Route | read-only | api | TEST |
| GET | `/api/floorsheet/trend` | Floorsheet Trend Route | read-only | floorsheet | TEST |
| POST | `/api/forecast` | Forecast | read-only | api | TEST |
| POST | `/api/forecast/compare` | Forecast Compare | read-only | api | TEST |
| GET | `/api/forecast/models` | Forecast Models | read-only | api | TEST |
| POST | `/api/forecast/rolling` | Forecast Rolling | read-only | api | TEST |
| POST | `/api/fundamental/run` | Fundamental Run | read-only | catalog | TEST |
| GET | `/api/fundamentals/as-of` | Fundamentals As Of | read-only | phase_api | TEST |
| GET | `/api/fundamentals/compare` | Fundamentals Compare | read-only | fundamentals | TEST |
| GET | `/api/fundamentals/eps-rankings` | Fundamentals Eps Rankings | read-only | — | NONE |
| POST | `/api/fundamentals/import` | Fundamentals Import Endpoint | mutating | api, friend_access | TEST |
| GET | `/api/fundamentals/revisions` | Fundamentals Revisions | read-only | phase_api | TEST |
| GET | `/api/fundamentals/summary` | Fundamentals Summary Endpoint | read-only | api | TEST |
| GET | `/api/fundamentals/{symbol}` | Fundamentals For Symbol | read-only | api, friend_access, fundamentals, phase_api | TEST |
| GET | `/api/fundamentals/{symbol}/eps-growth` | Fundamentals Eps Growth | read-only | api, friend_access, fundamentals, phase_api | TEST |
| GET | `/api/fundamentals/{symbol}/historical-pe` | Fundamentals Historical Pe | read-only | api, friend_access, fundamentals, phase_api | TEST |
| GET | `/api/fundamentals/{symbol}/ratios` | Fundamentals Ratios Endpoint | read-only | api, friend_access, fundamentals, phase_api | TEST |
| GET | `/api/fundamentals/{symbol}/ttm-eps` | Fundamentals Ttm Eps | read-only | api, friend_access, fundamentals, phase_api | TEST |
| GET | `/api/gonepse/status` | Gonepse Status | read-only | api | TEST |
| GET | `/api/health` | Health | read-only | api | TEST |
| GET | `/api/ideas` | Ideas Catalogue | read-only | api | TEST |
| GET | `/api/ideas/{model_id}` | Ideas Run | read-only | api | TEST |
| GET | `/api/indicators` | Indicators | read-only | api | TEST |
| GET | `/api/indices` | Indices | read-only | friend_access, index_consumer, index_ohlc_history | TEST |
| GET | `/api/indices/{name}` | Index Series | read-only | friend_access, index_consumer, index_ohlc_history | TEST |
| GET | `/api/indices/{name}/ohlc` | Index Ohlc | read-only | friend_access, index_consumer, index_ohlc_history | TEST |
| GET | `/api/indices/{name}/structure` | Index Structure | read-only | friend_access, index_consumer, index_ohlc_history | TEST |
| GET | `/api/journal` | Journal Entries | read-only | api, audit_a_fixes, friend_access, journal | TEST |
| POST | `/api/journal` | Journal New | mutating | api, audit_a_fixes, friend_access, journal | TEST |
| GET | `/api/journal/stats` | Journal Statistics | read-only | api, audit_a_fixes | TEST |
| DELETE | `/api/journal/{entry_id}` | Journal Delete Entry | mutating | api, audit_a_fixes, friend_access, journal | TEST |
| GET | `/api/journal/{entry_id}` | Journal One | read-only | api, audit_a_fixes, friend_access, journal | TEST |
| PATCH | `/api/journal/{entry_id}` | Journal Patch | mutating | api, audit_a_fixes, friend_access, journal | TEST |
| GET | `/api/journal/{entry_id}/grade` | Journal Grade Entry | read-only | api, audit_a_fixes, friend_access, journal | TEST |
| POST | `/api/journal/{entry_id}/reflect` | Journal Reflect Entry | read-only | api, audit_a_fixes, friend_access, journal | TEST |
| POST | `/api/kronos/evaluate` | Kronos Evaluate | read-only | api | TEST |
| GET | `/api/kronos/experiments` | Kronos Experiments | read-only | api | TEST |
| DELETE | `/api/kronos/experiments/{exp_id}` | Kronos Experiment Delete | mutating | api | TEST |
| POST | `/api/kronos/forecast` | Kronos Forecast | read-only | api | TEST |
| GET | `/api/kronos/status` | Kronos Status | read-only | api | TEST |
| POST | `/api/kronos/unload` | Kronos Unload | read-only | api | TEST |
| GET | `/api/live/market` | Live Market | read-only | api | TEST |
| GET | `/api/live/quotes` | Live Quotes | read-only | api | TEST |
| GET | `/api/live/status` | Live Status | read-only | api | TEST |
| POST | `/api/market-intelligence/collect` | Market Intelligence Collect | read-only | — | NONE |
| GET | `/api/market-intelligence/health` | Market Intelligence Health | read-only | — | NONE |
| POST | `/api/market-intelligence/import-csv` | Market Intelligence Import Csv | read-only | — | NONE |
| POST | `/api/market-intelligence/import-sources` | Market Intelligence Import Sources | read-only | — | NONE |
| GET | `/api/market-intelligence/source-health` | Market Intelligence Source Health | read-only | — | NONE |
| GET | `/api/market-intelligence/sources` | Market Intelligence Sources | read-only | — | NONE |
| GET | `/api/market/dashboard` | Market Dashboard | read-only | api | TEST |
| GET | `/api/market/ribbon` | Market Ribbon | read-only | api | TEST |
| POST | `/api/news/import` | News Import Route | mutating | api | TEST |
| GET | `/api/news/summary` | News Summary Route | read-only | api | TEST |
| POST | `/api/planning` | Planning | read-only | api, planning | TEST |
| POST | `/api/planning/grade` | Planning Grade | read-only | api | TEST |
| GET | `/api/portfolio` | Portfolio | read-only | api, friend_access, risk | TEST |
| GET | `/api/portfolio/cash-flow` | Portfolio Cash Flow | read-only | api | TEST |
| POST | `/api/portfolio/manual` | Portfolio Manual | mutating | api | TEST |
| DELETE | `/api/portfolio/manual/{symbol}` | Portfolio Delete Manual | mutating | api | TEST |
| GET | `/api/portfolio/risk` | Portfolio Risk | read-only | risk | TEST |
| GET | `/api/portfolio/transactions` | Portfolio Transactions | read-only | api | TEST |
| POST | `/api/portfolio/transactions` | Portfolio Add Transaction | mutating | api | TEST |
| DELETE | `/api/portfolio/transactions/{tx_id}` | Portfolio Delete Transaction | mutating | api | TEST |
| GET | `/api/quality` | Quality | read-only | api | TEST |
| GET | `/api/query/history` | Query History | read-only | phase_api | TEST |
| POST | `/api/query/run` | Query Run | read-only | phase_api | TEST |
| GET | `/api/quotes` | Quotes | read-only | api, friend_access, quotes_freshness_regression | TEST |
| POST | `/api/rank` | Rank | read-only | api, index_consumer | TEST |
| GET | `/api/reconciliation/datasets` | Reconciliation Datasets | read-only | phase_api | TEST |
| GET | `/api/reconciliation/history` | Reconciliation History | read-only | phase_api | TEST |
| GET | `/api/reconciliation/profile` | Reconciliation Profile | read-only | phase_api | TEST |
| POST | `/api/reconciliation/resolve` | Reconciliation Resolve | read-only | phase_api | TEST |
| POST | `/api/reconciliation/run` | Reconciliation Run | read-only | phase_api | TEST |
| GET | `/api/regime` | Regime | read-only | regime | TEST |
| GET | `/api/regime/history` | Regime History | read-only | regime | TEST |
| GET | `/api/research-desk/evidence` | Research Evidence | read-only | phase_api | TEST |
| GET | `/api/research-desk/history` | Research History | read-only | phase_api | TEST |
| POST | `/api/research-desk/review` | Research Review | read-only | phase_api | TEST |
| POST | `/api/research-desk/run` | Research Run | read-only | phase_api | TEST |
| POST | `/api/research/ask` | Research Ask | read-only | agent, api | TEST |
| GET | `/api/research/topics` | Research Topics | read-only | api | TEST |
| GET | `/api/research/workspace/{symbol}` | Research Workspace | read-only | workspace | TEST |
| GET | `/api/research/{symbol}` | Research Symbol | read-only | agent, api, friend_access, workspace | TEST |
| POST | `/api/sastoshare/backtest-vs-hold` | Sastoshare Backtest Vs Hold | read-only | sastoshare | TEST |
| GET | `/api/sastoshare/dividends` | Sastoshare Dividends | read-only | sastoshare | TEST |
| GET | `/api/sastoshare/movers` | Sastoshare Movers | read-only | sastoshare | TEST |
| GET | `/api/sastoshare/pulse` | Sastoshare Pulse | read-only | sastoshare | TEST |
| GET | `/api/sastoshare/risk/{symbol}` | Sastoshare Risk | read-only | sastoshare | TEST |
| GET | `/api/sastoshare/rotation` | Sastoshare Rotation | read-only | sastoshare | TEST |
| GET | `/api/sastoshare/valuation-history/{symbol}` | Sastoshare Valuation History | read-only | sastoshare | TEST |
| GET | `/api/sastoshare/valuation/{symbol}` | Sastoshare Valuation | read-only | sastoshare | TEST |
| GET | `/api/sastoshare/volatility/{symbol}` | Sastoshare Volatility | read-only | sastoshare | TEST |
| POST | `/api/screen` | Screen | read-only | api, friend_access, screens | TEST |
| GET | `/api/screen/export.csv` | Screen Export | read-only | api | TEST |
| GET | `/api/screen/export.pdf` | Screen Export Pdf | read-only | — | NONE |
| GET | `/api/screen/export.xlsx` | Screen Export Xlsx | read-only | — | NONE |
| GET | `/api/screen/presets` | Screen Presets | read-only | api | TEST |
| GET | `/api/screens` | Screens List | read-only | friend_access, screens | TEST |
| POST | `/api/screens` | Screens Save | mutating | friend_access, screens | TEST |
| POST | `/api/screens/propose` | Screens Propose | read-only | friend_access, screens | TEST |
| DELETE | `/api/screens/{screen_id}` | Screens Delete | mutating | friend_access, screens | TEST |
| GET | `/api/screens/{screen_id}` | Screens Get | read-only | friend_access, screens | TEST |
| PATCH | `/api/screens/{screen_id}` | Screens Patch | mutating | friend_access, screens | TEST |
| POST | `/api/screens/{screen_id}/duplicate` | Screens Duplicate | read-only | friend_access, screens | TEST |
| GET | `/api/seasonality/{symbol}` | Seasonality Route | read-only | api | TEST |
| GET | `/api/securities` | Securities | read-only | api, audit_a_fixes | TEST |
| GET | `/api/snapshots` | Snapshots List | read-only | phase_api | TEST |
| POST | `/api/snapshots` | Snapshots Create | read-only | phase_api | TEST |
| POST | `/api/snapshots/capture` | Snapshots Capture | read-only | phase_api | TEST |
| GET | `/api/snapshots/compare` | Snapshots Compare | read-only | phase_api | TEST |
| GET | `/api/snapshots/{snapshot_id}` | Snapshots Get | read-only | phase_api | TEST |
| POST | `/api/snapshots/{snapshot_id}/rerun` | Snapshots Rerun | read-only | phase_api | TEST |
| GET | `/api/sources` | Sources | read-only | api | TEST |
| GET | `/api/stats/correlation` | Stats Correlation | read-only | patterns_stats_api | TEST |
| GET | `/api/status` | Status | read-only | api, market_store_concurrency | TEST |
| GET | `/api/strategies` | Strategies | read-only | api | TEST |
| GET | `/api/templates` | Templates | read-only | friend_access, templates | TEST |
| POST | `/api/walk-forward` | Walk Forward Endpoint | read-only | api | TEST |
| GET | `/api/watchlists` | Watchlists List | read-only | watchlists | TEST |
| POST | `/api/watchlists` | Watchlists Create | mutating | watchlists | TEST |
| DELETE | `/api/watchlists/{name}` | Watchlists Delete | mutating | watchlists | TEST |
| GET | `/api/watchlists/{name}` | Watchlists Get | read-only | watchlists | TEST |
| PATCH | `/api/watchlists/{name}` | Watchlists Patch | mutating | watchlists | TEST |
| GET | `/api/written-pdf/records` | Written Pdf Records | read-only | api | TEST |
| POST | `/api/written-pdf/review` | Written Pdf Review | mutating | api, friend_access | TEST |
| GET | `/api/written-pdf/summary` | Written Pdf Summary | read-only | api | TEST |
