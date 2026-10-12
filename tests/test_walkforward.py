"""Walk-forward validation of the ranking.

Every expected number here is derived by hand in the comments from the fixture's
closed-form price path, not asked of the module under test. The point of these
tests is that the *chronology* is right: a ranking may only use data available
at the rebalance date, and a missing outcome must never be filled in.
"""

from __future__ import annotations

import pandas as pd
import pytest

from megatool.walkforward import (
    CAVEATS,
    FACTOR_HISTORY_WINDOW,
    WalkForwardConfig,
    rebalance_dates,
    walk_forward,
)

N_SYMBOLS = 6
#: Days per segment of the fixture's price path (see _frames).
DAYS = 100

#: Only momentum is scored; every other factor is switched off so the expected
#: ranks are unambiguous.
ONLY_MOMENTUM = {
    "momentum_3m": 1.0,
    "momentum_6m": 0.0,
    "volume_trend": 0.0,
    "volatility": 0.0,
    "near_52w_high": 0.0,
}

#: Target forward return in period A (Nov -> Dec) and B (Dec -> Jan), per
#: symbol index. These are the numbers the arithmetic assertions use.
PERIOD_A = {0: -0.10, 1: -0.05, 2: 0.0, 3: 0.02, 4: 0.05, 5: 0.10}
PERIOD_B = {0: 0.01, 1: 0.02, 2: 0.03, 3: 0.04, 4: 0.05, 5: 0.06}

#: Index of the first rebalance (last November trading day) in the fixture.
#: `bdate_range("2024-09-02", periods=100)` puts 21 September weekdays, 23 in
#: October and 21 in November, so the last November day is index 64.
NOV_LAST = 64
#: Index of the last December trading day. The series then runs out in the
#: middle of January, so the third rebalance is 2025-01-17, not the 31st.
DEC_LAST = 86


def _symbol_name(i: int) -> str:
    return f"S{i}"


def _slope(i: int) -> float:
    """Strictly increasing in i, so momentum ranks S5 best and S0 worst."""
    return 0.001 * (i + 1)


def _frames(
    period_a: dict[int, float] | None = None,
    period_b: dict[int, float] | None = None,
    drop: set[str] | None = None,
    drift_after: dict[int, float] | None = None,
    truncate: dict[str, str] | None = None,
) -> dict[str, pd.DataFrame]:
    """Six symbols on a three-segment price path.

    Segment 1 (days 0..64) is a linear ramp, so ``return_60d`` at the first
    rebalance is ``60a / (1 + 4a)`` - strictly increasing in the slope, which
    makes the rank order S5, S4, S3, S2, S1, S0 and nothing else.
    Segments 2 and 3 are flat at prices chosen to deliver exactly the target
    forward returns in PERIOD_A and PERIOD_B, so the expected spreads are round
    numbers that can be written down rather than computed by the module.

    ``drift_after`` adds an extra daily slope after the first rebalance, used
    by the look-ahead test to perturb outcome data without touching signal data.
    ``truncate`` cuts a symbol's history at a date, used to give a symbol a
    ranking but no measurable outcome.
    """
    pa = period_a or PERIOD_A
    pb = period_b or PERIOD_B
    dates = pd.bdate_range("2024-09-02", periods=DAYS)
    frames: dict[str, pd.DataFrame] = {}
    for i in range(N_SYMBOLS):
        name = _symbol_name(i)
        a = _slope(i)
        base = [100.0 * (1.0 + a * d) for d in range(DAYS)]
        ramp = (drift_after or {}).get(i, 0.0)
        closes: list[float] = []
        for d in range(DAYS):
            if d <= NOV_LAST:
                closes.append(base[d])
            elif d <= DEC_LAST:
                closes.append(base[NOV_LAST] * (1.0 + pa[i]) * (1.0 + ramp * (d - NOV_LAST)))
            else:
                target_b = base[NOV_LAST] * (1.0 + pa[i]) * (1.0 + pb[i])
                closes.append(target_b * (1.0 + ramp * (d - DEC_LAST)))
        frames[name] = pd.DataFrame(
            {
                "symbol": [name] * DAYS,
                "trading_date": dates,
                "open": closes,
                "high": closes,
                "low": closes,
                "close": closes,
                "volume": [1_000] * DAYS,
            }
        )
    if drop:
        frames = {s: f for s, f in frames.items() if s not in drop}
    if truncate:
        for name, cutoff in truncate.items():
            if name in frames:
                f = frames[name]
                frames[name] = f[f["trading_date"] <= pd.Timestamp(cutoff)].reset_index(drop=True)
    return frames


def _cfg(**kwargs) -> WalkForwardConfig:
    kwargs.setdefault("frequency", "M")
    kwargs.setdefault("start", "2024-11-01")
    kwargs.setdefault("weights", dict(ONLY_MOMENTUM))
    kwargs.setdefault("permutations", 60)
    return WalkForwardConfig(**kwargs)


