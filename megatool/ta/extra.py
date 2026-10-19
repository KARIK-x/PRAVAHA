"""Additional standard indicators (batch 1).

Every function here follows the same contract as the rest of the engine: the
formula in ``IndicatorMeta.formula`` is the formula that the code runs, the
warm-up is the number of leading bars the implementation can only fill with
NaN, and nothing is asserted about a series that is too short.

Nothing in this module is a forecast. Thresholds and pivot definitions are
stated so a reader can check the output against the rule.
"""

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
    rolling_sum,
    shift,
    true_range,
    wilder_smooth,
)


# --------------------------------------------------------------------- trend
@register(
    IndicatorMeta(
        name="vortex",
        label="Vortex Indicator",
        category="trend",
        params={"period": 14},
        inputs=("high", "low", "close"),
        outputs=("vi_plus", "vi_minus"),
        warmup=lambda p: p["period"],
        display="pane",
        reference="Etienne Botes & Douglas Siepman, 2009 (published in Technical Analysis of Stocks & Commodities, 2010).",
        formula=(
            "VM+ = |high - prev low| ; VM- = |low - prev high| ; TR = true range ; "
            "VI+ = sum(VM+, n) / sum(TR, n) ; VI- = sum(VM-, n) / sum(TR, n)"
        ),
        notes=(
            "Both lines sit around 1.0. The conventional reading is that VI+ crossing above VI- "
            "marks an up-trend and the reverse a down-trend. Crossovers are frequent, so on their "
            "own they are noisy; they are not a trade signal."
        ),
    )
)
def vortex(data: dict[str, np.ndarray], period: int = 14) -> IndicatorResult:
    h = data["high"]
    low = data["low"]
    c = data["close"]
    vm_plus = np.abs(h - shift(low, 1))
    vm_minus = np.abs(low - shift(h, 1))
    tr = true_range(h, low, c)
    num_p = rolling_sum(vm_plus, period)
    num_m = rolling_sum(vm_minus, period)
    den = rolling_sum(tr, period)
    with np.errstate(divide="ignore", invalid="ignore"):
        vi_plus = num_p / den
        vi_minus = num_m / den
    return IndicatorResult(
        name="vortex", params={}, values={"vi_plus": vi_plus, "vi_minus": vi_minus}
    )


@register(
    IndicatorMeta(
        name="ma_cross",
        label="Moving Average Cross (fast vs slow SMA)",
        category="trend",
        params={"fast": 20, "slow": 50},
        inputs=("close",),
        outputs=("fast", "slow", "diff", "state"),
        warmup=lambda p: p["slow"] - 1,
        output_warmup={
            "fast": lambda p: p["fast"] - 1,
            "diff": lambda p: p["slow"] - 1,
            "state": lambda p: p["slow"] - 1,
        },
        display="overlay",
        reference="Classic dual-moving-average crossover (Gardner; widely published).",
        formula=(
            "fast = SMA(close, fast) ; slow = SMA(close, slow) ; diff = fast - slow ; "
            "state = +1 while fast > slow else -1 (0 before the first full window)"
        ),
        notes=(
            "Both averages are simple means of the close over their windows. The `state` column "
            "is the crossover regime, not a recommendation; whipsaws in sideways markets are the "
            "known failure mode."
        ),
    )
)
def ma_cross(data: dict[str, np.ndarray], fast: int = 20, slow: int = 50) -> IndicatorResult:
    c = data["close"]
    f = rolling_mean(c, fast)
    s = rolling_mean(c, slow)
    diff = f - s
    with np.errstate(invalid="ignore"):
        # During warm-up `state` is a gap, not 0: "no reading" and "flat" are
        # different statements and must not be conflated.
        state = np.where(np.isfinite(diff), np.where(diff > 0, 1.0, -1.0), np.nan)
    return IndicatorResult(
        name="ma_cross", params={}, values={"fast": f, "slow": s, "diff": diff, "state": state}
    )


