"""Tests for the Fibonacci module.

Every expected value in this file is computed by hand from the formula in
``megatool.ta.fibonacci`` (``retracement = end - range*r``,
``extension = end + range*r``), not by calling the implementation twice.
"""

from __future__ import annotations

import math

import pytest

from megatool.ta.fibonacci import (
    DEFAULT_EXTENSIONS,
    DEFAULT_RETRACEMENTS,
    FibonacciError,
    levels_for,
)

# SYNTHETIC FIXTURE — hand-chosen anchors, not market data.


def test_default_level_sets_are_the_documented_ones():
    assert DEFAULT_RETRACEMENTS == (0.236, 0.382, 0.5, 0.618, 0.786)
    assert DEFAULT_EXTENSIONS == (1.272, 1.382, 1.5, 1.618, 2.0, 2.618)


def test_upward_retracement_hand_computed():
    # start 100 -> end 150, range +50.
    out = levels_for(100, 150)
    prices = {row["ratio"]: row["price"] for row in out.retracements}
    assert prices[0.236] == pytest.approx(150 - 50 * 0.236, abs=1e-9)
    assert prices[0.382] == pytest.approx(150 - 50 * 0.382, abs=1e-9)
    assert prices[0.5] == pytest.approx(125.0, abs=1e-9)
    assert prices[0.618] == pytest.approx(119.1, abs=1e-9)
    assert prices[0.786] == pytest.approx(150 - 50 * 0.786, abs=1e-9)
    assert out.direction == "up"


def test_upward_extension_hand_computed():
    out = levels_for(100, 150)
    prices = {row["ratio"]: row["price"] for row in out.extensions}
    assert prices[1.272] == pytest.approx(150 + 50 * 1.272, abs=1e-9)
    assert prices[1.618] == pytest.approx(230.9, abs=1e-9)
    assert prices[2.0] == pytest.approx(250.0, abs=1e-9)
    assert prices[2.618] == pytest.approx(150 + 50 * 2.618, abs=1e-9)


def test_downward_retracement_hand_computed():
    # start 150 (high) -> end 100 (low), range -50.
    out = levels_for(150, 100)
    prices = {row["ratio"]: row["price"] for row in out.retracements}
    assert prices[0.618] == pytest.approx(100 - (-50) * 0.618, abs=1e-9)
    assert prices[0.618] == pytest.approx(130.9, abs=1e-9)
    assert prices[0.5] == pytest.approx(125.0, abs=1e-9)
    assert out.direction == "down"


def test_downward_extension_hand_computed():
    out = levels_for(150, 100)
    prices = {row["ratio"]: row["price"] for row in out.extensions}
    assert prices[1.618] == pytest.approx(100 + (-50) * 1.618, abs=1e-9)
    assert prices[1.618] == pytest.approx(19.1, abs=1e-9)


def test_reversed_anchor_order_mirrors_the_result():
    up = levels_for(100, 150)
    down = levels_for(150, 100)
    up_ret = {row["ratio"]: row["price"] for row in up.retracements}
    down_ret = {row["ratio"]: row["price"] for row in down.retracements}
    # A retracement of the same depth lands the same distance from `end` on
    # both sides, so the two tables are mirror images about the midpoint 125.
    for ratio in up_ret:
        assert up_ret[ratio] + down_ret[ratio] == pytest.approx(250.0, abs=1e-9)
    assert up.direction == "up"
    assert down.direction == "down"


def test_retracement_stays_inside_the_move_and_extension_beyond():
    out = levels_for(100, 150)
    for row in out.retracements:
        assert 100.0 <= row["price"] <= 150.0
    for row in out.extensions:
        assert row["price"] >= 150.0


def test_downward_retracement_stays_inside_and_extension_below():
    out = levels_for(150, 100)
    for row in out.retracements:
        assert 100.0 <= row["price"] <= 150.0
    for row in out.extensions:
        assert row["price"] <= 100.0


def test_fifty_percent_is_labelled_convention_not_fibonacci():
    out = levels_for(100, 150)
    families = {row["ratio"]: row["family"] for row in out.retracements}
    assert families[0.5] == "convention"
    for ratio in (0.236, 0.382, 0.618, 0.786):
        assert families[ratio] == "fibonacci"
    # Extensions are all genuine ratios.
    assert {row["family"] for row in out.extensions} == {"fibonacci"}


def test_custom_level_set_is_honoured_exactly():
    out = levels_for(100, 150, retracements=[0.5], extensions=[1.618])
    assert [row["ratio"] for row in out.retracements] == [0.5]
    assert [row["ratio"] for row in out.extensions] == [1.618]


def test_empty_level_sets_yield_no_rows():
    out = levels_for(100, 150, retracements=[], extensions=[])
    assert out.retracements == []
    assert out.extensions == []


def test_equal_anchors_are_rejected():
    with pytest.raises(FibonacciError, match="equal"):
        levels_for(100.0, 100.0)


def test_empty_and_insufficient_input_rejected():
    with pytest.raises(FibonacciError):
        levels_for(float("nan"), 150.0)
    with pytest.raises(FibonacciError):
        levels_for(100.0, float("inf"))


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), -1.0])
def test_non_finite_or_negative_ratios_rejected(bad):
    with pytest.raises(FibonacciError):
        levels_for(100, 150, retracements=[bad])


def test_zero_ratio_is_allowed_and_returns_the_end_anchor():
    out = levels_for(100, 150, retracements=[0.0])
    assert out.retracements[0]["price"] == pytest.approx(150.0)


def test_non_positive_anchor_prices_rejected():
    with pytest.raises(FibonacciError, match="positive"):
        levels_for(0.0, 150.0)
    with pytest.raises(FibonacciError, match="positive"):
        levels_for(100.0, -5.0)


def test_float_tolerance_on_ratios():
    out = levels_for(100, 150, retracements=[0.6180000000000001])
    # Ratio is stored as given; price must match the same ratio exactly.
    assert out.retracements[0]["price"] == pytest.approx(150 - 50 * 0.6180000000000001)


def test_indices_are_carried_through_for_the_ui():
    out = levels_for(100, 150, start_index=12, end_index=47)
    assert out.start_index == 12
    assert out.end_index == 47
    d = out.to_dict()
    assert d["anchors"]["start_index"] == 12
    assert d["anchors"]["end_index"] == 47


def test_to_dict_states_the_formula_and_range():
    d = levels_for(100, 150).to_dict()
    assert d["formula"]["retracement"] == "end - range * r"
    assert d["formula"]["extension"] == "end + range * r"
    assert d["anchors"]["range"] == pytest.approx(50.0)
    assert d["direction"] == "up"


def test_results_are_deterministic():
    a = levels_for(100, 150).to_dict()
    b = levels_for(100, 150).to_dict()
    assert a == b


def test_no_non_finite_prices_in_output():
    out = levels_for(100, 150)
    for row in out.retracements + out.extensions:
        assert math.isfinite(row["price"])
        assert math.isfinite(row["ratio"])
