"""Unit tests for :mod:`megatool.ta.summary`.

Every series in this file is a ``# SYNTHETIC FIXTURE`` built by the helpers
below: nothing is read from or written to any database, and no network is
used.  Expected values are either hand-computed inside the test or produced
by an independent reference implementation written here, never by calling the
code under test twice.
"""

from __future__ import annotations

import json
import math
from dataclasses import asdict

import numpy as np
import pytest

from megatool.ta import momentum
from megatool.ta.summary import (
    MIN_BARS,
    SUMMARY_RULE_VERSION,
    SummaryError,
    SummaryParams,
    SummaryResult,
    build_summary,
    candidate_divergence,
)
from megatool.ta.swings import Swing, find_swings


# ------------------------------------------------------------------ fixtures
# SYNTHETIC FIXTURE: OHLC wrapper guaranteeing valid, strictly positive bars.
def _ohlc(closes):
    c = np.asarray(closes, dtype=float)
    o = c - 0.2
    h = c + 0.5
    lo = np.minimum(o, c) - 0.3
    return o, h, lo, c


# SYNTHETIC FIXTURE: strictly rising ramp (monotone, no swings).
def _ramp(n=130, start=100.0, step=1.0):
    return start + step * np.arange(n, dtype=float)


# SYNTHETIC FIXTURE: flat series (every bar has zero range).
def _const(n=40, price=50.0):
    return np.full(n, price, dtype=float)


# SYNTHETIC FIXTURE: two swing highs and two swing lows -> structure "up",
# with a slow second rally so RSI makes a lower high (bearish candidate).
def _zigzag():
    closes = (
        list(np.linspace(100, 140, 15))[1:]
        + list(np.linspace(140, 128, 8))[1:]
        + list(np.linspace(128, 145, 30))[1:]
        + list(np.linspace(145, 136, 8))[1:]
        + list(np.linspace(136, 139, 6))[1:]
    )
    return _ohlc(closes)


# SYNTHETIC FIXTURE: long decline, then a late rally, so the short horizon is
# up while the intermediate horizon is still down.
def _mixed_horizons():
    return _ohlc(np.concatenate([np.linspace(300, 150, 60), np.linspace(150, 175, 15)[1:]]))


# Small windows keep warm-up short; documented defaults are overridden here.
_FAST = {
    "swing_left": 3,
    "swing_right": 3,
    "trend_short": 10,
    "trend_intermediate": 20,
    "trend_long": 40,
    "sma_short": 5,
    "sma_long": 10,
    "slope_window": 10,
    "adx_period": 7,
    "hv_period": 10,
    "bollinger_period": 10,
    "return_window": 10,
    "rvol_baseline": 10,
    "rsi_period": 7,
    "roc_period": 5,
    "stoch_k": 5,
    "mfi_period": 5,
    "macd_fast": 5,
    "macd_slow": 10,
    "macd_signal": 5,
}


def _naive_rsi(closes, period):
    """Independent Wilder RSI: simple seed mean, then Wilder recursion."""
    closes = list(closes)
    n = len(closes)
    out = [None] * n
    if n < period + 1:
        return out
    deltas = [closes[i] - closes[i - 1] for i in range(1, n)]
    gains = [max(d, 0.0) for d in deltas]
    losses = [max(-d, 0.0) for d in deltas]
    ag = sum(gains[:period]) / period
    al = sum(losses[:period]) / period
    avgs = [None] * n
    avgs[period] = (ag, al)
    alpha = 1.0 / period
    for i in range(period + 1, n):
        ag = avgs[i - 1][0] * (1 - alpha) + gains[i - 1] * alpha
        al = avgs[i - 1][1] * (1 - alpha) + losses[i - 1] * alpha
        avgs[i] = (ag, al)
    for i in range(period, n):
        ag, al = avgs[i]
        if al == 0:
            out[i] = 100.0
        elif ag == 0:
            out[i] = 0.0
        else:
            out[i] = 100.0 - 100.0 / (1.0 + ag / al)
    return out


def _naive_mfi(high, low, close, volume, period):
    """Independent Money Flow Index over the trailing window."""
    tp = [(high[i] + low[i] + close[i]) / 3.0 for i in range(len(close))]
    mf = [tp[i] * volume[i] for i in range(len(close))]
    pos = [0.0] * len(close)
    neg = [0.0] * len(close)
    for i in range(1, len(close)):
        if tp[i] > tp[i - 1]:
            pos[i] = mf[i]
        elif tp[i] < tp[i - 1]:
            neg[i] = mf[i]
    p = sum(pos[-period:])
    ng = sum(neg[-period:])
    if ng == 0:
        # No negative flow: 100 is right only when there IS positive flow.
        # Both zero means no money flow at all, so the ratio is 0/0 -- undefined.
        return 100.0 if p > 0 else float("nan")
    return 100.0 - 100.0 / (1.0 + p / ng)


