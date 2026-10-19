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
        notes="Seeded with the SMA of the first `period` values; matches standard references once past warm-up.",
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
        notes="Linear weights 1..period; the most recent bar carries the largest weight.",
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
        notes="True range is max(high-low, |high-prevClose|, |low-prevClose|), then Wilder-smoothed. The first `period` bars are warm-up.",
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

    return IndicatorResult(
        name="supertrend", params={}, values={"supertrend": st, "direction": direction}
    )


@register(
    IndicatorMeta(
        name="vwma",
        label="Volume-Weighted Moving Average",
        category="trend",
        params={"period": 20},
        inputs=("close", "volume"),
        outputs=("vwma",),
        warmup=lambda p: p["period"] - 1,
        reference="A simple average whose observations are each weighted by that bar's volume.",
        formula="VWMA[t] = sum(close[i]*volume[i]) / sum(volume[i]) over i in [t-period+1 .. t]",
        notes="This is a *rolling* volume-weighted average of bar closes. It is NOT "
        "session VWAP, which requires trade-level (intraday) data that NEPSE daily "
        "history does not contain.",
    )
)
def vwma(data: dict[str, np.ndarray], period: int = 20) -> IndicatorResult:
    c = data["close"]
    if "volume" not in data:
        raise ValueError("vwma requires a 'volume' input")
    v = data["volume"]
    n = len(c)
    out = np.full(n, np.nan)
    if n < period:
        return IndicatorResult(
            name="vwma",
            params={},
            values={"vwma": out},
            insufficient_data=True,
            message=f"vwma({period}) needs at least {period} bars, got {n}",
        )
    for i in range(period - 1, n):
        w = c[i - period + 1 : i + 1]
        vv = v[i - period + 1 : i + 1]
        if np.any(np.isnan(w)) or np.any(np.isnan(vv)):
            continue
        denom = float(vv.sum())
        # Zero total volume makes the weighted average 0/0: undefined, not zero.
        if denom == 0.0:
            continue
        out[i] = float(np.dot(w, vv) / denom)
    if np.isnan(out).all():
        return IndicatorResult(
            name="vwma",
            params={},
            values={"vwma": out},
            insufficient_data=True,
            message="vwma is undefined for this series (no usable volume window)",
        )
    return IndicatorResult(name="vwma", params={}, values={"vwma": out})


@register(
    IndicatorMeta(
        name="dema",
        label="Double Exponential Moving Average",
        category="trend",
        params={"period": 20},
        inputs=("close",),
        outputs=("dema",),
        warmup=lambda p: 2 * (p["period"] - 1),
        reference="Patrick Mulloy, 1994.",
        formula="DEMA[t] = 2*EMA(close, p) - EMA(EMA(close, p), p)",
        notes="Composed EMAs share the core EMA seeding (SMA of the first window).",
    )
)
def dema(data: dict[str, np.ndarray], period: int = 20) -> IndicatorResult:
    c = data["close"]
    e1 = ema(c, period)
    e2 = ema(e1, period)
    return IndicatorResult(name="dema", params={}, values={"dema": 2.0 * e1 - e2})


@register(
    IndicatorMeta(
        name="tema",
        label="Triple Exponential Moving Average",
        category="trend",
        params={"period": 20},
        inputs=("close",),
        outputs=("tema",),
        warmup=lambda p: 3 * (p["period"] - 1),
        reference="Patrick Mulloy, 1994.",
        formula="TEMA[t] = 3*EMA - 3*EMA(EMA) + EMA(EMA(EMA))",
        notes="Triple exponential; very fast reaction, larger warm-up than EMA.",
    )
)
def tema(data: dict[str, np.ndarray], period: int = 20) -> IndicatorResult:
    c = data["close"]
    e1 = ema(c, period)
    e2 = ema(e1, period)
    e3 = ema(e2, period)
    return IndicatorResult(name="tema", params={}, values={"tema": 3.0 * e1 - 3.0 * e2 + e3})


