"""Reference-value tests for the batch-2 indicators.

Each test re-computes the published formula literally (loops and plain numpy,
no engine primitives) and compares it against the engine output on the shared
synthetic fixture. Causality, warm-up exactness and short-series safety for the
same indicators are already enforced generically by test_indicators.py.
"""

from __future__ import annotations

import numpy as np
import pytest

from megatool import ta


def _naive_ema(x: np.ndarray, n: int) -> np.ndarray:
    """SMA-seeded EMA written independently of the engine.

    Skips leading NaNs exactly like the engine does (the seed is the first
    window of `n` consecutive finite values), so chained EMAs are comparable.
    """
    out = np.full(len(x), np.nan)
    start = None
    run = 0
    for i, val in enumerate(x):
        run = 0 if np.isnan(val) else run + 1
        if run >= n:
            start = i - n + 1
            break
    if start is None:
        return out
    seed_idx = start + n - 1
    out[seed_idx] = x[start : seed_idx + 1].mean()
    a = 2.0 / (n + 1)
    for i in range(seed_idx + 1, len(x)):
        out[i] = out[i - 1] + a * (x[i] - out[i - 1])
    return out


def _naive_rsi(c: np.ndarray, n: int) -> np.ndarray:
    out = np.full(len(c), np.nan)
    if len(c) <= n:
        return out
    gains = np.zeros(len(c) - 1)
    losses = np.zeros(len(c) - 1)
    for i in range(1, len(c)):
        ch = c[i] - c[i - 1]
        gains[i - 1] = ch if ch > 0 else 0.0
        losses[i - 1] = -ch if ch < 0 else 0.0
    ag, al = gains[:n].mean(), losses[:n].mean()
    for i in range(n, len(c)):
        if i > n:
            ag = (ag * (n - 1) + gains[i - 1]) / n
            al = (al * (n - 1) + losses[i - 1]) / n
        if ag == 0 and al == 0:
            out[i] = np.nan
        elif al == 0:
            out[i] = 100.0
        else:
            out[i] = 100.0 - 100.0 / (1.0 + ag / al)
    return out


def _window(fn, x: np.ndarray, n: int, seed: float | None = None) -> np.ndarray:
    """Generic per-window loop helper: fn(window, prev) -> value."""
    out = np.full(len(x), np.nan)
    prev = seed
    for i in range(n - 1, len(x)):
        w = x[i - n + 1 : i + 1]
        if np.any(np.isnan(w)):
            continue
        val = fn(w, prev)
        out[i] = val
        prev = val
    return out


# ------------------------------------------------------------------- trend 2
def test_alma_matches_literal_formula(ohlcv):
    c, period, offset, sigma = ohlcv["close"], 9, 0.85, 6.0
    i = np.arange(period, dtype=float)
    m = offset * (period - 1)
    s = period / sigma
    w = np.exp(-((i - m) ** 2) / (2 * s * s))
    ref = _window(lambda win, _: float(np.dot(win, w) / w.sum()), c, period)
    got = ta.compute("alma", {"close": c}, period=period, offset=offset, sigma=sigma).values["alma"]
    np.testing.assert_allclose(got, ref, rtol=1e-9, atol=1e-9, equal_nan=True)


def test_t3_matches_literal_chained_ema(ohlcv):
    c, p, v = ohlcv["close"], 5, 0.7
    e = [c]
    for _ in range(6):
        e.append(_naive_ema(e[-1], p))
    c1, c2 = -v**3, 3 * v**2 + 3 * v**3
    c3, c4 = -6 * v**2 - 3 * v - 3 * v**3, 1 + 3 * v + v**3 + 3 * v**2
    ref = c1 * e[6] + c2 * e[5] + c3 * e[4] + c4 * e[3]
    got = ta.compute("t3", {"close": c}, period=p, volume_factor=v).values["t3"]
    np.testing.assert_allclose(got, ref, rtol=1e-9, atol=1e-9, equal_nan=True)


def test_zlema_matches_literal(ohlcv):
    c, p = ohlcv["close"], 20
    lag = (p - 1) // 2
    zl = 2.0 * c - np.concatenate((np.full(lag, np.nan), c[:-lag]))
    ref = _naive_ema(zl, p)
    got = ta.compute("zlema", {"close": c}, period=p).values["zlema"]
    np.testing.assert_allclose(got, ref, rtol=1e-9, atol=1e-9, equal_nan=True)