def _naive_stdev(values):
    """Independent sample standard deviation (ddof=1)."""
    n = len(values)
    mean = sum(values) / n
    return math.sqrt(sum((v - mean) ** 2 for v in values) / (n - 1))


# ------------------------------------------------------------------ validation
def test_error_is_value_error():
    assert issubclass(SummaryError, ValueError)
    with pytest.raises(SummaryError):
        build_summary([1.0], [1.0], [1.0], [1.0])


@pytest.mark.parametrize(
    "case",
    [
        "length_mismatch",
        "nan_input",
        "high_below_low",
        "single_bar",
        "nonpositive_low",
        "negative_volume",
        "volume_length",
        "dates_length",
    ],
)
def test_invalid_inputs_raise_summary_error(case):
    good = [100.0, 101.0, 102.0]
    calls = {
        "length_mismatch": lambda: build_summary(good, [100.0], good, good),
        "nan_input": lambda: build_summary([100.0, float("nan"), 102.0], good, good, good),
        "high_below_low": lambda: build_summary(good, [99.0, 99.0, 99.0], good, good),
        "single_bar": lambda: build_summary([100.0], [101.0], [99.0], [100.0]),
        "nonpositive_low": lambda: build_summary(good, good, [0.0, -1.0, 1.0], good),
        "negative_volume": lambda: build_summary(good, good, good, good, [1.0, -1.0, 1.0]),
        "volume_length": lambda: build_summary(good, good, good, good, [1.0, 2.0]),
        "dates_length": lambda: build_summary(good, good, good, good, None, ["a"]),
    }
    with pytest.raises(SummaryError):
        calls[case]()


def test_minimum_bars_matches_constant():
    assert MIN_BARS == 2
    with pytest.raises(SummaryError, match="insufficient history"):
        build_summary([100.0], [101.0], [99.0], [100.0])


@pytest.mark.parametrize(
    "kwargs",
    [
        {"macd_fast": 26, "macd_slow": 12},
        {"flat_threshold_pct": -1.0},
        {"flat_threshold_pct": "x"},
        {"adx_developing": 30.0, "adx_strong": 25.0},
        {"rsi_overbought": 20.0, "rsi_oversold": 80.0},
        {"bollinger_deviation": -1.0},
        {"timeframe": ""},
        {"rsi_period": 0},
    ],
)
def test_invalid_params_raise_summary_error(kwargs):
    with pytest.raises(SummaryError):
        SummaryParams(**kwargs)


def test_params_type_and_unknown_keys_rejected():
    with pytest.raises(SummaryError, match="params must be"):
        build_summary(*_ohlc(_ramp(30)), params=5)
    with pytest.raises(SummaryError, match="unknown parameter"):
        build_summary(*_ohlc(_ramp(30)), params={"definitely_not_a_param": 1})


def test_dict_params_merge_with_defaults():
    p = SummaryParams(**{**asdict(SummaryParams()), "trend_short": 5})
    assert p.trend_short == 5
    assert p.trend_intermediate == 60 and p.rsi_period == 14
    closes = _ramp(80)
    r = build_summary(*_ohlc(closes), params={"trend_short": 5})
    expected = (closes[-1] - closes[-6]) / closes[-6] * 100.0
    assert r.trend.short_change_pct == pytest.approx(expected)
    assert r.trend.intermediate_change_pct is not None  # default window kept


# ------------------------------------------------------------------ contract
def test_deterministic_output():
    a = build_summary(*_zigzag(), params=_FAST).to_dict()
    b = build_summary(*_zigzag(), params=_FAST).to_dict()
    assert a == b


def test_to_dict_is_json_clean_and_has_no_nan():
    payload = build_summary(*_zigzag(), params=_FAST).to_dict()
    text = json.dumps(payload, allow_nan=False)  # raises if any NaN/inf survived

    def walk(node):
        if isinstance(node, dict):
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)
        else:
            assert not isinstance(node, float) or math.isfinite(node)

    walk(payload)
    assert "null" in text  # warm-up Nones are present but never NaN


def test_output_never_contains_recommendation_tokens():
    r = build_summary(*_zigzag(), params=_FAST)
    payload = json.dumps(r.to_dict()).lower()
    for token in ("buy", "sell", "confidence"):
        assert token not in payload, token
    assert "no trading recommendation" in r.interpretation.disclaimer


