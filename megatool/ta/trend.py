"""Trend indicators."""

from __future__ import annotations

import numpy as np

from megatool.ta.core import (
    IndicatorMeta,
    IndicatorResult,
    ema,
    register,
    rolling_mean,
    true_range,
    wilder_smooth,
)


@register(
    IndicatorMeta(
        name="sma",
        label="Simple Moving Average",
        category="trend",
        params={"period": 20},
        inputs=("close",),
        outputs=("sma",),
        warmup=lambda p: p["period"] - 1,
        reference="Arithmetic mean of the last `period` closes.",
        formula="SMA[t] = mean(close[t-period+1 .. t])",
        notes="No look-ahead: the window ends at t.",
    )
)
def sma(data: dict[str, np.ndarray], period: int = 20) -> IndicatorResult:
    v = rolling_mean(data["close"], period)
    return IndicatorResult(name="sma", params={}, values={"sma": v})


@register(
    IndicatorMeta(
        name="ema",
        label="Exponential Moving Average",
        category="trend",
        params={"period": 20},
        inputs=("close",),
        outputs=("ema",),
        warmup=lambda p: p["period"] - 1,
        reference="Seeded with SMA of the first `period` values.",
        formula="EMA[t] = EMA[t-1] + 2/(period+1) * (close[t] - EMA[t-1])",
    )
)
def ema_ind(data: dict[str, np.ndarray], period: int = 20) -> IndicatorResult:
    v = ema(data["close"], period)
    return IndicatorResult(name="ema", params={}, values={"ema": v})


@register(
    IndicatorMeta(
        name="wma",
        label="Weighted Moving Average",
        category="trend",
        params={"period": 20},
        inputs=("close",),
        outputs=("wma",),
        warmup=lambda p: p["period"] - 1,
        reference="Linear weights, most recent observation weighted highest.",
        formula="WMA[t] = sum(i * close[t-period+i]) / sum(1..period), i=1..period",
    )
)
def wma(data: dict[str, np.ndarray], period: int = 20) -> IndicatorResult:
    n = len(data["close"])
    out = np.full(n, np.nan)
    c = data["close"]
    weights = np.arange(1, period + 1, dtype=float)
    denom = weights.sum()
    for i in range(period - 1, n):
        w = c[i - period + 1 : i + 1]
        if np.any(np.isnan(w)):
            continue
        out[i] = float(np.dot(w, weights) / denom)
    return IndicatorResult(name="wma", params={}, values={"wma": out})


