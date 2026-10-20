/* PRAVAHA — central feature registry.
 *
 * ONE structured source of truth for what the application can actually do. It
 * powers universal search (Cmd/Ctrl+K), navigation and command suggestions, so
 * a keyword list is never duplicated across unrelated files.
 *
 * Loaded as a classic script BEFORE app.js and exposed as
 * `window.PRAVAHA_FEATURES`. It is deliberately dependency-free so it can be
 * unit-tested with plain Node (tests/test_features_registry.mjs).
 *
 * HONESTY RULES
 *  - `available:false` entries are NEVER presented as usable; they carry a
 *    `reason` and are hidden until the user searches for them.
 *  - Every `view` must be a real view id from web/static/index.html.
 *  - A `run` is described declaratively (`view` + `tab` + optional `preset`),
 *    so this file never holds DOM code.
 *
 * Entry shape:
 *   {
 *     id:        unique stable id
 *     name:      displayed name
 *     kind:      view | tool | scanner | model | action | research
 *     category:  grouping label shown in the palette
 *     desc:      one-line description (shown under the name)
 *     view:      target view id (index.html `#view-<id>`)
 *     tab:       optional sub-tab id (new/kimi/sasto share)
 *     preset:    optional key passed to the destination (scanner preset, model id…)
 *     symbol:    true when the destination consumes the current symbol
 *     keywords:  extra search terms (aliases, synonyms, Nepali-market jargon)
 *     available: default true
 *     reason:    required when available is false
 *   }
 */
