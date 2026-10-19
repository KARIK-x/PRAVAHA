"""Momentum / oscillators."""

from __future__ import annotations

import numpy as np

from megatool.ta.core import (
    IndicatorMeta,
    IndicatorResult,
    ema,
    register,
    rolling_mean,
    rolling_sum,
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
        notes="Wilder smoothing (alpha = 1/period), not a plain moving average. "
        "A series that never moves has RS = 0/0, which is undefined: RSI is "
        "left as NaN and reported as insufficient_data rather than being "
        "given a directional value.",
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
    # No losses at all -> RSI is 100 by definition. The `avg_gain > 0` guard is
    # load-bearing: when BOTH averages are zero the series never moved, RS =
    # 0/0 is undefined, and the NaN already produced by the division above is
    # deliberately kept. Without the guard a flat series was reported as 100 -
    # a claim of maximum bullish momentum that the data does not support.
    out[(avg_loss == 0) & (avg_gain > 0)] = 100.0
    # No gains at all -> RSI is 0 by definition.
    out[(avg_gain == 0) & (avg_loss > 0)] = 0.0
    # Neither branch fires when both averages are zero, so a series that never
    # moved stays NaN. If that leaves nothing defined at all, report it as
    # insufficient data rather than a silent row of NaNs.
    if np.isnan(out).all():
        return IndicatorResult(
            name="rsi",
            params={},
            values={"rsi": out},
            insufficient_data=True,
            message=(
                f"rsi({period}) is undefined for this series: the price never "
                "moved, so average gains and average losses are both zero and "
                "RS = 0/0 has no value"
            ),
        )
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
        notes="Percentage change over n bars. A zero base price is not guarded; use on series that never touch zero.",
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
        notes="Absolute price change over n bars. Unlike ROC, the result is in price units, so it scales with the instrument.",
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


@register(
    IndicatorMeta(
        name="stochastic_rsi",
        label="Stochastic RSI",
        category="momentum",
        params={"rsi_period": 14, "stoch_period": 14},
        inputs=("close",),
        outputs=("stoch_rsi",),
        warmup=lambda p: p["rsi_period"] + p["stoch_period"] - 1,
        reference="Tushar Chande & Stanley Kroll, The New Technical Trader (1994).",
        formula="StochRSI[t] = 100 * (RSI[t] - min(RSI, stoch_period)) "
        "/ (max(RSI, stoch_period) - min(RSI, stoch_period))",
        notes="A stochastic of the RSI series, bounded 0-100 when defined. If the RSI "
        "is flat over the window the range is 0/0 and the value stays NaN.",
    )
)
def stochastic_rsi(
    data: dict[str, np.ndarray], rsi_period: int = 14, stoch_period: int = 14
) -> IndicatorResult:
    n = len(data["close"])
    out = np.full(n, np.nan)
    rsi_v = rsi(data, rsi_period).values["rsi"]
    if n < rsi_period + stoch_period - 1:
        return IndicatorResult(
            name="stochastic_rsi",
            params={},
            values={"stoch_rsi": out},
            insufficient_data=True,
            message=(
                f"stochastic_rsi needs at least {rsi_period + stoch_period - 1} bars, got {n}"
            ),
        )
    for i in range(rsi_period + stoch_period - 2, n):
        w = rsi_v[i - stoch_period + 1 : i + 1]
        if np.any(np.isnan(w)):
            continue
        lo, hi = float(np.min(w)), float(np.max(w))
        if hi == lo:
            continue
        out[i] = 100.0 * (float(rsi_v[i]) - lo) / (hi - lo)
    return IndicatorResult(name="stochastic_rsi", params={}, values={"stoch_rsi": out})


@register(
    IndicatorMeta(
        name="ppo",
        label="Percentage Price Oscillator",
        category="momentum",
        params={"fast": 12, "slow": 26, "signal": 9},
        inputs=("close",),
        outputs=("ppo", "signal", "histogram"),
        warmup=lambda p: p["slow"] + p["signal"] - 2,
        output_warmup={
            "ppo": lambda p: p["slow"] - 1,
            "signal": lambda p: p["slow"] + p["signal"] - 2,
            "histogram": lambda p: p["slow"] + p["signal"] - 2,
        },
        reference="Gerald Appel: the MACD expressed as a percentage of the slow EMA.",
        formula="PPO = 100*(EMA(fast) - EMA(slow))/EMA(slow); signal = EMA(PPO, signal)",
        notes="Percentage form, so price level does not distort the reading.",
    )
)
def ppo(
    data: dict[str, np.ndarray], fast: int = 12, slow: int = 26, signal: int = 9
) -> IndicatorResult:
    c = data["close"]
    if fast >= slow:
        raise ValueError(f"ppo: fast ({fast}) must be < slow ({slow})")
    e_fast, e_slow = ema(c, fast), ema(c, slow)
    with np.errstate(invalid="ignore", divide="ignore"):
        line = 100.0 * (e_fast - e_slow) / e_slow
    sig = ema(line, signal)
    return IndicatorResult(
        name="ppo", params={}, values={"ppo": line, "signal": sig, "histogram": line - sig}
    )


@register(
    IndicatorMeta(
        name="cmo",
        label="Chande Momentum Oscillator",
        category="momentum",
        params={"period": 14},
        inputs=("close",),
        outputs=("cmo",),
        warmup=lambda p: p["period"],
        reference="Tushar Chande, The New Technical Trader (1994).",
        formula="CMO = 100*(sum_up - sum_down)/(sum_up + sum_down) over absolute price changes",
        notes="Bounded -100..100. Every change enters as a magnitude, so a flat "
        "window is 0/0 and stays NaN rather than being forced to 0.",
    )
)
def cmo(data: dict[str, np.ndarray], period: int = 14) -> IndicatorResult:
    c = data["close"]
    n = len(c)
    out = np.full(n, np.nan)
    if n < period + 1:
        return IndicatorResult(
            name="cmo",
            params={},
            values={"cmo": out},
            insufficient_data=True,
            message=f"cmo({period}) needs at least {period + 1} bars, got {n}",
        )
    delta = np.diff(c)
    delta = np.concatenate(([np.nan], delta))
    up = np.where(delta > 0, delta, 0.0)
    dn = np.where(delta < 0, -delta, 0.0)
    up = np.where(np.isnan(delta), np.nan, up)
    dn = np.where(np.isnan(delta), np.nan, dn)
    su = rolling_sum(up, period)
    sd = rolling_sum(dn, period)
    with np.errstate(invalid="ignore", divide="ignore"):
        out = 100.0 * (su - sd) / (su + sd)
    return IndicatorResult(name="cmo", params={}, values={"cmo": out})


@register(
    IndicatorMeta(
        name="tsi",
        label="True Strength Index",
        category="momentum",
        params={"long": 25, "short": 13},
        inputs=("close",),
        outputs=("tsi",),
        warmup=lambda p: p["long"] + p["short"] - 1,
        reference="William Blau, Momentum, Direction and Divergence (1995).",
        formula="TSI = 100 * EMA(EMA(change, long), short) / EMA(EMA(|change|, long), short)",
        notes="Double-smoothed momentum over its double-smoothed absolute value; "
        "bounded -100..100 where the denominator is non-zero.",
    )
)
def tsi(data: dict[str, np.ndarray], long: int = 25, short: int = 13) -> IndicatorResult:
    c = data["close"]
    m = np.diff(c)
    m = np.concatenate(([np.nan], m))
    am = np.abs(m)
    num = ema(ema(m, long), short)
    den = ema(ema(am, long), short)
    with np.errstate(invalid="ignore", divide="ignore"):
        out = 100.0 * num / den
    out = np.where(den == 0, np.nan, out)
    return IndicatorResult(name="tsi", params={}, values={"tsi": out})
