"""Forecasting Lab: honest baselines rather than impressive-looking numbers.

Every forecast here is measured against the **naive baseline** (the last
observed value) on a hold-out window the model never saw. If a model cannot
beat that baseline, the result says so in plain words. A model that does not
beat "use yesterday's close" has demonstrated no predictive skill, however
smooth its curve looks.

WHAT THIS IS NOT
----------------
It is not a prediction of price. Price series are close to a random walk, and
nothing in this module claims otherwise. Outputs carry assumptions and a
verdict, and the interval is the *historical error distribution* - not a
calibrated confidence interval.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import Any

import numpy as np
import pandas as pd

MODELS: dict[str, dict[str, Any]] = {
    "naive": {
        "label": "Naive (last value)",
        "description": "Forecast every future step as the last observed value. "
        "The benchmark every other model must beat.",
        "params": {},
    },
    "drift": {
        "label": "Drift (mean change)",
        "description": "Last value plus the average historical change per step.",
        "params": {},
    },
    "mean": {
        "label": "Historical mean",
        "description": "Forecast the training mean for every future step.",
        "params": {},
    },
    "seasonal_naive": {
        "label": "Seasonal naive",
        "description": "Repeat the value from `period` steps ago. Useful only if "
        "the series genuinely repeats; NEPSE has no established daily "
        "seasonality, so this is included to be tested, not trusted.",
        "params": {"period": 5},
    },
    "holt": {
        "label": "Holt linear trend",
        "description": "Double exponential smoothing: level + trend, extended "
        "forward. Sensitive to alpha/beta.",
        "params": {"alpha": 0.3, "beta": 0.1},
    },
    "linear_trend": {
        "label": "Linear trend (OLS)",
        "description": "Fit a straight line by ordinary least squares over the "
        "training window and extend it. A line fitted to a random walk will "
        "look confident and be wrong.",
        "params": {},
    },
}


class ForecastError(ValueError):
    """Invalid forecasting input."""


@dataclass
class ForecastResult:
    model: str
    label: str
    params: dict[str, Any]
    series_start: str
    series_end: str
    train_points: int
    test_points: int
    horizon: int
    holdout: list[dict[str, Any]]
    forecast: list[dict[str, Any]]
    metrics: dict[str, Any]
    verdict: str
    assumptions: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _naive_forecast(history: np.ndarray, horizon: int) -> np.ndarray:
    return np.repeat(history[-1], horizon)


def _drift_forecast(history: np.ndarray, horizon: int) -> np.ndarray:
    if len(history) < 2:
        return _naive_forecast(history, horizon)
    step = (history[-1] - history[0]) / (len(history) - 1)
    return history[-1] + step * np.arange(1, horizon + 1)


def _mean_forecast(history: np.ndarray, horizon: int) -> np.ndarray:
    return np.repeat(float(np.mean(history)), horizon)


def _seasonal_naive_forecast(history: np.ndarray, horizon: int, period: int) -> np.ndarray:
    if period < 1:
        raise ForecastError("period must be >= 1")
    if period > len(history):
        raise ForecastError(
            f"seasonal_naive needs {period} training points for its cycle but only "
            f"{len(history)} are available"
        )
    out = np.empty(horizon, dtype=float)
    for h in range(horizon):
        out[h] = history[-period + (h % period)]
    return out


def _holt_forecast(history: np.ndarray, horizon: int, alpha: float, beta: float) -> np.ndarray:
    level = float(history[0])
    trend = float(history[1] - history[0]) if len(history) > 1 else 0.0
    for value in history[1:]:
        prev_level = level
        level = alpha * value + (1 - alpha) * (level + trend)
        trend = beta * (level - prev_level) + (1 - beta) * trend
    return level + trend * np.arange(1, horizon + 1)


def _linear_trend_forecast(history: np.ndarray, horizon: int) -> np.ndarray:
    x = np.arange(len(history), dtype=float)
    slope, intercept = np.polyfit(x, history, 1)
    future_x = np.arange(len(history), len(history) + horizon, dtype=float)
    return slope * future_x + intercept


def _fit(model: str, history: np.ndarray, horizon: int, params: dict[str, Any]) -> np.ndarray:
    if model == "naive":
        return _naive_forecast(history, horizon)
    if model == "drift":
        return _drift_forecast(history, horizon)
    if model == "mean":
        return _mean_forecast(history, horizon)
    if model == "seasonal_naive":
        return _seasonal_naive_forecast(history, horizon, int(params["period"]))
    if model == "holt":
        return _holt_forecast(history, horizon, float(params["alpha"]), float(params["beta"]))
    if model == "linear_trend":
        return _linear_trend_forecast(history, horizon)
    raise ForecastError(f"unknown model {model!r}; known: {', '.join(sorted(MODELS))}")


# --------------------------------------------------------------------- metrics
def mae(actual: np.ndarray, predicted: np.ndarray) -> float:
    return float(np.mean(np.abs(actual - predicted)))


def rmse(actual: np.ndarray, predicted: np.ndarray) -> float:
    return float(np.sqrt(np.mean((actual - predicted) ** 2)))


def mape(actual: np.ndarray, predicted: np.ndarray) -> float | None:
    """Mean absolute percentage error, ignoring zero actuals (undefined there)."""
    mask = actual != 0
    if not mask.any():
        return None
    return float(np.mean(np.abs((actual[mask] - predicted[mask]) / actual[mask])) * 100.0)


def smape(actual: np.ndarray, predicted: np.ndarray) -> float | None:
    denom = (np.abs(actual) + np.abs(predicted)) / 2.0
    mask = denom != 0
    if not mask.any():
        return None
    return float(np.mean(np.abs(actual[mask] - predicted[mask]) / denom[mask]) * 100.0)


def directional_accuracy(
    actual: np.ndarray, predicted: np.ndarray, baseline: np.ndarray
) -> float | None:
    """Fraction of steps where the model moved in the same direction as the
    realisation *relative to the baseline*."""
    a = actual - baseline
    p = predicted - baseline
    mask = (a != 0) & (p != 0)
    if not mask.any():
        return None
    return float(np.mean(np.sign(a[mask]) == np.sign(p[mask])) * 100.0)


# ----------------------------------------------------------------------- engine
def run_forecast(
    values: np.ndarray | pd.Series,
    model: str = "naive",
    horizon: int = 5,
    holdout: int | None = None,
    params: dict[str, Any] | None = None,
    dates: list[str] | None = None,
) -> ForecastResult:
    """Fit ``model`` on the training window and score it on a hold-out window.

    ``holdout`` defaults to ``horizon``. The model never sees the hold-out.
    """
    if model not in MODELS:
        raise ForecastError(f"unknown model {model!r}; known: {', '.join(sorted(MODELS))}")
    spec = MODELS[model]
    merged = {**spec["params"], **(params or {})}
    unknown = set(merged) - set(spec["params"])
    if unknown:
        raise ForecastError(
            f"{model}: unknown parameter(s) {sorted(unknown)}; allowed {sorted(spec['params'])}"
        )

    raw = np.asarray(values.to_numpy() if isinstance(values, pd.Series) else values, dtype=float)
    # Non-finite points are dropped, so the dates must be dropped with them.
    # Filtering the series alone silently shifts every hold-out row onto the
    # wrong date, which is worse than showing nothing: it misdates evidence.
    finite = np.isfinite(raw)
    series = raw[finite]
    date_list = None if dates is None else [str(d) for d in dates]
    if date_list is not None:
        if len(date_list) != len(raw):
            raise ForecastError(f"dates has {len(date_list)} entries but the series has {len(raw)}")
        date_list = [d for d, keep in zip(date_list, finite, strict=True) if keep]
    horizon = int(horizon)
    if horizon < 1:
        raise ForecastError("horizon must be >= 1")
    holdout_n = int(holdout) if holdout else horizon

    min_points = max(2, holdout_n + 3)
    if model == "seasonal_naive":
        # The TRAINING window (everything but the hold-out) must still hold a
        # complete cycle, so the requirement is period + holdout, not period.
        min_points = max(min_points, int(merged["period"]) + holdout_n)
    if len(series) < min_points:
        raise ForecastError(
            f"need at least {min_points} finite points for {model} with a hold-out "
            f"of {holdout_n}, got {len(series)}"
        )

    train = series[:-holdout_n]
    test = series[-holdout_n:]

    try:
        predicted = _fit(model, train, holdout_n, merged)
    except ValueError as exc:
        raise ForecastError(f"{model} could not be fitted: {exc}") from exc

    baseline = _naive_forecast(train, holdout_n)
    naive_err = rmse(test, baseline)
    model_err = rmse(test, predicted)
    # The naive model IS the baseline, so reporting a skill ratio of exactly
    # 1.0 for it would be self-referential: there is nothing for it to beat.
    skill = None if (naive_err == 0 or model == "naive") else model_err / naive_err

    warnings: list[str] = []
    if naive_err == 0:
        warnings.append(
            "the hold-out window has no variation, so the naive baseline scores "
            "a perfect zero and no skill ratio can be computed"
        )
    if holdout_n < 10:
        warnings.append(
            f"only {holdout_n} hold-out point(s): these error figures are noise, not evidence"
        )
    if model == "naive":
        verdict = (
            "BASELINE: this is the naive last-value forecast. Every other model's "
            "skill ratio is measured against it, so it has no skill ratio of its "
            "own and cannot beat itself."
        )
    elif skill is None:
        verdict = (
            "UNDETERMINED: the naive baseline is perfect on this window, so no skill ratio exists."
        )
    elif skill >= 1.0:
        verdict = (
            f"NO DEMONSTRATED SKILL: this model's RMSE is {skill:.2f}x the naive "
            "baseline on data it never saw. The naive (last value) forecast is "
            "the better forecast for this window."
        )
    else:
        verdict = (
            f"BEATS NAIVE ON THIS HOLD-OUT (RMSE ratio {skill:.2f}). One hold-out "
            "window on one series is not evidence of a tradeable edge: it is a "
            "single sample that could be luck."
        )

    if date_list is None:
        date_list = [str(i) for i in range(len(series))]
    dates = date_list
    holdout_start = len(series) - holdout_n

    residuals = test - predicted
    lo, hi = (
        (float(np.percentile(residuals, 5)), float(np.percentile(residuals, 95)))
        if len(residuals) >= 2
        else (0.0, 0.0)
    )

    return ForecastResult(
        model=model,
        label=spec["label"],
        params=merged,
        series_start=str(dates[0]),
        series_end=str(dates[-1]),
        train_points=int(len(train)),
        test_points=int(holdout_n),
        horizon=horizon,
        holdout=[
            {
                "date": str(dates[holdout_start + i]),
                "actual": round(float(test[i]), 4),
                "predicted": round(float(predicted[i]), 4),
                "naive": round(float(baseline[i]), 4),
                "error": round(float(test[i] - predicted[i]), 4),
            }
            for i in range(holdout_n)
        ],
        forecast=[
            {
                "step": i + 1,
                "value": round(float(v), 4),
                "interval_low": round(float(v + lo), 4),
                "interval_high": round(float(v + hi), 4),
            }
            for i, v in enumerate(_fit(model, series, horizon, merged))
        ],
        metrics={
            "mae": round(mae(test, predicted), 6),
            "rmse": round(model_err, 6),
            "mape": None if mape(test, predicted) is None else round(mape(test, predicted), 6),
            "smape": None if smape(test, predicted) is None else round(smape(test, predicted), 6),
            # Measured AGAINST the naive baseline's direction, not against a
            # zero move: it counts days where (actual - baseline) and
            # (predicted - baseline) agree in sign. The name carries the
            # qualifier so no UI can present it as a plain direction hit-rate.
            "directional_accuracy_vs_naive_pct": None
            if directional_accuracy(test, predicted, baseline) is None
            else round(directional_accuracy(test, predicted, baseline), 4),
            "naive_rmse": round(naive_err, 6),
            "rmse_skill_ratio": None if skill is None else round(skill, 6),
            "last_value": round(float(series[-1]), 4),
        },
        verdict=verdict,
        assumptions=[
            f"Model: {spec['label']} with params {merged}.",
            f"Fit on the first {len(train)} points and scored on the last "
            f"{holdout_n}, which the model never saw.",
            "The comparison baseline is the naive 'last value' forecast. A model "
            "that does not beat it has demonstrated no predictive skill.",
            "The interval shown for future steps is the 5th-95th percentile of "
            "the HISTORICAL hold-out errors - it is not a calibrated confidence "
            "interval and says nothing about tail risk.",
            "Prices are UNADJUSTED for bonus/rights issues.",
            "No fundamentals, macro news, circuit breakers, liquidity or "
            "sentiment enter this calculation.",
            "A single hold-out window is one sample. It cannot establish that a "
            "model will work in future.",
            "Nothing here is investment advice, and no figure is a promise of future performance.",
        ],
        warnings=warnings,
    )


def compare_models(
    values: np.ndarray | pd.Series,
    horizon: int = 5,
    holdout: int | None = None,
    dates: list[str] | None = None,
    models: list[str] | None = None,
) -> dict[str, Any]:
    """Score every model on the identical split, ranked by hold-out RMSE."""
    keys = models or list(MODELS)
    rows = []
    errors: dict[str, str] = {}
    for key in keys:
        try:
            r = run_forecast(values, model=key, horizon=horizon, holdout=holdout, dates=dates)
            rows.append(
                {
                    "model": key,
                    "label": r.label,
                    "rmse": r.metrics["rmse"],
                    "mae": r.metrics["mae"],
                    "mape": r.metrics["mape"],
                    "rmse_skill_ratio": r.metrics["rmse_skill_ratio"],
                    "verdict": r.verdict,
                }
            )
        except ForecastError as exc:
            errors[key] = str(exc)
    rows.sort(key=lambda r: (r["rmse"] is None, r["rmse"]))
    naive = next((r["rmse"] for r in rows if r["model"] == "naive"), None)
    return {
        "holdout": int(holdout or horizon),
        "ranking": rows,
        "errors": errors,
        "naive_rmse": naive,
        "note": "All models are scored on the identical hold-out window. Beating "
        "the naive baseline on one window is not evidence of a tradeable edge; "
        "it is a single sample.",
        "assumptions": [
            "Every model sees exactly the same training data and is scored on "
            "the same unseen hold-out window.",
            "Prices are unadjusted for bonus/rights issues, so these are price "
            "changes, not total returns.",
            "No transaction costs are modelled (this is price forecasting, not "
            "a strategy backtest).",
        ],
    }


def rolling_origin(
    values: np.ndarray | pd.Series,
    model: str = "naive",
    train_min: int = 20,
    holdout: int = 5,
    step: int = 5,
    params: dict[str, Any] | None = None,
    dates: list[str] | None = None,
) -> dict[str, Any]:
    """Chronological rolling-origin evaluation: the walk-forward of forecasting.

    Unlike :func:`run_forecast`'s single hold-out (one sample), this advances
    the evaluation origin forward in time repeatedly:

    * origin at cut ``c``: fit on ``series[:c]``, score on ``series[c:c+holdout]``;
    * origins start at ``train_min`` and advance by ``step``;
    * every origin's model sees only data STRICTLY BEFORE its own hold-out,
      so there is no way for a future value to leak into an earlier origin's
      fit (the property is asserted by ``test_rolling_origin_never_sees_a_future_value``).

    Each origin is scored against the naive last-value baseline, exactly like
    :func:`run_forecast`, and the summary reports how often the model beat it.
    """
    if model not in MODELS:
        raise ForecastError(f"unknown model {model!r}; known: {', '.join(sorted(MODELS))}")
    spec = MODELS[model]
    merged = {**spec["params"], **(params or {})}
    unknown = set(merged) - set(spec["params"])
    if unknown:
        raise ForecastError(
            f"{model}: unknown parameter(s) {sorted(unknown)}; allowed {sorted(spec['params'])}"
        )

    holdout = int(holdout)
    step = int(step)
    train_min = int(train_min)
    if holdout < 1:
        raise ForecastError("holdout must be >= 1")
    if step < 1:
        raise ForecastError("step must be >= 1")
    if train_min < 3:
        raise ForecastError("train_min must be >= 3")

    raw = np.asarray(values.to_numpy() if isinstance(values, pd.Series) else values, dtype=float)
    finite = np.isfinite(raw)
    series = raw[finite]
    date_list = None if dates is None else [str(d) for d in dates]
    if date_list is not None:
        if len(date_list) != len(raw):
            raise ForecastError(f"dates has {len(date_list)} entries but the series has {len(raw)}")
        date_list = [d for d, keep in zip(date_list, finite, strict=True) if keep]

    need = train_min + holdout
    if len(series) < need:
        raise ForecastError(
            f"rolling-origin needs at least {need} finite points "
            f"(train_min {train_min} + holdout {holdout}), got {len(series)}"
        )
    if model == "seasonal_naive":
        period = int(merged["period"])
        if period > train_min:
            raise ForecastError(
                f"seasonal_naive period {period} exceeds train_min {train_min}: "
                "the training window could not hold one full cycle at every origin"
            )

    cuts = list(range(train_min, len(series) - holdout + 1, step))
    origins: list[dict[str, Any]] = []
    skills: list[float] = []
    model_rmses: list[float] = []
    naive_rmses: list[float] = []
    undefined_naive = 0

    for cut in cuts:
        train = series[:cut]
        test = series[cut : cut + holdout]
        predicted = _fit(model, train, holdout, merged)
        baseline = _naive_forecast(train, holdout)
        m_err = rmse(test, predicted)
        n_err = rmse(test, baseline)
        model_rmses.append(m_err)
        naive_rmses.append(n_err)
        if n_err == 0 or model == "naive":
            skill: float | None = None
            if n_err == 0:
                undefined_naive += 1
        else:
            skill = m_err / n_err
            skills.append(skill)
        row: dict[str, Any] = {
            "origin_index": cut,
            "train_points": cut,
            "test_points": holdout,
            "model_rmse": round(m_err, 6),
            "naive_rmse": round(n_err, 6),
            "skill_ratio": None if skill is None else round(skill, 6),
        }
        if date_list is not None:
            row["train_end_date"] = date_list[cut - 1]
            row["holdout_dates"] = [date_list[cut + i] for i in range(holdout)]
        origins.append(row)

    n_origins = len(origins)
    beating = sum(1 for s in skills if s < 1.0)
    share = (100.0 * beating / len(skills)) if skills else None
    mean_skill = float(np.mean(skills)) if skills else None
    median_skill = float(np.median(skills)) if skills else None

    warnings: list[str] = []
    if n_origins < 3:
        warnings.append(
            f"only {n_origins} evaluation origin(s): this is barely more than a "
            "single hold-out window, not a distribution of results"
        )
    if holdout < 10:
        warnings.append(
            f"hold-out windows of {holdout} point(s) are noisy; per-origin skill "
            "ratios on such short windows are not evidence"
        )
    if undefined_naive:
        warnings.append(
            f"{undefined_naive} origin(s) had a flat hold-out (naive baseline "
            "perfect), so no skill ratio exists there"
        )

    if model == "naive":
        verdict = (
            "BASELINE: this IS the naive last-value forecast evaluated at every "
            "origin. It has no skill ratio of its own; use it as the bar others "
            "must clear."
        )
    elif not skills:
        verdict = (
            "UNDETERMINED: no origin produced a defined skill ratio (flat "
            "hold-outs), so nothing can be said about this model on this series."
        )
    elif share == 100.0:
        verdict = (
            f"BEATS NAIVE ON ALL {len(skills)} ORIGINS (mean RMSE ratio "
            f"{mean_skill:.2f}). Repeatedly winning on one series is still one "
            "series: it is not proof of a tradeable edge on other symbols or "
            "in future data."
        )
    elif share is not None and share >= 50.0:
        verdict = (
            f"MIXED: beats the naive baseline on {beating} of {len(skills)} "
            f"origins (mean RMSE ratio {mean_skill:.2f}). Inconsistent - no "
            "demonstrated skill."
        )
    else:
        verdict = (
            f"NO DEMONSTRATED SKILL: beats the naive baseline on only {beating} "
            f"of {len(skills)} origins (mean RMSE ratio {mean_skill:.2f}). The "
            "last-value forecast was the better forecast on most windows."
        )

    return {
        "model": model,
        "label": spec["label"],
        "params": merged,
        "train_min": train_min,
        "holdout": holdout,
        "step": step,
        "points_used": int(len(series)),
        "series_start": str(date_list[0]) if date_list else "0",
        "series_end": str(date_list[-1]) if date_list else str(len(series) - 1),
        "origins": origins,
        "summary": {
            "origins": n_origins,
            "origins_with_skill": len(skills),
            "origins_beating_naive": beating,
            "share_beating_naive_pct": None if share is None else round(share, 4),
            "mean_skill_ratio": None if mean_skill is None else round(mean_skill, 6),
            "median_skill_ratio": None if median_skill is None else round(median_skill, 6),
            "mean_model_rmse": round(float(np.mean(model_rmses)), 6),
            "mean_naive_rmse": round(float(np.mean(naive_rmses)), 6),
        },
        "verdict": verdict,
        "assumptions": [
            f"Model: {spec['label']} with params {merged}; fit window is always "
            f"the {train_min}+ points strictly before each hold-out.",
            f"Each of the {n_origins} origins scores {holdout} unseen point(s), "
            f"advancing {step} point(s) at a time - a chronological, "
            "expanding-window evaluation. No origin ever sees its own hold-out, "
            "and no random split of time series is used.",
            "The comparison baseline is the naive 'last value' forecast at each "
            "origin. Beating it consistently on one series is still not proof of "
            "a tradeable edge.",
            "Prices are UNADJUSTED for bonus/rights issues.",
            "No transaction costs are modelled (this is price forecasting, not "
            "a strategy backtest).",
            "This is a statistical evaluation of past data, not a forecast, a "
            "recommendation, or investment advice.",
        ],
        "warnings": warnings,
    }


def naive_drift_check(values: np.ndarray | pd.Series) -> dict[str, Any]:
    """How close is this series to a random walk? Runs a rough unit-root check.

    ADF-style tests need the `statsmodels` dependency, so this reports two
    simpler, fully transparent diagnostics instead of pretending to a formal
    test: the lag-1 autocorrelation of *changes*, and the variance ratio of
    1-step vs 5-step changes. A random walk has autocorrelation near 0 and a
    variance ratio near 1.
    """
    series = np.asarray(values.to_numpy() if isinstance(values, pd.Series) else values, dtype=float)
    series = series[np.isfinite(series)]
    if len(series) < 12:
        return {"available": False, "reason": "need at least 12 finite points"}
    change = np.diff(series)
    if np.std(change[:-1]) == 0 or np.std(change[1:]) == 0:
        ac1 = None
    else:
        ac1 = float(np.corrcoef(change[:-1], change[1:])[0, 1])
    var1 = float(np.var(change))
    five = series[5:] - series[:-5]
    var5 = float(np.var(five))
    vr = None if var1 == 0 else var5 / (5 * var1)
    return {
        "available": True,
        "lag1_change_autocorr": None if ac1 is None or math.isnan(ac1) else round(ac1, 4),
        "variance_ratio_5": None if vr is None else round(vr, 4),
        "interpretation": (
            "A random walk shows change-autocorrelation near 0 and a 5-step "
            "variance ratio near 1. Deviations here are descriptive statistics, "
            "not a formal unit-root test."
        ),
    }
