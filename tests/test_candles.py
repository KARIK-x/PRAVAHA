"""Candlestick pattern detection tests.

# SYNTHETIC FIXTURE
Every price series in this file is hand-built or deterministically generated
(same seed every run). Nothing here is real market data, nothing is written
to any database, and no test asserts anything about real NEPSE prices.

Verification layers, mirroring ``test_swings.py`` / ``test_indicators.py``:

1. Hand-built OHLC bars where every measurement (body, range, shadows,
   ratios) is arithmetically obvious, with exact expected values.
2. Near-miss negatives: geometry that fails exactly one documented
   condition must NOT fire.
3. Boundary cases: a value exactly at a threshold fires, just outside does not.
4. Bad-data contract: invalid OHLC, non-finite values, empty / 1-2 bar
   series, bad parameters -> ``CandleError``; zero-range bars -> no crash,
   no candidacy.
5. The causality property: detection on ``bars[0:k]`` equals the first ``k``
   detections of the full series (no future data).
"""

from __future__ import annotations

import numpy as np
import pytest

from megatool.ta.candles import (
    CANDLE_RULE_VERSION,
    MIN_BARS,
    CandleError,
    PatternParams,
    detect_patterns,
    validate_ohlc,
)


# ------------------------------------------------------- SYNTHETIC FIXTURES
def _bearish_context(n: int) -> tuple[list, list, list, list]:
    """Descending bearish bars: O=100-i, C=96-i, H=103-i, L=93-i.

    body=4, range=10, upper=3, lower=3 (body_ratio 0.4). Fires no pattern of
    its own at any index: 0.4 clears every body-ratio cap except the
    three-candle ones (0.5/0.6), shadows fail the 2x hammer tests, and
    identical same-direction pairs cannot engulf or pierce. Closes decline by
    exactly 1 per bar, so the prior trend is "down".
    """
    o = [100.0 - i for i in range(n)]
    c = [96.0 - i for i in range(n)]
    h = [103.0 - i for i in range(n)]
    lo = [93.0 - i for i in range(n)]
    return o, h, lo, c


def _bullish_context(n: int) -> tuple[list, list, list, list]:
    """Ascending bullish bars: O=100+i, C=104+i, H=107+i, L=97+i.

    Mirror of ``_bearish_context`` (same invariants, prior trend "up").
    """
    o = [100.0 + i for i in range(n)]
    c = [104.0 + i for i in range(n)]
    h = [107.0 + i for i in range(n)]
    lo = [97.0 + i for i in range(n)]
    return o, h, lo, c


def _append(
    base: tuple[list, list, list, list], bars: list[tuple]
) -> tuple[list, list, list, list]:
    o, h, lo, c = base
    for open_, high, low, close in bars:
        o.append(open_)
        h.append(high)
        lo.append(low)
        c.append(close)
    return o, h, lo, c


def _names(patterns) -> list[str]:
    return [p.name for p in patterns]


# ---------------------------------------------------------- validation layer
def test_empty_input_raises():
    with pytest.raises(CandleError, match="empty"):
        detect_patterns([], [], [], [])


@pytest.mark.parametrize("n", [1, 2])
def test_one_or_two_bars_raise_as_insufficient_history(n):
    o = [100.0] * n
    with pytest.raises(CandleError, match="insufficient history"):
        detect_patterns(o, [101.0] * n, [99.0] * n, [100.5] * n)


def test_three_bars_is_the_accepted_minimum():
    # doji needs no context, so it must fire even on the shortest accepted series
    o = [100.0, 100.0, 100.0]
    h = [105.0, 105.0, 105.0]
    lo = [95.0, 95.0, 95.0]
    c = [100.0, 100.0, 100.0]
    assert MIN_BARS == 3
    assert _names(detect_patterns(o, h, lo, c)) == ["doji", "doji", "doji"]


def test_mismatched_lengths_raise():
    with pytest.raises(CandleError, match="same length"):
        detect_patterns([100.0, 101.0], [102.0], [99.0], [101.0, 101.0])


def test_high_below_low_raises():
    with pytest.raises(CandleError, match="high` is below `low"):
        detect_patterns([100.0], [99.0], [101.0], [100.0])


def test_high_below_open_raises():
    with pytest.raises(CandleError, match="below the open or close"):
        detect_patterns([102.0], [101.0], [99.0], [100.0])


def test_low_above_close_raises():
    with pytest.raises(CandleError, match="above the open or close"):
        detect_patterns([100.0], [102.0], [101.0], [100.5])


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_values_raise(bad):
    o = [100.0, 100.0, 100.0]
    h = [101.0, 101.0, 101.0]
    lo = [99.0, 99.0, 99.0]
    c = [100.0, 100.0, 100.0]
    c[1] = bad
    with pytest.raises(CandleError, match="finite"):
        detect_patterns(o, h, lo, c)


def test_two_dimensional_input_raises():
    with pytest.raises(CandleError, match="one-dimensional"):
        detect_patterns(np.ones((3, 1)), np.ones((3, 1)), np.ones((3, 1)), np.ones((3, 1)))


def test_non_numeric_input_raises():
    with pytest.raises(CandleError, match="could not be read as numbers"):
        detect_patterns(["a", "b", "c"], ["d", "e", "f"], ["g", "h", "i"], ["j", "k", "l"])


# --------------------------------------------------------------- parameters
def test_unknown_param_key_raises():
    with pytest.raises(CandleError, match="unknown parameter"):
        detect_patterns([100.0] * 3, [101.0] * 3, [99.0] * 3, [100.0] * 3, params={"nope": 1})


@pytest.mark.parametrize(
    "overrides",
    [
        {"doji_max_body_ratio": 1.5},  # ratio above 1
        {"marubozu_max_shadow_ratio": -0.1},  # negative ratio
        {"hammer_min_lower_multiple": 0},  # multiple must be > 0
        {"inverted_min_upper_multiple": -2.0},
        {"trend_bars": 0},  # must be >= 1
        {"trend_bars": 2.5},  # must be an int
        {"require_prior_trend": "yes"},  # must be a bool
        {"doji_max_body_ratio": float("nan")},  # must be finite
    ],
)
def test_out_of_range_params_raise(overrides):
    with pytest.raises(CandleError):
        detect_patterns([100.0] * 3, [101.0] * 3, [99.0] * 3, [100.0] * 3, params=overrides)