@register(
    IndicatorMeta(
        name="kama",
        label="Kaufman Adaptive Moving Average",
        category="trend",
        params={"period": 10, "fast": 2, "slow": 30},
        inputs=("close",),
        outputs=("kama",),
        warmup=lambda p: p["period"] - 1,
        reference="Perry Kaufman, Trading Systems and Methods (1995/2013).",
        formula="ER = |change| / volatility; SC = (ER*(fast_sc - slow_sc) + slow_sc)^2; "
        "KAMA[t] = KAMA[t-1] + SC*(close[t] - KAMA[t-1])",
        notes="Seeded with the close at the end of the first `period` window. "
        "A window with zero volatility has ER = 0 by convention (change is then "
        "necessarily 0 too), never 0/0.",
    )
)
def kama(
    data: dict[str, np.ndarray], period: int = 10, fast: int = 2, slow: int = 30
) -> IndicatorResult:
    c = data["close"]
    n = len(c)
    out = np.full(n, np.nan)
    if n < period:
        return IndicatorResult(
            name="kama",
            params={},
            values={"kama": out},
            insufficient_data=True,
            message=f"kama({period}) needs at least {period} bars, got {n}",
        )
    fast_sc = 2.0 / (fast + 1)
    slow_sc = 2.0 / (slow + 1)
    out[period - 1] = float(c[period - 1])
    for i in range(period, n):
        change = abs(float(c[i]) - float(c[i - period]))
        # Kaufman's volatility is the sum of the last `period` absolute changes,
        # i.e. a window of period+1 bars. Using np.diff over only `period` bars
        # silently drops the most recent change and understates volatility.
        volatility = float(np.nansum(np.abs(np.diff(c[i - period : i + 1]))))
        er = 0.0 if volatility == 0.0 else change / volatility
        sc = (er * (fast_sc - slow_sc) + slow_sc) ** 2
        prev = out[i - 1]
        out[i] = prev + sc * (float(c[i]) - prev)
    return IndicatorResult(name="kama", params={}, values={"kama": out})


@register(
    IndicatorMeta(
        name="parabolic_sar",
        label="Parabolic Stop and Reverse",
        category="trend",
        params={"step": 0.02, "maximum": 0.2},
        inputs=("high", "low"),
        outputs=("sar",),
        warmup=1,
        reference="J. Welles Wilder, New Concepts in Technical Trading Systems (1978).",
        formula="SAR[t] = SAR[t-1] + AF*(EP - SAR[t-1]); AF grows by `step` while the "
        "extreme point (EP) advances, up to `maximum`; SAR flips side when price "
        "crosses it.",
        notes="The first bar has no SAR. In an uptrend the SAR is clamped below the "
        "prior two lows; in a downtrend it is clamped above the prior two highs.",
    )
)
def parabolic_sar(
    data: dict[str, np.ndarray], step: float = 0.02, maximum: float = 0.2
) -> IndicatorResult:
    high = data["high"]
    low = data["low"]
    n = len(high)
    out = np.full(n, np.nan)
    if n < 3:
        return IndicatorResult(
            name="parabolic_sar",
            params={},
            values={"sar": out},
            insufficient_data=True,
            message=f"parabolic_sar needs at least 3 bars, got {n}",
        )
    uptrend = True
    af = step
    sar = float(min(low[0], low[1]))
    ep = float(high[0])
    out[1] = sar
    for i in range(2, n):
        prior_sar = sar
        sar = prior_sar + af * (ep - prior_sar)
        if uptrend:
            if sar > float(low[i]):
                # Reversal down: seed the SAR at the recent extreme.
                uptrend = False
                sar = float(max(high[i - 1], high[i]))
                ep = float(low[i])
                af = step
            else:
                sar = min(sar, float(low[i - 1]), float(low[i - 2]))
                if float(high[i]) > ep:
                    ep = float(high[i])
                    af = min(af + step, maximum)
        else:
            if sar < float(high[i]):
                uptrend = True
                sar = float(min(low[i - 1], low[i]))
                ep = float(high[i])
                af = step
            else:
                sar = max(sar, float(high[i - 1]), float(high[i - 2]))
                if float(low[i]) < ep:
                    ep = float(low[i])
                    af = min(af + step, maximum)
        out[i] = float(sar)
    return IndicatorResult(name="parabolic_sar", params={}, values={"sar": out})
