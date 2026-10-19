"""Unified, searchable catalogue of analytical tools (mission §6, §8).

One metadata contract so the UI can offer a single consistent, searchable
catalogue with an information panel per tool across four families:

* **scanners**   — cross-sectional filters, run through the real ``/api/screen``
  engine (``megatool.scanner``). Each entry carries a genuine condition tree.
* **algorithms** — signal-generation rules and quantitative analyses. Strategy
  entries name a key in ``megatool.backtest.STRATEGIES`` (run through
  ``/api/backtest``); analysis entries name a function in this module.
* **fundamentals** — ratio / screen tools over the stored fundamentals, run
  through :func:`run_fundamental`.

Nothing here is a stub: ``catalog_health()`` verifies that every entry names an
execution path that actually exists, and the test suite fails if it does not.

Design rules (kept deliberately):
* Every tool has a stable ``id``; counts are of *distinct* tools, never of
  parameter variations.
* Metadata is honest: ``data_requirements`` names the real fields, and
  ``limitations`` states what the tool cannot do (e.g. no intraday data).
* Search matches name, short label, category, tags, formula and description,
  so a keyword like "cheap" or "breakout" finds the right tools without any
  hard-coded query special-casing.
"""

from __future__ import annotations

from typing import Any

# --------------------------------------------------------------------------- #
# Scanner catalogue
# --------------------------------------------------------------------------- #
# A condition is (metric, operator, value) or (metric, operator, value, lookback).

_SCANNER_CATEGORIES = {
    "price": "Price & return",
    "trend": "Trend",
    "momentum": "Momentum",
    "volatility": "Volatility",
    "volume": "Volume & turnover",
    "breakout": "Breakout & pattern",
    "relative_strength": "Relative strength",
    "mean_reversion": "Mean reversion",
    "liquidity": "Liquidity",
    "combo": "Multi-factor",
}


def _cond(c: tuple) -> dict[str, Any]:
    if len(c) == 3:
        metric, op, value = c
        return {"metric": metric, "operator": op, "value": value}
    metric, op, value, lookback = c
    return {"metric": metric, "operator": op, "value": value, "lookback": lookback}


def _tree(conds: list[tuple]) -> dict[str, Any]:
    return {"op": "AND", "conditions": [_cond(c) for c in conds]}


def render_condition(c: dict[str, Any]) -> str:
    sym = {
        "gt": ">", "gte": ">=", "lt": "<", "lte": "<=", "eq": "=",
        "crosses_above": "crosses above", "crosses_below": "crosses below",
    }[c["operator"]]
    lb = f"({c['lookback']})" if c.get("lookback") is not None else ""
    return f"{c['metric']}{lb} {sym} {c['value']:g}"


def render_tree(tree: dict[str, Any]) -> str:
    return " AND ".join(render_condition(c) for c in tree["conditions"])


#: A scanner spec: id, name, category, description, conditions, tags, limitations.
_SCANNER_SPECS: list[tuple] = [
    # ---- price & return ---------------------------------------------------
    ("ret_1d_up", "Positive day", "price",
     "Close above the previous close.", [("return_1d", "gt", 0.0)],
     ["daily", "up", "gainers"], []),
    ("ret_1d_down", "Negative day", "price",
     "Close below the previous close.", [("return_1d", "lt", 0.0)],
     ["daily", "down", "losers"], []),
    ("ret_5d_up", "Positive week", "price",
     "Five-session return above 3%.", [("return_5d", "gt", 0.03), ("bars_listed", "gte", 25)],
     ["weekly", "momentum", "gainers"], []),
    ("ret_5d_down", "Negative week", "price",
     "Five-session return below -3%.", [("return_5d", "lt", -0.03), ("bars_listed", "gte", 25)],
     ["weekly", "losers"], []),
    ("ret_20d_strong", "Strong month", "price",
     "Twenty-session return above 10%.", [("return_20d", "gt", 0.10), ("bars_listed", "gte", 60)],
     ["monthly", "momentum", "strong"], []),
    ("ret_20d_weak", "Weak month", "price",
     "Twenty-session return below -10%.", [("return_20d", "lt", -0.10), ("bars_listed", "gte", 60)],
     ["monthly", "weak"], []),
    ("ret_60d_strong", "Strong quarter", "price",
     "Sixty-session return above 15%.", [("return_60d", "gt", 0.15), ("bars_listed", "gte", 100)],
     ["quarterly", "momentum"], []),
    ("ret_60d_weak", "Weak quarter", "price",
     "Sixty-session return below -15%.", [("return_60d", "lt", -0.15), ("bars_listed", "gte", 100)],
     ["quarterly", "weak"], []),
    ("ret_120d_strong", "Strong half-year", "price",
     "120-session return above 20%.", [("return_120d", "gt", 0.20), ("bars_listed", "gte", 160)],
     ["half-year", "momentum"], []),
    ("ret_120d_weak", "Weak half-year", "price",
     "120-session return below -20%.", [("return_120d", "lt", -0.20), ("bars_listed", "gte", 160)],
     ["half-year", "weak"], []),
    ("flat_week", "Flat week", "price",
     "Absolute five-session move under 1% (coiling).",
     [("return_5d", "gt", -0.01), ("return_5d", "lt", 0.01), ("bars_listed", "gte", 25)],
     ["range", "quiet", "coil"], []),
    ("long_history", "Long trading history", "price",
     "At least 1,000 stored bars.", [("bars_listed", "gte", 1000)],
     ["history", "established"], []),
    ("new_listing", "Recently listed", "price",
     "Between 30 and 120 stored bars.",
     [("bars_listed", "gte", 30), ("bars_listed", "lt", 120)],
     ["new", "listing", "ipo"], ["Short history weakens most other statistics on the same row."]),
    ("low_price", "Low nominal price", "price",
     "Close below NPR 200.", [("close", "lt", 200)],
     ["cheap", "price"], ["A low price is not the same as a low valuation."]),
    ("high_price", "High nominal price", "price",
     "Close above NPR 1,000.", [("close", "gt", 1000)],
     ["price"], []),
    ("near_52w_high_strict", "Within 1% of 250-bar high", "price",
     "Close within 1% of its trailing 250-bar high.",
     [("distance_from_high_52w", "gt", -0.01), ("bars_listed", "gte", 250)],
     ["high", "breakout", "strength"], []),
    ("near_52w_low_10", "Within 10% of 250-bar low", "price",
     "Close within 10% of its trailing 250-bar low.",
     [("distance_from_low_52w", "lt", 0.10), ("bars_listed", "gte", 250)],
     ["low", "weakness"], []),

    # ---- trend ------------------------------------------------------------
    ("below_sma20", "Below 20-day SMA", "trend",
     "Close below its 20-bar SMA.",
     [("close_vs_sma", "lt", 0.0, 20), ("bars_listed", "gte", 30)], ["trend", "below"], []),
    ("below_sma50", "Below 50-day SMA", "trend",
     "Close below its 50-bar SMA.",
     [("close_vs_sma", "lt", 0.0, 50), ("bars_listed", "gte", 60)], ["trend", "below"], []),
    ("below_sma200", "Below 200-day SMA", "trend",
     "Close below its 200-bar SMA (long-term weakness).",
     [("close_vs_sma", "lt", 0.0, 200), ("bars_listed", "gte", 220)], ["trend", "below"], []),
    ("far_above_sma50", "Far above 50-day SMA", "trend",
     "Close more than 10% above its 50-bar SMA (extended).",
     [("close_vs_sma", "gt", 0.10, 50), ("bars_listed", "gte", 60)],
     ["trend", "extended", "stretched"], ["An extended price can also be a late entry."]),
    ("far_below_sma50", "Far below 50-day SMA", "trend",
     "Close more than 10% below its 50-bar SMA (oversold trend).",
     [("close_vs_sma", "lt", -0.10, 50), ("bars_listed", "gte", 60)], ["trend", "oversold"], []),
    ("sma50_above_sma200", "50-day above 200-day", "trend",
     "The 50-bar SMA sits above the 200-bar SMA (Golden-cross regime).",
     [("sma_cross", "gt", 0.0, 200), ("bars_listed", "gte", 220)],
     ["golden", "cross", "regime"], []),
    ("sma20_below_sma50", "20-day below 50-day", "trend",
     "The 20-bar SMA sits below the 50-bar SMA (Death-cross regime).",
     [("sma_cross", "lt", 0.0, 50), ("bars_listed", "gte", 60)],
     ["death", "cross", "regime"], []),
    ("adx_very_strong", "Very strong trend", "trend",
     "ADX(14) above 40.",
     [("adx", "gt", 40.0), ("bars_listed", "gte", 60)], ["trend", "strength", "adx"], []),
    ("adx_weak", "Weak / no trend", "trend",
     "ADX(14) below 15 (range-bound).",
     [("adx", "lt", 15.0), ("bars_listed", "gte", 60)], ["range", "chop", "adx"], []),
    ("adx_mid", "Moderate trend", "trend",
     "ADX(14) between 20 and 30.",
     [("adx", "gt", 20.0), ("adx", "lt", 30.0), ("bars_listed", "gte", 60)],
     ["trend", "adx"], []),

    # ---- momentum ---------------------------------------------------------
    ("rsi_mid_bull", "RSI bullish zone", "momentum",
     "RSI(14) between 50 and 65 (rising but not overbought).",
     [("rsi", "gt", 50.0), ("rsi", "lt", 65.0), ("bars_listed", "gte", 60)],
     ["rsi", "bullish", "momentum"], []),
    ("rsi_neutral", "RSI neutral", "momentum",
     "RSI(14) between 40 and 60.",
     [("rsi", "gt", 40.0), ("rsi", "lt", 60.0), ("bars_listed", "gte", 60)],
     ["rsi", "neutral"], []),
    ("rsi_extreme_oversold", "RSI deeply oversold", "momentum",
     "RSI(14) below 20.",
     [("rsi", "lt", 20.0), ("bars_listed", "gte", 60)],
     ["rsi", "oversold", "washed"], ["Deeply oversold names can keep falling."]),
    ("macd_hist_positive", "MACD histogram positive", "momentum",
     "MACD histogram above zero.",
     [("macd_histogram", "gt", 0.0), ("bars_listed", "gte", 60)], ["macd", "bullish"], []),
    ("macd_hist_negative", "MACD histogram negative", "momentum",
     "MACD histogram below zero.",
     [("macd_histogram", "lt", 0.0), ("bars_listed", "gte", 60)], ["macd", "bearish"], []),
    ("macd_above_zero", "MACD above zero", "momentum",
     "MACD line above zero.",
     [("macd", "gt", 0.0), ("bars_listed", "gte", 60)], ["macd", "bullish"], []),
    ("macd_below_zero", "MACD below zero", "momentum",
     "MACD line below zero.",
     [("macd", "lt", 0.0), ("bars_listed", "gte", 60)], ["macd", "bearish"], []),
    ("stoch_mid", "Stochastic centred", "momentum",
     "Stochastic %K between 40 and 60.",
     [("stochastic_k", "gt", 40.0), ("stochastic_k", "lt", 60.0), ("bars_listed", "gte", 60)],
     ["stochastic", "neutral"], []),
    ("mfi_strong", "Money-flow strong", "momentum",
     "MFI(14) above 80.",
     [("mfi", "gt", 80.0), ("bars_listed", "gte", 60)],
     ["mfi", "money flow", "overbought"], []),
    ("mfi_weak", "Money-flow weak", "momentum",
     "MFI(14) below 20.",
     [("mfi", "lt", 20.0), ("bars_listed", "gte", 60)], ["mfi", "money flow", "oversold"], []),
    ("roc_positive", "Positive 20-day ROC", "momentum",
     "Twenty-session momentum is positive but modest.",
     [("return_20d", "gt", 0.0), ("return_20d", "lt", 0.10), ("bars_listed", "gte", 60)],
     ["roc", "momentum"], []),

    # ---- volatility -------------------------------------------------------
    ("atr_high", "High ATR", "volatility",
     "ATR(14) above 5% of price (big daily ranges).",
     [("atr_percent", "gt", 5.0), ("bars_listed", "gte", 60)],
     ["atr", "volatile", "risk"], []),
    ("atr_low", "Low ATR", "volatility",
     "ATR(14) below 2% of price (calm).",
     [("atr_percent", "lt", 2.0), ("bars_listed", "gte", 60)], ["atr", "calm"], []),
    ("hv_high", "High historical volatility", "volatility",
     "Annualised 20-day volatility above 60%.",
     [("historical_volatility", "gt", 60.0), ("bars_listed", "gte", 60)],
     ["volatility", "risk", "volatile"], []),
    ("hv_low", "Low historical volatility", "volatility",
     "Annualised 20-day volatility below 25%.",
     [("historical_volatility", "lt", 25.0), ("bars_listed", "gte", 60)],
     ["volatility", "calm", "low vol"], []),
    ("bb_expansion", "Bollinger expansion", "volatility",
     "Bollinger bandwidth above 0.20 (wide bands).",
     [("bollinger_bandwidth", "gt", 0.20), ("bars_listed", "gte", 60)], ["bollinger", "expansion"], []),
    ("bb_squeeze_tight", "Tight Bollinger squeeze", "volatility",
     "Bollinger bandwidth below 0.05.",
     [("bollinger_bandwidth", "lt", 0.05), ("bars_listed", "gte", 60)],
     ["bollinger", "squeeze", "coil"], ["A squeeze precedes a move but not its direction."]),
    ("bb_near_upper", "At upper Bollinger band", "volatility",
     "Bollinger %B above 0.95.",
     [("bollinger_percent_b", "gt", 0.95), ("bars_listed", "gte", 60)], ["bollinger", "upper"], []),
    ("bb_near_lower", "At lower Bollinger band", "volatility",
     "Bollinger %B below 0.05.",
     [("bollinger_percent_b", "lt", 0.05), ("bars_listed", "gte", 60)], ["bollinger", "lower"], []),
    ("range_expansion", "Range expansion", "volatility",
     "Today's range more than twice the 20-session average.",
     [("range_compression_20", "gt", 2.0), ("bars_listed", "gte", 60)],
     ["range", "expansion", "impulse"], []),
    ("range_contraction", "Range contraction", "volatility",
     "Today's range below half the 20-session average.",
     [("range_compression_20", "lt", 0.5), ("bars_listed", "gte", 60)],
     ["range", "contraction", "coil"], []),

    # ---- volume & turnover ------------------------------------------------
    ("turnover_high", "High turnover (liquid)", "volume",
     "Daily turnover above NPR 50m.",
     [("turnover", "gt", 50_000_000.0)],
     ["turnover", "liquid", "money"], []),
    ("turnover_surge", "Turnover surge", "volume",
     "Turnover at least 3x its 20-bar average.",
     [("turnover_sma_ratio", "gte", 3.0), ("bars_listed", "gte", 25)],
     ["turnover", "surge", "spike"], []),
    ("turnover_dryup", "Turnover dry-up", "volume",
     "Turnover below 30% of its 20-bar average.",
     [("turnover_sma_ratio", "lte", 0.3), ("bars_listed", "gte", 25)],
     ["turnover", "dry", "quiet"], []),
    ("rvol_high", "Relative volume high", "volume",
     "Latest volume at least 3x its 20-bar mean.",
     [("relative_volume", "gte", 3.0), ("bars_listed", "gte", 25)],
     ["volume", "spike", "rvol"], []),
    ("rvol_low", "Relative volume low", "volume",
     "Latest volume below 30% of its 20-bar mean.",
     [("relative_volume", "lte", 0.3), ("bars_listed", "gte", 25)],
     ["volume", "dry", "quiet"], []),
    ("vol_ratio50_high", "Volume above 50-day base", "volume",
     "Latest volume at least 2.5x its 50-bar average.",
     [("volume_ratio_50", "gte", 2.5), ("bars_listed", "gte", 60)],
     ["volume", "spike"], []),
    ("vol_ratio50_low", "Volume below 50-day base", "volume",
     "Latest volume below 35% of its 50-bar average.",
     [("volume_ratio_50", "lte", 0.35), ("bars_listed", "gte", 60)],
     ["volume", "dry"], []),
    ("updown_volume_bull", "Up-volume dominant", "volume",
     "Up-day volume more than 2x down-day volume over 20 sessions.",
     [("updown_volume_ratio", "gt", 2.0, 20), ("bars_listed", "gte", 40)],
     ["volume", "accumulation", "bullish"], []),
    ("updown_volume_bear", "Down-volume dominant", "volume",
     "Down-day volume more than 2x up-day volume over 20 sessions.",
     [("updown_volume_ratio", "lt", 0.5, 20), ("bars_listed", "gte", 40)],
     ["volume", "distribution", "bearish"], []),
    ("obv_strong_distribution", "OBV distribution", "volume",
     "Net OBV pressure over 20 sessions below -0.3.",
     [("obv_pressure_20", "lt", -0.3, 20), ("bars_listed", "gte", 40)],
     ["obv", "distribution"], []),
    ("vol_biggest_20d", "Biggest volume of 20 sessions", "volume",
     "Today's volume is the largest of the last 20 sessions.",
     [("volume_vs_20d_max", "gt", 0.99), ("bars_listed", "gte", 40)],
     ["volume", "climax", "record"], []),
    ("vol_climax_high", "Volume climax", "volume",
     "Largest volume of the last 5 sessions above 3x the 20-bar mean.",
     [("volume_climax_5_20", "gt", 3.0), ("bars_listed", "gte", 40)],
     ["volume", "climax", "impulse"], []),

    # ---- breakout & pattern ----------------------------------------------
    ("donchian_top", "Near Donchian top", "breakout",
     "Close in the top 10% of its Donchian channel.",
     [("donchian_position", "gt", 0.90), ("bars_listed", "gte", 60)],
     ["breakout", "channel", "strength"], []),
    ("donchian_bottom", "Near Donchian bottom", "breakout",
     "Close in the bottom 10% of its Donchian channel.",
     [("donchian_position", "lt", 0.10), ("bars_listed", "gte", 60)],
     ["channel", "weakness"], []),
    ("donchian_mid", "Mid-channel", "breakout",
     "Close in the middle 20% of its Donchian channel.",
     [("donchian_position", "gt", 0.40), ("donchian_position", "lt", 0.60), ("bars_listed", "gte", 60)],
     ["channel", "neutral"], []),
    ("breakout_fresh", "Fresh channel breakout", "breakout",
     "New channel-high close today with a long history.",
     [("donchian_breakout", "gt", 0.0), ("bars_listed", "gte", 120)],
     ["breakout", "new high"], []),
    ("breakdown_fresh", "Fresh channel breakdown", "breakout",
     "New channel-low close today with a long history.",
     [("donchian_breakout", "lt", 0.0), ("bars_listed", "gte", 120)],
     ["breakdown", "new low"], []),
    ("breakout_volume_strong", "Breakout with strong volume", "breakout",
     "Channel breakout and volume at least 2x the 20-bar mean.",
     [("donchian_breakout", "gt", 0.0), ("volume_sma_ratio", "gte", 2.0), ("bars_listed", "gte", 60)],
     ["breakout", "volume", "confirmation"], []),
    ("high_vol_breakout", "High-ATR breakout", "breakout",
     "Breakout with ATR above 4% (volatile instrument).",
     [("donchian_breakout", "gt", 0.0), ("atr_percent", "gt", 4.0), ("bars_listed", "gte", 60)],
     ["breakout", "volatile"], []),
    ("near_high_with_volume", "Near high on volume", "breakout",
     "Within 2% of the 250-bar high on at least 2x volume.",
     [("distance_from_high_52w", "gt", -0.02), ("volume_sma_ratio", "gte", 2.0), ("bars_listed", "gte", 250)],
     ["breakout", "high", "volume"], []),

    # ---- relative strength ------------------------------------------------
    ("rs_strong", "Beating the index by 10%", "relative_strength",
     "Excess return over the NEPSE composite above 10pp over 60 sessions.",
     [("relative_strength", "gt", 10.0, 60), ("bars_listed", "gte", 80)],
     ["relative strength", "outperform", "leader"], []),
    ("rs_weak", "Lagging the index by 10%", "relative_strength",
     "Excess return over the NEPSE composite below -10pp over 60 sessions.",
     [("relative_strength", "lt", -10.0, 60), ("bars_listed", "gte", 80)],
     ["relative strength", "underperform", "laggard"], []),
    ("rs_positive", "Outperforming the index", "relative_strength",
     "Positive excess return over the NEPSE composite (60 sessions).",
     [("relative_strength", "gt", 0.0, 60), ("bars_listed", "gte", 80)],
     ["relative strength", "outperform"], []),
    ("rs_negative", "Underperforming the index", "relative_strength",
     "Negative excess return over the NEPSE composite (60 sessions).",
     [("relative_strength", "lt", 0.0, 60), ("bars_listed", "gte", 80)],
     ["relative strength", "underperform"], []),
    ("rs_strong_short", "Beating the index by 5% (20d)", "relative_strength",
     "Excess return over the index above 5pp over 20 sessions.",
     [("relative_strength", "gt", 5.0, 20), ("bars_listed", "gte", 40)],
     ["relative strength", "outperform", "monthly"], []),

    # ---- mean reversion ---------------------------------------------------
    ("mr_rsi_mild", "Mildly oversold (RSI<40)", "mean_reversion",
     "RSI(14) between 25 and 40.",
     [("rsi", "gt", 20.0), ("rsi", "lt", 40.0), ("bars_listed", "gte", 60)],
     ["oversold", "reversion", "dip"], []),
    ("mr_near_lower_band", "Near lower band in uptrend", "mean_reversion",
     "Below 50-day SMA but not in free-fall (RSI above 30).",
     [("close_vs_sma", "lt", 0.0, 50), ("rsi", "gt", 30.0), ("bars_listed", "gte", 60)],
     ["pullback", "reversion", "dip", "value"], []),
    ("mr_stoch_extreme", "Stochastic deeply oversold", "mean_reversion",
     "Stochastic %K below 10.",
     [("stochastic_k", "lt", 10.0), ("bars_listed", "gte", 60)],
     ["stochastic", "oversold"], []),
    ("mr_atr_pullback", "Sharp single-day fall", "mean_reversion",
     "Daily loss beyond one ATR, on a long history.",
     [("return_1d", "lt", -0.04), ("bars_listed", "gte", 60)],
     ["dip", "selloff", "reversion"], ["A large one-day fall is not by itself a reversal signal."]),

    # ---- liquidity --------------------------------------------------------
    ("liq_very_illiquid", "Illiquid", "liquidity",
     "Daily turnover below NPR 500k.",
     [("turnover", "lt", 500_000.0)],
     ["illiquid", "thin"], ["Thin names are hard to enter or exit at the quoted price."]),
    ("liq_active", "Active trading", "liquidity",
     "Daily turnover above NPR 20m and volume above the 50-day base.",
     [("turnover", "gt", 20_000_000.0), ("volume_ratio_50", "gte", 1.0)],
     ["liquid", "active"], []),
    ("liq_quiet_liquid", "Quiet but liquid", "liquidity",
     "High turnover history but today's volume is below 50% of base.",
     [("turnover_sma_ratio", "lte", 0.5), ("turnover", "gt", 5_000_000.0)],
     ["quiet", "liquid", "dry"], []),

    # ---- multi-factor combos ---------------------------------------------
    ("combo_momentum_volume", "Momentum + volume", "combo",
     "Positive 20-day return on above-average volume.",
     [("return_20d", "gt", 0.05), ("volume_sma_ratio", "gt", 1.5), ("bars_listed", "gte", 60)],
     ["momentum", "volume", "confirmation"], []),
    ("combo_oversold_volume", "Oversold + volume", "combo",
     "Oversold RSI with a volume pickup (capitulation candidate).",
     [("rsi", "lt", 35.0), ("volume_sma_ratio", "gt", 1.5), ("bars_listed", "gte", 60)],
     ["oversold", "volume", "capitulation"], []),
    ("combo_trend_pullback", "Uptrend pullback", "combo",
     "Above the 50-day SMA but RSI has cooled below 45.",
     [("close_vs_sma", "gt", 0.0, 50), ("rsi", "lt", 45.0), ("bars_listed", "gte", 60)],
     ["pullback", "trend", "dip"], []),
    ("combo_downtrend_bounce", "Downtrend bounce", "combo",
     "Below the 50-day SMA but RSI is strong (counter-trend bounce).",
     [("close_vs_sma", "lt", 0.0, 50), ("rsi", "gt", 60.0), ("bars_listed", "gte", 60)],
     ["bounce", "counter-trend"], []),
    ("combo_squeeze_momentum", "Squeeze + momentum", "combo",
     "Tight bandwidth with a positive 20-day return.",
     [("bollinger_bandwidth", "lt", 0.08), ("return_20d", "gt", 0.0), ("bars_listed", "gte", 60)],
     ["squeeze", "momentum", "coil"], []),
    ("combo_trend_continuation", "Trend continuation", "combo",
     "Strong ADX with RSI in the bullish 50-70 band.",
     [("adx", "gt", 25.0), ("rsi", "gt", 50.0), ("rsi", "lt", 70.0), ("bars_listed", "gte", 60)],
     ["trend", "continuation", "adx"], []),
    ("combo_range_reversal", "Range overbought", "combo",
     "No trend (ADX below 20) with RSI above 70.",
     [("adx", "lt", 20.0), ("rsi", "gt", 70.0), ("bars_listed", "gte", 60)],
     ["range", "reversal", "overbought"], []),
    ("combo_liquid_momentum", "Liquid momentum", "combo",
     "High turnover with a positive monthly return.",
     [("turnover", "gt", 10_000_000.0), ("return_20d", "gt", 0.05), ("bars_listed", "gte", 60)],
     ["liquid", "momentum"], []),
    ("combo_quiet_coil", "Quiet coil", "combo",
     "Tight range and tight Bollinger bandwidth together.",
     [("range_compression_20", "lt", 0.6), ("bollinger_bandwidth", "lt", 0.10), ("bars_listed", "gte", 60)],
     ["coil", "squeeze", "quiet"], []),
    ("combo_golden_volume", "Golden regime + volume", "combo",
     "Golden-cross regime with a volume pickup.",
     [("sma_cross", "gt", 0.0, 200), ("volume_sma_ratio", "gt", 1.5), ("bars_listed", "gte", 220)],
     ["golden", "trend", "volume"], []),
    ("combo_value_trend", "Cheap and turning up", "combo",
     "Near the 250-bar low yet with positive short-term momentum.",
     [("distance_from_low_52w", "lt", 0.15), ("return_20d", "gt", 0.0), ("bars_listed", "gte", 250)],
     ["value", "turnaround", "reversal"], []),
    ("combo_accumulation_trend", "Accumulation in uptrend", "combo",
     "OBV accumulation pressure with price above the 50-day SMA.",
     [("obv_pressure_20", "gt", 0.2, 20), ("close_vs_sma", "gt", 0.0, 50), ("bars_listed", "gte", 60)],
     ["obv", "accumulation", "trend"], []),
    ("combo_distribution_downtrend", "Distribution in downtrend", "combo",
     "OBV distribution pressure with price below the 50-day SMA.",
     [("obv_pressure_20", "lt", -0.2, 20), ("close_vs_sma", "lt", 0.0, 50), ("bars_listed", "gte", 60)],
     ["obv", "distribution", "trend"], []),
]


