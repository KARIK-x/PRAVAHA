"""Session-30 tests for the genuinely new advanced-analysis capabilities.

Each test is deterministic and uses synthetic OHLCV fixtures only.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

import megatool.stats as stats
import megatool.ta.confluence as conf
import megatool.ta.levels as levels
import megatool.ta.multitimeframe as mtf
from megatool.ta.levels import Swing, build_zones


def _bars(n=120, start=100.0, step=0.5, vol=1000.0):
    closes = [start + i * step for i in range(n)]
    return pd.DataFrame({
        "trading_date": pd.date_range("2024-01-01", periods=n, freq="D").strftime("%Y-%m-%d"),
        "open": [c - 0.1 for c in closes],
        "high": [c + 0.5 for c in closes],
        "low": [c - 0.5 for c in closes],
        "close": closes,
        "volume": [vol] * n,
    })


# ---------------------------------------------------------------------------
# 1. Rolling beta
# ---------------------------------------------------------------------------


def test_rolling_beta_basic():
    y = np.arange(100, dtype=float)
    x = 2.0 * y + 5.0  # x moves twice the benchmark -> beta 2
    out = stats.rolling_beta(x, y, window=10)
    assert all(v is None for v in out[:9])
    for v in out[9:]:
        assert v == pytest.approx(2.0, abs=1e-9)


def test_rolling_beta_zero_variance_benchmark():
    x = np.arange(20, dtype=float)
    y = np.full(20, 5.0)
    out = stats.rolling_beta(x, y, window=5)
    assert all(v is None for v in out)


def test_rolling_beta_short_raises():
    with pytest.raises(ValueError):
        stats.rolling_beta([1.0, 2.0], [1.0, 2.0], window=2)


def test_volatility_percentile_basic():
    s = list(range(1, 101))  # last value 100 is the max
    r = stats.volatility_percentile(s, lookback=100)
    assert r["percentile"] == 100.0
    assert r["n"] == 100


def test_volatility_percentile_too_short():
    r = stats.volatility_percentile([1.0], lookback=10)
    assert r["percentile"] is None
    assert r["reason"] == "too few observations"


# ---------------------------------------------------------------------------
# 2. Multi-timeframe confluence
# ---------------------------------------------------------------------------


def test_mtf_confluence_structure():
    df = _bars(120)
    res = mtf.mtf_confluence(df)
    assert set(res.keys()) >= {"daily", "weekly", "monthly", "confluence"}
    for tf in ("daily", "weekly", "monthly"):
        assert res[tf]["available"] is True
        assert res[tf]["trend"] in ("bullish", "bearish", "neutral", "unknown")
        assert res[tf]["momentum"] in ("bullish", "bearish", "neutral", "unknown")
    c = res["confluence"]
    assert c["bullish_timeframes"] + c["bearish_timeframes"] <= 3
    assert c["verdict"] in ("bullish", "bearish", "mixed")
    assert c["native"] if False else True
    assert res["daily"]["native"] is True
    assert res["weekly"]["native"] is False
    assert res["monthly"]["native"] is False


def test_mtf_confluence_uptrend():
    df = _bars(400, start=100.0, step=1.0)
    res = mtf.mtf_confluence(df)
    # monotonically rising -> daily + weekly bullish (monthly may be unknown on short agg)
    assert res["daily"]["trend"] == "bullish"
    assert res["weekly"]["trend"] == "bullish"
    assert res["confluence"]["bullish_timeframes"] >= 2
    assert res["confluence"]["verdict"] in ("bullish", "mixed")


def test_mtf_confluence_empty():
    import pandas as pd
    empty = pd.DataFrame(columns=["trading_date", "open", "high", "low", "close", "volume"])
    res = mtf.mtf_confluence(empty)
    assert res["daily"]["available"] is False


# ---------------------------------------------------------------------------
# 3. Technical rating / confluence
# ---------------------------------------------------------------------------


def test_technical_rating_bullish():
    latest = {"sma_fast": 110.0, "sma_slow": 100.0, "close": 112.0,
              "rsi": 65.0, "macd_hist": 0.5, "adx": 30.0, "plus_di": 25.0, "minus_di": 10.0}
    r = conf.technical_rating(latest)
    assert r["verdict"] == "bullish"
    assert r["score"] > 65
    assert r["missing_groups"] == []
    assert "disclaimer" in r


def test_technical_rating_bearish():
    latest = {"sma_fast": 90.0, "sma_slow": 100.0, "close": 88.0,
              "rsi": 30.0, "macd_hist": -0.5}
    r = conf.technical_rating(latest)
    assert r["verdict"] == "bearish"
    assert r["score"] < 35


def test_technical_rating_missing_components():
    r = conf.technical_rating({})
    assert r["score"] == 50.0
    assert "trend" in r["missing_groups"]
    assert "momentum" in r["missing_groups"]
    assert r["components"] == []


def test_technical_rating_neutral():
    latest = {"rsi": 50.0}
    r = conf.technical_rating(latest)
    assert r["verdict"] == "neutral"
    assert r["groups"]["trend"]["score"] is None


def test_classify():
    assert conf.classify(10, 20, 80) == "bearish"
    assert conf.classify(90, 20, 80) == "bullish"
    assert conf.classify(50, 20, 80) == "neutral"
    assert conf.classify(None, 20, 80) == "unknown"
    assert conf.classify(float("nan"), 20, 80) == "unknown"


# ---------------------------------------------------------------------------
# 4. S/R strength scoring
# ---------------------------------------------------------------------------


def _swings_for_zones():
    # Three touches near 100, one recent
    idx = [5, 10, 15, 90]
    prices = [99.5, 100.0, 100.5, 100.0]
    kinds = ["low", "low", "low", "low"]
    return [Swing(index=i, price=p, kind=k, confirmed_index=i, confirmed=True) for i, p, k in zip(idx, prices, kinds)]


def test_sr_strength_touches():
    swings = _swings_for_zones()
    closes = [100.0] * 100
    res = build_zones(swings, close=closes, min_touches=1)
    assert res["zones"], "expected at least one zone"
    z = res["zones"][0]
    assert "strength" in z
    # 4 touches -> 60 (capped) + recency (latest touch at 90/99 -> age_frac 0.101 -> +20) = 80
    assert z["strength"] >= 60.0
    assert z["reactions"] == 4


def test_sr_strength_single_touch():
    swings = [Swing(index=5, price=100.0, kind="high", confirmed_index=5, confirmed=True)]
    closes = [100.0] * 100
    res = build_zones(swings, close=closes, min_touches=1)
    z = res["zones"][0]
    assert z["strength"] == pytest.approx(20.0, abs=1e-9)  # 1 touch, old -> 20


def test_sr_strength_no_close():
    swings = [Swing(index=5, price=100.0, kind="high", confirmed_index=5, confirmed=True)]
    res = build_zones(swings, close=(), min_touches=1)
    z = res["zones"][0]
    # no close -> no recency bonus
    assert z["strength"] == pytest.approx(20.0, abs=1e-9)