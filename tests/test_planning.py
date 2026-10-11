"""Trade-planning arithmetic: every expectation computed by hand."""

from __future__ import annotations

import pytest

from megatool.planning import PlanError, make_plan, plan_outcome, position_size


def test_basic_plan_arithmetic():
    p = make_plan(entry=100, stop=90, target=120)
    assert p.risk_per_share == pytest.approx(10)
    assert p.reward_per_share == pytest.approx(20)
    assert p.risk_reward == pytest.approx(2.0)
    assert p.risk_pct_of_entry == pytest.approx(10.0)
    assert p.reward_pct_of_entry == pytest.approx(20.0)
    assert p.invalidation_pct == pytest.approx(-10.0)
    assert p.target_pct == pytest.approx(20.0)


def test_plan_accepts_string_numbers_from_a_form():
    p = make_plan(entry="100", stop="95", target="110")
    assert p.risk_per_share == pytest.approx(5)


def test_stop_must_be_below_entry():
    with pytest.raises(PlanError, match="shorting"):
        make_plan(entry=100, stop=110, target=120)


def test_stop_equal_to_entry_is_rejected():
    with pytest.raises(PlanError, match="below the entry"):
        make_plan(entry=100, stop=100, target=120)


def test_target_must_be_above_entry():
    with pytest.raises(PlanError, match="target must be above"):
        make_plan(entry=100, stop=90, target=95)


@pytest.mark.parametrize("value", [0, -5])
def test_non_positive_prices_rejected(value):
    with pytest.raises(PlanError, match="must be > 0"):
        make_plan(entry=value, stop=90, target=120)


def test_non_numeric_price_rejected():
    with pytest.raises(PlanError, match="must be a number"):
        make_plan(entry="one hundred", stop=90, target=120)


def test_position_size_from_risk_budget():
    # capital 100k, risk 2% = 2,000 budget, 5 risk/share -> 400 units
    s = position_size(capital=100_000, risk_pct=2, risk_per_share=5, price=100)
    assert s.units == 400
    assert s.cash_used == pytest.approx(40_000)
    assert s.actual_risk == pytest.approx(2_000)
    assert s.actual_risk_pct == pytest.approx(2.0)
    assert s.remainder_cash == pytest.approx(60_000)
    assert s.rounded_down is False


def test_position_size_is_capped_by_affordability():
    # Risk budget would allow 200 units, but capital only buys 2.
    s = position_size(capital=10_000, risk_pct=2, risk_per_share=1, price=5_000)
    assert s.units == 2
    assert s.cash_used == pytest.approx(10_000)
    assert s.remainder_cash == pytest.approx(0.0)
    # actual risk (2 units * 1) is far below the 2% budget - reported honestly
    assert s.actual_risk_pct == pytest.approx(0.02)


def test_position_size_rounds_down_not_up():
    # budget 2,000 / risk 600 = 3.33 -> 3 units (never 4)
    s = position_size(capital=100_000, risk_pct=2, risk_per_share=600, price=100)
    assert s.units == 3
    assert s.rounded_down is True
    assert s.actual_risk <= 2_000


@pytest.mark.parametrize(
    "kwargs",
    [
        {"capital": 0, "risk_pct": 2, "risk_per_share": 5, "price": 100},
        {"capital": 100, "risk_pct": 0, "risk_per_share": 5, "price": 100},
        {"capital": 100, "risk_pct": 101, "risk_per_share": 5, "price": 100},
        {"capital": 100, "risk_pct": 2, "risk_per_share": 0, "price": 100},
        {"capital": 100, "risk_pct": 2, "risk_per_share": 5, "price": -1},
    ],
)
def test_position_size_validation(kwargs):
    with pytest.raises(PlanError):
        position_size(**kwargs)


def test_outcome_when_target_is_hit():
    o = plan_outcome(entry=100, stop=90, target=120, exit_price=125)
    assert o["result"] == "target"
    assert o["r_multiple"] == pytest.approx(2.5)
    assert o["planned_r"] == pytest.approx(2.0)
    assert "historical measurement" in o["note"]


def test_outcome_when_stop_is_hit():
    o = plan_outcome(entry=100, stop=90, target=120, exit_price=88)
    assert o["result"] == "stop"
    assert o["r_multiple"] == pytest.approx(-1.2)


def test_outcome_when_neither_level_is_reached():
    o = plan_outcome(entry=100, stop=90, target=120, exit_price=105)
    assert o["result"] == "neither"
    assert o["r_multiple"] == pytest.approx(0.5)


def test_exit_exactly_at_target_counts_as_target():
    assert plan_outcome(100, 90, 120, 120)["result"] == "target"


def test_exit_exactly_at_stop_counts_as_stop():
    assert plan_outcome(100, 90, 120, 90)["result"] == "stop"
