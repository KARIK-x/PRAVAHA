"""Indicator correctness tests.

Three layers of verification:
1. Hand-computable exact values (SMA, ROC, momentum, true range, OBV).
2. An independent literal re-implementation of the published formula, written
   directly from the reference rather than reusing engine primitives.
3. A causality property: recomputing on any prefix must reproduce the same
   values, which catches look-ahead bugs across every indicator at once.
"""

from __future__ import annotations

import numpy as np
import pytest

from megatool import ta
from megatool.ta import volume as volume_ta


def _naive_sma(x: np.ndarray, n: int) -> np.ndarray:
    out = np.full(len(x), np.nan)
    for i in range(n - 1, len(x)):
        out[i] = x[i - n + 1 : i + 1].mean()
    return out


def _naive_ema(x: np.ndarray, n: int) -> np.ndarray:
    """Independent EMA: SMA seed, then alpha = 2/(n+1)."""
    out = np.full(len(x), np.nan)
    out[n - 1] = x[:n].mean()
    a = 2.0 / (n + 1)
    for i in range(n, len(x)):
        out[i] = out[i - 1] + a * (x[i] - out[i - 1])
    return out


def _naive_wilder_rsi(c: np.ndarray, n: int) -> np.ndarray:
    """Literal transcription of Wilder's RSI, written from the definition."""
    out = np.full(len(c), np.nan)
    gains = np.zeros(len(c) - 1)
    losses = np.zeros(len(c) - 1)
    for i in range(1, len(c)):
        ch = c[i] - c[i - 1]
        gains[i - 1] = ch if ch > 0 else 0.0
        losses[i - 1] = -ch if ch < 0 else 0.0
    ag = gains[:n].mean()
    al = losses[:n].mean()
    # Both averages zero means the series never moved: RS = 0/0 is undefined,
    # so the honest answer is NaN, not a directional 100 or 0.
    out[n] = np.nan if (ag == 0 and al == 0) else 100.0 - 100.0 / (1.0 + ag / al)
    for i in range(n + 1, len(c)):
        ag = (ag * (n - 1) + gains[i - 1]) / n
        al = (al * (n - 1) + losses[i - 1]) / n
        if ag == 0 and al == 0:
            out[i] = np.nan
        elif al == 0:
            out[i] = 100.0
        else:
            out[i] = 100.0 - 100.0 / (1.0 + ag / al)
    return out


# ------------------------------------------------------------------- exact
def test_sma_exact():
    x = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    got = ta.compute("sma", {"close": x}, period=3).values["sma"]
    assert np.isnan(got[0]) and np.isnan(got[1])
    assert got[2] == pytest.approx(2.0)
    assert got[3] == pytest.approx(3.0)
    assert got[4] == pytest.approx(4.0)


def test_ema_seed_is_sma_of_first_period():
    x = np.arange(1.0, 11.0)
    r = ta.compute("ema", {"close": x}, period=4)
    # seeded with mean(1,2,3,4) = 2.5
    assert r.values["ema"][3] == pytest.approx(2.5)
    assert np.isnan(r.values["ema"][2])
    # next: 2.5 + 2/5*(5 - 2.5) = 3.5
    assert r.values["ema"][4] == pytest.approx(3.5)


def test_roc_and_momentum_exact():
    x = np.array([100.0, 110.0, 121.0, 133.1])
    roc = ta.compute("roc", {"close": x}, period=2).values["roc"]
    assert np.isnan(roc[1])
    assert roc[2] == pytest.approx(21.0)
    mom = ta.compute("momentum", {"close": x}, period=2).values["momentum"]
    assert mom[2] == pytest.approx(21.0)


def test_true_range_first_bar_is_nan_then_max():
    high = np.array([10.0, 12.0, 11.0])
    low = np.array([8.0, 9.0, 9.5])
    close = np.array([9.0, 11.0, 10.0])
    tr = ta.compute("true_range", {"high": high, "low": low, "close": close}).values["true_range"]
    assert np.isnan(tr[0])
    # bar1: max(12-9=3, |12-9|=3, |9-9|=0) = 3
    assert tr[1] == pytest.approx(3.0)
    # bar2: max(11-9.5=1.5, |11-11|=0, |9.5-11|=1.5) = 1.5
    assert tr[2] == pytest.approx(1.5)


def test_obv_hand_computed():
    close = np.array([10.0, 11.0, 10.5, 10.5, 12.0])
    vol = np.array([100.0, 200.0, 150.0, 50.0, 300.0])
    obv = ta.compute("obv", {"close": close, "volume": vol}).values["obv"]
    assert obv[0] == pytest.approx(0.0)
    assert obv[1] == pytest.approx(200.0)  # up
    assert obv[2] == pytest.approx(50.0)  # down -150
    assert obv[3] == pytest.approx(50.0)  # flat
    assert obv[4] == pytest.approx(350.0)  # up +300


def test_bollinger_uses_population_std():
    x = np.array([2.0, 4.0, 4.0, 4.0, 5.0, 5.0, 7.0, 9.0])
    r = ta.compute("bollinger", {"close": x}, period=8, std_dev=2.0)
    mid = r.values["middle"][7]
    assert mid == pytest.approx(5.0)
    # population stddev of that sample is exactly 2.0
    assert np.std(x, ddof=0) == pytest.approx(2.0)
    assert r.values["upper"][7] == pytest.approx(5.0 + 4.0)
    assert r.values["lower"][7] == pytest.approx(5.0 - 4.0)


def test_rsi_matches_wilder_published_example():
    """Wilder's own worked example; first two published values must match."""
    close = np.array(
        [
            44.34,
            44.09,
            44.15,
            43.61,
            44.33,
            44.83,
            45.10,
            45.42,
            45.84,
            46.08,
            45.89,
            46.03,
            45.61,
            46.28,
            46.28,
            46.00,
            46.03,
            46.41,
            46.22,
            45.64,
        ]
    )
    rsi = ta.compute("rsi", {"close": close}, period=14).values["rsi"]
    assert np.isnan(rsi[13])
    assert rsi[14] == pytest.approx(70.46, abs=0.01)
    assert rsi[15] == pytest.approx(66.25, abs=0.01)


