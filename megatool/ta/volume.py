"""Volume indicators."""

from __future__ import annotations

import numpy as np

from megatool.ta.core import (
    IndicatorMeta,
    IndicatorResult,
    register,
    rolling_mean,
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
        notes="Often called a 'volume-weighted RSI'; ranges 0-100.",
    )
)
def mfi(data: dict[str, np.ndarray], period: int = 14) -> IndicatorResult:
    tp = (data["high"] + data["low"] + data["close"]) / 3.0
    v = _require_volume(data, "mfi")
    mf = tp * v
    n = len(tp)
    pos = np.zeros(n)
    neg = np.zeros(n)
    for i in range(1, n):
        if tp[i] > tp[i - 1]:
            pos[i] = mf[i]
        elif tp[i] < tp[i - 1]:
            neg[i] = mf[i]

    out = np.full(n, np.nan)
    for i in range(period, n):
        p = pos[i - period + 1 : i + 1].sum()
        ng = neg[i - period + 1 : i + 1].sum()
        if ng == 0:
            out[i] = 100.0
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
    )
)
def volume_sma(data: dict[str, np.ndarray], period: int = 20) -> IndicatorResult:
    v = _require_volume(data, "volume_sma").astype(float)
    return IndicatorResult(name="volume_sma", params={}, values={"volume_sma": rolling_mean(v, period)})


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