def build_scanners() -> list[dict[str, Any]]:
    """Build the full scanner catalogue (existing presets + the specs above).

    The existing ``PRESET_SCREENS`` are folded in so the catalogue is a single
    authoritative list; their metadata is enriched here without changing the
    trees the engine already runs.
    """
    from megatool.scanner import PRESET_SCREENS

    out: list[dict[str, Any]] = []
    seen: set[str] = set()

    # 1. Existing presets first (stable ids, real trees) with enriched metadata.
    existing_meta = _EXISTING_PRESET_META
    for key, spec in PRESET_SCREENS.items():
        meta = existing_meta.get(key, {})
        out.append(
            {
                "id": f"scan.{key}",
                "key": key,
                "kind": "scanner",
                "name": spec["name"],
                "short": meta.get("short", ""),
                "category": meta.get("category", _infer_category(spec)),
                "description": spec["description"],
                "formula": render_tree(spec["tree"]),
                "tree": spec["tree"],
                "params": meta.get("params", {}),
                "tags": meta.get("tags", []),
                "limitations": meta.get("limitations", []),
                "data_requirements": ["daily OHLCV bars (close, high, low, volume, turnover)"],
                "run": {"engine": "screen", "tree": spec["tree"]},
                "status": "available",
            }
        )
        seen.add(f"scan.{key}")
        seen.add(key)

    # 2. New specs.
    for sid, name, category, desc, conds, tags, lim in _SCANNER_SPECS:
        full_id = f"scan.{sid}"
        if full_id in seen or sid in seen:
            continue
        tree = _tree(conds)
        out.append(
            {
                "id": full_id,
                "key": sid,
                "kind": "scanner",
                "name": name,
                "short": render_tree(tree),
                "category": category,
                "description": desc,
                "formula": render_tree(tree),
                "tree": tree,
                "params": {},
                "tags": list(tags),
                "limitations": list(lim),
                "data_requirements": ["daily OHLCV bars (close, high, low, volume, turnover)"],
                "run": {"engine": "screen", "tree": tree},
                "status": "available",
            }
        )
        seen.add(full_id)
        seen.add(sid)
    return out


def _infer_category(spec: dict[str, Any]) -> str:
    text = (spec.get("name", "") + " " + spec.get("description", "")).lower()
    for cat, words in (
        ("volume", ("volume", "turnover")),
        ("volatility", ("bollinger", "volatil", "atr", "squeeze")),
        ("breakout", ("breakout", "channel", "donchian")),
        ("momentum", ("rsi", "macd", "stochastic", "mfi", "momentum")),
        ("trend", ("sma", "trend", "adx", "cross")),
    ):
        if any(w in text for w in words):
            return cat
    return "price"