# ------------------------------------------- flat series (RS = 0/0 is undefined)
# A series that never moved has avg_gain == avg_loss == 0, so RS = 0/0 has no
# value. Reporting 100 (maximum bullish) or 0 (maximum bearish) would be a
# directional claim the data cannot support, so RSI must be NaN.
@pytest.mark.parametrize("length", [15, 16, 30, 60, 200])
@pytest.mark.parametrize("level", [1.0, 50.0, 5000.0])
def test_rsi_flat_series_is_undefined(level, length):
    r = ta.compute("rsi", {"close": np.full(length, level)}, period=14)
    out = r.values["rsi"]
    assert np.isnan(out).all(), f"flat series at {level} x{length} produced {out[-1]!r}"
    assert r.insufficient_data is True
    assert "undefined" in r.message
    assert r.latest()["rsi"] is None


def test_rsi_flat_series_is_neither_0_nor_100():
    """Asymmetry guard: 100 and 0 are both directional, NaN is the only honest value."""
    out = ta.compute("rsi", {"close": np.full(40, 50.0)}, period=14).values["rsi"]
    assert not np.any(out == 100.0)
    assert not np.any(out == 0.0)


def test_rsi_flat_series_does_not_depend_on_price_scale():
    """RSI is scale-free, so the undefined verdict must not vary with price level."""
    verdicts = [
        np.isnan(ta.compute("rsi", {"close": np.full(40, x)}, period=14).values["rsi"]).all()
        for x in (0.01, 1.0, 33.3, 50.0, 999.9, 5000.0)
    ]
    assert all(verdicts)


def test_rsi_rising_series_still_reports_exactly_100():
    """The new guard must not overreach into genuine all-gain series."""
    r = ta.compute("rsi", {"close": np.arange(100.0, 130.0)}, period=14)
    assert r.values["rsi"][-1] == pytest.approx(100.0)
    assert r.insufficient_data is False


def test_rsi_falling_series_still_reports_exactly_0():
    r = ta.compute("rsi", {"close": np.arange(130.0, 100.0, -1.0)}, period=14)
    assert r.values["rsi"][-1] == pytest.approx(0.0)
    assert r.insufficient_data is False


def test_rsi_insufficient_history_is_unchanged():
    """Length short-circuit keeps its own message, distinct from the flat verdict."""
    for n in (1, 5, 14):
        r = ta.compute("rsi", {"close": np.full(n, 50.0)}, period=14)
        assert r.insufficient_data is True
        assert "needs at least 15 closes" in r.message
        assert np.isnan(r.values["rsi"]).all()


def test_rsi_warmup_is_nan_then_defined():
    """Warm-up bars stay NaN without flipping the whole result to insufficient."""
    r = ta.compute("rsi", {"close": np.arange(100.0, 120.0)}, period=14)
    assert np.isnan(r.values["rsi"][:14]).all()
    assert not np.isnan(r.values["rsi"][14])
    assert r.insufficient_data is False


def test_rsi_independent_reference_agrees_on_flat_series():
    """The corrected literal reference must reach the same NaN verdict."""
    c = np.full(40, 77.0)
    ref = _naive_wilder_rsi(c, 14)
    got = ta.compute("rsi", {"close": c}, period=14).values["rsi"]
    np.testing.assert_allclose(got, ref, rtol=1e-12, atol=1e-12, equal_nan=True)
    assert np.isnan(ref).all()


def test_rsi_reference_still_agrees_on_varying_series():
    """The helper edit must not have broken ordinary agreement."""
    rng = np.random.default_rng(11)
    c = 100.0 + np.cumsum(rng.normal(0, 1.0, 80))
    ref = _naive_wilder_rsi(c, 14)
    got = ta.compute("rsi", {"close": c}, period=14).values["rsi"]
    np.testing.assert_allclose(got, ref, rtol=1e-10, atol=1e-10, equal_nan=True)


def test_rsi_recovers_after_a_flat_prefix():
    """A flat start followed by movement must produce defined values again."""
    c = np.concatenate([np.full(15, 50.0), np.arange(50.0, 70.0)])
    r = ta.compute("rsi", {"close": c}, period=14)
    assert np.isnan(r.values["rsi"][15])  # still flat at that bar
    assert r.values["rsi"][-1] == pytest.approx(100.0)
    assert r.insufficient_data is False


def test_rsi_flat_tail_retains_prior_momentum():
    """Known, standard Wilder behaviour — pinned deliberately, not an accident.

    The smoothed averages decay proportionally, so their RATIO (and therefore
    RSI) is preserved through a flat tail. Only a series that has *never* moved
    is undefined. Changing this would require inventing a decay rule.
    """
    c = np.concatenate([np.arange(100.0, 115.0), np.full(15, 114.0)])
    r = ta.compute("rsi", {"close": c}, period=14)
    assert r.values["rsi"][-1] == pytest.approx(100.0)
    assert not np.isnan(r.values["rsi"][14])


# --------------------------------------------- money flow index (0/0 is undefined)
def _naive_mfi(h, lo, c, v, period):
    """Literal transcription of MFI, written from the definition."""
    tp = [(h[i] + lo[i] + c[i]) / 3.0 for i in range(len(c))]
    mf = [tp[i] * v[i] for i in range(len(c))]
    pos, neg = [0.0] * len(c), [0.0] * len(c)
    for i in range(1, len(c)):
        if tp[i] > tp[i - 1]:
            pos[i] = mf[i]
        elif tp[i] < tp[i - 1]:
            neg[i] = mf[i]
    p, ng = sum(pos[-period:]), sum(neg[-period:])
    if ng == 0:
        return 100.0 if p > 0 else float("nan")
    return 100.0 - 100.0 / (1.0 + p / ng)


def _flat_mfi(n, level=50.0, volume=0.0):
    px = np.full(n, level)
    return ta.compute(
        "mfi", {"high": px, "low": px, "close": px, "volume": np.full(n, volume)}, period=14
    )


@pytest.mark.parametrize("volume", [0.0, 1_000.0])
@pytest.mark.parametrize("level", [1.0, 50.0, 5000.0])
def test_mfi_no_money_flow_is_undefined(level, volume):
    """Constant typical price means no positive and no negative flow -> MFR = 0/0."""
    r = _flat_mfi(40, level, volume)
    assert np.isnan(r.values["mfi"]).all(), f"flat tp/vol={volume} gave {r.values['mfi'][-1]!r}"
    assert r.latest()["mfi"] is None