def test_vidya_matches_literal(ohlcv):
    c, p, sp = ohlcv["close"], 14, 2
    k = 2.0 / (sp + 1)
    ref = np.full(len(c), np.nan)
    for t in range(p, len(c)):
        win = c[t - p : t + 1]
        ch = np.diff(win)
        su, sd = ch[ch > 0].sum(), (-ch[ch < 0]).sum()
        cmo = 0.0 if su + sd == 0 else 100.0 * (su - sd) / (su + sd)
        prev = ref[t - 1] if not np.isnan(ref[t - 1]) else c[t]
        ref[t] = k * abs(cmo) / 100 * c[t] + (1 - k * abs(cmo) / 100) * prev
    got = ta.compute("vidya", {"close": c}, period=p, short_period=sp).values["vidya"]
    np.testing.assert_allclose(got, ref, rtol=1e-9, atol=1e-9, equal_nan=True)


def test_smma_matches_literal_wilder(ohlcv):
    c, p = ohlcv["close"], 20
    ref = np.full(len(c), np.nan)
    ref[p - 1] = c[:p].mean()
    for i in range(p, len(c)):
        ref[i] = ref[i - 1] + (c[i] - ref[i - 1]) / p
    got = ta.compute("smma", {"close": c}, period=p).values["smma"]
    np.testing.assert_allclose(got, ref, rtol=1e-9, atol=1e-9, equal_nan=True)


@pytest.mark.parametrize("name", ["lsma", "linreg_slope", "standard_error"])
def test_regression_family_matches_numpy_polyfit(name, ohlcv):
    c, p = ohlcv["close"], 14
    ref = np.full(len(c), np.nan)
    for t in range(p - 1, len(c)):
        x = np.arange(p, dtype=float)
        y = c[t - p + 1 : t + 1]
        b, a = np.polyfit(x, y, 1)
        resid = y - (a + b * x)
        if name == "lsma":
            ref[t] = a + b * (p - 1)
        elif name == "linreg_slope":
            ref[t] = b
        else:
            ref[t] = np.sqrt((resid**2).sum() / (p - 2))
    got = ta.compute(name, {"close": c}, period=p).values[list(ta.compute(name, {"close": c}, period=p).values)[0]]
    np.testing.assert_allclose(got, ref, rtol=1e-8, atol=1e-8, equal_nan=True)


def test_mcginley_dynamic_matches_literal(ohlcv):
    c, p = ohlcv["close"], 14
    ref = np.full(len(c), np.nan)
    ref[p - 1] = c[:p].mean()
    for t in range(p, len(c)):
        ref[t] = ref[t - 1] + (c[t] - ref[t - 1]) / (p * (c[t] / ref[t - 1]) ** 4)
    got = ta.compute("mcginley_dynamic", {"close": c}, period=p).values["md"]
    np.testing.assert_allclose(got, ref, rtol=1e-9, atol=1e-9, equal_nan=True)


def test_alligator_matches_literal_smma_and_shift(ohlcv):
    h, low = ohlcv["high"], ohlcv["low"]
    med = (h + low) / 2.0

    def smma(x, p):
        out = np.full(len(x), np.nan)
        out[p - 1] = x[:p].mean()
        for i in range(p, len(x)):
            out[i] = out[i - 1] + (x[i] - out[i - 1]) / p
        return out

    def lag(x, k):
        out = np.full(len(x), np.nan)
        out[k:] = x[:-k]
        return out

    got = ta.compute("alligator", {"high": h, "low": low}).values
    np.testing.assert_allclose(got["jaw"], lag(smma(med, 13), 8), rtol=1e-9, atol=1e-9, equal_nan=True)
    np.testing.assert_allclose(got["teeth"], lag(smma(med, 8), 5), rtol=1e-9, atol=1e-9, equal_nan=True)
    np.testing.assert_allclose(got["lips"], lag(smma(med, 5), 3), rtol=1e-9, atol=1e-9, equal_nan=True)