@register(
    IndicatorMeta(
        name="chande_kroll_stop",
        label="Chande Kroll Stop",
        category="trend",
        params={"period": 10, "multiplier": 1.0, "atr_period": 10, "trail": 3.0},
        inputs=("high", "low", "close"),
        outputs=("stop_long", "stop_short", "initial_long", "initial_short"),
        warmup=lambda p: max(p["period"], p["atr_period"]),
        display="overlay",
        reference="Tushar Chande & Stanley Kroll (1995), 'The New Technical Trader'.",
        formula=(
            "ATR = Wilder ATR(atr_period) ; xATR = multiplier * ATR ; yATR = trail * ATR ; "
            "initial_long = max(high, period) - xATR ; initial_short = min(low, period) + xATR ; "
            "stop_long = max(stop_long[-1], close - yATR) ; stop_short = min(stop_short[-1], close + yATR), "
            "seeded from the initial stops"
        ),
        notes=(
            "Both stages are exposed: `initial_long/short` are the first-stage stops (highest/lowest "
            "over the window), and `stop_long/short` are the trailing stage. The trailing stage uses "
            "the previous stop, so it is path-dependent — recomputing over a different window start "
            "can shift it. ATR uses Wilder smoothing with an SMA seed."
        ),
    )
)
def chande_kroll_stop(
    data: dict[str, np.ndarray],
    period: int = 10,
    multiplier: float = 1.0,
    atr_period: int = 10,
    trail: float = 3.0,
) -> IndicatorResult:
    h = data["high"]
    low = data["low"]
    c = data["close"]
    n = len(c)
    atr_v = wilder_smooth(true_range(h, low, c), atr_period)
    hh = rolling_max(h, period)
    ll = rolling_min(low, period)
    x_atr = multiplier * atr_v
    y_atr = trail * atr_v
    init_long = hh - x_atr
    init_short = ll + x_atr
    stop_long = np.full(n, np.nan)
    stop_short = np.full(n, np.nan)
    prev_l = np.nan
    prev_s = np.nan
    for i in range(n):
        if not (np.isfinite(init_long[i]) and np.isfinite(init_short[i])):
            continue
        if not np.isfinite(prev_l):
            prev_l = init_long[i]
            prev_s = init_short[i]
        else:
            prev_l = max(prev_l, c[i] - y_atr[i])
            prev_s = min(prev_s, c[i] + y_atr[i])
        stop_long[i] = prev_l
        stop_short[i] = prev_s
    return IndicatorResult(
        name="chande_kroll_stop",
        params={},
        values={
            "stop_long": stop_long,
            "stop_short": stop_short,
            "initial_long": init_long,
            "initial_short": init_short,
        },
    )


# ----------------------------------------------------------------- volatility
@register(
    IndicatorMeta(
        name="bollinger_width",
        label="Bollinger Band Width (percent)",
        category="volatility",
        params={"period": 20, "std_dev": 2.0},
        inputs=("close",),
        outputs=("width_pct",),
        warmup=lambda p: p["period"] - 1,
        display="pane",
        reference="John Bollinger, 1980s (band-width presentation).",
        formula=(
            "middle = SMA(close, n) ; sd = population stddev(close, n) ; "
            "upper/lower = middle +/- k*sd ; width_pct = 100 * (upper - lower) / middle"
        ),
        notes=(
            "Expressed in PERCENT (100 * ratio), unlike the `bandwidth` column of the Bollinger "
            "Bands indicator, which is the raw ratio. Width is scale-free, so it can be compared "
            "across symbols; a low reading is 'squeeze' only in relative terms (compare it with its "
            "own history — no fixed threshold is asserted here)."
        ),
    )
)
def bollinger_width(
    data: dict[str, np.ndarray], period: int = 20, std_dev: float = 2.0
) -> IndicatorResult:
    c = data["close"]
    mid = rolling_mean(c, period)
    sd = rolling_std(c, period, ddof=0)
    with np.errstate(divide="ignore", invalid="ignore"):
        width_pct = 100.0 * (2.0 * std_dev * sd) / mid
    return IndicatorResult(name="bollinger_width", params={}, values={"width_pct": width_pct})


@register(
    IndicatorMeta(
        name="percent_b",
        label="Bollinger %B",
        category="volatility",
        params={"period": 20, "std_dev": 2.0},
        inputs=("close",),
        outputs=("percent_b",),
        warmup=lambda p: p["period"] - 1,
        display="pane",
        reference="John Bollinger, 1980s.",
        formula=(
            "middle = SMA(close, n) ; sd = population stddev(close, n) ; "
            "upper/lower = middle +/- k*sd ; %B = (close - lower) / (upper - lower)"
        ),
        notes=(
            "1.0 = close at the upper band, 0.0 = close at the lower band, 0.5 = at the middle. "
            "Values outside [0,1] mean the close is outside the band. When upper == lower the "
            "result is undefined and reported as a gap."
        ),
    )
)
def percent_b(
    data: dict[str, np.ndarray], period: int = 20, std_dev: float = 2.0
) -> IndicatorResult:
    c = data["close"]
    mid = rolling_mean(c, period)
    sd = rolling_std(c, period, ddof=0)
    up = mid + std_dev * sd
    lo = mid - std_dev * sd
    with np.errstate(divide="ignore", invalid="ignore"):
        pb = (c - lo) / (up - lo)
    return IndicatorResult(name="percent_b", params={}, values={"percent_b": pb})


