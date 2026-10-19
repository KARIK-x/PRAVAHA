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
    COMMISSION_REVISION_DATE,
    MIN_COMMISSION_NPR,
    STRATEGIES,
    BacktestConfig,
    always_in,
    build_strategy,
    cagr,
    capital_gains_tax,
    get_fee_schedule,
    max_drawdown,
    never_in,
    run_backtest,
    sharpe_ratio,
    side_transaction_costs,
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
    # return_pct is a PERCENT, consistent with every other *_pct field in the
    # payload (contract corrected 2026-10-14; it was a fraction, which read as
    # -0.10% where -10.15% was meant).
    assert trade["return_pct"] == pytest.approx((expected_cash_after_exit - 1000) / 1000 * 100)
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


# ------------------------------------- verified schedule engine (C3/D-y, 2026-10-15)
# Every number below is hand-computed from the OFFICIAL schedule (register §3):
# commission slabs 0.36/0.33/0.31/0.27/0.24% (min NPR 10), SEBON 0.015% per
# side, NPR 25 DP per sell, CGT 7.5% (>365d) / 10% (<=365d) post-amendment and
# 5%/7.5% before 2026-07-15. No invented rates.

SCHED = "official-2083-84"


def _sched_df(closes, start):
    closes = [float(c) for c in closes]
    n = len(closes)
    return pd.DataFrame(
        {
            "trading_date": pd.bdate_range(start, periods=n),
            "open": closes,
            "high": [c * 1.01 for c in closes],
            "low": [c * 0.99 for c in closes],
            "close": closes,
        }
    )


def _sched_run(closes, start, *, cgt, initial_cash=100_000.0, hold=1):
    """Buy bar 0 at its close, hold `hold` bars, sell at bar `hold` (same_close)."""
    n = len(closes)
    sig = [1] * hold + [0] * (n - hold)
    cfg = BacktestConfig(
        initial_cash=initial_cash,
        fee_schedule=SCHED,
        cgt=cgt,
        execution="same_close",
        whole_units=True,
    )
    return run_backtest(_sched_df(closes, start), _sig(sig), cfg, symbol="TEST", strategy="fx")


# 1. commission-tier boundary values (current table, both sides of each slab edge)
def test_commission_tier_boundaries_follow_schedule_14():
    sched = get_fee_schedule(SCHED)
    cases = [
        (50_000.00, 0.0036, 180.00),
        (50_000.01, 0.0033, 165.00),
        (500_000.00, 0.0033, 1650.00),
        (500_000.01, 0.0031, 1550.00),
        (2_000_000.00, 0.0031, 6200.00),
        (2_000_000.01, 0.0027, 5400.00),
        (10_000_000.00, 0.0027, 27000.00),
        (10_000_000.01, 0.0024, 24000.00),
    ]
    for value, rate, commission in cases:
        sc = side_transaction_costs(value, "buy", "2026-08-03", sched)
        assert sc.commission_rate == rate, value
        assert sc.commission == pytest.approx(commission), value
        assert "official-2083-84" in sc.commission_table


def test_pre_revision_commission_table_applies_before_2024_05_14():
    sched = get_fee_schedule(SCHED)
    before = side_transaction_costs(50_000.0, "buy", "2024-05-13", sched)
    after = side_transaction_costs(50_000.0, "buy", COMMISSION_REVISION_DATE, sched)
    assert before.commission_rate == 0.0040  # officially superseded table
    assert before.commission == pytest.approx(200.00)
    assert "pre_revision" in before.commission_table
    assert after.commission_rate == 0.0036  # current Schedule 14
    assert "official-2083-84" in after.commission_table


# 2. minimum transaction charge
def test_minimum_commission_binds_on_small_transactions():
    sched = get_fee_schedule(SCHED)
    sc = side_transaction_costs(200.0, "buy", "2026-08-03", sched)
    assert sc.commission == MIN_COMMISSION_NPR == 10.0  # 0.36% of 200 is 0.72; the floor binds
    assert sc.sebon == pytest.approx(0.03)
    assert sc.total == pytest.approx(10.03)


