"""Volatility indicators."""

from __future__ import annotations

import numpy as np

from megatool.ta.core import (
    IndicatorMeta,
    IndicatorResult,
    ema,
    register,
    rolling_max,
    rolling_mean,
    rolling_min,
    rolling_std,
    shift,
    true_range,
    wilder_smooth,
)


@register(
    IndicatorMeta(
        name="bollinger",
        label="Bollinger Bands",
        category="volatility",
        params={"period": 20, "std_dev": 2.0},
        inputs=("close",),
        outputs=("upper", "middle", "lower", "bandwidth", "percent_b"),
        warmup=lambda p: p["period"] - 1,
        reference="John Bollinger, 1980s.",
        formula="middle = SMA(n); upper/lower = middle +/- k * population stddev(n)",
        notes="Uses the population standard deviation (ddof=0), as Bollinger specifies.",
    )
)
def bollinger(
    data: dict[str, np.ndarray], period: int = 20, std_dev: float = 2.0
) -> IndicatorResult:
    c = data["close"]
    mid = rolling_mean(c, period)
    sd = rolling_std(c, period, ddof=0)
    up = mid + std_dev * sd
    lo = mid - std_dev * sd
    with np.errstate(divide="ignore", invalid="ignore"):
        bandwidth = (up - lo) / mid
        percent_b = (c - lo) / (up - lo)
    return IndicatorResult(
        name="bollinger",
        params={},
        values={"upper": up, "middle": mid, "lower": lo, "bandwidth": bandwidth, "percent_b": percent_b},
    )


@register(
    IndicatorMeta(
        name="donchian",
        label="Donchian Channel",
        category="volatility",
        params={"period": 20},
        inputs=("high", "low"),
        outputs=("upper", "middle", "lower"),
        warmup=lambda p: p["period"] - 1,
        reference="Richard Donchian; popularised by the Turtle Traders.",
        formula="upper = max(high, n); lower = min(low, n); middle = mean of the two",
        notes="Breakout systems treat a new channel high/low as a signal.",
    )
)
def donchian(data: dict[str, np.ndarray], period: int = 20) -> IndicatorResult:
    up = rolling_max(data["high"], period)
    lo = rolling_min(data["low"], period)
    return IndicatorResult(
        name="donchian", params={}, values={"upper": up, "lower": lo, "middle": (up + lo) / 2.0}
    )


@register(
    IndicatorMeta(
        name="keltner",
        label="Keltner Channel",
        category="volatility",
        params={"period": 20, "atr_period": 10, "multiplier": 2.0},
        inputs=("high", "low", "close"),
        outputs=("upper", "middle", "lower"),
        warmup=lambda p: max(p["period"] - 1, p["atr_period"]),
        reference="Chester Keltner, 1960; ATR variant popularised by Linda Raschke.",
        formula="middle = EMA(n); upper/lower = middle +/- multiplier * ATR(atr_period)",
    )
)
def keltner(
    data: dict[str, np.ndarray], period: int = 20, atr_period: int = 10, multiplier: float = 2.0
) -> IndicatorResult:
    mid = ema(data["close"], period)
    tr = true_range(data["high"], data["low"], data["close"])
    atr_v = wilder_smooth(tr, atr_period)
    return IndicatorResult(
        name="keltner",
        params={},
        values={"upper": mid + multiplier * atr_v, "middle": mid, "lower": mid - multiplier * atr_v},
    )


@register(
    IndicatorMeta(
        name="historical_volatility",
        label="Historical Volatility (annualised)",
        category="volatility",
        params={"period": 20, "trading_days": 250},
        inputs=("close",),
        outputs=("hv",),
        warmup=lambda p: p["period"],
        reference="Standard close-to-close realised volatility.",
        formula="HV = stddev(log return, n) * sqrt(trading_days) * 100",
        notes="NEPSE trades roughly 250 days a year; this is an assumption, "
        "not a guarantee, and is configurable.",
    )
)
def historical_volatility(
    data: dict[str, np.ndarray], period: int = 20, trading_days: int = 250
) -> IndicatorResult:
    c = data["close"]
    n = len(c)
    out = np.full(n, np.nan)
    with np.errstate(divide="ignore", invalid="ignore"):
        logret = np.log(c / shift(c, 1))
    for i in range(period, n):
        w = logret[i - period + 1 : i + 1]
        if np.any(np.isnan(w)):
            continue
        out[i] = float(np.std(w, ddof=1)) * np.sqrt(trading_days) * 100.0
    return IndicatorResult(name="historical_volatility", params={}, values={"hv": out})


@register(
    IndicatorMeta(
        name="true_range",
        label="True Range",
        category="volatility",
        params={},
        inputs=("high", "low", "close"),
        outputs=("true_range",),
        warmup=lambda p: 1,
        reference="J. Welles Wilder (1978).",
        formula="TR = max(H-L, |H-Pc|, |L-Pc|)",
    )
)
def true_range_ind(data: dict[str, np.ndarray]) -> IndicatorResult:
    return IndicatorResult(
        name="true_range", params={}, values={"true_range": true_range(data["high"], data["low"], data["close"])}
    )