# --------------------------------------------------------------------- dates


def test_rebalance_dates_are_the_last_trading_day_of_each_period():
    frames = _frames()
    monthly = rebalance_dates(frames, "M", start="2024-11-01")
    # The series runs out on 2025-01-17, so the last "month end" is that day:
    # the function takes the last *observed* date per period, not a calendar
    # month end that the data does not contain.
    assert monthly == ["2024-11-29", "2024-12-31", "2025-01-17"]

    quarterly = rebalance_dates(frames, "Q")
    # Q3 2024 (partial, data starts 2024-09-02) -> 30 Sep, Q4 -> 31 Dec,
    # Q1 2025 (partial, data ends 2025-01-17) -> 17 Jan.
    assert quarterly == ["2024-09-30", "2024-12-31", "2025-01-17"]


def test_an_unknown_frequency_is_refused_rather_than_silently_treated_as_daily():
    with pytest.raises(ValueError, match="unknown frequency"):
        rebalance_dates(_frames(), "D")


def test_a_window_narrower_than_the_data_reports_too_few_dates_not_an_error():
    result = walk_forward(_frames(), _cfg(start="2024-11-01", end="2024-11-30"))
    assert result.periods == []
    assert result.periods_used == 0
    assert any("at least two consecutive periods" in n for n in result.notes)


# --------------------------------------------------------------- the arithmetic


def test_every_period_return_matches_the_hand_derived_value():
    """The fixture's flat segments make every expected return a round number.

    With only ``momentum_3m`` scored, ``return_60d`` at the November rebalance
    is ``close[64]/close[4] - 1 = 60a/(1+4a)``, strictly increasing in the
    slope, so ranks are S5..S0. ``top_quantile`` 0.25 over 6 symbols gives
    k = round(1.5) = 2 tails: long {S5,S4}, short {S1,S0}.

        period A  long  = (0.10 + 0.05)/2 =  0.075
                  short = (-0.10 - 0.05)/2 = -0.075
                  spread = 0.15
        period B  long  = (0.06 + 0.05)/2 =  0.055
                  short = (0.01 + 0.02)/2 =  0.015
                  spread = 0.04
    """
    result = walk_forward(_frames(), _cfg())
    assert result.periods_used == 2

    a, b = result.periods
    assert a.long_symbols == ["S5", "S4"]
    assert a.short_symbols == ["S1", "S0"]
    assert a.long_return == pytest.approx(0.075, abs=1e-9)
    assert a.short_return == pytest.approx(-0.075, abs=1e-9)
    assert a.spread == pytest.approx(0.15, abs=1e-9)

    assert b.long_symbols == ["S5", "S4"]
    assert b.short_symbols == ["S1", "S0"]
    assert b.spread == pytest.approx(0.04, abs=1e-9)


def test_the_summary_is_the_documented_aggregate_of_the_periods():
    result = walk_forward(_frames(), _cfg())
    # mean of the two spreads: (0.15 + 0.04) / 2 = 0.095
    assert result.mean_spread == pytest.approx(0.095, abs=1e-9)
    assert result.hit_rate == pytest.approx(1.0)
    # compounded across periods, not summed
    assert result.cumulative_long == pytest.approx(1.075 * 1.055, rel=1e-9)
    assert result.cumulative_short == pytest.approx(0.925 * 1.015, rel=1e-9)
    # benchmark is the equal-weight mean of ALL ranked symbols each period:
    # A: (-0.10-0.05+0.00+0.02+0.05+0.10)/6 = 0.02/6
    # B: (0.01+0.02+0.03+0.04+0.05+0.06)/6 = 0.21/6
    expected_bench = (1.0 + 0.02 / 6) * (1.0 + 0.21 / 6)
    assert result.cumulative_benchmark == pytest.approx(expected_bench, rel=1e-9)
    assert result.mean_benchmark == pytest.approx((0.02 / 6 + 0.21 / 6) / 2, abs=1e-9)


def test_a_negative_spread_is_reported_negative_not_absoluted():
    """A ranking whose favourites lose is the finding, so it must survive."""
    inverted = {i: -v for i, v in PERIOD_A.items()}
    result = walk_forward(_frames(period_a=inverted), _cfg())
    assert result.mean_spread is not None and result.mean_spread < 0
    assert result.hit_rate == 0.0
    assert result.cumulative_long is not None and result.cumulative_short is not None
    assert result.cumulative_long < result.cumulative_short


# ------------------------------------------------------------------ chronology