#: Enriched metadata for the pre-existing presets (trees unchanged).
_EXISTING_PRESET_META: dict[str, dict[str, Any]] = {
    "oversold_rsi": {"category": "momentum", "tags": ["rsi", "oversold", "dip", "mean reversion"]},
    "volume_surge": {"category": "volume", "tags": ["volume", "spike", "unusual"]},
    "near_52w_high": {"category": "price", "tags": ["high", "breakout", "strength"]},
    "above_sma50": {"category": "trend", "tags": ["sma", "trend", "above"]},
    "rsi_overbought": {"category": "momentum", "tags": ["rsi", "overbought"]},
    "macd_bullish_cross": {"category": "momentum", "tags": ["macd", "cross", "bullish"]},
    "macd_bearish_cross": {"category": "momentum", "tags": ["macd", "cross", "bearish"]},
    "above_sma20": {"category": "trend", "tags": ["sma", "trend"]},
    "above_sma200": {"category": "trend", "tags": ["sma", "trend", "long term"]},
    "sma5_above_sma20": {"category": "trend", "tags": ["sma", "alignment", "trend"]},
    "bollinger_lower_band": {"category": "volatility", "tags": ["bollinger", "lower", "oversold"]},
    "bollinger_upper_band": {"category": "volatility", "tags": ["bollinger", "upper"]},
    "bollinger_squeeze": {"category": "volatility", "tags": ["bollinger", "squeeze", "coil"]},
    "stochastic_oversold": {"category": "momentum", "tags": ["stochastic", "oversold"]},
    "stochastic_overbought": {"category": "momentum", "tags": ["stochastic", "overbought"]},
    "mfi_oversold": {"category": "momentum", "tags": ["mfi", "money flow", "oversold"]},
    "donchian_breakout_up": {"category": "breakout", "tags": ["donchian", "breakout"]},
    "breakout_with_volume": {"category": "breakout", "tags": ["breakout", "volume", "confirmation"]},
    "near_52w_low": {"category": "price", "tags": ["low", "weakness"]},
    "momentum_20d": {"category": "momentum", "tags": ["momentum", "monthly"]},
    "strong_trend_adx": {"category": "trend", "tags": ["adx", "trend", "strength"]},
    "low_volatility": {"category": "volatility", "tags": ["volatility", "calm", "low vol"]},
    "liquid_turnover": {"category": "volume", "tags": ["turnover", "liquid"]},
    "volume_dryup": {"category": "volume", "tags": ["volume", "dry", "quiet"]},
    "accumulation_20d": {"category": "volume", "tags": ["accumulation", "volume"]},
    "distribution_20d": {"category": "volume", "tags": ["distribution", "volume"]},
    "pocket_pivot": {"category": "breakout", "tags": ["pocket pivot", "volume", "breakout"]},
    "obv_accumulation_20d": {"category": "volume", "tags": ["obv", "accumulation"]},
    "volume_climax": {"category": "volume", "tags": ["volume", "climax"]},
    "biggest_volume_20d": {"category": "volume", "tags": ["volume", "record"]},
    "unusual_volume_50": {"category": "volume", "tags": ["volume", "unusual"]},
}


# --------------------------------------------------------------------------- #
# Algorithm catalogue — metadata for strategies (executed by the backtest
# engine) plus pure quantitative analyses implemented in this module.
# --------------------------------------------------------------------------- #

_ALGORITHM_CATEGORIES = {
    "trend": "Trend following",
    "reversion": "Mean reversion",
    "momentum": "Momentum",
    "breakout": "Breakout & pullback",
    "relative_value": "Relative value",
    "risk": "Risk management",
    "portfolio": "Portfolio & allocation",
    "statistical": "Statistical & quantitative",
    "valuation": "Valuation & research",
    "regime": "Regime & filtering",
    "baseline": "Baseline",
    "volume": "Volume",
}


def build_algorithms() -> list[dict[str, Any]]:
    """Metadata for every runnable strategy, plus the analysis algorithms."""
    from megatool.backtest import STRATEGIES

    out: list[dict[str, Any]] = []
    meta = _STRATEGY_META
    for key, spec in STRATEGIES.items():
        m = meta.get(key, {})
        out.append(
            {
                "id": f"algo.{key}",
                "key": key,
                "kind": "algorithm",
                "engine": "backtest",
                "name": spec["label"],
                "category": spec.get("category", "undefined"),
                "description": spec["description"],
                "formula": m.get("rules", spec["description"]),
                "params": dict(spec["params"]),
                "tags": m.get("tags", []),
                "limitations": m.get("limitations", []),
                "data_requirements": ["daily close (and volume/ATR inputs where used)"],
                "run": {"engine": "backtest", "strategy": key},
                "status": "available",
            }
        )

    for a in _ANALYSIS_ALGORITHMS:
        out.append(
            {
                "id": f"algo.{a['key']}",
                "key": a["key"],
                "kind": "algorithm",
                "engine": "analysis",
                "name": a["name"],
                "category": a["category"],
                "description": a["description"],
                "formula": a["formula"],
                "params": a.get("params", {}),
                "tags": a.get("tags", []),
                "limitations": a.get("limitations", []),
                "data_requirements": a.get("data_requirements", ["daily close"]),
                "run": {"engine": "analysis", "fn": a["key"]},
                "status": "available",
            }
        )
    return out


_STRATEGY_META: dict[str, dict[str, Any]] = {
    "sma_cross": {"tags": ["sma", "cross", "trend"], "rules": "Long while SMA(fast) > SMA(slow)."},
    "rsi_threshold": {"tags": ["rsi", "reversion", "oversold"], "rules": "Long while RSI < buy_below; flat when RSI > sell_above."},
    "ma_slope_trend": {"tags": ["trend", "slope"], "rules": "Long while the N-bar SMA slope is positive."},
    "always_in": {"tags": ["baseline", "buy and hold"], "rules": "Always long."},
    "donchian_breakout": {"tags": ["breakout", "donchian"], "rules": "Long on a new N-bar high; flat on an M-bar low."},
    "bollinger_revert": {"tags": ["bollinger", "reversion"], "rules": "Long below the lower band; flat at the mid band."},
    "macd_trend": {"tags": ["macd", "trend"], "rules": "Long while MACD > signal."},
    "momentum_90d": {"tags": ["momentum", "time series"], "rules": "Long while the N-day return is positive."},
    "rsi2_reversion": {"tags": ["rsi", "connors", "reversion"], "rules": "Long while RSI(2) < buy_below; flat above exit_above."},
    "trend200_filter": {"tags": ["regime", "sma"], "rules": "Long only while price > SMA(N)."},
    "vol_regime": {"tags": ["volatility", "regime"], "rules": "Long while trailing volatility is in its calm percentile."},
    "atr_channel": {"tags": ["atr", "breakout"], "rules": "Enter beyond range + entry_k×ATR; exit near the opposite edge."},
    "ema_ribbon": {"tags": ["ema", "trend"], "rules": "Long while EMA(fast) > EMA(mid) > EMA(slow)."},
    "rate_of_change": {"tags": ["roc", "momentum"], "rules": "Long while the N-day ROC exceeds min_pct."},
    "stochastic_revert": {"tags": ["stochastic", "reversion"], "rules": "Long under the buy level; flat above the exit level."},
    "cci_trend": {"tags": ["cci", "momentum"], "rules": "Long while CCI > 0."},
    "accum_dist_trend": {"tags": ["volume", "ad line"], "rules": "Long while the AD line is above its EMA."},
    "obv_trend": {"tags": ["volume", "obv"], "rules": "Long while OBV is above its EMA."},
    "golden_cross": {"tags": ["golden cross", "regime"], "rules": "Long while SMA(fast) > SMA(slow) and price > SMA(fast)."},
    "range_rider": {"tags": ["range", "breakout"], "rules": "Long while the close is in the upper fraction of the trailing range."},
}


#: Pure-analysis algorithms (no trade ledger). Each key is a function below.
_ANALYSIS_ALGORITHMS: list[dict[str, Any]] = [
    {
        "key": "technical_rating",
        "name": "Technical rating (confluence score)",
        "category": "statistical",
        "description": "Aggregates a fixed set of technical readings (trend, momentum, "
        "oscillator, volatility) into one explainable rating per bar.",
        "formula": "Weighted sum of per-signal votes (bullish +1 / neutral 0 / bearish -1), "
        "normalised to [-100, 100].",
        "params": {"rsi_period": 14},
        "tags": ["rating", "confluence", "score", "technical"],
        "limitations": ["A composite of historical readings; it is not a forecast."],
    },
    {
        "key": "mtf_confluence",
        "name": "Multi-timeframe confluence",
        "category": "statistical",
        "description": "Compares the trend reading on daily, weekly and monthly "
        "aggregations and reports how many agree.",
        "formula": "Trend = sign(SMA20 - SMA50) on each timeframe; confluence = agreeing / total.",
        "params": {},
        "tags": ["multi-timeframe", "confluence", "mtf"],
        "limitations": ["Weekly/monthly bars are aggregated from the daily series; no new data."],
    },
    {
        "key": "rolling_beta",
        "name": "Rolling beta vs index",
        "category": "statistical",
        "description": "Rolling market beta of a security versus the NEPSE composite.",
        "formula": "beta = cov(r_stock, r_index) / var(r_index) over a rolling window.",
        "params": {"window": 60},
        "tags": ["beta", "market model", "risk", "regression"],
        "limitations": ["Needs a benchmark series; unavailable without it rather than substituted."],
        "data_requirements": ["daily close", "NEPSE composite index closes"],
    },
    {
        "key": "volatility_percentile",
        "name": "Volatility percentile",
        "category": "statistical",
        "description": "Where the current realized volatility sits in its own history.",
        "formula": "Percentile rank of the latest N-day realized volatility among its trailing values.",
        "params": {"window": 20, "lookback": 252},
        "tags": ["volatility", "percentile", "regime"],
        "limitations": ["Percentile is relative to the symbol's own stored history."],
    },
    {
        "key": "correlation_matrix",
        "name": "Return correlation matrix",
        "category": "portfolio",
        "description": "Pairwise correlation of daily returns across a set of symbols.",
        "formula": "Pearson correlation of aligned daily log/close-to-close returns.",
        "params": {"symbols": [], "window": 120},
        "tags": ["correlation", "portfolio", "diversification"],
        "limitations": ["Correlations are unstable and estimated from the stored window only."],
    },
    {
        "key": "efficient_frontier",
        "name": "Efficient frontier (mean-variance)",
        "category": "portfolio",
        "description": "Long-only minimum-variance and max-Sharpe portfolios plus the frontier curve.",
        "formula": "Solve min wᵀΣw and max (wᵀμ)/sqrt(wᵀΣw) subject to Σw=1, w≥0.",
        "params": {"symbols": [], "window": 250, "risk_free": 0.05},
        "tags": ["portfolio", "optimization", "frontier", "sharpe", "covariance"],
        "limitations": ["Expected returns are historical sample means; results are highly sensitive "
                        "to them and are not forecasts."],
    },
    {
        "key": "monte_carlo",
        "name": "Monte Carlo (GBM / bootstrap)",
        "category": "statistical",
        "description": "Simulates terminal wealth from a starting value under GBM or a "
        "bootstrap of historical returns, with reproducible seeds.",
        "formula": "GBM: S_t = S_0·exp((μ-σ²/2)dt + σ√dt·Z). Bootstrap: resample historical returns.",
        "params": {"start": 100.0, "drift": 0.08, "volatility": 0.25, "days": 252,
                   "paths": 1000, "seed": 42},
        "tags": ["monte carlo", "simulation", "gbm", "bootstrap", "distribution"],
        "limitations": ["Model output under stated assumptions, not a prediction; no jumps, "
                        "costs or fat tails beyond the bootstrap sample."],
    },
    {
        "key": "risk_of_ruin",
        "name": "Risk of ruin / losing streak",
        "category": "risk",
        "description": "Simulates equity paths from a trade-return distribution to estimate "
        "drawdown and depletion probabilities.",
        "formula": "Given win rate and win/loss sizes, compound a fixed risk-per-trade over N trades, repeat M times.",
        "params": {"win_rate": 0.5, "avg_win": 0.02, "avg_loss": 0.02, "risk_per_trade": 0.01,
                   "trades": 200, "paths": 1000, "ruin_threshold": 0.5, "seed": 42},
        "tags": ["risk", "drawdown", "ruin", "monte carlo", "position sizing"],
        "limitations": ["IID assumption across trades; dependence between trades is not modelled."],
    },
    {
        "key": "signal_outcomes",
        "name": "Signal outcome study",
        "category": "statistical",
        "description": "Forward returns following a signal, with explicit entry timing and "
        "no look-ahead.",
        "formula": "For each signal at bar t, forward return = close[t+h] / close[t+1] - 1 (h sessions).",
        "params": {"signal": "rsi_oversold", "horizons": [5, 10, 20]},
        "tags": ["event study", "forward returns", "signal", "outcome"],
        "limitations": ["Signal semantics are historical; overlapping windows are not adjusted."],
    },
    {
        "key": "dcf_valuation",
        "name": "Discounted cash-flow valuation",
        "category": "valuation",
        "description": "Projects free cash flow, discounts at WACC, adds a Gordon terminal "
        "value, and reports enterprise/equity value per share with a sensitivity grid.",
        "formula": "EV = Σ FCF_t/(1+w)^t + TV/(1+w)^n, TV = FCF_n(1+g)/(w-g); equity = EV - net debt",
        "params": {"fcf0": 1e9, "growth": 0.08, "wacc": 0.13, "terminal_growth": 0.04,
                   "years": 5, "net_debt": 0.0, "shares": 1e8},
        "tags": ["valuation", "dcf", "wacc", "terminal value", "cash flow"],
        "limitations": ["Every input is supplied by the caller; the model does not estimate or fetch them.",
                        "The Gordon terminal value is undefined when WACC <= terminal growth."],
    },
    {
        "key": "reverse_dcf",
        "name": "Reverse DCF (implied growth)",
        "category": "valuation",
        "description": "Solves for the FCF growth the current price implies, making the "
        "market's embedded assumption explicit.",
        "formula": "Find g such that DCF(g) = target price (bisection).",
        "params": {"target_price": 500.0, "fcf0": 1e9, "wacc": 0.13,
                   "terminal_growth": 0.04, "years": 5, "shares": 1e8},
        "tags": ["valuation", "reverse dcf", "implied growth", "assumptions"],
        "limitations": ["Reports an assumption, not a forecast; sensitive to WACC and terminal growth."],
    },
    {
        "key": "hrp_portfolio",
        "name": "Hierarchical risk parity (HRP)",
        "category": "portfolio",
        "description": "Allocation from the covariance structure via hierarchical clustering and "
        "recursive bisection - no matrix inversion, no expected-return input.",
        "formula": "Cluster by correlation distance; split clusters by inverse cluster variance.",
        "params": {"symbols": [], "window": 250},
        "tags": ["portfolio", "hrp", "allocation", "clustering", "risk parity"],
        "limitations": ["Ignores expected returns by design; covariance is estimated from the stored window."],
    },
    {
        "key": "deflated_sharpe",
        "name": "Deflated Sharpe ratio",
        "category": "statistical",
        "description": "Adjusts an observed Sharpe ratio for skew, kurtosis and the number of "
        "strategies searched, so the best of many backtests is not mistaken for skill.",
        "formula": "Deflated z = (SR - E[max SR | null]) / SE(SR), SE accounting for skew/kurtosis.",
        "params": {"trials": 1},
        "tags": ["statistics", "sharpe", "selection bias", "multiple testing"],
        "limitations": ["Requires an honest trial count; selecting the trial count after the fact defeats it."],
    },
    {
        "key": "stress_test",
        "name": "Market-shock stress test",
        "category": "risk",
        "description": "Translates a market shock into a portfolio impact using each symbol's "
        "beta versus the NEPSE composite.",
        "formula": "impact_i = beta_i × shock; portfolio impact = Σ w_i · impact_i",
        "params": {"symbols": [], "market_shock": -0.10, "window": 250},
        "tags": ["risk", "stress", "scenario", "beta", "market model"],
        "limitations": ["Single-factor: captures systematic exposure only, not idiosyncratic or liquidity risk."],
        "data_requirements": ["daily close", "NEPSE composite index closes"],
    },
    {
        "key": "event_study",
        "name": "Event study (abnormal returns)",
        "category": "statistical",
        "description": "Cumulative abnormal return around supplied event dates using a "
        "market-model benchmark and next-session entry.",
        "formula": "AR_t = r_t - beta·r_m,t; CAR = Σ AR over the event window.",
        "params": {"symbol": "", "event_dates": [], "pre": 5, "post": 20},
        "tags": ["event study", "abnormal return", "car", "research"],
        "limitations": ["No corporate-event calendar is stored, so dates must be supplied; small samples are noisy."],
        "data_requirements": ["daily close", "NEPSE composite index closes", "supplied event dates"],
    },
    {
        "key": "liquidity_drought",
        "name": "Liquidity drought & unusual activity",
        "category": "liquidity",
        "description": "Daily liquidity health: volume drought runs, relative volume, zero-volume "
        "days and an Amihud illiquidity proxy, all from genuine stored volume.",
        "formula": "relative volume = mean(recent) / median(window); Amihud = mean(|r| / turnover)",
        "params": {"symbol": "", "window": 250, "recent": 20},
        "tags": ["liquidity", "volume", "drought", "amihud", "dry up"],
        "limitations": ["Daily data only - no intraday, order-book or trade-level detail.",
                        "Refuses rather than reading missing volume as zero liquidity."],
        "data_requirements": ["daily close", "genuine daily volume", "turnover"],
    },
    {
        "key": "fundamental_forensics",
        "name": "Financial statement forensics",
        "category": "forensics",
        "description": "Reviews stored fundamentals for gaps, staleness, non-positive values, "
        "P/E-vs-price divergence, cross-source conflicts and unreviewed records.",
        "formula": "Rule-based checks over stored fields; each finding carries a severity.",
        "params": {"symbol": ""},
        "tags": ["forensics", "fundamentals", "data quality", "restatement", "red flag"],
        "limitations": ["Flags observations for review; it never concludes fraud.",
                        "Only fields that are actually stored can be checked."],
        "data_requirements": ["stored fundamentals", "daily close"],
    },
    {
        "key": "factor_snapshot",
        "name": "Cross-sectional factor snapshot",
        "category": "factors",
        "description": "Ranks the stored universe on one factor (12-1 momentum, 1-month momentum, "
        "low volatility, liquidity) and reports the top/bottom spread.",
        "formula": "momentum_12_1 = P[-21]/P[-252] - 1; vol_63 = std(log returns, 63) x sqrt(252)",
        "params": {"factor": "momentum_12_1", "top": 20, "min_bars": 260},
        "tags": ["factors", "cross-section", "momentum", "low volatility", "ranking"],
        "limitations": ["Uses the trailing window only; no lag/reporting-delay adjustment is applied."],
        "data_requirements": ["daily close", "genuine daily volume"],
    },
    {
        "key": "coverage_explorer",
        "name": "Data coverage & feasibility explorer",
        "category": "data quality",
        "description": "Reports what data actually exists: securities, bar ranges, fundamentals "
        "coverage and a live per-table row count, with the known gaps listed explicitly.",
        "formula": "Live counts from the market store and the application database.",
        "params": {},
        "tags": ["coverage", "feasibility", "data quality", "provenance", "statistics"],
        "limitations": ["Describes coverage; it does not assess correctness of the values."],
        "data_requirements": ["market store", "application database"],
    },
]


