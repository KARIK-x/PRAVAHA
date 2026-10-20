"""Next-session range forecasting for NEPSE, with honest out-of-sample scoring.

The question this module answers is deliberately narrow:

    Given only information available at the prior close, how far is the *next*
    stored session likely to move (high - low), and how wide should a stop be?

It does **not** predict direction or price. Realised volatility clusters, so a
range forecast is far more defensible than a return forecast — but the module
still refuses to claim skill it has not measured. Every model is scored against
the naive baseline ("tomorrow's range equals today's range") on a strictly
chronological, expanding-origin walk-forward. A model that does not beat that
baseline is reported as such.

Models
------
``naive``
    Previous session's high-low range.
``ewma_tr``
    Exponentially weighted true range (lambda 0.94), which reacts faster to a
    volatility regime change than a simple average.
``har``
    A HAR-style regression of log range on the previous 1, 5 and 22 session
    log ranges (Corsi, 2009), fitted by ordinary least squares on data that
    precedes the forecast. Coefficients are re-fitted at every origin.
``blend``
    The average of ``ewma_tr`` and ``har``. Included because averaging two
    noisy volatility forecasts is a standard, hard-to-beat benchmark.

No performance figure from any other market is copied in. All numbers returned
here are computed from the bars passed in.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np

__all__ = [
    "VolatilityError",
    "bar_arrays",
    "forecast_range",
    "evaluate_models",
    "position_sizing",
    "volatility_report",
]

MIN_BARS = 60
TRADING_DAYS = 252


class VolatilityError(ValueError):
    """Not enough usable bars, or an invalid sizing input."""


@dataclass
class _Bars:
    dates: list[str]
    open: np.ndarray
    high: np.ndarray
    low: np.ndarray
    close: np.ndarray
    volume: np.ndarray | None

    def __len__(self) -> int:
        return int(self.close.size)


def bar_arrays(df: Any) -> _Bars:
    """Extract finite OHLC arrays, dropping bars that cannot form a candle."""
    if df is None or getattr(df, "empty", True):
        raise VolatilityError("no stored bars")
    cols = {str(c).lower(): c for c in df.columns}
    need = ("trading_date", "open", "high", "low", "close")
    missing = [c for c in need if c not in cols]
    if missing:
        raise VolatilityError(f"stored bars are missing column(s): {', '.join(missing)}")

    o = np.asarray(df[cols["open"]], dtype=float)
    h = np.asarray(df[cols["high"]], dtype=float)
    lo = np.asarray(df[cols["low"]], dtype=float)
    c = np.asarray(df[cols["close"]], dtype=float)
    dates = [str(d)[:10] for d in df[cols["trading_date"]]]
    v = np.asarray(df[cols["volume"]], dtype=float) if "volume" in cols else None

    ok = (
        np.isfinite(o) & np.isfinite(h) & np.isfinite(lo) & np.isfinite(c)
        & (c > 0) & (h > 0) & (lo > 0) & (h >= lo)
        & (h >= np.maximum(o, c)) & (lo <= np.minimum(o, c))
    )
    if int(ok.sum()) < MIN_BARS:
        raise VolatilityError(
            f"only {int(ok.sum())} internally consistent bars; {MIN_BARS} are required"
        )
    if v is not None:
        v = np.where(np.isfinite(v), v, 0.0)
        v = v[ok]
    return _Bars([d for d, keep in zip(dates, ok, strict=False) if keep],
                 o[ok], h[ok], lo[ok], c[ok], v)


def _true_range(b: _Bars) -> np.ndarray:
    prev_close = np.concatenate(([b.close[0]], b.close[:-1]))
    return np.maximum.reduce([
        b.high - b.low,
        np.abs(b.high - prev_close),
        np.abs(b.low - prev_close),
    ])


def _ewma(values: np.ndarray, lam: float = 0.94) -> float:
    """EWMA variance-style smoothing, returned as a level (not squared)."""
    if values.size == 0:
        return float("nan")
    level = float(values[0])
    for v in values[1:]:
        level = lam * level + (1.0 - lam) * float(v)
    return level


def _log_ranges(rng: np.ndarray) -> np.ndarray:
    return np.log(np.maximum(rng, 1e-9))


def _har_forecast(log_rng: np.ndarray) -> float:
    """One-step HAR forecast from the most recent observations.

    The regression is fitted on the observations *before* the forecast origin:
    ``y[t] = b0 + b1*x[t-1] + b2*mean(x[t-5:t-1]) + b3*mean(x[t-22:t-1])``.
    """
    n = log_rng.size
    if n < 30:
        return float(math.exp(float(np.mean(log_rng[-5:]))))
    rows, target = [], []
    for t in range(22, n):
        rows.append([1.0, log_rng[t - 1],
                     float(np.mean(log_rng[t - 5:t])),
                     float(np.mean(log_rng[t - 22:t]))])
        target.append(log_rng[t])
    x = np.asarray(rows, dtype=float)
    y = np.asarray(target, dtype=float)
    # Ridge-stabilised OLS: the intercept column is not penalised.
    penalty = np.eye(x.shape[1]) * 1e-6
    penalty[0, 0] = 0.0
    try:
        beta = np.linalg.solve(x.T @ x + penalty, x.T @ y)
    except np.linalg.LinAlgError:
        beta = np.array([float(np.mean(y)), 1.0, 0.0, 0.0])
    last = np.array([1.0, log_rng[-1],
                     float(np.mean(log_rng[-5:])),
                     float(np.mean(log_rng[-22:]))])
    return float(math.exp(float(last @ beta)))


def _model_forecasts(rng: np.ndarray, log_rng: np.ndarray) -> dict[str, float]:
    """One-step-ahead forecasts using the values strictly before the target."""
    naive = float(rng[-1])
    ewma = _ewma(rng, 0.94)
    har = _har_forecast(log_rng)
    return {
        "naive": naive,
        "ewma_tr": ewma,
        "har": har,
        "blend": (ewma + har) / 2.0,
    }


def _metrics(actual: np.ndarray, pred: np.ndarray) -> dict[str, Any]:
    err = pred - actual
    abs_err = np.abs(err)
    pct = np.abs(err) / np.maximum(actual, 1e-9) * 100.0
    return {
        "n": int(actual.size),
        "mae": round(float(np.mean(abs_err)), 4),
        "rmse": round(float(math.sqrt(float(np.mean(err ** 2)))), 4),
        "median_ape_percent": round(float(np.median(pct)), 2),
        "mean_ape_percent": round(float(np.mean(pct)), 2),
    }


def evaluate_models(b: _Bars, min_train: int = 40) -> dict[str, Any]:
    """Chronological walk-forward evaluation, no leakage.

    For each target session ``t`` the model sees bars ``0..t-1`` only. Each
    model's 80% interval is calibrated from *its own* previous out-of-sample
    errors, so the coverage number is genuinely out-of-sample.
    """
    rng = _true_range(b)
    log_rng = _log_ranges(rng)
    names = ("naive", "ewma_tr", "har", "blend")
    actual: list[float] = []
    preds: dict[str, list[float]] = {k: [] for k in names}
    bands: dict[str, tuple[list[float], list[float]]] = {k: ([], []) for k in names}
    dates: list[str] = []

    start = max(min_train, 24)
    for t in range(start, len(b)):
        f = _model_forecasts(rng[:t], log_rng[:t])
        truth = float(rng[t])
        if not math.isfinite(truth) or truth <= 0:
            continue
        actual.append(truth)
        dates.append(b.dates[t])
        a_prev = np.asarray(actual[:-1], dtype=float)
        for k in names:
            preds[k].append(float(f[k]))
            lo_band, hi_band = bands[k]
            if a_prev.size >= 20:
                ratios = np.sort(np.asarray(preds[k][:-1], dtype=float)
                                 / np.maximum(a_prev, 1e-9))
                lo_f = float(np.quantile(ratios, 0.10))
                hi_f = float(np.quantile(ratios, 0.90))
                lo_band.append(max(0.0, float(f[k]) * lo_f))
                hi_band.append(float(f[k]) * hi_f)
            else:
                lo_band.append(float("nan"))
                hi_band.append(float("nan"))

    if not actual:
        raise VolatilityError("not enough bars to evaluate a one-step forecast")

    a = np.asarray(actual, dtype=float)
    results = {k: _metrics(a, np.asarray(preds[k], dtype=float)) for k in names}
    base_mae = results["naive"]["mae"] or float("nan")
    for k in names:
        results[k]["improvement_vs_naive_percent"] = (
            round((1.0 - results[k]["mae"] / base_mae) * 100.0, 2)
            if base_mae and math.isfinite(base_mae) else None
        )
        lo = np.asarray(bands[k][0], dtype=float)
        hi = np.asarray(bands[k][1], dtype=float)
        usable = np.isfinite(lo) & np.isfinite(hi)
        covered = usable & (a >= lo) & (a <= hi)
        results[k]["interval_coverage_percent"] = (
            round(float(covered.sum()) / int(usable.sum()) * 100.0, 2)
            if int(usable.sum()) else None
        )
        results[k]["interval_observations"] = int(usable.sum())

    best = min(names, key=lambda k: results[k]["mae"])
    # Final empirical factors from the complete out-of-sample error history.
    for k in names:
        ratios = np.asarray(preds[k], dtype=float) / np.maximum(a, 1e-9)
        if ratios.size >= 20:
            results[k]["interval_factors"] = [
                round(float(np.quantile(ratios, 0.10)), 4),
                round(float(np.quantile(ratios, 0.90)), 4),
            ]
        else:
            results[k]["interval_factors"] = [0.5, 1.5]
    return {
        "models": results,
        "best_model": best,
        "naive_baseline": "previous session's high-low range",
        "evaluation": {
            "method": "expanding-origin, one-step-ahead, chronological",
            "leak_free": True,
            "first_target": dates[0],
            "last_target": dates[-1],
            "observations": int(a.size),
            "interval": "80% empirical band from each model's prior errors",
            "expected_coverage_percent": 80.0,
        },
        "note": (
            "Out-of-sample errors on stored NEPSE bars. A model that does not "
            "beat the naive baseline is reported as having no measured skill."
        ),
    }


def _last_forecast(b: _Bars, ev: dict[str, Any]) -> dict[str, Any]:
    rng = _true_range(b)
    log_rng = _log_ranges(rng)
    f = _model_forecasts(rng, log_rng)
    best = ev["best_model"]
    point = float(f[best])

    # Use this model's own out-of-sample multiplicative error quantiles, so
    # the band matches the coverage that was actually measured.
    lo_f, hi_f = ev["models"][best].get("interval_factors", [0.5, 1.5])
    lo_point = max(0.0, point * float(lo_f))
    hi_point = point * float(hi_f)
    normal = float(np.median(rng[-60:])) if rng.size >= 20 else float(np.median(rng))
    last_close = float(b.close[-1])
    return {
        "as_of_session": b.dates[-1],
        "next_session": "the next session stored after this report is generated",
        "point_range": round(point, 2),
        "point_range_percent_of_price": round(point / last_close * 100.0, 3),
        "band_80": [round(lo_point, 2), round(hi_point, 2)],
        "band_80_percent_of_price": [
            round(lo_point / last_close * 100.0, 3),
            round(hi_point / last_close * 100.0, 3),
        ],
        "band_80_method": "empirical 10th-90th percentile of this model's prior out-of-sample errors",
        "normal_range_60_session_median": round(normal, 2),
        "ratio_to_normal": round(point / normal, 3) if normal > 0 else None,
        "model": best,
        "model_mae": ev["models"][best]["mae"],
        "measured_interval_coverage_percent": ev["models"][best]["interval_coverage_percent"],
        "last_close": round(last_close, 2),
        "last_range": round(float(rng[-1]), 2),
        "history_bars": len(b),
        "history_first": b.dates[0],
        "price_kind": "stored end-of-day bars, not a live quote",
    }


def forecast_range(df: Any, *, min_train: int = 40) -> dict[str, Any]:
    """Point forecast + 80% band for the next session, with model evidence."""
    b = bar_arrays(df)
    ev = evaluate_models(b, min_train=min_train)
    fc = _last_forecast(b, ev)
    return {
        "available": True,
        "symbol": None,
        "forecast": fc,
        "evaluation": ev,
        "caveats": [
            "This forecasts the SIZE of the next session's range, not its direction.",
            "Every input is a stored end-of-day bar available at the prior close.",
            "The band is an empirical error band, not a guarantee.",
            "No order is placed, and nothing here is investment advice.",
        ],
    }


def position_sizing(
    price: float,
    risk_budget: float,
    expected_range: float,
    *,
    stop_multiple: float = 1.0,
    capital: float | None = None,
    max_position_percent: float = 100.0,
) -> dict[str, Any]:
    """Risk-budget sizing: constant rupee risk, stop width scaled to volatility.

    ``shares = floor(risk_budget / (stop_multiple * expected_range))`` with no
    leverage. If ``capital`` is supplied the position value is capped at
    ``max_position_percent`` of it. Returns the rejected notional and why, so a
    zero-share result is explained rather than silently shown.
    """
    for name, value in (("price", price), ("risk_budget", risk_budget),
                        ("expected_range", expected_range),
                        ("stop_multiple", stop_multiple)):
        if not math.isfinite(float(value)) or float(value) <= 0:
            raise VolatilityError(f"{name} must be a positive, finite number")
    stop_distance = float(stop_multiple) * float(expected_range)
    raw_shares = int(math.floor(float(risk_budget) / stop_distance))
    cap_note = None
    if capital is not None:
        if not math.isfinite(float(capital)) or float(capital) <= 0:
            raise VolatilityError("capital must be a positive, finite number")
        max_value = float(capital) * max(0.0, min(100.0, float(max_position_percent))) / 100.0
        max_shares = int(math.floor(max_value / float(price)))
        if max_shares < raw_shares:
            raw_shares = max(0, max_shares)
            cap_note = "capped by capital / max position percent"
    shares = max(0, raw_shares)
    notional = shares * float(price)
    return {
        "price": round(float(price), 2),
        "risk_budget": round(float(risk_budget), 2),
        "expected_range": round(float(expected_range), 2),
        "stop_multiple": round(float(stop_multiple), 3),
        "stop_distance": round(stop_distance, 2),
        "shares": shares,
        "notional": round(notional, 2),
        "max_loss_at_stop": round(shares * stop_distance, 2),
        "risk_used_percent_of_budget": (
            round(shares * stop_distance / float(risk_budget) * 100.0, 2)
            if float(risk_budget) > 0 else None
        ),
        "cap_note": cap_note,
        "board_lot_note": (
            "NEPSE trades in board lots for many symbols; round DOWN to the "
            "board lot before entering an order."
        ),
    }


def sizing_table(price: float, risk_budget: float, expected_range: float,
                 *, capital: float | None = None) -> list[dict[str, Any]]:
    """Sizing at 0.5x, 1x, 1.5x and 2x the expected range."""
    return [
        {"label": f"{m:g}x expected range",
         **position_sizing(price, risk_budget, expected_range,
                           stop_multiple=m, capital=capital)}
        for m in (0.5, 1.0, 1.5, 2.0)
    ]


def volatility_report(df: Any, symbol: str, *, risk_budget: float | None = None,
                      capital: float | None = None) -> dict[str, Any]:
    """The complete payload used by the API and the research report."""
    out = forecast_range(df)
    out["symbol"] = symbol.upper()
    fc = out["forecast"]
    if risk_budget is not None:
        budget = float(risk_budget)
        out["position_sizing"] = {
            "inputs": {
                "price": fc["last_close"],
                "risk_budget": round(budget, 2),
                "expected_range": fc["point_range"],
                "capital": round(float(capital), 2) if capital is not None else None,
            },
            "table": sizing_table(fc["last_close"], budget, fc["point_range"],
                                  capital=capital),
            "note": (
                "Sizing only. No order is created, queued or placed. Wider "
                "stops on high-volatility days keep rupee risk constant by "
                "reducing the number of shares."
            ),
        }
    else:
        out["position_sizing"] = {
            "available": False,
            "reason": "provide risk_budget (NPR) to compute share sizing",
        }
    return out