def test_a_bar_after_the_rebalance_cannot_change_that_periods_portfolio():
    """No look-ahead: outcome data is not signal data.

    The perturbation only touches days after the first rebalance and only in
    the *second* segment, so nothing available at the November rebalance
    changes. The portfolios formed there must be identical.
    """
    plain = walk_forward(_frames(), _cfg())
    perturbed = walk_forward(_frames(drift_after={i: 0.05 for i in range(N_SYMBOLS)}), _cfg())

    assert plain.periods[0].long_symbols == perturbed.periods[0].long_symbols
    assert plain.periods[0].short_symbols == perturbed.periods[0].short_symbols
    # The outcome of the later period does change, which is the whole point of
    # measuring it: if it did not, the perturbation would not have done anything.
    assert plain.periods[1].long_return != perturbed.periods[1].long_return


def test_ranking_at_the_first_rebalance_ignores_every_later_bar():
    frames = _frames()
    first = rebalance_dates(frames, "M", start="2024-11-01")[0]
    # Replace every bar after the first rebalance with something absurd and
    # confirm the first period's chosen symbols are untouched.
    poisoned = {
        s: pd.concat(
            [
                f[f["trading_date"] <= pd.Timestamp(first)],
                pd.DataFrame(
                    {
                        "symbol": [s] * 10,
                        "trading_date": pd.bdate_range("2024-12-02", periods=10),
                        "open": [1e9] * 10,
                        "high": [1e9] * 10,
                        "low": [1e9] * 10,
                        "close": [1e9] * 10,
                        "volume": [10**9] * 10,
                    }
                ),
            ],
            ignore_index=True,
        )
        for s, f in frames.items()
    }
    a = walk_forward(frames, _cfg())
    b = walk_forward(poisoned, _cfg())
    assert a.periods[0].long_symbols == b.periods[0].long_symbols
    assert a.periods[0].short_symbols == b.periods[0].short_symbols


# ------------------------------------------------------- speed trim correctness


def test_the_trim_used_for_speed_returns_exactly_the_same_ranking():
    """Trimming to the factor window must not change a single answer.

    Every ranking factor is a trailing window whose widest member is 250 bars,
    so each symbol is trimmed before ranking. That is an optimisation, and an
    optimisation that alters results is a defect - so both paths are compared
    period by period rather than trusted.
    """
    wide = walk_forward(_frames(), _cfg(trim_window=100_000))
    trimmed = walk_forward(_frames(), _cfg(trim_window=FACTOR_HISTORY_WINDOW))

    assert [p.long_symbols for p in wide.periods] == [p.long_symbols for p in trimmed.periods]
    assert [p.short_symbols for p in wide.periods] == [p.short_symbols for p in trimmed.periods]
    for x, y in zip(wide.periods, trimmed.periods, strict=True):
        assert x.spread == pytest.approx(y.spread, abs=1e-12)


def test_a_trim_narrower_than_min_bars_cannot_starve_the_eligibility_gate():
    """The trim window is widened to ``min_bars`` so the gate sees the truth.

    If the trim were applied literally, a symbol with 64 bars and a 10-bar trim
    would look ineligible even though it has enough history. The gate must be
    answered from the trimmed length, which is why the effective window is
    ``max(trim_window, min_bars)``.
    """
    frames = _frames()
    narrow = walk_forward(frames, _cfg(trim_window=10, min_bars=64))
    wide = walk_forward(frames, _cfg(trim_window=250, min_bars=64))
    assert narrow.periods_used == wide.periods_used == 2
    assert [p.long_symbols for p in narrow.periods] == [p.long_symbols for p in wide.periods]


def test_factor_window_is_at_least_min_bars():
    assert _cfg(trim_window=10, min_bars=64).factor_window == 64
    assert _cfg(trim_window=250, min_bars=60).factor_window == 250


# ----------------------------------------------------------- missing outcomes


def test_a_stale_price_is_flagged_not_treated_as_fresh():
    """A carried-forward price is reported as stale, never as a fresh trade.

    S2's history ends on the first rebalance day, so its forward price for both
    periods is carried forward from 2024-11-29: the return is zero and the
    staleness is 32 and 49 calendar days. Both exceed :data:`STALE_DAYS`, so S2
    must appear in ``stale_outcome`` — a return of zero from a name that never
    traded is not the same thing as a name that traded flat.
    """
    result = walk_forward(_frames(truncate={"S2": "2024-11-29"}), _cfg())
    for period in result.periods:
        assert "S2" in period.stale_outcome
        assert "S2" not in period.missing_outcome
        assert period.outcome_returns["S2"] == 0.0
    # One stale symbol (S2) per period, over both periods.
    assert result.stale_symbols_total == len(result.periods)


def test_a_symbol_with_no_price_at_all_is_reported_missing():
    """``None`` from the price lookup is a missing outcome, never a zero."""
    frames = _frames()
    # Give S3 a frame that ends before the first rebalance: it cannot be
    # ranked, so the honest outcome is that it is absent, not that it returned 0.
    frames["S3"] = frames["S3"][frames["S3"]["trading_date"] < "2024-09-02"]
    result = walk_forward(frames, _cfg())
    assert all("S3" not in p.outcome_returns for p in result.periods)