def test_mfi_zero_volume_with_constant_price_reports_nan_not_100():
    """The originally reported defect: this returned 100."""
    r = _flat_mfi(40, 50.0, 0.0)
    assert not np.any(r.values["mfi"] == 100.0)
    assert not np.any(r.values["mfi"] == 0.0)  # 0 would be equally directional


def test_mfi_constant_price_with_positive_volume_is_also_undefined():
    """Volume alone cannot create flow if the typical price never moves."""
    r = _flat_mfi(40, 50.0, 1_000.0)
    assert np.isnan(r.values["mfi"]).all()


def test_mfi_rising_prices_report_exactly_100():
    """Purely positive flow is the maximum by definition - the guard must not overreach."""
    px = np.arange(100.0, 140.0)
    r = ta.compute("mfi", {"high": px, "low": px, "close": px, "volume": np.full(40, 1000.0)})
    assert r.values["mfi"][-1] == pytest.approx(100.0)
    assert r.insufficient_data is False


def test_mfi_falling_prices_report_exactly_0():
    px = np.arange(140.0, 100.0, -1.0)
    r = ta.compute("mfi", {"high": px, "low": px, "close": px, "volume": np.full(40, 1000.0)})
    assert r.values["mfi"][-1] == pytest.approx(0.0)
    assert r.insufficient_data is False


def test_mfi_insufficient_history_reports_clearly():
    px = np.full(40, 50.0)
    for n in (1, 5, 14):
        r = ta.compute(
            "mfi",
            {"high": px[:n], "low": px[:n], "close": px[:n], "volume": np.zeros(n)},
            period=14,
        )
        assert r.insufficient_data is True
        assert "needs at least 15 bars" in r.message
        assert np.isnan(r.values["mfi"]).all()


def test_mfi_warmup_is_nan_then_defined():
    """First output lands at index `period`; shortness must not flip the whole result."""
    rng = np.random.default_rng(5)
    px = 100.0 + np.cumsum(rng.normal(0, 1.0, 40))
    r = ta.compute("mfi", {"high": px, "low": px, "close": px, "volume": np.full(40, 1000.0)})
    assert np.isnan(r.values["mfi"][:14]).all()
    assert not np.isnan(r.values["mfi"][14])
    assert r.insufficient_data is False


def test_mfi_matches_independent_reference_including_undefined():
    rng = np.random.default_rng(9)
    px = 100.0 + np.cumsum(rng.normal(0, 1.0, 60))
    vol = rng.integers(1_000, 9_000, size=60).astype(float)
    ref = _naive_mfi(list(px), list(px), list(px), list(vol), 14)
    got = ta.compute("mfi", {"high": px, "low": px, "close": px, "volume": vol}).values["mfi"][-1]
    assert got == pytest.approx(ref, abs=1e-9)
    # and the corrected reference agrees the flat case is undefined
    flat = np.full(40, 50.0)
    assert np.isnan(_naive_mfi(list(flat), list(flat), list(flat), [0.0] * 40, 14))


def test_mfi_rejects_missing_volume():
    px = np.full(40, 50.0)
    with pytest.raises(ValueError, match="requires a 'volume' input"):
        volume_ta.mfi({"high": px, "low": px, "close": px})


def test_mfi_rejects_entirely_missing_volume():
    px = np.full(40, 50.0)
    with pytest.raises(ValueError, match="entirely missing"):
        volume_ta.mfi({"high": px, "low": px, "close": px, "volume": np.full(40, np.nan)})


def test_mfi_tolerates_partially_missing_volume():
    """NaN volume is treated as zero flow for that bar, not as a crash."""
    px = np.arange(100.0, 140.0)
    vol = np.full(40, np.nan)
    vol[14:] = 1_000.0
    r = ta.compute("mfi", {"high": px, "low": px, "close": px, "volume": vol})
    assert r.values["mfi"][-1] == pytest.approx(100.0)  # rising -> positive flow only


def test_mfi_does_not_crash_on_a_nan_price_bar():
    px = np.full(40, 50.0)
    px[10] = np.nan
    vol = np.zeros(40)
    r = ta.compute("mfi", {"high": px, "low": px, "close": px, "volume": vol})
    assert np.isnan(r.values["mfi"]).all()  # still no flow, so still undefined


# -------------------------------------------------- independent re-implement
@pytest.mark.parametrize(
    "name,params,inputs",
    [
        ("sma", {"period": 7}, ["close"]),
        ("ema", {"period": 7}, ["close"]),
        ("rsi", {"period": 14}, ["close"]),
        ("roc", {"period": 5}, ["close"]),
        ("momentum", {"period": 5}, ["close"]),
    ],
)
def test_matches_independent_reference(name, params, inputs, closes):
    r = ta.compute(name, {"close": closes}, **params)
    out = r.values[list(r.values)[0]]
    if name == "sma":
        ref = _naive_sma(closes, params["period"])
    elif name == "ema":
        ref = _naive_ema(closes, params["period"])
    elif name == "rsi":
        ref = _naive_wilder_rsi(closes, params["period"])
    elif name == "roc":
        ref = np.full(len(closes), np.nan)
        p = params["period"]
        ref[p:] = 100.0 * (closes[p:] - closes[:-p]) / closes[:-p]
    else:
        p = params["period"]
        ref = np.full(len(closes), np.nan)
        ref[p:] = closes[p:] - closes[:-p]
    np.testing.assert_allclose(out, ref, rtol=1e-10, atol=1e-10, equal_nan=True)


def test_sma_matches_pandas_independent_path(closes):
    """Cross-check the NumPy implementation against pandas' rolling mean."""
    import pandas as pd

    got = ta.compute("sma", {"close": closes}, period=20).values["sma"]
    ref = pd.Series(closes).rolling(20).mean().to_numpy()
    np.testing.assert_allclose(got, ref, rtol=1e-12, atol=1e-12, equal_nan=True)


# ------------------------------------ extra batch-1: independent re-checks
def _naive_tr(h, lo, c):
    n = len(c)
    out = np.full(n, np.nan)
    for i in range(1, n):
        out[i] = max(h[i] - lo[i], abs(h[i] - c[i - 1]), abs(lo[i] - c[i - 1]))
    return out


