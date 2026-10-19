"""Full-lifecycle backtest verification against independently derived numbers.

Every expected value below is derived BY HAND from the fixture tables in the
docstrings - none is copied from engine output. A failure therefore means the
engine's execution, accounting, marking or metric arithmetic is wrong.

Coverage of the verification matrix: no trades / one winning trade / one
losing trade / multiple trades / open position at end / missing sessions /
insufficient history / invalid and non-positive prices / duplicate dates /
transaction costs / slippage / drawdown / unaffordable sizing / benchmark
with known returns / next-bar-open fill semantics (no look-ahead).

Fixtures are SYNTHETIC-TEST-FIXTURE rows; nothing here touches real records.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from megatool.backtest import (
    BacktestConfig,
    always_in,
    never_in,
    run_backtest,
    sharpe_ratio,
)

RETRIEVED = pd.Timestamp("2026-10-11 00:00:00")


# --------------------------------------------------------------------- helpers
def _frame(rows: list[tuple[str, float, float, float, float]]) -> pd.DataFrame:
    """rows: (date, open, high, low, close) -> SYNTHETIC-TEST-FIXTURE frame."""
    return pd.DataFrame(
        {
            "symbol": ["TEST"] * len(rows),
            "trading_date": [pd.Timestamp(d) for d, *_ in rows],
            "open": [o for _, o, _, _, _ in rows],
            "high": [h for _, _, h, _, _ in rows],
            "low": [lo for _, _, _, lo, _ in rows],
            "close": [c for _, _, _, _, c in rows],
            "volume": [1000] * len(rows),
            "source": ["SYNTHETIC-TEST-FIXTURE"] * len(rows),
            "retrieved_at": [RETRIEVED] * len(rows),
            "validation_status": ["valid"] * len(rows),
        }
    )


def _sig(values: list[int]):
    arr = np.asarray(values, dtype=np.int8)
    return lambda _df: arr.copy()


# Fixture L - the core 5-bar lifecycle fixture:
#
#   i  date        open  high   low  close
#   0  2026-01-05   100   105    95    100
#   1  2026-01-06   110   115   105    105
#   2  2026-01-07   120   125   115    115   <- signal[1]=1 buys here (next open)
#   3  2026-01-08   110   115   100    100   <- signal[2]=0 sells here (next open)
#   4  2026-01-09   105   110   100    108
L = [
    ("2026-01-05", 100, 105, 95, 100),
    ("2026-01-06", 110, 115, 105, 105),
    ("2026-01-07", 120, 125, 115, 115),
    ("2026-01-08", 110, 115, 100, 100),
    ("2026-01-09", 105, 110, 100, 108),
]

# Fixture N - alternating opens (a no-edge churn market):
#
#   i  date        open  close      (closes constant at 105)
#   0  2026-02-02   100   105
#   1  2026-02-03   110   105   <- buy fill
#   2  2026-02-04   100   105   <- sell fill
#   3  2026-02-05   110   105   <- buy fill
#   4  2026-02-06   100   105   <- sell fill
#   5  2026-02-07   110   105
N = [
    ("2026-02-02", 100, 110, 95, 105),
    ("2026-02-03", 110, 115, 100, 105),
    ("2026-02-04", 100, 110, 95, 105),
    ("2026-02-05", 110, 115, 100, 105),
    ("2026-02-06", 100, 110, 95, 105),
    ("2026-02-07", 110, 115, 100, 105),
]

# Hand-checked cost basis for fixture L, 1% per side, 10,000 cash, whole units.
#   buy  @120: affordable = 10000 / (120 * 1.01) = 82.508... -> 82 units
#           cost = 82 * 120 = 9,840.0  fee = 98.4  cash = 61.6
#   sell @110: proceeds = 82 * 110 = 9,020.0  fee = 90.2  cash = 61.6 + 8,929.8
#           cost basis = 9,840.0 + 98.4 = 9,938.4
#           pnl = (9,020.0 - 90.2) - 9,938.4 = -1,008.6
CFG_1PCT = BacktestConfig(initial_cash=10_000.0, fee_rate=0.01)


# ------------------------------------------------- B-32 pipeline consistency
# Verification pass (defect hunt): the SAME economic return must be expressed
# consistently across trade accounting, equity accounting and metrics, and the
# API layer must not rescale or double-convert any of them.
#
# Fixture W - one winning round trip:
#
#   i  date        open  close     (high/low equal to open for simplicity)
#   0  2026-03-02   100   100
#   1  2026-03-03   110   110   <- signal[0]=1 buys here (next open)
#   2  2026-03-04   120   120   <- signal[1]=0 sells here (next open)
#   3  2026-03-05   105   105
W = [
    ("2026-03-02", 100, 100, 100, 100),
    ("2026-03-03", 110, 110, 110, 110),
    ("2026-03-04", 120, 120, 120, 120),
    ("2026-03-05", 105, 105, 105, 105),
]
# Hand-derived, 1% per side, 10,000 cash:
#   buy  @110: affordable = floor(10000 / (110*1.01)) = floor(90.09) = 90 units
#           cost = 9,900.0  fee = 99.0  cash = 1.0
#   sell @120: proceeds = 90 * 120 = 10,800.0  fee = 108.0  cash = 1 + 10,692 = 10,693
#   pnl    = (10,800 - 108) - (9,900 + 99) = 693.0
#   trade.return_pct = 693 / 9,999 * 100 = 6.930693... (cost basis incl. entry fee)
#   total_return_pct = (10,693 / 10,000 - 1) * 100 = 6.93
CFG_W = BacktestConfig(initial_cash=10_000.0, fee_rate=0.01)


def test_same_economic_return_is_consistent_across_the_whole_pipeline():
    """B-32: one winning round trip - every layer must agree, hand-derived."""
    res = run_backtest(_frame(W), _sig([1, 0, 0, 0]), config=CFG_W)
    trade = res.trades[0]
    m = res.metrics

    # Trade accounting, hand-computed:
    assert trade["entry_price"] == 110.0 and trade["exit_price"] == 120.0
    assert trade["units"] == 90.0
    assert trade["pnl"] == pytest.approx(693.0, abs=1e-9)
    assert trade["return_pct"] == pytest.approx(693.0 / 9999.0 * 100.0, rel=1e-9)

    # Equity accounting, hand-computed, and it AGREES with trade accounting
    # (a fully-closed flat account has realised == equity change exactly):
    assert m["final_equity"] == pytest.approx(10_693.0, abs=1e-9)
    assert m["total_return_pct"] == pytest.approx(6.93, abs=1e-9)
    assert m["realized_pnl"] == pytest.approx(trade["pnl"], abs=1e-9)
    assert m["realized_pnl"] == pytest.approx(m["final_equity"] - CFG_W.initial_cash, abs=1e-9)

    # Metrics agree with the trade list in the SAME percent unit:
    assert m["win_rate_pct"] == 100.0
    assert m["avg_trade_pct"] == pytest.approx(trade["return_pct"], abs=1e-4)
    assert m["trades"] == 1


# ------------------------------------------------------- one losing round trip
def test_one_losing_trade_hand_computed_cash_accounting():
    res = run_backtest(_frame(L), _sig([0, 1, 0, 0, 0]), CFG_1PCT, symbol="TEST")
    assert len(res.trades) == 1
    t = res.trades[0]
    assert t["exit_date"] is not None
    assert t["units"] == 82
    assert t["entry_price"] == pytest.approx(120.0)
    assert t["exit_price"] == pytest.approx(110.0)
    assert t["pnl"] == pytest.approx(-1008.6, abs=1e-9)
    # return_pct is a PERCENT (contract: every *_pct field is percent).
    assert t["return_pct"] == pytest.approx(-1008.6 / 9938.4 * 100.0, abs=1e-9)
    assert t["bars_held"] == 1

    m = res.metrics
    assert m["final_equity"] == pytest.approx(8991.4, abs=1e-9)
    assert m["total_return_pct"] == pytest.approx(-10.086, abs=1e-9)
    # peak 10,000 at bar 0/1, trough 8,991.4 at bar 3 -> -10.086%
    assert m["max_drawdown_pct"] == pytest.approx(-10.086, abs=1e-9)
    assert m["trades"] == 1
    assert m["win_rate_pct"] == 0.0
    assert m["fees_paid"] == pytest.approx(188.6, abs=1e-9)  # 98.4 + 90.2
    assert m["exposure_pct"] == pytest.approx(20.0, abs=1e-9)  # 1 of 5 bars long
    assert m["active_days"] == 1 and m["total_days"] == 5
    assert m["open_position_at_end"] is False
    assert m["realized_pnl"] == pytest.approx(-1008.6, abs=1e-9)
    assert m["unrealized_pnl"] is None

    # equity curve: 10,000 | 10,000 | 61.6 + 82*115 | 8,991.4 | 8,991.4
    eq = [row["equity"] for row in res.equity]
    assert eq == pytest.approx([10000.0, 10000.0, 9491.6, 8991.4, 8991.4], abs=1e-9)

    joined = " ".join(res.warnings)
    assert "1 completed trade" in joined  # tiny sample called out
    assert "shorter than one year" in joined


# ------------------------------------------- one winning + one losing round trip
def test_two_trades_win_rate_and_realised_pnl_hand_computed():
    rows = L + [
        ("2026-01-12", 115, 120, 110, 120),
        ("2026-01-13", 120, 125, 115, 118),
    ]
    # signal[1]=1 buys @120, signal[2]=0 sells @110 (loss),
    # signal[3]=1 buys @105, signal[4]=0 sells @115 (win).
    res = run_backtest(_frame(rows), _sig([0, 1, 0, 1, 0, 0, 0]), CFG_1PCT, symbol="TEST")
    assert len(res.trades) == 2
    first, second = res.trades

    # --- trade 1 (loss): identical to the single-trade case above
    assert first["pnl"] == pytest.approx(-1008.6, abs=1e-9)

    # --- trade 2 (win):
    #   buy @105: affordable = 8,991.4 / (105 * 1.01) = 84.7846 -> 84 units
    #           cost = 8,820.0  fee = 88.2  cash = 8,991.4 - 8,908.2 = 83.2
    #   sell @115: proceeds = 9,660.0  fee = 96.6  cash = 83.2 + 9,563.4 = 9,646.6
    #           cost basis = 8,820.0 + 88.2 = 8,908.2
    #           pnl = 9,563.4 - 8,908.2 = 655.2
    assert second["units"] == 84
    assert second["entry_price"] == pytest.approx(105.0)
    assert second["exit_price"] == pytest.approx(115.0)
    assert second["pnl"] == pytest.approx(655.2, abs=1e-9)
    assert second["return_pct"] == pytest.approx(655.2 / 8908.2 * 100.0, abs=1e-9)

    m = res.metrics
    assert m["trades"] == 2
    assert m["win_rate_pct"] == 50.0
    assert m["final_equity"] == pytest.approx(9646.6, abs=1e-9)
    assert m["realized_pnl"] == pytest.approx(-1008.6 + 655.2, abs=1e-9)
    # final equity - initial cash must equal the sum of realised pnl
    # (position is flat at the end, so nothing is unrealised).
    assert m["final_equity"] - 10_000.0 == pytest.approx(m["realized_pnl"], abs=1e-9)
    # avg of the two percent returns: (-10.1485150 + 7.3550582) / 2
    assert m["avg_trade_pct"] == pytest.approx(-1.3967, abs=1e-4)
    assert m["fees_paid"] == pytest.approx(98.4 + 90.2 + 88.2 + 96.6, abs=1e-9)
    assert m["exposure_pct"] == pytest.approx(round(200 / 7, 2), abs=1e-9)
    # equity path: 10,000 | 10,000 | 9,491.6 | 8,991.4 | 83.2+84*108 | 9,646.6 | 9,646.6
    eq = [row["equity"] for row in res.equity]
    assert eq == pytest.approx([10000.0, 10000.0, 9491.6, 8991.4, 9155.2, 9646.6, 9646.6], abs=1e-9)


# ------------------------------------------------------- open position at the end
def test_open_position_is_marked_not_closed():
    res = run_backtest(_frame(L), _sig([1, 1, 1, 1, 1]), CFG_1PCT, symbol="TEST")
    # buy @110 on bar 1: affordable = 10,000 / (110*1.01) = 90.009 -> 90 units
    # cost 9,900  fee 99  cash 1.0; marks: 1+90*105, +90*115, +90*100, +90*108
    m = res.metrics
    assert m["open_position_at_end"] is True
    assert m["trades"] == 0  # an open trade is not a completed trade
    assert m["win_rate_pct"] is None
    assert m["realized_pnl"] == 0.0
    # unrealised = mark value 90*108 = 9,720 minus cost basis 9,900 + 99
    assert m["unrealized_pnl"] == pytest.approx(-279.0, abs=1e-9)
    assert m["final_equity"] == pytest.approx(9721.0, abs=1e-9)  # cash 1.0 + 9,720
    assert m["exposure_pct"] == 80.0

    assert len(res.trades) == 1
    assert res.trades[0]["exit_date"] is None and res.trades[0]["pnl"] is None

    eq = [row["equity"] for row in res.equity]
    assert eq == pytest.approx([10000.0, 9451.0, 10351.0, 9001.0, 9721.0], abs=1e-9)

    joined = " ".join(res.warnings)
    assert "still open at the end" in joined
    assert "0 completed trade" in joined


# --------------------------------------------------------------- no trades at all
def test_never_in_is_fully_flat_and_undefined_where_it_should_be():
    res = run_backtest(_frame(L), never_in, CFG_1PCT, symbol="TEST")
    m = res.metrics
    assert m["final_equity"] == 10_000.0
    assert m["total_return_pct"] == 0.0
    assert m["max_drawdown_pct"] == 0.0
    assert m["sharpe"] is None  # zero variance -> undefined, not 0
    assert m["trades"] == 0 and m["win_rate_pct"] is None
    assert m["fees_paid"] == 0.0
    assert m["exposure_pct"] == 0.0
    assert m["realized_pnl"] == 0.0 and m["unrealized_pnl"] is None
    # Benchmark with the same cost model, hand-computed:
    #   affordable = 10,000 / (100*1.01) = 99.009 -> 99 units
    #   cost 9,900  fee 99  cash 1.0  final = 1 + 99*108 = 10,693.0
    assert m["benchmark_final_equity"] == pytest.approx(10693.0, abs=1e-9)
    assert m["benchmark_total_return_pct"] == pytest.approx(6.93, abs=1e-9)


def test_zero_fee_benchmark_is_exact_buy_and_hold():
    res = run_backtest(_frame(L), never_in, BacktestConfig(initial_cash=10_000.0, fee_rate=0.0))
    # 100 units at the first open, valued at the last close: 100 * 108 = 10,800
    assert res.metrics["benchmark_final_equity"] == pytest.approx(10800.0, abs=1e-9)
    assert res.metrics["benchmark_total_return_pct"] == pytest.approx(8.0, abs=1e-9)


# ------------------------------------------------------------------ missing sessions
def test_missing_sessions_are_not_fabricated_and_days_are_calendar_days():
    rows = [
        ("2026-01-05", 100, 105, 95, 100),
        ("2026-01-12", 101, 106, 96, 101),
        ("2026-01-15", 102, 107, 97, 102),
        ("2026-03-01", 103, 108, 98, 103),
        ("2026-06-01", 104, 109, 99, 104),
    ]
    res = run_backtest(_frame(rows), never_in, CFG_1PCT, symbol="TEST")
    # 5 stored sessions are 5 bars - the gaps between them are NOT synthetic bars.
    assert res.bars == 5
    assert res.metrics["total_days"] == 5
    # 2026-01-05 -> 2026-06-01 is 147 calendar days (26+28+31+30+31+1).
    joined = " ".join(res.assumptions)
    assert "5 bars, 2026-01-05 to 2026-06-01 (147 calendar days)" in joined


def test_two_bars_is_the_supported_minimum():
    rows = L[:2]
    res = run_backtest(_frame(rows), always_in, CFG_1PCT, symbol="TEST")
    assert res.bars == 2
    assert res.metrics["sharpe"] is None  # one return observation -> undefined
    assert "shorter than one year" in " ".join(res.warnings)


def test_one_bar_is_rejected():
    with pytest.raises(ValueError, match="at least 2 bars"):
        run_backtest(_frame(L[:1]), always_in, CFG_1PCT)


# --------------------------------------------------------- invalid / bad prices
def test_nan_open_falls_back_to_the_same_bar_close():
    rows = [
        (d, float("nan"), h, lo, c) if d == "2026-01-07" else r for r in L for d, o, h, lo, c in [r]
    ]
    res = run_backtest(_frame(rows), _sig([0, 1, 0, 0, 0]), CFG_1PCT, symbol="TEST")
    t = res.trades[0]
    # The buy could not use bar 2's open, so it filled at bar 2's close (115).
    assert t["entry_price"] == pytest.approx(115.0)
    # affordable = 10,000 / (115 * 1.01) = 86.095 -> 86 units; no fill was skipped.
    assert t["units"] == 86
    assert not any("no usable price" in w for w in res.warnings)


def _nan_close_rows(value):
    return [(d, o, h, lo, value if d == "2026-01-08" else c) for d, o, h, lo, c in L]


@pytest.mark.parametrize("bad_close", [float("nan"), 0.0])
def test_unusable_close_marks_at_last_known_price_never_at_cash(bad_close):
    """A missing or non-positive close must not collapse the equity curve.

    Holding 82 units through bar 3, the position is worth 82 x 115 (the last
    usable close) - NOT 0. Valuing it at cash would invent a -47% one-day
    crash out of a data gap. The historical row itself is never altered.
    """
    rows = _nan_close_rows(bad_close)
    res = run_backtest(_frame(rows), _sig([0, 1, 1, 1, 1]), CFG_1PCT, symbol="TEST")
    eq = [row["equity"] for row in res.equity]
    # buy @120 on bar 2 -> cash 61.6, 82 units; bar 3 close unusable ->
    # mark at 115 (bar 2's close); bar 4 close 108 usable again.
    assert eq[3] == pytest.approx(61.6 + 82 * 115.0, abs=1e-9)
    assert eq[4] == pytest.approx(61.6 + 82 * 108.0, abs=1e-9)
    assert any("usable close" in w or "stale" in w for w in res.warnings)


def test_fully_unusable_fill_bar_skips_the_fill_and_warns():
    rows = [
        ("2026-01-07", 0.0, 125, 115, 0.0) if d == "2026-01-07" else r
        for r in L
        for d, o, h, lo, c in [r]
    ]
    res = run_backtest(_frame(rows), _sig([0, 1, 0, 0, 0]), CFG_1PCT, symbol="TEST")
    assert res.trades == []  # the fill could not happen at any usable price
    assert res.metrics["exposure_pct"] == 0.0
    assert res.metrics["final_equity"] == 10_000.0
    assert any("no usable price" in w for w in res.warnings)


def test_duplicate_trading_dates_are_rejected_not_double_counted():
    rows = L + [("2026-01-08", 110, 115, 100, 100)]  # 2026-01-08 appears twice
    with pytest.raises(ValueError, match="duplicate trading date"):
        run_backtest(_frame(rows), never_in, CFG_1PCT)


def test_mixed_date_representations_of_one_session_are_rejected_as_duplicates():
    """B-34: the same session written two ways is still ONE session.

    "2026-01-08" and "2026-01-08 00:00:00" must normalize to the same
    instant, so the duplicate guard fires instead of pricing the day twice.
    """
    df = _frame(L[:3] + [("2026-01-08", 110, 115, 100, 100)])
    # Row 2 is the same session as row 3, written as a raw STRING with a time
    # component while the rest are Timestamps (object dtype keeps it a string
    # instead of letting pandas silently coerce it back to a Timestamp).
    df["trading_date"] = df["trading_date"].astype(object)
    df.loc[2, "trading_date"] = "2026-01-08 00:00:00"
    assert isinstance(df.loc[2, "trading_date"], str)  # genuinely mixed types
    with pytest.raises(ValueError, match="duplicate trading date"):
        run_backtest(df, never_in, CFG_1PCT)


def test_distinct_securities_sharing_dates_are_not_collapsed():
    """B-34: duplicates are checked PER symbol run, never across symbols."""
    res_a = run_backtest(_frame(L), _sig([0, 1, 0, 0, 0]), CFG_1PCT, symbol="AAA")
    res_b = run_backtest(_frame(L), _sig([0, 1, 0, 0, 0]), CFG_1PCT, symbol="BBB")
    # Two independent securities over the SAME calendar dates both run fine
    # and produce identical economics - sharing dates is not duplication.
    assert res_a.metrics["final_equity"] == pytest.approx(res_b.metrics["final_equity"])
    assert res_a.start == res_b.start == "2026-01-05"


def test_unparseable_dates_fail_loudly_not_silently_misordered():
    df = _frame(L)
    df["trading_date"] = df["trading_date"].astype(object)
    df.loc[2, "trading_date"] = "not-a-date"  # genuinely a garbage string
    with pytest.raises(ValueError, match="unparseable trading_date"):
        run_backtest(df, never_in, CFG_1PCT)


def test_unordered_dates_are_sorted_not_silently_misaligned():
    rows = list(reversed(L))
    res = run_backtest(_frame(rows), _sig([0, 1, 0, 0, 0]), CFG_1PCT, symbol="TEST")
    # After sorting, the same next-open lifecycle must occur: buy @120, sell @110.
    assert res.start == "2026-01-05" and res.end == "2026-01-09"
    assert res.trades[0]["entry_price"] == pytest.approx(120.0)
    assert res.trades[0]["exit_price"] == pytest.approx(110.0)


# ----------------------------------------------------------- sizing and slippage
def test_cash_too_small_to_buy_one_unit_warns_instead_of_silently_never_entering():
    res = run_backtest(
        _frame(L), _sig([1, 1, 1, 1, 1]), BacktestConfig(initial_cash=50.0, fee_rate=0.01)
    )
    assert res.metrics["exposure_pct"] == 0.0
    assert res.metrics["final_equity"] == 50.0
    assert any("afford" in w for w in res.warnings)


def test_slippage_worsens_both_sides_by_the_hand_computed_amount():
    # entry price 100 -> 101 with 1% slippage; exit 100 -> 99.
    # same_close, fractional units, fee 0, cash 10,000:
    #   no slip: units = 100, final = 100 * 100 = 10,000 (flat prices)
    #   slipped: units = 10,000 / 101 = 99.00990099
    #            final = 99.00990099 * 99 = 9,801.980198... (reported to 2 dp)
    rows = [(d, 100.0, 101.0, 99.0, 100.0) for d, *_ in L]
    plain = run_backtest(
        _frame(rows),
        _sig([1, 1, 1, 1, 0]),
        BacktestConfig(
            initial_cash=10_000.0, fee_rate=0.0, execution="same_close", whole_units=False
        ),
    )
    slipped = run_backtest(
        _frame(rows),
        _sig([1, 1, 1, 1, 0]),
        BacktestConfig(
            initial_cash=10_000.0,
            fee_rate=0.0,
            slippage=0.01,
            execution="same_close",
            whole_units=False,
        ),
    )
    assert plain.metrics["final_equity"] == pytest.approx(10_000.0, abs=1e-6)
    assert slipped.metrics["final_equity"] == pytest.approx(9801.980198, abs=0.01)


# ------------------------------------------------------------------- no-edge churn
def test_alternating_churn_in_a_no_edge_market_loses_exactly_the_costs():
    # Every cycle buys at 110 and sells at 100 on flat closes: a 10/share loss
    # plus 1% per side. Hand-computed cycles (see fixture N):
    #   cycle 1: 90 units, pnl = (9,000 - 90) - (9,900 + 99) = -1,089
    #   cycle 2: 80 units, pnl = (8,000 - 80) - (8,800 + 88)  =   -968
    res = run_backtest(_frame(N), _sig([1, 0, 1, 0, 0, 0]), CFG_1PCT, symbol="TEST")
    m = res.metrics
    assert [round(t["pnl"], 6) for t in res.trades] == pytest.approx([-1089.0, -968.0])
    assert m["realized_pnl"] == pytest.approx(-2057.0, abs=1e-9)
    assert m["final_equity"] == pytest.approx(7943.0, abs=1e-9)
    assert m["total_return_pct"] == pytest.approx(-20.57, abs=1e-9)
    assert m["max_drawdown_pct"] == pytest.approx(-20.57, abs=1e-9)
    assert m["win_rate_pct"] == 0.0
    assert m["fees_paid"] == pytest.approx(99 + 90 + 88 + 80, abs=1e-9)
    eq = [row["equity"] for row in res.equity]
    assert eq == pytest.approx([10000.0, 9451.0, 8911.0, 8423.0, 7943.0, 7943.0], abs=1e-9)


def test_fees_are_monotonically_harmful_for_an_identical_signal():
    sig = _sig([1, 0, 1, 0, 0, 0])
    free = run_backtest(_frame(N), sig, BacktestConfig(initial_cash=10_000.0, fee_rate=0.0))
    costly = run_backtest(_frame(N), sig, CFG_1PCT)
    assert costly.metrics["total_return_pct"] < free.metrics["total_return_pct"]


# ------------------------------------------------------------------- no look-ahead
def test_signal_on_the_last_bar_never_fills_and_cannot_change_the_result():
    a = run_backtest(_frame(L), _sig([0, 1, 0, 0, 0]), CFG_1PCT, symbol="T")
    b = run_backtest(_frame(L), _sig([0, 1, 0, 0, 1]), CFG_1PCT, symbol="T")
    # The final bar's signal has no next bar to fill on, so nothing may change.
    assert [row["equity"] for row in a.equity] == [row["equity"] for row in b.equity]
    assert a.metrics == b.metrics
    assert a.trades == b.trades


def test_earlier_bars_are_unaffected_by_a_later_signal_change():
    a = run_backtest(_frame(L), _sig([0, 1, 0, 0, 0]), CFG_1PCT, symbol="T")
    c = run_backtest(_frame(L), _sig([0, 0, 0, 0, 0]), CFG_1PCT, symbol="T")
    # Signals can only affect bars AFTER the bar they were computed on.
    assert [row["equity"] for row in a.equity][:2] == [row["equity"] for row in c.equity][:2]
    assert a.equity[2]["equity"] != c.equity[2]["equity"]


def test_entry_fills_at_the_next_open_not_the_signal_bar_close():
    res = run_backtest(_frame(L), _sig([0, 1, 0, 0, 0]), CFG_1PCT, symbol="T")
    # signal[1] = 1 was produced on bar 1 (close 105); the fill is bar 2's
    # OPEN of 120 - never 105, which would leak the signal bar's own outcome.
    assert res.trades[0]["entry_price"] == pytest.approx(120.0)


# ------------------------------------------------------------------------- metrics
def test_sharpe_of_a_hand_checked_two_point_series():
    # mean = 0.02, sample sd = sqrt(((0.01-0.02)^2 + (0.03-0.02)^2) / 1)
    #       = sqrt(2e-4) -> mean/sd = sqrt(2); x sqrt(250) = sqrt(500).
    assert sharpe_ratio([0.01, 0.03]) == pytest.approx(math.sqrt(500.0), rel=1e-9)


def test_drawdown_on_a_known_equity_path():
    res = run_backtest(_frame(L), _sig([0, 1, 0, 0, 0]), CFG_1PCT, symbol="T")
    assert res.metrics["max_drawdown_pct"] == pytest.approx(
        (8991.4 / 10000.0 - 1.0) * 100.0, abs=1e-9
    )


def test_result_is_deterministic_across_runs():
    a = run_backtest(_frame(L), _sig([0, 1, 0, 0, 0]), CFG_1PCT, symbol="T")
    b = run_backtest(_frame(L), _sig([0, 1, 0, 0, 0]), CFG_1PCT, symbol="T")
    assert a.to_dict() == b.to_dict()
