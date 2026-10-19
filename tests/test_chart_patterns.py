"""Chart-pattern detection tests — hand-built geometries, not market history.

Every fixture is a piecewise-linear price path with deliberate, hand-placed
pivots, so the expected pivots, necklines and confirmation states can be read
off the input by hand. Nothing here asserts anything about real NEPSE prices.
"""

from __future__ import annotations

import numpy as np
import pytest

from megatool.ta.patterns import PATTERN_TYPES, PatternConfig, detect_patterns


def _series(points: list[tuple[int, float]], n: int) -> np.ndarray:
    """Piecewise-linear price path through ``points`` sampled on ``range(n)``."""
    xs = np.array([p[0] for p in points], dtype=float)
    ys = np.array([p[1] for p in points], dtype=float)
    return np.interp(np.arange(n, dtype=float), xs, ys)


def _detect(points, n, **cfg_kwargs):
    close = _series(points, n)
    cfg = PatternConfig(min_prominence=0.0, min_bars=cfg_kwargs.pop("min_bars", 60), **cfg_kwargs)
    return detect_patterns(close, close, close, config=cfg)


def _patterns(result):
    return {p["pattern"]: p for p in result["patterns"]}


# --------------------------------------------------------------------- tops/bottoms


def test_double_top_is_detected_and_confirmed_by_the_neckline_break():
    n = 120
    pts = [(0, 100), (10, 110), (20, 102), (30, 110), (40, 95), (119, 95)]
    r = _detect(pts, n)
    assert r["available"] is True
    p = _patterns(r)["double_top"]
    assert p["direction"] == "bearish"
    assert p["status"] == "confirmed"
    assert p["breakout_level"] == pytest.approx(102.0, abs=1e-6)
    assert p["target_level"] == pytest.approx(102.0 - 8.0, abs=1e-6)
    # Pivots: high, neck low, high.
    kinds = [pv["kind"] for pv in p["pivots"]]
    assert kinds == ["high", "low", "high"]


def test_double_top_without_a_neckline_break_is_only_forming():
    n = 120
    pts = [(0, 100), (10, 110), (20, 102), (30, 110), (40, 95), (119, 95)]
    r = _detect(pts, n)  # full data -> confirmed
    assert _patterns(r)["double_top"]["status"] == "confirmed"
    # Truncate before the breakdown: the same shape must be reported "forming".
    close = _series(pts, n)
    cfg = PatternConfig(min_prominence=0.0, min_bars=60)
    r2 = detect_patterns(close, close, close, config=cfg, last_index=34)
    got = _patterns(r2).get("double_top")
    assert got is not None and got["status"] == "forming"


def test_double_bottom_is_bullish_and_confirmed_on_an_upward_break():
    n = 120
    pts = [(0, 100), (10, 90), (20, 98), (30, 90), (40, 105), (119, 105)]
    p = _patterns(_detect(pts, n))["double_bottom"]
    assert p["direction"] == "bullish"
    assert p["status"] == "confirmed"
    assert p["breakout_level"] == pytest.approx(98.0, abs=1e-6)


def test_triple_top_is_detected():
    n = 140
    pts = [(0, 100), (10, 110), (20, 102), (30, 110), (40, 102), (50, 110), (60, 95), (139, 95)]
    p = _patterns(_detect(pts, n))["triple_top"]
    assert p["direction"] == "bearish"
    assert p["status"] == "confirmed"


def test_head_and_shoulders_requires_the_head_to_be_the_most_extreme():
    n = 140
    good = [(0, 100), (10, 108), (20, 102), (30, 115), (40, 103), (50, 108), (60, 95), (139, 95)]
    p = _patterns(_detect(good, n))["head_and_shoulders"]
    assert p["status"] == "confirmed"
    # A shape whose "head" is not the highest pivot is not a head-and-shoulders.
    flat = [(0, 100), (10, 110), (20, 102), (30, 110), (40, 103), (50, 109), (60, 95), (139, 95)]
    assert "head_and_shoulders" not in _patterns(_detect(flat, n))


# -------------------------------------------------------------------- triangles/wedges


def test_ascending_triangle_flat_highs_rising_lows():
    n = 140
    pts = [(0, 100), (10, 110), (25, 100), (40, 110), (55, 106), (139, 106)]
    p = _patterns(_detect(pts, n))["ascending_triangle"]
    assert p["direction"] == "bullish"
    assert p["status"] == "forming"


def test_rising_wedge_is_bearish_and_converging():
    n = 140
    pts = [(0, 90), (10, 100), (25, 90), (45, 112), (60, 106), (139, 106)]
    p = _patterns(_detect(pts, n))["rising_wedge"]
    assert p["direction"] == "bearish"


# ----------------------------------------------------------------------------- flags


def test_bull_flag_pole_then_tight_consolidation():
    n = 60
    pts = [(0, 100), (34, 100), (49, 120), (59, 120)]
    p = _patterns(_detect(pts, n))["bull_flag"]
    assert p["direction"] == "bullish"
    assert p["breakout_level"] == pytest.approx(120.0, abs=1e-6)


def test_channel_breakout_up_on_a_new_high():
    n = 120
    pts = [(0, 100), (118, 100), (119, 105)]
    p = _patterns(_detect(pts, n))["channel_breakout_up"]
    assert p["status"] == "confirmed"
    assert p["breakout_level"] == pytest.approx(100.0, abs=1e-6)


# ------------------------------------------------------------------------ edge cases


def test_insufficient_history_is_unavailable_not_empty():
    n = 20
    r = _detect([(0, 100), (19, 110)], n)
    assert r["available"] is False
    assert "required" in r["unavailable_reason"]
    assert r["patterns"] == []


def test_non_finite_input_is_refused():
    close = np.full(120, 100.0)
    close[10] = np.nan
    r = detect_patterns(close, close, close, config=PatternConfig(min_bars=60))
    assert r["available"] is False
    assert "non-finite" in r["unavailable_reason"]


def test_no_patterns_on_a_clean_monotonic_ramp():
    # A straight ramp has no pivots that satisfy prominence: nothing should be
    # labelled. (Channel logic only fires on an actual new extreme.)
    n = 120
    r = _detect([(0, 100), (119, 160)], n)
    found = {p["pattern"] for p in r["patterns"]}
    assert "double_top" not in found and "head_and_shoulders" not in found
    assert "ascending_triangle" not in found


def test_quality_score_is_a_documented_symmetry_rule():
    # Touches within 0% of each other score the documented 100-point max.
    n = 120
    pts = [(0, 100), (10, 110), (20, 102), (30, 110), (40, 95), (119, 95)]
    p = _patterns(_detect(pts, n))["double_top"]
    assert p["quality"] == pytest.approx(100.0, abs=1e-6)
    # A looser tolerance cannot exceed 100.
    assert 0.0 <= p["quality"] <= 100.0


def test_every_emitted_pattern_is_in_the_declared_catalogue():
    n = 140
    pts = [(0, 100), (10, 110), (20, 102), (30, 115), (40, 103), (50, 108), (60, 95), (139, 95)]
    for p in _detect(pts, n)["patterns"]:
        assert p["pattern"] in PATTERN_TYPES
        assert PATTERN_TYPES[p["pattern"]] == p["direction"]