def test_gmma_is_twelve_plain_smas(ohlcv):
    c = ohlcv["close"]
    got = ta.compute("gmma", {"close": c}).values
    assert len(got) == 12
    for p in (3, 5, 8, 10, 12, 15, 30, 35, 40, 45, 50, 60):
        ref = np.array([np.nan] * (p - 1) + [float(c[i - p + 1 : i + 1].mean()) for i in range(p - 1, len(c))])
        np.testing.assert_allclose(got[f"sma_{p}"], ref, rtol=1e-9, atol=1e-9, equal_nan=True)


def test_envelopes_matches_literal(ohlcv):
    c, p, pc = ohlcv["close"], 20, 1.0
    mid = np.array([np.nan] * (p - 1) + [float(c[i - p + 1 : i + 1].mean()) for i in range(p - 1, len(c))])
    got = ta.compute("envelopes", {"close": c}, period=p, percent=pc).values
    np.testing.assert_allclose(got["middle"], mid, rtol=1e-9, atol=1e-9, equal_nan=True)
    np.testing.assert_allclose(got["upper"], mid * 1.01, rtol=1e-9, atol=1e-9, equal_nan=True)
    np.testing.assert_allclose(got["lower"], mid * 0.99, rtol=1e-9, atol=1e-9, equal_nan=True)


# ---------------------------------------------------------------- momentum 2
def test_awesome_oscillator_matches_literal(ohlcv):
    med = (ohlcv["high"] + ohlcv["low"]) / 2.0

    def sma(x, n):
        return np.array([np.nan] * (n - 1) + [float(x[i - n + 1 : i + 1].mean()) for i in range(n - 1, len(x))])

    ref = sma(med, 5) - sma(med, 34)
    got = ta.compute("awesome_oscillator", {"high": ohlcv["high"], "low": ohlcv["low"]}).values["ao"]
    np.testing.assert_allclose(got, ref, rtol=1e-9, atol=1e-9, equal_nan=True)


def test_accelerator_oscillator_matches_literal(ohlcv):
    med = (ohlcv["high"] + ohlcv["low"]) / 2.0

    def sma(x, n):
        return np.array([np.nan] * (n - 1) + [float(x[i - n + 1 : i + 1].mean()) for i in range(n - 1, len(x))])

    ao = sma(med, 5) - sma(med, 34)
    ref = ao - sma(ao, 5)
    got = ta.compute("accelerator_oscillator", {"high": ohlcv["high"], "low": ohlcv["low"]}).values["ac"]
    np.testing.assert_allclose(got, ref, rtol=1e-9, atol=1e-9, equal_nan=True)


def test_dpo_matches_literal(ohlcv):
    c, p = ohlcv["close"], 21
    k = p // 2 + 1
    sma = np.array([np.nan] * (p - 1) + [float(c[i - p + 1 : i + 1].mean()) for i in range(p - 1, len(c))])
    ref = np.full(len(c), np.nan)
    ref[k:] = c[:-k] - sma[k:]
    got = ta.compute("dpo", {"close": c}, period=p).values["dpo"]
    np.testing.assert_allclose(got, ref, rtol=1e-9, atol=1e-9, equal_nan=True)


def test_kst_matches_literal(ohlcv):
    c = ohlcv["close"]

    def roc(x, n):
        out = np.full(len(x), np.nan)
        out[n:] = (x[n:] / x[:-n] - 1) * 100.0
        return out

    def sma(x, n):
        out = np.full(len(x), np.nan)
        for i in range(n - 1, len(x)):
            w = x[i - n + 1 : i + 1]
            if not np.any(np.isnan(w)):
                out[i] = w.mean()
        return out

    cfg = [(10, 10), (15, 10), (20, 10), (30, 15)]
    ref = np.zeros(len(c))
    for i, (r, s) in enumerate(cfg, start=1):
        ref = ref + i * sma(roc(c, r), s)
    ref_sig = sma(ref, 9)
    got = ta.compute("kst", {"close": c}).values
    np.testing.assert_allclose(got["kst"], ref, rtol=1e-9, atol=1e-9, equal_nan=True)
    np.testing.assert_allclose(got["signal"], ref_sig, rtol=1e-9, atol=1e-9, equal_nan=True)