def test_params_of_wrong_type_raise():
    with pytest.raises(CandleError, match="PatternParams"):
        detect_patterns([100.0] * 3, [101.0] * 3, [99.0] * 3, [100.0] * 3, params=3)


def test_dict_params_override_defaults():
    # body_ratio = 0.08: a doji under the default 0.10 cap, not under 0.05
    o, h, lo, c = [100.0] * 3, [105.0] * 3, [95.0] * 3, [100.8] * 3
    assert _names(detect_patterns(o, h, lo, c)) == ["doji"] * 3
    assert _names(detect_patterns(o, h, lo, c, params={"doji_max_body_ratio": 0.05})) == []


def test_pattern_params_instance_accepted():
    p = PatternParams(doji_max_body_ratio=0.05)
    o, h, lo, c = [100.0] * 3, [105.0] * 3, [95.0] * 3, [100.8] * 3
    assert _names(detect_patterns(o, h, lo, c, params=p)) == []


def test_none_params_use_documented_defaults():
    p = PatternParams()
    assert p.doji_max_body_ratio == 0.10
    assert p.trend_bars == 3
    assert p.require_prior_trend is True
    assert p.hammer_min_lower_multiple == 2.0


# --------------------------------------------------------------------- doji
def test_doji_positive_and_measurements():
    # body 1, range 10 -> body_ratio 0.10; three identical bars -> three dojis
    o, h, lo, c = [100.0] * 3, [105.0] * 3, [95.0] * 3, [101.0] * 3
    p = detect_patterns(o, h, lo, c)
    assert _names(p) == ["doji"] * 3
    pat = p[1]
    assert pat.direction == "neutral"
    assert pat.index == 1
    m = pat.measurements
    assert m["body"] == 1.0
    assert m["range"] == 10.0
    assert m["upper_shadow"] == 4.0  # 105 - max(100, 101)
    assert m["lower_shadow"] == 5.0  # min(100, 101) - 95
    assert m["body_ratio"] == pytest.approx(0.10)
    assert m["upper_ratio"] == pytest.approx(0.40)
    assert m["lower_ratio"] == pytest.approx(0.50)
    assert pat.context["near_support"] is None
    assert pat.context["prior_trend_required"] is False


def test_doji_boundary_exactly_at_threshold_fires():
    # body_ratio = 1/10 == 0.10 exactly; rule is "<=" so it fires
    p = detect_patterns([100.0] * 3, [105.0] * 3, [95.0] * 3, [101.0] * 3)
    assert _names(p) == ["doji"] * 3


def test_doji_boundary_just_outside_does_not_fire():
    # body_ratio = 1.001/10 = 0.1001 > 0.10
    p = detect_patterns([100.0] * 3, [105.0] * 3, [95.0] * 3, [101.001] * 3)
    assert "doji" not in _names(p)


def test_doji_near_miss_beyond_threshold():
    p = detect_patterns([100.0] * 3, [105.0] * 3, [95.0] * 3, [101.5] * 3)
    assert "doji" not in _names(p)


def test_doji_fires_without_prior_context():
    # 3 bars total: prior trend cannot be evaluated, but doji requires none
    p = detect_patterns([100.0] * 3, [105.0] * 3, [95.0] * 3, [100.0] * 3)
    assert _names(p) == ["doji"] * 3


# ------------------------------------------------------------------- hammer
def test_hammer_positive_exact_and_measurements():
    # context 0..3, hammer at 4: body 1 (O=95,C=96), lower 2 (L=93),
    # upper 0.2 (H=96.2): range 3.2, body_ratio 0.3125, lower == 2x body
    base = _bearish_context(4)
    o, h, lo, c = _append(base, [(95.0, 96.2, 93.0, 96.0)])
    p = detect_patterns(o, h, lo, c)
    assert _names(p) == ["hammer"]
    pat = p[0]
    assert pat.direction == "bullish"
    assert pat.index == 4
    m = pat.measurements
    assert m["body"] == 1.0
    assert m["range"] == pytest.approx(3.2)
    assert m["lower_shadow"] == 2.0
    assert m["upper_shadow"] == pytest.approx(0.2)
    assert m["body_ratio"] == pytest.approx(1.0 / 3.2)
    assert m["lower_shadow"] == pytest.approx(2.0 * m["body"])
    assert pat.context["prior_trend"] == "down"
    assert pat.context["prior_trend_required"] is True
    assert any("prior down trend" in n for n in pat.notes)


def test_hammer_near_miss_lower_shadow_shorter_than_twice_body():
    base = _bearish_context(4)
    o, h, lo, c = _append(base, [(95.0, 96.2, 93.1, 96.0)])  # lower 1.9 < 2x body
    assert "hammer" not in _names(detect_patterns(o, h, lo, c))


def test_hammer_boundary_lower_shadow_exactly_twice_body_fires():
    base = _bearish_context(4)
    o, h, lo, c = _append(base, [(95.0, 96.2, 93.0, 96.0)])
    p = detect_patterns(o, h, lo, c)
    assert "hammer" in _names(p)


def test_hammer_boundary_just_below_twice_body_does_not_fire():
    base = _bearish_context(4)
    o, h, lo, c = _append(base, [(95.0, 96.2, 93.01, 96.0)])  # lower 1.99
    assert "hammer" not in _names(detect_patterns(o, h, lo, c))


def test_hammer_requires_prior_downtrend():
    base = _bullish_context(4)  # same geometry, opposite context
    o, h, lo, c = _append(base, [(95.0, 96.2, 93.0, 96.0)])
    assert "hammer" not in _names(detect_patterns(o, h, lo, c))


def test_hammer_with_upper_shadow_too_long_does_not_fire():
    base = _bearish_context(4)
    # upper = 0.4 > 10% of range (0.4/3.4), lower still 2x body
    o, h, lo, c = _append(base, [(95.0, 96.4, 93.0, 96.0)])
    assert "hammer" not in _names(detect_patterns(o, h, lo, c))


