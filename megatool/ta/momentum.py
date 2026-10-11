"""Momentum / oscillators."""

from __future__ import annotations

import numpy as np

from megatool.ta.core import (
    IndicatorMeta,
    IndicatorResult,
    ema,
    register,
    rolling_mean,
    shift,
)


@register(
    IndicatorMeta(
        name="rsi",
        label="Relative Strength Index",
        category="momentum",
        params={"period": 14},
        inputs=("close",),
        outputs=("rsi",),
        warmup=lambda p: p["period"],
        reference="J. Welles Wilder, New Concepts in Technical Trading Systems (1978).",
        formula="change = diff(close); avg_gain/loss = Wilder smooth; "
        "RS = avg_gain/avg_loss; RSI = 100 - 100/(1+RS)",
        notes="Wilder smoothing (alpha = 1/period), not a plain moving average.",
    )
)
def rsi(data: dict[str, np.ndarray], period: int = 14) -> IndicatorResult:
    c = data["close"]
    n = len(c)
    out = np.full(n, np.nan)
    if n < period + 1:
        return IndicatorResult(
            name="rsi",
            params={},
            values={"rsi": out},
            insufficient_data=True,
            message=f"rsi({period}) needs at least {period + 1} closes, got {n}",
        )
    delta = np.diff(c)
    gain = np.where(delta > 0, delta, 0.0)
    loss = np.where(delta < 0, -delta, 0.0)
    # Wilder smoothing starts from the simple mean of the first `period` moves.
    avg_gain = np.full(n, np.nan)
    avg_loss = np.full(n, np.nan)
    avg_gain[period] = gain[:period].mean()
    avg_loss[period] = loss[:period].mean()
    alpha = 1.0 / period
    for i in range(period + 1, n):
        avg_gain[i] = avg_gain[i - 1] * (1 - alpha) + gain[i - 1] * alpha
        avg_loss[i] = avg_loss[i - 1] * (1 - alpha) + loss[i - 1] * alpha

    with np.errstate(divide="ignore", invalid="ignore"):
        rs = avg_gain / avg_loss
        out = 100.0 - 100.0 / (1.0 + rs)
    # No losses at all -> RSI is 100 by definition.
    out[(avg_loss == 0) & ~np.isnan(avg_loss)] = 100.0
    # No gains at all -> RSI is 0.
    out[(avg_gain == 0) & ~np.isnan(avg_gain) & (avg_loss > 0)] = 0.0
    return IndicatorResult(name="rsi", params={}, values={"rsi": out})


@register(
    IndicatorMeta(
        name="macd",
        label="Moving Average Convergence Divergence",
        category="momentum",
        params={"fast": 12, "slow": 26, "signal": 9},
        inputs=("close",),
        outputs=("macd", "signal", "histogram"),
        warmup=lambda p: p["slow"] + p["signal"] - 2,
        output_warmup={
            "macd": lambda p: p["slow"] - 1,
            "signal": lambda p: p["slow"] + p["signal"] - 2,
            "histogram": lambda p: p["slow"] + p["signal"] - 2,
        },
        reference="Gerald Appel, 1979.",
        formula="MACD = EMA(fast) - EMA(slow); signal = EMA(MACD, signal); hist = MACD - signal",
        notes="EMAs are seeded with an SMA of their own period.",
    )
)
def macd(
    data: dict[str, np.ndarray], fast: int = 12, slow: int = 26, signal: int = 9
) -> IndicatorResult:
    c = data["close"]
    if fast >= slow:
        raise ValueError(f"macd: fast ({fast}) must be < slow ({slow})")
    line = ema(c, fast) - ema(c, slow)
    sig = ema(line, signal)
    return IndicatorResult(
        name="macd", params={}, values={"macd": line, "signal": sig, "histogram": line - sig}
    )


