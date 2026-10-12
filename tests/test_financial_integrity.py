"""Phase 2 of the evidence-based completion audit: financial-integrity tests.

Every expected value in this file is worked out by hand, in comments, from a
fixture written by hand. No expected value is produced by the module under
test, read back out of the store, or copied from another implementation.

Status vocabulary used in the section banners follows the audit's labels:
  TESTED-PASS   - asserted here, executed, observed green
  TESTED-FAIL   - a defect the audit found; the test pins the fixed behaviour
  PARTIAL       - behaviour is correct but incomplete; pinned so it stays honest
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from megatool.backtest import BacktestConfig, run_backtest
from megatool.db import init_app_db
from megatool.market_store import MarketStore
from megatool.portfolio import (
    PortfolioError,
    add_transaction,
    derive_positions,
    value_portfolio,
)
from megatool.ranking import (
    DEFAULT_WEIGHTS,
    RankConfig,
    _percentile_rank,
    rank_universe,
)
from megatool.written_pdf import (
    PdfValidationError,
    validate_settlement_reconciliation,
)

RETRIEVED = pd.Timestamp("2026-10-11 00:00:00")


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "state.sqlite"
    init_app_db(path)
    return path


# ===========================================================================
# 1. SETTLEMENT RECONCILIATION - TESTED-PASS
# ===========================================================================
# The four settlements on page 21 of WRITTENdata.pdf, transcribed by hand.
# Each net is checked here by ordinary subtraction, independently of the code:
#
#   186,129.76 - 120,579.43 = 65,550.33
#   106,186.34 -  88,169.68 = 18,016.66
#   189,763.58 - 157,168.39 = 32,595.19
#    54,157.24 -  45,035.39 =  9,121.85
#
# NOTE ON WHAT THIS PROVES: passing these proves the recorded net equals the
# difference of the two recorded totals. It is an *arithmetic self-check* of one
# page against itself. It is NOT independent verification against the source
# document - that requires re-reading the page, which is T-09.

PAGE21 = [
    (186_129.76, 120_579.43, 65_550.33),
    (106_186.34, 88_169.68, 18_016.66),
    (189_763.58, 157_168.39, 32_595.19),
    (54_157.24, 45_035.39, 9_121.85),
]


def test_page21_nets_equal_the_difference_of_totals_by_hand():
    for buy, sell, net in PAGE21:
        # Plain arithmetic, done here, not by calling the validator first.
        assert round(abs(buy - sell), 2) == round(net, 2)
        validate_settlement_reconciliation(buy, sell, net)


def test_settlement_accepts_either_sign_convention():
    # The document labels one settlement "Net Payable" (buy - sell) and others
    # write sell - buy. The magnitude is what reconciles, so both must pass.
    validate_settlement_reconciliation(106_186.34, 88_169.68, +18_016.66)
    validate_settlement_reconciliation(106_186.34, 88_169.68, -18_016.66)


def test_settlement_tolerance_is_inclusive_at_the_boundary():
    # 0.25 and 0.5 are exactly representable in binary float, so this boundary
    # test is exact rather than subject to the 0.02 that subtraction noise
    # produces (186129.76 - 120579.43 = 65550.33000000002, not 65550.33).
    validate_settlement_reconciliation(100.0, 70.0, 30.25, tolerance=0.25)
    with pytest.raises(PdfValidationError, match="does not reconcile"):
        validate_settlement_reconciliation(100.0, 70.0, 30.5, tolerance=0.25)
    # A perfect match needs no tolerance at all.
    validate_settlement_reconciliation(100.0, 70.0, 30.0)


def test_settlement_catches_the_transcription_error_that_was_actually_found():
    """The real defect B-02: buy read as 177,609.76 instead of 186,129.76.

    177,609.76 - 120,579.43 = 57,030.33, but the recorded net is 65,550.33 -
    a difference of 8,520.00, far outside tolerance. This is exactly the error
    arithmetic catches and eyeballing does not.
    """
    wrong_buy = 177_609.76
    sell = 120_579.43
    recorded_net = 65_550.33
    assert round(abs(wrong_buy - sell), 2) == 57_030.33
    with pytest.raises(PdfValidationError, match="does not reconcile"):
        validate_settlement_reconciliation(wrong_buy, sell, recorded_net)


# ===========================================================================
# 2. CROSS-SECTIONAL PERCENTILE MATH - TESTED-PASS
# ===========================================================================
# _percentile_rank is pandas rank(method="average", pct=True) * 100.
# Hand-worked for three symbols:
#   distinct 10 < 20 < 30 -> ranks 1,2,3 -> pct 1/3, 2/3, 3/3 -> 33.33, 66.67, 100
#   tied 10 = 10 < 20     -> ranks 1.5,1.5,3 -> pct .5,.5,1   -> 50, 50, 100


def test_percentile_of_distinct_values_is_hand_computable():
    out = _percentile_rank({"A": 10.0, "B": 20.0, "C": 30.0})
    assert out["A"] == pytest.approx(100.0 / 3.0)
    assert out["B"] == pytest.approx(200.0 / 3.0)
    assert out["C"] == pytest.approx(100.0)


def test_percentile_of_tied_values_is_the_average_rank():
    out = _percentile_rank({"A": 10.0, "B": 10.0, "C": 20.0})
    assert out["A"] == pytest.approx(50.0)
    assert out["B"] == pytest.approx(50.0)
    assert out["C"] == pytest.approx(100.0)


def test_percentile_of_n_fully_tied_values_is_the_same_for_all():
    # (n+1)/(2n) * 100. For n=4 that is 62.5; for n=369 it is 50.135...
    out = _percentile_rank({f"S{i}": 1.0 for i in range(4)})
    assert all(v == pytest.approx(62.5) for v in out.values())
    out369 = _percentile_rank({f"S{i}": 1.0 for i in range(369)})
    assert out369["S0"] == pytest.approx((369 + 1) / (2 * 369) * 100.0)


# ===========================================================================
# 3. RANKING DIRECTIONALITY, NORMALISATION, WEIGHTS - TESTED-PASS
# ===========================================================================
# Four synthetic symbols, 121 bars each, alternating around 100 by +-a:
#
#     close[i] = 100           when i is even
#               = 100 * (1+a)  when i is odd
#
# Because bar 0 and bar 120 are both even, both equal 100, so
#   return_60d  = close[-1]/close[-61]  = 100/100 - 1 = 0   (index 60 is even)
#   return_120d = close[-1]/close[-121] = 100/100 - 1 = 0   (index 0 is even)
# Both momentum factors are therefore EXACTLY 0 for every symbol -> all tied.
# Volume is constant -> volume_sma_ratio is identical -> all tied.
#
# Tied percentile for n=4 is (4+1)/(2*4) = 62.5 (computed in section 2).
#
# volatility scales with a, ascending:  a -> larger a -> larger volatility
# near_52w_high = last/max(close) - 1 = 1/(1+a) - 1, so larger a -> smaller value
#
#                        mom3m   mom6m   vol_trend  volatility  52w_high   SCORE
#   a=0.01  (S1, least vol) 62.5   62.5     62.5      75.0      100.0   = 71.875
#   a=0.02  (S2)            62.5   62.5     62.5      50.0       75.0   = 63.125
#   a=0.05  (S3)            62.5   62.5     62.5      25.0       50.0   = 54.375
#   a=0.10  (S4, most vol)  62.5   62.5     62.5       0.0       25.0   = 45.625
#
# Weights: momentum_3m .25, momentum_6m .25, volume_trend .15,
#          volatility .15, near_52w_high .20  (sum 1.00)
#
#   S1 = .25(62.5)+.25(62.5)+.15(62.5)+.15(75)+.20(100)
#      = 15.625 + 15.625 + 9.375 + 11.25 + 20.00  = 71.875
#   S2 = 40.625 + .15(50) + .20(75)  = 40.625 + 7.50 + 15.00 = 63.125
#   S3 = 40.625 + .15(25) + .20(50)  = 40.625 + 3.75 + 10.00 = 54.375
#   S4 = 40.625 + .15(0)  + .20(25)  = 40.625 + 0.00 +  5.00 = 45.625

AMPS = [("S1", 0.01), ("S2", 0.02), ("S3", 0.05), ("S4", 0.10)]


def _zigzag(a: float, n: int = 121, start: str = "2025-01-01") -> pd.DataFrame:
    closes = [100.0 * (1.0 + a) if i % 2 == 1 else 100.0 for i in range(n)]
    dates = pd.bdate_range(start, periods=n)
    return pd.DataFrame(
        {
            "date": dates,
            "open": closes,
            "high": [c * 1.01 for c in closes],
            "low": [c * 0.99 for c in closes],
            "close": closes,
            "volume": [1000.0] * n,
        }
    ).sort_values("date")


@pytest.fixture
def four_symbol_universe():
    return {sym: _zigzag(a) for sym, a in AMPS}


def test_default_weights_sum_to_exactly_one():
    assert sum(DEFAULT_WEIGHTS.values()) == pytest.approx(1.0)


def test_ranking_scores_are_the_hand_computed_values(four_symbol_universe):
    res = rank_universe(four_symbol_universe, RankConfig())
    by_sym = {r.symbol: r for r in res.ranked}
    expected = {"S1": 71.875, "S2": 63.125, "S3": 54.375, "S4": 45.625}
    for sym, want in expected.items():
        assert by_sym[sym].score == pytest.approx(want, abs=1e-6), sym
    assert [r.symbol for r in res.ranked] == ["S1", "S2", "S3", "S4"]


def test_tied_factors_score_the_hand_computed_62_5(four_symbol_universe):
    res = rank_universe(four_symbol_universe, RankConfig())
    for r in res.ranked:
        for key in ("momentum_3m", "momentum_6m", "volume_trend"):
            assert r.percentiles[key] == pytest.approx(62.5), (r.symbol, key)


def test_contributions_reproduce_the_score(four_symbol_universe):
    res = rank_universe(four_symbol_universe, RankConfig())
    for r in res.ranked:
        # Each contribution is rounded to 4dp in the API, so the sum of the
        # rounded parts can differ from the rounded score by a few 1e-5.
        assert abs(sum(r.contributions.values()) - r.score) < 1e-4, r.symbol
        # Shares must sum to 1 before percentiles are applied.
        assert sum(r.contributions.values()) / sum(
            r.percentiles[k] * w for k, w in DEFAULT_WEIGHTS.items()
        ) == pytest.approx(1.0, abs=1e-9)


def test_volatility_is_inverted_so_the_calmest_symbol_scores_highest(
    four_symbol_universe,
):
    res = rank_universe(four_symbol_universe, RankConfig())
    by_sym = {r.symbol: r for r in res.ranked}
    assert by_sym["S1"].percentiles["volatility"] == pytest.approx(75.0)  # least volatile
    assert by_sym["S4"].percentiles["volatility"] == pytest.approx(0.0)  # most volatile
    # Raw volatility runs the other way: S4 has the largest raw value.
    assert by_sym["S4"].raw_values["volatility"] > by_sym["S1"].raw_values["volatility"]


def test_inverted_factor_never_reaches_100_for_the_best_symbol(four_symbol_universe):
    """Known normalisation asymmetry (audit finding, LOW severity).

    A non-inverted factor spans (100/n, 100]; the inverted factor uses
    ``100 - p`` and therefore spans [0, 100 - 100/n). Every inverted
    percentile is understated by exactly 100/n against a true reverse rank.

    Consequences, both asserted below:
      * ordering on that factor is unaffected (the shift is the same constant
        for every symbol), so ranks do not change;
      * the factor's contribution is depressed by weight * 100/n for everyone,
        which at n=4 is 0.15 * 25 = 3.75 score points but at the real n=369 is
        0.15 * 0.2716 = 0.04 - negligible for a 372-symbol universe.
    """
    res = rank_universe(four_symbol_universe, RankConfig())
    by_sym = {r.symbol: r for r in res.ranked}
    n = len(res.ranked)
    best = by_sym["S1"].percentiles["volatility"]
    assert best == pytest.approx(100.0 - 100.0 / n)  # 75.0, not 100.0
    # Ordering still holds: calmest > next > next > wildest.
    assert by_sym["S1"].percentiles["volatility"] > by_sym["S2"].percentiles["volatility"]
    assert by_sym["S2"].percentiles["volatility"] > by_sym["S3"].percentiles["volatility"]
    assert by_sym["S3"].percentiles["volatility"] > by_sym["S4"].percentiles["volatility"]


def test_unavailable_factors_carry_no_weight_and_no_contribution():
    res = rank_universe({"S1": _zigzag(0.01), "S2": _zigzag(0.05)}, RankConfig())
    declared_unavailable = {f.key for f in res.factors if not f.available}
    assert declared_unavailable == {
        "pe_ratio",
        "pb_ratio",
        "dividend_yield",
        "relative_strength",
        "sector_percentile",
    }
    assert all(res.unavailable[k] for k in declared_unavailable)
    for r in res.ranked:
        assert not (declared_unavailable & set(r.contributions))
    # And none of them are present in the effective weights actually used.
    assert not (declared_unavailable & set(res.weights))


# ===========================================================================
# 4. MISSING-DATA SUBSTITUTION IS NOT NEUTRAL - PARTIAL
# ===========================================================================
# Median substitution is disclosed (the symbol is flagged incomplete and the
# substitution is named in its note), but the substituted value also enters the
# cross-sectional distribution, so it moves OTHER symbols' percentiles. This is
# a documented limitation, not a claim of correctness.


@pytest.fixture
def universe_with_one_short_history():
    frames = {sym: _zigzag(a) for sym, a in AMPS}
    # S9 has only 90 bars: enough for min_bars=60, not enough for return_120d
    # (needs >120), so momentum_6m is uncomputable for it.
    frames["S9"] = _zigzag(0.03, n=90)
    return frames


def test_short_history_symbol_is_ranked_with_a_named_substitution(
    universe_with_one_short_history,
):
    res = rank_universe(universe_with_one_short_history, RankConfig())
    by_sym = {r.symbol: r for r in res.ranked}
    assert "S9" in by_sym, "a 90-bar symbol meets min_bars=60 and must be ranked"
    s9 = by_sym["S9"]
    assert s9.complete is False
    assert "momentum_6m" in s9.missing
    assert "median-substituted" in s9.note


def test_substituted_value_is_exactly_the_cross_sectional_median(
    universe_with_one_short_history,
):
    res = rank_universe(universe_with_one_short_history, RankConfig())
    by_sym = {r.symbol: r for r in res.ranked}
    observed = [
        r.raw_values["momentum_6m"]
        for r in res.ranked
        if r.raw_values.get("momentum_6m") is not None
    ]
    observed.sort()
    # numpy median of an even-length list is the mean of the two middle values.
    hand_median = (observed[len(observed) // 2 - 1] + observed[len(observed) // 2]) / 2
    assert by_sym["S9"].raw_values["momentum_6m"] is None  # never observed
    assert by_sym["S9"].filled["momentum_6m"] == pytest.approx(hand_median)


def test_substitution_moves_other_symbols_scores(universe_with_one_short_history):
    """The audit's bias finding: substitution is not ranking-neutral.

    Ranking the 4 complete symbols alone gives them a different score than
    ranking them alongside S9, because S9's synthetic median point sits in the
    distribution every percentile is computed from (momentum_6m goes from 4
    observations to 5, one of which is fabricated).

    Only momentum_6m's distribution changes, so the movement is bounded by that
    one factor's full contribution: weight 0.25 x 100 percentile points = 25.
    """
    with_gap = rank_universe(universe_with_one_short_history, RankConfig())
    complete_syms = [sym for sym, _ in AMPS]
    without_gap = rank_universe(
        {s: universe_with_one_short_history[s] for s in complete_syms}, RankConfig()
    )
    a = {r.symbol: r.score for r in with_gap.ranked}
    b = {r.symbol: r.score for r in without_gap.ranked}
    deltas = {s: abs(a[s] - b[s]) for s in complete_syms}
    changed = [s for s, d in deltas.items() if d > 1e-9]

    # Pin the behaviour so a future change to it is a deliberate decision.
    assert changed, "substitution is currently not ranking-neutral"
    assert max(deltas.values()) <= DEFAULT_WEIGHTS["momentum_6m"] * 100.0 + 1e-9
    # The disclosure on the substituted symbol itself must remain.
    s9 = next(r for r in with_gap.ranked if r.symbol == "S9")
    assert s9.complete is False and "median-substituted" in s9.note


# ===========================================================================
# 5. PORTFOLIO LEDGER ARITHMETIC - TESTED-PASS
# ===========================================================================
# Hand-replayed ledger for one symbol:
#
#   (1) buy  100 @ 500 fees 500
#         cost = 100*500 + 500       = 50,500
#         qty  = 100, avg = 50,500/100 = 505.00
#   (2) buy  100 @ 600 fees 600
#         cost = 100*505 + 100*600 + 600 = 111,100
#         qty  = 200, avg = 111,100/200   = 555.50
#   (3) sell  50 @ 700 fees 350
#         realised = (700*50 - 350) - 555.50*50
#                  = 34,650 - 27,775        =  6,875
#         qty  = 150, avg unchanged at 555.50
#   (4) sell 150 @ 650 fees 975
#         realised = (650*150 - 975) - 555.50*150
#                  = 96,525 - 83,325        = 13,200
#         qty  = 0, avg reset to 0
#
#   total realised = 6,875 + 13,200 = 20,075
#   buy_value (fees included) = 50,500 + 60,600 = 111,100

LEDGER = [
    dict(
        symbol="NABIL",
        side="buy",
        quantity=100,
        price=500.0,
        fees=500.0,
        traded_at="2026-01-05T10:00:00+00:00",
    ),
    dict(
        symbol="NABIL",
        side="buy",
        quantity=100,
        price=600.0,
        fees=600.0,
        traded_at="2026-02-05T10:00:00+00:00",
    ),
    dict(
        symbol="NABIL",
        side="sell",
        quantity=50,
        price=700.0,
        fees=350.0,
        traded_at="2026-03-05T10:00:00+00:00",
    ),
    dict(
        symbol="NABIL",
        side="sell",
        quantity=150,
        price=650.0,
        fees=975.0,
        traded_at="2026-04-05T10:00:00+00:00",
    ),
]


@pytest.fixture
def replayed(db):
    for tx in LEDGER:
        add_transaction(tx, db_path=db)
    return derive_positions(db_path=db)


def test_realised_pnl_is_the_hand_computed_20075(replayed):
    pos = {p.symbol: p for p in replayed}["NABIL"]
    assert pos.realized_pnl == pytest.approx(20_075.0)
    assert pos.quantity == 0
    assert pos.avg_cost == 0.0


def test_average_cost_after_two_buys_is_the_hand_computed_555_50(db):
    add_transaction(LEDGER[0], db_path=db)
    add_transaction(LEDGER[1], db_path=db)
    pos = {p.symbol: p for p in derive_positions(db_path=db)}["NABIL"]
    # (100*500 + 500 + 100*600 + 600) / 200 = 111,100 / 200
    assert pos.avg_cost == pytest.approx(555.50)
    assert pos.buy_value == pytest.approx(111_100.0)
    assert pos.realized_pnl == pytest.approx(0.0)


def test_fees_are_counted_exactly_once_per_side(db):
    """Buy fees enter the cost basis; sell fees reduce proceeds. Not both."""
    for tx in LEDGER[:3]:
        add_transaction(tx, db_path=db)
    pos = {p.symbol: p for p in derive_positions(db_path=db)}["NABIL"]
    # Realised on the partial sell only:
    #   proceeds net of fees = 700*50 - 350 = 34,650
    #   cost released        = 555.50*50    = 27,775
    #   difference           =  6,875
    assert pos.realized_pnl == pytest.approx(6_875.0)
    # Cost basis still held = 555.50 * 150 = 83,325; the entry fee for the
    # 50 sold shares stays inside the realised figure, not double-counted.
    assert pos.avg_cost * pos.quantity == pytest.approx(83_325.0)


def test_overselling_is_refused_and_the_ledger_is_left_alone(db):
    add_transaction(LEDGER[0], db_path=db)
    with pytest.raises(PortfolioError):
        add_transaction(
            dict(
                symbol="NABIL",
                side="sell",
                quantity=10_000,
                price=700.0,
                fees=0.0,
                traded_at="2026-03-05T10:00:00+00:00",
            ),
            db_path=db,
        )
    pos = {p.symbol: p for p in derive_positions(db_path=db)}["NABIL"]
    assert pos.quantity == 100  # unchanged by the refused sell


def test_valuation_discloses_that_cash_is_not_modelled(db, tmp_path):
    """PARTIAL: there is no cash account in this build.

    The summary must say so rather than implying the ledger total is a
    portfolio value. Portfolio cash is a documented gap (KNOWN_BUGS / TASK_QUEUE).
    """
    for tx in LEDGER[:2]:
        add_transaction(tx, db_path=db)
    store = MarketStore(tmp_path / "market.duckdb")
    out = value_portfolio(store, db_path=db)
    store.close()
    assert "Cash balances are not modelled" in out["note"]
    assert out["summary"]["unvalued_positions"] == 0 or "unvalued" in out["note"]


# ===========================================================================
# 6. BACKTEST COSTS, TIMING, DUPLICATE TRADES - TESTED-PASS
# ===========================================================================
# Hand-computed round trip, initial_cash 100,000, fee_rate 0.004 per side,
# slippage 0, whole units, execution next_open, flat prices (open = close = 100):
#
#   bar 0: pending signal 0 -> no trade; pending := signal[0] = 1
#   bar 1: target 1, current 0 -> BUY at open 100
#          affordable = 100,000 / (100 * 1.004) = 996.0159... -> floor 996
#          cost = 996 * 100 = 99,600
#          fee  = 99,600 * 0.004 = 398.40
#          cash = 100,000 - 99,600 - 398.40 = 1.60
#   bar 2: still long, equity = 1.60 + 996*100 = 99,601.60
#
#   so: fees_total = 398.40, final equity = 99,601.60
#       initial - final = 398.40 = the fee, exactly once.


def _flat_bars(prices, start="2026-01-01"):
    n = len(prices)
    return pd.DataFrame(
        {
            "trading_date": pd.bdate_range(start, periods=n),
            "open": prices,
            "high": prices,
            "low": prices,
            "close": prices,
            "volume": [1000] * n,
        }
    )


def _always_long(df):
    return np.ones(len(df))


def test_round_trip_costs_exactly_the_hand_computed_fee():
    df = _flat_bars([100.0, 100.0, 100.0])
    cfg = BacktestConfig(initial_cash=100_000.0, fee_rate=0.004, slippage=0.0)
    res = run_backtest(df, _always_long, cfg, symbol="TEST")
    assert res.metrics["fees_paid"] == pytest.approx(398.40)
    assert res.metrics["final_equity"] == pytest.approx(99_601.60)
    assert 100_000.0 - res.metrics["final_equity"] == pytest.approx(
        res.metrics["fees_paid"], abs=1e-6
    )


def test_fees_are_never_double_counted_on_the_round_trip():
    df = _flat_bars([100.0, 100.0, 100.0])
    cfg = BacktestConfig(initial_cash=100_000.0, fee_rate=0.004, slippage=0.0)
    res = run_backtest(df, _always_long, cfg, symbol="TEST")
    # always_in never sells, so the position is only marked at the end - no
    # phantom exit fee may be charged for a sale that never happened.
    assert res.metrics["fees_paid"] == pytest.approx(398.40)
    assert all(t["exit_date"] is None for t in res.trades)


def test_next_open_fill_uses_the_bar_after_the_signal():
    """Look-ahead guard: the signal from bar i is filled at bar i+1's open."""
    prices = [10.0, 10.0, 10.0, 10.0, 40.0]
    df = _flat_bars(prices)

    # Signal: flat for bars 0-2, long from bar 3. Under next_open the BUY must
    # happen on bar 4 at open 40 - NOT on bar 3 where the signal appeared, and
    # not at bar 3's close of 10, which would hand the backtest the +300% jump.
    def sig(frame):
        s = np.zeros(len(frame))
        s[3:] = 1.0
        return s

    res = run_backtest(df, sig, BacktestConfig(fee_rate=0.0), symbol="TEST")
    assert res.trades, "expected a trade"
    t = res.trades[0]
    assert t["entry_price"] == pytest.approx(40.0)  # bar 4 open
    assert t["entry_price"] != pytest.approx(10.0)  # not the signal bar's close
    assert t["entry_date"] == str(df["trading_date"].iloc[4].date())