def test_labels_and_metadata():
    r = build_summary(*_zigzag(), params={**_FAST, "timeframe": "1d"})
    assert isinstance(r, SummaryResult)
    assert r.rule_version == SUMMARY_RULE_VERSION == "summary-1.0"
    assert r.timeframe == "1d"
    assert r.last_index == len(_zigzag()[3]) - 1
    assert r.generated_from.startswith("ohlc(")
    assert r.trend.label == r.momentum.label == r.volatility.label == "CALCULATED"
    assert r.volume_stats.label == "CALCULATED"
    assert r.structure.label == "DETECTED"
    assert r.interpretation.label == "INTERPRETIVE"


def test_timestamp_echoes_last_date_only():
    o, h, lo, c = _ohlc(_ramp(30))
    dates = [f"2024-01-{i + 1:02d}" for i in range(30)]
    r = build_summary(o, h, lo, c, dates=dates, params=_FAST)
    assert r.last_time == dates[-1]
    assert build_summary(o, h, lo, c, params=_FAST).last_time is None


# ------------------------------------------------------------------ trend
def test_net_change_and_direction_up_defaults():
    closes = _ramp(130, start=100.0, step=1.0)  # defaults: 20/60/120 windows
    r = build_summary(*_ohlc(closes))
    expected = (closes[-1] - closes[-1 - 60]) / closes[-1 - 60] * 100.0
    assert r.trend.intermediate_change_pct == pytest.approx(expected)
    assert r.trend.intermediate_direction == "up"
    expected = (closes[-1] - closes[-1 - 20]) / closes[-1 - 20] * 100.0
    assert r.trend.short_change_pct == pytest.approx(expected)
    assert r.trend.short_direction == "up"
    assert r.trend.long_change_pct is not None  # 130 bars > 120-bar window
    assert r.trend.long_direction == "up"
    assert r.interpretation.trend_direction == r.trend.intermediate_direction


def test_flat_threshold_boundary_is_strict():
    closes = np.array([1.0, 1.1, 1.2, 1.3, 1.5])  # exactly +50.0%
    o, h, lo, c = _ohlc(closes)
    fast = {
        **_FAST,
        "trend_short": 4,
        "trend_intermediate": 4,
        "trend_long": 4,
        "sma_short": 3,
        "sma_long": 4,
        "slope_window": 3,
    }
    on_tie = build_summary(o, h, lo, c, params={**fast, "flat_threshold_pct": 50.0})
    assert on_tie.trend.short_change_pct == pytest.approx(50.0)
    assert on_tie.trend.short_direction == "flat"  # a tie is not "up"
    below = build_summary(o, h, lo, c, params={**fast, "flat_threshold_pct": 49.9})
    assert below.trend.short_direction == "up"


def test_down_direction_and_constant_series_are_flat():
    down = build_summary(*_ohlc(_ramp(130, start=200.0, step=-1.0)))
    assert down.trend.intermediate_direction == "down"
    assert down.trend.intermediate_change_pct < 0

    flat = build_summary(*_ohlc(_const(130, 50.0)))
    assert flat.trend.short_change_pct == 0.0
    assert flat.trend.short_direction == "flat"
    assert flat.trend.intermediate_direction == "flat"
    assert flat.trend.long_direction == "flat"
    assert flat.interpretation.trend_direction == "flat"
    assert any(item.startswith("trend: flat") for item in flat.interpretation.ambiguous)


def test_combined_direction_uses_intermediate_horizon():
    params = {**_FAST, "trend_short": 20, "trend_intermediate": 60, "trend_long": 120}
    r = build_summary(*_mixed_horizons(), params=params)
    assert r.trend.short_direction == "up"
    assert r.trend.intermediate_direction == "down"
    assert r.trend.long_direction is None  # 74 bars < 120-bar window
    # The combined reading follows the documented primary (intermediate)
    # horizon, not the short one: the two disagree here on purpose.
    assert r.interpretation.trend_direction == "down"
    assert r.interpretation.trend_direction != r.trend.short_direction


def test_warmup_is_none_not_faked():
    r = build_summary(*_ohlc(_ramp(10)))  # default params, 10 bars
    assert r.trend.short_change_pct is None
    assert r.trend.intermediate_change_pct is None
    assert r.trend.long_change_pct is None
    assert r.trend.status == "insufficient_history"
    assert r.trend.sma_long is None  # needs 30 bars
    assert r.trend.adx is None and r.trend.strength == "not available"
    assert r.momentum.rsi is None and r.momentum.roc_pct is None
    assert r.momentum.macd is None and r.momentum.macd_cross == "not_available"
    assert r.momentum.status == "insufficient_history"
    assert r.volatility.historical_volatility_pct_annual is None
    assert r.volatility.bandwidth_pct is None
    assert r.volatility.regime is None
    assert r.trend.sma_short is not None  # a 10-bar SMA on 10 bars is real


