"""Portfolio risk analytics (Phase 2, feature 6).

Computes deterministic risk metrics from the *stored* price history, reusing
the portfolio module's position derivation (the ledger stays the single source
of truth - no second position store is introduced).

Method
------
The current positions are held fixed in share terms and marked against stored
closes, producing a historical value series ("what the current portfolio would
have been worth"). Everything is causal: each date's value uses only closes
stored for that date. From the series:

* annualised volatility (daily std × √250);
* maximum drawdown (peak-to-trough) and current drawdown from the peak;
* historical VaR / CVaR at a stated confidence (the empirical tail of daily
  returns - no distribution is fitted);
* annualised Sharpe with a **0% risk-free rate**, stated wherever it appears.

Limits are explicit, configurable thresholds; a breach is always reported
against its threshold with the measured value. Missing prices never become
fabricated ones: symbols without usable history are excluded from the series
and named in the coverage note. With fewer than ``min_points`` usable series
points the result is ``insufficient_data``, never a number.

Cash balances are not modelled (the portfolio module says so and this module
inherits the position); every figure is a share-positions-only figure.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
import pandas as pd

from megatool.portfolio import derive_positions, value_portfolio

MIN_POINTS = 30
TRADING_DAYS = 250


def portfolio_value_series(
    store: Any, db_path=None, *, min_points: int = MIN_POINTS
) -> tuple[pd.Series | None, dict[str, Any]]:
    """Historical value series of the current positions from stored closes.

    Returns ``(series, coverage)``; ``series`` is None when there is nothing
    computable. Coverage names every held symbol and whether it contributed.
    """
    positions = [p for p in derive_positions(db_path) if p.quantity > 0]
    if not positions:
        return None, {"held": 0, "contributing": [], "excluded": [], "reason": "no open positions"}

    frames: dict[str, pd.Series] = {}
    excluded: list[str] = []
    for p in positions:
        try:
            df = store.get_bars(p.symbol)
        except Exception:
            excluded.append(p.symbol)
            continue
        if df is None or df.empty:
            excluded.append(p.symbol)
            continue
        df = df.sort_values("trading_date")
        series = pd.to_numeric(df["close"], errors="coerce")
        series = series[series.notna() & np.isfinite(series) & (series > 0)]
        if series.empty:
            excluded.append(p.symbol)
            continue
        frames[p.symbol] = series.astype(float)

    if not frames:
        return None, {
            "held": len(positions),
            "contributing": [],
            "excluded": excluded,
            "reason": "no symbol with a usable stored close",
        }

    # Align on the common dates: a date where any contributing symbol is
    # missing cannot value the whole portfolio, so it is dropped, not patched.
    closes = pd.DataFrame(frames)
    closes = closes.dropna()
    if len(closes) < min_points:
        return None, {
            "held": len(positions),
            "contributing": sorted(frames),
            "excluded": excluded,
            "points": len(closes),
            "reason": f"only {len(closes)} fully-covered sessions; {min_points} required",
        }
    quantities = {p.symbol: p.quantity for p in positions if p.symbol in frames}
    value = closes.mul(quantities, axis=1).sum(axis=1)
    value.name = "portfolio_value"
    coverage = {
        "held": len(positions),
        "contributing": sorted(frames),
        "excluded": excluded,
        "points": len(value),
        "start": str(value.index[0])[:10],
        "end": str(value.index[-1])[:10],
        "reason": None,
    }
    return value, coverage


def risk_metrics(value: pd.Series) -> dict[str, Any]:
    """Drawdown, volatility, VaR/CVaR and Sharpe from a value series."""
    rets = value.pct_change(fill_method=None).dropna()
    peak = value.cummax()
    drawdown = value / peak - 1.0
    max_dd = float(drawdown.min())
    current_dd = float(drawdown.iloc[-1])
    vol = float(rets.std()) * math.sqrt(TRADING_DAYS) if len(rets) > 1 else None
    var_threshold = float(rets.quantile(1.0 - 0.95)) if len(rets) else None
    cvar = float(rets[rets <= var_threshold].mean()) if var_threshold is not None else None
    sharpe = (
        float(rets.mean() / rets.std() * math.sqrt(TRADING_DAYS))
        if len(rets) > 1 and rets.std() > 0
        else None
    )
    return {
        "sessions": int(len(value)),
        "returns_observed": int(len(rets)),
        "annualized_volatility_pct": None if vol is None else round(vol * 100, 2),
        "max_drawdown_pct": round(max_dd * 100, 2),
        "current_drawdown_pct": round(current_dd * 100, 2),
        "daily_var_95_pct": None if var_threshold is None else round(var_threshold * 100, 2),
        "daily_cvar_95_pct": None if cvar is None else round(cvar * 100, 2),
        "sharpe_rf0": None if sharpe is None else round(sharpe, 3),
    }


def _limit_breaches(
    metrics: dict[str, Any], valuation: dict[str, Any], limits: dict[str, Any]
) -> list[dict[str, Any]]:
    """Each breach names the measured value, the limit, and what it means."""
    breaches: list[dict[str, Any]] = []
    weight = (valuation.get("summary") or {}).get("largest_weight_pct")
    if weight is not None and weight > limits["max_weight_pct"]:
        breaches.append(
            {
                "limit": "max_weight_pct",
                "measured_pct": weight,
                "threshold_pct": limits["max_weight_pct"],
                "meaning": "one symbol dominates the valued portfolio; a single adverse move moves the whole",
            }
        )
    if (
        metrics.get("max_drawdown_pct") is not None
        and metrics["max_drawdown_pct"] < -limits["max_drawdown_pct"]
    ):
        breaches.append(
            {
                "limit": "max_drawdown_pct",
                "measured_pct": metrics["max_drawdown_pct"],
                "threshold_pct": limits["max_drawdown_pct"],
                "meaning": "historical peak-to-trough loss exceeded the tolerated drawdown",
            }
        )
    vol = metrics.get("annualized_volatility_pct")
    if vol is not None and vol > limits["max_vol_pct"]:
        breaches.append(
            {
                "limit": "max_vol_pct",
                "measured_pct": vol,
                "threshold_pct": limits["max_vol_pct"],
                "meaning": "annualised return volatility exceeded the tolerated level",
            }
        )
    return breaches


def portfolio_risk(
    store: Any,
    db_path=None,
    *,
    limits: dict[str, Any] | None = None,
    min_points: int = MIN_POINTS,
) -> dict[str, Any]:
    """Full risk report: metrics, limits, breaches, coverage and limits used."""
    limits_used = {
        "max_weight_pct": 40.0,
        "max_drawdown_pct": 25.0,
        "max_vol_pct": 5.0,
    }
    if limits:
        limits_used.update(limits)

    value, coverage = portfolio_value_series(store, db_path, min_points=min_points)
    valuation = value_portfolio(store, db_path)
    if value is None:
        return {
            "status": "insufficient_data",
            "reason": coverage.get("reason", "no computable value series"),
            "coverage": coverage,
            "limits": limits_used,
            "valuation_summary": valuation["summary"],
            "breaches": [],
            "disclaimer_note": "No metric was computed; nothing was guessed.",
        }

    metrics = risk_metrics(value)
    breaches = _limit_breaches(metrics, valuation, limits_used)
    return {
        "status": "ok",
        "metrics": metrics,
        "limits": limits_used,
        "breaches": breaches,
        "coverage": coverage,
        "valuation_summary": valuation["summary"],
        "assumptions": [
            "Positions are held fixed in share terms over the whole window (no rebalancing, no cash).",
            "Sharpe uses a 0% risk-free rate.",
            "VaR/CVaR are the empirical daily-return tail (historical method); no distribution is fitted.",
            "Only stored closes are used; symbols listed under coverage.excluded did not contribute.",
        ],
    }