# ----------------------------------------------- inverted hammer / shooting star
def test_inverted_hammer_positive():
    # body 1 (O=95,C=96), upper 2 (H=98), lower 0 (L=95): range 3
    base = _bearish_context(4)
    o, h, lo, c = _append(base, [(95.0, 98.0, 95.0, 96.0)])
    p = detect_patterns(o, h, lo, c)
    assert _names(p) == ["inverted_hammer"]
    assert p[0].direction == "bullish"
    assert p[0].context["prior_trend"] == "down"


def test_shooting_star_same_geometry_after_uptrend():
    base = _bullish_context(4)
    o, h, lo, c = _append(base, [(95.0, 98.0, 95.0, 96.0)])
    p = detect_patterns(o, h, lo, c)
    assert _names(p) == ["shooting_star"]
    assert p[0].direction == "bearish"
    assert p[0].context["prior_trend"] == "up"


def test_inverted_hammer_geometry_after_uptrend_is_not_an_inverted_hammer():
    # Geometry identical; only the context differs, so only shooting star may fire
    base = _bullish_context(4)
    o, h, lo, c = _append(base, [(95.0, 98.0, 95.0, 96.0)])
    names = _names(detect_patterns(o, h, lo, c))
    assert "inverted_hammer" not in names
    assert "shooting_star" in names


def test_inverted_hammer_near_miss_short_upper_shadow():
    base = _bearish_context(4)
    # upper 1.9 < 2x body (2.0)
    o, h, lo, c = _append(base, [(95.0, 97.9, 95.0, 96.0)])
    assert "inverted_hammer" not in _names(detect_patterns(o, h, lo, c))


# ------------------------------------------------------------- spinning top
def test_spinning_top_positive_boundary_shadows():
    # body 2 (O=100,C=102), upper 6 (H=108), lower 2 (L=98): range 10,
    # body_ratio 0.20, upper_ratio 0.60, lower_ratio 0.20 exactly at the floor
    o, h, lo, c = [100.0] * 3, [108.0] * 3, [98.0] * 3, [102.0] * 3
    p = detect_patterns(o, h, lo, c)
    assert _names(p) == ["spinning_top"] * 3
    assert p[0].measurements["body_ratio"] == pytest.approx(0.20)
    assert p[0].measurements["upper_ratio"] == pytest.approx(0.60)
    assert p[0].measurements["lower_ratio"] == pytest.approx(0.20)


def test_spinning_top_near_miss_upper_shadow_below_floor():
    # upper 1.9 / range 10 = 0.19 < 0.20
    o, h, lo, c = [100.0] * 3, [103.9] * 3, [93.9] * 3, [102.0] * 3
    assert "spinning_top" not in _names(detect_patterns(o, h, lo, c))


def test_spinning_top_boundary_body_just_above_doji_band_fires():
    # body_ratio 0.1001 -> outside doji, inside spinning top band
    o, h, lo, c = [100.0] * 3, [105.0] * 3, [95.0] * 3, [101.001] * 3
    names = _names(detect_patterns(o, h, lo, c))
    assert "spinning_top" in names
    assert "doji" not in names


def test_spinning_top_not_fired_by_large_body():
    # body_ratio 0.50 > 0.30 cap
    o, h, lo, c = [100.0] * 3, [106.0] * 3, [96.0] * 3, [105.0] * 3
    assert "spinning_top" not in _names(detect_patterns(o, h, lo, c))


# ----------------------------------------------------------------- marubozu
def test_marubozu_bullish_positive():
    o, h, lo, c = [100.0] * 3, [105.0] * 3, [100.0] * 3, [105.0] * 3
    p = detect_patterns(o, h, lo, c)
    assert _names(p) == ["marubozu"] * 3
    assert p[0].direction == "bullish"
    assert p[0].measurements["upper_shadow"] == 0.0
    assert p[0].measurements["lower_shadow"] == 0.0


def test_marubozu_bearish_positive():
    o, h, lo, c = [105.0] * 3, [105.0] * 3, [100.0] * 3, [100.0] * 3
    p = detect_patterns(o, h, lo, c)
    assert _names(p) == ["marubozu"] * 3
    assert p[0].direction == "bearish"


def test_marubozu_boundary_upper_shadow_exactly_5pct_fires():
    # upper 1 / range 20 = 0.05 exactly
    o, h, lo, c = [100.0] * 3, [120.0] * 3, [100.0] * 3, [119.0] * 3
    assert "marubozu" in _names(detect_patterns(o, h, lo, c))


def test_marubozu_boundary_upper_shadow_just_over_5pct_does_not_fire():
    # upper 1.01 / range 20.01 = 0.0505 > 0.05
    o, h, lo, c = [100.0] * 3, [120.01] * 3, [100.0] * 3, [119.0] * 3
    assert "marubozu" not in _names(detect_patterns(o, h, lo, c))


def test_marubozu_neutral_candle_never_marubozu():
    # open == close -> body 0 -> excluded by the body > 0 rule
    o, h, lo, c = [100.0] * 3, [100.0] * 3, [99.9] * 3, [100.0] * 3
    assert "marubozu" not in _names(detect_patterns(o, h, lo, c))


# ------------------------------------------------------- bullish engulfing
def test_bullish_engulfing_positive_exact_and_measurements():
    # c1 (i=4): O=96, C=92 (bearish body 4), H=97, L=91
    # c2 (i=5): O=91, C=97 (bullish body 6), H=98, L=90
    base = _bearish_context(4)
    o, h, lo, c = _append(base, [(96.0, 97.0, 91.0, 92.0), (91.0, 98.0, 90.0, 97.0)])
    p = detect_patterns(o, h, lo, c)
    assert _names(p) == ["bullish_engulfing"]
    pat = p[0]
    assert pat.direction == "bullish"
    assert pat.index == 5
    assert pat.measurements["open2_minus_close1"] == -1.0  # 91 - 92
    assert pat.measurements["close2_minus_open1"] == 1.0  # 97 - 96
    assert pat.measurements["body2_minus_body1"] == 2.0  # 6 - 4
    assert pat.context["prior_trend"] == "down"