def test_window_boundary_short_horizon():
    for n, expect_none in ((20, True), (21, False)):
        closes = _ramp(n)
        r = build_summary(*_ohlc(closes), params={"trend_short": 20})
        assert (r.trend.short_change_pct is None) is expect_none
        if not expect_none:
            expected = (closes[-1] - closes[0]) / closes[0] * 100.0
            assert r.trend.short_change_pct == pytest.approx(expected)


def test_sma_values_and_linear_slope():
    closes = _ramp(130, start=100.0, step=1.0)
    r = build_summary(*_ohlc(closes))
    sma_short = float(np.mean(closes[-10:]))
    sma_long = float(np.mean(closes[-30:]))
    assert r.trend.sma_short == pytest.approx(sma_short)
    assert r.trend.sma_long == pytest.approx(sma_long)
    assert r.trend.price_vs_sma_short_pct == pytest.approx(
        (closes[-1] - sma_short) / sma_short * 100.0
    )
    # The SMA of a linear series is linear with the same step.
    assert r.trend.sma_slope_per_bar == pytest.approx(1.0, abs=1e-9)


def test_adx_ramp_is_strong_and_constant_is_not_available():
    strong = build_summary(*_ohlc(_ramp(130)))
    assert strong.trend.adx is not None and strong.trend.adx >= 25.0
    assert strong.trend.strength == "strong"
    assert strong.trend.minus_di == 0.0  # no down moves in a ramp

    flat = build_summary(*_ohlc(_const(40, 50.0)))
    assert flat.trend.adx is None
    assert flat.trend.strength == "not available"
    assert any("ADX unavailable" in item for item in flat.limitations)


# ------------------------------------------------------------------ momentum
def test_rsi_matches_independent_reference():
    rng = np.random.default_rng(7)  # deterministic synthetic walk
    closes = 100.0 + np.cumsum(rng.normal(0, 1.0, 60))
    o, h, lo, c = _ohlc(closes)
    r = build_summary(o, h, lo, c, params={"rsi_period": 14})
    expected = _naive_rsi(list(c), 14)[-1]
    assert r.momentum.rsi == pytest.approx(expected, abs=1e-9)
    assert 0.0 <= r.momentum.rsi <= 100.0


def test_constant_close_masks_rsi_quirk():
    r = build_summary(*_ohlc(_const(40, 50.0)), params=_FAST)
    assert r.momentum.rsi is None and r.momentum.rsi_zone is None
    assert r.interpretation.momentum_state == "not_available"
    assert any("RSI masked" in item for item in r.limitations)
    assert any(
        "momentum: RSI constant price series masked" in item for item in r.interpretation.missing
    )


def test_monotone_rise_reports_overbought_zone():
    r = build_summary(*_ohlc(_ramp(60, start=100.0, step=1.0)), params=_FAST)
    assert r.momentum.rsi == pytest.approx(100.0)
    assert r.momentum.rsi_zone == "overbought"
    assert r.interpretation.momentum_state == "overbought"
    assert any("RSI overbought" in item for item in r.interpretation.ambiguous)


def test_roc_and_stochastic_and_macd_identity():
    closes = _ramp(60, start=100.0, step=1.5)
    r = build_summary(*_ohlc(closes), params=_FAST)
    expected_roc = (closes[-1] - closes[-1 - 5]) / closes[-1 - 5] * 100.0
    assert r.momentum.roc_pct == pytest.approx(expected_roc)
    assert r.momentum.stoch_k is not None
    assert 0.0 <= r.momentum.stoch_k <= 100.0
    assert r.momentum.stoch_d is not None
    # The reported histogram is exactly MACD minus its signal line.
    assert r.momentum.macd_histogram == pytest.approx(
        r.momentum.macd - r.momentum.macd_signal, abs=1e-9
    )


def test_macd_cross_label_follows_documented_rule():
    closes = _ramp(60, start=100.0, step=1.5)
    o, h, lo, c = _ohlc(closes)
    r = build_summary(o, h, lo, c, params=_FAST)
    res = momentum.macd(
        {"close": c}, _FAST["macd_fast"], _FAST["macd_slow"], _FAST["macd_signal"]
    ).values
    line, sig = res["macd"], res["signal"]
    i = len(c) - 1
    finite = all(math.isfinite(float(x)) for x in (line[i], sig[i], line[i - 1], sig[i - 1]))
    if not finite:
        assert r.momentum.macd_cross in ("none", "not_available")
        return
    if line[i] > sig[i] and line[i - 1] <= sig[i - 1]:
        expected = "bullish_cross"
    elif line[i] < sig[i] and line[i - 1] >= sig[i - 1]:
        expected = "bearish_cross"
    else:
        expected = "none"
    assert r.momentum.macd_cross == expected