def test_ultimate_oscillator_matches_literal(ohlcv):
    h, low, c = ohlcv["high"], ohlcv["low"], ohlcv["close"]
    n = len(c)
    bp = np.full(n, np.nan)
    tr = np.full(n, np.nan)
    for i in range(1, n):
        bp[i] = c[i] - min(low[i], c[i - 1])
        tr[i] = max(h[i], c[i - 1]) - min(low[i], c[i - 1])

    def avg(p):
        out = np.full(n, np.nan)
        for i in range(p, n):
            s_tr = tr[i - p + 1 : i + 1]
            if np.any(np.isnan(s_tr)):
                continue
            out[i] = bp[i - p + 1 : i + 1].sum() / s_tr.sum() if s_tr.sum() != 0 else np.nan
        return out

    ref = 100.0 * (4 * avg(7) + 2 * avg(14) + avg(28)) / 7.0
    got = ta.compute("ultimate_oscillator", {"high": h, "low": low, "close": c}).values["uo"]
    np.testing.assert_allclose(got, ref, rtol=1e-9, atol=1e-9, equal_nan=True)


def test_connors_rsi_matches_literal(ohlcv):
    c = ohlcv["close"]
    n = len(c)
    streak = np.zeros(n)
    for i in range(1, n):
        if c[i] > c[i - 1]:
            streak[i] = streak[i - 1] + 1 if streak[i - 1] > 0 else 1
        elif c[i] < c[i - 1]:
            streak[i] = streak[i - 1] - 1 if streak[i - 1] < 0 else -1
    ref = (_naive_rsi(c, 3) + _naive_rsi(streak, 2)) / 2.0  # partial; rank added below
    roc1 = np.full(n, np.nan)
    roc1[1:] = (c[1:] / c[:-1] - 1) * 100.0
    pr = np.full(n, np.nan)
    for t in range(100, n):
        win = roc1[t - 99 : t + 1]
        pr[t] = 100.0 * (win < win[-1]).sum() / 99.0
    ref = (ref * 2.0 + pr) / 3.0
    got = ta.compute("connors_rsi", {"close": c}).values["crsi"]
    np.testing.assert_allclose(got, ref, rtol=1e-10, atol=1e-10, equal_nan=True)


def test_coppock_matches_literal(ohlcv):
    c = ohlcv["close"]

    def roc(x, n):
        out = np.full(len(x), np.nan)
        out[n:] = (x[n:] / x[:-n] - 1) * 100.0
        return out

    combined = roc(c, 14) + roc(c, 11)
    ref = np.full(len(c), np.nan)
    w = np.arange(1, 11, dtype=float)
    for i in range(9, len(c)):
        win = combined[i - 9 : i + 1]
        if not np.any(np.isnan(win)):
            ref[i] = float(np.dot(win, w) / w.sum())
    got = ta.compute("coppock_curve", {"close": c}).values["coppock"]
    np.testing.assert_allclose(got, ref, rtol=1e-9, atol=1e-9, equal_nan=True)


def test_rvi_matches_literal(ohlcv):
    o, h, low, c = ohlcv["open"], ohlcv["high"], ohlcv["low"], ohlcv["close"]
    n = len(c)

    def swma(x):
        out = np.full(len(x), np.nan)
        for i in range(3, len(x)):
            out[i] = (x[i - 3] + 2 * x[i - 2] + 2 * x[i - 1] + x[i]) / 6.0
        return out

    def sma(x, p):
        out = np.full(len(x), np.nan)
        for i in range(p - 1, len(x)):
            w = x[i - p + 1 : i + 1]
            if not np.any(np.isnan(w)):
                out[i] = w.mean()
        return out

    num = sma(swma(c - o), 10)
    den = sma(swma(h - low), 10)
    ref = np.where(den != 0, num / den, np.nan)
    ref_sig = swma(ref)
    got = ta.compute("rvi", {"open": o, "high": h, "low": low, "close": c}).values
    np.testing.assert_allclose(got["rvi"], ref, rtol=1e-9, atol=1e-9, equal_nan=True)
    np.testing.assert_allclose(got["signal"], ref_sig, rtol=1e-9, atol=1e-9, equal_nan=True)


