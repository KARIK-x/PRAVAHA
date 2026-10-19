"""Miscellaneous reference calculations ("other").

These are the small, well-defined price transformations and level calculations
that the spec lists alongside the indicator families (typical/median/weighted
price, rolling standard deviation, z-score, classic floor pivot points). They are
kept separate from the indicator families because they are primitives and level
tools rather than oscillators, trend or volume measures.
"""

from __future__ import annotations

import numpy as np

from megatool.ta.core import (
    IndicatorMeta,
    IndicatorResult,
    register,
    rolling_mean,
    rolling_std,
    shift,
)


@register(
    IndicatorMeta(
        name="typical_price",
        label="Typical Price",
        category="other",
        params={},
        inputs=("high", "low", "close"),
        outputs=("typical_price",),
        warmup=0,
        formula="TP[t] = (high + low + close) / 3",
        reference="Standard bar representative price (typical price).",
        notes="A bar's representative price. It is an arithmetic construction, not a traded price.",
    )
)
def typical_price(data: dict[str, np.ndarray]) -> IndicatorResult:
    tp = (data["high"] + data["low"] + data["close"]) / 3.0
    return IndicatorResult(name="typical_price", params={}, values={"typical_price": tp})


@register(
    IndicatorMeta(
        name="median_price",
        label="Median Price",
        category="other",
        params={},
        inputs=("high", "low"),
        outputs=("median_price",),
        warmup=0,
        formula="MP[t] = (high + low) / 2",
        reference="Standard median (midpoint) price of a bar.",
        notes="A bar's midpoint price; an arithmetic construction, not a traded price.",
    )
)
def median_price(data: dict[str, np.ndarray]) -> IndicatorResult:
    mp = (data["high"] + data["low"]) / 2.0
    return IndicatorResult(name="median_price", params={}, values={"median_price": mp})


@register(
    IndicatorMeta(
        name="weighted_close",
        label="Weighted Close",
        category="other",
        params={},
        inputs=("high", "low", "close"),
        outputs=("weighted_close",),
        warmup=0,
        formula="WC[t] = (high + low + 2*close) / 4",
        reference="Standard weighted-close price (close weighted double).",
        notes="Weights the close double because it is the last observation of the bar.",
    )
)
def weighted_close(data: dict[str, np.ndarray]) -> IndicatorResult:
    wc = (data["high"] + data["low"] + 2.0 * data["close"]) / 4.0
    return IndicatorResult(name="weighted_close", params={}, values={"weighted_close": wc})


@register(
    IndicatorMeta(
        name="standard_deviation",
        label="Rolling Standard Deviation",
        category="other",
        params={"period": 20, "ddof": 1},
        inputs=("close",),
        outputs=("std",),
        warmup=lambda p: p["period"] - 1,
        formula="std over the trailing `period` closes (sample ddof by default)",
        reference="Rolling standard deviation (sample or population, per ddof).",
        notes="Describes dispersion within the window. ddof=1 is the sample "
        "estimator; ddof=0 the population one.",
    )
)
def standard_deviation(
    data: dict[str, np.ndarray], period: int = 20, ddof: int = 1
) -> IndicatorResult:
    out = rolling_std(data["close"], period, ddof=ddof)
    return IndicatorResult(name="standard_deviation", params={}, values={"std": out})


@register(
    IndicatorMeta(
        name="zscore",
        label="Z-Score",
        category="other",
        params={"period": 20, "ddof": 1},
        inputs=("close",),
        outputs=("zscore",),
        warmup=lambda p: p["period"] - 1,
        formula="z[t] = (close[t] - mean(close, period)) / std(close, period)",
        reference="Standard z-score (value minus rolling mean over std).",
        notes="Unit-free distance from the window mean. A flat window gives a "
        "zero denominator, so the value stays NaN rather than being forced to 0.",
    )
)
def zscore(data: dict[str, np.ndarray], period: int = 20, ddof: int = 1) -> IndicatorResult:
    c = data["close"]
    mean = rolling_mean(c, period)
    std = rolling_std(c, period, ddof=ddof)
    with np.errstate(invalid="ignore", divide="ignore"):
        out = (c - mean) / std
    out = np.where(std == 0, np.nan, out)
    return IndicatorResult(name="zscore", params={}, values={"zscore": out})


@register(
    IndicatorMeta(
        name="pivot_points",
        label="Classic Floor Pivot Points",
        category="other",
        params={},
        inputs=("high", "low", "close"),
        outputs=("pivot", "r1", "r2", "r3", "s1", "s2", "s3"),
        warmup=1,
        reference="Traditional trading-floor pivot calculation.",
        formula="from the PREVIOUS bar's H/L/C: P = (H+L+C)/3; "
        "R1 = 2P - L, S1 = 2P - H, R2 = P + (H-L), S2 = P - (H-L), "
        "R3 = H + 2(P-L), S3 = L - 2(H-P)",
        notes="Levels are computed from the *previous* bar, so the value shown at "
        "bar t uses only information available at t-1. Pivot levels are arithmetic "
        "reference levels, not predictions.",
    )
)
def pivot_points(data: dict[str, np.ndarray]) -> IndicatorResult:
    h = shift(data["high"], 1)
    lw = shift(data["low"], 1)
    c = shift(data["close"], 1)
    pivot = (h + lw + c) / 3.0
    rng = h - lw
    values = {
        "pivot": pivot,
        "r1": 2.0 * pivot - lw,
        "s1": 2.0 * pivot - h,
        "r2": pivot + rng,
        "s2": pivot - rng,
        "r3": h + 2.0 * (pivot - lw),
        "s3": lw - 2.0 * (h - pivot),
    }
    return IndicatorResult(name="pivot_points", params={}, values=values)
