"""Trend indicators, batch 2.

Every indicator here is causal (uses only t and earlier), publishes its
formula/reference, and declares the exact first-valid bar so the generic
engine tests can enforce it.
"""

from __future__ import annotations

import numpy as np

from megatool.ta.core import (
    IndicatorMeta,
    IndicatorResult,
    ema,
    register,
    rolling_mean,
    shift,
    wilder_smooth,
)


def weighted_mean(values: np.ndarray, period: int) -> np.ndarray:
    """Linear-weighted moving average (shared helper), first valid at period-1."""
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
        name="alma",
        label="Arnaud Legoux Moving Average",
        category="trend",
        params={"period": 9, "offset": 0.85, "sigma": 6.0},
        inputs=("close",),
        outputs=("alma",),
        warmup=lambda p: p["period"] - 1,
        reference="Arnaud Legoux & Dimitrios Kouzis-Loukas, ALMA (2009).",
        formula="W_i = exp(-(i - m)^2 / (2*s^2)), m = offset*(period-1), s = period/sigma; "
        "ALMA[t] = sum(W_i * close[t-period+1+i]) / sum(W_i)",
        notes="Gaussian-weighted average; sigma controls flatness, offset shifts the "
        "weight peak toward the newest (1.0) or oldest (0.0) bars.",
    )
)
def alma(data: dict[str, np.ndarray], period: int = 9, offset: float = 0.85, sigma: float = 6.0) -> IndicatorResult:
    c = data["close"]
    n = len(c)
    out = np.full(n, np.nan)
    if period > 0 and n >= period:
        i = np.arange(period, dtype=float)
        m = offset * (period - 1)
        s = period / sigma
        w = np.exp(-((i - m) ** 2) / (2.0 * s * s))
        wsum = w.sum()
        for t in range(period - 1, n):
            win = c[t - period + 1 : t + 1]
            if np.any(np.isnan(win)):
                continue
            out[t] = float(np.dot(win, w) / wsum)
    return IndicatorResult(name="alma", params={}, values={"alma": out})


@register(
    IndicatorMeta(
        name="t3",
        label="T3 Moving Average",
        category="trend",
        params={"period": 5, "volume_factor": 0.7},
        inputs=("close",),
        outputs=("t3",),
        warmup=lambda p: 6 * (p["period"] - 1),
        reference="Tim Tillson, 'Smoothing Techniques for More Accurate Signals', TASC 1998.",
        formula="Six chained EMAs (e1..e6). c1=-v^3; c2=3v^2+3v^3; c3=-6v^2-3v-3v^3; "
        "c4=1+3v+v^3+3v^2; T3 = c1*e6 + c2*e5 + c3*e4 + c4*e3  (v = volume_factor)",
        notes="The volume_factor (a misnomer in the literature) controls response speed; "
        "it is not traded volume.",
    )
)
def t3(data: dict[str, np.ndarray], period: int = 5, volume_factor: float = 0.7) -> IndicatorResult:
    c = data["close"]
    e1 = ema(c, period)
    e2 = ema(e1, period)
    e3 = ema(e2, period)
    e4 = ema(e3, period)
    e5 = ema(e4, period)
    e6 = ema(e5, period)
    v = volume_factor
    c1 = -v**3
    c2 = 3 * v**2 + 3 * v**3
    c3 = -6 * v**2 - 3 * v - 3 * v**3
    c4 = 1 + 3 * v + v**3 + 3 * v**2
    out = c1 * e6 + c2 * e5 + c3 * e4 + c4 * e3
    return IndicatorResult(name="t3", params={}, values={"t3": out})