# --------------------------------------------------------------------------- #
# Fundamental-analysis catalogue
# --------------------------------------------------------------------------- #

_FUNDAMENTAL_TOOLS: list[tuple] = [
    ("pe_ratio", "Price / earnings (P/E)", "valuation",
     "Latest price divided by trailing EPS from stored fundamentals.",
     "P/E = price / EPS", ["valuation", "multiple", "cheap", "expensive"], []),
    ("earnings_yield", "Earnings yield", "valuation",
     "Inverse of P/E; earnings per rupee of price.",
     "earnings yield = EPS / price", ["valuation", "yield", "cheap"], []),
    ("pb_ratio", "Price / book (P/B)", "valuation",
     "Price divided by net worth per share.",
     "P/B = price / net_worth_per_share", ["valuation", "book", "cheap"], []),
    ("book_to_price", "Book-to-price", "valuation",
     "Inverse of P/B.",
     "B/P = net_worth_per_share / price", ["valuation", "value", "book"], []),
    ("net_worth_yield", "Net-worth yield", "valuation",
     "Net worth per share divided by price.",
     "nwps / price", ["valuation", "book"], []),
    ("peg_proxy", "PEG proxy", "valuation",
     "P/E divided by the period-over-period EPS growth.",
     "PEG ≈ P/E / (EPS growth %)", ["valuation", "growth", "peg"],
     ["A rough proxy: growth is measured over the stored periods only and is not a forecast."]),
    ("pe_vs_universe", "P/E vs universe median", "valuation",
     "The symbol's P/E against the median P/E of the stored universe.",
     "P/E - median(P/E)", ["valuation", "relative", "rank"],
     ["The universe is every symbol with a stored P/E; it is not sector-neutral."]),
    ("pb_vs_universe", "P/B vs universe median", "valuation",
     "The symbol's P/B against the median P/B of the stored universe.",
     "P/B - median(P/B)", ["valuation", "relative"], []),
    ("historical_pe_percentile", "Historical P/E percentile", "valuation",
     "Where the current P/E sits in the symbol's own stored P/E history.",
     "percentile rank of latest P/E among the symbol's P/E observations",
     ["valuation", "percentile", "history"],
     ["Uses only stored periods; a short history makes the percentile unstable."]),
    ("market_cap_proxy", "Market capitalisation (proxy)", "valuation",
     "Price times a share-count proxy (paid-up capital / par 100).",
     "mktcap ≈ price × (paid_up_capital / 100)", ["size", "market cap"],
     ["Uses par value 100 as a proxy for the reported share count."]),
    ("equity_proxy", "Book equity (proxy)", "strength",
     "Net worth per share times the share-count proxy.",
     "equity ≈ net_worth_per_share × (paid_up_capital / 100)", ["book", "equity", "size"],
     ["Uses par value 100 as a proxy for the reported share count."]),

    ("eps", "Earnings per share", "profitability",
     "Trailing EPS from the stored fundamentals.", "EPS as reported",
     ["earnings", "eps"], []),
    ("net_worth_per_share", "Net worth per share", "profitability",
     "Reported net worth (book value) per share.", "net_worth_per_share as reported",
     ["book", "net worth"], []),
    ("profit", "Reported profit", "profitability",
     "Reported profit for the period.", "profit as reported", ["earnings", "profit"], []),
    ("roe", "Return on equity (proxy)", "profitability",
     "Profit over paid-up capital as a proxy for book equity.",
     "ROE ≈ profit / paid_up_capital", ["profitability", "roe", "quality"],
     ["Paid-up capital is a proxy for book equity; it excludes reserves."]),
    ("profit_per_capital", "Profit per unit capital", "profitability",
     "Reported profit scaled by paid-up capital.",
     "profit / paid_up_capital", ["profitability", "capital"], []),

    ("paid_up_capital", "Paid-up capital", "strength",
     "Reported paid-up (issued) capital.", "paid_up_capital as reported",
     ["capital", "size"], []),
    ("capital_growth", "Paid-up capital growth", "strength",
     "Change in reported paid-up capital across stored periods (bonus/rights effects).",
     "capital_latest / capital_prior - 1", ["capital", "growth", "size"],
     ["Capital growth often reflects bonus/rights issues rather than new money."]),
    ("book_value_growth", "Book-value growth", "strength",
     "Change in net worth per share across stored periods.",
     "nwps_latest / nwps_prior - 1", ["book", "growth"], []),
    ("earnings_volatility", "Earnings volatility", "strength",
     "Dispersion of EPS across stored periods (std / |mean|).",
     "std(EPS) / |mean(EPS)|", ["earnings", "risk", "stability"],
     ["Few stored periods make this unstable."]),

    ("eps_growth", "EPS growth", "growth",
     "Change in EPS across the two most recent stored periods.",
     "growth = EPS_latest / EPS_prior - 1", ["growth", "eps", "trend"], []),
    ("eps_growth_consistency", "EPS growth consistency", "growth",
     "Fraction of period-over-period EPS changes that are positive.",
     "share of positive EPS changes", ["growth", "consistency", "quality"], []),
    ("eps_cagr", "EPS CAGR (stored periods)", "growth",
     "Compound growth of EPS across all stored periods.",
     "CAGR = (EPS_last / EPS_first)^(1/n) - 1", ["growth", "eps", "cagr"],
     ["Periods may not be evenly spaced, so this is a rough annualisation."]),

    ("earnings_rank", "EPS ranking", "ranking",
     "Cross-sectional rank of each symbol's latest EPS.",
     "rank by latest EPS (descending)", ["ranking", "eps", "leader"], []),
    ("value_rank", "Value ranking (low P/E)", "ranking",
     "Cross-sectional rank by P/E, cheapest first.",
     "rank by latest P/E (ascending)", ["ranking", "value", "cheap"], []),
    ("quality_rank", "Quality ranking (ROE proxy)", "ranking",
     "Cross-sectional rank by the ROE proxy, highest first.",
     "rank by profit / paid_up_capital (descending)", ["ranking", "quality", "roe"], []),
    ("growth_rank", "Growth ranking (EPS)", "ranking",
     "Cross-sectional rank by EPS growth, highest first.",
     "rank by EPS growth (descending)", ["ranking", "growth"], []),
    ("composite_rank", "Composite value + quality rank", "ranking",
     "Average percentile of value rank and quality rank.",
     "mean(value percentile, quality percentile)", ["ranking", "composite", "value", "quality"], []),
    ("cheap_quality_screen", "Cheap and high-quality screen", "ranking",
     "Bottom-third P/E and top-third ROE across the universe.",
     "P/E percentile < 33 and ROE percentile > 67", ["screen", "value", "quality"], []),

    ("negative_eps_flag", "Negative-earnings flag", "forensics",
     "Flags symbols whose latest EPS is negative.",
     "EPS < 0", ["forensics", "flag", "loss"], ["A single loss-making period is not proof of distress."]),
    ("valuation_anomaly", "Valuation anomaly flag", "forensics",
     "Flags P/E more than 3 cross-sectional standard deviations from the mean.",
     "|z(P/E)| > 3", ["forensics", "outlier", "valuation"], []),

    ("dividend_yield", "Dividend yield", "dividends",
     "Dividend per share over price.",
     "dividend yield = DPS / price", ["dividend", "yield"],
     ["DPS is not populated in the current dataset, so this returns not-available rather than zero."]),
]


def build_fundamentals() -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for key, name, category, desc, formula, tags, lim in _FUNDAMENTAL_TOOLS:
        out.append(
            {
                "id": f"fund.{key}",
                "key": key,
                "kind": "fundamental",
                "name": name,
                "category": category,
                "description": desc,
                "formula": formula,
                "params": {},
                "tags": list(tags),
                "limitations": list(lim),
                "data_requirements": ["stored fundamentals (eps, pe, net_worth_per_share, "
                                      "profit, paid_up_capital, price)"],
                "run": {"engine": "fundamental", "fn": key},
                "status": "available" if key != "dividend_yield" else "blocked",
            }
        )
    return out


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #

_BUILDERS = {
    "scanner": build_scanners,
    "algorithm": build_algorithms,
    "fundamental": build_fundamentals,
}
_cache: dict[str, list[dict[str, Any]]] = {}


def all_tools(kind: str | None = None) -> list[dict[str, Any]]:
    """Return catalogue tools, optionally filtered by kind."""
    if kind is None:
        out: list[dict[str, Any]] = []
        for k in _BUILDERS:
            out.extend(all_tools(k))
        return out
    if kind not in _BUILDERS:
        raise ValueError(f"unknown catalogue kind {kind!r}; expected one of {sorted(_BUILDERS)}")
    if kind not in _cache:
        _cache[kind] = _BUILDERS[kind]()
    return _cache[kind]


def categories(kind: str) -> dict[str, str]:
    if kind == "scanner":
        return dict(_SCANNER_CATEGORIES)
    if kind == "algorithm":
        return dict(_ALGORITHM_CATEGORIES)
    return {
        "valuation": "Valuation",
        "profitability": "Profitability",
        "strength": "Financial strength",
        "ranking": "Ranking",
        "dividends": "Dividends",
        "growth": "Growth",
    }


def search(kind: str | None, query: str = "", category: str = "all") -> list[dict[str, Any]]:
    """Search the catalogue by name, short label, category, tags, formula, description."""
    terms = [t for t in (query or "").lower().split() if t]
    tools = all_tools(kind)
    out = []
    for t in tools:
        if category and category != "all" and t.get("category") != category:
            continue
        if not terms:
            out.append(t)
            continue
        hay = " ".join(
            str(x)
            for x in [
                t.get("name"), t.get("short"), t.get("category"), t.get("description"),
                t.get("formula"), *t.get("tags", []), t.get("key"),
            ]
        ).lower()
        if all(term in hay for term in terms):
            out.append(t)
    return out


def get_tool(tool_id: str) -> dict[str, Any] | None:
    for t in all_tools():
        if t["id"] == tool_id:
            return t
    return None


def catalog_summary() -> dict[str, Any]:
    """Counts per kind, distinct by id, plus a health check on run paths."""
    summary: dict[str, Any] = {}
    for kind in _BUILDERS:
        tools = all_tools(kind)
        ids = {t["id"] for t in tools}
        summary[kind] = {
            "total": len(tools),
            "distinct": len(ids),
            "categories": len({t.get("category") for t in tools}),
        }
    summary["health"] = catalog_health()
    return summary


def catalog_health() -> dict[str, Any]:
    """Verify every tool names an execution path that actually exists."""
    problems: list[str] = []
    try:
        from megatool.backtest import STRATEGIES
    except Exception:  # pragma: no cover
        STRATEGIES = {}
    for t in all_tools("algorithm"):
        run = t.get("run", {})
        if run.get("engine") == "backtest" and run.get("strategy") not in STRATEGIES:
            problems.append(f"{t['id']}: missing strategy key {run.get('strategy')!r}")
        if run.get("engine") == "analysis" and run.get("fn") not in _ANALYSIS_FUNCS:
            problems.append(f"{t['id']}: missing analysis fn {run.get('fn')!r}")
    for t in all_tools("scanner"):
        tree = t.get("run", {}).get("tree")
        if not tree or not tree.get("conditions"):
            problems.append(f"{t['id']}: empty condition tree")
    return {"ok": not problems, "problems": problems, "tools": len(all_tools())}


# --------------------------------------------------------------------------- #
# Analysis algorithm implementations (small, deterministic, testable)
# --------------------------------------------------------------------------- #


def _import_np():
    import numpy as np

    return np


def run_monte_carlo(
    *, start: float = 100.0, drift: float = 0.08, volatility: float = 0.25,
    days: int = 252, paths: int = 1000, seed: int = 42, returns: list[float] | None = None,
) -> dict[str, Any]:
    """Monte Carlo terminal-wealth distribution.

    GBM when ``returns`` is None, else a bootstrap of the supplied return
    series. Fully reproducible under a fixed seed.
    """
    np = _import_np()
    rng = np.random.default_rng(int(seed))
    paths = max(1, int(paths))
    days = max(1, int(days))
    dt = 1.0 / 252.0
    if returns:
        r = np.asarray(returns, dtype=float)
        r = r[np.isfinite(r)]
        if r.size == 0:
            raise ValueError("returns series has no finite observations")
        draws = rng.choice(r, size=(paths, days), replace=True)
        term = float(start) * np.prod(1.0 + draws, axis=1)
        method = "bootstrap"
    else:
        mu, sig = float(drift), float(volatility)
        z = rng.standard_normal((paths, days))
        log_paths = np.cumsum((mu - 0.5 * sig * sig) * dt + sig * np.sqrt(dt) * z, axis=1)
        term = float(start) * np.exp(log_paths[:, -1])
        method = "gbm"
    term = term[np.isfinite(term)]
    pct = {p: float(np.percentile(term, p)) for p in (5, 25, 50, 75, 95)}
    return {
        "method": method,
        "paths": int(term.size),
        "days": days,
        "start": float(start),
        "median": pct[50],
        "percentiles": {f"p{p}": v for p, v in pct.items()},
        "prob_gain": float(np.mean(term > float(start))),
        "prob_loss_20pct": float(np.mean(term < 0.8 * float(start))),
        "seed": int(seed),
    }


