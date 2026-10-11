"""Backtest engine tests.

Every expectation here is computed by hand from a synthetic fixture, so a
failure means the engine is wrong rather than "the fixture moved". Synthetic
data is labelled and never mixed with real records.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from megatool.backtest import (
    STRATEGIES,
    BacktestConfig,
    always_in,
    build_strategy,
    cagr,
    max_drawdown,
    never_in,
    run_backtest,
    sharpe_ratio,
    sma_cross,
)

RETRIEVED = pd.Timestamp("2026-10-11 00:00:00")


def _df(closes, opens=None, highs=None, lows=None) -> pd.DataFrame:
    closes = [float(c) for c in closes]
    n = len(closes)
    opens = [float(o) for o in opens] if opens is not None else list(closes)
    return pd.DataFrame(
        {
            "symbol": ["TEST"] * n,
            "trading_date": pd.bdate_range("2026-01-01", periods=n),
            "open": opens,
            "high": highs or [c * 1.01 for c in closes],
            "low": lows or [c * 0.99 for c in closes],
            "close": closes,
            "volume": [1000] * n,
            "source": ["SYNTHETIC-TEST-FIXTURE"] * n,
            "retrieved_at": [RETRIEVED] * n,
            "validation_status": ["valid"] * n,
        }
    )


def _sig(values):
    """Constant-signal strategy function."""
    arr = np.asarray(values, dtype=np.int8)
    return lambda _df: arr.copy()


# ------------------------------------------------------------------- metrics
def test_max_drawdown_known_series():
    # peak 120, trough 60 -> -50%
    assert max_drawdown([100, 120, 60, 90]) == pytest.approx(-0.5)


def test_max_drawdown_monotone_rise_is_zero():
    assert max_drawdown([1, 2, 3, 4]) == 0.0


def test_max_drawdown_empty_is_zero():
    assert max_drawdown([]) == 0.0


def test_sharpe_is_none_when_variance_is_zero():
    assert sharpe_ratio([0.01, 0.01, 0.01, 0.01]) is None


def test_sharpe_is_none_for_too_few_points():
    assert sharpe_ratio([0.01]) is None
    assert sharpe_ratio([]) is None


def test_cagr_of_one_year_doubling():
    # 365.25 days used as the year length, so a full-year double ~ 100%
    assert cagr(100.0, 200.0, 365.25) == pytest.approx(1.0)


def test_cagr_rejects_degenerate_inputs():
    assert cagr(0.0, 100.0, 365.0) is None
    assert cagr(100.0, 100.0, 0.0) is None


# --------------------------------------------------------------- execution
def test_signal_on_bar_zero_fills_on_bar_one_next_open():
    # No lookahead: a signal known only at bar 0 cannot fill at bar 0.
    df = _df([100] * 5)
    res = run_backtest(
        df,
        _sig([1, 0, 0, 0, 0]),
        BacktestConfig(initial_cash=1000, fee_rate=0.0, execution="next_open"),
        symbol="TEST",
        strategy="probe",
    )
    assert len(res.trades) == 1
    trade = res.trades[0]
    assert trade["entry_date"] == str(df["trading_date"].iloc[1].date())
    assert trade["exit_date"] == str(df["trading_date"].iloc[2].date())
    assert trade["pnl"] == pytest.approx(0.0)
    # Filled at bar 1's open and exited at bar 2's open: the position is on the
    # books at bar 1's close only, so exactly one day is marked as active.
    assert res.metrics["active_days"] == 1
    assert res.metrics["total_days"] == 5


def test_same_close_mode_fills_on_the_signal_bar():
    df = _df([100] * 5)
    res = run_backtest(
        df,
        _sig([1, 0, 0, 0, 0]),
        BacktestConfig(initial_cash=1000, fee_rate=0.0, execution="same_close"),
    )
    assert res.trades[0]["entry_date"] == str(df["trading_date"].iloc[0].date())
    assert res.assumptions[0].startswith("OPTIMISTIC MODE")


def test_equity_is_flat_when_never_in():
    df = _df([100, 110, 90, 105])
    res = run_backtest(df, never_in, BacktestConfig(initial_cash=1000, fee_rate=0.0))
    assert all(p["equity"] == 1000 for p in res.equity)
    assert res.metrics["trades"] == 0
    assert res.metrics["exposure_pct"] == 0.0
    assert res.metrics["total_return_pct"] == 0.0


def test_always_in_tracks_price_with_zero_fees():
    df = _df([100, 100, 120])  # open of bar 0 is 100, last close 120
    res = run_backtest(df, always_in, BacktestConfig(initial_cash=1000, fee_rate=0.0))
    # whole units: floor(1000/100) = 10 units, cash remainder 0
    assert res.metrics["final_equity"] == pytest.approx(1200.0)
    assert res.metrics["total_return_pct"] == pytest.approx(20.0)
    assert res.metrics["exposure_pct"] == pytest.approx(200.0 / 3.0, abs=0.01)


def test_fees_reduce_the_round_trip_by_the_hand_computed_amount():
    # 1% per side, fractional units: units = 1000 / (100 * 1.01)
    df = _df([100] * 6)
    res = run_backtest(
        df,
        _sig([1, 1, 1, 1, 0, 0]),
        BacktestConfig(initial_cash=1000, fee_rate=0.01, execution="same_close", whole_units=False),
    )
    units = 1000 / 100 / 1.01
    expected_cash_after_exit = units * 100 * 0.99
    trade = res.trades[0]
    assert trade["units"] == pytest.approx(units)
    assert trade["pnl"] == pytest.approx(expected_cash_after_exit - 1000.0)
    assert trade["return_pct"] == pytest.approx((expected_cash_after_exit - 1000) / 1000)
    assert res.metrics["final_equity"] == pytest.approx(expected_cash_after_exit, abs=0.01)
    # metrics are rounded to 2 dp for display; allow exactly that much slack
    assert res.metrics["fees_paid"] == pytest.approx(
        1000 * 0.01 + expected_cash_after_exit * 0.01, abs=0.01
    )


def test_whole_units_leave_an_uninvested_remainder():
    df = _df([100] * 4)
    res = run_backtest(
        df,
        _sig([1, 1, 1, 1]),
        BacktestConfig(initial_cash=1050, fee_rate=0.0, whole_units=True),
    )
    # 10 units cost 1000, leaving 50 in cash for the whole run
    assert res.equity[0]["equity"] == pytest.approx(1050.0)
    assert res.metrics["final_equity"] == pytest.approx(1050.0)


def test_slippage_costs_money_on_a_round_trip():
    base = BacktestConfig(initial_cash=1000, fee_rate=0.0, execution="same_close")
    df = _df([100] * 6)
    sig = _sig([1, 1, 1, 1, 0, 0])
    plain = run_backtest(df, sig, base)
    slipped = run_backtest(
        df,
        sig,
        BacktestConfig(initial_cash=1000, fee_rate=0.0, slippage=0.01, execution="same_close"),
    )
    assert slipped.metrics["final_equity"] < plain.metrics["final_equity"]


def test_buy_and_hold_benchmark_beats_a_flat_strategy_in_a_rising_market():
    df = _df([100, 100, 130, 130])
    res = run_backtest(df, never_in, BacktestConfig(initial_cash=1000, fee_rate=0.0))
    assert res.metrics["benchmark_total_return_pct"] == pytest.approx(30.0)
    assert res.metrics["total_return_pct"] == 0.0


# ----------------------------------------------------------------- guardrails
def test_signal_length_mismatch_is_rejected():
    with pytest.raises(ValueError, match="does not match bars"):
        run_backtest(_df([100] * 5), _sig([1, 0]), BacktestConfig())


def test_negative_signal_is_rejected():
    with pytest.raises(ValueError, match="short signals"):
        run_backtest(_df([100] * 5), _sig([1, -1, 0, 0, 0]), BacktestConfig())


def test_config_rejects_shorting():
    with pytest.raises(ValueError, match="shorting is not supported"):
        BacktestConfig(allow_short=True).validate()


def test_config_rejects_non_positive_cash():
    with pytest.raises(ValueError, match="initial_cash"):
        BacktestConfig(initial_cash=0).validate()


def test_missing_columns_are_rejected():
    with pytest.raises(ValueError, match="missing columns"):
        run_backtest(pd.DataFrame({"close": [1, 2, 3]}), always_in, BacktestConfig())


def test_too_few_bars_is_rejected():
    with pytest.raises(ValueError, match="at least 2 bars"):
        run_backtest(_df([100]), always_in, BacktestConfig())


def test_unknown_strategy_is_rejected():
    with pytest.raises(ValueError, match="unknown strategy"):
        build_strategy("moon_phases")


def test_unknown_strategy_parameter_is_rejected():
    with pytest.raises(ValueError, match="unknown parameter"):
        build_strategy("sma_cross", fast=10, banana=3)


# ------------------------------------------------------------------ assumptions
def test_result_carries_assumptions_and_warnings():
    df = _df([100] * 40)
    res = run_backtest(
        df,
        _sig([1] * 40),
        BacktestConfig(initial_cash=10000, fee_rate=0.004),
        symbol="TEST",
    )
    joined = " ".join(res.assumptions)
    assert "PLACEHOLDER" in joined
    assert "UNADJUSTED" in joined
    assert "no lookahead" in joined.lower() or "NEXT bar" in joined
    assert "Past performance" in joined
    assert res.warnings  # short sample and/or open position must be called out


def test_result_is_json_serialisable():
    import json

    df = _df([100] * 30)
    res = run_backtest(df, always_in, BacktestConfig(initial_cash=1000), symbol="TEST")
    payload = json.dumps(res.to_dict())
    assert '"assumptions"' in payload


# ------------------------------------------------------------------ strategies
def test_sma_cross_rejects_backwards_periods():
    with pytest.raises(ValueError, match="fast period must be"):
        sma_cross(50, 20)


def test_sma_cross_is_long_in_an_uptrend_and_flat_after():
    # Steady rise: fast SMA above slow SMA everywhere it is defined.
    df = _df(list(range(100, 160)))
    sig = sma_cross(5, 20)(df)
    assert set(np.unique(sig)) <= {0, 1}
    assert sig[0] == 0  # warm-up is flat, never silently long
    assert sig[-1] == 1


def test_float_periods_from_forms_are_coerced_to_int():
    _fn, _label, params = build_strategy("sma_cross", fast=20.0, slow=50.0)
    assert params["fast"] == 20 and isinstance(params["fast"], int)
    assert params["slow"] == 50 and isinstance(params["slow"], int)


def test_fractional_period_is_rejected_at_the_boundary():
    with pytest.raises(ValueError, match="whole number"):
        build_strategy("sma_cross", fast=20.5)


def test_float_valued_params_are_kept_as_floats():
    _fn, _label, params = build_strategy("rsi_threshold", buy_below=25.5)
    assert params["buy_below"] == pytest.approx(25.5)


def test_every_registered_strategy_runs_on_synthetic_data():
    closes = list(np.linspace(100, 140, 150)) + list(np.linspace(140, 90, 150))
    df = _df(closes)
    for key in STRATEGIES:
        fn, label, params = build_strategy(key)
        sig = fn(df)
        assert len(sig) == len(df), key
        assert set(np.unique(sig)) <= {0, 1}, key
        assert label and isinstance(params, dict)


def test_backtest_is_deterministic():
    df = _df(np.linspace(100, 150, 80).tolist())
    fn, label, params = build_strategy("sma_cross", fast=5, slow=20)
    a = run_backtest(df, fn, BacktestConfig(), symbol="T", strategy=label, params=params)
    b = run_backtest(df, fn, BacktestConfig(), symbol="T", strategy=label, params=params)
    assert a.to_dict() == b.to_dict()
