"""Volume / flow indicators, batch 2."""

from __future__ import annotations

import numpy as np

from megatool.ta.core import (
    IndicatorMeta,
    IndicatorResult,
    ema,
    register,
    rolling_mean,
)
from megatool.ta.volume import _require_volume


@register(
    IndicatorMeta(
        name="net_volume",
        label="Net Volume",
        category="volume",
        params={},
        inputs=("close", "volume"),
        outputs=("net_volume",),
        warmup=1,
        reference="Per-bar signed volume (up/down volume decomposition).",
        formula="net_volume[t] = +volume[t] if close rises; -volume[t] if it falls; "
        "0 if unchanged. Bar 0 has no previous close and is 0 by construction.",
        notes="Unlike OBV this is NOT cumulative — it shows each bar's directional "
        "volume so spikes are not averaged into the level.",
    )
)
def net_volume(data: dict[str, np.ndarray]) -> IndicatorResult:
    c = data["close"]
    v = _require_volume(data, "net_volume")
    n = len(c)
    out = np.zeros(n)
    for i in range(1, n):
        if c[i] > c[i - 1]:
            out[i] = v[i]
        elif c[i] < c[i - 1]:
            out[i] = -v[i]
        else:
            out[i] = 0.0
    return IndicatorResult(name="net_volume", params={}, values={"net_volume": out})


@register(
    IndicatorMeta(
        name="pvt",
        label="Price Volume Trend",
        category="volume",
        params={},
        inputs=("close", "volume"),
        outputs=("pvt",),
        warmup=1,
        reference="Classic Price Volume Trend (PVT), described in most volume-analysis texts.",
        formula="PVT[t] = PVT[t-1] + volume[t] * (close[t]-close[t-1]) / close[t-1]",
        notes="Like OBV but weights each bar's volume by the size of the move, so a "
        "large volume on a tiny move counts far less.",
    )
)
def pvt(data: dict[str, np.ndarray]) -> IndicatorResult:
    c = data["close"]
    v = _require_volume(data, "pvt")
    n = len(c)
    out = np.zeros(n)
    for i in range(1, n):
        prev = c[i - 1]
        out[i] = out[i - 1] if prev == 0 else out[i - 1] + v[i] * (c[i] - prev) / prev
    return IndicatorResult(name="pvt", params={}, values={"pvt": out})


@register(
    IndicatorMeta(
        name="volume_oscillator",
        label="Volume Oscillator",
        category="volume",
        params={"short": 14, "long": 28},
        inputs=("volume",),
        outputs=("volume_osc",),
        warmup=lambda p: p["long"] - 1,
        reference="Standard volume-oscillator construction (percentage difference of two "
        "volume EMAs).",
        formula="volume_osc = 100 * (EMA(volume, short) - EMA(volume, long)) / EMA(volume, long)",
        notes="Positive = shorter-term volume running above the longer baseline; it says "
        "nothing about price direction.",
    )
)
def volume_oscillator(data: dict[str, np.ndarray], short: int = 14, long: int = 28) -> IndicatorResult:
    v = _require_volume(data, "volume_oscillator")
    s = ema(v, short)
    lo = ema(v, long)
    with np.errstate(invalid="ignore", divide="ignore"):
        out = np.where(lo != 0, 100.0 * (s - lo) / lo, np.nan)
    return IndicatorResult(name="volume_oscillator", params={}, values={"volume_osc": out})


@register(
    IndicatorMeta(
        name="ease_of_movement",
        label="Ease of Movement",
        category="volume",
        params={"period": 14},
        inputs=("high", "low", "volume"),
        outputs=("emv",),
        warmup=lambda p: p["period"],
        reference="Richard Arms, 'Volume Adjusted Moving Averages' (1960s).",
        formula="distance = (high+low)/2 - (prev high+prev low)/2; "
        "box_ratio = volume / (high-low); emv = SMA(distance / box_ratio, period)",
        notes="High values mean price moved far on little volume (easy movement); "
        "zero-range or zero-volume bars are skipped as NaN, not forced to zero.",
    )
)
def ease_of_movement(data: dict[str, np.ndarray], period: int = 14) -> IndicatorResult:
    h, l = data["high"], data["low"]
    v = _require_volume(data, "ease_of_movement")
    n = len(h)
    mid = (h + l) / 2.0
    dist = np.full(n, np.nan)
    dist[1:] = mid[1:] - mid[:-1]
    rng = h - l
    with np.errstate(invalid="ignore", divide="ignore"):
        box = np.where(rng > 0, v / rng, np.nan)
        raw = np.where(box > 0, dist / box, np.nan)
    emv = rolling_mean(raw, period)
    return IndicatorResult(name="ease_of_movement", params={}, values={"emv": emv})


@register(
    IndicatorMeta(
        name="klinger",
        label="Klinger Volume Oscillator",
        category="volume",
        params={"short": 34, "long": 55, "signal": 13},
        inputs=("high", "low", "close", "volume"),
        outputs=("kvo", "signal"),
        warmup=lambda p: p["long"] - 1,
        output_warmup={
            "kvo": lambda p: p["long"] - 1,
            "signal": lambda p: p["long"] - 1 + p["signal"] - 1,
        },
        reference="Stephen Klinger, 'Volume Oscillator Confirms Price Movements', TASC 1997.",
        formula="trend[t] = sign of (high+low) change vs previous bar, holding on equal; "
        "cm[t] = cm[t-1] + dm if trend unchanged else dm[t-1] + dm[t], dm = high-low; "
        "vf[t] = volume * |2*(dm/cm - 1)| * trend * 100; "
        "KVO = EMA(vf, short) - EMA(vf, long); signal = EMA(KVO, signal)",
        notes="Trend is decided on (high+low), not close, per the original definition. "
        "Bar 0 has no comparison bar and seeds the cumulative measurement.",
    )
)
def klinger(
    data: dict[str, np.ndarray],
    short: int = 34,
    long: int = 55,
    signal: int = 13,
) -> IndicatorResult:
    h, l = data["high"], data["low"]
    v = _require_volume(data, "klinger")
    n = len(h)
    trend = np.ones(n)
    cm = np.zeros(n)
    vf = np.zeros(n)
    dm0 = h[0] - l[0] if n else 0.0
    cm[0] = dm0
    for i in range(1, n):
        dm = h[i] - l[i]
        hl = h[i] + l[i]
        hl_prev = h[i - 1] + l[i - 1]
        if hl > hl_prev:
            trend[i] = 1.0
        elif hl < hl_prev:
            trend[i] = -1.0
        else:
            trend[i] = trend[i - 1]
        if trend[i] == trend[i - 1]:
            cm[i] = cm[i - 1] + dm
        else:
            cm[i] = h[i - 1] - l[i - 1] + dm
        if cm[i] != 0:
            vf[i] = v[i] * abs(2.0 * (dm / cm[i] - 1.0)) * trend[i] * 100.0
    kvo = ema(vf, short) - ema(vf, long)
    signal_vals = ema(kvo, signal)
    return IndicatorResult(name="klinger", params={}, values={"kvo": kvo, "signal": signal_vals})