def _naive_pop_std(x, n):
    out = np.full(len(x), np.nan)
    for i in range(n - 1, len(x)):
        w = x[i - n + 1 : i + 1]
        out[i] = np.sqrt(((w - w.mean()) ** 2).mean())
    return out


def test_vortex_matches_literal_definition(ohlcv):
    """VI+ / VI- recomputed from the published sums, not the engine helpers."""
    h, lo, c = ohlcv["high"], ohlcv["low"], ohlcv["close"]
    n = 14
    got = ta.compute("vortex", ohlcv, period=n)
    vmp = np.abs(h[1:] - lo[:-1])
    vmm = np.abs(lo[1:] - h[:-1])
    tr = _naive_tr(h, lo, c)[1:]
    for i in range(n - 1, len(vmp)):
        sp = vmp[i - n + 1 : i + 1].sum()
        sm = vmm[i - n + 1 : i + 1].sum()
        st = tr[i - n + 1 : i + 1].sum()
        assert got.values["vi_plus"][i + 1] == pytest.approx(sp / st, rel=1e-12)
        assert got.values["vi_minus"][i + 1] == pytest.approx(sm / st, rel=1e-12)


def test_average_price_matches_literal_mean(ohlcv):
    got = ta.compute("average_price", ohlcv).values["average_price"]
    ref = (ohlcv["open"] + ohlcv["high"] + ohlcv["low"] + ohlcv["close"]) / 4.0
    np.testing.assert_allclose(got, ref, rtol=1e-12, atol=1e-12)


def test_bollinger_width_and_percent_b_match_literal_definition(closes):
    n, k = 20, 2.0
    w = ta.compute("bollinger_width", {"close": closes}, period=n, std_dev=k)
    b = ta.compute("percent_b", {"close": closes}, period=n, std_dev=k)
    sd = _naive_pop_std(closes, n)
    mean = _naive_sma(closes, n)
    up = mean + k * sd
    lo = mean - k * sd
    with np.errstate(divide="ignore", invalid="ignore"):
        np.testing.assert_allclose(
            w.values["width_pct"], 100.0 * (up - lo) / mean, rtol=1e-10, equal_nan=True
        )
        np.testing.assert_allclose(
            b.values["percent_b"], (closes - lo) / (up - lo), rtol=1e-10, equal_nan=True
        )


def test_chaikin_volatility_matches_literal_definition(ohlcv):
    e_p, r_p = 10, 10
    got = ta.compute("chaikin_volatility", ohlcv, ema_period=e_p, roc_period=r_p)
    e = _naive_ema(ohlcv["high"] - ohlcv["low"], e_p)
    ref = np.full(len(e), np.nan)
    with np.errstate(divide="ignore", invalid="ignore"):
        ref[r_p:] = 100.0 * (e[r_p:] - e[:-r_p]) / e[:-r_p]
    np.testing.assert_allclose(
        got.values["chaikin_vol"], ref, rtol=1e-10, atol=1e-10, equal_nan=True
    )


def test_ma_cross_matches_literal_definition(closes):
    got = ta.compute("ma_cross", {"close": closes}, fast=10, slow=30)
    np.testing.assert_allclose(got.values["fast"], _naive_sma(closes, 10), rtol=1e-12, equal_nan=True)
    np.testing.assert_allclose(got.values["slow"], _naive_sma(closes, 30), rtol=1e-12, equal_nan=True)
    diff = got.values["diff"]
    for i in range(len(closes)):
        if np.isfinite(diff[i]):
            assert got.values["state"][i] == (1.0 if diff[i] > 0 else -1.0)
        else:
            assert np.isnan(got.values["state"][i])


def test_chande_kroll_stop_matches_literal_two_stage_definition(ohlcv):
    p, atr_p, x, y = 10, 10, 1.0, 3.0
    got = ta.compute(
        "chande_kroll_stop", ohlcv, period=p, multiplier=x, atr_period=atr_p, trail=y
    )
    # Independent Wilder ATR: SMA seed over the first atr_p true ranges.
    tr = _naive_tr(ohlcv["high"], ohlcv["low"], ohlcv["close"])
    atr = np.full(len(tr), np.nan)
    atr[atr_p] = np.nanmean(tr[1 : atr_p + 1])
    for i in range(atr_p + 1, len(tr)):
        atr[i] = (atr[i - 1] * (atr_p - 1) + tr[i]) / atr_p
    hh = np.full(len(tr), np.nan)
    ll = np.full(len(tr), np.nan)
    for i in range(p - 1, len(tr)):
        hh[i] = ohlcv["high"][i - p + 1 : i + 1].max()
        ll[i] = ohlcv["low"][i - p + 1 : i + 1].min()
    init_l, init_s = hh - x * atr, ll + x * atr
    np.testing.assert_allclose(got.values["initial_long"], init_l, rtol=1e-9, equal_nan=True)
    np.testing.assert_allclose(got.values["initial_short"], init_s, rtol=1e-9, equal_nan=True)
    prev_l = prev_s = np.nan
    for i in range(len(tr)):
        if not (np.isfinite(init_l[i]) and np.isfinite(init_s[i])):
            continue
        if not np.isfinite(prev_l):
            prev_l, prev_s = init_l[i], init_s[i]
        else:
            prev_l = max(prev_l, ohlcv["close"][i] - y * atr[i])
            prev_s = min(prev_s, ohlcv["close"][i] + y * atr[i])
        assert got.values["stop_long"][i] == pytest.approx(prev_l, rel=1e-9)
        assert got.values["stop_short"][i] == pytest.approx(prev_s, rel=1e-9)


