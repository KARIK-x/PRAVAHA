"""Volume indicators."""

from __future__ import annotations

import numpy as np

from megatool.ta.core import (
    IndicatorMeta,
    IndicatorResult,
    ema,
    register,
    rolling_mean,
    rolling_sum,
)


def _require_volume(data: dict[str, np.ndarray], name: str) -> np.ndarray:
    if "volume" not in data:
        raise ValueError(f"{name} requires a 'volume' input")
    v = data["volume"]
    if np.all(np.isnan(v)):
        raise ValueError(f"{name}: the volume series is entirely missing")
    return np.where(np.isnan(v), 0.0, v)


@register(
    IndicatorMeta(
        name="obv",
        label="On-Balance Volume",
        category="volume",
        params={},
        inputs=("close", "volume"),
        outputs=("obv",),
        warmup=lambda p: 1,
        reference="Joseph Granville, 1963.",
        formula="OBV[t] = OBV[t-1] + volume[t] if close rises; - volume if it falls; "
        "unchanged if close is flat.",
        notes="Level is arbitrary (starts at 0); only the slope carries meaning.",
    )
)
def obv(data: dict[str, np.ndarray]) -> IndicatorResult:
    c = data["close"]
    v = _require_volume(data, "obv")
    n = len(c)
    out = np.zeros(n)
    for i in range(1, n):
        if c[i] > c[i - 1]:
            out[i] = out[i - 1] + v[i]
        elif c[i] < c[i - 1]:
            out[i] = out[i - 1] - v[i]
        else:
            out[i] = out[i - 1]
    return IndicatorResult(name="obv", params={}, values={"obv": out})


@register(
    IndicatorMeta(
        name="mfi",
        label="Money Flow Index",
        category="volume",
        params={"period": 14},
        inputs=("high", "low", "close", "volume"),
        outputs=("mfi",),
        warmup=lambda p: p["period"],
        reference="Quinn and Weigand, 1990s.",
        formula="raw money flow = typical price * volume; MFI = 100 - 100/(1+money ratio)",
        notes="Often called a 'volume-weighted RSI'; ranges 0-100. A window "
        "with no positive and no negative money flow (constant typical price, "
        "or zero volume) has a money ratio of 0/0, which is undefined: MFI is "
        "left as NaN and reported as insufficient_data rather than being given "
        "a directional value.",
    )
)
def mfi(data: dict[str, np.ndarray], period: int = 14) -> IndicatorResult:
    tp = (data["high"] + data["low"] + data["close"]) / 3.0
    v = _require_volume(data, "mfi")
    mf = tp * v
    n = len(tp)
    out = np.full(n, np.nan)
    if n < period + 1:
        return IndicatorResult(
            name="mfi",
            params={},
            values={"mfi": out},
            insufficient_data=True,
            message=f"mfi({period}) needs at least {period + 1} bars, got {n}",
        )
    pos = np.zeros(n)
    neg = np.zeros(n)
    for i in range(1, n):
        if tp[i] > tp[i - 1]:
            pos[i] = mf[i]
        elif tp[i] < tp[i - 1]:
            neg[i] = mf[i]

    for i in range(period, n):
        p = pos[i - period + 1 : i + 1].sum()
        ng = neg[i - period + 1 : i + 1].sum()
        # `p > 0` is load-bearing. When BOTH sums are zero the money ratio is
        # 0/0, which is undefined, so the honest result is NaN. Without that
        # guard a window with no flow at all (constant typical price, or zero
        # volume) reported 100 - a claim of maximum buying pressure produced by
        # nothing happening. `ng == 0 && p > 0` really is 100: purely positive
        # flow is the maximum by definition.
        if ng == 0:
            out[i] = 100.0 if p > 0 else np.nan
        else:
            out[i] = 100.0 - 100.0 / (1.0 + p / ng)
    return IndicatorResult(name="mfi", params={}, values={"mfi": out})