def run_risk_of_ruin(
    *, win_rate: float = 0.5, avg_win: float = 0.02, avg_loss: float = 0.02,
    risk_per_trade: float = 0.01, trades: int = 200, paths: int = 1000,
    ruin_threshold: float = 0.5, seed: int = 42,
) -> dict[str, Any]:
    """Losing-streak / ruin simulator with explicit IID assumptions."""
    np = _import_np()
    rng = np.random.default_rng(int(seed))
    paths = max(1, int(paths))
    trades = max(1, int(trades))
    wins = rng.random((paths, trades)) < float(win_rate)
    step = np.where(
        wins,
        float(risk_per_trade) * (float(avg_win) / max(1e-9, float(avg_loss))),
        -float(risk_per_trade),
    )
    equity = np.cumprod(1.0 + step, axis=1)
    min_eq = equity.min(axis=1)
    return {
        "paths": paths,
        "trades": trades,
        "win_rate": float(win_rate),
        "risk_per_trade": float(risk_per_trade),
        "prob_ruin": float(np.mean(min_eq <= float(ruin_threshold))),
        "median_final": float(np.median(equity[:, -1])),
        "median_max_drawdown": float(np.median(1.0 - min_eq)),
        "p95_max_drawdown": float(np.percentile(1.0 - min_eq, 95)),
        "seed": int(seed),
    }


# --------------------------------------------------------------------------- #
# Store-backed analysis algorithms
# --------------------------------------------------------------------------- #

#: Optional provider returning an already-open MarketStore. The API server sets
#: this so analysis code reuses the server's live connection instead of trying to
#: open a second one: DuckDB allows only one read-write connection to a file, and
#: a read-only open from the same process would collide with it. Standalone
#: callers leave it unset and get a read-only store opened here.
_STORE_PROVIDER: Any = None


def set_store_provider(provider: Any) -> None:
    """Register a callable returning the store analysis code should use."""
    global _STORE_PROVIDER
    _STORE_PROVIDER = provider


def store_provider() -> Any:
    """Return the currently registered provider, or ``None`` when unset."""
    return _STORE_PROVIDER


def _store():
    """Return a market store for analysis.

    If the host application (the API server) has registered a provider, reuse
    its open store. Otherwise open the store read-only: a read-write connection
    would take DuckDB's exclusive lock and collide with a running server.
    Analyses never mutate the store.
    """
    if _STORE_PROVIDER is not None:
        return _STORE_PROVIDER()
    from megatool.market_store import MarketStore

    return MarketStore(read_only=True)


def _symbol_frame(symbol: str):
    store = _store()
    df = store.get_bars(str(symbol).upper())
    return store, df


def _benchmark_closes():
    from megatool.ranking import NEPSE_COMPOSITE_INDEX

    try:
        return _store().index_closes(NEPSE_COMPOSITE_INDEX)
    except Exception:  # pragma: no cover - defensive
        return None


def run_rolling_beta(symbol: str, benchmark: str | None = None, window: int = 60) -> dict[str, Any]:
    """Rolling beta of a security versus the NEPSE composite (or a named index)."""
    from megatool.stats import rolling_beta

    store, df = _symbol_frame(symbol)
    if df is None or df.empty:
        return {"symbol": symbol, "available": False, "reason": "no stored history"}
    if benchmark:
        bench = store.index_closes(benchmark)
    else:
        bench = _benchmark_closes()
    if bench is None or getattr(bench, "empty", True):
        return {
            "symbol": symbol, "available": False,
            "reason": "benchmark series unavailable - not substituted",
        }
    r_s = df["close"].astype(float).pct_change().to_numpy()
    r_b = bench["close"].astype(float).pct_change().to_numpy()
    n = min(len(r_s), len(r_b))
    beta = rolling_beta(r_s[-n:], r_b[-n:], int(window))
    latest = next((v for v in reversed(beta) if v is not None), None)
    return {
        "symbol": symbol, "available": True, "window": int(window),
        "latest_beta": latest, "series_tail": beta[-20:], "bars": int(n),
        "benchmark": benchmark or "NEPSE composite",
    }


def run_volatility_percentile(symbol: str, window: int = 20, lookback: int = 252) -> dict[str, Any]:
    """Percentile rank of the latest realized volatility in its own history."""
    from megatool.stats import volatility_percentile

    _, df = _symbol_frame(symbol)
    if df is None or df.empty:
        return {"symbol": symbol, "available": False, "reason": "no stored history"}
    ret = df["close"].astype(float).pct_change()
    realized = ret.rolling(int(window)).std() * (252 ** 0.5)
    res = volatility_percentile(realized.to_numpy(), lookback=int(lookback))
    res.update({"symbol": symbol, "available": res.get("percentile") is not None,
                "window": int(window)})
    return res


def run_technical_rating(symbol: str) -> dict[str, Any]:
    """Composite technical rating from the latest indicator readings."""
    from megatool.ta.confluence import technical_rating

    import megatool.ta as ta

    _, df = _symbol_frame(symbol)
    if df is None or df.empty:
        return {"symbol": symbol, "available": False, "reason": "no stored history"}
    data = {
        "close": df["close"].astype(float).to_numpy(),
        "high": df["high"].astype(float).to_numpy() if "high" in df else None,
        "low": df["low"].astype(float).to_numpy() if "low" in df else None,
    }
    close = data["close"]
    latest: dict[str, Any] = {"close": float(close[-1])}
    try:
        latest["sma_fast"] = ta.compute("sma", {"close": close}, period=20).latest().get("sma")
        latest["sma_slow"] = ta.compute("sma", {"close": close}, period=50).latest().get("sma")
        latest["rsi"] = ta.compute("rsi", {"close": close}, period=14).latest().get("rsi")
        macd = ta.compute("macd", {"close": close})
        latest["macd_hist"] = macd.latest().get("macd_histogram")
        latest["adx"] = ta.compute("adx", {"high": data["high"], "low": data["low"], "close": close}).latest().get("adx")
        st = ta.compute("stochastic", {"high": data["high"], "low": data["low"], "close": close})
        latest["stoch_k"] = st.latest().get("stochastic_k")
    except Exception as exc:  # pragma: no cover - defensive
        return {"symbol": symbol, "available": False, "reason": f"indicator error: {exc}"}
    rating = technical_rating(latest)
    rating.update({"symbol": symbol, "available": True, "inputs": latest})
    return rating


def run_mtf_confluence(symbol: str, fast: int = 20, slow: int = 50, rsi_period: int = 14) -> dict[str, Any]:
    """Daily/weekly/monthly trend-momentum-volatility confluence."""
    from megatool.ta.multitimeframe import mtf_confluence

    _, df = _symbol_frame(symbol)
    if df is None or df.empty:
        return {"symbol": symbol, "available": False, "reason": "no stored history"}
    res = mtf_confluence(df, fast=fast, slow=slow, rsi_period=rsi_period)
    if isinstance(res, dict):
        res.setdefault("symbol", symbol)
        res["available"] = True
    return res


def run_correlation_matrix(symbols: list[str], window: int = 120, method: str = "pearson") -> dict[str, Any]:
    """Pairwise return correlation across the requested symbols."""
    from megatool.stats import correlation_matrix

    store = _store()
    series: dict[str, Any] = {}
    missing: list[str] = []
    for s in symbols:
        df = store.get_bars(str(s).upper())
        if df is None or df.empty or len(df) < 5:
            missing.append(str(s).upper())
            continue
        series[str(s).upper()] = df["close"].astype(float).pct_change().to_numpy()[-int(window):]
    if len(series) < 2:
        return {"available": False, "reason": "fewer than two symbols with enough history",
                "missing": missing}
    res = correlation_matrix(series, method=method)
    res["available"] = True
    res["missing"] = missing
    return res


def _project_simplex(v):
    """Euclidean projection of a vector onto {w >= 0, sum(w) = 1}."""
    np = _import_np()
    n = v.size
    u = np.sort(v)[::-1]
    css = np.cumsum(u)
    rho = np.nonzero(u * np.arange(1, n + 1) > (css - 1))[0][-1]
    theta = (css[rho] - 1) / (rho + 1.0)
    return np.maximum(v - theta, 0)


def _solve_frontier(mu, cov, *, risk_free=0.05, n_points=25, iters=4000, ridge=1e-8):
    """Long-only frontier by sweeping risk-aversion over projected gradient.

    Returns minimum-variance and max-Sharpe portfolios plus the frontier curve.
    Implemented without scipy so the platform keeps its declared dependency set.
    """
    np = _import_np()
    n = mu.size
    cov = cov + ridge * np.eye(n)
    ones = np.ones(n)

    def objective_grad(w, lam):
        # minimise wᵀΣw - lam·(wᵀμ)  (long-only, sum=1)
        grad = 2.0 * cov @ w - lam * mu
        return float(w @ cov @ w) - lam * float(w @ mu), grad

    def solve(lam, w0):
        w = w0.copy()
        lr = 1.0 / (2.0 * (np.trace(cov) / n) + lam * np.abs(mu).mean() + 1e-9)
        for _ in range(iters):
            _, g = objective_grad(w, lam)
            w = _project_simplex(w - lr * g)
        return w

    def stats(w):
        ret = float(w @ mu)
        vol = float(np.sqrt(max(w @ cov @ w, 0.0)))
        return ret, vol, ((ret - risk_free) / vol if vol > 0 else None)

    w_eq = ones / n
    # Minimum variance = lambda 0.
    w_mv = solve(0.0, w_eq)
    # Max Sharpe searched over lambda.
    lambdas = np.concatenate([np.linspace(0.0, 5.0, 40), np.linspace(5.0, 200.0, 30)])
    best_w, best_s = w_mv, stats(w_mv)[2] or -1e9
    for lam in lambdas:
        w = solve(float(lam), w_mv)
        s = stats(w)[2]
        if s is not None and s > best_s:
            best_s, best_w = s, w
    curve = []
    for lam in np.linspace(0.0, float(lambdas.max()), n_points):
        w = solve(float(lam), w_mv)
        r, v, s = stats(w)
        curve.append({"lambda": float(lam), "return": r, "volatility": v, "sharpe": s,
                      "weights": [float(x) for x in w]})
    return {"min_variance": w_mv, "max_sharpe": best_w, "curve": curve, "stats": stats}


def run_efficient_frontier(symbols: list[str], window: int = 250, risk_free: float = 0.05) -> dict[str, Any]:
    """Long-only mean-variance frontier from historical return statistics."""
    np = _import_np()
    store = _store()
    rets: dict[str, Any] = {}
    for s in symbols:
        df = store.get_bars(str(s).upper())
        if df is None or df.empty or len(df) < 30:
            continue
        r = df["close"].astype(float).pct_change().to_numpy()[-int(window):]
        r = r[np.isfinite(r)]
        if r.size >= 30:
            rets[str(s).upper()] = r
    if len(rets) < 2:
        return {"available": False, "reason": "need at least two symbols with >=30 returns"}
    names = list(rets)
    n = min(a.size for a in rets.values())
    R = np.column_stack([rets[k][-n:] for k in names])
    mu_daily = R.mean(axis=0)
    cov_daily = np.cov(R, rowvar=False)
    ann = 252
    mu = mu_daily * ann
    cov = cov_daily * ann
    solver = _solve_frontier(mu, cov, risk_free=float(risk_free))
    mv = solver["min_variance"]
    ms = solver["max_sharpe"]
    r_mv, v_mv, s_mv = solver["stats"](mv)
    r_ms, v_ms, s_ms = solver["stats"](ms)
    return {
        "available": True,
        "symbols": names,
        "window": int(window),
        "observations": int(n),
        "annualisation": ann,
        "min_variance": {"weights": {k: float(w) for k, w in zip(names, mv)},
                         "return": r_mv, "volatility": v_mv, "sharpe": s_mv},
        "max_sharpe": {"weights": {k: float(w) for k, w in zip(names, ms)},
                       "return": r_ms, "volatility": v_ms, "sharpe": s_ms},
        "frontier": [{k: p[k] for k in ("lambda", "return", "volatility", "sharpe")}
                     for p in solver["curve"]],
        "assumptions": [
            "Expected returns are historical sample means - highly unstable and not forecasts.",
            f"Covariance from the trailing {window} daily returns, annualised by {ann}.",
            "Long-only, fully invested (weights >= 0, sum = 1). No transaction costs.",
        ],
    }


_SIGNAL_DEFS: dict[str, str] = {
    "rsi_oversold": "RSI(14) below 30",
    "rsi_overbought": "RSI(14) above 70",
    "macd_bullish_cross": "MACD crosses above its signal line",
    "donchian_breakout": "close makes a new 20-bar high",
    "volume_spike": "volume at least 2x its 20-bar mean",
}


def run_signal_outcomes(symbol: str, signal: str = "rsi_oversold",
                        horizons: list[int] | None = None) -> dict[str, Any]:
    """Forward returns following a signal, with next-bar entry (no look-ahead)."""
    np = _import_np()
    import megatool.ta as ta

    horizons = horizons or [5, 10, 20]
    _, df = _symbol_frame(symbol)
    if df is None or df.empty or len(df) < 80:
        return {"symbol": symbol, "available": False, "reason": "insufficient history"}
    close = df["close"].astype(float).to_numpy()
    high = df["high"].astype(float).to_numpy()
    low = df["low"].astype(float).to_numpy()
    volume = df["volume"].astype(float).to_numpy() if "volume" in df else None
    n = len(close)
    mask = np.zeros(n, dtype=bool)
    if signal == "rsi_oversold":
        v = ta.compute("rsi", {"close": close}, period=14).values["rsi"]
        mask = np.array([(x == x and x < 30) for x in v])
    elif signal == "rsi_overbought":
        v = ta.compute("rsi", {"close": close}, period=14).values["rsi"]
        mask = np.array([(x == x and x > 70) for x in v])
    elif signal == "macd_bullish_cross":
        m = ta.compute("macd", {"close": close})
        macd = m.values["macd"]
        sig = m.values.get("macd_signal")
        if sig is None:
            return {"symbol": symbol, "available": False, "reason": "macd signal unavailable"}
        for i in range(1, n):
            if macd[i] == macd[i] and sig[i] == sig[i] and macd[i - 1] == macd[i - 1] and sig[i - 1] == sig[i - 1]:
                if macd[i - 1] <= sig[i - 1] and macd[i] > sig[i]:
                    mask[i] = True
    elif signal == "donchian_breakout":
        for i in range(20, n):
            if close[i] == close[i] and close[i] > np.nanmax(close[i - 20:i]):
                mask[i] = True
    elif signal == "volume_spike":
        if volume is None:
            return {"symbol": symbol, "available": False, "reason": "no volume column"}
        for i in range(20, n):
            base = np.nanmean(volume[i - 20:i])
            if base > 0 and volume[i] == volume[i] and volume[i] >= 2 * base:
                mask[i] = True
    else:
        return {"symbol": symbol, "available": False,
                "reason": f"unknown signal {signal!r}; known: {sorted(_SIGNAL_DEFS)}"}

    results: dict[str, Any] = {}
    for h in horizons:
        fwd = []
        for i in np.nonzero(mask)[0]:
            if i + h < n and close[i + 1] == close[i + 1] and close[i + 1] > 0:
                fwd.append(close[i + h] / close[i + 1] - 1.0)  # enter on the next bar
        arr = np.asarray(fwd, dtype=float)
        arr = arr[np.isfinite(arr)]
        results[f"h{h}"] = {
            "n": int(arr.size),
            "mean": float(arr.mean()) if arr.size else None,
            "median": float(np.median(arr)) if arr.size else None,
            "hit_rate": float(np.mean(arr > 0)) if arr.size else None,
        }
    return {
        "symbol": symbol, "available": True, "signal": signal,
        "signal_definition": _SIGNAL_DEFS.get(signal, signal),
        "signals": int(mask.sum()), "bars": int(n),
        "entry": "next session close after the signal bar (no look-ahead)",
        "horizons": results,
        "note": "Overlapping windows are not adjusted for; treat as descriptive, not inferential.",
    }