def test_smi_matches_literal(ohlcv):
    h, low, c = ohlcv["high"], ohlcv["low"], ohlcv["close"]
    n = len(c)
    hi = np.array([np.nan] * 13 + [h[i - 13 : i + 1].max() for i in range(13, n)])
    lo = np.array([np.nan] * 13 + [low[i - 13 : i + 1].min() for i in range(13, n)])
    rel = c - (hi + lo) / 2.0
    half = (hi - lo) / 2.0
    num = _naive_ema(_naive_ema(rel, 3), 3)
    den = _naive_ema(_naive_ema(half, 3), 3)
    ref = np.where(den != 0, 100.0 * num / den, np.nan)
    ref_sig = _naive_ema(ref, 3)
    got = ta.compute("smi", {"high": h, "low": low, "close": c}).values
    np.testing.assert_allclose(got["smi"], ref, rtol=1e-9, atol=1e-9, equal_nan=True)
    np.testing.assert_allclose(got["signal"], ref_sig, rtol=1e-9, atol=1e-9, equal_nan=True)


def test_fisher_transform_matches_literal(ohlcv):
    h, low = ohlcv["high"], ohlcv["low"]
    n, p = len(h), 9
    ref = np.full(n, np.nan)
    value, prev_f = 0.0, 0.0
    for t in range(p - 1, n):
        hi = h[t - p + 1 : t + 1].max()
        lo = low[t - p + 1 : t + 1].min()
        rng = hi - lo
        if rng == 0:
            ref[t] = ref[t - 1]
            continue
        x = 2.0 * (((h[t] + low[t]) / 2.0 - lo) / rng - 0.5)
        x = max(-0.999, min(0.999, x))
        value = 0.33 * x + 0.67 * value
        value = max(-0.999, min(0.999, value))
        ref[t] = 0.5 * np.log((1 + value) / (1 - value)) + 0.5 * prev_f
        prev_f = ref[t]
    got = ta.compute("fisher_transform", {"high": h, "low": low}).values
    np.testing.assert_allclose(got["fisher"], ref, rtol=1e-9, atol=1e-9, equal_nan=True)
    np.testing.assert_allclose(got["trigger"][1:], ref[:-1], rtol=1e-9, atol=1e-9, equal_nan=True)


def test_balance_of_power_matches_literal(ohlcv):
    o, h, low, c = ohlcv["open"], ohlcv["high"], ohlcv["low"], ohlcv["close"]
    rng = h - low
    ref = np.where(rng > 0, (c - o) / rng, np.nan)
    got = ta.compute("balance_of_power", {"open": o, "high": h, "low": low, "close": c}).values["bop"]
    np.testing.assert_allclose(got, ref, rtol=1e-9, atol=1e-9, equal_nan=True)


def test_force_index_matches_literal(ohlcv):
    c, v = ohlcv["close"], ohlcv["volume"]
    raw = np.full(len(c), np.nan)
    raw[1:] = (c[1:] - c[:-1]) * v[1:]
    got = ta.compute("force_index", {"close": c, "volume": v}).values
    np.testing.assert_allclose(got["efi"], raw, rtol=1e-9, atol=1e-9, equal_nan=True)
    np.testing.assert_allclose(got["efi_ema"], _naive_ema(raw, 13), rtol=1e-9, atol=1e-9, equal_nan=True)


def test_price_oscillator_matches_literal(ohlcv):
    c = ohlcv["close"]

    def sma(x, n):
        return np.array([np.nan] * (n - 1) + [float(x[i - n + 1 : i + 1].mean()) for i in range(n - 1, len(x))])

    f, s = sma(c, 10), sma(c, 21)
    ref = np.where(s != 0, 100.0 * (f - s) / s, np.nan)
    got = ta.compute("price_oscillator", {"close": c}).values["price_osc"]
    np.testing.assert_allclose(got, ref, rtol=1e-9, atol=1e-9, equal_nan=True)


# -------------------------------------------------------------- volatility 2
def test_mass_index_matches_literal(ohlcv):
    rng = ohlcv["high"] - ohlcv["low"]
    e1 = _naive_ema(rng, 9)
    e2 = _naive_ema(e1, 9)
    ratio = np.where(e2 != 0, e1 / e2, np.nan)
    ref = np.full(len(rng), np.nan)
    for i in range(24, len(rng)):
        w = ratio[i - 24 : i + 1]
        if not np.any(np.isnan(w)):
            ref[i] = w.sum()
    got = ta.compute("mass_index", {"high": ohlcv["high"], "low": ohlcv["low"]}).values["mass"]
    np.testing.assert_allclose(got, ref, rtol=1e-10, equal_nan=True)


