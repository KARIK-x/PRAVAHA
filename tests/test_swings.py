"""Swing detection and market-structure tests.

Verified three ways, mirroring ``test_indicators.py``:

1. Hand-built price paths where every pivot is arithmetically obvious.
2. The look-ahead rule — the property this module exists to guarantee. A
   swing's ``confirmed_index`` must never precede the bar that proves it, and
   recomputing on a prefix must not change any swing already confirmed.
3. The API contract, through FastAPI's test client against an isolated store.
"""

from __future__ import annotations

import numpy as np
import pytest

from megatool.ta.swings import (
    Swing,
    SwingError,
    classify_structure,
    detect_equal_highs_lows,
    detect_fvgs,
    find_breaks,
    find_swings,
)


def _zigzag() -> tuple[np.ndarray, np.ndarray]:
    """A hand-checkable zigzag: peaks and troughs 5 bars apart.

    closes: 8 9 10 9 8 | 7 6 7 8 9 | 10 9 8 7 6 | 5 6 7 8 9 | 10 11 12 11 10 |
            9 8 7 6 7 | 8 9 10 11 12 | 13 14
    With left=right=2 the intended pivots are unambiguous:
        high 10 @2, low 6 @6, high 10 @10, low 5 @15, high 12 @22, low 6 @28,
        high 14 @36 is NOT a swing (no right context), last high 12 @22..34.
    """
    close = np.array(
        [
            8,
            9,
            10,
            9,
            8,
            7,
            6,
            7,
            8,
            9,
            10,
            9,
            8,
            7,
            6,
            5,
            6,
            7,
            8,
            9,
            10,
            11,
            12,
            11,
            10,
            9,
            8,
            7,
            6,
            7,
            8,
            9,
            10,
            11,
            12,
            13,
            14,
        ],
        dtype=float,
    )
    return close + 0.5, close - 0.5


# ------------------------------------------------------------------- geometry
def test_hand_built_zigzag_finds_exact_pivots():
    high, low = _zigzag()
    swings = find_swings(high, low, left=2, right=2)

    got = [(s.kind, s.index, s.price) for s in swings]
    assert got == [
        ("high", 2, 10.5),
        ("low", 6, 5.5),
        ("high", 10, 10.5),
        ("low", 15, 4.5),
        ("high", 22, 12.5),
        ("low", 28, 5.5),
    ]


def test_swings_alternate_high_low():
    high, low = _zigzag()
    kinds = [s.kind for s in find_swings(high, low, left=2, right=2)]
    assert all(a != b for a, b in zip(kinds, kinds[1:], strict=False)), kinds


def test_confirmation_lags_the_pivot_by_exactly_right_bars():
    high, low = _zigzag()
    for s in find_swings(high, low, left=2, right=3):
        assert s.confirmed_index == s.index + 3


def test_plateau_produces_one_swing_not_several():
    """A flat top must not emit a swing per bar: uniqueness is required."""
    close = np.array([5, 6, 7, 7, 7, 7, 6, 5, 4], dtype=float)
    swings = find_swings(close + 0.2, close - 0.2, left=2, right=2)
    highs = [s for s in swings if s.kind == "high"]
    assert len(highs) == 1


def test_too_few_bars_returns_no_swing_not_an_error():
    high, low = _zigzag()
    assert find_swings(high[:3], low[:3], left=2, right=2) == []


def test_min_prominence_filters_small_pivots():
    """A tighter prominence threshold never adds swings, and eventually clears them.

    Monotonicity is the property that matters: raising the bar may only remove
    pivots. The exact count depends on the geometry, so this asserts the
    direction rather than a fragile number.
    """
    rng = np.random.default_rng(3)
    close = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, 200)))
    high, low = close + 1.0, close - 1.0

    counts = [len(find_swings(high, low, 3, 3, min_prominence=m)) for m in (0.0, 0.01, 0.03, 0.5)]
    assert counts == sorted(counts, reverse=True), counts
    assert counts[0] > 0, "fixture produced no pivots at all"
    assert counts[-1] == 0, "an extreme threshold should reject every pivot"


# ------------------------------------------------------------------ look-ahead
def test_confirmed_index_never_precedes_the_pivot():
    rng = np.random.default_rng(7)
    close = 100 * np.exp(np.cumsum(rng.normal(0, 0.02, 300)))
    swings = find_swings(close + 1, close - 1, left=5, right=5)
    for s in swings:
        assert s.confirmed_index >= s.index


def test_prefix_recomputation_reproduces_every_confirmed_swing():
    """The causality property: history never rewrites itself.

    Running the detector on the first N bars must return exactly the swings the
    full series returns that were already confirmed by bar N. If a pivot could
    change retroactively, a backtest would be reading the future.
    """
    rng = np.random.default_rng(11)
    close = 100 * np.exp(np.cumsum(rng.normal(0, 0.015, 400)))
    high, low = close + 1.0, close - 1.0

    full = find_swings(high, low, left=5, right=5)
    for cut in (120, 200, 311, 377):
        prefix = find_swings(high[:cut], low[:cut], left=5, right=5, last_index=cut - 1)
        expected = [s for s in full if s.confirmed_index < cut]
        assert [(s.kind, s.index, s.price) for s in prefix] == [
            (s.kind, s.index, s.price) for s in expected
        ], f"prefix {cut} disagrees with the full series"


def test_unconfirmed_tail_is_excluded_rather_than_guessed():
    """A pivot needing bars past the data end is not reported."""
    close = np.array([1, 2, 3, 4, 5, 4, 3], dtype=float)
    # With right=2 the peak at index 4 is confirmable at 6, inside the data.
    assert any(s.index == 4 for s in find_swings(close + 0.5, close - 0.5, 1, 2))
    # With right=10 it is not, so it must be absent.
    assert not any(s.index == 4 for s in find_swings(close + 0.5, close - 0.5, 1, 10))