# --------------------------------------------------------------------------- #
# Valuation engines (Part C)
# --------------------------------------------------------------------------- #

def run_dcf(
    *, fcf0: float = 1_000_000_000.0, growth: float = 0.08, wacc: float = 0.13,
    terminal_growth: float = 0.04, years: int = 5, net_debt: float = 0.0,
    shares: float = 100_000_000.0, price: float | None = None,
) -> dict[str, Any]:
    """Discounted cash-flow valuation with an explicit sensitivity grid.

    This is a model. Its output is entirely determined by the assumptions the
    caller supplies; none of them are estimated or fetched here, so the result
    is transparent rather than authoritative.
    """
    years = max(1, int(years))
    if wacc <= terminal_growth:
        return {"available": False,
                "reason": "WACC must exceed terminal growth for the Gordon terminal value to be finite"}
    if shares <= 0:
        return {"available": False, "reason": "shares must be positive"}

    def value(g=growth, w=wacc, tg=terminal_growth):
        fcf = float(fcf0)
        pv = 0.0
        proj = []
        for t in range(1, years + 1):
            fcf = fcf * (1.0 + g)
            disc = fcf / ((1.0 + w) ** t)
            pv += disc
            proj.append({"year": t, "fcf": fcf, "pv": disc})
        tv = fcf * (1.0 + tg) / (w - tg)
        pv_tv = tv / ((1.0 + w) ** years)
        ev = pv + pv_tv
        equity = ev - net_debt
        return {"projection": proj, "pv_explicit": pv, "terminal_value": tv,
                "pv_terminal": pv_tv, "enterprise_value": ev, "equity_value": equity,
                "per_share": equity / shares}

    base = value()
    sens = []
    for dw in (-0.02, -0.01, 0.0, 0.01, 0.02):
        row = {"wacc": round(wacc + dw, 4), "values": {}}
        for dg in (-0.01, -0.005, 0.0, 0.005, 0.01):
            tg = terminal_growth + dg
            if (wacc + dw) > tg:
                row["values"][f"{tg:.3f}"] = round(value(w=wacc + dw, tg=tg)["per_share"], 4)
        sens.append(row)
    out = {
        "available": True,
        "assumptions": {"fcf0": fcf0, "growth": growth, "wacc": wacc,
                        "terminal_growth": terminal_growth, "years": years,
                        "net_debt": net_debt, "shares": shares},
        "projection": base["projection"],
        "terminal_value": base["terminal_value"],
        "pv_explicit": base["pv_explicit"],
        "pv_terminal": base["pv_terminal"],
        "enterprise_value": base["enterprise_value"],
        "equity_value": base["equity_value"],
        "per_share": base["per_share"],
        "sensitivity": sens,
        "note": "Model output under the stated assumptions. Change any assumption and the value changes; "
                "this is not a price target.",
    }
    if price is not None and price > 0:
        out["market_price"] = price
        out["upside"] = base["per_share"] / price - 1.0
    return out


def run_reverse_dcf(
    *, target_price: float, fcf0: float = 1_000_000_000.0, wacc: float = 0.13,
    terminal_growth: float = 0.04, years: int = 5, net_debt: float = 0.0,
    shares: float = 100_000_000.0, lo: float = -0.5, hi: float = 1.0,
) -> dict[str, Any]:
    """Solve for the FCF growth the market price implies (bisection).

    Answers "what growth would justify this price?" - the assumption is made
    explicit instead of a single point estimate being reported.
    """
    if target_price <= 0:
        return {"available": False, "reason": "target_price must be positive"}

    def per_share(g):
        r = run_dcf(fcf0=fcf0, growth=g, wacc=wacc, terminal_growth=terminal_growth,
                    years=years, net_debt=net_debt, shares=shares)
        return r["per_share"] if r.get("available") else None

    f_lo, f_hi = per_share(lo), per_share(hi)
    if f_lo is None or f_hi is None:
        return {"available": False, "reason": "assumptions make the model undefined over the search range"}
    if not (f_lo <= target_price <= f_hi):
        return {"available": False,
                "reason": f"target price outside the achievable range [{f_lo:.2f}, {f_hi:.2f}] for growth in "
                          f"[{lo}, {hi}]"}
    for _ in range(200):
        mid = (lo + hi) / 2.0
        v = per_share(mid)
        if v is None:
            return {"available": False, "reason": "model became undefined mid-search"}
        if abs(v - target_price) < 1e-9:
            break
        if v < target_price:
            lo = mid
        else:
            hi = mid
    implied = (lo + hi) / 2.0
    return {
        "available": True,
        "implied_growth": implied,
        "target_price": target_price,
        "assumptions": {"fcf0": fcf0, "wacc": wacc, "terminal_growth": terminal_growth,
                        "years": years, "net_debt": net_debt, "shares": shares},
        "note": "The growth rate that, under the other stated assumptions, reproduces the target price.",
    }


# --------------------------------------------------------------------------- #
# Portfolio & risk engines (Part C)
# --------------------------------------------------------------------------- #

def _single_linkage_order(corr):
    """Leaf ordering from single-linkage clustering of a correlation matrix."""
    np = _import_np()
    n = corr.shape[0]
    dist = np.sqrt(np.maximum(0.0, 0.5 * (1.0 - corr)))
    active = {i: [i] for i in range(n)}
    d = dist.copy()
    np.fill_diagonal(d, np.inf)
    while len(active) > 1:
        # Closest pair of current clusters.
        keys = list(active)
        best = None
        for a_i, a in enumerate(keys):
            for b in keys[a_i + 1:]:
                m = float(np.min(d[np.ix_(active[a], active[b])]))
                if best is None or m < best[0]:
                    best = (m, a, b)
        _, a, b = best
        active[a] = active[a] + active[b]
        del active[b]
    return list(active.values())[0]


def run_hrp_portfolio(symbols: list[str], window: int = 250) -> dict[str, Any]:
    """Hierarchical risk parity (López de Prado) - allocation without matrix inversion."""
    np = _import_np()
    store = _store()
    rets: dict[str, Any] = {}
    for s in symbols:
        df = store.get_bars(str(s).upper())
        if df is None or df.empty or len(df) < 30:
            continue
        r = df["close"].astype(float).pct_change().to_numpy()[-int(window):]
        r = r[np.isfinite(r)]
        if r.size >= 30:
            rets[str(s).upper()] = r
    if len(rets) < 2:
        return {"available": False, "reason": "need at least two symbols with >=30 returns"}
    names = list(rets)
    n = min(a.size for a in rets.values())
    R = np.column_stack([rets[k][-n:] for k in names])
    corr = np.corrcoef(R, rowvar=False)
    order = _single_linkage_order(corr)
    cov = np.cov(R, rowvar=False)
    n_assets = len(names)

    def cluster_var(idx):
        sub = cov[np.ix_(idx, idx)]
        iv = 1.0 / np.diag(sub)
        iv = iv / iv.sum()
        return float(iv @ sub @ iv)

    def bisect(idx, w):
        if len(idx) == 1:
            return
        half = len(idx) // 2
        left, right = idx[:half], idx[half:]
        v_left, v_right = cluster_var(left), cluster_var(right)
        alpha = 1.0 - v_left / (v_left + v_right)
        for i in left:
            w[i] *= alpha
        for i in right:
            w[i] *= (1.0 - alpha)
        bisect(left, w)
        bisect(right, w)

    w = np.ones(n_assets)
    bisect(order, w)
    w = w / w.sum()
    # Diversification ratio vs equal weight.
    port_vol = float(np.sqrt(w @ cov @ w))
    eq = np.ones(n_assets) / n_assets
    eq_vol = float(np.sqrt(eq @ cov @ eq))
    return {
        "available": True,
        "symbols": names,
        "window": int(window),
        "observations": int(n),
        "weights": {k: float(x) for k, x in zip(names, w)},
        "annualised_volatility": port_vol * np.sqrt(252),
        "equal_weight_volatility": eq_vol * np.sqrt(252),
        "cluster_order": [names[i] for i in order],
        "assumptions": [
            "Allocation uses covariance structure only - HRP ignores expected returns by design.",
            f"Covariance from the trailing {window} daily returns.",
            "Long-only, fully invested (weights >= 0, sum = 1).",
        ],
    }


def _norm_cdf(x: float) -> float:
    import math

    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def run_deflated_sharpe(symbol: str, trials: int = 1, window: int = 0) -> dict[str, Any]:
    """Deflated Sharpe ratio (Bailey & López de Prado).

    Adjusts an observed Sharpe ratio for skewness, kurtosis and the number of
    trials that were searched, because the best of many backtests looks good by
    chance alone.
    """
    np = _import_np()
    _, df = _symbol_frame(symbol)
    if df is None or df.empty or len(df) < 30:
        return {"symbol": symbol, "available": False, "reason": "insufficient history"}
    r = df["close"].astype(float).pct_change().dropna().to_numpy()
    if window and 0 < window < r.size:
        r = r[-int(window):]
    r = r[np.isfinite(r)]
    n = r.size
    if n < 20 or r.std(ddof=1) == 0:
        return {"symbol": symbol, "available": False, "reason": "degenerate return series"}
    sr = float(r.mean() / r.std(ddof=1)) * np.sqrt(252)  # annualised
    skew = float(((r - r.mean()) ** 3).mean() / r.std(ddof=1) ** 3)
    kurt = float(((r - r.mean()) ** 4).mean() / r.std(ddof=1) ** 4)
    trials = max(1, int(trials))
    # Expected maximum Sharpe under the null (Euler-Mascheroni approximation).
    emc = 0.5772156649
    e_max = ((1 - emc) * _norm_inv(1 - 1.0 / trials) +
             emc * _norm_inv(1 - 1.0 / (trials * 2.718281828459045))) if trials > 1 else 0.0
    se = np.sqrt((1.0 - skew * sr / np.sqrt(252) + (kurt - 1.0) / 4.0 * (sr / np.sqrt(252)) ** 2) / (n - 1))
    # Compare the observed annualised Sharpe against the expected max, in SE units.
    se_ann = float(se) * np.sqrt(252)
    if se_ann <= 0:
        z = 0.0
    else:
        z = (sr - e_max * se_ann) / se_ann
    return {
        "symbol": symbol, "available": True,
        "sharpe_annualised": sr,
        "skew": skew, "kurtosis": kurt, "observations": n, "trials": trials,
        "expected_max_sharpe_under_null": e_max * se_ann if trials > 1 else 0.0,
        "deflated_z": float(z),
        "prob_true_sharpe_positive": _norm_cdf(float(z)),
        "note": "A high Sharpe from a search over many strategies is discounted here; "
                "prob < 0.95 is not evidence of skill.",
    }


