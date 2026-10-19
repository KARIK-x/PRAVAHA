"""Rolling-origin (walk-forward) forecast evaluation + leakage probes.

Every expected number here is derived by hand from the fixture series, not
from engine output:

* ``mean([1,2,3,4]) = 2.5`` against hold-out ``[5,6]`` gives
  RMSE = sqrt((2.5^2 + 3.5^2) / 2) = sqrt(9.25);
* the naive baseline forecasts ``4`` there, RMSE = sqrt((1^2 + 2^2)/2)
  = sqrt(2.5);
* skill ratio = sqrt(9.25 / 2.5) = sqrt(3.7).

The leakage tests are the point of this file: a model whose prediction
changes when data AFTER its training window changes has seen the future,
and no amount of good metrics can excuse that.

Fixtures are SYNTHETIC-TEST-FIXTURE series. Nothing here asserts anything
about real NEPSE prices.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from megatool.forecast import ForecastError, rolling_origin, run_forecast

# A clean 16-point chronological series with real dates (business days).
SERIES = np.arange(1.0, 17.0)
DATES = [str(d.date()) for d in pd.bdate_range("2026-01-01", periods=len(SERIES))]


# --------------------------------------------------------------- basic mechanics
def test_two_origins_hand_computed_mean_vs_naive():
    # train_min=4, holdout=2, step=2 over 8 points -> cuts at 4 and 6.
    r = rolling_origin(np.arange(1.0, 9.0), model="mean", train_min=4, holdout=2, step=2)
    assert [o["origin_index"] for o in r["origins"]] == [4, 6]

    first, second = r["origins"]
    # origin 4: mean([1,2,3,4]) = 2.5 vs [5,6] -> sqrt(9.25); naive 4 -> sqrt(2.5)
    assert first["train_points"] == 4 and first["test_points"] == 2
    assert first["model_rmse"] == pytest.approx(math.sqrt(9.25), abs=1e-6)
    assert first["naive_rmse"] == pytest.approx(math.sqrt(2.5), abs=1e-6)
    assert first["skill_ratio"] == pytest.approx(math.sqrt(3.7), abs=1e-6)
    # origin 6: mean([1..6]) = 3.5 vs [7,8] -> sqrt(16.25); naive 6 -> sqrt(2.5)
    assert second["model_rmse"] == pytest.approx(math.sqrt(16.25), abs=1e-6)
    assert second["skill_ratio"] == pytest.approx(math.sqrt(6.5), abs=1e-6)

    s = r["summary"]
    assert s["origins"] == 2
    assert s["origins_with_skill"] == 2
    assert s["origins_beating_naive"] == 0
    assert s["share_beating_naive_pct"] == 0.0
    assert s["mean_skill_ratio"] == pytest.approx((math.sqrt(3.7) + math.sqrt(6.5)) / 2, abs=1e-5)
    assert s["mean_naive_rmse"] == pytest.approx(math.sqrt(2.5), abs=1e-5)
    assert "NO DEMONSTRATED SKILL" in r["verdict"]


def test_perfect_linear_model_beats_naive_on_every_origin():
    r = rolling_origin(SERIES, model="linear_trend", train_min=6, holdout=3, step=3)
    assert r["summary"]["origins"] >= 3
    for o in r["origins"]:
        assert o["model_rmse"] == pytest.approx(0.0, abs=1e-9)
        assert o["skill_ratio"] == pytest.approx(0.0, abs=1e-9)
    assert r["summary"]["share_beating_naive_pct"] == 100.0
    assert r["verdict"].startswith("BEATS NAIVE ON ALL")
    # The verdict must still carry the caveat - a perfect score on one
    # synthetic line proves nothing about markets.
    assert "not proof of a tradeable edge" in r["verdict"]


def test_constant_series_is_undetermined_not_a_fake_100_pct_win():
    flat = np.full(16, 100.0)
    r = rolling_origin(flat, model="mean", train_min=4, holdout=2, step=2)
    assert r["summary"]["origins_with_skill"] == 0
    assert r["summary"]["share_beating_naive_pct"] is None
    assert r["verdict"].startswith("UNDETERMINED")
    assert any("flat hold-out" in w for w in r["warnings"])


def test_naive_model_is_self_referential_and_says_so():
    r = rolling_origin(SERIES, model="naive", train_min=6, holdout=3, step=3)
    assert all(o["skill_ratio"] is None for o in r["origins"])
    assert r["summary"]["origins_with_skill"] == 0
    assert r["verdict"].startswith("BASELINE")


def test_every_origin_is_strictly_chronological():
    r = rolling_origin(SERIES, model="holt", train_min=6, holdout=3, step=3, dates=DATES)
    assert len(r["origins"]) >= 2
    for o in r["origins"]:
        assert o["train_points"] == o["origin_index"]
        assert len(o["holdout_dates"]) == 3
        assert o["train_end_date"] < o["holdout_dates"][0]
        assert o["holdout_dates"][0] < o["holdout_dates"][-1]
        # the training window really did end before its own hold-out started
        cut = o["origin_index"]
        assert DATES[cut - 1] == o["train_end_date"]
        assert DATES[cut : cut + 3] == o["holdout_dates"]


def test_short_series_is_rejected_with_the_exact_requirement():
    with pytest.raises(ForecastError, match="at least 7 finite points"):
        rolling_origin(np.arange(1.0, 7.0), model="mean", train_min=4, holdout=3)


def test_bad_arguments_are_rejected():
    with pytest.raises(ForecastError, match="unknown model"):
        rolling_origin(SERIES, model="horoscope")
    with pytest.raises(ForecastError, match="unknown parameter"):
        rolling_origin(SERIES, model="holt", params={"banana": 1})
    with pytest.raises(ForecastError, match="holdout"):
        rolling_origin(SERIES, model="mean", holdout=0)
    with pytest.raises(ForecastError, match="train_min"):
        rolling_origin(SERIES, model="mean", train_min=2)
    with pytest.raises(ForecastError, match="seasonal_naive period"):
        rolling_origin(SERIES, model="seasonal_naive", train_min=6, params={"period": 12})


def test_non_finite_points_are_dropped_with_dates_kept_aligned():
    values = SERIES.copy()
    values[5] = np.nan
    dates = list(DATES)
    r = rolling_origin(values, model="mean", train_min=6, holdout=3, step=3, dates=dates)
    assert r["points_used"] == len(SERIES) - 1
    # alignment: every reported date is still a real fixture date and the
    # row count matches the finite-point count.
    flat = [d for o in r["origins"] for d in o["holdout_dates"]]
    assert set(flat) <= set(dates)
    with pytest.raises(ForecastError, match="dates"):
        rolling_origin(values, model="mean", dates=dates[:-1], holdout=3, train_min=6)


def test_result_is_deterministic():
    a = rolling_origin(SERIES, model="holt", train_min=6, holdout=3, step=3, dates=DATES)
    b = rolling_origin(SERIES, model="holt", train_min=6, holdout=3, step=3, dates=DATES)
    assert a == b


def test_carrying_warnings_and_assumptions():
    r = rolling_origin(np.arange(1.0, 9.0), model="mean", train_min=4, holdout=2, step=2)
    assert any("only 2 evaluation origin" in w for w in r["warnings"])
    assert any("hold-out windows of 2" in w for w in r["warnings"])
    joined = " ".join(r["assumptions"])
    assert "no random split of time series" in joined
    assert "not a forecast, a recommendation" in joined
    assert "UNADJUSTED" in joined


# ---------------------------------------------------------------- leakage probes
def test_rolling_origin_never_uses_data_after_an_origins_window():
    """An origin at cut 4 must be blind to points 6+ (its future).

    The probe tampers with the series strictly AFTER origin 4's hold-out.
    Origin 4's result must be bit-identical while a later origin - which
    trains on the tampered points - must change. The second assertion keeps
    the first from being vacuous: it proves the probe is data-sensitive at all.
    """
    base = np.arange(1.0, 17.0)
    tampered = base.copy()
    tampered[6:] = np.array([999.0, -50.0, 7.5, 123.0, 4.0, 8.0, 61.0, 3.0, 55.0, 12.0])
    a = rolling_origin(base, model="mean", train_min=4, holdout=2, step=2)
    b = rolling_origin(tampered, model="mean", train_min=4, holdout=2, step=2)
    a4 = next(o for o in a["origins"] if o["origin_index"] == 4)
    b4 = next(o for o in b["origins"] if o["origin_index"] == 4)
    assert a4 == b4  # unchanged: cut 4 cannot see points 6+
    a8 = next(o for o in a["origins"] if o["origin_index"] == 8)
    b8 = next(o for o in b["origins"] if o["origin_index"] == 8)
    assert a8 != b8  # changed: cut 8 trains on tampered points 6,7


def test_run_forecast_holdout_predictions_ignore_holdout_values():
    """The single-hold-out fit must depend on the TRAIN segment only.

    Inflating the last 5 points (the hold-out) by +1000 must move `actual`
    but not one digit of `predicted` - otherwise the model trained on its
    own test window.
    """
    base = np.arange(1.0, 21.0)
    holdout = 5
    a = run_forecast(base, model="mean", horizon=3, holdout=holdout)
    tampered = base.copy()
    tampered[-holdout:] += 1000
    b = run_forecast(tampered, model="mean", horizon=3, holdout=holdout)

    pred_a = [row["predicted"] for row in a.holdout]
    pred_b = [row["predicted"] for row in b.holdout]
    assert pred_a == pred_b
    actual_a = [row["actual"] for row in a.holdout]
    actual_b = [row["actual"] for row in b.holdout]
    assert actual_a != actual_b  # the probe really did move the test segment
    # The forward projection is a DIFFERENT animal: once the hold-out has been
    # scored, the deployed model refits on ALL available data (train +
    # hold-out), because for future points every past observation is fair
    # game. For the mean model that is exactly mean(series): 10.5 on the
    # untouched series, 260.5 once the tail is inflated.
    assert a.forecast[0]["value"] == pytest.approx(float(np.mean(base)))
    assert b.forecast[0]["value"] == pytest.approx(float(np.mean(tampered)))


def test_rolling_origin_advances_forward_not_backward():
    r = rolling_origin(SERIES, model="mean", train_min=4, holdout=3, step=5, dates=DATES)
    cuts = [o["origin_index"] for o in r["origins"]]
    assert cuts == sorted(cuts) and len(set(cuts)) == len(cuts)
    assert cuts[0] == 4  # first origin trains on exactly train_min points