@register(
    IndicatorMeta(
        name="stochastic",
        label="Stochastic Oscillator",
        category="momentum",
        params={"k_period": 14, "d_period": 3, "smooth": 3},
        inputs=("high", "low", "close"),
        outputs=("k", "d"),
        warmup=lambda p: p["k_period"] + p["smooth"] + p["d_period"] - 3,
        output_warmup={
            "k": lambda p: p["k_period"] + p["smooth"] - 2,
            "d": lambda p: p["k_period"] + p["smooth"] + p["d_period"] - 3,
        },
        reference="George Lane, 1950s.",
        formula="%K = 100*(close - lowest_low(n)) / (highest_high(n) - lowest_low(n)); "
        "%D = SMA(%K, d)",
        notes="This is the 'slow' stochastic: raw %K is smoothed before %D is taken.",
    )
)
def stochastic(
    data: dict[str, np.ndarray], k_period: int = 14, d_period: int = 3, smooth: int = 3
) -> IndicatorResult:
    h, lo, c = data["high"], data["low"], data["close"]
    n = len(c)
    raw_k = np.full(n, np.nan)
    for i in range(k_period - 1, n):
        hh = np.max(h[i - k_period + 1 : i + 1])
        ll = np.min(lo[i - k_period + 1 : i + 1])
        if hh == ll:
            raw_k[i] = 50.0  # no range: undefined by formula, use neutral
        else:
            raw_k[i] = 100.0 * (c[i] - ll) / (hh - ll)
    k = rolling_mean(raw_k, smooth) if smooth > 1 else raw_k
    d = rolling_mean(k, d_period)
    return IndicatorResult(name="stochastic", params={}, values={"k": k, "d": d})


@register(
    IndicatorMeta(
        name="cci",
        label="Commodity Channel Index",
        category="momentum",
        params={"period": 20},
        inputs=("high", "low", "close"),
        outputs=("cci",),
        warmup=lambda p: p["period"] - 1,
        reference="Donald Lambert, 1980.",
        formula="TP = (H+L+C)/3; CCI = (TP - SMA(TP,n)) / (0.015 * mean deviation)",
        notes="0.015 is Lambert's scaling constant, not a statistical one.",
    )
)
def cci(data: dict[str, np.ndarray], period: int = 20) -> IndicatorResult:
    tp = (data["high"] + data["low"] + data["close"]) / 3.0
    n = len(tp)
    out = np.full(n, np.nan)
    ma = rolling_mean(tp, period)
    for i in range(period - 1, n):
        w = tp[i - period + 1 : i + 1]
        if np.any(np.isnan(w)) or np.isnan(ma[i]):
            continue
        md = np.mean(np.abs(w - ma[i]))
        out[i] = (tp[i] - ma[i]) / (0.015 * md) if md != 0 else 0.0
    return IndicatorResult(name="cci", params={}, values={"cci": out})


@register(
    IndicatorMeta(
        name="roc",
        label="Rate of Change",
        category="momentum",
        params={"period": 12},
        inputs=("close",),
        outputs=("roc",),
        warmup=lambda p: p["period"],
        reference="Standard momentum measure.",
        formula="ROC[t] = 100 * (close[t] - close[t-n]) / close[t-n]",
    )
)
def roc(data: dict[str, np.ndarray], period: int = 12) -> IndicatorResult:
    c = data["close"]
    past = shift(c, period)
    with np.errstate(divide="ignore", invalid="ignore"):
        out = 100.0 * (c - past) / past
    return IndicatorResult(name="roc", params={}, values={"roc": out})


@register(
    IndicatorMeta(
        name="momentum",
        label="Momentum",
        category="momentum",
        params={"period": 10},
        inputs=("close",),
        outputs=("momentum",),
        warmup=lambda p: p["period"],
        reference="Standard momentum measure.",
        formula="MOM[t] = close[t] - close[t-n]",
    )
)
def momentum(data: dict[str, np.ndarray], period: int = 10) -> IndicatorResult:
    return IndicatorResult(
        name="momentum",
        params={},
        values={"momentum": data["close"] - shift(data["close"], period)},
    )