# ------------------------------------------------------------------ volatility
def test_historical_volatility_hand_computed():
    closes = [100.0]
    for i in range(1, 40):
        closes.append(closes[-1] * 1.01 if i % 2 == 1 else closes[-1] / 1.01)
    closes = np.array(closes)
    r = build_summary(
        *_ohlc(closes),
        params={**_FAST, "hv_period": 20, "hv_trading_days": 250},
    )
    a = math.log(1.01)
    # 20 alternating log returns: sample stdev = a * sqrt(20/19).
    expected = a * math.sqrt(20.0 / 19.0) * math.sqrt(250.0) * 100.0
    assert r.volatility.historical_volatility_pct_annual == pytest.approx(expected, rel=1e-12)


def test_atr_period_one_equals_true_range():
    c = np.array([100.0, 102, 101, 105, 104, 108, 110, 109])
    o, h, lo, _ = _ohlc(c)
    r = build_summary(o, h, lo, c, params={"atr_period": 1, **_FAST})
    tr = max(
        h[-1] - lo[-1],
        abs(h[-1] - c[-2]),
        abs(lo[-1] - c[-2]),
    )
    assert r.volatility.atr == pytest.approx(float(tr), abs=1e-9)
    assert r.volatility.atr_pct == pytest.approx(float(tr) / c[-1] * 100.0, rel=1e-9)


def test_atr_disabled_by_configuration():
    r = build_summary(*_ohlc(_ramp(60)), params={"atr_period": 0, **_FAST})
    assert r.volatility.atr is None and r.volatility.atr_pct is None
    assert any("atr_period is 0" in item for item in r.limitations)


def test_rolling_return_stdev_hand_computed():
    closes = np.linspace(100, 130, 40) + np.array([(-1.0) ** i * (i % 3) for i in range(40)])
    r = build_summary(*_ohlc(closes), params={**_FAST, "return_window": 10})
    rets = [(closes[i] - closes[i - 1]) / closes[i - 1] * 100.0 for i in range(1, len(closes))]
    expected = _naive_stdev(rets[-10:])  # ddof=1, last `return_window` bars
    assert r.volatility.rolling_stddev_pct_per_bar == pytest.approx(expected, abs=1e-9)


def test_bandwidth_hand_computed():
    closes = np.linspace(100, 130, 40) + np.array([(-1.0) ** i * (i % 3) for i in range(40)])
    r = build_summary(*_ohlc(closes), params={**_FAST, "bollinger_period": 20})
    window = closes[-20:]
    mid = float(np.mean(window))
    sd = float(np.std(window, ddof=0))  # Bollinger uses the population stdev
    expected = 400.0 * sd / mid  # 100 * (mid+2sd - (mid-2sd)) / mid
    assert r.volatility.bandwidth_pct == pytest.approx(expected, abs=1e-9)


def test_volatility_regime_expanding_and_contracting():
    params = {**_FAST, "bollinger_period": 10}
    calm = 100.0 + np.array([0.2 * (-1) ** i for i in range(30)])
    violent = 101.0 + np.array([8.0 * (-1) ** i for i in range(3)])
    expanding = build_summary(*_ohlc(np.concatenate([calm, violent])), params=params)
    assert expanding.volatility.regime == "expanding"

    # Violent phase inside the comparison window but outside the final one:
    # the newest bandwidth is far below the mean of the preceding bars.
    calm_short = 100.0 + np.array([0.2 * (-1) ** i for i in range(12)])
    violent_mid = 101.0 + np.array([8.0 * (-1) ** i for i in range(5)])
    contracting = build_summary(
        *_ohlc(np.concatenate([calm_short, violent_mid, calm_short])), params=params
    )
    assert contracting.volatility.regime == "contracting"


def test_constant_series_regime_not_evaluated():
    r = build_summary(*_ohlc(_const(40, 50.0)), params=_FAST)
    assert r.volatility.bandwidth_pct == 0.0  # bands collapse on a zero range
    assert r.volatility.regime is None
    assert any("volatility: regime not available" in item for item in r.interpretation.missing)
    assert any("Volatility regime not evaluated" in item for item in r.limitations)


