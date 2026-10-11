"""Forecasting Lab tests. Every expectation is computed by hand."""

from __future__ import annotations

import json

import numpy as np
import pytest

from megatool.forecast import (
    MODELS,
    ForecastError,
    compare_models,
    directional_accuracy,
    mae,
    mape,
    naive_drift_check,
    rmse,
    run_forecast,
    smape,
)


# -------------------------------------------------------------------- metrics
def test_mae_rmse_known_values():
    actual = np.array([10.0, 10.0, 10.0])
    pred = np.array([7.0, 13.0, 10.0])
    assert mae(actual, pred) == pytest.approx(2.0)
    assert rmse(actual, pred) == pytest.approx(np.sqrt((9 + 9 + 0) / 3))


def test_mape_ignores_zero_actuals():
    actual = np.array([0.0, 100.0])
    pred = np.array([5.0, 110.0])
    assert mape(actual, pred) == pytest.approx(10.0)  # only the 100 point counts


def test_mape_is_none_when_every_actual_is_zero():
    assert mape(np.zeros(4), np.zeros(4)) is None
    assert smape(np.zeros(4), np.zeros(4)) is None


def test_directional_accuracy_counts_signs_only():
    actual = np.array([105.0, 95.0, 105.0])
    pred = np.array([101.0, 99.0, 99.0])
    base = np.array([100.0, 100.0, 100.0])
    # directions: actual +,-,+ ; pred +,-,-  -> 2 of 3 agree
    assert directional_accuracy(actual, pred, base) == pytest.approx(200 / 3)


def test_directional_accuracy_none_when_no_movement():
    assert directional_accuracy(np.ones(3), np.ones(3), np.ones(3)) is None


# -------------------------------------------------------------- model behaviour
def test_naive_scores_against_the_training_window():
    # train = the first 10 points (all 100), so naive predicts 100 while the
    # hold-out is 110 -> a constant error of 10.
    series = [100.0] * 10 + [110.0] * 3
    r = run_forecast(series, model="naive", horizon=3, holdout=3)
    assert [h["predicted"] for h in r.holdout] == [100.0] * 3
    assert r.metrics["rmse"] == pytest.approx(10.0)
    assert r.metrics["mae"] == pytest.approx(10.0)
    assert r.metrics["mape"] == pytest.approx(10 / 110 * 100.0)
    # The FUTURE forecast is refitted on all 13 points, so it uses 110.
    assert [f["value"] for f in r.forecast] == pytest.approx([110.0] * 3)


def test_naive_is_labelled_the_baseline_not_a_failure():
    # Reporting a 1.0 skill ratio for the naive model would be self-referential
    # (it cannot beat itself), and calling it 'no demonstrated skill' would be
    # nonsense. It is labelled BASELINE and carries no skill ratio.
    r = run_forecast([100.0] * 10 + [110.0] * 3, model="naive", horizon=3, holdout=3)
    assert r.verdict.startswith("BASELINE")
    assert r.metrics["rmse_skill_ratio"] is None
    assert "cannot beat itself" in r.verdict


def test_naive_skill_ratio_is_undefined_when_the_window_is_flat():
    r = run_forecast([100.0] * 20, model="naive", horizon=3, holdout=3)
    # It is the baseline regardless of the window...
    assert r.verdict.startswith("BASELINE")
    assert r.metrics["rmse_skill_ratio"] is None
    # ...and the flat window is still reported, because nothing could be scored.
    assert any("no variation" in w for w in r.warnings)


def test_linear_trend_fits_a_perfect_line():
    series = np.arange(1.0, 31.0)
    r = run_forecast(series, model="linear_trend", horizon=3, holdout=3)
    assert r.metrics["rmse"] == pytest.approx(0.0, abs=1e-9)
    assert r.metrics["naive_rmse"] == pytest.approx(np.sqrt((1 + 4 + 9) / 3))
    assert r.metrics["rmse_skill_ratio"] == pytest.approx(0.0, abs=1e-9)
    assert r.verdict.startswith("BEATS NAIVE")
    # The future forecast is refitted on the full series (1..30), so it
    # continues the line rather than repeating the hold-out window.
    assert [f["value"] for f in r.forecast] == pytest.approx([31.0, 32.0, 33.0])


def test_drift_extrapolates_the_average_change():
    r = run_forecast(np.arange(1.0, 21.0), model="drift", horizon=3, holdout=3)
    # The hold-out is scored against the training window (step = 1)...
    assert [h["predicted"] for h in r.holdout] == pytest.approx([18.0, 19.0, 20.0])
    assert r.metrics["rmse"] == pytest.approx(0.0, abs=1e-9)
    # ...and the future forecast continues from the end of the full series.
    assert [f["value"] for f in r.forecast] == pytest.approx([21.0, 22.0, 23.0])


def test_mean_forecast_is_the_full_series_mean_for_future_steps():
    series = [1.0, 2.0, 3.0, 4.0, 10.0, 20.0]
    r = run_forecast(series, model="mean", horizon=2, holdout=2)
    # Future steps are refitted on all 6 points -> mean 40/6 (rounded to 4dp).
    assert [f["value"] for f in r.forecast] == pytest.approx([40 / 6, 40 / 6], abs=1e-4)
    # The hold-out is scored against the training mean (1+2+3+4)/4 = 2.5.
    assert [h["predicted"] for h in r.holdout] == pytest.approx([2.5, 2.5])