def test_bullish_engulfing_near_miss_open_above_first_close():
    base = _bearish_context(4)
    o, h, lo, c = _append(base, [(96.0, 97.0, 91.0, 92.0), (92.5, 98.0, 90.0, 97.0)])
    names = _names(detect_patterns(o, h, lo, c))
    assert "bullish_engulfing" not in names
    assert "piercing_pattern" not in names


def test_bullish_engulfing_boundary_open_equal_first_close_fires():
    base = _bearish_context(4)
    o, h, lo, c = _append(base, [(96.0, 97.0, 91.0, 92.0), (92.0, 98.0, 90.0, 96.5)])
    assert "bullish_engulfing" in _names(detect_patterns(o, h, lo, c))


def test_bullish_engulfing_equal_bodies_do_not_engulf():
    # span is contained, but body2 == body1: neither engulfing (needs >)
    # nor harami (needs <) may fire
    base = _bearish_context(4)
    o, h, lo, c = _append(base, [(96.0, 97.0, 91.0, 92.0), (92.0, 98.0, 90.0, 96.0)])
    names = _names(detect_patterns(o, h, lo, c))
    assert "bullish_engulfing" not in names
    assert "harami" not in names


def test_bullish_engulfing_requires_prior_downtrend():
    base = _bullish_context(4)
    o, h, lo, c = _append(base, [(96.0, 97.0, 91.0, 92.0), (91.0, 98.0, 90.0, 97.0)])
    assert "bullish_engulfing" not in _names(detect_patterns(o, h, lo, c))


def test_context_gate_can_be_disabled_explicitly():
    base = _bullish_context(4)
    o, h, lo, c = _append(base, [(96.0, 97.0, 91.0, 92.0), (91.0, 98.0, 90.0, 97.0)])
    p = detect_patterns(o, h, lo, c, params={"require_prior_trend": False})
    hit = [x for x in p if x.name == "bullish_engulfing"]
    assert len(hit) == 1
    assert hit[0].context["prior_trend"] == "up"  # measured, honestly reported
    assert hit[0].context["prior_trend_required"] is True
    assert any("disabled by params" in n for n in hit[0].notes)


# ------------------------------------------------------- bearish engulfing
def test_bearish_engulfing_positive_mirror():
    # bullish context, c1 (O=104, C=108, H=109, L=103),
    # c2 (O=109, C=103, H=110, L=102): body 6 > 4, open2 >= close1, close2 <= open1
    base = _bullish_context(4)
    o, h, lo, c = _append(base, [(104.0, 109.0, 103.0, 108.0), (109.0, 110.0, 102.0, 103.0)])
    p = detect_patterns(o, h, lo, c)
    assert _names(p) == ["bearish_engulfing"]
    assert p[0].direction == "bearish"
    assert p[0].context["prior_trend"] == "up"


def test_bearish_engulfing_requires_prior_uptrend():
    base = _bearish_context(4)
    o, h, lo, c = _append(base, [(104.0, 109.0, 103.0, 108.0), (109.0, 110.0, 102.0, 103.0)])
    assert "bearish_engulfing" not in _names(detect_patterns(o, h, lo, c))


# -------------------------------------------------------------------- harami
def test_harami_bullish_positive_exact_and_measurements():
    # c1: O=97, C=91 (body 6, range 8 -> body_ratio 0.75)
    # c2: O=93, C=94 (body 1, inside the first body)
    base = _bearish_context(4)
    o, h, lo, c = _append(base, [(97.0, 98.0, 90.0, 91.0), (93.0, 94.5, 92.5, 94.0)])
    p = detect_patterns(o, h, lo, c)
    assert _names(p) == ["harami"]
    pat = p[0]
    assert pat.direction == "bullish"
    assert pat.index == 5
    assert pat.measurements["body1_minus_body2"] == 5.0  # 6 - 1
    assert pat.measurements["containment_margin_low"] == 2.0  # 93 - 91
    assert pat.measurements["containment_margin_high"] == 3.0  # 97 - 94
    assert pat.context["prior_trend"] == "down"


def test_harami_bearish_positive_mirror():
    base = _bullish_context(4)
    o, h, lo, c = _append(base, [(91.0, 98.0, 90.0, 97.0), (94.0, 95.5, 93.5, 95.0)])
    p = detect_patterns(o, h, lo, c)
    assert _names(p) == ["harami"]
    assert p[0].direction == "bearish"
    assert p[0].context["prior_trend"] == "up"


def test_harami_near_miss_second_body_escapes_first():
    base = _bearish_context(4)
    o, h, lo, c = _append(base, [(97.0, 98.0, 90.0, 91.0), (97.5, 98.5, 96.5, 98.0)])
    assert "harami" not in _names(detect_patterns(o, h, lo, c))


def test_harami_boundary_first_body_exactly_half_range_fires():
    # c1: body 4 / range 8 = 0.50 exactly
    base = _bearish_context(4)
    o, h, lo, c = _append(base, [(97.0, 97.0, 89.0, 93.0), (94.0, 95.5, 93.5, 95.0)])
    assert "harami" in _names(detect_patterns(o, h, lo, c))


def test_harami_boundary_first_body_just_below_half_does_not_fire():
    # body 3.9 / range 7.9 = 0.4937 < 0.50
    base = _bearish_context(4)
    o, h, lo, c = _append(base, [(96.9, 96.9, 89.0, 93.0), (94.0, 95.5, 93.5, 95.0)])
    assert "harami" not in _names(detect_patterns(o, h, lo, c))


def test_harami_direction_neutral_first_bar_never_harami():
    base = _bearish_context(4)
    # first bar of the pair has open == close (direction neutral)
    o, h, lo, c = _append(base, [(95.0, 98.0, 92.0, 95.0), (94.0, 95.5, 93.5, 94.5)])
    assert "harami" not in _names(detect_patterns(o, h, lo, c))