def test_same_close_execution_is_explicitly_optimistic_and_labelled():
    prices = [10.0, 10.0, 10.0, 10.0, 40.0]
    df = _flat_bars(prices)

    def sig(frame):
        s = np.zeros(len(frame))
        s[3:] = 1.0
        return s

    optimistic = run_backtest(
        df, sig, BacktestConfig(fee_rate=0.0, execution="same_close"), symbol="TEST"
    )
    # same_close buys at bar 3's close (10) - the very bar that produced the
    # signal. That is why it is not the default and must be labelled.
    assert optimistic.trades[0]["entry_price"] == pytest.approx(10.0)
    text = " ".join(optimistic.assumptions).lower()
    assert "same_close" in text or "lookahead" in text or "optimistic" in text, (
        optimistic.assumptions
    )


def test_default_execution_is_next_open_not_same_close():
    cfg = BacktestConfig()
    assert cfg.execution == "next_open"
    # fee_rate must stay a labelled placeholder, not a fabricated Nepal figure.
    assert isinstance(cfg.fee_rate, float) and cfg.fee_rate >= 0


def test_repeated_signal_toggles_produce_distinct_trades_not_duplicates():
    n = 21
    prices = [100.0 + i for i in range(n)]
    df = _flat_bars(prices)

    def toggle(frame):
        # long on even bars, flat on odd -> a round trip every two bars
        return np.array([1.0 if i % 2 == 0 else 0.0 for i in range(len(frame))])

    res = run_backtest(df, toggle, BacktestConfig(fee_rate=0.0), symbol="TEST")
    pairs = [(t["entry_date"], t["exit_date"]) for t in res.trades]
    assert pairs, "expected several round trips"
    assert len(pairs) == len(set(pairs)), "duplicate (entry, exit) pairs"
    # And no trade may start before it ends.
    for t in res.trades:
        if t["exit_date"] is not None:
            assert t["entry_date"] <= t["exit_date"]