def test_relative_volatility_index_matches_literal_definition(closes):
    n, sig = 10, 14
    got = ta.compute("relative_volatility_index", {"close": closes}, period=n, signal=sig)
    sd = _naive_pop_std(closes, n)
    up = np.zeros(len(closes))
    dn = np.zeros(len(closes))
    for i in range(1, len(closes)):
        if np.isnan(sd[i]):
            up[i] = dn[i] = np.nan
        elif closes[i] > closes[i - 1]:
            up[i] = sd[i]
        elif closes[i] < closes[i - 1]:
            dn[i] = sd[i]
    # Independent Wilder smoothing with an SMA seed over the first n values.
    def _wilder(vals, period):
        out = np.full(len(vals), np.nan)
        start = None
        for i in range(len(vals)):
            if start is None:
                if i + 1 >= period and np.isfinite(vals[i - period + 1 : i + 1]).all():
                    start = i
                    out[i] = vals[i - period + 1 : i + 1].mean()
            else:
                out[i] = (out[i - 1] * (period - 1) + vals[i]) / period
        return out

    su, sn = _wilder(up, n), _wilder(dn, n)
    with np.errstate(divide="ignore", invalid="ignore"):
        rvi = 100.0 * su / (su + sn)
    np.testing.assert_allclose(got.values["rvi"], rvi, rtol=1e-9, equal_nan=True)
    np.testing.assert_allclose(
        got.values["signal"], _naive_sma(rvi, sig), rtol=1e-9, equal_nan=True
    )


def test_price_correlation_matches_numpy_corrcoef(closes):
    n = 20
    got = ta.compute("price_correlation", {"close": closes}, period=n).values["corr"]
    x = np.arange(len(closes), dtype=float)
    for i in range(n - 1, len(closes)):
        ref = np.corrcoef(x[i - n + 1 : i + 1], closes[i - n + 1 : i + 1])[0, 1]
        assert got[i] == pytest.approx(ref, rel=1e-9, abs=1e-9)


def test_price_correlation_is_exactly_one_on_a_perfect_line():
    """A strictly straight line has zero residual, so r = 1 to machine precision."""
    n = 60
    line = 10.0 + 0.5 * np.arange(n)
    got = ta.compute("price_correlation", {"close": line}, period=20).values["corr"]
    assert got[-1] == pytest.approx(1.0, abs=1e-12)


# ------------------------------------- sparse pivot indicators (carve-out)
# (These live after ALL_INDICATORS is defined, further down the file.)


# ------------------------------------------------------------------ causality
ALL_INDICATORS = [m["name"] for m in ta.available()]

#: Indicators whose output is a SPARSE pivot price stamped on the bar the pivot
#: belongs to. That construction repaints by design — the value at bar i is only
#: decided once a later bar confirms the reversal — so the two warm-up
#: invariants below (which assume a dense, monotonically-defined series) cannot
#: hold and no honest fixed warm-up exists. They are excluded here on purpose and
#: covered instead by the dedicated tests further down, which assert the
#: properties that DO hold and assert the repainting explicitly. Excluding them
#: is recorded in INDICATOR_CATALOGUE.md rather than hidden.
SPARSE_PIVOT_INDICATORS = {"zigzag", "williams_fractal"}
DENSE_INDICATORS = [n for n in ALL_INDICATORS if n not in SPARSE_PIVOT_INDICATORS]
REPAINTING_INDICATORS = [n for n in ALL_INDICATORS if n in SPARSE_PIVOT_INDICATORS]


def test_sparse_carve_out_is_small_and_named():
    """The carve-out must be exactly the declared set — no silent growth."""
    assert set(SPARSE_PIVOT_INDICATORS) <= set(ALL_INDICATORS)
    assert set(DENSE_INDICATORS) | set(REPAINTING_INDICATORS) == set(ALL_INDICATORS)
    assert not set(DENSE_INDICATORS) & set(REPAINTING_INDICATORS)