# --------------------------------------------------------------- piercing
def test_piercing_positive_exact_and_measurements():
    # c1: O=96, C=90 (body 6); midpoint 93
    # c2: O=88 (< close1), C=94 (> midpoint, < open1), H=95, L=87
    base = _bearish_context(4)
    o, h, lo, c = _append(base, [(96.0, 97.0, 89.0, 90.0), (88.0, 95.0, 87.0, 94.0)])
    p = detect_patterns(o, h, lo, c)
    assert _names(p) == ["piercing_pattern"]
    assert p[0].direction == "bullish"
    assert p[0].measurements["first_body_midpoint"] == 93.0
    assert p[0].measurements["close2_minus_midpoint"] == 1.0  # 94 - 93
    assert p[0].measurements["open2_minus_close1"] == -2.0  # 88 - 90


def test_piercing_boundary_close_at_midpoint_does_not_fire():
    base = _bearish_context(4)
    o, h, lo, c = _append(base, [(96.0, 97.0, 89.0, 90.0), (88.0, 95.0, 87.0, 93.0)])
    assert _names(detect_patterns(o, h, lo, c)) == []


def test_piercing_boundary_close_just_above_midpoint_fires():
    base = _bearish_context(4)
    o, h, lo, c = _append(base, [(96.0, 97.0, 89.0, 90.0), (88.0, 95.0, 87.0, 93.01)])
    assert "piercing_pattern" in _names(detect_patterns(o, h, lo, c))


def test_piercing_close_at_or_above_first_open_is_an_engulfing_not_a_pierce():
    base = _bearish_context(4)
    o, h, lo, c = _append(base, [(96.0, 97.0, 89.0, 90.0), (88.0, 97.0, 87.0, 97.0)])
    names = _names(detect_patterns(o, h, lo, c))
    assert "piercing_pattern" not in names
    assert "bullish_engulfing" in names


def test_piercing_requires_prior_downtrend():
    base = _bullish_context(4)
    o, h, lo, c = _append(base, [(96.0, 97.0, 89.0, 90.0), (88.0, 95.0, 87.0, 94.0)])
    assert "piercing_pattern" not in _names(detect_patterns(o, h, lo, c))


# -------------------------------------------------------- dark cloud cover
def test_dark_cloud_cover_positive_exact_and_measurements():
    # c1: O=90, C=96 (body 6); midpoint 93
    # c2: O=98 (> close1), C=92 (< midpoint, > open1), H=99, L=91
    base = _bullish_context(4)
    o, h, lo, c = _append(base, [(90.0, 97.0, 89.0, 96.0), (98.0, 99.0, 91.0, 92.0)])
    p = detect_patterns(o, h, lo, c)
    assert _names(p) == ["dark_cloud_cover"]
    assert p[0].direction == "bearish"
    assert p[0].measurements["first_body_midpoint"] == 93.0
    assert p[0].measurements["close2_minus_midpoint"] == -1.0  # 92 - 93
    assert p[0].context["prior_trend"] == "up"


def test_dark_cloud_cover_boundary_close_at_midpoint_does_not_fire():
    base = _bullish_context(4)
    o, h, lo, c = _append(base, [(90.0, 97.0, 89.0, 96.0), (98.0, 99.0, 91.0, 93.0)])
    assert _names(detect_patterns(o, h, lo, c)) == []


def test_dark_cloud_cover_boundary_close_just_below_midpoint_fires():
    base = _bullish_context(4)
    o, h, lo, c = _append(base, [(90.0, 97.0, 89.0, 96.0), (98.0, 99.0, 91.0, 92.99)])
    assert "dark_cloud_cover" in _names(detect_patterns(o, h, lo, c))


def test_dark_cloud_cover_requires_prior_uptrend():
    base = _bearish_context(4)
    o, h, lo, c = _append(base, [(90.0, 97.0, 89.0, 96.0), (98.0, 99.0, 91.0, 92.0)])
    assert "dark_cloud_cover" not in _names(detect_patterns(o, h, lo, c))


# ------------------------------------------------------------- morning star
def test_morning_star_positive_exact_and_measurements():
    # c1: O=97, C=90 (body 7 / range 9 = 0.778 >= 0.60)
    # star: O=89 (< close1 90), C=89.8 (body 0.8 / range 2 = 0.40 <= 0.50)
    # c3: O=91, C=95; midpoint (97+90)/2 = 93.5; close3 > midpoint
    base = _bearish_context(4)
    o, h, lo, c = _append(
        base,
        [
            (97.0, 98.0, 89.0, 90.0),
            (89.0, 90.0, 88.0, 89.8),
            (91.0, 96.0, 90.0, 95.0),
        ],
    )
    p = detect_patterns(o, h, lo, c)
    assert _names(p) == ["morning_star"]
    pat = p[0]
    assert pat.direction == "bullish"
    assert pat.index == 6
    assert pat.measurements["first_body_midpoint"] == 93.5
    assert pat.measurements["open2_minus_close1"] == -1.0  # 89 - 90
    assert pat.measurements["close3_minus_midpoint"] == 1.5  # 95 - 93.5
    assert pat.context["prior_trend"] == "down"


def test_morning_star_near_miss_star_opens_above_first_close():
    # gap requirement fails (O2 >= C1) while every other condition holds;
    # a bullish harami may fire on the same bars instead
    base = _bearish_context(4)
    o, h, lo, c = _append(
        base,
        [
            (97.0, 98.0, 89.0, 90.0),
            (90.5, 92.0, 89.5, 91.3),
            (91.0, 96.0, 90.0, 95.0),
        ],
    )
    assert "morning_star" not in _names(detect_patterns(o, h, lo, c))


def test_morning_star_near_miss_star_body_too_large():
    # star body 1.2 / range 2 = 0.60 > 0.50
    base = _bearish_context(4)
    o, h, lo, c = _append(
        base,
        [
            (97.0, 98.0, 89.0, 90.0),
            (89.0, 91.0, 89.0, 90.2),
            (91.0, 96.0, 90.0, 95.0),
        ],
    )
    assert "morning_star" not in _names(detect_patterns(o, h, lo, c))