def test_standard_error_bands_matches_literal(ohlcv):
    c, p = ohlcv["close"], 14
    mid = np.full(len(c), np.nan)
    up = np.full(len(c), np.nan)
    lo = np.full(len(c), np.nan)
    for t in range(p - 1, len(c)):
        x = np.arange(p, dtype=float)
        y = c[t - p + 1 : t + 1]
        b, a = np.polyfit(x, y, 1)
        se = np.sqrt(((y - (a + b * x)) ** 2).sum() / (p - 2))
        mid[t] = a + b * (p - 1)
        up[t] = mid[t] + 2 * se
        lo[t] = mid[t] - 2 * se
    got = ta.compute("standard_error_bands", {"close": c}, period=p).values
    np.testing.assert_allclose(got["middle"], mid, rtol=1e-8, equal_nan=True)
    np.testing.assert_allclose(got["upper"], up, rtol=1e-8, equal_nan=True)
    np.testing.assert_allclose(got["lower"], lo, rtol=1e-8, equal_nan=True)


def test_choppiness_matches_literal(ohlcv):
    h, low, c = ohlcv["high"], ohlcv["low"], ohlcv["close"]
    n, p = len(c), 14
    tr = np.full(n, np.nan)
    for i in range(1, n):
        tr[i] = max(h[i] - low[i], abs(h[i] - c[i - 1]), abs(low[i] - c[i - 1]))
    ref = np.full(n, np.nan)
    for i in range(p, n):
        s_tr = tr[i - p + 1 : i + 1]
        span = h[i - p + 1 : i + 1].max() - low[i - p + 1 : i + 1].min()
        if np.any(np.isnan(s_tr)) or span == 0:
            continue
        ref[i] = 100.0 * np.log10(s_tr.sum() / span) / np.log10(p)
    got = ta.compute("choppiness", {"high": h, "low": low, "close": c}).values["chop"]
    np.testing.assert_allclose(got, ref, rtol=1e-9, atol=1e-9, equal_nan=True)


def test_garman_klass_matches_literal(ohlcv):
    h, low, o, c = ohlcv["high"], ohlcv["low"], ohlcv["open"], ohlcv["close"]
    p = 20
    v = 0.5 * np.log(h / low) ** 2 - (2 * np.log(2) - 1) * np.log(c / o) ** 2
    ref = np.full(len(c), np.nan)
    for i in range(p - 1, len(c)):
        ref[i] = 100.0 * np.sqrt(max(v[i - p + 1 : i + 1].mean(), 0.0) * 252)
    got = ta.compute("garman_klass", {"high": h, "low": low, "open": o, "close": c}).values["gk_vol"]
    np.testing.assert_allclose(got, ref, rtol=1e-9, atol=1e-9, equal_nan=True)


def test_volatility_zero_trend_matches_literal(ohlcv):
    c, p = ohlcv["close"], 20
    ref = np.full(len(c), np.nan)
    for i in range(p, len(c)):
        ch = np.abs(np.diff(c[i - p : i + 1]))
        ref[i] = 100.0 * ch.mean() / c[i - p + 1 : i + 1].mean()
    got = ta.compute("volatility_zero_trend", {"close": c}).values["vzt"]
    np.testing.assert_allclose(got, ref, rtol=1e-9, atol=1e-9, equal_nan=True)


# ------------------------------------------------------------------ volume 2
def test_net_volume_matches_literal(ohlcv):
    c, v = ohlcv["close"], ohlcv["volume"]
    ref = np.zeros(len(c))
    for i in range(1, len(c)):
        ref[i] = v[i] if c[i] > c[i - 1] else (-v[i] if c[i] < c[i - 1] else 0.0)
    got = ta.compute("net_volume", {"close": c, "volume": v}).values["net_volume"]
    np.testing.assert_allclose(got, ref, rtol=1e-9, atol=1e-9, equal_nan=True)