@register(
    IndicatorMeta(
        name="hma",
        label="Hull Moving Average",
        category="trend",
        params={"period": 16},
        inputs=("close",),
        outputs=("hma",),
        warmup=lambda p: p["period"] + max(1, int(round(np.sqrt(p["period"])))) - 2,
        reference="Alan Hull, 2005. Reduces lag while keeping smoothness.",
        formula="HMA = WMA(2*WMA(period/2) - WMA(period), round(sqrt(period)))",
        notes="Half period is rounded down; sqrt period rounded to nearest int.",
    )
)
def hma(data: dict[str, np.ndarray], period: int = 16) -> IndicatorResult:
    c = data["close"]
    n = len(c)
    out = np.full(n, np.nan)
    half = max(1, int(period // 2))
    sqrt_p = max(1, int(round(np.sqrt(period))))

    wma_half = _wma_arr(c, half)
    wma_full = _wma_arr(c, period)
    with np.errstate(invalid="ignore"):
        raw = 2.0 * wma_half - wma_full
    out = _wma_arr(raw, sqrt_p)
    return IndicatorResult(name="hma", params={}, values={"hma": out})


def _wma_arr(values: np.ndarray, period: int) -> np.ndarray:
    n = len(values)
    out = np.full(n, np.nan)
    if period <= 0 or n < period:
        return out
    weights = np.arange(1, period + 1, dtype=float)
    denom = weights.sum()
    for i in range(period - 1, n):
        w = values[i - period + 1 : i + 1]
        if np.any(np.isnan(w)):
            continue
        out[i] = float(np.dot(w, weights) / denom)
    return out


@register(
    IndicatorMeta(
        name="atr",
        label="Average True Range",
        category="volatility",
        params={"period": 14},
        inputs=("high", "low", "close"),
        outputs=("atr",),
        # TR[0] has no prior close, so the first full window ends at index `period`.
        warmup=lambda p: p["period"],
        reference="J. Welles Wilder, New Concepts in Technical Trading Systems (1978).",
        formula="TR = max(H-L, |H-Pc|, |L-Pc|); ATR = Wilder smooth of TR",
    )
)
def atr(data: dict[str, np.ndarray], period: int = 14) -> IndicatorResult:
    tr = true_range(data["high"], data["low"], data["close"])
    return IndicatorResult(name="atr", params={}, values={"atr": wilder_smooth(tr, period)})


@register(
    IndicatorMeta(
        name="adx",
        label="Average Directional Index",
        category="trend",
        params={"period": 14},
        inputs=("high", "low", "close"),
        outputs=("adx", "plus_di", "minus_di"),
        warmup=lambda p: 2 * p["period"] - 1,
        output_warmup={
            "adx": lambda p: 2 * p["period"] - 1,
            "plus_di": lambda p: p["period"],
            "minus_di": lambda p: p["period"],
        },
        reference="J. Welles Wilder (1978). Trend-strength, not direction.",
        formula="+DM = max(H-Hp,0) if (H-Hp)>(Lp-L) else 0; -DM likewise; "
        "DI = 100*Wilder(PDM)/ATR; DX = 100*|+DI - -DI|/(+DI + -DI); "
        "ADX = Wilder(DX)",
        notes="ADX > 25 is conventionally read as trending; this is a convention, not a law.",
    )
)
def adx(data: dict[str, np.ndarray], period: int = 14) -> IndicatorResult:
    h, lo, c = data["high"], data["low"], data["close"]
    n = len(c)
    plus_dm = np.full(n, np.nan)
    minus_dm = np.full(n, np.nan)
    plus_dm[0] = 0.0
    minus_dm[0] = 0.0
    hp, lp = h[:-1], lo[:-1]
    up_move = h[1:] - hp
    down_move = lp - lo[1:]
    plus_dm[1:] = np.where((up_move > down_move) & (up_move > 0), up_move, 0.0)
    minus_dm[1:] = np.where((down_move > up_move) & (down_move > 0), down_move, 0.0)

    tr = true_range(h, lo, c)
    atr_s = wilder_smooth(tr, period)
    pdm_s = wilder_smooth(plus_dm, period)
    mdm_s = wilder_smooth(minus_dm, period)

    with np.errstate(invalid="ignore", divide="ignore"):
        plus_di = 100.0 * pdm_s / atr_s
        minus_di = 100.0 * mdm_s / atr_s
        dx = 100.0 * np.abs(plus_di - minus_di) / (plus_di + minus_di)
    adx_v = wilder_smooth(dx, period)
    return IndicatorResult(
        name="adx", params={}, values={"adx": adx_v, "plus_di": plus_di, "minus_di": minus_di}
    )


@register(
    IndicatorMeta(
        name="aroon",
        label="Aroon",
        category="trend",
        params={"period": 14},
        inputs=("high", "low"),
        outputs=("aroon_up", "aroon_down", "aroon_osc"),
        warmup=lambda p: p["period"],
        reference="Tushar Chande, 1995.",
        formula="Aroon Up = 100 * (period - bars_since_high) / period",
        notes="Measures how recently the period high/low occurred.",
    )
)
def aroon(data: dict[str, np.ndarray], period: int = 14) -> IndicatorResult:
    h, lo = data["high"], data["low"]
    n = len(h)
    up = np.full(n, np.nan)
    dn = np.full(n, np.nan)
    for i in range(period, n):
        wh = h[i - period : i + 1]
        wl = lo[i - period : i + 1]
        if np.any(np.isnan(wh)) or np.any(np.isnan(wl)):
            continue
        # Index (within the window) of the most recent extreme; on ties the
        # latest occurrence wins so we measure recency, not first occurrence.
        idx_high = len(wh) - 1 - int(np.argmax(wh[::-1]))
        idx_low = len(wl) - 1 - int(np.argmin(wl[::-1]))
        # Aroon Up = 100 * (period - bars_since_high) / period, and
        # bars_since_high == period - idx_high, so this reduces to idx/period.
        up[i] = 100.0 * idx_high / period
        dn[i] = 100.0 * idx_low / period
    return IndicatorResult(
        name="aroon", params={}, values={"aroon_up": up, "aroon_down": dn, "aroon_osc": up - dn}
    )


@register(
    IndicatorMeta(
        name="supertrend",
        label="Supertrend",
        category="trend",
        params={"period": 10, "multiplier": 3.0},
        inputs=("high", "low", "close"),
        outputs=("supertrend", "direction"),
        warmup=lambda p: p["period"],
        reference="Commonly used in Indian/South-Asian technical analysis.",
        formula="UB/LB = ATR-based bands; supertrend flips when close crosses them.",
        notes="direction is +1 while in an uptrend, -1 while in a downtrend.",
    )
)
def supertrend(
    data: dict[str, np.ndarray], period: int = 10, multiplier: float = 3.0
) -> IndicatorResult:
    h, lo, c = data["high"], data["low"], data["close"]
    n = len(c)
    tr = true_range(h, lo, c)
    atr_v = wilder_smooth(tr, period)

    st = np.full(n, np.nan)
    direction = np.full(n, np.nan)
    upper = np.full(n, np.nan)
    lower = np.full(n, np.nan)

    for i in range(n):
        if np.isnan(atr_v[i]):
            continue
        mid = (h[i] + lo[i]) / 2.0
        ub = mid + multiplier * atr_v[i]
        lb = mid - multiplier * atr_v[i]

        # The bands trail: once set, they can only move in the direction that
        # loosens them, which is what makes supertrend sticky.
        if i > 0 and not np.isnan(upper[i - 1]):
            ub = ub if (ub < upper[i - 1] or c[i - 1] > upper[i - 1]) else upper[i - 1]
            lb = lb if (lb > lower[i - 1] or c[i - 1] < lower[i - 1]) else lower[i - 1]
        upper[i], lower[i] = ub, lb

        if i == 0:
            direction[i] = 1.0
            st[i] = lb
            continue
        prev_dir = direction[i - 1]
        if np.isnan(prev_dir):
            direction[i] = 1.0
            st[i] = lb
            continue
        if c[i] > ub:
            direction[i] = 1.0
        elif c[i] < lb:
            direction[i] = -1.0
        else:
            direction[i] = prev_dir
        st[i] = lb if direction[i] == 1.0 else ub

    return IndicatorResult(name="supertrend", params={}, values={"supertrend": st, "direction": direction})