def _norm_inv(p: float) -> float:
    """Inverse standard-normal CDF (Acklam's rational approximation)."""
    import math

    if p <= 0.0:
        return -math.inf
    if p >= 1.0:
        return math.inf
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00,
         3.754408661907416e+00]
    plow, phigh = 0.02425, 1 - 0.02425
    if p < plow:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    if p > phigh:
        q = math.sqrt(-2 * math.log(1 - p))
        return -(((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    q = p - 0.5
    r = q * q
    return (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5])*q / (((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1)


def run_stress_test(symbols: list[str], market_shock: float = -0.10,
                    weights: dict[str, float] | None = None, window: int = 250) -> dict[str, Any]:
    """Translate a market shock into a portfolio impact via each symbol's beta."""
    np = _import_np()
    store = _store()
    bench = _benchmark_closes()
    if bench is None or getattr(bench, "empty", True):
        return {"available": False, "reason": "benchmark series unavailable - not substituted"}
    rb = bench["close"].astype(float).pct_change().to_numpy()
    betas: dict[str, float] = {}
    for s in symbols:
        df = store.get_bars(str(s).upper())
        if df is None or df.empty or len(df) < 30:
            continue
        rs = df["close"].astype(float).pct_change().to_numpy()
        n = min(len(rs), len(rb)) - 1
        x, y = rb[-n:], rs[-n:]
        mask = np.isfinite(x) & np.isfinite(y)
        x, y = x[mask], y[mask]
        if x.size < 20 or x.std() == 0:
            continue
        beta = float(np.cov(x, y, ddof=1)[0, 1] / x.var(ddof=1))
        betas[str(s).upper()] = beta
    if not betas:
        return {"available": False, "reason": "no symbols had usable history against the benchmark"}
    names = list(betas)
    if weights:
        w = np.array([float(weights.get(k, 0.0)) for k in names])
        if w.sum() <= 0:
            w = np.ones(len(names))
    else:
        w = np.ones(len(names))
    w = w / w.sum()
    impacts = {k: betas[k] * float(market_shock) for k in names}
    port = float(sum(w[i] * impacts[names[i]] for i in range(len(names))))
    return {
        "available": True,
        "scenario": {"market_shock": float(market_shock)},
        "betas": betas,
        "weights": {names[i]: float(w[i]) for i in range(len(names))},
        "symbol_impacts": impacts,
        "portfolio_impact": port,
        "note": "Single-factor (market-model) stress: it captures systematic exposure only. "
                "It says nothing about idiosyncratic events or liquidity.",
    }


def run_event_study(symbol: str, event_dates: list[str], pre: int = 5, post: int = 20) -> dict[str, Any]:
    """Event study: cumulative abnormal return around supplied event dates.

    There is no stored corporate-event calendar, so event dates must be supplied
    by the caller; the engine never invents them.
    """
    if not event_dates:
        return {"available": False,
                "reason": "no event dates supplied; the dataset has no sourced event calendar"}
    np = _import_np()
    import pandas as pd

    store = _store()
    df = store.get_bars(str(symbol).upper())
    if df is None or df.empty or len(df) < 60:
        return {"available": False, "reason": "insufficient price history"}
    bench = _benchmark_closes()
    if bench is None or getattr(bench, "empty", True):
        return {"available": False, "reason": "benchmark series unavailable - not substituted"}
    s = df[["trading_date", "close"]].copy()
    s["trading_date"] = pd.to_datetime(s["trading_date"]).dt.normalize()
    b = bench[["trading_date", "close"]].copy()
    b["trading_date"] = pd.to_datetime(b["trading_date"]).dt.normalize()
    m = s.merge(b, on="trading_date", suffixes=("_s", "_b")).sort_values("trading_date")
    if len(m) < 60:
        return {"available": False, "reason": "fewer than 60 aligned bars"}
    m["rs"] = m["close_s"].pct_change()
    m["rb"] = m["close_b"].pct_change()
    dates = m["trading_date"].tolist()
    est = m.iloc[:-1]
    x, y = est["rb"].to_numpy(), est["rs"].to_numpy()
    mask = np.isfinite(x) & np.isfinite(y)
    beta = float(np.cov(x[mask], y[mask], ddof=1)[0, 1] / x[mask].var(ddof=1)) if mask.sum() > 5 and x[mask].var() else 1.0
    rows = []
    for ed in event_dates:
        try:
            ts = pd.Timestamp(ed).normalize()
        except Exception:
            rows.append({"date": ed, "status": "unparseable"})
            continue
        if ts not in dates:
            rows.append({"date": ts.strftime("%Y-%m-%d"), "status": "not a trading day in the stored series"})
            continue
        i = dates.index(ts)
        lo, hi = i + 1, i + 1 + int(post)  # enter the session after the event
        if lo >= len(m) or hi > len(m):
            rows.append({"date": ts.strftime("%Y-%m-%d"), "status": "insufficient bars after the event"})
            continue
        window = m.iloc[lo:hi]
        ar = (window["rs"].to_numpy() - beta * window["rb"].to_numpy())
        rows.append({
            "date": ts.strftime("%Y-%m-%d"),
            "status": "ok",
            "beta": beta,
            "horizon": int(post),
            "cumulative_abnormal_return": float(np.nansum(ar)),
        })
    ok = [r for r in rows if r.get("status") == "ok"]
    cars = np.asarray([r["cumulative_abnormal_return"] for r in ok], dtype=float)
    return {
        "available": bool(ok),
        "symbol": symbol,
        "events": rows,
        "n": len(ok),
        "mean_car": float(cars.mean()) if ok else None,
        "median_car": float(np.median(cars)) if ok else None,
        "positive_share": float(np.mean(cars > 0)) if ok else None,
        "entry": "session after the event date (no look-ahead)",
        "note": "Market-model abnormal returns. With few events the estimate is noisy; dates must be supplied.",
    }


# --------------------------------------------------------------------------- #
# Liquidity, forensics, factors and coverage (NF-005 / NF-007 / NF-008 / NF-030)
# --------------------------------------------------------------------------- #

def run_liquidity_drought(symbol: str, window: int = 250, recent: int = 20) -> dict[str, Any]:
    """Daily liquidity health for one symbol: volume drought and an Amihud proxy.

    Uses only genuine stored volume. If a symbol has no genuine volume series
    (missing or all-zero), this refuses rather than treating it as zero.
    """
    np = _import_np()
    _, df = _symbol_frame(symbol)
    if df is None or df.empty or len(df) < 30:
        return {"symbol": symbol, "available": False, "reason": "insufficient price history"}
    if "volume" not in df:
        return {"symbol": symbol, "available": False, "reason": "no volume column stored - not substituted with zero"}
    v = df["volume"].astype(float).to_numpy()
    c = df["close"].astype(float).to_numpy()
    t = df["turnover"].astype(float).to_numpy() if "turnover" in df else (v * c)
    v_recent = v[-int(window):]
    if v_recent.size == 0 or not np.isfinite(v_recent).any() or float(np.nanmax(v_recent)) <= 0:
        return {"symbol": symbol, "available": False,
                "reason": "stored volume is missing or all zero - refused rather than read as zero liquidity"}
    med = float(np.nanmedian(v_recent))
    recent_v = v_recent[-int(recent):]
    thresh = 0.5 * med
    below = recent_v < thresh
    # Longest current trailing run below half the median.
    run = 0
    for x in below[::-1]:
        if x:
            run += 1
        else:
            break
    zero_days = int(np.sum(v_recent <= 0))
    # Amihud illiquidity (daily): |return| per unit turnover, scaled for readability.
    ret = np.abs(np.diff(c[-int(window) - 1:]) / c[-int(window) - 1:-1])
    turn = t[-int(window):]
    mask = np.isfinite(ret) & np.isfinite(turn) & (turn > 0)
    amihud = float(np.nanmean(ret[mask] / turn[mask]) * 1e9) if mask.any() else None
    prev = v_recent[-2 * int(recent):-int(recent)] if v_recent.size >= 2 * int(recent) else None
    vol_trend = (float(np.nanmean(recent_v) / np.nanmean(prev))
                 if prev is not None and np.nanmean(prev) > 0 else None)
    return {
        "symbol": symbol,
        "available": True,
        "window": int(window),
        "bars_used": int(v_recent.size),
        "median_daily_volume": med,
        "recent_mean_volume": float(np.nanmean(recent_v)),
        "relative_volume": float(np.nanmean(recent_v) / med) if med > 0 else None,
        "drought_threshold": thresh,
        "days_below_half_median_recent": int(np.sum(below)),
        "current_drought_run": run,
        "zero_volume_days": zero_days,
        "volume_trend_recent_vs_prior": vol_trend,
        "amihud_illiquidity_1e9": amihud,
        "state": "drought" if run >= max(3, recent // 4) else "normal",
        "note": "Daily-data liquidity proxy only. There is no intraday, order-book or trade-level "
                "data, so this cannot describe microstructure or execution slippage directly.",
    }


def run_fundamental_forensics(symbol: str) -> dict[str, Any]:
    """Review stored fundamentals for gaps, staleness and internal inconsistency.

    Flags observations for a human to check. It never asserts fraud or error and
    never fills a missing value with a guess.
    """
    import datetime as _dt

    rows = _symbol_rows(symbol)
    if not rows:
        return {"symbol": symbol, "available": False, "reason": "no fundamentals stored for this symbol"}
    latest = _latest(rows)
    issues: list[dict[str, Any]] = []
    core = ["eps", "pe", "paid_up_capital", "profit", "net_worth_per_share"]
    missing = [f for f in core if f not in latest]
    if missing:
        issues.append({"severity": "medium", "issue": "missing core fields", "detail": ", ".join(missing)})
    for f in ("paid_up_capital", "net_worth_per_share"):
        if f in latest and latest[f] <= 0:
            issues.append({"severity": "high", "issue": "non-positive value where a positive figure is expected",
                           "detail": f"{f} = {latest[f]}"})
    if "profit" in latest and latest["profit"] == 0:
        issues.append({"severity": "low", "issue": "reported net profit is exactly zero", "detail": "profit = 0"})
    # Staleness: newest period_end vs today.
    dates = [r.get("period_end") for r in rows if r.get("period_end")]
    newest_age = None
    if dates:
        try:
            newest = max(_dt.date.fromisoformat(d) for d in dates if d)
            newest_age = (_dt.date.today() - newest).days
            if newest_age > 400:
                issues.append({"severity": "medium", "issue": "newest fundamental period is stale",
                               "detail": f"{newest.isoformat()} ({newest_age} days old)"})
        except ValueError:
            pass
    # P/E internal consistency against the latest stored close.
    implied = None
    pe_price_gap = None
    if "pe" in latest and "eps" in latest and latest["eps"] not in (0, None):
        implied = latest["pe"] * latest["eps"]
        _, df = _symbol_frame(symbol)
        if df is not None and not df.empty:
            market = float(df["close"].astype(float).iloc[-1])
            if market > 0:
                pe_price_gap = implied / market - 1.0
                if abs(pe_price_gap) > 0.25:
                    issues.append({"severity": "medium", "issue": "P/E-implied price diverges from market close",
                                   "detail": f"implied {implied:.2f} vs close {market:.2f} ({pe_price_gap:+.1%})"})
    # Multiple sources disagreeing on the same field/period.
    seen: dict[tuple, set] = {}
    for r in rows:
        if r.get("value") is None:
            continue
        seen.setdefault((r.get("field"), r.get("period_end")), set()).add(round(float(r["value"]), 6))
    conflicts = [k for k, v in seen.items() if len(v) > 1]
    if conflicts:
        issues.append({"severity": "medium", "issue": "sources disagree on the same field/period",
                       "detail": f"{len(conflicts)} field/period pair(s) with differing values"})
    unreviewed = [r for r in rows if r.get("verification") not in ("reviewed", "verified")]
    if unreviewed:
        issues.append({"severity": "low", "issue": "unreviewed fundamental records present",
                       "detail": f"{len(unreviewed)} of {len(rows)} records are not reviewed/verified"})
    high = sum(1 for i in issues if i["severity"] == "high")
    med = sum(1 for i in issues if i["severity"] == "medium")
    return {
        "symbol": symbol,
        "available": True,
        "records": len(rows),
        "fields": sorted({r["field"] for r in rows if r.get("field")}),
        "newest_period": dates and max(d for d in dates if d) or None,
        "newest_age_days": newest_age,
        "implied_price_from_pe": implied,
        "pe_implied_vs_market_gap": pe_price_gap,
        "severity_counts": {"high": high, "medium": med, "low": len(issues) - high - med},
        "issues": issues,
        "note": "These are observations for review, not conclusions. Missing data is reported as missing, never imputed.",
    }


#: Cross-sectional factor definitions: label -> (extractor, "high"|"low" is better).
_FACTORS: dict[str, tuple[Any, str]] = {
    "momentum_12_1": (lambda r: r["momentum_12_1"], "high"),
    "momentum_1m": (lambda r: r["momentum_21"], "high"),
    "low_volatility": (lambda r: r["volatility_63"], "low"),
    "liquidity": (lambda r: r["avg_volume_63"], "high"),
}


def run_factor_snapshot(factor: str = "momentum_12_1", top: int = 20, min_bars: int = 260) -> dict[str, Any]:
    """Rank the stored universe on one cross-sectional factor.

    Reports the top/bottom names and the factor's cross-sectional spread. This is
    a research ranking over the stored window, not a forecast or a recommendation.
    """
    np = _import_np()
    if factor not in _FACTORS:
        raise ValueError(f"unknown factor {factor!r}; choose from {sorted(_FACTORS)}")
    store = _store()
    syms = [s for s in store.symbols(min_bars=min_bars)]
    rows: list[dict[str, Any]] = []
    for s in syms:
        df = store.get_bars(s)
        if df is None or df.empty or len(df) < min_bars:
            continue
        c = df["close"].astype(float).to_numpy()
        if c.size < 260 or not np.isfinite(c[-252]) or c[-252] <= 0:
            continue
        v = df["volume"].astype(float).to_numpy() if "volume" in df else None
        lr = np.diff(np.log(c[-64:]))
        lr = lr[np.isfinite(lr)]
        vol63 = float(np.std(lr, ddof=1) * np.sqrt(252)) if lr.size > 5 else None
        rows.append({
            "symbol": s,
            "last_close": float(c[-1]),
            "momentum_12_1": float(c[-21] / c[-252] - 1.0),
            "momentum_21": float(c[-1] / c[-21] - 1.0),
            "volatility_63": vol63,
            "avg_volume_63": float(np.nanmean(v[-63:])) if v is not None and np.isfinite(v[-63:]).any() else None,
        })
    extractor, direction = _FACTORS[factor]
    usable = [r for r in rows if extractor(r) is not None]
    if len(usable) < 5:
        return {"factor": factor, "available": False,
                "reason": f"only {len(usable)} symbols had enough history for this factor (need >=5)"}
    ranked = sorted(usable, key=extractor, reverse=(direction == "high"))
    vals = np.array([extractor(r) for r in usable], dtype=float)
    k = max(1, min(int(top), len(ranked) // 2 or 1))
    hi, lo = ranked[:k], ranked[-k:]
    hi_mean = float(np.mean([extractor(r) for r in hi]))
    lo_mean = float(np.mean([extractor(r) for r in lo]))
    return {
        "factor": factor,
        "available": True,
        "universe": len(usable),
        "direction": direction,
        "mean": float(vals.mean()),
        "median": float(np.median(vals)),
        "spread_top_minus_bottom": hi_mean - lo_mean if direction == "low" else hi_mean - lo_mean,
        "top": ranked[:k],
        "bottom": lo[::-1],
        "note": "Cross-sectional ranking over the stored window. No survivorship or "
                "look-ahead adjustment beyond the trailing window; not a recommendation.",
    }


def run_coverage_explorer() -> dict[str, Any]:
    """What data actually exists right now, per store and per table (NF-030)."""
    from megatool.db import get_conn

    store = _store()
    syms = list(store.symbols(min_bars=1))
    cov = store.global_coverage()
    counts = [len(store.get_bars(s)) for s in syms[:500]]
    tables: dict[str, Any] = {}
    try:
        with get_conn() as conn:
            names = [r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name").fetchall()]
            for n in names:
                if n.startswith("sqlite_"):
                    continue
                try:
                    tables[n] = conn.execute(f"SELECT COUNT(*) FROM {n}").fetchone()[0]
                except Exception:
                    tables[n] = None
            fund = conn.execute(
                "SELECT COUNT(*) n, COUNT(DISTINCT symbol) s, COUNT(DISTINCT field) f FROM fundamentals"
            ).fetchone() if "fundamentals" in names else None
    except Exception:
        fund = None
    return {
        "available": True,
        "market": {
            "securities": len(syms),
            "bars_total": cov.get("bars") if isinstance(cov, dict) else None,
            "first_date": cov.get("first_date") if isinstance(cov, dict) else None,
            "last_date": cov.get("last_date") if isinstance(cov, dict) else None,
            "bars_min": min(counts) if counts else None,
            "bars_max": max(counts) if counts else None,
            "securities_with_lt_60_bars": sum(1 for c in counts if c < 60),
        },
        "fundamentals": ({"records": fund[0], "symbols": fund[1], "fields": fund[2]} if fund else None),
        "app_tables": tables,
        "known_gaps": [
            "floorsheet_trades: 0 rows (broker/order-flow features blocked)",
            "no sourced corporate-event / IPO / rights calendar",
            "dps: 0 records (dividend-yield tool blocked)",
            "promoter_holding / public_holding: 0 records (ownership blocked)",
            "all prices adjustment_status='unadjusted'",
            "no intraday or order-book series",
        ],
        "note": "Counts are read live from the stores. Gaps are listed explicitly rather than implied.",
    }


#: Registry of analysis functions referenced by the catalogue.
_ANALYSIS_FUNCS: dict[str, Any] = {
    "monte_carlo": run_monte_carlo,
    "risk_of_ruin": run_risk_of_ruin,
    "rolling_beta": run_rolling_beta,
    "volatility_percentile": run_volatility_percentile,
    "technical_rating": run_technical_rating,
    "mtf_confluence": run_mtf_confluence,
    "correlation_matrix": run_correlation_matrix,
    "efficient_frontier": run_efficient_frontier,
    "hrp_portfolio": run_hrp_portfolio,
    "signal_outcomes": run_signal_outcomes,
    "dcf_valuation": run_dcf,
    "reverse_dcf": run_reverse_dcf,
    "deflated_sharpe": run_deflated_sharpe,
    "stress_test": run_stress_test,
    "event_study": run_event_study,
    "liquidity_drought": run_liquidity_drought,
    "fundamental_forensics": run_fundamental_forensics,
    "factor_snapshot": run_factor_snapshot,
    "coverage_explorer": run_coverage_explorer,
}


def run_analysis(fn: str, **kwargs: Any) -> dict[str, Any]:
    if fn not in _ANALYSIS_FUNCS:
        raise ValueError(f"unknown analysis function {fn!r}")
    return _ANALYSIS_FUNCS[fn](**kwargs)


# --------------------------------------------------------------------------- #
# Fundamental engine
# --------------------------------------------------------------------------- #

def _symbol_rows(symbol: str) -> list[dict[str, Any]]:
    from megatool.db import get_conn
    from megatool.fundamentals import query_symbol

    with get_conn() as conn:
        return query_symbol(conn, str(symbol).upper())


def _latest(rows: list[dict[str, Any]]) -> dict[str, float]:
    out: dict[str, float] = {}
    for r in rows:  # newest period first
        f = r.get("field")
        if f and f not in out and r.get("value") is not None:
            out[f] = float(r["value"])
    return out


def _periods(rows: list[dict[str, Any]], field: str) -> list[float]:
    return [float(r["value"]) for r in rows
            if r.get("field") == field and r.get("value") is not None]


def _price(latest: dict[str, float]) -> float | None:
    if "price" in latest and latest["price"]:
        return latest["price"]
    pe, eps = latest.get("pe"), latest.get("eps")
    if pe is not None and eps not in (None, 0):
        return pe * eps
    return None


def _universe_latest() -> dict[str, dict[str, float]]:
    from megatool.db import get_conn

    with get_conn() as conn:
        rows = conn.execute(
            "SELECT symbol, field, value, period_end FROM fundamentals "
            "WHERE value IS NOT NULL ORDER BY symbol, period_end = '', period_end DESC"
        ).fetchall()
    out: dict[str, dict[str, float]] = {}
    for r in rows:
        sym, field, value = r[0], r[1], r[2]
        d = out.setdefault(sym, {})
        if field not in d:
            d[field] = float(value)
    return out


def _median(vals: list[float]) -> float | None:
    import statistics

    vals = [v for v in vals if v is not None]
    return statistics.median(vals) if vals else None


def _rank_map(values: dict[str, float], descending: bool) -> dict[str, int]:
    items = sorted(values.items(), key=lambda kv: kv[1], reverse=descending)
    return {k: i + 1 for i, (k, _) in enumerate(items)}


def _fund_result(fn: str, symbol: str, value: Any, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    out = {"tool": fn, "symbol": symbol, "available": value is not None, "value": value}
    if value is None:
        out["reason"] = "required fundamental field(s) not stored for this symbol"
    if extra:
        out.update(extra)
    return out


def _f_pe(symbol: str) -> dict[str, Any]:
    latest = _latest(_symbol_rows(symbol))
    return _fund_result("pe_ratio", symbol, latest.get("pe"),
                        {"inputs": {"pe": latest.get("pe")}})


def _f_earnings_yield(symbol: str) -> dict[str, Any]:
    latest = _latest(_symbol_rows(symbol))
    eps, price = latest.get("eps"), _price(latest)
    val = (eps / price) if (eps is not None and price) else None
    return _fund_result("earnings_yield", symbol, val, {"inputs": {"eps": eps, "price": price}})


def _f_pb(symbol: str) -> dict[str, Any]:
    latest = _latest(_symbol_rows(symbol))
    price, nwps = _price(latest), latest.get("net_worth_per_share")
    val = (price / nwps) if (price and nwps) else None
    return _fund_result("pb_ratio", symbol, val, {"inputs": {"price": price, "nwps": nwps}})


def _f_book_to_price(symbol: str) -> dict[str, Any]:
    latest = _latest(_symbol_rows(symbol))
    price, nwps = _price(latest), latest.get("net_worth_per_share")
    val = (nwps / price) if (price and nwps) else None
    return _fund_result("book_to_price", symbol, val)


def _f_net_worth_yield(symbol: str) -> dict[str, Any]:
    latest = _latest(_symbol_rows(symbol))
    price, nwps = _price(latest), latest.get("net_worth_per_share")
    val = (nwps / price) if (price and nwps) else None
    return _fund_result("net_worth_yield", symbol, val)


def _f_peg(symbol: str) -> dict[str, Any]:
    rows = _symbol_rows(symbol)
    latest = _latest(rows)
    eps_periods = _periods(rows, "eps")
    growth = (eps_periods[0] / eps_periods[1] - 1.0) if len(eps_periods) >= 2 and eps_periods[1] else None
    pe = latest.get("pe")
    val = (pe / (growth * 100.0)) if (pe is not None and growth and growth > 0) else None
    return _fund_result("peg_proxy", symbol, val,
                        {"inputs": {"pe": pe, "eps_growth": growth}})


def _f_pe_vs_universe(symbol: str) -> dict[str, Any]:
    uni = _universe_latest()
    med = _median([d["pe"] for d in uni.values() if "pe" in d])
    pe = uni.get(symbol.upper(), {}).get("pe")
    val = (pe - med) if (pe is not None and med is not None) else None
    return _fund_result("pe_vs_universe", symbol, val, {"universe_median": med})


def _f_pb_vs_universe(symbol: str) -> dict[str, Any]:
    uni = _universe_latest()
    pbs = []
    for d in uni.values():
        price = d.get("price") or (d.get("pe", 0) * d.get("eps", 0) if "pe" in d and "eps" in d else None)
        nwps = d.get("net_worth_per_share")
        if price and nwps:
            pbs.append(price / nwps)
    med = _median(pbs)
    d = uni.get(symbol.upper(), {})
    price = d.get("price") or (d.get("pe", 0) * d.get("eps", 0) if "pe" in d and "eps" in d else None)
    nwps = d.get("net_worth_per_share")
    pb = (price / nwps) if (price and nwps) else None
    val = (pb - med) if (pb is not None and med is not None) else None
    return _fund_result("pb_vs_universe", symbol, val, {"universe_median": med, "pb": pb})


def _f_hist_pe_percentile(symbol: str) -> dict[str, Any]:
    rows = _symbol_rows(symbol)
    pes = _periods(rows, "pe")
    if len(pes) < 2:
        return _fund_result("historical_pe_percentile", symbol, None,
                            {"reason": "fewer than two stored P/E periods"})
    last = pes[0]
    rank = sum(1 for x in pes if x <= last) / len(pes) * 100.0
    return _fund_result("historical_pe_percentile", symbol, round(rank, 2), {"n": len(pes)})


def _f_market_cap(symbol: str) -> dict[str, Any]:
    latest = _latest(_symbol_rows(symbol))
    price, cap = _price(latest), latest.get("paid_up_capital")
    val = (price * cap / 100.0) if (price and cap) else None
    return _fund_result("market_cap_proxy", symbol, val,
                        {"inputs": {"price": price, "paid_up_capital": cap}})


def _f_equity(symbol: str) -> dict[str, Any]:
    latest = _latest(_symbol_rows(symbol))
    nwps, cap = latest.get("net_worth_per_share"), latest.get("paid_up_capital")
    val = (nwps * cap / 100.0) if (nwps and cap) else None
    return _fund_result("equity_proxy", symbol, val)


def _f_simple(field: str, tool: str):
    def fn(symbol: str) -> dict[str, Any]:
        latest = _latest(_symbol_rows(symbol))
        return _fund_result(tool, symbol, latest.get(field))
    return fn


def _f_roe(symbol: str) -> dict[str, Any]:
    latest = _latest(_symbol_rows(symbol))
    profit, cap = latest.get("profit"), latest.get("paid_up_capital")
    val = (profit / cap) if (profit is not None and cap) else None
    return _fund_result("roe", symbol, val, {"inputs": {"profit": profit, "paid_up_capital": cap}})


def _f_profit_per_capital(symbol: str) -> dict[str, Any]:
    latest = _latest(_symbol_rows(symbol))
    profit, cap = latest.get("profit"), latest.get("paid_up_capital")
    val = (profit / cap) if (profit is not None and cap) else None
    return _fund_result("profit_per_capital", symbol, val)


def _f_capital_growth(symbol: str) -> dict[str, Any]:
    ps = _periods(_symbol_rows(symbol), "paid_up_capital")
    val = (ps[0] / ps[1] - 1.0) if len(ps) >= 2 and ps[1] else None
    return _fund_result("capital_growth", symbol, val)


def _f_book_growth(symbol: str) -> dict[str, Any]:
    ps = _periods(_symbol_rows(symbol), "net_worth_per_share")
    val = (ps[0] / ps[1] - 1.0) if len(ps) >= 2 and ps[1] else None
    return _fund_result("book_value_growth", symbol, val)


def _f_earnings_vol(symbol: str) -> dict[str, Any]:
    import statistics

    ps = _periods(_symbol_rows(symbol), "eps")
    if len(ps) < 2:
        return _fund_result("earnings_volatility", symbol, None,
                            {"reason": "need >=2 EPS periods"})
    mean = statistics.mean(ps)
    val = (statistics.pstdev(ps) / abs(mean)) if mean else None
    return _fund_result("earnings_volatility", symbol, val, {"n": len(ps)})


def _f_eps_growth(symbol: str) -> dict[str, Any]:
    ps = _periods(_symbol_rows(symbol), "eps")
    val = (ps[0] / ps[1] - 1.0) if len(ps) >= 2 and ps[1] else None
    return _fund_result("eps_growth", symbol, val)


def _f_eps_growth_consistency(symbol: str) -> dict[str, Any]:
    ps = _periods(_symbol_rows(symbol), "eps")
    if len(ps) < 2:
        return _fund_result("eps_growth_consistency", symbol, None,
                            {"reason": "need >=2 EPS periods"})
    changes = [ps[i] / ps[i + 1] - 1.0 for i in range(len(ps) - 1) if ps[i + 1]]
    val = (sum(1 for c in changes if c > 0) / len(changes)) if changes else None
    return _fund_result("eps_growth_consistency", symbol, val, {"n": len(changes)})


def _f_eps_cagr(symbol: str) -> dict[str, Any]:
    ps = _periods(_symbol_rows(symbol), "eps")
    if len(ps) < 2 or ps[0] <= 0 or ps[-1] <= 0:
        return _fund_result("eps_cagr", symbol, None,
                            {"reason": "need >=2 positive EPS periods"})
    n = len(ps) - 1
    val = (ps[0] / ps[-1]) ** (1.0 / n) - 1.0
    return _fund_result("eps_cagr", symbol, val, {"n": n})


def _rank_tool(tool: str, field: str, descending: bool, transform=None):
    def fn(symbol: str) -> dict[str, Any]:
        uni = _universe_latest()
        vals: dict[str, float] = {}
        for sym, d in uni.items():
            v = d.get(field)
            if field == "pe":
                v = d.get("pe")
            elif field == "roe":
                p, c = d.get("profit"), d.get("paid_up_capital")
                v = (p / c) if (p is not None and c) else None
            elif field == "eps_growth":
                rows = d  # use latest eps only here (period growth needs per-symbol rows)
                v = None
            if v is not None:
                vals[sym] = float(v)
        if field == "eps_growth":
            for sym in uni:
                rows = _symbol_rows(sym)
                ps = _periods(rows, "eps")
                if len(ps) >= 2 and ps[1]:
                    vals[sym] = ps[0] / ps[1] - 1.0
        if transform:
            vals = {k: transform(v) for k, v in vals.items()}
        ranks = _rank_map(vals, descending)
        sym = symbol.upper()
        return {"tool": tool, "symbol": sym, "available": sym in ranks,
                "rank": ranks.get(sym), "universe": len(ranks),
                "value": vals.get(sym),
                "reason": None if sym in ranks else "no stored value for this symbol"}
    return fn


def _f_composite_rank(symbol: str) -> dict[str, Any]:
    uni = _universe_latest()
    pe_vals = {s: d["pe"] for s, d in uni.items() if "pe" in d and d["pe"]}
    roe_vals = {}
    for s, d in uni.items():
        p, c = d.get("profit"), d.get("paid_up_capital")
        if p is not None and c:
            roe_vals[s] = p / c
    if not pe_vals or not roe_vals:
        return _fund_result("composite_rank", symbol, None,
                            {"reason": "insufficient universe data"})
    pe_rank = _rank_map(pe_vals, descending=False)  # cheap = best (rank 1)
    roe_rank = _rank_map(roe_vals, descending=True)  # high = best
    sym = symbol.upper()
    if sym not in pe_rank or sym not in roe_rank:
        return {"tool": "composite_rank", "symbol": sym, "available": False,
                "reason": "symbol lacks P/E or ROE inputs"}
    score = (pe_rank[sym] / len(pe_rank) + roe_rank[sym] / len(roe_rank)) / 2.0
    return {"tool": "composite_rank", "symbol": sym, "available": True,
            "value": round(score, 4), "pe_rank": pe_rank[sym], "roe_rank": roe_rank[sym],
            "universe": len(pe_rank), "note": "lower is better (0 = best value+quality combo)"}


def _f_cheap_quality_screen(symbol: str) -> dict[str, Any]:
    uni = _universe_latest()
    pe_vals = {s: d["pe"] for s, d in uni.items() if "pe" in d and d["pe"]}
    roe_vals = {}
    for s, d in uni.items():
        p, c = d.get("profit"), d.get("paid_up_capital")
        if p is not None and c:
            roe_vals[s] = p / c
    sym = symbol.upper()
    if sym not in pe_vals or sym not in roe_vals:
        return {"tool": "cheap_quality_screen", "symbol": sym, "available": False,
                "reason": "symbol lacks P/E or ROE inputs"}
    pe_sorted = sorted(pe_vals.values())
    roe_sorted = sorted(roe_vals.values(), reverse=True)
    pe_cut = pe_sorted[max(0, int(len(pe_sorted) / 3) - 1)]
    roe_cut = roe_sorted[max(0, int(len(roe_sorted) / 3) - 1)]
    passed = pe_vals[sym] <= pe_cut and roe_vals[sym] >= roe_cut
    return {"tool": "cheap_quality_screen", "symbol": sym, "available": True,
            "value": bool(passed), "pe": pe_vals[sym], "roe": roe_vals[sym],
            "pe_cutoff": pe_cut, "roe_cutoff": roe_cut,
            "criteria": "bottom-third P/E and top-third ROE across the stored universe"}


def _f_neg_eps(symbol: str) -> dict[str, Any]:
    latest = _latest(_symbol_rows(symbol))
    eps = latest.get("eps")
    return _fund_result("negative_eps_flag", symbol, (eps is not None and eps < 0) if eps is not None else None,
                        {"eps": eps})


def _f_valuation_anomaly(symbol: str) -> dict[str, Any]:
    import statistics

    uni = _universe_latest()
    pes = [d["pe"] for d in uni.values() if "pe" in d and d["pe"] is not None]
    if len(pes) < 5:
        return _fund_result("valuation_anomaly", symbol, None,
                            {"reason": "insufficient universe P/E data"})
    mean = statistics.mean(pes)
    sd = statistics.pstdev(pes)
    pe = uni.get(symbol.upper(), {}).get("pe")
    if pe is None or not sd:
        return _fund_result("valuation_anomaly", symbol, None, {"reason": "no P/E for symbol"})
    z = (pe - mean) / sd
    return _fund_result("valuation_anomaly", symbol, abs(z) > 3.0,
                        {"z": round(z, 3), "pe": pe, "universe_mean": round(mean, 2)})


def _f_dividend_yield(symbol: str) -> dict[str, Any]:
    latest = _latest(_symbol_rows(symbol))
    if "dps" not in latest:
        return {"tool": "dividend_yield", "symbol": symbol.upper(), "available": False,
                "value": None, "reason": "DPS is not stored in the dataset (field has 0 records); "
                                         "returned not-available rather than zero"}
    price, dps = _price(latest), latest.get("dps")
    return _fund_result("dividend_yield", symbol, (dps / price) if price else None)


_FUND_FUNCS: dict[str, Any] = {
    "pe_ratio": _f_pe,
    "earnings_yield": _f_earnings_yield,
    "pb_ratio": _f_pb,
    "book_to_price": _f_book_to_price,
    "net_worth_yield": _f_net_worth_yield,
    "peg_proxy": _f_peg,
    "pe_vs_universe": _f_pe_vs_universe,
    "pb_vs_universe": _f_pb_vs_universe,
    "historical_pe_percentile": _f_hist_pe_percentile,
    "market_cap_proxy": _f_market_cap,
    "equity_proxy": _f_equity,
    "eps": _f_simple("eps", "eps"),
    "net_worth_per_share": _f_simple("net_worth_per_share", "net_worth_per_share"),
    "profit": _f_simple("profit", "profit"),
    "roe": _f_roe,
    "profit_per_capital": _f_profit_per_capital,
    "paid_up_capital": _f_simple("paid_up_capital", "paid_up_capital"),
    "capital_growth": _f_capital_growth,
    "book_value_growth": _f_book_growth,
    "earnings_volatility": _f_earnings_vol,
    "eps_growth": _f_eps_growth,
    "eps_growth_consistency": _f_eps_growth_consistency,
    "eps_cagr": _f_eps_cagr,
    "earnings_rank": _rank_tool("earnings_rank", "eps", True),
    "value_rank": _rank_tool("value_rank", "pe", False),
    "quality_rank": _rank_tool("quality_rank", "roe", True),
    "growth_rank": _rank_tool("growth_rank", "eps_growth", True),
    "composite_rank": _f_composite_rank,
    "cheap_quality_screen": _f_cheap_quality_screen,
    "negative_eps_flag": _f_neg_eps,
    "valuation_anomaly": _f_valuation_anomaly,
    "dividend_yield": _f_dividend_yield,
}


def run_fundamental(fn: str, symbol: str | None = None) -> dict[str, Any]:
    """Run one fundamental tool. Ranking tools need only a symbol to report on."""
    if fn not in _FUND_FUNCS:
        raise ValueError(f"unknown fundamental tool {fn!r}")
    if not symbol:
        raise ValueError("a symbol is required")
    return _FUND_FUNCS[fn](str(symbol).upper())