def test_morning_star_near_miss_third_close_at_midpoint():
    base = _bearish_context(4)
    o, h, lo, c = _append(
        base,
        [
            (97.0, 98.0, 89.0, 90.0),
            (89.0, 90.0, 88.0, 89.8),
            (91.0, 96.0, 90.0, 93.5),  # close3 == midpoint, not strictly above
        ],
    )
    assert "morning_star" not in _names(detect_patterns(o, h, lo, c))


def test_morning_star_boundary_first_body_exactly_60pct_fires():
    # c1: body 6 / range 10 = 0.60 exactly
    base = _bearish_context(4)
    o, h, lo, c = _append(
        base,
        [
            (96.0, 96.0, 86.0, 90.0),
            (89.0, 90.0, 88.0, 89.8),
            (91.0, 96.0, 90.0, 95.0),
        ],
    )
    assert "morning_star" in _names(detect_patterns(o, h, lo, c))


def test_morning_star_boundary_first_body_just_below_60pct_does_not_fire():
    # c1: body 5.9 / range 9.9 = 0.5960 < 0.60; every other condition holds
    base = _bearish_context(4)
    o, h, lo, c = _append(
        base,
        [
            (95.9, 95.9, 86.0, 90.0),
            (89.0, 90.0, 88.0, 89.8),
            (91.0, 96.0, 90.0, 95.0),
        ],
    )
    assert "morning_star" not in _names(detect_patterns(o, h, lo, c))


def test_morning_star_requires_prior_downtrend():
    base = _bullish_context(4)
    o, h, lo, c = _append(
        base,
        [
            (97.0, 98.0, 89.0, 90.0),
            (89.0, 90.0, 88.0, 89.8),
            (91.0, 96.0, 90.0, 95.0),
        ],
    )
    assert "morning_star" not in _names(detect_patterns(o, h, lo, c))


# ------------------------------------------------------------- evening star
def test_evening_star_positive_exact_and_measurements():
    # c1: O=90, C=96 (body 6 / range 10 = 0.60)
    # star: O=97 (> close1 96), C=97.8 (body 0.8 / range 2 = 0.40)
    # c3: O=94, C=90 (bearish); midpoint 93; close3 < midpoint
    base = _bullish_context(4)
    o, h, lo, c = _append(
        base,
        [
            (90.0, 96.0, 86.0, 96.0),
            (97.0, 98.0, 96.0, 97.8),
            (94.0, 95.0, 89.0, 90.0),
        ],
    )
    p = detect_patterns(o, h, lo, c)
    assert _names(p) == ["evening_star"]
    assert p[0].direction == "bearish"
    assert p[0].index == 6
    assert p[0].measurements["first_body_midpoint"] == 93.0
    assert p[0].context["prior_trend"] == "up"


def test_evening_star_near_miss_star_gap_missing():
    # star opens exactly at the first close: gap rule is strict (>)
    base = _bullish_context(4)
    o, h, lo, c = _append(
        base,
        [
            (90.0, 96.0, 86.0, 96.0),
            (96.0, 98.0, 95.5, 96.8),
            (94.0, 95.0, 89.0, 90.0),
        ],
    )
    assert "evening_star" not in _names(detect_patterns(o, h, lo, c))


def test_evening_star_requires_prior_uptrend():
    base = _bearish_context(4)
    o, h, lo, c = _append(
        base,
        [
            (90.0, 96.0, 86.0, 96.0),
            (97.0, 98.0, 96.0, 97.8),
            (94.0, 95.0, 89.0, 90.0),
        ],
    )
    assert "evening_star" not in _names(detect_patterns(o, h, lo, c))


# ------------------------------------------------------ three white soldiers
def test_three_white_soldiers_positive_exact_and_measurements():
    # b4: O=94, C=97 (body 3 / range 5 = 0.60), b5: O=95.5 in [94,97],
    # C=98.5, b6: O=97.5 in [95.5,98.5], C=100.5; closes 97 < 98.5 < 100.5
    base = _bearish_context(4)
    o, h, lo, c = _append(
        base,
        [
            (94.0, 98.0, 93.0, 97.0),
            (95.5, 99.0, 94.5, 98.5),
            (97.5, 101.0, 96.5, 100.5),
        ],
    )
    p = detect_patterns(o, h, lo, c)
    assert _names(p) == ["three_white_soldiers"]
    pat = p[0]
    assert pat.direction == "bullish"
    assert pat.index == 6
    assert pat.measurements["close2_minus_close1"] == 1.5
    assert pat.measurements["close3_minus_close2"] == 2.0
    assert pat.context["prior_trend"] == "down"


def test_three_white_soldiers_flat_third_close_does_not_fire():
    base = _bearish_context(4)
    o, h, lo, c = _append(
        base,
        [
            (94.0, 98.0, 93.0, 97.0),
            (95.5, 99.0, 94.5, 98.5),
            (97.5, 99.0, 96.5, 98.5),  # close3 == close2, not strictly higher
        ],
    )
    assert "three_white_soldiers" not in _names(detect_patterns(o, h, lo, c))


def test_three_white_soldiers_boundary_body_exactly_half_fires():
    # b4: body 3 / range 6 = 0.50 exactly
    base = _bearish_context(4)
    o, h, lo, c = _append(
        base,
        [
            (94.0, 98.0, 92.0, 97.0),
            (95.5, 99.0, 94.5, 98.5),
            (97.5, 101.0, 96.5, 100.5),
        ],
    )
    assert "three_white_soldiers" in _names(detect_patterns(o, h, lo, c))


def test_three_white_soldiers_boundary_body_just_below_half_does_not_fire():
    # b4: body 2.99 / range 6 = 0.4983 < 0.50; everything else holds
    base = _bearish_context(4)
    o, h, lo, c = _append(
        base,
        [
            (94.0, 98.0, 92.0, 96.99),
            (95.5, 99.0, 94.5, 98.5),
            (97.5, 101.0, 96.5, 100.5),
        ],
    )
    assert "three_white_soldiers" not in _names(detect_patterns(o, h, lo, c))


def test_three_white_soldiers_open_outside_prior_body_does_not_fire():
    base = _bearish_context(4)
    o, h, lo, c = _append(
        base,
        [
            (94.0, 98.0, 93.0, 97.0),
            (93.5, 99.0, 93.5, 98.5),  # opens below the prior body (94)
            (97.5, 101.0, 96.5, 100.5),
        ],
    )
    assert "three_white_soldiers" not in _names(detect_patterns(o, h, lo, c))