@register(
    IndicatorMeta(
        name="zlema",
        label="Zero-Lag Exponential Moving Average",
        category="trend",
        params={"period": 20},
        inputs=("close",),
        outputs=("zlema",),
        warmup=lambda p: (p["period"] - 1) // 2 + p["period"] - 1,
        reference="Ehlers-style lag compensation; popularised by John Ehlers.",
        formula="lag = floor((period-1)/2); zl[t] = 2*close[t] - close[t-lag]; "
        "ZLEMA = EMA(zl, period)",
        notes="Reduces EMA lag by de-lagging the input with the price 'lag' bars ago.",
    )
)
def zlema(data: dict[str, np.ndarray], period: int = 20) -> IndicatorResult:
    c = data["close"]
    lag = (period - 1) // 2
    zl = 2.0 * c - shift(c, lag)
    out = ema(zl, period)
    return IndicatorResult(name="zlema", params={}, values={"zlema": out})


@register(
    IndicatorMeta(
        name="vidya",
        label="Variable Index Dynamic Average",
        category="trend",
        params={"period": 14, "short_period": 2},
        inputs=("close",),
        outputs=("vidya",),
        warmup=lambda p: p["period"],
        reference="Tushar Chande, 'Chande's Variable Index Dynamic Average', TASC 1992.",
        formula="k = 2/(short_period+1); w = |CMO(period)|/100; "
        "VIDYA[t] = (k*w)*close[t] + (1 - k*w)*VIDYA[t-1]; seeded with close at the "
        "first bar where CMO is available",
        notes="Adaptive average: it speeds up when the Chande Momentum Oscillator is "
        "large in absolute value and slows down when momentum fades.",
    )
)
def vidya(data: dict[str, np.ndarray], period: int = 14, short_period: int = 2) -> IndicatorResult:
    c = data["close"]
    n = len(c)
    out = np.full(n, np.nan)
    # CMO inline (causal): 100*(sum_up - sum_down)/(sum_up + sum_down) over `period`.
    ch = np.full(n, np.nan)
    ch[1:] = c[1:] - c[:-1]
    up = np.where(ch > 0, ch, 0.0)
    dn = np.where(ch < 0, -ch, 0.0)
    k = 2.0 / (short_period + 1)
    for t in range(period, n):
        win_up = up[t - period + 1 : t + 1]
        win_dn = dn[t - period + 1 : t + 1]
        if np.any(np.isnan(ch[t - period + 1 : t + 1])):
            continue
        su = float(win_up.sum())
        sd = float(win_dn.sum())
        if su + sd == 0.0:
            cmo = 0.0
        else:
            cmo = 100.0 * (su - sd) / (su + sd)
        prev = out[t - 1]
        if np.isnan(prev):
            prev = c[t]
        w = abs(cmo) / 100.0
        out[t] = (k * w) * c[t] + (1.0 - k * w) * prev
    return IndicatorResult(name="vidya", params={}, values={"vidya": out})


@register(
    IndicatorMeta(
        name="smma",
        label="Smoothed Moving Average (Wilder)",
        category="trend",
        params={"period": 20},
        inputs=("close",),
        outputs=("smma",),
        warmup=lambda p: p["period"] - 1,
        reference="J. Welles Wilder, New Concepts in Technical Trading Systems (1978).",
        formula="SMMA[t] = SMMA[t-1] + (close[t] - SMMA[t-1]) / period; seeded with "
        "the SMA of the first `period` values",
        notes="Also called RMA; identical to Wilder's smoothing.",
    )
)
def smma(data: dict[str, np.ndarray], period: int = 20) -> IndicatorResult:
    out = wilder_smooth(data["close"], period)
    return IndicatorResult(name="smma", params={}, values={"smma": out})