def test_equity_curve_is_finite_and_never_exceeds_cash_on_entry():
    prices = [100.0, 110.0, 90.0, 120.0, 95.0, 105.0] * 5
    df = _flat_bars(prices)
    cfg = BacktestConfig()
    res = run_backtest(df, _always_long, cfg, symbol="TEST")
    curve = [e["equity"] for e in res.equity]
    assert len(curve) == len(df)
    assert all(np.isfinite(v) for v in curve)
    assert curve[0] <= cfg.initial_cash  # fees can only reduce it first
    # Every bar must carry a date and a position flag: no silent gaps.
    assert all("date" in e and "position" in e for e in res.equity)


def test_backtest_labels_its_assumptions():
    df = _flat_bars([100.0, 100.0, 100.0])
    res = run_backtest(df, _always_long, BacktestConfig(), symbol="TEST")
    text = " ".join(res.assumptions).lower()
    assert res.assumptions, "a backtest must state what it assumes"
    # The unverified-fee disclosure must be present.
    assert any(k in text for k in ("fee", "cost", "slippage", "commission"))


# ===========================================================================
# 7. MARKET-DATA READ PATH - PARTIAL (documented limitation)
# ===========================================================================


def test_invalid_bars_are_still_returned_by_the_read_path(tmp_path):
    """PARTIAL: the read path does not filter on validation_status.

    The store marks bad rows ('invalid'/'suspect') and surfaces them through
    the API, but get_bars returns them, so indicator maths sees them too. The
    real store holds 124 invalid and 13,093 suspect rows of 514,018. This test
    pins the CURRENT behaviour so the limitation cannot be forgotten; it does
    not endorse it. See KNOWN_BUGS.
    """
    store = MarketStore(tmp_path / "market.duckdb")
    n = 5
    store.upsert_bars(
        pd.DataFrame(
            {
                "symbol": ["BAD"] * n,
                "trading_date": pd.bdate_range("2026-01-01", periods=n),
                "open": [10.0] * n,
                "high": [9.0] * n,  # high < low: physically impossible
                "low": [11.0] * n,
                "close": [10.0] * n,
                "volume": [100] * n,
                "source": ["TEST"] * n,
                "retrieved_at": [RETRIEVED] * n,
                "validation_status": ["invalid"] * n,
                "flags": ["high_low_inverted"] * n,
            }
        )
    )
    bars = store.get_bars("BAD")
    store.close()
    assert len(bars) == n, "invalid rows are returned today, not filtered out"
    assert set(bars["validation_status"]) == {"invalid"}