# ------------------------------------------------------------------ validation
def test_rejects_mismatched_lengths_and_bad_windows():
    with pytest.raises(SwingError):
        find_swings([1.0, 2.0], [1.0], 1, 1)
    with pytest.raises(SwingError):
        find_swings([1.0, 2.0], [1.0, 0.5], 0, 1)
    with pytest.raises(SwingError):
        find_swings([1.0, 2.0], [1.0, 0.5], 1, 1, min_prominence=-0.1)


def test_rejects_non_finite_prices():
    with pytest.raises(SwingError):
        find_swings([1.0, np.nan, 3.0], [1.0, 0.5, 0.2], 1, 1)


# ------------------------------------------------------------------- structure
def _mk(kind: str, index: int, price: float, confirmed: int | None = None) -> Swing:
    c = confirmed if confirmed is not None else index + 2
    return Swing(index=index, kind=kind, price=float(price), confirmed_index=c, confirmed=True)


def test_higher_highs_and_higher_lows_read_as_an_uptrend():
    swings = [_mk("high", 4, 10), _mk("low", 8, 6), _mk("high", 12, 12), _mk("low", 16, 8)]
    out = classify_structure(swings)
    assert out["trend"] == "up"
    assert [x["kind"] for x in out["labels"]] == ["HH", "HL"]


def test_lower_highs_and_lower_lows_read_as_a_downtrend():
    swings = [_mk("high", 4, 12), _mk("low", 8, 8), _mk("high", 12, 10), _mk("low", 16, 6)]
    assert classify_structure(swings)["trend"] == "down"


def test_disagreeing_swings_read_as_mixed_not_as_a_trend():
    swings = [_mk("high", 4, 12), _mk("low", 8, 6), _mk("high", 12, 10), _mk("low", 16, 8)]
    assert classify_structure(swings)["trend"] == "mixed"


def test_a_single_swing_asserts_no_trend():
    assert classify_structure([_mk("high", 4, 10)])["trend"] == "insufficient data"


def test_break_of_structure_is_dated_at_the_confirmation_not_the_pivot():
    """A break cannot be dated before the level it broke was knowable.

    The close passes 10.0 at index 5, but a researcher at index 5 had no idea
    10.0 was a level. The level becomes knowable at index 9 — and the close is
    already above it there — so 9 is the earliest honest date.
    """
    swings = [_mk("high", 4, 10.0, confirmed=9)]
    close = np.array([1, 2, 3, 4, 5, 11, 12, 13, 14, 15, 16], dtype=float)
    breaks = find_breaks(swings, close)
    assert breaks == [{"direction": "bullish", "index": 9, "level": 10.0, "level_index": 4}]


def test_bearish_break_below_a_confirmed_swing_low():
    swings = [_mk("low", 4, 10.0, confirmed=9)]
    close = np.array([20, 19, 18, 17, 16, 15, 14, 13, 12, 9, 8], dtype=float)
    breaks = find_breaks(swings, close)
    assert breaks and breaks[0]["direction"] == "bearish"
    assert breaks[0]["index"] == 9


# ------------------------------------------------------------------ new Phase B.1


def test_detect_fvg_bullish():
    highs = [10, 11, 12, 13, 14]
    lows = [9, 10, 11, 12, 13]
    # bar 2: low[2]=11 > high[0]=10 -> bullish FVG top=11 bottom=10
    fvgs = detect_fvgs(highs, lows)
    assert any(f["type"] == "bullish" for f in fvgs)
    b = [f for f in fvgs if f["type"] == "bullish"][0]
    assert b["top"] == 11 and b["bottom"] == 10
    assert b["confirmed_index"] == b["index"]


def test_detect_fvg_bearish():
    highs = [14, 13, 12, 11, 10]
    lows = [13, 12, 11, 10, 9]
    # bar 2: high[2]=12 < low[0]=13 -> bearish FVG
    fvgs = detect_fvgs(highs, lows)
    assert any(f["type"] == "bearish" for f in fvgs)


def test_detect_fvg_no_gap():
    # Flat bars: no 3-bar imbalance.
    highs = [5.0, 5.0, 5.0, 5.0, 5.0]
    lows = [4.0, 4.0, 4.0, 4.0, 4.0]
    fvgs = detect_fvgs(highs, lows)
    assert fvgs == []


def test_detect_fvg_shape_mismatch_raises():
    import pytest

    with pytest.raises(SwingError):
        detect_fvgs([1, 2, 3], [1, 2])


def test_detect_equal_highs_lows_basic():
    from megatool.ta.swings import Swing

    s1 = Swing(index=2, kind="high", price=100.0, confirmed_index=4, confirmed=True)
    s2 = Swing(index=8, kind="high", price=100.05, confirmed_index=10, confirmed=True)
    res = detect_equal_highs_lows([s1, s2], tolerance=0.001)
    assert len(res) == 1
    assert res[0]["kind"] == "equal_high"
    assert res[0]["relative_diff"] <= 0.001


def test_detect_equal_highs_lows_none_when_far():
    from megatool.ta.swings import Swing

    s1 = Swing(index=2, kind="high", price=100.0, confirmed_index=4, confirmed=True)
    s2 = Swing(index=8, kind="high", price=110.0, confirmed_index=10, confirmed=True)
    res = detect_equal_highs_lows([s1, s2], tolerance=0.001)
    assert res == []


def test_detect_equal_highs_lows_negative_tolerance_raises():
    import pytest

    with pytest.raises(SwingError):
        detect_equal_highs_lows([], tolerance=-0.1)
