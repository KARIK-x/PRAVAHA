"""Statistical-analysis tests — checked against hand/known values.

Where a closed form exists it is asserted directly (e.g. y = 3x + 2 has slope 3
and intercept 2). Distributional p-values are checked against published tables.
All fixtures are synthetic.
"""

from __future__ import annotations

import numpy as np
import pytest

from megatool import stats


def test_student_t_p_matches_published_table():
    # Two-sided t table: t=2.228, df=10 -> p=0.05 ; t=2.0, df=10 -> p=0.0734.
    assert stats.student_t_two_sided_p(2.228, 10) == pytest.approx(0.05, abs=2e-3)
    assert stats.student_t_two_sided_p(2.0, 10) == pytest.approx(0.0734, abs=2e-3)
    # t=0 gives p=1; df<=0 is undefined.
    assert stats.student_t_two_sided_p(0.0, 10) == pytest.approx(1.0, abs=1e-9)
    assert stats.student_t_two_sided_p(1.0, 0) is None


def test_descriptive_known_values():
    d = stats.descriptive([1, 2, 3, 4, 5])
    assert d["n"] == 5
    assert d["mean"] == pytest.approx(3.0)
    assert d["median"] == pytest.approx(3.0)
    assert d["std"] == pytest.approx(np.std([1, 2, 3, 4, 5], ddof=1))
    assert d["min"] == 1 and d["max"] == 5


def test_descriptive_empty_is_none_not_zero():
    d = stats.descriptive([])
    assert d["n"] == 0
    assert d["mean"] is None and d["std"] is None


def test_pearson_perfect_linear_is_one():
    x = np.arange(20, dtype=float)
    y = 2 * x + 1
    r = stats.pearson(x, y)
    assert r["r"] == pytest.approx(1.0, abs=1e-12)
    assert r["p"] == pytest.approx(0.0, abs=1e-6)
    assert r["n"] == 20


def test_spearman_handles_monotonic_nonlinearity():
    x = np.arange(15, dtype=float)
    y = np.exp(x)  # monotonic but not linear
    assert stats.pearson(x, y)["r"] < 0.999
    assert stats.spearman(x, y)["rho"] == pytest.approx(1.0, abs=1e-12)


def test_pearson_insufficient_points_is_none():
    assert stats.pearson([1.0, 2.0], [2.0, 4.0])["r"] is None


def test_ols_recovers_a_known_line():
    x = np.linspace(-5, 5, 41)
    y = 3 * x + 2
    fit = stats.ols(x, y)
    assert fit["slope"] == pytest.approx(3.0, abs=1e-9)
    assert fit["intercept"] == pytest.approx(2.0, abs=1e-9)
    assert fit["r2"] == pytest.approx(1.0, abs=1e-9)


def test_ols_constant_regressor_is_undefined():
    fit = stats.ols([5.0] * 10, list(range(10)))
    assert fit["slope"] is None and "reason" in fit


def test_return_statistics_total_and_drawdown():
    r = stats.return_statistics([100.0, 120.0, 90.0, 110.0])
    assert r["total_return"] == pytest.approx(0.10, abs=1e-12)
    assert r["max_drawdown"] == pytest.approx(-0.25, abs=1e-12)


def test_max_drawdown_duration_is_measured_correctly():
    r = stats.return_statistics([100.0, 120.0, 90.0, 110.0, 130.0])
    # Peak at index 1 (120); recovery to a new high at index 4 (130): 3 bars.
    assert r["max_drawdown_duration"] == 3


def test_flat_series_has_no_sharpe_or_volatility():
    r = stats.return_statistics([100.0] * 30)
    assert r["annualised_volatility"] == pytest.approx(0.0, abs=1e-12)
    assert r["sharpe"] is None  # zero variance -> undefined, not a fake number


def test_return_statistics_rejects_non_positive_prices():
    r = stats.return_statistics([100.0, 0.0, 50.0])
    assert r["total_return"] is None
    assert "undefined" in r["note"]


def test_rolling_correlation_of_identical_series_is_one():
    x = np.linspace(1, 50, 50) + np.sin(np.arange(50))
    rc = stats.rolling_correlation(x, x, window=10)
    assert rc[8] is None  # not enough data yet
    assert all(v == pytest.approx(1.0) for v in rc[9:] if v is not None)


def test_autocorrelation_of_a_trend_is_high():
    x = np.arange(30, dtype=float) + np.sin(np.arange(30) / 3.0)
    ac = stats.autocorrelation(x, lag=1)
    assert ac["r"] > 0.9


def test_variance_ratio_of_noise_is_near_one():
    rng = np.random.default_rng(7)
    noise = 100.0 * np.exp(np.cumsum(rng.normal(0, 0.01, 3000)))
    vr = stats.variance_ratio(noise, q=5)
    assert 0.85 < vr["vr"] < 1.15


def test_variance_ratio_of_mean_reverting_series_is_below_one():
    # Alternating up/down moves are negatively autocorrelated -> VR < 1.
    prices = 100.0 * np.cumprod(np.tile([1.02, 0.98], 200))
    vr = stats.variance_ratio(prices, q=5)
    assert vr["vr"] < 1.0


def test_correlation_matrix_shapes_and_signs():
    a = np.arange(40, dtype=float)
    b = a.copy()
    c = -a
    m = stats.correlation_matrix({"A": a, "B": b, "C": c})
    assert m["symbols"] == ["A", "B", "C"]
    assert m["matrix"][0][1] == pytest.approx(1.0)
    assert m["matrix"][0][2] == pytest.approx(-1.0)
    assert m["matrix"][0][0] == 1.0
    assert m["pair_n"][0][1] == 40


def test_correlation_matrix_rejects_bad_method():
    with pytest.raises(ValueError):
        stats.correlation_matrix({"A": [1, 2, 3]}, method="kendall")