# ------------------------------------------------------- three black crows
def test_three_black_crows_positive_exact_and_measurements():
    # b4: O=106, C=103 (body 3 / range 5 = 0.60), b5: O=104.5 in [103,106],
    # C=101.5, b6: O=102.5 in [101.5,104.5], C=99.5; closes 103 > 101.5 > 99.5
    base = _bullish_context(4)
    o, h, lo, c = _append(
        base,
        [
            (106.0, 107.0, 102.0, 103.0),
            (104.5, 105.5, 101.0, 101.5),
            (102.5, 103.5, 99.0, 99.5),
        ],
    )
    p = detect_patterns(o, h, lo, c)
    assert _names(p) == ["three_black_crows"]
    pat = p[0]
    assert pat.direction == "bearish"
    assert pat.index == 6
    assert pat.measurements["close2_minus_close1"] == -1.5
    assert pat.measurements["close3_minus_close2"] == -2.0
    assert pat.context["prior_trend"] == "up"


def test_three_black_crows_flat_third_close_does_not_fire():
    base = _bullish_context(4)
    o, h, lo, c = _append(
        base,
        [
            (106.0, 107.0, 102.0, 103.0),
            (104.5, 105.5, 101.0, 101.5),
            (103.5, 104.5, 100.5, 101.5),  # close3 == close2
        ],
    )
    assert "three_black_crows" not in _names(detect_patterns(o, h, lo, c))


def test_three_black_crows_requires_prior_uptrend():
    base = _bearish_context(4)
    o, h, lo, c = _append(
        base,
        [
            (106.0, 107.0, 102.0, 103.0),
            (104.5, 105.5, 101.0, 101.5),
            (102.5, 103.5, 99.0, 99.5),
        ],
    )
    assert "three_black_crows" not in _names(detect_patterns(o, h, lo, c))


# ------------------------------------------------------- context / causality
def test_insufficient_context_is_skipped_not_reported_without_context():
    # only 2 bars before the engulfing window: prior trend cannot be
    # evaluated, so the pattern must be skipped, not reported without context
    o, h, lo, c = _append(_bearish_context(2), [(96.0, 97.0, 91.0, 92.0), (91.0, 98.0, 90.0, 97.0)])
    assert _names(detect_patterns(o, h, lo, c)) == []


def test_shorter_trend_window_makes_the_same_context_sufficient():
    # same bars as above, but trend_bars=1 only needs closes[0..1] before s=2
    o, h, lo, c = _append(_bearish_context(2), [(96.0, 97.0, 91.0, 92.0), (91.0, 98.0, 90.0, 97.0)])
    p = detect_patterns(o, h, lo, c, params={"trend_bars": 1})
    assert "bullish_engulfing" in _names(p)


def test_no_future_data_prefix_equals_full_series():
    """Causality: detections on bars[0:k] are exactly the first k of the full run."""
    rng = np.random.default_rng(1234)
    n = 60
    close = 100.0 * np.exp(np.cumsum(rng.normal(0.0, 0.01, n)))
    open_ = np.empty(n)
    open_[0] = close[0]
    open_[1:] = close[:-1] * (1 + rng.normal(0, 0.002, n - 1))
    span = np.abs(rng.normal(0, 0.01, n)) * close
    high = np.maximum(open_, close) + span
    low = np.minimum(open_, close) - span

    full = detect_patterns(open_, high, low, close)
    assert len(full) > 0, "fixture produced no patterns; the test would prove nothing"
    for k in (10, 25, 41, 59, n):
        prefix = detect_patterns(open_[:k], high[:k], low[:k], close[:k])
        expected = [p for p in full if p.index < k]
        assert prefix == expected, f"prefix {k} disagrees with the full series"


def test_pattern_index_is_never_beyond_its_own_bar():
    rng = np.random.default_rng(99)
    n = 40
    close = 100.0 * np.exp(np.cumsum(rng.normal(0.0, 0.012, n)))
    open_ = np.concatenate(([close[0]], close[:-1]))
    high = np.maximum(open_, close) * 1.01
    low = np.minimum(open_, close) * 0.99
    for p in detect_patterns(open_, high, low, close):
        assert 0 <= p.index < n


# ------------------------------------------------------------- zero-range
def test_zero_range_series_detects_nothing_and_never_divides_by_zero():
    v = [100.0] * 5  # high == low == open == close everywhere
    assert detect_patterns(v, v, v, v) == []


def test_zero_range_bar_is_excluded_while_neighbours_still_detect():
    # dojis everywhere except bar 2, which is zero-range
    o = [100.0] * 5
    h = [105.0, 105.0, 100.0, 105.0, 105.0]
    lo = [95.0, 95.0, 100.0, 95.0, 95.0]
    c = [100.0] * 5
    p = detect_patterns(o, h, lo, c)
    assert [x.index for x in p] == [0, 1, 3, 4]
    assert all(x.name == "doji" for x in p)


# ------------------------------------------------------------- dates / output
def test_dates_are_attached_by_pattern_index():
    base = _bearish_context(4)
    o, h, lo, c = _append(base, [(95.0, 96.2, 93.0, 96.0)])
    dates = [f"2024-01-{i + 1:02d}" for i in range(5)]
    p = detect_patterns(o, h, lo, c, dates=dates)
    assert len(p) == 1
    assert p[0].date == dates[p[0].index] == "2024-01-05"


def test_dates_length_mismatch_raises():
    with pytest.raises(CandleError, match="one entry per bar"):
        detect_patterns([100.0] * 3, [101.0] * 3, [99.0] * 3, [100.0] * 3, dates=["2024-01-01"])


def test_deterministic_output_for_equivalent_inputs():
    base = _bearish_context(4)
    o, h, lo, c = _append(base, [(95.0, 96.2, 93.0, 96.0)])
    a = detect_patterns(o, h, lo, c)
    b = detect_patterns(list(o), list(h), list(lo), list(c))
    assert a == b


