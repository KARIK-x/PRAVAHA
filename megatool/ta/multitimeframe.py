"""Multi-timeframe candle aggregation."""

from __future__ import annotations

import pandas as pd


def aggregate_daily_to_weekly(df):
    df = df.copy()
    df["trading_date"] = pd.to_datetime(df["trading_date"], format="%Y-%m-%d", errors="coerce")
    df = df.sort_values("trading_date")
    df["week"] = df["trading_date"].dt.to_period("W").dt.start_time
    agg = (
        df.groupby("week")
        .agg(
            open=("open", "first"),
            high=("high", "max"),
            low=("low", "min"),
            close=("close", "last"),
            volume=("volume", "sum"),
        )
        .reset_index()
    )
    agg.rename(columns={"week": "trading_date"}, inplace=True)
    return agg


def aggregate_daily_to_monthly(df):
    df = df.copy()
    df["trading_date"] = pd.to_datetime(df["trading_date"], format="%Y-%m-%d", errors="coerce")
    df = df.sort_values("trading_date")
    df["month"] = df["trading_date"].dt.to_period("M").dt.start_time
    agg = (
        df.groupby("month")
        .agg(
            open=("open", "first"),
            high=("high", "max"),
            low=("low", "min"),
            close=("close", "last"),
            volume=("volume", "sum"),
        )
        .reset_index()
    )
    agg.rename(columns={"month": "trading_date"}, inplace=True)
    return agg


def _frame_to_data(frame):
    return {
        "open": frame["open"].to_numpy(dtype=float),
        "high": frame["high"].to_numpy(dtype=float),
        "low": frame["low"].to_numpy(dtype=float),
        "close": frame["close"].to_numpy(dtype=float),
        "volume": frame["volume"].to_numpy(dtype=float),
    }


def mtf_confluence(df, fast: int = 20, slow: int = 50, rsi_period: int = 14) -> dict:
    """Multi-timeframe trend/momentum/volatility confluence (daily/weekly/monthly).

    Aggregates the daily frame to weekly and monthly bars (OHLCV, derived
    aggregation — NOT native data; labelled as such in the result) and computes,
    on each timeframe, a trend label (SMA fast vs slow), a momentum label (RSI
    vs 50) and a volatility reading (ATR as % of price). Returns a per-timeframe
    dict plus a confluence summary counting how many timeframes agree.

    Requires genuine OHLCV on the daily frame; the aggregate is derived.
    """
    import numpy as np
    import megatool.ta as ta

    frames = {
        "daily": df,
        "weekly": aggregate_daily_to_weekly(df),
        "monthly": aggregate_daily_to_monthly(df),
    }
    out: dict = {}
    for label, frame in frames.items():
        if frame is None or len(frame) == 0:
            out[label] = {"bars": 0, "available": False, "reason": "no data"}
            continue
        data = _frame_to_data(frame)
        n = len(data["close"])
        sma_fast = ta.compute("sma", data, period=fast).values["sma"]
        sma_slow = ta.compute("sma", data, period=slow).values["sma"]
        rsi = ta.compute("rsi", data, period=rsi_period).values["rsi"]
        atr = ta.compute("atr", data, period=14).values["atr"]
        i = n - 1
        sf = float(sma_fast[i]) if not (sma_fast[i] != sma_fast[i]) else None
        ss = float(sma_slow[i]) if not (sma_slow[i] != sma_slow[i]) else None
        rv = float(rsi[i]) if not (rsi[i] != rsi[i]) else None
        av = float(atr[i]) if not (atr[i] != atr[i]) else None
        if sf is not None and ss is not None:
            trend = "bullish" if sf > ss else ("bearish" if sf < ss else "neutral")
        else:
            trend = "unknown"
        if rv is not None:
            momentum = "bullish" if rv > 55 else ("bearish" if rv < 45 else "neutral")
        else:
            momentum = "unknown"
        atr_pct = (av / data["close"][i] * 100.0) if (av is not None and data["close"][i]) else None
        if atr_pct is None:
            vol_state = "unknown"
        elif atr_pct > 3.0:
            vol_state = "high"
        elif atr_pct < 1.5:
            vol_state = "low"
        else:
            vol_state = "normal"
        out[label] = {
            "bars": n,
            "available": True,
            "native": label == "daily",
            "last_close": round(float(data["close"][i]), 4),
            "sma_fast": None if sf is None else round(sf, 4),
            "sma_slow": None if ss is None else round(ss, 4),
            "trend": trend,
            "rsi": None if rv is None else round(rv, 2),
            "momentum": momentum,
            "atr_pct": None if atr_pct is None else round(atr_pct, 3),
            "volatility": vol_state,
        }
    bull = sum(1 for t in ("daily", "weekly", "monthly") if out.get(t, {}).get("trend") == "bullish")
    bear = sum(1 for t in ("daily", "weekly", "monthly") if out.get(t, {}).get("trend") == "bearish")
    out["confluence"] = {
        "bullish_timeframes": bull,
        "bearish_timeframes": bear,
        "score": bull - bear,
        "verdict": "bullish" if bull > bear else ("bearish" if bear > bull else "mixed"),
        "note": "Counts timeframes whose fast SMA is above the slow SMA. Derived from aggregated weekly/monthly bars, not native data.",
    }
    return out