# ------------------------------------------------------------------ volume
def test_missing_volume_is_reported_not_invented():
    r = build_summary(*_ohlc(_ramp(40)), params=_FAST)
    assert r.volume_stats.status == "no_volume"
    assert r.volume_stats.mfi is None
    assert r.volume_stats.relative_volume is None
    assert any("volume: not supplied" in item for item in r.interpretation.missing)
    assert any("No volume series supplied" in item for item in r.limitations)


def test_mfi_matches_independent_reference():
    rng = np.random.default_rng(7)
    closes = 100.0 + np.cumsum(rng.normal(0, 1.0, 40))
    o, h, lo, c = _ohlc(closes)
    vol = rng.uniform(50.0, 150.0, 40)
    r = build_summary(o, h, lo, c, vol, params=_FAST)
    expected = _naive_mfi(list(h), list(lo), list(c), list(vol), 5)
    assert r.volume_stats.mfi == pytest.approx(expected, abs=1e-9)
    assert 0.0 <= r.volume_stats.mfi <= 100.0


def test_relative_volume_hand_computed():
    o, h, lo, c = _ohlc(_ramp(24))
    vol = np.array([100.0] * 19 + [100.0, 100.0, 100.0, 100.0, 200.0])
    r = build_summary(o, h, lo, c, vol, params={**_FAST, "rvol_baseline": 5})
    assert r.volume_stats.volume_sma == pytest.approx(120.0)  # (4*100+200)/5
    assert r.volume_stats.relative_volume == pytest.approx(200.0 / 120.0, rel=1e-12)
    assert r.volume_stats.latest_volume == 200.0


def test_small_rvol_baseline_is_not_evaluated():
    vol = np.full(30, 100.0)
    r = build_summary(*_ohlc(_ramp(30)), vol, params={**_FAST, "rvol_baseline": 1})
    assert r.volume_stats.relative_volume is None
    assert r.volume_stats.volume_sma is None
    assert any("relative_volume not evaluated" in item for item in r.limitations)


def test_zero_volume_masks_mfi_and_rvol():
    vol = np.zeros(30)
    r = build_summary(*_ohlc(_ramp(30)), vol, params=_FAST)
    assert r.volume_stats.mfi is None  # 0/0 flow is undefined, so NaN -> None
    assert r.volume_stats.relative_volume is None  # 0 / mean(0) is NaN -> None
    assert any("zero-volume window" in item for item in r.limitations)


def test_constant_typical_price_masks_mfi():
    r = build_summary(*_ohlc(_const(40, 50.0)), np.full(40, 100.0), params=_FAST)
    assert r.volume_stats.mfi is None
    assert any("constant typical-price" in item for item in r.limitations)


def test_engine_itself_reports_mfi_as_undefined_not_100():
    """The summary mask is not hiding an engine bug - the engine agrees now."""
    from megatool.ta import volume as _volume

    flat = np.full(40, 50.0)
    eng = _volume.mfi({"high": flat, "low": flat, "close": flat, "volume": np.full(40, 100.0)}, 14)
    assert np.isnan(eng.values["mfi"]).all()


# ------------------------------------------------------------------ structure
def test_structure_up_with_swing_levels_and_near_support_none():
    r = build_summary(*_zigzag(), params=_FAST)
    assert r.structure.structure == "up"
    assert r.structure.swing_count == 4
    assert r.structure.status == "ok"
    assert r.structure.near_support is None  # documented: not evaluated
    o, h, lo, c = _zigzag()
    swings = find_swings(h, lo, left=3, right=3, last_index=len(c) - 1)
    lows = [s for s in swings if s.kind == "low"]
    highs = [s for s in swings if s.kind == "high"]
    assert r.structure.support_level == pytest.approx(lows[-1].price)
    assert r.structure.resistance_level == pytest.approx(highs[-1].price)


def test_structure_insufficient_on_short_series():
    r = build_summary(*_ohlc(_const(8, 50.0)), params=_FAST)
    assert r.structure.structure == "insufficient data"
    assert r.structure.status == "insufficient_history"
    assert any("Swing structure not evaluated" in item for item in r.limitations)


# ------------------------------------------------------------------ divergence
def _swings():
    # Two swing highs making a higher high (110 -> 120) and two swing lows
    # making a lower low (100 -> 95).
    return [
        Swing(10, "high", 110.0, 13, True),
        Swing(16, "low", 100.0, 18, True),
        Swing(24, "high", 120.0, 26, True),
        Swing(30, "low", 95.0, 32, True),
    ]


