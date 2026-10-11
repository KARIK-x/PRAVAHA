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
    out[n] = 100.0 - 100.0 / (1.0 + ag / al)
    for i in range(n + 1, len(c)):
        ag = (ag * (n - 1) + gains[i - 1]) / n
        al = (al * (n - 1) + losses[i - 1]) / n
        out[i] = 100.0 if al == 0 else 100.0 - 100.0 / (1.0 + ag / al)
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


# ------------------------------------------------------------------ causality
ALL_INDICATORS = [m["name"] for m in ta.available()]


@pytest.mark.parametrize("name", ALL_INDICATORS)
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


@pytest.mark.parametrize("name", ALL_INDICATORS)
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


@pytest.mark.parametrize("name", ALL_INDICATORS)
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