@register(
    IndicatorMeta(
        name="williams_r",
        label="Williams %R",
        category="momentum",
        params={"period": 14},
        inputs=("high", "low", "close"),
        outputs=("williams_r",),
        warmup=lambda p: p["period"] - 1,
        reference="Larry Williams, 1973.",
        formula="%R = -100 * (highest_high(n) - close) / (highest_high - lowest_low)",
        notes="Ranges -100..0; the sign convention is negative, unlike stochastic %K.",
    )
)
def williams_r(data: dict[str, np.ndarray], period: int = 14) -> IndicatorResult:
    h, lo, c = data["high"], data["low"], data["close"]
    n = len(c)
    out = np.full(n, np.nan)
    for i in range(period - 1, n):
        hh = np.max(h[i - period + 1 : i + 1])
        ll = np.min(lo[i - period + 1 : i + 1])
        out[i] = -100.0 * (hh - c[i]) / (hh - ll) if hh != ll else -50.0
    return IndicatorResult(name="williams_r", params={}, values={"williams_r": out})


@register(
    IndicatorMeta(
        name="trix",
        label="TRIX",
        category="momentum",
        params={"period": 15, "signal": 9},
        inputs=("close",),
        outputs=("trix", "signal"),
        warmup=lambda p: 3 * p["period"] + p["signal"] - 3,
        output_warmup={
            "trix": lambda p: 3 * p["period"] - 2,
            "signal": lambda p: 3 * p["period"] + p["signal"] - 3,
        },
        reference="Jack Hutson, 1980s.",
        formula="Triple-smoothed EMA of close; TRIX = 100 * pct change of that EMA.",
        notes="A very smooth momentum measure; slow to react by design.",
    )
)
def trix(data: dict[str, np.ndarray], period: int = 15, signal: int = 9) -> IndicatorResult:
    c = data["close"]
    e1 = ema(c, period)
    e2 = ema(e1, period)
    e3 = ema(e2, period)
    with np.errstate(divide="ignore", invalid="ignore"):
        prev = shift(e3, 1)
        trix_v = 100.0 * (e3 - prev) / prev
    sig = rolling_mean(trix_v, signal)
    return IndicatorResult(name="trix", params={}, values={"trix": trix_v, "signal": sig})


@register(
    IndicatorMeta(
        name="ichimoku",
        label="Ichimoku Kinko Hyo",
        category="trend",
        params={"tenkan": 9, "kijun": 26, "senkou_b": 52},
        inputs=("high", "low", "close"),
        outputs=("tenkan", "kijun", "senkou_a", "senkou_b"),
        warmup=lambda p: p["senkou_b"] - 1,
        output_warmup={
            "tenkan": lambda p: p["tenkan"] - 1,
            "kijun": lambda p: p["kijun"] - 1,
            "senkou_a": lambda p: p["kijun"] - 1,
            "senkou_b": lambda p: p["senkou_b"] - 1,
        },
        reference="Goichi Hosoda, 1930s.",
        formula="Tenkan/Kijun = midpoint of highest-high/lowest-low over n; "
        "Senkou A = (Tenkan+Kijun)/2; Senkou B = midpoint over senkou_b",
        notes="Mega Tool plots Senkou A/B unshifted (no forward displacement), so "
        "nothing here uses future data. The traditional chart shifts them forward "
        "26 bars, which is a display convention, not extra information.",
    )
)
def ichimoku(
    data: dict[str, np.ndarray], tenkan: int = 9, kijun: int = 26, senkou_b: int = 52
) -> IndicatorResult:
    h, lo = data["high"], data["low"]
    n = len(h)

    def mid(period: int) -> np.ndarray:
        out = np.full(n, np.nan)
        for i in range(period - 1, n):
            hh = np.max(h[i - period + 1 : i + 1])
            ll = np.min(lo[i - period + 1 : i + 1])
            out[i] = (hh + ll) / 2.0
        return out

    ten = mid(tenkan)
    kij = mid(kijun)
    sb = mid(senkou_b)
    return IndicatorResult(
        name="ichimoku",
        params={},
        values={
            "tenkan": ten,
            "kijun": kij,
            "senkou_a": (ten + kij) / 2.0,
            "senkou_b": sb,
        },
    )