@register(
    IndicatorMeta(
        name="chaikin_volatility",
        label="Chaikin Volatility",
        category="volatility",
        params={"ema_period": 10, "roc_period": 10},
        inputs=("high", "low"),
        outputs=("chaikin_vol",),
        warmup=lambda p: p["ema_period"] - 1 + p["roc_period"],
        display="pane",
        reference="Marc Chaikin (published in Technical Analysis of Stocks & Commodities).",
        formula=(
            "hl = high - low ; e = EMA(hl, ema_period) ; "
            "chaikin_vol = 100 * (e - e[roc_period ago]) / e[roc_period ago]"
        ),
        notes=(
            "A positive reading means the high-low range is expanding relative to roc_period bars "
            "ago, negative means contracting. It measures range expansion only — it is directionless."
        ),
    )
)
def chaikin_volatility(
    data: dict[str, np.ndarray], ema_period: int = 10, roc_period: int = 10
) -> IndicatorResult:
    hl = data["high"] - data["low"]
    e = ema(hl, ema_period)
    prev = shift(e, roc_period)
    with np.errstate(divide="ignore", invalid="ignore"):
        out = 100.0 * (e - prev) / prev
    return IndicatorResult(name="chaikin_volatility", params={}, values={"chaikin_vol": out})


@register(
    IndicatorMeta(
        name="relative_volatility_index",
        label="Relative Volatility Index",
        category="volatility",
        params={"period": 10, "signal": 14},
        inputs=("close",),
        outputs=("rvi", "signal"),
        warmup=lambda p: 2 * p["period"] + p["signal"] - 3,
        output_warmup={
            "rvi": lambda p: 2 * p["period"] - 2,
            "signal": lambda p: 2 * p["period"] + p["signal"] - 3,
        },
        display="pane",
        reference="Donald Dorsey, 1993 (Technical Analysis of Stocks & Commodities).",
        formula=(
            "sd = population stddev(close, n) ; up = sd where close > close[-1] else 0 ; "
            "dn = sd where close < close[-1] else 0 ; "
            "rvi = 100 * Wilder(up, n) / (Wilder(up, n) + Wilder(dn, n)) ; signal = SMA(rvi, signal)"
        ),
        notes=(
            "Unlike RSI, which weights by price change size, the RVI weights by the standard "
            "deviation of the close, so large moves in either direction raise it. Dorsey's "
            "published threshold is 50 (above = up-side volatility dominates), stated here as the "
            "author's rule, not as verified for NEPSE."
        ),
    )
)
def relative_volatility_index(
    data: dict[str, np.ndarray], period: int = 10, signal: int = 14
) -> IndicatorResult:
    c = data["close"]
    sd = rolling_std(c, period, ddof=0)
    diff = c - shift(c, 1)
    up = np.where(np.isfinite(diff) & (diff > 0), sd, 0.0)
    dn = np.where(np.isfinite(diff) & (diff < 0), sd, 0.0)
    up[~np.isfinite(sd)] = np.nan
    dn[~np.isfinite(sd)] = np.nan
    su = wilder_smooth(up, period)
    sn = wilder_smooth(dn, period)
    with np.errstate(divide="ignore", invalid="ignore"):
        rvi = 100.0 * su / (su + sn)
    return IndicatorResult(
        name="relative_volatility_index",
        params={},
        values={"rvi": rvi, "signal": rolling_mean(rvi, signal)},
    )


# ---------------------------------------------------------------------- other
@register(
    IndicatorMeta(
        name="average_price",
        label="Average Price (OHLC/4)",
        category="other",
        params={},
        inputs=("open", "high", "low", "close"),
        outputs=("average_price",),
        warmup=0,
        display="overlay",
        reference="Common OHLC mean; used by several platforms as 'AvgPrice'.",
        formula="average_price = (open + high + low + close) / 4",
        notes=(
            "A single smoothed price per bar. It is the mean of the bar's four published prices, "
            "not a volume-weighted average and not a moving average."
        ),
    )
)
def average_price(data: dict[str, np.ndarray]) -> IndicatorResult:
    ap = (data["open"] + data["high"] + data["low"] + data["close"]) / 4.0
    return IndicatorResult(name="average_price", params={}, values={"average_price": ap})