def test_divergence_detects_both_directions_and_skips_ties():
    ind = [None] * 40
    ind[10] = 90.0
    ind[24] = 70.0  # higher price high, lower indicator -> bearish
    ind[16] = 25.0
    ind[30] = 45.0  # lower price low, higher indicator -> bullish
    out = candidate_divergence(_swings(), ind, indicator_name="rsi")
    directions = [c["direction"] for c in out]
    assert directions.count("bearish") == 1
    assert directions.count("bullish") == 1
    bearish = next(c for c in out if c["direction"] == "bearish")
    assert bearish["price_index"] == 24
    assert bearish["price_move"] == pytest.approx(10.0)
    assert bearish["indicator_move"] == pytest.approx(-20.0)

    tied = [None] * 40
    tied[10] = 80.0
    tied[24] = 80.0  # exact tie: not reported (strict inequalities)
    assert candidate_divergence(_swings(), tied) == []


def test_divergence_field_contract_disclaims_confirmation():
    ind = [None] * 40
    ind[10], ind[24] = 90.0, 70.0
    out = candidate_divergence(_swings(), ind, indicator_name="rsi")
    assert len(out) == 1
    cand = out[0]
    assert cand["classification"] == "DETECTED"
    assert cand["label"] == "CANDIDATE"
    assert cand["confirmed"] is None
    assert cand["status"] == "not evaluated"
    assert "no confirmation rule" in cand["caveat"]
    assert "near_support" in cand["caveat"]
    assert cand["indicator"] == "rsi"
    assert cand["indicator_value_at_index"] == 70.0


def test_divergence_last_index_reads_no_future_data():
    ind = [None] * 40
    ind[10], ind[24] = 90.0, 70.0  # bearish pair: higher high 110 -> 120
    ind[16], ind[30] = 25.0, 45.0  # bullish pair: lower low 100 -> 95

    cutoff = candidate_divergence(_swings(), ind, last_index=29)
    assert [c["price_index"] for c in cutoff] == [24]
    assert all(c["price_index"] <= 29 for c in cutoff)
    # The swing low at index 30 is future data for an analyst at bar 29.
    assert not any(c["price_index"] == 30 for c in cutoff)

    whole = candidate_divergence(_swings(), ind, last_index=39)
    assert sorted(c["price_index"] for c in whole) == [24, 30]

    # An explicit cutoff equals operating on the truncated series itself.
    assert cutoff == candidate_divergence(_swings(), ind[:30], last_index=29)


def test_divergence_min_move_and_lookback_bounds():
    ind = [None] * 60
    ind[10], ind[24] = 90.0, 70.0
    # Price leg 110 -> 120 is +9.09%: dropped when the floor is higher.
    strict = candidate_divergence(_swings(), ind, min_move_pct=10.0)
    assert all(c["direction"] != "bearish" for c in strict)
    loose = candidate_divergence(_swings(), ind, min_move_pct=5.0)
    assert any(c["direction"] == "bearish" for c in loose)
    # Only the most recent max_lookback+1 swings of a kind are examined.
    many = [
        Swing(10, "high", 110.0, 13, True),
        Swing(24, "high", 120.0, 26, True),
        Swing(40, "high", 130.0, 42, True),
    ]
    ind_many = [None] * 60
    ind_many[10], ind_many[24], ind_many[40] = 90.0, 70.0, 50.0
    bounded = candidate_divergence(many, ind_many, max_lookback=1)
    assert [c["price_index"] for c in bounded] == [40]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"last_index": -1},
        {"last_index": 99},
        {"last_index": 1.5},
        {"min_move_pct": -1.0},
        {"max_lookback": -1},
    ],
)
def test_divergence_invalid_arguments(kwargs):
    ind = [1.0] * 10
    with pytest.raises(SummaryError):
        candidate_divergence(_swings(), ind, **kwargs)
    with pytest.raises(SummaryError):
        candidate_divergence(_swings(), [])


def test_build_summary_reports_end_to_end_divergence():
    r = build_summary(*_zigzag(), params=_FAST)
    o, h, lo, c = _zigzag()
    swings = find_swings(h, lo, left=3, right=3, last_index=len(c) - 1)
    highs = [s.index for s in swings if s.kind == "high"]
    assert len(r.divergence_candidates) == 1
    cand = r.divergence_candidates[0]
    assert cand["direction"] == "bearish"
    assert cand["price_index"] == highs[-1]  # second, higher swing high
    assert cand["confirmed"] is None and cand["status"] == "not evaluated"
    assert r.structure.structure == "up"  # trend context stated separately