@register(
    IndicatorMeta(
        name="ad_line",
        label="Accumulation / Distribution Line",
        category="volume",
        params={},
        inputs=("high", "low", "close", "volume"),
        outputs=("ad", "clv"),
        warmup=lambda p: 1,
        reference="Chaikin, 1960s.",
        formula="CLV = ((close-low) - (high-close)) / (high-low); AD = cumsum(CLV * volume)",
        notes="When high == low the CLV is defined as 0 for that bar.",
    )
)
def ad_line(data: dict[str, np.ndarray]) -> IndicatorResult:
    h, lo, c = data["high"], data["low"], data["close"]
    v = _require_volume(data, "ad_line")
    rng = h - lo
    with np.errstate(divide="ignore", invalid="ignore"):
        clv = np.where(rng == 0, 0.0, ((c - lo) - (h - c)) / rng)
    clv = np.where(np.isnan(clv), 0.0, clv)
    ad = np.cumsum(clv * v)
    return IndicatorResult(name="ad_line", params={}, values={"ad": ad, "clv": clv})


@register(
    IndicatorMeta(
        name="relative_volume",
        label="Relative Volume",
        category="volume",
        params={"baseline": 20},
        inputs=("volume",),
        outputs=("rvol",),
        warmup=lambda p: p["baseline"] - 1,
        reference="volume[t] / mean(volume over trailing baseline window)",
        formula="RVOL = volume / SMA(volume, baseline)",
        notes="A value of 2 means twice the recent average volume. Uses only past bars.",
    )
)
def relative_volume(data: dict[str, np.ndarray], baseline: int = 20) -> IndicatorResult:
    v = _require_volume(data, "relative_volume").astype(float)
    avg = rolling_mean(v, baseline)
    with np.errstate(divide="ignore", invalid="ignore"):
        rvol = v / avg
    return IndicatorResult(name="relative_volume", params={}, values={"rvol": rvol})


@register(
    IndicatorMeta(
        name="volume_sma",
        label="Volume Moving Average",
        category="volume",
        params={"period": 20},
        inputs=("volume",),
        outputs=("volume_sma",),
        warmup=lambda p: p["period"] - 1,
        reference="Simple moving average of volume.",
        formula="SMA(volume, n)",
        notes="Simple moving average of volume; a flat/missing volume series makes the average flat or NaN.",
    )
)
def volume_sma(data: dict[str, np.ndarray], period: int = 20) -> IndicatorResult:
    v = _require_volume(data, "volume_sma").astype(float)
    return IndicatorResult(
        name="volume_sma", params={}, values={"volume_sma": rolling_mean(v, period)}
    )


@register(
    IndicatorMeta(
        name="vwap_bands",
        label="VWAP-style rolling band",
        category="volume",
        params={"period": 20},
        inputs=("high", "low", "close", "volume"),
        outputs=("vwap",),
        warmup=lambda p: p["period"] - 1,
        reference="Rolling volume-weighted average price over `period` bars.",
        formula="VWAP = sum(typical_price * volume) / sum(volume) over the window",
        notes="This is a ROLLING VWAP. True session VWAP only makes sense intraday; "
        "NEPSE history here is daily, so this is a rolling approximation.",
    )
)
def vwap_bands(data: dict[str, np.ndarray], period: int = 20) -> IndicatorResult:
    tp = (data["high"] + data["low"] + data["close"]) / 3.0
    v = _require_volume(data, "vwap_bands").astype(float)
    pv = tp * v
    n = len(tp)
    out = np.full(n, np.nan)
    for i in range(period - 1, n):
        vv = v[i - period + 1 : i + 1]
        pp = pv[i - period + 1 : i + 1]
        if vv.sum() == 0:
            continue
        out[i] = pp.sum() / vv.sum()
    return IndicatorResult(name="vwap_bands", params={}, values={"vwap": out})


