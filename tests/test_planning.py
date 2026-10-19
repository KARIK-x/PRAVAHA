"""Trade-planning arithmetic: every expectation computed by hand."""

from __future__ import annotations

import pytest

from megatool.planning import (
    PlanError,
    constraint_check,
    make_plan,
    plan_outcome,
    position_size,
)


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


# ----------------------------------------- portfolio constraint check (F11)
def _sizing(capital=50000.0, risk_pct=2.0, risk_per_share=10.0, price=100.0):
    """Hand-computed: budget 1,000 / 10 = 100 units, cash 10,000."""
    return position_size(capital, risk_pct, risk_per_share, price)


def test_constraint_check_current_and_post_trade_by_hand():
    out = constraint_check(
        symbol="nabil",
        entry=100.0,
        sizing=_sizing(),  # 100 units
        current_units=50,
        current_price=110.0,
        current_price_date="2026-10-12",
        valued_total=5500.0,  # only position: 50 x 110
        open_positions=1,
        max_weight_pct=40.0,
    )
    assert out["symbol"] == "NABIL" and out["checked"] is True
    cur = out["current"]
    assert cur["value"] == 5500.0 and cur["weight_pct"] == 100.0
    assert cur["price_date"] == "2026-10-12" and cur["weight_reason"] is None
    post = out["post_trade"]
    assert post["units"] == 150  # 50 held + 100 planned
    assert post["value_at_entry"] == 15000.0  # 150 x 100
    # denominator = 5,500 (existing, marked to close) + 100 x 100 (new capital)
    assert post["weight_pct"] == pytest.approx(15000 / 15500 * 100, abs=1e-4)
    assert post["within_limit"] is False and out["limit"]["breach"] is True
    assert out["limit"]["max_weight_pct"] == 40.0
    assert out["diversification"] == {"open_positions": 1, "symbol_already_held": True}
    assert "NEW capital" in post["funded_by"]


def test_constraint_check_within_limit_on_a_large_portfolio():
    out = constraint_check(
        symbol="BIG",
        entry=100.0,
        sizing=_sizing(),  # 100 units x 100 = 10,000 new
        current_units=0,
        valued_total=200000.0,
        open_positions=5,
    )
    post = out["post_trade"]
    # 10,000 / (200,000 + 10,000) = 4.7619%
    assert post["weight_pct"] == pytest.approx(10000 / 210000 * 100, abs=1e-4)
    assert post["within_limit"] is True and out["limit"]["breach"] is False
    assert out["diversification"]["symbol_already_held"] is False
    assert out["current"]["weight_pct"] is None  # none held: nothing to weight


def test_constraint_check_refuses_weights_for_a_held_but_unpriced_symbol():
    out = constraint_check(
        symbol="GHOST",
        entry=100.0,
        sizing=_sizing(),
        current_units=50,
        current_price=None,
        valued_total=10000.0,
        open_positions=1,
    )
    assert out["current"]["weight_pct"] is None
    assert "no usable stored close for GHOST" in out["current"]["weight_reason"]
    # The pre-existing shares would be missing from the denominator, so the
    # post-trade weight is refused too - never approximated.
    assert out["post_trade"]["checked"] is False
    assert "no usable stored close" in out["post_trade"]["reason"]
    assert out["checked"] is False and out["limit"]["breach"] is None


def test_constraint_check_without_sizing_computes_current_and_defers_post():
    out = constraint_check(
        symbol="NABIL",
        entry=100.0,
        sizing=None,
        current_units=50,
        current_price=110.0,
        valued_total=5500.0,
    )
    assert out["current"]["weight_pct"] == 100.0
    assert out["post_trade"]["checked"] is False
    assert "supply capital and risk_pct" in out["post_trade"]["reason"]
    assert out["checked"] is False and out["limit"]["breach"] is None


def test_constraint_check_without_symbol_never_guesses_held_status():
    out = constraint_check(symbol=None, entry=100.0, sizing=_sizing(), valued_total=100000.0)
    assert out["symbol"] is None
    assert out["diversification"]["symbol_already_held"] is None
    assert out["post_trade"]["checked"] is True  # aggregate sizing is still arithmetic


@pytest.mark.parametrize("bad", [0, -1, 100.1, float("nan")])
def test_constraint_check_rejects_impossible_limits(bad):
    with pytest.raises(PlanError, match="max_weight_pct"):
        constraint_check(symbol="X", entry=100.0, max_weight_pct=bad)


def test_constraint_check_zero_denominator_is_stated_with_the_sizing_warning():
    tiny = position_size(100, 1, 10, 1000)  # budget 1 cannot buy 1 unit -> 0
    assert tiny.units == 0 and tiny.warning
    out = constraint_check(symbol="X", entry=1000.0, sizing=tiny, valued_total=0.0)
    assert out["post_trade"]["checked"] is False
    assert "denominator is zero" in out["post_trade"]["reason"]
    assert out["warnings"][0] == tiny.warning