def test_a_period_built_mostly_on_stale_prices_says_so():
    """Staleness is surfaced in the summary, not buried in a period."""
    result = walk_forward(_frames(truncate={"S2": "2024-11-29"}), _cfg())
    payload = result.to_dict()
    assert payload["summary"]["stale_symbols_total"] > 0


def test_a_universe_too_small_for_two_tails_is_skipped_with_a_reason():
    # Three symbols cannot supply two disjoint tails of round(3*0.5)=2, so the
    # period is skipped with a reason rather than silently shrinking the tails.
    frames = _frames(drop={"S3", "S4", "S5"})
    result = walk_forward(frames, _cfg(top_quantile=0.5))
    assert result.periods_used == 0
    assert result.skipped_periods
    assert "fewer than" in result.skipped_periods[0].note
    assert any("no period produced a measurable spread" in n for n in result.notes)


# ------------------------------------------------------------ chance baseline


def test_a_large_and_consistent_spread_beats_the_chance_baseline():
    result = walk_forward(_frames(), _cfg())
    d = result.to_dict()["chance_baseline"]
    assert d["permutations"] == 60
    assert d["observed_percentile"] is not None
    # A 15%/4% spread against a random distribution centred near zero.
    assert result.beats_chance is True
    assert d["observed_percentile"] >= 0.95


def test_the_chance_baseline_is_reproducible_and_ignores_the_seed_when_off():
    first = walk_forward(_frames(), _cfg(random_seed=1))
    second = walk_forward(_frames(), _cfg(random_seed=1))
    assert first.chance_mean_spread == second.chance_mean_spread
    assert first.chance_p95_spread == second.chance_p95_spread

    off = walk_forward(_frames(), _cfg(permutations=0))
    assert off.chance_mean_spread is None
    assert off.chance_p95_spread is None
    assert off.beats_chance is None
    assert off.to_dict()["chance_baseline"]["permutations"] == 0


def test_the_chance_baseline_is_computed_for_a_normal_run():
    """With last-price-carried-forward every ranked symbol has an outcome, so
    the null distribution can be drawn - which it could not be when a symbol
    that simply did not trade on the rebalance day was dropped instead."""
    result = walk_forward(_frames(), _cfg())
    d = result.to_dict()["chance_baseline"]
    assert d["mean_spread"] is not None
    assert d["p95_spread"] is not None
    assert d["observed_percentile"] is not None
    # The fixture's spread is large and consistent, so it clears the null.
    assert result.beats_chance is True


# ------------------------------------------------------------------- honesty


def test_every_result_carries_its_caveats():
    result = walk_forward(_frames(), _cfg())
    assert result.caveats == CAVEATS
    assert any("SURVIVORSHIP BIAS" in c for c in result.caveats)
    assert any("NO TRANSACTION COSTS" in c for c in result.caveats)
    assert any("not evidence of future returns" in c for c in result.caveats)


def test_the_chance_baseline_explains_what_it_is_in_the_payload():
    payload = walk_forward(_frames(), _cfg()).to_dict()
    explanation = payload["chance_baseline"]["what_it_means"]
    assert "random" in explanation
    assert "picking names out of a hat" in explanation


def test_config_validation_rejects_nonsensical_settings():
    assert WalkForwardConfig(top_quantile=0.7).validate()
    assert WalkForwardConfig(top_quantile=0.0).validate()
    assert WalkForwardConfig(frequency="W").validate()
    assert WalkForwardConfig(min_bars=0).validate()
    assert WalkForwardConfig(trim_window=0).validate()
    assert WalkForwardConfig(permutations=-1).validate()
    assert WalkForwardConfig(start="2026-01-01", end="2025-01-01").validate()
    assert _cfg().validate() == []
    # A 50/50 split is a legitimate "top half vs bottom half" test.
    assert WalkForwardConfig(top_quantile=0.5).validate() == []


def test_the_payload_keeps_the_period_detail_but_not_every_symbol():
    payload = walk_forward(_frames(), _cfg()).to_dict()
    assert payload["summary"]["periods_used"] == 2
    assert len(payload["periods"]) == 2
    period = payload["periods"][0]
    assert "outcome_returns" not in period, "per-symbol returns would dwarf the report"
    assert period["universe"] == 6
    assert period["long_symbols"] == ["S5", "S4"]
    assert payload["config"]["frequency_label"] == "monthly"


def test_an_empty_universe_is_reported_not_crashed():
    result = walk_forward({}, _cfg())
    assert result.periods == []
    assert result.periods_used == 0
    assert result.mean_spread is None