# ------------------------------------------------------------------ causality
@pytest.mark.parametrize("k", [12, 25, 44])
def test_prefix_values_match_prefix_only_references(k):
    o, h, lo, c = _zigzag()
    po, ph, pl, pc = o[: k + 1], h[: k + 1], lo[: k + 1], c[: k + 1]
    r = build_summary(po, ph, pl, pc, params=_FAST)
    assert r.last_index == k

    # Independent trailing-window references, computed from the prefix only.
    expected_sma = float(np.mean(pc[-_FAST["sma_short"] :]))
    assert r.trend.sma_short == pytest.approx(expected_sma)
    expected_rsi = _naive_rsi(list(pc), _FAST["rsi_period"])[-1]
    if expected_rsi is None:
        assert r.momentum.rsi is None
    else:
        assert r.momentum.rsi == pytest.approx(expected_rsi, abs=1e-9)
    window = _FAST["trend_short"]
    if len(pc) > window:
        expected_change = (pc[-1] - pc[-1 - window]) / pc[-1 - window] * 100.0
        assert r.trend.short_change_pct == pytest.approx(expected_change)
    else:
        assert r.trend.short_change_pct is None

    # Nothing derived from a future bar may appear in the output.
    assert all(c_["price_index"] <= k for c_ in r.divergence_candidates)
    prefix_swings = find_swings(ph, pl, left=3, right=3, last_index=k)
    prefix_lows = [s for s in prefix_swings if s.kind == "low"]
    prefix_highs = [s for s in prefix_swings if s.kind == "high"]
    if prefix_lows:
        assert r.structure.support_level == pytest.approx(prefix_lows[-1].price)
    if prefix_highs:
        assert r.structure.resistance_level == pytest.approx(prefix_highs[-1].price)


def test_shared_prefix_with_different_futures_is_identical():
    o, h, lo, c = _zigzag()
    k = 30
    future_a = np.concatenate([c[: k + 1], c[: k + 1] * 1.5])
    future_b = np.concatenate([c[: k + 1], c[: k + 1] * 0.5])
    ra = build_summary(*_ohlc(future_a[: k + 1]), params=_FAST).to_dict()
    rb = build_summary(*_ohlc(future_b[: k + 1]), params=_FAST).to_dict()
    assert ra == rb  # the suffix beyond k cannot reach the summary of bar k


def test_price_gap_does_not_break_summary():
    closes = _ramp(40)
    closes[20] = closes[19] * 0.8  # hard gap down between bars 19 and 20
    r = build_summary(*_ohlc(closes), params=_FAST)
    assert r.volatility.atr is not None and math.isfinite(r.volatility.atr)
    assert r.momentum.rsi is not None and math.isfinite(r.momentum.rsi)
    # Trailing-window maths is unaffected by the gap being a gap.
    window = _FAST["trend_short"]
    expected = (closes[-1] - closes[-1 - window]) / closes[-1 - window] * 100.0
    assert r.trend.short_change_pct == pytest.approx(expected)
    assert 0.0 <= r.momentum.rsi <= 100.0


# ------------------------------------------------------------------ interpretation
def test_interpretation_lists_are_coherent():
    r = build_summary(*_zigzag(), params=_FAST)
    inter = r.interpretation
    assert inter.trend_direction == r.trend.intermediate_direction
    assert inter.trend_strength == r.trend.strength
    assert inter.momentum_state == r.momentum.rsi_zone
    assert inter.volatility_regime == r.volatility.regime
    buckets = [inter.supporting, inter.conflicting, inter.ambiguous, inter.missing]
    seen = set()
    for bucket in buckets:
        for item in bucket:
            assert item not in seen  # every line is classified exactly once
            seen.add(item)
    assert any("trend:" in item for item in inter.supporting + inter.ambiguous)
    assert "INTERPRETIVE summary:" in inter.narrative
    assert "no trading recommendation" in inter.disclaimer


def test_interpretation_conflict_when_structure_disagrees():
    # The zigzag fixture ends with an up structure while the intermediate
    # horizon is down: the disagreement must surface in `conflicting`.
    r = build_summary(*_zigzag(), params=_FAST)
    assert r.structure.structure == "up"
    assert r.trend.intermediate_direction == "down"
    assert any(item.startswith("structure: up") for item in r.interpretation.conflicting)


def test_summary_never_emits_a_confidence_or_rating_field():
    r = build_summary(*_zigzag(), params=_FAST)
    payload = r.to_dict()

    def walk(node, path=""):
        if isinstance(node, dict):
            for key, value in node.items():
                assert "confidence" not in str(key).lower()
                assert "rating" not in str(key).lower() or key == "disclaimer"
                walk(value, path + "." + str(key))
        elif isinstance(node, list):
            for value in node:
                walk(value, path)
        elif isinstance(node, str):
            assert "confidence" not in node.lower()

    walk(payload)
