"""Volatility and range indicators, batch 2."""

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
    rolling_sum,
    true_range,
)
from megatool.ta.trend2 import regression_triplet


@register(
    IndicatorMeta(
        name="mass_index",
        label="Mass Index",
        category="volatility",
        params={"period": 9, "sum_period": 25},
        inputs=("high", "low"),
        outputs=("mass",),
        warmup=lambda p: 2 * (p["period"] - 1) + p["sum_period"] - 1,
        reference="Donald Dorsey, 'The Mass Index', TASC 1992.",
        formula="ratio = EMA(high-low, period) / EMA(EMA(high-low, period), period); "
        "mass = sum(ratio, sum_period)",
        notes="Watches range expansion/contraction ('bulge') rather than direction.",
    )
)
def mass_index(data: dict[str, np.ndarray], period: int = 9, sum_period: int = 25) -> IndicatorResult:
    rng = data["high"] - data["low"]
    e1 = ema(rng, period)
    e2 = ema(e1, period)
    with np.errstate(invalid="ignore", divide="ignore"):
        ratio = np.where(e2 != 0, e1 / e2, np.nan)
    return IndicatorResult(name="mass_index", params={}, values={"mass": rolling_sum(ratio, sum_period)})


@register(
    IndicatorMeta(
        name="standard_error",
        label="Standard Error (of regression)",
        category="volatility",
        params={"period": 14},
        inputs=("close",),
        outputs=("se",),
        warmup=lambda p: p["period"] - 1,
        reference="Standard OLS residual standard error.",
        formula="se[t] = sqrt( sum((y - y_hat)^2) / (period - 2) ) over the rolling fit "
        "of close on x = 0..period-1",
        notes="Requires period >= 3 for a residual degree of freedom; smaller periods "
        "produce NaN rather than a fabricated number.",
    )
)
def standard_error(data: dict[str, np.ndarray], period: int = 14) -> IndicatorResult:
    _, _, se = regression_triplet(data["close"], period)
    return IndicatorResult(name="standard_error", params={}, values={"se": se})


@register(
    IndicatorMeta(
        name="standard_error_bands",
        label="Standard Error Bands",
        category="volatility",
        params={"period": 14, "mult": 2.0},
        inputs=("close",),
        outputs=("upper", "middle", "lower"),
        warmup=lambda p: p["period"] - 1,
        reference="Jon Anderson, 'Standard Error Bands', TASC 1996.",
        formula="middle = linear-regression endpoint over the window; "
        "upper = middle + mult*se; lower = middle - mult*se",
        notes="Bands widen with the regression's residual error, not with the raw price "
        "range, so they differ deliberately from Bollinger bands.",
    )
)
def standard_error_bands(data: dict[str, np.ndarray], period: int = 14, mult: float = 2.0) -> IndicatorResult:
    end, _, se = regression_triplet(data["close"], period)
    return IndicatorResult(
        name="standard_error_bands",
        params={},
        values={"upper": end + mult * se, "middle": end, "lower": end - mult * se},
    )


@register(
    IndicatorMeta(
        name="choppiness",
        label="Choppiness Index",
        category="volatility",
        params={"period": 14},
        inputs=("high", "low", "close"),
        outputs=("chop",),
        warmup=lambda p: p["period"],
        reference="E. W. Dreiss, 'The Choppiness Index', TASC 1993.",
        formula="CHOP = 100 * log10( sum(TR, period) / (highest(high, period) - "
        "lowest(low, period)) ) / log10(period)",
        notes="High values (near 100) mean range-bound, low values trending; it says "
        "nothing about direction.",
    )
)
def choppiness(data: dict[str, np.ndarray], period: int = 14) -> IndicatorResult:
    h, l, c = data["high"], data["low"], data["close"]
    atr_sum = rolling_sum(true_range(h, l, c), period)
    span = rolling_max(h, period) - rolling_min(l, period)
    with np.errstate(invalid="ignore", divide="ignore"):
        ratio = np.where(span > 0, atr_sum / span, np.nan)
    out = 100.0 * np.log10(ratio) / np.log10(period)
    return IndicatorResult(name="choppiness", params={}, values={"chop": out})


@register(
    IndicatorMeta(
        name="garman_klass",
        label="Garman-Klass Volatility",
        category="volatility",
        params={"period": 20, "annualize": 252},
        inputs=("high", "low", "open", "close"),
        outputs=("gk_vol",),
        warmup=lambda p: p["period"] - 1,
        reference="Garman & Klass, 'On the Estimation of Security Price Volatilities "
        "from Historical Data', Journal of Business (1980).",
        formula="v[t] = 0.5*ln(H/L)^2 - (2*ln2 - 1)*ln(C/O)^2; gk_vol = "
        "100*sqrt( mean(v, period) * annualize )",
        notes="Uses the full OHLC bar and is more efficient than close-to-close "
        "volatility when gaps are rare; reported in percent per year.",
    )
)
def garman_klass(
    data: dict[str, np.ndarray], period: int = 20, annualize: int = 252
) -> IndicatorResult:
    h, l, o, c = data["high"], data["low"], data["open"], data["close"]
    with np.errstate(invalid="ignore", divide="ignore"):
        hl = np.where((h > 0) & (l > 0), np.log(h / l), np.nan)
        co = np.where((c > 0) & (o > 0), np.log(c / o), np.nan)
        v = 0.5 * hl**2 - (2.0 * np.log(2.0) - 1.0) * co**2
    mean_v = rolling_mean(v, period)
    out = 100.0 * np.sqrt(np.maximum(mean_v, 0.0) * annualize)
    return IndicatorResult(name="garman_klass", params={}, values={"gk_vol": out})


@register(
    IndicatorMeta(
        name="volatility_zero_trend",
        label="Volatility (Zero Trend)",
        category="volatility",
        params={"period": 20},
        inputs=("close",),
        outputs=("vzt",),
        warmup=lambda p: p["period"],
        reference="'Zero-trend' volatility: mean absolute close-to-close change without "
        "assuming any drift.",
        formula="VZT = 100 * mean(|close[t-k+1] - close[t-k]|, k=1..period) / "
        "mean(close, period)",
        notes="Reports the average absolute bar movement as a percent of the average "
        "price over the same window.",
    )
)
def volatility_zero_trend(data: dict[str, np.ndarray], period: int = 20) -> IndicatorResult:
    c = data["close"]
    n = len(c)
    abs_change = np.full(n, np.nan)
    abs_change[1:] = np.abs(c[1:] - c[:-1])
    num = rolling_mean(abs_change, period)
    den = rolling_mean(c, period)
    with np.errstate(invalid="ignore", divide="ignore"):
        out = np.where(den != 0, 100.0 * num / den, np.nan)
    return IndicatorResult(name="volatility_zero_trend", params={}, values={"vzt": out})