def regression_triplet(values: np.ndarray, period: int) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Rolling OLS over the last `period` points.

    Returns (endpoint_value, slope, standard_error). A window containing any
    non-finite value yields NaN for all three. First valid bar: period-1.
    """
    n = len(values)
    end = np.full(n, np.nan)
    slope = np.full(n, np.nan)
    se = np.full(n, np.nan)
    if period < 2 or n < period:
        return end, slope, se
    x = np.arange(period, dtype=float)
    x_mean = x.mean()
    sxx = float(((x - x_mean) ** 2).sum())
    for t in range(period - 1, n):
        y = values[t - period + 1 : t + 1]
        if np.any(~np.isfinite(y)):
            continue
        y_mean = float(y.mean())
        b = float(((x - x_mean) * (y - y_mean)).sum() / sxx)
        a = y_mean - b * x_mean
        end[t] = a + b * (period - 1)
        slope[t] = b
        if period - 2 > 0:
            resid = y - (a + b * x)
            se[t] = float(np.sqrt((resid**2).sum() / (period - 2)))
    return end, slope, se


@register(
    IndicatorMeta(
        name="lsma",
        label="Least Squares Moving Average",
        category="trend",
        params={"period": 25},
        inputs=("close",),
        outputs=("lsma",),
        warmup=lambda p: p["period"] - 1,
        reference="Oldest recorded use: R. B. Barnaby / 'time series forecast' (1936); "
        "popularised as LSMA on TradingView.",
        formula="OLS fit of close on x=0..period-1 over the window ending at t; "
        "LSMA[t] = fitted value at x = period-1 (the endpoint)",
        notes="Also known as the linear-regression endpoint / time-series forecast. "
        "The fitted endpoint is causal: the window ends at t.",
    )
)
def lsma(data: dict[str, np.ndarray], period: int = 25) -> IndicatorResult:
    end, _, _ = regression_triplet(data["close"], period)
    return IndicatorResult(name="lsma", params={}, values={"lsma": end})


@register(
    IndicatorMeta(
        name="linreg_slope",
        label="Linear Regression Slope",
        category="trend",
        params={"period": 20},
        inputs=("close",),
        outputs=("slope",),
        warmup=lambda p: p["period"] - 1,
        reference="Standard OLS; slope of the rolling linear-regression fit.",
        formula="slope[t] = sum((x-xmean)*(y-ymean)) / sum((x-xmean)^2), x=0..period-1, "
        "window ending at t",
        notes="Units are price per bar — compare against the symbol's own history, "
        "not across symbols.",
    )
)
def linreg_slope(data: dict[str, np.ndarray], period: int = 20) -> IndicatorResult:
    _, slope, _ = regression_triplet(data["close"], period)
    return IndicatorResult(name="linreg_slope", params={}, values={"slope": slope})


@register(
    IndicatorMeta(
        name="mcginley_dynamic",
        label="McGinley Dynamic",
        category="trend",
        params={"period": 14},
        inputs=("close",),
        outputs=("md",),
        warmup=lambda p: p["period"] - 1,
        reference="John R. McGinley, 'The McGinley Dynamic' (1990s).",
        formula="MD[t] = MD[t-1] + (close[t] - MD[t-1]) / (period * (close[t]/MD[t-1])^4); "
        "seeded with the SMA of the first `period` values",
        notes="Mechanically tracks speed changes of price; the fourth power coefficient "
        "is the author's own tuning.",
    )
)
def mcginley_dynamic(data: dict[str, np.ndarray], period: int = 14) -> IndicatorResult:
    c = data["close"]
    n = len(c)
    out = np.full(n, np.nan)
    if period > 0 and n >= period:
        seed = float(np.mean(c[:period]))
        out[period - 1] = seed
        for t in range(period, n):
            prev = out[t - 1]
            if np.isnan(c[t]) or np.isnan(prev) or prev == 0.0:
                out[t] = prev
                continue
            ratio = c[t] / prev
            out[t] = prev + (c[t] - prev) / (period * ratio**4)
    return IndicatorResult(name="mcginley_dynamic", params={}, values={"md": out})


@register(
    IndicatorMeta(
        name="alligator",
        label="Williams Alligator",
        category="trend",
        params={
            "jaw_period": 13,
            "jaw_offset": 8,
            "teeth_period": 8,
            "teeth_offset": 5,
            "lips_period": 5,
            "lips_offset": 3,
        },
        inputs=("high", "low"),
        outputs=("jaw", "teeth", "lips"),
        warmup=lambda p: max(
            p["jaw_period"] - 1 + p["jaw_offset"],
            p["teeth_period"] - 1 + p["teeth_offset"],
            p["lips_period"] - 1 + p["lips_offset"],
        ),
        output_warmup={
            "jaw": lambda p: p["jaw_period"] - 1 + p["jaw_offset"],
            "teeth": lambda p: p["teeth_period"] - 1 + p["teeth_offset"],
            "lips": lambda p: p["lips_period"] - 1 + p["lips_offset"],
        },
        reference="Bill Williams, Trading Chaos (1995).",
        formula="lines = SMMA(SMMA of (high+low)/2, n) displaced back by `offset` bars: "
        "jaw n=13 offset 8, teeth n=8 offset 5, lips n=5 offset 3",
        notes="The offsets are shifts toward the PAST (causal), matching the original "
        "plotting convention: each line shows an older smoothed value so crossings "
        "read correctly.",
        display="overlay",
    )
)
def alligator(
    data: dict[str, np.ndarray],
    jaw_period: int = 13,
    jaw_offset: int = 8,
    teeth_period: int = 8,
    teeth_offset: int = 5,
    lips_period: int = 5,
    lips_offset: int = 3,
) -> IndicatorResult:
    med = (data["high"] + data["low"]) / 2.0
    jaw = shift(wilder_smooth(med, jaw_period), jaw_offset)
    teeth = shift(wilder_smooth(med, teeth_period), teeth_offset)
    lips = shift(wilder_smooth(med, lips_period), lips_offset)
    return IndicatorResult(name="alligator", params={}, values={"jaw": jaw, "teeth": teeth, "lips": lips})


_GMMA_SHORT = (3, 5, 8, 10, 12, 15)
_GMMA_LONG = (30, 35, 40, 45, 50, 60)


@register(
    IndicatorMeta(
        name="gmma",
        label="Guppy Multiple Moving Average",
        category="trend",
        params={},
        inputs=("close",),
        outputs=tuple(f"sma_{p}" for p in (*_GMMA_SHORT, *_GMMA_LONG)),
        warmup=lambda p: 59,  # overall = longest line; per-output warm-ups below are authoritative
        output_warmup={f"sma_{p}": p - 1 for p in (*_GMMA_SHORT, *_GMMA_LONG)},
        reference="Daryl Guppy, 'Trading Tactics' (1998).",
        formula="12 SMAs of close: short group (3,5,8,10,12,15) tracks traders, "
        "long group (30,35,40,45,50,60) tracks investors.",
        notes="The compression/expansion of the two groups is the signal; the raw "
        "lines carry no direction on their own.",
        display="overlay",
    )
)
def gmma(data: dict[str, np.ndarray]) -> IndicatorResult:
    c = data["close"]
    vals = {f"sma_{p}": rolling_mean(c, p) for p in (*_GMMA_SHORT, *_GMMA_LONG)}
    return IndicatorResult(name="gmma", params={}, values=vals)


@register(
    IndicatorMeta(
        name="envelopes",
        label="Moving Average Envelopes",
        category="trend",
        params={"period": 20, "percent": 1.0},
        inputs=("close",),
        outputs=("upper", "middle", "lower"),
        warmup=lambda p: p["period"] - 1,
        reference="Standard MA-envelope construction (percent bands around an SMA).",
        formula="middle = SMA(close, period); upper = middle * (1 + percent/100); "
        "lower = middle * (1 - percent/100)",
        notes="A fixed-percent band, unlike Bollinger's volatility-scaled band.",
    )
)
def envelopes(data: dict[str, np.ndarray], period: int = 20, percent: float = 1.0) -> IndicatorResult:
    mid = rolling_mean(data["close"], period)
    k = percent / 100.0
    return IndicatorResult(
        name="envelopes",
        params={},
        values={"upper": mid * (1.0 + k), "middle": mid, "lower": mid * (1.0 - k)},
    )