def test_constraint_check_warns_when_some_positions_cannot_be_valued():
    out = constraint_check(
        symbol="X",
        entry=100.0,
        sizing=_sizing(),
        valued_total=10000.0,
        unvalued_positions=2,
    )
    assert any("valued positions only" in w for w in out["warnings"])
    assert any("not advice" in w for w in out["warnings"])


# ---------------------------------------------------------------- F11 route
def test_planning_route_checks_portfolio_constraints(tmp_path):
    import numpy as np
    import pandas as pd
    from fastapi.testclient import TestClient

    from megatool.api import create_app
    from megatool.db import init_app_db
    from megatool.market_store import MarketStore
    from megatool.portfolio import add_transaction

    init_app_db()  # isolated PATHS.app_db (conftest)
    add_transaction(
        {
            "symbol": "NABIL",
            "side": "buy",
            "quantity": 50,
            "price": 100.0,
            "traded_at": "2026-10-01T10:00:00",
        }
    )
    store = MarketStore(tmp_path / "market.duckdb")
    n = 30
    closes = np.linspace(100.0, 110.0, n)
    store.upsert_bars(
        pd.DataFrame(
            {
                "symbol": ["NABIL"] * n,
                "trading_date": pd.bdate_range(end="2026-10-12", periods=n),
                "open": closes,
                "high": closes * 1.01,
                "low": closes * 0.99,
                "close": closes,
                "volume": [10_000] * n,
                "turnover": closes * 10_000,
                "source": ["SYNTHETIC-TEST-FIXTURE"] * n,
                "retrieved_at": [pd.Timestamp("2026-10-12")] * n,
                "validation_status": ["valid"] * n,
            }
        )
    )
    app = create_app(store=store)
    with TestClient(app) as client:
        d = client.post(
            "/api/planning",
            json={
                "entry": 100.0,
                "stop": 90.0,
                "target": 120.0,
                "capital": 50000.0,
                "risk_pct": 2.0,
                "symbol": "nabil",
            },
        ).json()
        assert d["sizing"]["units"] == 100
        pc = d["portfolio_check"]
        assert pc["checked"] is True
        assert pc["current"]["units"] == 50
        assert pc["current"]["price"] == pytest.approx(110.0)
        assert pc["current"]["value"] == 5500.0
        assert pc["current"]["weight_pct"] == 100.0
        assert pc["post_trade"]["units"] == 150
        assert pc["post_trade"]["weight_pct"] == pytest.approx(96.7742, abs=1e-3)
        assert pc["limit"]["breach"] is True  # 96.8% > 40%
        # No symbol -> the check says what is missing instead of guessing.
        d2 = client.post(
            "/api/planning", json={"entry": 100.0, "stop": 90.0, "target": 120.0}
        ).json()
        assert d2["portfolio_check"]["checked"] is False
        assert "no symbol" in d2["portfolio_check"]["reason"]
        # Symbol without sizing -> current computed, post-trade deferred.
        d3 = client.post(
            "/api/planning",
            json={"entry": 100.0, "stop": 90.0, "target": 120.0, "symbol": "NABIL"},
        ).json()
        assert d3["portfolio_check"]["current"]["weight_pct"] == 100.0
        assert d3["portfolio_check"]["post_trade"]["checked"] is False
        assert "supply capital and risk_pct" in d3["portfolio_check"]["post_trade"]["reason"]
    store.close()


# ------------------------- verified buy-cost estimate (C3/D-y, 2026-10-15)
def test_entry_cost_estimate_uses_the_verified_tier_table():
    from megatool.planning import entry_cost_estimate

    est = entry_cost_estimate(100_000.0, on_date="2026-08-03")
    # 100k sits in the >50k-5L slab: commission 0.33% = 330.00, SEBON 15.00.
    assert est["commission"] == pytest.approx(330.00)
    assert est["sebon"] == pytest.approx(15.00)
    assert est["dp"] == 0.0  # a buy has no DP charge
    assert est["total"] == pytest.approx(345.00)
    assert est["schedule"] == "official-2083-84"


def test_entry_cost_estimate_small_order_pays_the_minimum_commission():
    from megatool.planning import entry_cost_estimate

    est = entry_cost_estimate(5_000.0, on_date="2026-08-03")
    assert est["commission"] == 18.00  # 0.36% of 5,000, above the NPR 10 floor
    tiny = entry_cost_estimate(1_000.0, on_date="2026-08-03")
    assert tiny["commission"] == 10.00  # 0.36% of 1,000 is 3.60; the floor binds


def test_entry_cost_estimate_rejects_bad_values():
    from megatool.planning import PlanError, entry_cost_estimate

    for bad in (0, -5, "x", None):
        with pytest.raises(PlanError):
            entry_cost_estimate(bad)