(function () {
  "use strict";

  var V = {
    overview: "overview", watchlists: "watchlists", charts: "charts",
    screener: "screener", ideas: "ideas", tracing: "tracing",
    portfolio: "portfolio", journal: "journal", research: "research",
    marketintel: "marketintel", fundamentals: "fundamentals",
    floorsheet: "floorsheet", pdf: "pdf", breadth: "breadth",
    sea: "sea", swingw: "swingw", backtest: "backtest",
    workshop: "workshop", templates: "templates", forecaster: "forecaster",
    kronos: "kronos", data: "data", kimi: "kimi", sastoshare: "sastoshare",
    nu: "nu", nse: "nse", nprof: "nprof", neps: "neps",
    nepsh: "nepsh", nttm: "nttm", ncmp: "ncmp", nscr: "nscr",
    nelig: "nelig", ncov: "ncov",
  };

  // Analytics-layer ids that the Analysis drawer exposes on the chart.
  var LAYER = {
    sr: "Support & resistance", fib: "Fibonacci", profile: "Volume profile",
    candles: "Candlestick patterns", patterns: "Chart patterns",
    elliott: "Elliott Wave", harmonic: "Harmonic patterns",
    structure: "Market structure & liquidity", trend: "Trend strength & regime",
    momentum: "Momentum, divergence & relative strength",
    volatility: "Volatility & breakout", volume: "Volume & accumulation",
    gap: "Gap & opening-price analysis", regime: "Market regime & rotation",
    relative: "Relative performance & leaders/laggards",
    micro: "Market microstructure & liquidity proxies",
    distribution: "Price distribution & value areas",
    event: "Event & corporate-action analysis",
    strategy: "Strategy & signal validation",
  };

  var F = [];
  function add(e) { F.push(e); }

  /* ---------------------------------------------------------------- views */
  [
    ["overview", "Dashboard", "Market overview, barometer, breadth, movers", "dashboard home market overview snapshot"],
    ["charts", "Charting", "Candles, indicators, drawing tools, analysis", "chart candles technical analysis charting"],
    ["watchlists", "Watchlists", "Saved symbol lists", "watchlist favourites saved symbols"],
    ["screener", "More Scanners", "Composable scanner / rule builder", "scanner screener screen filter rules"],
    ["ideas", "Ideas", "Preset investment-model screens", "ideas models frameworks stock ideas"],
    ["tracing", "Tracing", "Indicator-alert history", "alerts tracing signals history"],
    ["portfolio", "Portfolios", "Holdings, transactions, risk", "portfolio holdings positions pnl"],
    ["journal", "Journal", "Trade journal, planning, grading", "journal trades diary plan"],
    ["research", "Research", "Research workspace and reports", "research report workbench"],
    ["marketintel", "Market Intelligence", "News/social source registry and browser", "news market intelligence sentiment"],
    ["fundamentals", "Fundamentals", "Import, compare, ratios", "fundamentals financials statements"],
    ["floorsheet", "Floor Sheet", "Broker floorsheet history", "floorsheet broker transaction"],
    ["pdf", "PDF Journal", "Transcribed handwritten journal records", "pdf journal written records"],
    ["breadth", "Breadth History", "Advance/decline and %-above-MA history", "breadth advance decline participation"],
    ["sea", "Seasonality", "Month/day-of-week seasonality", "seasonality monthly calendar"],
    ["swingw", "Swing Bench", "Swing structure, S/R, invalidation", "swing support resistance structure"],
    ["backtest", "My Algorithms", "Backtesting workspace", "backtest strategy algorithms"],
    ["workshop", "Algorithm Workshop", "Indicator workshop and templates", "workshop templates"],
    ["templates", "Templates", "Saved indicator templates", "templates saved"],
    ["forecaster", "AI Forecaster", "Transparent forecasting models", "forecast prediction model"],
    ["kronos", "Kronos AI", "Kronos foundation-model workspace", "kronos ai foundation model"],
    ["data", "Data & Quality", "Coverage, provenance, source health", "data quality coverage provenance sources"],
    ["kimi", "KIMI Research", "Research workspace (18 tabs)", "kimi research workspace"],
    ["sastoshare", "Sasto Share", "Market pulse, movers, valuation, risk, rotation", "sasto share market pulse"],
    ["nu", "Company Universe", "All listed companies", "company universe symbols list"],
    ["nse", "Sector Explorer", "Sector classifications and members", "sector explorer classification"],
    ["nprof", "Company Profiles", "Per-company research view", "company profile"],
    ["neps", "EPS Rankings", "Rank companies by EPS", "eps ranking earnings"],
    ["nepsh", "EPS History & Growth", "Historical EPS and growth", "eps history growth"],
    ["nttm", "TTM EPS Analysis", "Trailing-twelve-month EPS", "ttm eps trailing"],
    ["ncmp", "Fundamentals Comparison", "Compare fundamentals side by side", "fundamentals comparison compare"],
    ["nscr", "Financial Screener", "Screen on fundamentals", "financial screener"],
    ["nelig", "Margin Eligibility", "Margin-eligible securities", "margin eligibility"],
    ["ncov", "Data Coverage", "Per-symbol data coverage", "coverage data completeness"],
  ].forEach(function (r) {
    add({ id: "view:" + r[0], name: r[1], kind: "view", category: "Views",
      desc: r[2], view: r[0], keywords: r[3] });
  });

  /* ------------------------------------------------- sub-tab destinations */
  [["nu", "Company Universe"], ["nse", "Sector Explorer"], ["nprof", "Company Profiles"],
   ["neps", "EPS Rankings"], ["nepsh", "EPS History & Growth"], ["nttm", "TTM EPS Analysis"],
   ["ncmp", "Fundamentals Comparison"], ["nscr", "Financial Screener"],
   ["nelig", "Margin Eligibility"], ["ncov", "Data Coverage"]].forEach(function (r) {
    add({ id: "tab:new:" + r[0], name: r[1], kind: "tool", category: "Fundamentals",
      desc: "Open the " + r[1] + " tab", view: "new", tab: r[0], keywords: r[1].toLowerCase() });
  });

  /* ----------------------------------------------------------- Sasto Share */
  [["pulse", "ssmovers", "Market Pulse", "Market breadth, participation, PE context", "market pulse breadth"],
   ["movers", "ssmovers", "Movers & Sparklines", "Gainers, losers and turnover leaders", "movers gainers losers sparkline"],
   ["valuation", "ssvaluation", "Valuation", "PE/PB/Graham-style valuation models", "valuation pe pb graham"],
   ["risk", "ssrisk", "Risk & Volatility", "Support/resistance, risk-reward, volatility", "risk volatility drawdown"],
   ["rotation", "ssrotation", "Sector Rotation", "Relative-strength rotation across sectors", "sector rotation relative strength"],
   ["dividends", "ssdividends", "Dividends", "Dividend history and yield (data-dependent)", "dividends yield payout"],
   ["strategy", "ssstrategy", "Strategy vs Buy & Hold", "Strategy comparison against a baseline", "strategy buy hold backtest"],
  ].forEach(function (r) {
    add({ id: "sasto:" + r[0], name: r[2], kind: "tool", category: "Sasto Share",
      desc: r[3], view: "sastoshare", tab: r[0], keywords: r[4] });
  });

  /* ------------------------------------------------------- research commands */
  [
    ["dividend-analysis", "Dividend analysis", "ssdividends", "dividends dividend yield payout income"],
    ["eps-history", "EPS history", "nepsh", "eps earnings history per share"],
    ["eps-growth", "EPS growth", "nepsh", "eps growth earnings growth"],
    ["eps-rankings", "EPS rankings", "neps", "eps ranking best earnings"],
    ["ttm-eps", "TTM EPS analysis", "nttm", "ttm trailing twelve month eps"],
    ["book-value", "Book-value analysis", "ssvaluation", "book value pb price to book bargain"],
    ["graham", "Graham valuation", "ideas", "graham defensive intrinsic value"],
    ["lynch", "Peter Lynch valuation", "ideas", "lynch peg growth fair value"],
    ["multibagger", "Multibagger screen", "ideas", "multibagger compounder"],
    ["canslim", "CANSLIM screen", "ideas", "canslim oneil growth momentum"],
    ["magic-formula", "Magic Formula screen", "ideas", "magic formula greenblatt roc earnings yield"],
    ["piotroski", "Piotroski F-Score", "ideas", "piotroski f score quality fundamentals"],
    ["altman", "Altman Z-Score", "ideas", "altman z score distress bankruptcy risk"],
    ["pb-bargain", "P/B bargain screen", "ideas", "pb bargain cheap book"],
    ["low-52w", "Near 52-week low", "ideas", "52 week low near low"],
    ["strategy-vs-hold", "Strategy vs Buy & Hold", "ssstrategy", "strategy versus buy and hold benchmark"],
    ["seasonality", "Seasonality", "sea", "seasonality monthly calendar month of year"],
    ["holiday-effect", "Holiday effect", "sea", "holiday effect festival pre post event window"],
    ["sector-rotation", "Sector rotation", "ssrotation", "sector rotation leadership relative"],
    ["relative-strength", "Relative strength", "screener", "relative strength rs rating vs index"],
    ["market-breadth", "Market breadth", "breadth", "breadth advance decline participation"],
    ["elliott-wave", "Elliott Wave", "charts", "elliott wave impulse correction", "elliott"],
    ["fib-retracement", "Fibonacci retracement", "charts", "fibonacci retracement fib", "fib"],
    ["fib-extension", "Fibonacci extension", "charts", "fibonacci extension projection fib", "fib"],
    ["chart-patterns", "Chart patterns", "charts", "chart patterns head shoulders triangle flag", "patterns"],
    ["harmonic-patterns", "Harmonic patterns", "charts", "harmonic gartley bat butterfly crab", "harmonic"],
    ["candlestick-patterns", "Candlestick patterns", "charts", "candlestick hammer engulfing doji", "candles"],
    ["volume-profile", "Volume profile", "charts", "volume profile poc value area", "profile"],
    ["trade-planner", "Trade planner", "journal", "trade planner position size risk reward stop"],
    ["trade-journal", "Trade journal", "journal", "journal trades review"],
    ["portfolio-risk", "Portfolio risk", "portfolio", "portfolio risk exposure concentration"],
    ["backtesting", "Backtesting", "backtest", "backtest strategy equity curve"],
    ["corporate-events", "Corporate events", "kimi", "corporate events dividends bonus rights agm"],
    ["data-quality", "Data quality & provenance", "data", "data quality provenance freshness coverage"],
  ].forEach(function (r) {
    var e = { id: "cmd:" + r[0], name: r[1], kind: "research", category: "Research",
      desc: "Open " + r[1], view: r[2], keywords: r[3], symbol: true };
    if (r[4]) e.layer = r[4];             // analysis-layer toggle on the chart
    add(e);
  });

  /* ---------------------------------------------------------------- scanners
   * `preset` MUST be a real key from megatool/scanner.py PRESET_SCREENS — the
   * palette applies it to the Screener's preset <select>. Where no preset
   * exists the entry stays available but says so, instead of pretending. */
  [
    ["mfi_oversold", "Money-flow oversold", "money flow oversold mfi cmf accumulation"],
    ["low_volatility", "Low volatility", "low volatility calm stable quiet"],
    ["liquid_turnover", "Liquid by turnover", "liquidity liquid turnover tradable volume"],
    ["unusual_volume_50", "Unusual volume", "unusual volume spike relative"],
    ["breakout_with_volume", "Volume breakout", "volume breakout expansion breakout"],
    ["biggest_volume_20d", "Biggest volume (20d)", "high volume turnover biggest"],
    ["oversold_rsi", "Oversold RSI", "rsi oversold 30"],
    ["rsi_overbought", "Overbought RSI", "rsi overbought 70"],
    ["macd_bullish_cross", "MACD bullish crossover", "macd bullish cross golden"],
    ["macd_bearish_cross", "MACD bearish crossover", "macd bearish cross death"],
    ["strong_trend_adx", "Trend strength (ADX)", "trend continuation adx strong"],
    ["accumulation_20d", "Accumulation candidates", "accumulation ad line"],
    ["distribution_20d", "Distribution candidates", "distribution selling ad line"],
    ["obv_accumulation_20d", "OBV accumulation", "obv on balance volume accumulation"],
    ["near_52w_high", "Near 52-week high", "52 week high breakout"],
    ["near_52w_low", "Near 52-week low", "52 week low"],
    ["momentum_20d", "Momentum (20d)", "momentum relative strength leaders"],
    ["volume_dryup", "Volume dry-up", "volume dry up quiet"],
    ["volume_surge", "Volume surge", "volume surge spike"],
    ["volume_climax", "Volume climax", "volume climax exhaustion"],
    ["pocket_pivot", "Pocket pivot", "pocket pivot accumulation"],
    ["bollinger_squeeze", "Bollinger squeeze", "bollinger squeeze volatility contraction"],
    ["bollinger_lower_band", "At lower Bollinger band", "bollinger lower band oversold"],
    ["bollinger_upper_band", "At upper Bollinger band", "bollinger upper band"],
    ["donchian_breakout_up", "Donchian breakout", "donchian breakout channel"],
    ["stochastic_oversold", "Stochastic oversold", "stochastic oversold"],
    ["stochastic_overbought", "Stochastic overbought", "stochastic overbought"],
    ["above_sma20", "Above 20-day SMA", "above sma moving average participation"],
    ["above_sma50", "Above 50-day SMA", "above sma moving average participation"],
    ["above_sma200", "Above 200-day SMA", "above sma moving average participation"],
    ["sma5_above_sma20", "SMA5 above SMA20", "moving average crossover sma"],
  ].forEach(function (r) {
    add({ id: "scanner:" + r[0], name: r[1], kind: "scanner", category: "Scanners",
      desc: "Open the Screener with this saved preset", view: "screener",
      preset: r[0], keywords: r[2] });
  });

  // Commands the user expects but that this build has no saved preset for.
  // Available (the Screener can build them from metrics) but explicitly honest.
  [
    ["top-gainers", "Top gainers", "gainers up top"],
    ["top-losers", "Top losers", "losers down"],
    ["near-support", "Near support", "support near bounce"],
    ["near-resistance", "Near resistance", "resistance near"],
    ["price-volume-divergence", "Price-volume divergence", "divergence price volume"],
    ["high-relative-strength", "High relative strength", "relative strength leaders outperform"],
  ].forEach(function (r) {
    add({ id: "scanner-custom:" + r[0], name: r[1], kind: "scanner", category: "Scanners",
      desc: "No saved preset — open the Screener and build it from metrics",
      view: "screener", keywords: r[2] });
  });

  /* ------------------------------------------------------- floor-sheet views */
  [
    ["top-buyers", "Top buyers", "buyer buyers net buy accumulation broker"],
    ["top-sellers", "Top sellers", "seller sellers net sell distribution broker"],
    ["buyer-seller-pairs", "Buyer-seller pairs", "buyer seller pair counterparty matched"],
    ["broker-activity", "Broker activity", "broker member code activity"],
    ["transaction-analysis", "Transaction analysis", "transaction trades quantity turnover"],
  ].forEach(function (r) {
    add({ id: "floor:" + r[0], name: r[1], kind: "tool", category: "Floor Sheet",
      desc: "Open the Floor Sheet workspace", view: "floorsheet", keywords: r[2] });
  });

  /* ------------------------------------------------------------ known gaps */
  [
    ["multi-timeframe", "Multi-timeframe trend consensus", "Only the daily timeframe is stored; weekly/monthly consensus is not computed"],
    ["live-feed", "Live NEPSE feed", "The official feed returns 401 without credentials; every price shown is a stored close"],
    ["shareholding", "Shareholder watchlist", "No shareholding-register source in this build"],
    ["order-book", "Order book / market depth", "No intraday order-book data in the stored dataset"],
    ["multi-chart", "Multi-chart layout", "This build draws one chart per view"],
    ["trading-simulator", "Trading simulator", "Not implemented"],
    ["pine-script", "Pine Script", "No Pine engine; a sandboxed custom-formula DSL is the closest built feature"],
    ["chart-calendar", "Chart calendar (events/earnings)", "No events/earnings calendar source"],
    ["chart-share", "Chart image sharing", "Chart image sharing is not built"],
    ["footprint", "Footprint / intraday mode", "No intraday tick data in the stored dataset"],
    ["mtf-scan", "MTF scan", "Multi-timeframe scan is not implemented (daily only)"],
    ["draw-to-scan", "Draw to scan", "Drawing-to-scan is not implemented"],
  ].forEach(function (r) {
    add({ id: "gap:" + r[0], name: r[1], kind: "action", category: "Not implemented",
      desc: r[2], available: false, reason: r[2] });
  });

  /* ----------------------------------------------------- chart analysis layers */
  Object.keys(LAYER).forEach(function (id) {
    add({ id: "layer:" + id, name: LAYER[id], kind: "tool", category: "Chart analysis",
      desc: "Toggle this analysis layer on the chart", view: "charts", layer: id,
      keywords: "analysis layer overlay " + id });
  });

  window.PRAVAHA_FEATURES = F;
})();
