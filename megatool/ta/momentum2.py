"""Momentum indicators, batch 2.

Same contract as the first batch: causal, formula-documented, exact warm-ups.
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
    rolling_sum,
)
from megatool.ta.momentum import rsi as _rsi_fn
from megatool.ta.trend2 import weighted_mean


def _roc(values: np.ndarray, period: int) -> np.ndarray:
    """Percent rate of change, first valid at index `period`."""
    n = len(values)
    out = np.full(n, np.nan)
    if period <= 0 or n <= period:
        return out
    base = values[:-period]
    with np.errstate(invalid="ignore", divide="ignore"):
        out[period:] = np.where(base != 0, (values[period:] / base - 1.0) * 100.0, np.nan)
    return out


@register(
    IndicatorMeta(
        name="awesome_oscillator",
        label="Awesome Oscillator",
        category="momentum",
        params={"fast": 5, "slow": 34},
        inputs=("high", "low"),
        outputs=("ao",),
        warmup=lambda p: p["slow"] - 1,
        reference="Bill Williams, New Trading Dimensions (1998).",
        formula="median = (high+low)/2; AO = SMA(median, fast) - SMA(median, slow)",
        notes="A median-price momentum difference; it is not normalised, so magnitude is "
        "comparable only within one symbol.",
    )
)
def awesome_oscillator(data: dict[str, np.ndarray], fast: int = 5, slow: int = 34) -> IndicatorResult:
    med = (data["high"] + data["low"]) / 2.0
    ao = rolling_mean(med, fast) - rolling_mean(med, slow)
    return IndicatorResult(name="awesome_oscillator", params={}, values={"ao": ao})


@register(
    IndicatorMeta(
        name="accelerator_oscillator",
        label="Accelerator Oscillator",
        category="momentum",
        params={"fast": 5, "slow": 34, "smooth": 5},
        inputs=("high", "low"),
        outputs=("ac",),
        warmup=lambda p: p["slow"] - 1 + p["smooth"] - 1,
        reference="Bill Williams, New Trading Dimensions (1998).",
        formula="AC = AO - SMA(AO, smooth), where AO = SMA(median, fast) - SMA(median, slow)",
        notes="Measures the acceleration of the Awesome Oscillator; sign change is the "
        "conventional signal.",
    )
)
def accelerator_oscillator(
    data: dict[str, np.ndarray], fast: int = 5, slow: int = 34, smooth: int = 5
) -> IndicatorResult:
    med = (data["high"] + data["low"]) / 2.0
    ao = rolling_mean(med, fast) - rolling_mean(med, slow)
    ac = ao - rolling_mean(ao, smooth)
    return IndicatorResult(name="accelerator_oscillator", params={}, values={"ac": ac})


@register(
    IndicatorMeta(
        name="dpo",
        label="Detrended Price Oscillator",
        category="momentum",
        params={"period": 21},
        inputs=("close",),
        outputs=("dpo",),
        warmup=lambda p: max(p["period"] - 1, p["period"] // 2 + 1),
        reference="Walt Bressert / 'Cycles' literature; popularised by Investor's Business Daily.",
        formula="DPO[t] = close[t - (period//2 + 1)] - SMA(close, period)[t]",
        notes="Removes the trend so cycle length is easier to read. The displaced close "
        "is a PAST price (causal) — this implementation never uses future bars, unlike "
        "textbook plots that recentre the line.",
    )
)
def dpo(data: dict[str, np.ndarray], period: int = 21) -> IndicatorResult:
    c = data["close"]
    k = period // 2 + 1
    dpo_vals = np.full(len(c), np.nan)
    sma = rolling_mean(c, period)
    if k <= period - 1:
        with np.errstate(invalid="ignore"):
            dpo_vals[k:] = c[:-k] - sma[k:]
    else:
        for t in range(k, len(c)):
            if not np.isnan(sma[t]):
                dpo_vals[t] = c[t - k] - sma[t]
    return IndicatorResult(name="dpo", params={}, values={"dpo": dpo_vals})


_KST_ROCS = (10, 15, 20, 30)
_KST_SMAS = (10, 10, 10, 15)


@register(
    IndicatorMeta(
        name="kst",
        label="Know Sure Thing",
        category="momentum",
        params={"signal": 9},
        inputs=("close",),
        outputs=("kst", "signal"),
        warmup=lambda p: max(r + s - 1 for r, s in zip(_KST_ROCS, _KST_SMAS)),
        output_warmup={
            "kst": lambda p: max(r + s - 1 for r, s in zip(_KST_ROCS, _KST_SMAS)),
            "signal": lambda p: max(r + s - 1 for r, s in zip(_KST_ROCS, _KST_SMAS)) + p["signal"] - 1,
        },
        reference="Martin Pring, 'Summed Rate of Change' — KST (1992).",
        formula="RCMA_i = SMA(ROC(close, n_i), m_i); KST = 1*RCMA1 + 2*RCMA2 + 3*RCMA3 + "
        "4*RCMA4 with (n,m) = (10,10),(15,10),(20,10),(30,15); signal = SMA(KST, 9)",
        notes="Pring's four ROC horizons, linearly weighted by horizon length.",
    )
)
def kst(data: dict[str, np.ndarray], signal: int = 9) -> IndicatorResult:
    c = data["close"]
    kst_vals = np.zeros(len(c))
    for i, (r, s) in enumerate(zip(_KST_ROCS, _KST_SMAS), start=1):
        # Weight each smoothed ROC by its horizon index (1..4), per Pring.
        kst_vals = kst_vals + i * rolling_mean(_roc(c, r), s)
    signal_vals = rolling_mean(kst_vals, signal)
    return IndicatorResult(name="kst", params={}, values={"kst": kst_vals, "signal": signal_vals})


@register(
    IndicatorMeta(
        name="ultimate_oscillator",
        label="Ultimate Oscillator",
        category="momentum",
        params={"short": 7, "medium": 14, "long": 28},
        inputs=("high", "low", "close"),
        outputs=("uo",),
        warmup=lambda p: p["long"],
        reference="Larry Williams, 'Ultimate Oscillator', TASC 1985.",
        formula="BP = close - min(low, prev close); TR = max(high, prev close) - "
        "min(low, prev close); avg_n = sum(BP,n)/sum(TR,n); "
        "UO = 100*(4*avg_short + 2*avg_medium + avg_long)/7",
        notes="A weighted blend of three horizons, deliberately smoothing the "
        "short-term oscillator's whipsaws.",
    )
)
def ultimate_oscillator(
    data: dict[str, np.ndarray], short: int = 7, medium: int = 14, long: int = 28
) -> IndicatorResult:
    h, l, c = data["high"], data["low"], data["close"]
    n = len(c)
    bp = np.full(n, np.nan)
    tr = np.full(n, np.nan)
    bp[1:] = c[1:] - np.minimum(l[1:], c[:-1])
    tr[1:] = np.maximum(h[1:], c[:-1]) - np.minimum(l[1:], c[:-1])

    def avg(period: int) -> np.ndarray:
        s_bp = rolling_sum(bp, period)
        s_tr = rolling_sum(tr, period)
        with np.errstate(invalid="ignore", divide="ignore"):
            return np.where(s_tr != 0, s_bp / s_tr, np.nan)

    uo = 100.0 * (4.0 * avg(short) + 2.0 * avg(medium) + avg(long)) / 7.0
    return IndicatorResult(name="ultimate_oscillator", params={}, values={"uo": uo})


@register(
    IndicatorMeta(
        name="connors_rsi",
        label="Connors RSI",
        category="momentum",
        params={"rsi_period": 3, "streak_period": 2, "rank_period": 100},
        inputs=("close",),
        outputs=("crsi",),
        warmup=lambda p: p["rank_period"],
        reference="Larry Connors & Cesar Alvarez, 'An Introduction to ConnorsRSI' (2012).",
        formula="CRSI = ( RSI(close, 3) + RSI(streak, 2) + PercentRank(ROC1, 100) ) / 3; "
        "streak counts consecutive up (+) / down (-) closes, resetting on a reversal; "
        "PercentRank = 100 * (# window values strictly below the current ROC1) / (rank_period - 1)",
        notes="A composite short-term mean-reversion oscillator. The PercentRank "
        "definition is stated here explicitly because implementations differ.",
    )
)
def connors_rsi(
    data: dict[str, np.ndarray], rsi_period: int = 3, streak_period: int = 2, rank_period: int = 100
) -> IndicatorResult:
    c = data["close"]
    n = len(c)
    streak = np.zeros(n)
    for i in range(1, n):
        if c[i] > c[i - 1]:
            streak[i] = streak[i - 1] + 1.0 if streak[i - 1] > 0 else 1.0
        elif c[i] < c[i - 1]:
            streak[i] = streak[i - 1] - 1.0 if streak[i - 1] < 0 else -1.0
        else:
            streak[i] = 0.0
    r1 = _rsi_fn({"close": c}, period=rsi_period).values["rsi"]
    r2 = _rsi_fn({"close": streak}, period=streak_period).values["rsi"]
    roc1 = _roc(c, 1)
    pr = np.full(n, np.nan)
    if rank_period >= 2:
        for t in range(rank_period, n):
            win = roc1[t - rank_period + 1 : t + 1]
            if np.any(np.isnan(win)):
                continue
            below = int((win < win[-1]).sum())
            pr[t] = 100.0 * below / (rank_period - 1)
    with np.errstate(invalid="ignore"):
        crsi = (r1 + r2 + pr) / 3.0
    return IndicatorResult(name="connors_rsi", params={}, values={"crsi": crsi})


@register(
    IndicatorMeta(
        name="coppock_curve",
        label="Coppock Curve",
        category="momentum",
        params={"long": 14, "short": 11, "wma_period": 10},
        inputs=("close",),
        outputs=("coppock",),
        warmup=lambda p: max(p["long"], p["short"]) + p["wma_period"] - 1,
        reference="Edwin Sedgwick Coppock, Barron's (1962); WMA smoothing added by "
        "later implementations.",
        formula="Coppock = WMA( ROC(close, long) + ROC(close, short), wma_period )",
        notes="Designed for monthly charts originally; on daily data expect frequent "
        "zero crossings.",
    )
)
def coppock_curve(
    data: dict[str, np.ndarray], long: int = 14, short: int = 11, wma_period: int = 10
) -> IndicatorResult:
    c = data["close"]
    combined = _roc(c, long) + _roc(c, short)
    out = weighted_mean(combined, wma_period)
    return IndicatorResult(name="coppock_curve", params={}, values={"coppock": out})


def _swma(values: np.ndarray) -> np.ndarray:
    """Symmetric-weighted 4-bar average (1,2,2,1)/6; first valid at index 3."""
    n = len(values)
    out = np.full(n, np.nan)
    if n < 4:
        return out
    out[3:] = (values[:-3] + 2 * values[1:-2] + 2 * values[2:-1] + values[3:]) / 6.0
    return out


@register(
    IndicatorMeta(
        name="rvi",
        label="Relative Vigor Index",
        category="momentum",
        params={"period": 10},
        inputs=("open", "high", "low", "close"),
        outputs=("rvi", "signal"),
        warmup=lambda p: p["period"] + 2,
        output_warmup={"rvi": lambda p: p["period"] + 2, "signal": lambda p: p["period"] + 5},
        reference="John Ehlers, 'The Relative Vigor Index', TASC 2002.",
        formula="num = SMA(SWMA(close-open), period); den = SMA(SWMA(high-low), period); "
        "RVI = num/den; signal = SWMA(RVI); SWMA = (x[t-3] + 2x[t-2] + 2x[t-1] + x[t])/6",
        notes="Values oscillate around zero; vigor is the closes-vs-opens move relative "
        "to the bar's range.",
    )
)
def rvi(data: dict[str, np.ndarray], period: int = 10) -> IndicatorResult:
    o, h, l, c = data["open"], data["high"], data["low"], data["close"]
    num = rolling_mean(_swma(c - o), period)
    den = rolling_mean(_swma(h - l), period)
    with np.errstate(invalid="ignore", divide="ignore"):
        rvi_vals = np.where(den != 0, num / den, np.nan)
    signal = _swma(rvi_vals)
    return IndicatorResult(name="rvi", params={}, values={"rvi": rvi_vals, "signal": signal})


@register(
    IndicatorMeta(
        name="smi",
        label="Stochastic Momentum Index",
        category="momentum",
        params={"period": 14, "smooth1": 3, "smooth2": 3, "signal": 3},
        inputs=("high", "low", "close"),
        outputs=("smi", "signal"),
        warmup=lambda p: p["period"] + p["smooth1"] + p["smooth2"] - 3,
        output_warmup={
            "smi": lambda p: p["period"] + p["smooth1"] + p["smooth2"] - 3,
            "signal": lambda p: p["period"] + p["smooth1"] + p["smooth2"] - 3 + p["signal"] - 1,
        },
        reference="William Blau, Momentum, Direction and Divergence (1993).",
        formula="mid = (highest(high,n)+lowest(low,n))/2; rel = close - mid; "
        "halfrange = (highest(high,n)-lowest(low,n))/2; "
        "SMI = 100 * EMA(EMA(rel, k1), k2) / EMA(EMA(halfrange, k1), k2); signal = EMA(SMI, s)",
        notes="A double-smoothed stochastic centred on zero: ±100 means the close sits "
        "at the window extreme, 0 at its middle.",
    )
)
def smi(
    data: dict[str, np.ndarray], period: int = 14, smooth1: int = 3, smooth2: int = 3, signal: int = 3
) -> IndicatorResult:
    h, l, c = data["high"], data["low"], data["close"]
    hi, lo = rolling_max(h, period), rolling_min(l, period)
    rel = c - (hi + lo) / 2.0
    half = (hi - lo) / 2.0
    num = ema(ema(rel, smooth1), smooth2)
    den = ema(ema(half, smooth1), smooth2)
    with np.errstate(invalid="ignore", divide="ignore"):
        smi_vals = np.where(den != 0, 100.0 * num / den, np.nan)
    signal_vals = ema(smi_vals, signal)
    return IndicatorResult(name="smi", params={}, values={"smi": smi_vals, "signal": signal_vals})


@register(
    IndicatorMeta(
        name="fisher_transform",
        label="Fisher Transform",
        category="momentum",
        params={"period": 9},
        inputs=("high", "low"),
        outputs=("fisher", "trigger"),
        warmup=lambda p: p["period"] - 1,
        output_warmup={"fisher": lambda p: p["period"] - 1, "trigger": lambda p: p["period"]},
        reference="John Ehlers, 'Using the Fisher Transform', TASC 2002.",
        formula="x = 2*((hl2 - min(low,n))/(max(high,n)-min(low,n)) - 0.5), clipped to "
        "±0.999 where hl2 = (high+low)/2; v[t] = 0.33*x + 0.67*v[t-1]; "
        "fisher[t] = 0.5*ln((1+v)/(1-v)) + 0.5*fisher[t-1]; trigger = fisher[t-1]",
        notes="Ehlers' smoothing constants (0.33/0.67) and the 0.5 recursion are the "
        "author's published values.",
    )
)
def fisher_transform(data: dict[str, np.ndarray], period: int = 9) -> IndicatorResult:
    h, l = data["high"], data["low"]
    n = len(h)
    hi, lo = rolling_max(h, period), rolling_min(l, period)
    hl2 = (h + l) / 2.0
    fisher = np.full(n, np.nan)
    value = 0.0
    prev_fisher = 0.0
    for t in range(period - 1, n):
        rng = hi[t] - lo[t]
        if np.isnan(rng) or rng == 0 or np.isnan(hl2[t]):
            fisher[t] = fisher[t - 1] if t > 0 else np.nan
            continue
        x = 2.0 * ((hl2[t] - lo[t]) / rng - 0.5)
        x = float(np.clip(x, -0.999, 0.999))
        value = 0.33 * x + 0.67 * value
        value = float(np.clip(value, -0.999, 0.999))
        fisher[t] = 0.5 * np.log((1.0 + value) / (1.0 - value)) + 0.5 * prev_fisher
        prev_fisher = fisher[t]
    trigger = np.full(n, np.nan)
    if n > 1:
        trigger[1:] = fisher[:-1]
    return IndicatorResult(name="fisher_transform", params={}, values={"fisher": fisher, "trigger": trigger})


@register(
    IndicatorMeta(
        name="balance_of_power",
        label="Balance of Power",
        category="momentum",
        params={},
        inputs=("open", "high", "low", "close"),
        outputs=("bop",),
        warmup=0,
        reference="Igor Livshin, 'Balance of Power' (2001).",
        formula="BOP = (close - open) / (high - low)",
        notes="Range-relative buying pressure per bar in [-1, 1]; a zero-range bar "
        "produces NaN rather than a fabricated value.",
    )
)
def balance_of_power(data: dict[str, np.ndarray]) -> IndicatorResult:
    o, h, l, c = data["open"], data["high"], data["low"], data["close"]
    rng = h - l
    with np.errstate(invalid="ignore", divide="ignore"):
        out = np.where(rng > 0, (c - o) / rng, np.nan)
    return IndicatorResult(name="balance_of_power", params={}, values={"bop": out})


@register(
    IndicatorMeta(
        name="force_index",
        label="Elder Force Index",
        category="momentum",
        params={"period": 13},
        inputs=("close", "volume"),
        outputs=("efi", "efi_ema"),
        warmup=lambda p: p["period"],
        output_warmup={"efi": 1, "efi_ema": lambda p: p["period"]},
        reference="Alexander Elder, Trading for a Living (1993).",
        formula="EFI[t] = (close[t]-close[t-1]) * volume[t]; efi_ema = EMA(EFI, period)",
        notes="Raw EFI is noisy bar-by-bar; the EMA line is what Elder plots. Both are "
        "published so nothing is hidden.",
    )
)
def force_index(data: dict[str, np.ndarray], period: int = 13) -> IndicatorResult:
    c = data["close"]
    v = data["volume"]
    n = len(c)
    raw = np.full(n, np.nan)
    raw[1:] = (c[1:] - c[:-1]) * v[1:]
    smoothed = ema(raw, period)
    return IndicatorResult(name="force_index", params={}, values={"efi": raw, "efi_ema": smoothed})


@register(
    IndicatorMeta(
        name="price_oscillator",
        label="Price Oscillator",
        category="momentum",
        params={"fast": 10, "slow": 21},
        inputs=("close",),
        outputs=("price_osc",),
        warmup=lambda p: p["slow"] - 1,
        reference="Classic percentage price oscillator with SIMPLE moving averages.",
        formula="price_osc = 100 * (SMA(close, fast) - SMA(close, slow)) / SMA(close, slow)",
        notes="Distinct from `ppo`, which uses EMAs; the backend keeps both so the "
        "difference is visible instead of hidden behind one name.",
    )
)
def price_oscillator(data: dict[str, np.ndarray], fast: int = 10, slow: int = 21) -> IndicatorResult:
    c = data["close"]
    f = rolling_mean(c, fast)
    s = rolling_mean(c, slow)
    with np.errstate(invalid="ignore", divide="ignore"):
        out = np.where(s != 0, 100.0 * (f - s) / s, np.nan)
    return IndicatorResult(name="price_oscillator", params={}, values={"price_osc": out})