def test_pvt_matches_literal(ohlcv):
    c, v = ohlcv["close"], ohlcv["volume"]
    ref = np.zeros(len(c))
    for i in range(1, len(c)):
        ref[i] = ref[i - 1] + v[i] * (c[i] - c[i - 1]) / c[i - 1]
    got = ta.compute("pvt", {"close": c, "volume": v}).values["pvt"]
    np.testing.assert_allclose(got, ref, rtol=1e-9, atol=1e-9, equal_nan=True)


def test_volume_oscillator_matches_literal(ohlcv):
    v = ohlcv["volume"]
    s, lo = _naive_ema(v, 14), _naive_ema(v, 28)
    ref = np.where(lo != 0, 100.0 * (s - lo) / lo, np.nan)
    got = ta.compute("volume_oscillator", {"volume": v}).values["volume_osc"]
    np.testing.assert_allclose(got, ref, rtol=1e-9, atol=1e-9, equal_nan=True)


def test_ease_of_movement_matches_literal(ohlcv):
    h, low, v = ohlcv["high"], ohlcv["low"], ohlcv["volume"]
    n, p = len(h), 14
    raw = np.full(n, np.nan)
    for i in range(1, n):
        dist = (h[i] + low[i]) / 2 - (h[i - 1] + low[i - 1]) / 2
        rng = h[i] - low[i]
        if rng <= 0 or v[i] <= 0:
            continue
        raw[i] = dist / (v[i] / rng)
    ref = np.full(n, np.nan)
    for i in range(p, n):
        w = raw[i - p + 1 : i + 1]
        if not np.any(np.isnan(w)):
            ref[i] = w.mean()
    got = ta.compute("ease_of_movement", {"high": h, "low": low, "volume": v}).values["emv"]
    np.testing.assert_allclose(got, ref, rtol=1e-9, atol=1e-9, equal_nan=True)


def test_klinger_matches_literal(ohlcv):
    h, low, c, v = ohlcv["high"], ohlcv["low"], ohlcv["close"], ohlcv["volume"]
    n = len(h)
    trend = np.ones(n)
    cm = np.zeros(n)
    vf = np.zeros(n)
    cm[0] = h[0] - low[0]
    for i in range(1, n):
        dm = h[i] - low[i]
        if h[i] + low[i] > h[i - 1] + low[i - 1]:
            trend[i] = 1.0
        elif h[i] + low[i] < h[i - 1] + low[i - 1]:
            trend[i] = -1.0
        else:
            trend[i] = trend[i - 1]
        cm[i] = cm[i - 1] + dm if trend[i] == trend[i - 1] else (h[i - 1] - low[i - 1]) + dm
        if cm[i] != 0:
            vf[i] = v[i] * abs(2 * (dm / cm[i] - 1)) * trend[i] * 100.0
    ref_kvo = _naive_ema(vf, 34) - _naive_ema(vf, 55)
    ref_sig = _naive_ema(ref_kvo, 13)
    got = ta.compute("klinger", {"high": h, "low": low, "close": c, "volume": v}).values
    np.testing.assert_allclose(got["kvo"], ref_kvo, rtol=1e-10, equal_nan=True)
    np.testing.assert_allclose(got["signal"], ref_sig, rtol=1e-10, equal_nan=True)


# --------------------------------------------------------------- docs guard
NEW_NAMES = [
    "alma", "t3", "zlema", "vidya", "smma", "lsma", "linreg_slope",
    "mcginley_dynamic", "alligator", "gmma", "envelopes",
    "awesome_oscillator", "accelerator_oscillator", "dpo", "kst",
    "ultimate_oscillator", "connors_rsi", "coppock_curve", "rvi", "smi",
    "fisher_transform", "balance_of_power", "force_index", "price_oscillator",
    "mass_index", "standard_error", "standard_error_bands", "choppiness",
    "garman_klass", "volatility_zero_trend",
    "net_volume", "pvt", "volume_oscillator", "ease_of_movement", "klinger",
]


def test_batch2_indicators_are_documented():
    by_name = {m["name"]: m for m in ta.available()}
    for name in NEW_NAMES:
        assert name in by_name, f"{name} is not registered"
        assert by_name[name]["formula"], f"{name} has no documented formula"
        assert by_name[name]["reference"], f"{name} has no reference"