# 3. additional fee components (SEBON both sides; DP sell side only)
def test_sebon_on_both_sides_and_dp_only_on_sells():
    sched = get_fee_schedule(SCHED)
    buy = side_transaction_costs(50_000.0, "buy", "2026-08-03", sched)
    sell = side_transaction_costs(50_000.0, "sell", "2026-08-03", sched)
    assert buy.sebon == sell.sebon == pytest.approx(7.50)
    assert buy.dp == 0.0
    assert sell.dp == 25.0
    assert buy.total == pytest.approx(187.50)
    assert sell.total == pytest.approx(212.50)


# 8. rounding and precision: every charge is exactly 2dp
def test_every_charge_is_rounded_to_money_precision():
    sched = get_fee_schedule(SCHED)
    sc = side_transaction_costs(12_345.678, "sell", "2026-08-03", sched)
    assert sc.value == 12_345.68
    for amount in (sc.commission, sc.sebon, sc.dp, sc.total):
        assert round(amount, 2) == amount


# 4 + 5 + 6 + 9. full round trip: gross/cost/tax reconciliation, >365d CGT,
# and no double counting. Hand-computed: 996 units bought at 100.00
# (value 99,600.00; commission 328.68 + SEBON 14.94 = 343.62; cash left 56.38),
# sold at 110.03 (value 109,589.88; commission 361.65 + SEBON 16.44 + DP 25.00
# = 403.09). Basis 99,943.62; net proceeds 109,186.79; gain 9,243.17; tax at
# 7.5% (>365 days, post-amendment) = 693.24; net P&L 8,549.93.
def test_long_hold_winning_trade_reconciles_gross_costs_tax_net():
    res = _sched_run([100.0] * 400 + [110.03], "2026-07-01", cgt="natural_person", hold=400)
    t = res.trades[0]
    assert t["entry_value"] == pytest.approx(99_600.00)
    assert t["exit_value"] == pytest.approx(109_589.88)
    assert t["fees_paid"] == pytest.approx(746.71)  # 343.62 + 403.09, once each
    assert t["gross_pnl"] == pytest.approx(9_989.88)  # 109,589.88 - 99,600.00
    assert t["transaction_costs"] == pytest.approx(746.71)
    assert t["taxable_gain"] == pytest.approx(9_243.17)  # gross - costs
    assert t["capital_gains_tax"] == pytest.approx(693.24)  # 7.5% of 9,243.17
    assert t["pnl"] == pytest.approx(8_549.93)  # 9,243.17 - 693.24
    # gross - costs - tax == net, exactly the disclosed decomposition
    assert t["gross_pnl"] - t["transaction_costs"] - t["capital_gains_tax"] == pytest.approx(
        t["pnl"], abs=1e-6
    )
    # no double counting: the run total equals the trade total, once
    assert res.metrics["fees_paid"] == pytest.approx(746.71)
    assert res.metrics["capital_gains_tax_paid"] == pytest.approx(693.24)
    assert res.metrics["realized_pnl"] == pytest.approx(8_549.93, abs=1e-6)


def test_benchmark_uses_the_same_schedule_costs():
    res = _sched_run([100.0] * 400 + [110.03], "2026-07-01", cgt="natural_person", hold=400)
    # buy-and-hold: same affordability (996 units), cash 56.38, last close 110.03
    assert res.metrics["benchmark_final_equity"] == pytest.approx(109_646.26)
    assert res.metrics["benchmark_total_return_pct"] == pytest.approx(9.6463)


# 5. holding-period condition: <=365 days at 10% (same money, same era)
def test_short_hold_uses_the_ten_percent_rate():
    res = _sched_run([100.0] * 5 + [110.03] * 5, "2026-08-03", cgt="natural_person", hold=5)
    t = res.trades[0]
    assert t["capital_gains_tax"] == pytest.approx(924.32)  # 10% of 9,243.17
    assert t["pnl"] == pytest.approx(8_318.85)


# 10. effective-date handling: a pre-amendment disposal uses the official
# pre-amendment ITA rates (5%/7.5%), not the amended ones.
def test_pre_amendment_disposal_uses_pre_amendment_rates():
    res = _sched_run([100.0] * 5 + [110.03] * 5, "2024-08-01", cgt="natural_person", hold=5)
    t = res.trades[0]
    assert t["exit_date"] < "2026-07-15"
    assert t["capital_gains_tax"] == pytest.approx(693.24)  # 7.5% (pre-amendment short-hold rate)
    assert "pre-amendment" in t["tax_note"]