@register(
    IndicatorMeta(
        name="price_correlation",
        label="Rolling Price Correlation (with time)",
        category="other",
        params={"period": 20},
        inputs=("close",),
        outputs=("corr",),
        warmup=lambda p: p["period"] - 1,
        display="pane",
        reference="Pearson product-moment correlation, applied to (bar index, close).",
        formula=(
            "x = 0..n-1 over the window ; corr = cov(x, close) / (stddev(x) * stddev(close)), "
            "using population moments (ddof=0) over the last `period` bars"
        ),
        notes=(
            "Near +1 means the close has risen almost monotonically over the window, near -1 almost "
            "monotonically fallen, near 0 means no linear trend. It measures LINEAR dependence only "
            "and says nothing about volatility or about future direction. x is the bar index, so a "
            "gap-free series is assumed — missing bars are not modelled."
        ),
    )
)
def price_correlation(data: dict[str, np.ndarray], period: int = 20) -> IndicatorResult:
    c = data["close"]
    n = len(c)
    x = np.arange(n, dtype=float)
    mx = rolling_mean(x, period)
    my = rolling_mean(c, period)
    mxy = rolling_mean(x * c, period)
    mxx = rolling_mean(x * x, period)
    myy = rolling_mean(c * c, period)
    vx = mxx - mx * mx
    vy = myy - my * my
    with np.errstate(divide="ignore", invalid="ignore"):
        corr = (mxy - mx * my) / np.sqrt(vx * vy)
    corr[~np.isfinite(corr)] = np.nan
    return IndicatorResult(name="price_correlation", params={}, values={"corr": corr})


@register(
    IndicatorMeta(
        name="williams_fractal",
        label="Williams Fractal",
        category="other",
        params={"window": 2},
        inputs=("high", "low"),
        outputs=("fractal_up", "fractal_down"),
        warmup=lambda p: p["window"],
        display="overlay",
        reference="Bill Williams, 'Trading Chaos' (1995).",
        formula=(
            "up[i] = high[i] if high[i] is strictly the highest of the 2*W+1 bars centred on i, "
            "else NaN ; down[i] = low[i] if low[i] is strictly the lowest of those bars, else NaN"
        ),
        notes=(
            "A fractal is only knowable W bars after it forms (the right side must close), so the "
            "value is stamped on the pivot bar but is not usable until W bars later. The last W "
            "bars are provisional and can still gain a fractal. "
            "Strict inequality means equal highs/lows produce no fractal."
        ),
    )
)
def williams_fractal(data: dict[str, np.ndarray], window: int = 2) -> IndicatorResult:
    h = data["high"]
    low = data["low"]
    n = len(h)
    up = np.full(n, np.nan)
    dn = np.full(n, np.nan)
    w = int(window)
    for i in range(w, n - w):
        lo_i = i - w
        hi_i = i + w + 1
        win_h = h[lo_i:hi_i]
        win_l = low[lo_i:hi_i]
        if np.isfinite(h[i]) and h[i] == np.nanmax(win_h) and (win_h == h[i]).sum() == 1:
            up[i] = h[i]
        if np.isfinite(low[i]) and low[i] == np.nanmin(win_l) and (win_l == low[i]).sum() == 1:
            dn[i] = low[i]
    return IndicatorResult(
        name="williams_fractal", params={}, values={"fractal_up": up, "fractal_down": dn}
    )


@register(
    IndicatorMeta(
        name="zigzag",
        label="Zig Zag (percent threshold)",
        category="other",
        params={"threshold_pct": 5.0},
        inputs=("high", "low", "close"),
        outputs=("zigzag",),
        warmup=0,
        display="overlay",
        reference="Common chartist construction (percent-reversal swing filter).",
        formula=(
            "Track an extreme; when price retraces at least threshold_pct from that extreme, the "
            "extreme is confirmed as a pivot and the direction flips. The pivot's price is stamped "
            "on its bar; every other bar is a gap."
        ),
        notes=(
            "Purely descriptive: it labels swings that already happened and is REVISED up to the "
            "last pivot, because the final extreme is provisional until the threshold is breached. "
            "It does not predict the next pivot. Threshold is in percent of the running extreme."
        ),
    )
)
def zigzag(data: dict[str, np.ndarray], threshold_pct: float = 5.0) -> IndicatorResult:
    h = data["high"]
    low = data["low"]
    c = data["close"]
    n = len(c)
    out = np.full(n, np.nan)
    if n < 2:
        return IndicatorResult(name="zigzag", params={}, values={"zigzag": out})
    thr = float(threshold_pct) / 100.0
    direction = 1
    ext_i = 0
    ext_p = h[0]
    for i in range(1, n):
        if not np.isfinite(h[i]) or not np.isfinite(low[i]):
            continue
        if direction == 1:
            if h[i] > ext_p:
                ext_i, ext_p = i, h[i]
            elif ext_p > 0 and low[i] <= ext_p * (1.0 - thr):
                out[ext_i] = ext_p
                direction = -1
                ext_i, ext_p = i, low[i]
        else:
            if low[i] < ext_p:
                ext_i, ext_p = i, low[i]
            elif ext_p > 0 and h[i] >= ext_p * (1.0 + thr):
                out[ext_i] = ext_p
                direction = 1
                ext_i, ext_p = i, h[i]
    out[ext_i] = ext_p  # provisional: the current extreme is not yet confirmed
    return IndicatorResult(name="zigzag", params={}, values={"zigzag": out})
