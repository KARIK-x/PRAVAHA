"""Independent naive re-implementations used by test_indicators3.py.

Kept in a non-collected module (name does not match test_*.py) so the
indicator verification scanner (scripts/generate_indicator_info.py) does not
mistake them for numeric reference evidence.
"""

from __future__ import annotations

import math

import numpy as np


def wilder_smooth_naive(x, period):
    n = len(x)
    out = np.full(n, np.nan)
    finite = [i for i in range(n) if not (isinstance(x[i], float) and math.isnan(x[i]))]
    if len(finite) < period:
        return out
    seed_i = finite[period - 1]
    out[seed_i] = float(np.mean([x[finite[k]] for k in range(period)]))
    for j in range(seed_i + 1, n):
        if math.isnan(x[j]):
            out[j] = out[j - 1]
        else:
            out[j] = (out[j - 1] * (period - 1) + x[j]) / period
    return out


def naive_atr(data, period):
    h = data["high"]; l = data["low"]; c = data["close"]
    n = len(c)
    tr = np.full(n, np.nan)
    for i in range(1, n):
        tr[i] = max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1]))
    return wilder_smooth_naive(tr, period)


def naive_hma(data, period):
    c = data["close"]
    n = len(c)
    def wma(x, p):
        out = np.full(n, np.nan)
        for i in range(p - 1, n):
            w = np.arange(1, p + 1, dtype=float)
            out[i] = np.dot(x[i - p + 1:i + 1], w) / w.sum()
        return out
    half = max(1, period // 2)
    sqrt_p = max(1, round(math.sqrt(period)))
    w1 = wma(c, half)
    w2 = wma(c, period)
    raw = 2 * w1 - w2
    return wma(raw, sqrt_p)


def naive_adx(data, period):
    h = data["high"]; l = data["low"]; c = data["close"]
    n = len(c)
    tr = np.full(n, np.nan)
    pdm = np.zeros(n); mdm = np.zeros(n)
    for i in range(1, n):
        tr[i] = max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1]))
        up = h[i] - h[i - 1]; down = l[i - 1] - l[i]
        pdm[i] = up if (up > down and up > 0) else 0.0
        mdm[i] = down if (down > up and down > 0) else 0.0
    atr = wilder_smooth_naive(tr, period)
    sp = wilder_smooth_naive(pdm, period)
    sm = wilder_smooth_naive(mdm, period)
    pdi = 100 * np.where(atr > 0, sp / atr, 0.0)
    mdi = 100 * np.where(atr > 0, sm / atr, 0.0)
    dx = np.where((pdi + mdi) > 0, 100 * abs(pdi - mdi) / (pdi + mdi), 0.0)
    adx = wilder_smooth_naive(dx, period)
    return adx, pdi, mdi


def naive_supertrend(data, period, mult):
    h = data["high"]; l = data["low"]; c = data["close"]
    n = len(c)
    tr = np.full(n, np.nan)
    for i in range(1, n):
        tr[i] = max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1]))
    atr = wilder_smooth_naive(tr, period)
    hl2 = (h + l) / 2
    ub = hl2 + mult * atr
    lb = hl2 - mult * atr
    st = np.full(n, np.nan); d = np.full(n, np.nan)
    si = next((i for i in range(n) if not math.isnan(atr[i])), None)
    if si is None:
        return st, d
    st[si] = lb[si]; d[si] = 1.0
    for i in range(si + 1, n):
        if c[i - 1] <= st[i - 1]:
            st[i] = min(ub[i], st[i - 1]) if not math.isnan(st[i - 1]) else ub[i]
            d[i] = -1.0
            if c[i] > st[i]:
                st[i] = lb[i]; d[i] = 1.0
        else:
            st[i] = max(lb[i], st[i - 1]) if not math.isnan(st[i - 1]) else lb[i]
            d[i] = 1.0
            if c[i] < st[i]:
                st[i] = ub[i]; d[i] = -1.0
    return st, d


def naive_trix(data, period, signal):
    c = data["close"]; n = len(c)
    def ema(x, p):
        out = np.full(n, np.nan); a = 2.0 / (p + 1)
        out[p - 1] = np.mean(x[:p])
        for i in range(p, n):
            out[i] = a * x[i] + (1 - a) * out[i - 1]
        return out
    e1 = ema(c, period); e2 = ema(e1, period); e3 = ema(e2, period)
    trix = np.full(n, np.nan)
    for i in range(period * 3 - 1, n):
        if e3[i - 1] != 0 and not math.isnan(e3[i - 1]):
            trix[i] = 100.0 * (e3[i] - e3[i - 1]) / e3[i - 1]
    sig = np.full(n, np.nan)
    for i in range(period * 3 - 1 + signal - 1, n):
        sig[i] = np.mean(trix[i - signal + 1:i + 1])
    return trix, sig


def naive_aroon(data, period):
    h = data["high"]; l = data["low"]; n = len(h)
    up = np.full(n, np.nan); down = np.full(n, np.nan)
    for i in range(period, n):
        w_h = h[i - period:i + 1]; w_l = l[i - period:i + 1]
        hi_idx = max(range(len(w_h)), key=lambda k: (w_h[k], k))
        lo_idx = max(range(len(w_l)), key=lambda k: (-w_l[k], k))
        up[i] = 100.0 * (period - (period - hi_idx)) / period
        down[i] = 100.0 * (period - (period - lo_idx)) / period
    return up, down