def test_sides_before_the_commission_revision_are_priced_and_warned():
    res = _sched_run([100.0] * 3, "2024-05-13", cgt="natural_person", hold=2)
    t = res.trades[0]
    # The fixture deliberately STRADDLES the revision: buy 2024-05-13 on the
    # pre-revision table (>50k-5L slab 0.37%: commission 368.52 + SEBON 14.94
    # = 383.46), sell 2024-05-15 on the current table (328.68 + 14.94 + DP
    # 25.00 = 368.62). Only the buy side is pre-revision, and the warning says
    # exactly that - effectiveness is honored PER SIDE.
    assert t["entry_value"] == pytest.approx(99_600.00)
    assert t["fees_paid"] == pytest.approx(752.08)
    assert any("1 side(s) predate the 2024-05-14 commission revision" in w for w in res.warnings)


# 6. a loss is never taxed (the charge is on the gain amount)
def test_loss_trade_is_never_taxed():
    res = _sched_run([100.0] * 3, "2024-05-13", cgt="natural_person", hold=2)
    t = res.trades[0]
    assert t["gross_pnl"] == pytest.approx(0.0)  # flat prices: no price gain
    assert t["taxable_gain"] == pytest.approx(-752.08)  # costs alone make the loss
    assert t["capital_gains_tax"] == 0.0
    assert t["pnl"] == pytest.approx(t["gross_pnl"] - t["transaction_costs"])
    assert "not taxed" in t["tax_note"]


# 7. missing tax-related inputs stay explicit, never fabricated
def test_cgt_not_declared_leaves_tax_fields_none_and_says_why():
    res = _sched_run([100.0] * 400 + [110.03], "2026-07-01", cgt=None, hold=400)
    t = res.trades[0]
    assert t["capital_gains_tax"] is None
    assert t["taxable_gain"] is None
    assert "not declared" in t["tax_note"]
    assert res.metrics["capital_gains_tax_paid"] is None  # None = not computed, not zero
    assert any("NOT computed" in w for w in res.warnings)
    assert t["pnl"] == pytest.approx(9_243.17)  # gross - costs, no tax withheld


# 13. backward compatibility: the flat-fee path is untouched; its trades gain
# disclosure fields but the same numbers.
def test_flat_fee_run_keeps_its_numbers_and_adds_only_disclosure():
    df = _df([100.0] * 5 + [110.03] * 5)
    cfg = BacktestConfig(initial_cash=100_000.0, execution="same_close", whole_units=True)
    res = run_backtest(df, _sig([1] * 5 + [0] * 5), cfg, symbol="TEST", strategy="fx")
    t = res.trades[0]
    assert t["capital_gains_tax"] is None and t["tax_note"] == ""
    assert t["transaction_costs"] == pytest.approx(t["fees_paid"])
    # Flat mode keeps the unrounded engine math, so the decomposition holds to
    # the 2dp disclosure rounding (the schedule mode above is exact by
    # construction: its charges are rounded at the source).
    assert t["gross_pnl"] - t["transaction_costs"] == pytest.approx(t["pnl"], abs=0.01)
    assert res.metrics["capital_gains_tax_paid"] is None
    # placeholder labelling is untouched
    assert res.cost_model["status"] == "placeholder"
    assert res.cost_model["fee_schedule"] is None


# 2 (engine minimum) + 11 (backtest integration): tiny capital where the NPR 10
# minimum commission binds and the schedule's affordability solves the size.
def test_minimum_commission_engine_round_trip_on_tiny_capital():
    res = _sched_run([100.0] * 3, "2026-08-03", cgt="natural_person", initial_cash=300.0, hold=2)
    t = res.trades[0]
    assert t["units"] == 2  # 3 units' charges (310.04) exceed the cash; 2 fits
    assert t["entry_value"] == pytest.approx(200.00)
    assert t["fees_paid"] == pytest.approx(45.06)  # (10 + 0.03) + (10 + 0.03 + 25)
    assert t["capital_gains_tax"] == 0.0  # flat prices: no gain after costs