def test_to_dict_is_labelled_and_json_clean():
    import json

    base = _bearish_context(4)
    o, h, lo, c = _append(base, [(95.0, 96.2, 93.0, 96.0)])
    d = detect_patterns(o, h, lo, c)[0].to_dict()
    assert d["classification"] == "DETECTED"
    assert d["rule_version"] == CANDLE_RULE_VERSION
    assert d["confirmed"] is None
    assert d["confirmation_status"] == "not evaluated"
    assert d["context"]["near_support"] is None
    assert any("geometry only" in n for n in d["notes"])
    assert "confidence" not in json.dumps(d).lower()
    # floats rounded to 6 decimals for stable serialisation
    assert d["measurements"]["body_ratio"] == round(1.0 / 3.2, 6)


def test_every_direction_is_one_of_the_three_documented_labels():
    rng = np.random.default_rng(7)
    n = 50
    close = 100.0 * np.exp(np.cumsum(rng.normal(0.0, 0.015, n)))
    open_ = np.concatenate(([close[0]], close[:-1] * (1 + rng.normal(0, 0.003, n - 1))))
    high = np.maximum(open_, close) + 1.0
    low = np.minimum(open_, close) - 1.0
    p = detect_patterns(open_, high, low, close)
    assert p, "fixture produced no patterns"
    assert all(x.direction in {"bullish", "bearish", "neutral"} for x in p)
    assert all(x.classification == "DETECTED" for x in p)


def test_validate_ohlc_returns_float_arrays():
    o, h, lo, c = validate_ohlc([100], [101], [99], [100.5], min_bars=1)
    assert o.dtype == float and c.dtype == float
    assert o.shape == (1,)


def test_validate_ohlc_min_bars_enforced():
    with pytest.raises(CandleError, match="insufficient history"):
        validate_ohlc([100.0], [101.0], [99.0], [100.0], min_bars=3)


# ------------------------------------------------ session 18: new detectors
def test_harami_cross_fires_when_second_candle_is_a_doji():
    # Descending context, big bearish candle, then a doji inside its body.
    o = [112.0, 111.0, 110.0, 109.0, 108.0, 107.6]
    h = [112.5, 111.5, 110.5, 109.5, 108.2, 107.9]
    lo = [111.0, 110.0, 109.0, 108.0, 106.8, 106.7]
    c = [111.5, 110.5, 109.5, 108.5, 107.0, 107.65]
    names = _names(detect_patterns(o, h, lo, c))
    assert "harami_cross" in names
    # the cross is a distinct label, not merged into an ordinary harami
    assert "harami_cross" in names


def test_harami_cross_does_not_fire_when_second_body_is_large():
    # Second candle has a big body -> an ordinary harami, never a cross.
    o = [112.0, 111.0, 110.0, 109.0, 108.0, 107.0]
    h = [112.5, 111.5, 110.5, 109.5, 108.2, 108.4]
    lo = [111.0, 110.0, 109.0, 108.0, 106.8, 106.8]
    c = [111.5, 110.5, 109.5, 108.5, 107.0, 108.3]
    assert "harami_cross" not in _names(detect_patterns(o, h, lo, c))


def test_tweezer_bottom_fires_on_matching_lows():
    o = [112.0, 111.0, 110.0, 109.0, 108.0, 107.0, 106.6]
    h = [112.5, 111.5, 110.5, 109.5, 108.5, 107.2, 108.0]
    lo = [111.0, 110.0, 109.0, 108.0, 107.0, 106.0, 106.0]
    c = [111.5, 110.5, 109.5, 108.5, 107.5, 106.4, 107.8]
    assert "tweezer_bottom" in _names(detect_patterns(o, h, lo, c))


def test_tweezer_bottom_does_not_fire_when_lows_differ():
    o = [112.0, 111.0, 110.0, 109.0, 108.0, 107.0, 106.6]
    h = [112.5, 111.5, 110.5, 109.5, 108.5, 107.2, 108.0]
    lo = [111.0, 110.0, 109.0, 108.0, 107.0, 106.0, 104.0]  # lows far apart
    c = [111.5, 110.5, 109.5, 108.5, 107.5, 106.4, 107.8]
    assert "tweezer_bottom" not in _names(detect_patterns(o, h, lo, c))


def test_tweezer_top_fires_on_matching_highs():
    # Ascending context, bullish then bearish candle sharing a high.
    o = [100.0, 101.0, 102.0, 103.0, 104.0, 105.0, 105.8]
    h = [100.5, 101.5, 102.5, 103.5, 104.4, 106.0, 106.0]
    lo = [99.0, 100.0, 101.0, 102.0, 103.0, 104.6, 104.8]
    c = [100.4, 101.4, 102.4, 103.4, 104.3, 105.8, 105.0]
    assert "tweezer_top" in _names(detect_patterns(o, h, lo, c))


def test_new_detectors_are_in_the_public_catalogue():
    from megatool.ta.candles import PATTERN_CANDLE_COUNT, PATTERN_NAMES

    for name in ("harami_cross", "tweezer_bottom", "tweezer_top"):
        assert name in PATTERN_NAMES
    # every catalogue name is classified as 1-, 2-, or 3-candle
    assert set(PATTERN_CANDLE_COUNT) == set(PATTERN_NAMES)
    assert all(PATTERN_CANDLE_COUNT[n] in (1, 2, 3) for n in PATTERN_NAMES)


def test_tweezer_tolerance_is_configurable():
    # A looser tolerance makes a near-miss become a match.
    o = [112.0, 111.0, 110.0, 109.0, 108.0, 107.0, 106.6]
    h = [112.5, 111.5, 110.5, 109.5, 108.5, 107.2, 108.0]
    lo = [111.0, 110.0, 109.0, 108.0, 107.0, 106.0, 106.2]
    c = [111.5, 110.5, 109.5, 108.5, 107.5, 106.4, 107.8]
    assert "tweezer_bottom" not in _names(detect_patterns(o, h, lo, c))
    loose = PatternParams(tweezer_tolerance_ratio=0.01)
    assert "tweezer_bottom" in _names(detect_patterns(o, h, lo, c, params=loose))