@register(
    IndicatorMeta(
        name="cmf",
        label="Chaikin Money Flow",
        category="volume",
        params={"period": 20},
        inputs=("high", "low", "close", "volume"),
        outputs=("cmf",),
        warmup=lambda p: p["period"] - 1,
        reference="Marc Chaikin.",
        formula="MFV = (((close-low) - (high-close)) / (high-low)) * volume; "
        "CMF = sum(MFV, period) / sum(volume, period)",
        notes="Bounded -1..1 where defined. A bar whose high equals its low has an "
        "undefined CLV (0/0); its contribution is treated as 0 rather than guessed.",
    )
)
def cmf(data: dict[str, np.ndarray], period: int = 20) -> IndicatorResult:
    high, low, c = data["high"], data["low"], data["close"]
    v = _require_volume(data, "cmf").astype(float)
    rng = high - low
    with np.errstate(invalid="ignore", divide="ignore"):
        clv = ((c - low) - (high - c)) / rng
    clv = np.where(rng == 0, 0.0, clv)
    clv = np.where(np.isnan(rng), np.nan, clv)
    mfv = clv * v
    mfv = np.where(np.isnan(mfv), np.nan, mfv)
    num = rolling_sum(mfv, period)
    vv = rolling_sum(v, period)
    with np.errstate(invalid="ignore", divide="ignore"):
        out = num / vv
    return IndicatorResult(name="cmf", params={}, values={"cmf": out})


@register(
    IndicatorMeta(
        name="chaikin_oscillator",
        label="Chaikin Oscillator",
        category="volume",
        params={"fast": 3, "slow": 10},
        inputs=("high", "low", "close", "volume"),
        outputs=("chaikin_oscillator",),
        warmup=lambda p: p["slow"] - 1,
        reference="Marc Chaikin: the MACD of the Accumulation/Distribution line.",
        formula="Chaikin Osc = EMA(ad_line, fast) - EMA(ad_line, slow)",
        notes="A MACD of the Accumulation/Distribution line; positive means accumulation pressure.",
    )
)
def chaikin_oscillator(
    data: dict[str, np.ndarray], fast: int = 3, slow: int = 10
) -> IndicatorResult:
    high, low, c = data["high"], data["low"], data["close"]
    v = _require_volume(data, "chaikin_oscillator").astype(float)
    if fast >= slow:
        raise ValueError(f"chaikin_oscillator: fast ({fast}) must be < slow ({slow})")
    with np.errstate(invalid="ignore", divide="ignore"):
        clv = ((c - low) - (high - c)) / (high - low)
    clv = np.where((high - low) == 0, 0.0, clv)
    mfv = clv * v
    mfv = np.where(np.isnan(high + low + c + v), np.nan, mfv)
    n = len(c)
    ad = np.zeros(n)
    for i in range(1, n):
        ad[i] = ad[i - 1] + (0.0 if np.isnan(mfv[i]) else mfv[i])
    osc = ema(ad, fast) - ema(ad, slow)
    return IndicatorResult(name="chaikin_oscillator", params={}, values={"chaikin_oscillator": osc})


@register(
    IndicatorMeta(
        name="volume_roc",
        label="Volume Rate of Change",
        category="volume",
        params={"period": 14},
        inputs=("close", "volume"),
        outputs=("volume_roc",),
        warmup=lambda p: p["period"],
        reference="Percentage change in volume against `period` bars earlier.",
        formula="VROC = 100*(volume[t] - volume[t-period]) / volume[t-period]",
        notes="A zero historical volume makes the ratio undefined (NaN), not zero.",
    )
)
def volume_roc(data: dict[str, np.ndarray], period: int = 14) -> IndicatorResult:
    v = _require_volume(data, "volume_roc").astype(float)
    n = len(v)
    out = np.full(n, np.nan)
    if n <= period:
        return IndicatorResult(
            name="volume_roc",
            params={},
            values={"volume_roc": out},
            insufficient_data=True,
            message=f"volume_roc({period}) needs at least {period + 1} bars, got {n}",
        )
    with np.errstate(invalid="ignore", divide="ignore"):
        out[period:] = 100.0 * (v[period:] - v[:-period]) / v[:-period]
    return IndicatorResult(name="volume_roc", params={}, values={"volume_roc": out})