# config validation: one cost model per run, declared categories only
def test_schedule_config_validation_refuses_ambiguity():
    with pytest.raises(ValueError, match="unknown fee_schedule"):
        BacktestConfig(fee_schedule="nepse-2026").validate()
    with pytest.raises(ValueError, match="one cost model"):
        BacktestConfig(fee_schedule=SCHED, fee_rate=0.001).validate()
    with pytest.raises(ValueError, match="requires fee_schedule"):
        BacktestConfig(cgt="natural_person").validate()
    with pytest.raises(ValueError, match="None \\(not computed\\)"):
        BacktestConfig(fee_schedule=SCHED, cgt="company").validate()
    BacktestConfig(fee_schedule=SCHED).validate()  # the supported shape passes
    BacktestConfig(fee_schedule=SCHED, cgt="natural_person").validate()


# 5 (direct tax function): the refusal paths never guess.
def test_capital_gains_tax_function_refusals_are_explicit():
    refused = capital_gains_tax(100.0, 90.0, "2026-01-01", "2026-06-01", None)
    assert refused.computed is False and refused.amount is None
    assert "will not infer" in refused.reason
    entity = capital_gains_tax(100.0, 90.0, "2026-01-01", "2026-06-01", "company")
    assert entity.computed is False and entity.amount is None


# -------------------------------------------- algorithm workshop catalogue
def test_strategy_registry_candidates_are_well_formed():
    from megatool.backtest import STRATEGIES

    # The workshop shipped with 20 founders; the library is now larger, so the
    # test asserts the floor and the metadata contract for every entry.
    assert len(STRATEGIES) >= 20
    for key, spec in STRATEGIES.items():
        assert spec.get("category"), f"{key} is missing a workshop category"
        assert spec["label"] and spec["description"]


@pytest.mark.parametrize("key", sorted(STRATEGIES))
def test_every_workshop_strategy_runs_leak_free(key):
    """Each of the 20 candidates compiles and runs on synthetic bars, and its
    positions only ever contain 0/1 (long/flat) values."""
    from megatool.backtest import build_strategy

    fn, label, params = build_strategy(key)
    rng = np.random.default_rng(11)
    n = 260
    close = 100 + np.cumsum(rng.normal(0, 0.6, n))
    df = pd.DataFrame(
        {
            "trading_date": pd.bdate_range("2025-01-01", periods=n),
            "open": close + 0.3,
            "high": close + 1.1,
            "low": close - 0.9,
            "close": close,
            "volume": rng.integers(1_000, 90_000, n).astype(float),
        }
    )
    positions = fn(df)
    assert positions.dtype == np.int8
    assert set(np.unique(positions)) <= {0, 1}
    # a strategy must not be all-NaN silently converted weirdness
    assert len(positions) == n


def test_donchian_breakout_is_not_lookahead():
    """The breakout level must come from PRIOR bars: a day whose close IS the
    N-day high cannot have entered on itself."""
    n = 80
    close = np.full(n, 100.0)
    close[-3:] = [100.0, 130.0, 131.0]  # day n-2 breaks out, day n-1 rides
    df = pd.DataFrame(
        {
            "trading_date": pd.bdate_range("2025-01-01", periods=n),
            "open": close - 0.5,
            "high": close + 0.5,
            "low": close - 0.5,
            "close": close,
            "volume": np.full(n, 10_000.0),
        }
    )
    from megatool.backtest import donchian_breakout

    pos = donchian_breakout(breakout_days=20, exit_days=10)(df)
    # the bar that CREATES the new high must not have been long already...
    assert pos[-3] == 0
    # ...and the breakout bar's close (channel fromPRIOR bars) goes long
    assert pos[-2] == 1
    # ...and flat again when price collapses below the 10-day low
    df2 = df.copy()
    df2.loc[df2.index[-1], ["open", "high", "low", "close"]] = [60.0] * 4
    pos2 = donchian_breakout(breakout_days=20, exit_days=10)(df2)
    assert pos2[-1] == 0