def test_bar_rows_carry_per_row_provenance(tmp_path):
    store = MarketStore(tmp_path / "market.duckdb")
    store.upsert_bars(
        pd.DataFrame(
            {
                "symbol": ["ABC"],
                "trading_date": [pd.Timestamp("2026-01-01")],
                "open": [10.0],
                "high": [11.0],
                "low": [9.0],
                "close": [10.0],
                "volume": [100],
                "source": ["github.com/example/dataset"],
                "source_url": ["https://example.test/a.csv"],
                "retrieved_at": [RETRIEVED],
                "validation_status": ["valid"],
            }
        )
    )
    bars = store.get_bars("ABC")
    store.close()
    assert bars.iloc[0]["source"] == "github.com/example/dataset"
    assert str(bars.iloc[0]["source_url"]).startswith("https://")
    assert not pd.isna(bars.iloc[0]["retrieved_at"])


def test_bars_are_unique_on_symbol_and_date(tmp_path):
    store = MarketStore(tmp_path / "market.duckdb")
    df = pd.DataFrame(
        {
            "symbol": ["ABC", "ABC"],
            "trading_date": [pd.Timestamp("2026-01-01")] * 2,
            "close": [10.0, 11.0],
            "source": ["TEST", "TEST"],
            "retrieved_at": [RETRIEVED, RETRIEVED],
        }
    )
    store.upsert_bars(df)
    count = store.bar_count()
    store.close()
    assert count == 1, "re-upserting the same (symbol, date) must not duplicate"