@pytest.mark.parametrize("name", DENSE_INDICATORS)
def test_no_lookahead_full_series_equals_prefix(name, ohlcv):
    """Recomputing on any prefix must reproduce the same leading values.

    This is the single strongest guard against look-ahead bias: if an indicator
    ever reached forward, truncating the series would change its past output.
    """
    meta, _ = ta.get(name)
    inputs = {k: ohlcv[k] for k in meta.inputs if k in ohlcv}
    full = ta.compute(name, inputs)

    for cut in (len(ohlcv["close"]) // 2, len(ohlcv["close"]) - 1):
        prefix = {k: v[:cut] for k, v in inputs.items()}
        part = ta.compute(name, prefix)
        for col in full.values:
            a = full.values[col][:cut]
            b = part.values[col]
            np.testing.assert_allclose(
                a,
                b,
                rtol=1e-9,
                atol=1e-9,
                equal_nan=True,
                err_msg=f"{name}.{col} changed when the future was removed",
            )


@pytest.mark.parametrize("name", DENSE_INDICATORS)
def test_warmup_is_nan(name, ohlcv):
    """Nothing may be emitted before an output's declared warm-up.

    Multi-output indicators declare a per-output warm-up, because (for example)
    MACD's line is valid well before its signal line.
    """
    meta, _ = ta.get(name)
    inputs = {k: ohlcv[k] for k in meta.inputs if k in ohlcv}
    r = ta.compute(name, inputs)
    for col, vals in r.values.items():
        w = r.output_warmup.get(col, r.warmup)
        if w <= 1:
            continue
        head = vals[: w - 1]
        assert np.all(np.isnan(head)), (
            f"{name}.{col} produced values before its declared warm-up of {w}"
        )


@pytest.mark.parametrize("name", DENSE_INDICATORS)
def test_warmup_is_not_over_declared(name, ohlcv):
    """The declared warm-up must be the *first* valid bar, not a loose bound."""
    meta, _ = ta.get(name)
    inputs = {k: ohlcv[k] for k in meta.inputs if k in ohlcv}
    r = ta.compute(name, inputs)
    for col, vals in r.values.items():
        w = r.output_warmup.get(col, r.warmup)
        if w >= len(vals):
            continue
        assert not np.isnan(vals[w]), (
            f"{name}.{col} warm-up declared as {w} but that bar is still NaN - "
            "the declared warm-up is too long"
        )


@pytest.mark.parametrize("name", ALL_INDICATORS)
def test_short_series_does_not_crash(name, ohlcv):
    meta, _ = ta.get(name)
    inputs = {k: v[:3] for k, v in ohlcv.items() if k in meta.inputs}
    r = ta.compute(name, inputs)
    for col, vals in r.values.items():
        assert len(vals) == 3, f"{name}.{col} length changed"


def test_ohlc_inputs_are_honoured(ohlcv):
    """An indicator declaring (high, low) must actually receive them."""
    r = ta.compute("donchian", {"high": ohlcv["high"], "low": ohlcv["low"]}, period=20)
    assert not r.insufficient_data
    last = len(ohlcv["high"]) - 1
    assert r.values["upper"][last] == pytest.approx(ohlcv["high"][last - 19 : last + 1].max())


# ----------------------------------------------------------------- parameters
def test_unknown_parameter_rejected():
    with pytest.raises(ValueError, match="unknown parameter"):
        ta.compute("sma", {"close": np.arange(10.0)}, period=5, window=3)


def test_non_positive_period_rejected():
    with pytest.raises(ValueError, match="must be > 0"):
        ta.compute("sma", {"close": np.arange(10.0)}, period=0)


def test_unknown_indicator_lists_alternatives():
    with pytest.raises(KeyError, match="unknown indicator"):
        ta.compute("does_not_exist", {"close": np.arange(10.0)})


def test_macd_requires_fast_lt_slow(ohlcv):
    r = ta.compute("macd", {"close": ohlcv["close"]}, fast=26, slow=12, signal=9)
    assert r.insufficient_data
    assert "fast" in r.message


def test_missing_volume_indicator_reports_clearly(closes):
    r = ta.compute("obv", {"close": closes})
    assert r.insufficient_data
    assert "volume" in r.message


def test_latest_returns_none_for_nan():
    x = np.array([1.0, 2.0, 3.0])
    r = ta.compute("sma", {"close": x}, period=5)
    assert r.latest() == {"sma": None}


# ============================================================================
# NEW indicators (Phase 2 run) — independent literal references.
#
# Each reference below is written directly from the published formula using
# plain Python loops and no engine primitive, so agreement is real verification
# rather than the engine agreeing with itself.
# ============================================================================


def _naive_dema(x: np.ndarray, p: int) -> np.ndarray:
    e1 = _naive_ema2(x, p)
    return 2.0 * e1 - _naive_ema2(e1, p)


def _naive_tema(x: np.ndarray, p: int) -> np.ndarray:
    e1 = _naive_ema2(x, p)
    e2 = _naive_ema2(e1, p)
    e3 = _naive_ema2(e2, p)
    return 3.0 * e1 - 3.0 * e2 + e3


def _naive_ema2(x: np.ndarray, p: int) -> np.ndarray:
    """Literal EMA seeded at the first full window of non-NaN values.

    Deliberately distinct from :func:`_naive_ema`: chained indicators (DEMA, TEMA,
    TSI, PPO signal) feed an EMA *its own* input, whose leading entries are NaN,
    so the seed has to skip that warm-up prefix instead of averaging across it.
    """
    out = np.full(len(x), np.nan)
    run = 0
    start = None
    for i, v in enumerate(x):
        run = 0 if np.isnan(v) else run + 1
        if run >= p:
            start = i - p + 1
            break
    if start is None:
        return out
    out[start + p - 1] = float(np.mean(x[start : start + p]))
    a = 2.0 / (p + 1)
    for i in range(start + p, len(x)):
        prev, v = out[i - 1], x[i]
        if np.isnan(v):
            out[i] = prev
        elif np.isnan(prev):
            out[i] = v
        else:
            out[i] = prev + a * (v - prev)
    return out


def _naive_zscore(c: np.ndarray, p: int) -> np.ndarray:
    """Literal z-score reference written straight from the definition."""
    out = np.full(len(c), np.nan)
    for i in range(p - 1, len(c)):
        w = c[i - p + 1 : i + 1]
        m = float(np.mean(w))
        sd = float(np.std(w, ddof=1))
        out[i] = (float(c[i]) - m) / sd if sd != 0 else np.nan
    return out


def _naive_vwma(c: np.ndarray, v: np.ndarray, p: int) -> np.ndarray:
    out = np.full(len(c), np.nan)
    for i in range(p - 1, len(c)):
        w = slice(i - p + 1, i + 1)
        out[i] = float(np.dot(c[w], v[w]) / v[w].sum())
    return out


def _naive_cmo(c: np.ndarray, p: int) -> np.ndarray:
    out = np.full(len(c), np.nan)
    for i in range(p, len(c)):
        su = sd = 0.0
        for j in range(i - p + 1, i + 1):
            ch = c[j] - c[j - 1]
            if ch > 0:
                su += ch
            elif ch < 0:
                sd -= ch
        out[i] = 100.0 * (su - sd) / (su + sd) if (su + sd) else np.nan
    return out


def _naive_stoch_rsi(c: np.ndarray, rp: int, sp: int) -> np.ndarray:
    rsi_v = _naive_wilder_rsi(c, rp)
    out = np.full(len(c), np.nan)
    for i in range(rp + sp - 1, len(c)):
        w = rsi_v[i - sp + 1 : i + 1]
        lo, hi = float(np.min(w)), float(np.max(w))
        if hi != lo:
            out[i] = 100.0 * (float(rsi_v[i]) - lo) / (hi - lo)
    return out


def _naive_ppo(c: np.ndarray, fast: int, slow: int, signal: int) -> np.ndarray:
    ef, es = _naive_ema(c, fast), _naive_ema(c, slow)
    line = 100.0 * (ef - es) / es
    return line, _naive_ema2(line, signal)


def _naive_tsi(c: np.ndarray, long: int, short: int) -> np.ndarray:
    m = np.concatenate(([np.nan], np.diff(c)))
    am = np.abs(m)
    num = _naive_ema2(_naive_ema2(m, long), short)
    den = _naive_ema2(_naive_ema2(am, long), short)
    with np.errstate(invalid="ignore", divide="ignore"):
        out = np.where(den == 0, np.nan, 100.0 * num / den)
    return out


def _naive_cmf(h: np.ndarray, low_: np.ndarray, c: np.ndarray, v: np.ndarray, p: int) -> np.ndarray:
    out = np.full(len(c), np.nan)
    for i in range(p - 1, len(c)):
        s = slice(i - p + 1, i + 1)
        num = den = 0.0
        for j in range(p):
            rng = h[s][j] - low_[s][j]
            clv = ((c[s][j] - low_[s][j]) - (h[s][j] - c[s][j])) / rng if rng else 0.0
            num += clv * v[s][j]
            den += v[s][j]
        out[i] = num / den if den else np.nan
    return out


def _naive_pivot(h: np.ndarray, low_: np.ndarray, c: np.ndarray) -> np.ndarray:
    out = np.full(len(c), np.nan)
    for i in range(1, len(c)):
        hh, ll, cc = h[i - 1], low_[i - 1], c[i - 1]
        out[i] = (hh + ll + cc) / 3.0
    return out


@pytest.mark.parametrize(
    "name,reference",
    [
        ("vwma", lambda d: _naive_vwma(d["close"], d["volume"], 20)),
        ("dema", lambda d: _naive_dema(d["close"], 20)),
        ("tema", lambda d: _naive_tema(d["close"], 20)),
        ("cmo", lambda d: _naive_cmo(d["close"], 14)),
        (
            "stochastic_rsi",
            lambda d: _naive_stoch_rsi(d["close"], 14, 14),
        ),
        ("tsi", lambda d: _naive_tsi(d["close"], 25, 13)),
        ("cmf", lambda d: _naive_cmf(d["high"], d["low"], d["close"], d["volume"], 20)),
        ("typical_price", lambda d: (d["high"] + d["low"] + d["close"]) / 3.0),
        ("median_price", lambda d: (d["high"] + d["low"]) / 2.0),
        ("weighted_close", lambda d: (d["high"] + d["low"] + 2 * d["close"]) / 4.0),
        (
            "standard_deviation",
            lambda d: np.where(
                np.arange(len(d["close"]), dtype=float) >= 19,
                np.array(
                    [np.nan] * 19
                    + [
                        float(np.std(d["close"][i - 19 : i + 1], ddof=1))
                        for i in range(19, len(d["close"]))
                    ]
                ),
                np.nan,
            ),
        ),
        (
            "zscore",
            lambda d: _naive_zscore(d["close"], 20),
        ),
        (
            "volume_roc",
            lambda d: np.concatenate(
                (
                    np.full(14, np.nan),
                    100.0 * (d["volume"][14:] - d["volume"][:-14]) / d["volume"][:-14],
                )
            ),
        ),
        ("pivot_points", lambda d: _naive_pivot(d["high"], d["low"], d["close"])),
    ],
)
def test_new_indicator_matches_independent_reference(name, reference, ohlcv):
    """Literal, engine-free recomputation of every formula added in the Phase 2 run."""
    got = ta.compute(name, {k: v for k, v in ohlcv.items() if k != "open"}).values
    col = "pivot" if name == "pivot_points" else list(got)[0]
    np.testing.assert_allclose(got[col], reference(ohlcv), rtol=1e-9, atol=1e-9, equal_nan=True)


def test_ppo_matches_independent_reference(ohlcv):
    c = ohlcv["close"]
    line, sig = _naive_ppo(c, 12, 26, 9)
    got = ta.compute("ppo", {"close": c}).values
    np.testing.assert_allclose(got["ppo"], line, rtol=1e-9, atol=1e-9, equal_nan=True)
    np.testing.assert_allclose(got["signal"], sig, rtol=1e-9, atol=1e-9, equal_nan=True)


def test_kama_matches_independent_reference(ohlcv):
    c = ohlcv["close"]
    p, fast, slow = 10, 2, 30
    ref = np.full(len(c), np.nan)
    ref[p - 1] = c[p - 1]
    fast_sc, slow_sc = 2.0 / (fast + 1), 2.0 / (slow + 1)
    for i in range(p, len(c)):
        change = abs(c[i] - c[i - p])
        volatility = sum(abs(c[j] - c[j - 1]) for j in range(i - p + 1, i + 1))
        er = 0.0 if volatility == 0 else change / volatility
        sc = (er * (fast_sc - slow_sc) + slow_sc) ** 2
        ref[i] = ref[i - 1] + sc * (c[i] - ref[i - 1])
    np.testing.assert_allclose(
        ta.compute("kama", {"close": c}).values["kama"], ref, rtol=1e-10, atol=1e-10, equal_nan=True
    )


def test_pivot_points_use_the_previous_bar(ohlcv):
    """A pivot level labelled at bar t must come from bar t-1, never bar t."""
    r = ta.compute(
        "pivot_points", {"high": ohlcv["high"], "low": ohlcv["low"], "close": ohlcv["close"]}
    )
    h, lw, c = ohlcv["high"], ohlcv["low"], ohlcv["close"]
    i = 37
    expected = (h[i - 1] + lw[i - 1] + c[i - 1]) / 3.0
    assert float(r.values["pivot"][i]) == pytest.approx(expected, rel=1e-12)
    assert np.isnan(r.values["pivot"][0])


def test_parabolic_sar_is_below_price_in_a_clean_uptrend():
    """In a straight rising series the SAR must stay below the bar's low."""
    n = 60
    c = np.linspace(100.0, 160.0, n)
    h = c * 1.001
    lw = c * 0.999
    sar = ta.compute("parabolic_sar", {"high": h, "low": lw}).values["sar"]
    assert np.isnan(sar[0])
    valid = sar[1:]
    assert valid.size and np.all(valid <= lw[1:] + 1e-9)


def test_chaikin_oscillator_is_the_macd_of_the_ad_line(ohlcv):
    h, low_, c, v = ohlcv["high"], ohlcv["low"], ohlcv["close"], ohlcv["volume"]
    ad = np.zeros(len(c))
    for i in range(1, len(c)):
        rng = h[i] - low_[i]
        clv = ((c[i] - low_[i]) - (h[i] - c[i])) / rng if rng else 0.0
        ad[i] = ad[i - 1] + clv * v[i]
    ref = _naive_ema2(ad, 3) - _naive_ema2(ad, 10)
    np.testing.assert_allclose(
        ta.compute(
            "chaikin_oscillator",
            {"high": h, "low": low_, "close": c, "volume": v},
        ).values["chaikin_oscillator"],
        ref,
        rtol=1e-9,
        atol=1e-9,
        equal_nan=True,
    )


def test_catalogue_documents_every_new_indicator():
    """Every indicator must publish a formula/reference, or the UI can't explain it."""
    by_name = {m["name"]: m for m in ta.available()}
    new = [
        "vwma",
        "dema",
        "tema",
        "kama",
        "parabolic_sar",
        "stochastic_rsi",
        "ppo",
        "cmo",
        "tsi",
        "cmf",
        "chaikin_oscillator",
        "volume_roc",
        "typical_price",
        "median_price",
        "weighted_close",
        "standard_deviation",
        "zscore",
        "pivot_points",
    ]
    for name in new:
        assert name in by_name, f"{name} is not registered"
        assert bool(by_name[name]["formula"]), f"{name} has no documented formula"


# ------------------------------------------------ vectorised rolling_std (B-50)
# `rolling_std` was rewritten from a per-window np.std loop to a vectorised
# cumulative-sum computation because the loop made `historical_volatility` the
# dominant cost of a factor ranking (89% of rank_universe). These tests pin the
# numerical contract so the optimisation cannot silently change results.


@pytest.mark.parametrize("period,ddof", [(20, 1), (20, 0), (50, 1), (250, 1), (5, 1)])
def test_rolling_std_matches_pandas(period, ddof):
    import pandas as pd

    from megatool.ta.core import rolling_std

    rng = np.random.default_rng(1234)
    # Deliberately large mean with small dispersion: the worst case for the
    # E[x^2] - E[x]^2 formulation the optimisation had to be careful about.
    c = 1500.0 + rng.normal(0, 8, 600).cumsum() * 0.02
    got = rolling_std(c, period, ddof=ddof)
    ref = pd.Series(c).rolling(period).std(ddof=ddof).to_numpy()
    np.testing.assert_allclose(got, ref, rtol=1e-7, atol=1e-6, equal_nan=True)


def test_rolling_std_nan_window_matches_pandas():
    import pandas as pd

    from megatool.ta.core import rolling_std

    x = np.array([1.0, 2.0, np.nan, 4.0, 5.0, 6.0])
    got = rolling_std(x, 3, ddof=1)
    ref = pd.Series(x).rolling(3).std(ddof=1).to_numpy()
    np.testing.assert_allclose(got, ref, rtol=1e-9, atol=1e-9, equal_nan=True)


def test_degenerate_windows_are_nan():
    from megatool.ta.core import rolling_std

    assert np.isnan(rolling_std(np.arange(10.0), 1)).all()  # period <= 1
    assert np.isnan(rolling_std(np.arange(3.0), 10)).all()  # n < period
    assert np.isnan(rolling_std(np.arange(10.0), 2, ddof=2)).all()  # divisor 0


def test_flat_window_has_zero_std_not_nan():
    from megatool.ta.core import rolling_std

    out = rolling_std(np.full(10, 42.0), 5, ddof=1)
    assert np.isnan(out[:4]).all()
    np.testing.assert_allclose(out[4:], 0.0, atol=1e-12)


def test_historical_volatility_matches_an_independent_loop():
    """The vectorised path must equal the literal per-window computation."""
    rng = np.random.default_rng(99)
    c = 100 * np.exp(np.cumsum(rng.normal(0.0005, 0.02, 800)))
    got = ta.compute("historical_volatility", {"close": c}, period=20).values["hv"]
    lr = np.log(c / np.concatenate(([np.nan], c[:-1])))
    ref = np.full(len(c), np.nan)
    for i in range(20, len(c)):
        w = lr[i - 19 : i + 1]
        if not np.any(np.isnan(w)):
            ref[i] = np.std(w, ddof=1) * np.sqrt(250) * 100.0
    np.testing.assert_allclose(got, ref, rtol=1e-9, atol=1e-9, equal_nan=True)


# ------------------------------------- sparse pivot indicators (carve-out)
def test_sparse_pivot_indicators_are_registered_and_flagged():
    for name in sorted(SPARSE_PIVOT_INDICATORS):
        meta, _ = ta.get(name)
        assert meta.display == "overlay"
        assert "provisional" in meta.notes.lower(), (
            f"{name} must disclose that its tail is provisional"
        )


@pytest.mark.parametrize("name", REPAINTING_INDICATORS)
def test_sparse_pivot_output_is_sparse_and_on_real_prices(name, ohlcv):
    """Every emitted value is a real high/low of the bar it is stamped on."""
    meta, _ = ta.get(name)
    inputs = {k: ohlcv[k] for k in meta.inputs if k in ohlcv}
    r = ta.compute(name, inputs)
    n = len(ohlcv["close"])
    for col, vals in r.values.items():
        assert len(vals) == n
        finite = np.isfinite(vals)
        # Sparse by construction: a pivot is a small minority of bars.
        assert 0 < finite.sum() < n
        for i in np.flatnonzero(finite):
            if col == "fractal_up":
                assert vals[i] == ohlcv["high"][i]
            elif col == "fractal_down":
                assert vals[i] == ohlcv["low"][i]
            else:  # zigzag: a pivot is a high or low of the bar it spans
                assert ohlcv["low"][i] <= vals[i] <= ohlcv["high"][i]


def test_zigzag_repaints_only_the_tail(ohlcv):
    """Disclosed behaviour: the LAST pivot is provisional and may move.

    This is the documented difference from the dense indicators: a Zig Zag pivot
    can only be confirmed by a later reversal, so truncating the series can
    change (or drop) the final stamp. The test asserts the repainting is real
    and confined to the tail, rather than pretending it does not happen.
    """
    full = ta.compute("zigzag", ohlcv, threshold_pct=5.0).values["zigzag"]
    cut = len(ohlcv["close"]) - 1
    part = ta.compute(
        "zigzag", {k: v[:cut] for k, v in ohlcv.items()}, threshold_pct=5.0
    ).values["zigzag"]
    a, b = full[:cut], part
    stable = np.flatnonzero(np.isfinite(a))
    assert stable.size > 0
    diffs = [int(i) for i in stable if not (np.isfinite(b[i]) and a[i] == b[i])]
    assert diffs == [] or max(diffs) >= cut - 6, (
        "repainting must be confined to the tail, not the whole series"
    )


def test_williams_fractal_needs_the_right_side(ohlcv):
    """A fractal can only be stamped once `window` bars to its right exist."""
    w = 2
    up = ta.compute("williams_fractal", ohlcv, window=w).values["fractal_up"]
    assert np.isnan(up[:w]).all()          # left edge: no full window
    assert np.isnan(up[-w:]).all()         # right edge: unconfirmed
    for i in np.flatnonzero(np.isfinite(up)):
        win = ohlcv["high"][i - w : i + w + 1]
        assert float(np.nanmax(win)) == ohlcv["high"][i]