def test_seasonal_naive_repeats_the_cycle():
    series = [1.0, 2.0, 3.0, 4.0] * 8  # 32 points, exact period 4
    r = run_forecast(series, model="seasonal_naive", horizon=4, holdout=4, params={"period": 4})
    assert [h["predicted"] for h in r.holdout] == pytest.approx([1.0, 2.0, 3.0, 4.0])
    assert r.metrics["rmse"] == pytest.approx(0.0)
    assert r.verdict.startswith("BEATS NAIVE")


def test_holt_stays_flat_on_a_constant_series():
    r = run_forecast([50.0] * 30, model="holt", horizon=3, holdout=3)
    assert [f["value"] for f in r.forecast] == pytest.approx([50.0, 50.0, 50.0])


def test_holt_follows_an_trend_reasonably():
    series = np.arange(1.0, 41.0) * 2.0  # exact line, slope 2
    r = run_forecast(series, model="holt", horizon=5, holdout=5, params={"alpha": 0.5, "beta": 0.5})
    # A perfect line is what Holt is built for; it should be very close.
    assert r.metrics["rmse"] < 1.0


def test_all_registered_models_run():
    series = list(np.linspace(100, 160, 120)) + list(np.linspace(160, 90, 80))
    for key in MODELS:
        r = run_forecast(series, model=key, horizon=5, holdout=10)
        assert len(r.forecast) == 5, key
        assert len(r.holdout) == 10, key
        assert r.verdict, key


def test_forecast_is_deterministic():
    series = list(np.linspace(100, 150, 60))
    a = run_forecast(series, model="holt", horizon=4, holdout=6).to_dict()
    b = run_forecast(series, model="holt", horizon=4, holdout=6).to_dict()
    assert a == b


def test_result_is_json_serialisable():
    r = run_forecast(list(np.linspace(100, 150, 60)), horizon=3, holdout=5)
    payload = json.dumps(r.to_dict())
    assert '"verdict"' in payload and '"assumptions"' in payload


# ------------------------------------------------------------------ guardrails
def test_unknown_model_rejected():
    with pytest.raises(ForecastError, match="unknown model"):
        run_forecast([1.0] * 30, model="crystal_ball")


def test_unknown_parameter_rejected():
    with pytest.raises(ForecastError, match="unknown parameter"):
        run_forecast([1.0] * 30, model="holt", params={"gamma": 0.5})


def test_zero_horizon_rejected():
    with pytest.raises(ForecastError, match="horizon"):
        run_forecast([1.0] * 30, horizon=0)


def test_too_little_data_rejected():
    with pytest.raises(ForecastError, match="need at least"):
        run_forecast([1.0, 2.0, 3.0], horizon=5, holdout=3)


def test_seasonal_naive_needs_a_full_period_of_history():
    with pytest.raises(ForecastError, match="need at least"):
        run_forecast([1.0] * 6, model="seasonal_naive", horizon=2, holdout=2, params={"period": 5})


def test_non_finite_points_are_dropped():
    series = [1.0, np.nan, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
    r = run_forecast(series, horizon=2, holdout=2)
    assert r.train_points + r.test_points == 10


# -------------------------------------------------------------------- ranking
def test_compare_models_ranks_by_holdout_rmse():
    series = np.arange(1.0, 41.0)
    out = compare_models(series, horizon=3, holdout=5)
    rmses = [row["rmse"] for row in out["ranking"]]
    assert rmses == sorted(rmses)
    assert out["naive_rmse"] == pytest.approx(np.sqrt(np.mean((np.arange(36.0, 41.0) - 35.0) ** 2)))
    assert "single sample" in out["note"]


def test_compare_models_reports_models_it_could_not_run():
    # 5 points is enough for the naive model (needs holdout + 3) but far too
    # short for a 5-step seasonal cycle.
    out = compare_models([1.0] * 5, horizon=1, holdout=1, models=["naive", "seasonal_naive"])
    assert "seasonal_naive" in out["errors"]
    assert any(row["model"] == "naive" for row in out["ranking"])


# ------------------------------------------------------- random-walk diagnostics
def test_random_walk_diagnostics_on_a_random_walk():
    rng = np.random.default_rng(7)
    series = 100 + np.cumsum(rng.normal(0, 1, 400))
    d = naive_drift_check(series)
    assert d["available"] is True
    # A random walk: changes are uncorrelated, variance ratio near 1.
    assert abs(d["lag1_change_autocorr"]) < 0.2
    assert 0.6 < d["variance_ratio_5"] < 1.5


def test_random_walk_diagnostics_detect_autocorrelated_changes():
    rng = np.random.default_rng(11)
    # Changes with AR(1) coefficient 0.8: momentum, clearly not a random walk.
    e = np.zeros(400)
    for i in range(1, 400):
        e[i] = 0.8 * e[i - 1] + rng.normal(0, 1)
    d = naive_drift_check(100 + np.cumsum(e))
    assert d["available"] is True
    assert d["lag1_change_autocorr"] > 0.5


def test_random_walk_diagnostics_are_undefined_on_a_perfect_line():
    # A deterministic trend has zero-variance changes, so an autocorrelation
    # does not exist. Reporting None is the honest answer.
    d = naive_drift_check(np.arange(1.0, 201.0))
    assert d["available"] is True
    assert d["lag1_change_autocorr"] is None
    assert d["variance_ratio_5"] is None


def test_random_walk_diagnostics_need_data():
    d = naive_drift_check([1.0, 2.0, 3.0])
    assert d["available"] is False
    assert "at least 12" in d["reason"]
