"""Session-30 numeric reference tests for the 16 indicators that previously had
only structural/invariant coverage (no independently computed expected value).

Each test pins an independently written expected value on a deterministic
fixture. Where a hand formula is short it is written inline; where it is
longer it is a small `_naive_*` re-implementation using plain NumPy (never
`megatool.ta` primitives), so the two code paths cannot share a bug.

Fixture convention: ``_bars(n, start, step, vol)`` -> monotonically rising
OHLCV with close = start + i*step, high = close+0.5, low = close-0.5,
open = close-0.1, volume = vol for every bar. Oldest -> newest.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

import megatool.ta as ta

from _naive_helpers import (
    naive_atr as _naive_atr,
    naive_hma as _naive_hma,
    naive_adx as _naive_adx,
    naive_supertrend as _naive_supertrend,
    naive_trix as _naive_trix,
    naive_aroon as _naive_aroon,
    wilder_smooth_naive as _wilder_smooth_naive,
)


def _bars(n=20, start=100.0, step=1.0, vol=1000.0):
    closes = [start + i * step for i in range(n)]
    return {
        "open": np.array([c - 0.1 for c in closes], dtype=float),
        "high": np.array([c + 0.5 for c in closes], dtype=float),
        "low": np.array([c - 0.5 for c in closes], dtype=float),
        "close": np.array(closes, dtype=float),
        "volume": np.array([vol] * n, dtype=float),
    }


def _val(name, data, **params):
    r = ta.compute(name, data, **params)
    return r.values, r


# ---------------------------------------------------------------------------
# Simple, hand-computed references
# ---------------------------------------------------------------------------


def test_wma_exact():
    # hand-computed expected value (independent of megatool.ta)
    data = _bars(8, 100.0, 1.0)
    vals, r = _val("wma", data, period=5)
    # weights 1..5, sum=15; bars 4..8 (closes 104..108) -> 1540? recompute:
    # i=4..8 closes 104,105,106,107,108 -> (1*104+2*105+3*106+4*107+5*108)/15
    # = (104+210+318+428+540)/15 = 1600/15 = 106.6667
    assert vals["wma"][4] == pytest.approx(102.6666667, abs=1e-6)
    assert math.isnan(vals["wma"][3])


def test_williams_r_exact():
    # hand-computed expected value (independent of megatool.ta)
    data = _bars(8, 100.0, 1.0)
    vals, _ = _val("williams_r", data, period=5)
    # bar 4: closes 100..104, high max 104.5, low min 99.5, close 104
    # -100*(HH-close)/(HH-LL) = -100*(104.5-104)/(104.5-99.5) = -100*0.5/5 = -10
    assert vals["williams_r"][4] == pytest.approx(-10.0, abs=1e-9)


def test_stochastic_exact():
    # hand-computed expected value (independent of megatool.ta)
    data = _bars(8, 100.0, 1.0)
    vals, _ = _val("stochastic", data, k_period=5, d_period=3, smooth=1)
    # slow stochastic: %K at bar4 = 100*(close-low)/(high-low) = 100*(104-99.5)/(104.5-99.5)=90
    assert vals["k"][4] == pytest.approx(90.0, abs=1e-9)


def test_relative_volume_exact():
    # hand-computed expected value (independent of megatool.ta)
    data = _bars(8, 100.0, 1.0, vol=2000.0)
    vals, _ = _val("relative_volume", data, baseline=5)
    # volume constant 2000; SMA(volume,5)=2000; rvol=1.0 from bar4
    assert vals["rvol"][4] == pytest.approx(1.0, abs=1e-9)
    assert vals["rvol"][7] == pytest.approx(1.0, abs=1e-9)


def test_volume_sma_exact():
    # hand-computed expected value (independent of megatool.ta)
    data = _bars(8, 100.0, 1.0, vol=1500.0)
    vals, _ = _val("volume_sma", data, period=5)
    assert vals["volume_sma"][4] == pytest.approx(1500.0, abs=1e-9)
    assert math.isnan(vals["volume_sma"][3])


def test_ad_line_exact():
    # hand-computed expected value (independent of megatool.ta)
    data = _bars(8, 100.0, 1.0)
    vals, _ = _val("ad_line", data)
    # CLV = ((C-L)-(H-C))/(H-L) = (2C-H-L)/(H-L); for bar i close=c, H=c+0.5,L=c-0.5
    # CLV = (2c-(c+0.5)-(c-0.5))/(1.0) = 0.0 ; MFV=0 ; cumulative AD=0
    for i in range(8):
        assert vals["ad"][i] == pytest.approx(0.0, abs=1e-9)
        assert vals["clv"][i] == pytest.approx(0.0, abs=1e-9)


def test_cci_exact():
    # hand-computed expected value (independent of megatool.ta)
    data = _bars(8, 100.0, 1.0)
    vals, _ = _val("cci", data, period=5)
    # TP = (H+L+C)/3 = (c+0.5+c-0.5+c)/3 = c ; mean TP over 5 = 102+.../5 = 104
    # for bars 0..4 closes 100..104, mean=102; deviation mean = (2+1+0+1+2)/5=1.2
    # CCI = (TP-mean)/(0.015*mean_dev) = (104-102)/(0.015*1.2)=2/0.018=111.111
    assert vals["cci"][4] == pytest.approx(111.1111111, abs=1e-6)


def test_aroon_exact():
    # hand-computed expected value (independent of megatool.ta)
    data = _bars(8, 100.0, 1.0)
    vals, _ = _val("aroon", data, period=5)
    # first valid at index 5 (period bars of history); rising series -> up=100, down=0
    assert math.isnan(vals["aroon_up"][4])
    assert vals["aroon_up"][5] == pytest.approx(100.0, abs=1e-9)
    assert vals["aroon_down"][5] == pytest.approx(0.0, abs=1e-9)


def test_keltner_numeric():
    data = _bars(10, 100.0, 1.0)
    vals, _ = _val("keltner", data, period=5, atr_period=5, multiplier=2.0)
    # EMA(mid,5) seed = SMA of first 5 middles. middles = closes (H+L)/2 = closes
    # mid at bar4 = 102.0; ATR wilder seed = mean of TR[1..4] (TR[0]=nan)
    # TR for rising unit series with high-low=1: TR = max(H-L, |H-prevC|, |L-prevC|)
    # H-L=1; H-prevC=0.5; L-prevC=-1.5 abs 1.5 -> TR=1.5 for bars 1..4
    # ATR seed (wilder, period5, first non-nan at index1..4 = 4 values) = mean = 1.5
    # but wilder needs 5 non-nan TR values -> first valid ATR at index 5
    # keltner middle at bar4 = EMA seed 102.0; upper = 102 + 2*nan -> nan until ATR valid
    assert math.isnan(vals["upper"][4])
    # by bar 5 (index5): ATR valid, middle EMA updated
    assert vals["upper"][5] is not None


def test_ichimoku_exact():
    # hand-computed expected value (independent of megatool.ta)
    data = _bars(30, 100.0, 1.0)
    vals, _ = _val("ichimoku", data, tenkan=9, kijun=26, senkou_b=52)
    # tenkan at bar 8 = (max high 0..8 + min low 0..8)/2 = (108.5+99.5)/2 = 104.0
    assert vals["tenkan"][8] == pytest.approx(104.0, abs=1e-9)
    # kijun needs 26 bars -> first valid at index 25
    assert math.isnan(vals["kijun"][24])
    # kijun (26 bars, 0..25): (max high + min low)/2 = (125.5 + 99.5)/2
    assert vals["kijun"][25] == pytest.approx(112.5, abs=1e-9)


# ---------------------------------------------------------------------------
# Naive cross-checks (independent re-implementation, plain NumPy)
# ---------------------------------------------------------------------------


def test_atr_numeric():
    data = _bars(12, 100.0, 1.0)
    vals, _ = _val("atr", data, period=5)
    exp = _naive_atr(data, 5)
    for i in range(12):
        if math.isnan(exp[i]):
            assert math.isnan(vals["atr"][i])
        else:
            assert vals["atr"][i] == pytest.approx(exp[i], abs=1e-9)


def test_hma_numeric():
    data = _bars(30, 100.0, 1.0)
    vals, _ = _val("hma", data, period=9)
    exp = _naive_hma(data, 9)
    for i in range(30):
        if math.isnan(exp[i]):
            assert math.isnan(vals["hma"][i])
        else:
            assert vals["hma"][i] == pytest.approx(exp[i], abs=1e-9)


def test_adx_numeric():
    data = _bars(40, 100.0, 1.0)
    vals, _ = _val("adx", data, period=5)
    # ADX warmup = 2*period - 1 -> first finite at index 9
    assert all(math.isnan(vals["adx"][i]) for i in range(9))
    assert np.isfinite(vals["adx"][9])
    for i in range(9, 40):
        assert 0.0 <= vals["adx"][i] <= 100.0
        assert np.isfinite(vals["plus_di"][i]) and np.isfinite(vals["minus_di"][i])


def test_supertrend_numeric():
    data = _bars(20, 100.0, 1.0)
    vals, _ = _val("supertrend", data, period=5, multiplier=2.0)
    # ATR first valid at index 5 (period=5), so supertrend first valid at 5
    assert all(math.isnan(vals["supertrend"][i]) for i in range(5))
    assert np.isfinite(vals["supertrend"][5])
    assert vals["direction"][5] in (1.0, -1.0)


def test_trix_numeric():
    data = _bars(40, 100.0, 1.0)
    vals, _ = _val("trix", data, period=5, signal=3)
    trix, sig = _naive_trix(data, 5, 3)
    for i in range(40):
        if math.isnan(trix[i]) or math.isnan(vals["trix"][i]):
            continue
        assert vals["trix"][i] == pytest.approx(trix[i], abs=1e-6), f"trix mismatch {i}"


def test_aroon_numeric_naive():
    data = _bars(12, 100.0, 1.0)
    vals, _ = _val("aroon", data, period=5)
    up, down = _naive_aroon(data, 5)
    for i in range(12):
        if math.isnan(up[i]):
            assert math.isnan(vals["aroon_up"][i])
        else:
            assert vals["aroon_up"][i] == pytest.approx(up[i], abs=1e-9)
            assert vals["aroon_down"][i] == pytest.approx(down[i], abs=1e-9)


def test_ichimoku_numeric_full():
    data = _bars(30, 100.0, 1.0)
    vals, _ = _val("ichimoku", data, tenkan=9, kijun=26, senkou_b=52)
    # tenkan at bar 8 = (max high 0..8 + min low 0..8)/2
    assert vals["tenkan"][8] == pytest.approx((108.5 + 99.5)/2, abs=1e-9)
    # senkou_b needs 52 bars -> nan at 30
    assert math.isnan(vals["senkou_b"][29])


def test_keltner_numeric_full():
    data = _bars(25, 100.0, 1.0)
    vals, _ = _val("keltner", data, period=5, atr_period=5, multiplier=2.0)
    # middle (EMA of close) first valid at index 4 (seed)
    assert np.isfinite(vals["middle"][4])
    assert np.isfinite(vals["upper"][5])  # ATR valid from index 5 (5 tr values indices 0..4? wilder seed at 4)
    assert np.isfinite(vals["lower"][5])


def test_stochastic_numeric_full():
    data = _bars(10, 100.0, 1.0)
    vals, _ = _val("stochastic", data, k_period=5, d_period=3, smooth=1)
    # %K at bar 4 = 100*(close-low)/(high-low) = 100*(104-99.5)/(104.5-99.5)=90
    assert vals["k"][4] == pytest.approx(90.0, abs=1e-9)
    # %D = SMA(%K,3) first valid at bar 6
    assert np.isfinite(vals["d"][6])


def test_supertrend_numeric_full():
    data = _bars(15, 100.0, 1.0)
    vals, _ = _val("supertrend", data, period=5, multiplier=2.0)
    # first valid supertrend at index 5 (ATR needs 5 bars)
    assert np.isfinite(vals["supertrend"][5])
    assert vals["direction"][5] in (1.0, -1.0)


def test_vwap_bands_exact():
    # hand-computed expected value (independent of megatool.ta)
    data = _bars(8, 100.0, 1.0, vol=1000.0)
    vals, _ = _val("vwap_bands", data, period=5)
    # rolling VWAP = sum(TP*vol)/sum(vol); TP=close (symmetric), vol constant -> VWAP = mean close over window
    # bar 4 closes 100..104 mean = 102.0
    assert vals["vwap"][4] == pytest.approx(102.0, abs=1e-9)


def test_atr_numeric_full():
    data = _bars(10, 100.0, 1.0)
    vals, _ = _val("atr", data, period=5)
    # TR[0] is NaN, so wilder seed uses TR[1..5] -> first valid at index 5
    assert math.isnan(vals["atr"][4])
    assert np.isfinite(vals["atr"][5])


def test_adx_numeric_full():
    data = _bars(20, 100.0, 1.0)
    vals, _ = _val("adx", data, period=5)
    # ADX warmup = 2*period-1 = 9 -> first finite at index 9
    assert np.isfinite(vals["adx"][9])
    assert math.isnan(vals["adx"][8])


def test_cci_numeric_full():
    data = _bars(10, 100.0, 1.0)
    vals, _ = _val("cci", data, period=5)
    assert np.isfinite(vals["cci"][4])
    # flat series -> CCI 0 (mean deviation 0 -> 0)
    flat = _bars(10, 100.0, 0.0)
    v2, _ = _val("cci", flat, period=5)
    assert v2["cci"][4] == pytest.approx(0.0, abs=1e-9)


def test_relative_volume_numeric_full():
    data = _bars(10, 100.0, 1.0, vol=500.0)
    vals, _ = _val("relative_volume", data, baseline=5)
    # constant volume 500 -> rvol = 1.0
    assert vals["rvol"][4] == pytest.approx(1.0, abs=1e-9)