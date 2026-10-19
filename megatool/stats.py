"""Deterministic statistical analysis for research (no undeclared dependencies).

Everything here is pure :mod:`numpy` + :mod:`math` so it runs in the declared
dependency set (scipy is only a transitive dependency of scikit-learn and is not
imported). Every function is deterministic for a given input and documents its
annualisation and edge-case behaviour.

Discipline
----------
* Missing / non-finite inputs are dropped pairwise and the surviving sample size
  is always reported, so a "significant" result on two points cannot be mistaken
  for a real one.
* Undefined statistics (zero variance, empty sample, too few points) return
  ``None`` rather than a fabricated number.
* p-values are two-sided and computed from the exact Student-t distribution via
  the regularised incomplete beta function (no normal shortcut), so small-sample
  results are honest.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

import numpy as np

__all__ = [
    "TRADING_DAYS_PER_YEAR",
    "descriptive",
    "return_statistics",
    "pearson",
    "spearman",
    "ols",
    "rolling_correlation",
    "rolling_beta",
    "volatility_percentile",
    "autocorrelation",
    "variance_ratio",
    "correlation_matrix",
    "student_t_two_sided_p",
]

#: NEPSE trades roughly 240 days a year (Sunday–Thursday weeks, minus holidays).
#: Used only for annualisation; it is a stated convention, not a measured fact.
TRADING_DAYS_PER_YEAR = 240


# --------------------------------------------------------------------- t distribution


def _betacf(a: float, b: float, x: float, *, max_iter: int = 200, eps: float = 3e-12) -> float:
    """Continued-fraction kernel for the regularised incomplete beta."""
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < 1e-300:
        d = 1e-300
    d = 1.0 / d
    h = d
    for m in range(1, max_iter + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < 1e-300:
            d = 1e-300
        c = 1.0 + aa / c
        if abs(c) < 1e-300:
            c = 1e-300
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < 1e-300:
            d = 1e-300
        c = 1.0 + aa / c
        if abs(c) < 1e-300:
            c = 1e-300
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < eps:
            break
    return h


def _betainc(a: float, b: float, x: float) -> float:
    """Regularised incomplete beta I_x(a, b)."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    lbeta = math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
    front = math.exp(lbeta + a * math.log(x) + b * math.log1p(-x))
    if x < (a + 1.0) / (a + b + 2.0):
        return front * _betacf(a, b, x) / a
    return 1.0 - front * _betacf(b, a, 1.0 - x) / b


def student_t_two_sided_p(t: float, df: int) -> float | None:
    """Two-sided p-value for a t statistic with ``df`` degrees of freedom."""
    if df <= 0 or not math.isfinite(t):
        return None
    x = df / (df + t * t)
    return float(_betainc(df / 2.0, 0.5, x))


# --------------------------------------------------------------------- helpers


def _clean_pair(x: Any, y: Any) -> tuple[np.ndarray, np.ndarray]:
    a = np.asarray(x, dtype=float).ravel()
    b = np.asarray(y, dtype=float).ravel()
    n = min(a.size, b.size)
    a, b = a[:n], b[:n]
    ok = np.isfinite(a) & np.isfinite(b)
    return a[ok], b[ok]


def _clean(x: Any) -> np.ndarray:
    a = np.asarray(x, dtype=float).ravel()
    return a[np.isfinite(a)]


def _rankdata(a: np.ndarray) -> np.ndarray:
    """Average ranks (1-based, ties averaged) — the basis of Spearman."""
    order = np.argsort(a, kind="mergesort")
    ranks = np.empty(a.size, dtype=float)
    sorted_a = a[order]
    i = 0
    while i < a.size:
        j = i
        while j + 1 < a.size and sorted_a[j + 1] == sorted_a[i]:
            j += 1
        ranks[order[i : j + 1]] = (i + j) / 2.0 + 1.0
        i = j + 1
    return ranks


# --------------------------------------------------------------------- descriptive


def descriptive(x: Any) -> dict[str, Any]:
    """Descriptive statistics. Keys with undefined values are ``None``."""
    a = _clean(x)
    n = int(a.size)
    out: dict[str, Any] = {"n": n}
    if n == 0:
        return out | {
            k: None
            for k in (
                "mean",
                "median",
                "std",
                "variance",
                "min",
                "max",
                "skew",
                "kurtosis",
                "q25",
                "q75",
            )
        }
    mean = float(a.mean())
    std = float(a.std(ddof=1)) if n > 1 else None
    out |= {
        "mean": mean,
        "median": float(np.median(a)),
        "std": std,
        "variance": (std * std) if std is not None else None,
        "min": float(a.min()),
        "max": float(a.max()),
        "q25": float(np.percentile(a, 25)),
        "q75": float(np.percentile(a, 75)),
    }
    if n > 2 and std and std > 0:
        z = (a - mean) / std
        out["skew"] = float(np.mean(z**3))
        out["kurtosis"] = float(np.mean(z**4) - 3.0)
    else:
        out["skew"] = None
        out["kurtosis"] = None
    return out


# --------------------------------------------------------------------- returns


def _max_drawdown(equity: np.ndarray) -> tuple[float | None, int]:
    """Max drawdown (negative fraction) and its duration in bars."""
    if equity.size < 2:
        return None, 0
    peak = np.maximum.accumulate(equity)
    dd = equity / peak - 1.0
    mdd = float(dd.min())
    # Longest run between a peak and the subsequent recovery to that peak.
    duration = 0
    start = 0
    for i in range(equity.size):
        if equity[i] >= peak[i]:
            duration = max(duration, i - start)
            start = i
    duration = max(duration, equity.size - 1 - start)
    return mdd, int(duration)


def return_statistics(
    prices: Any,
    *,
    periods_per_year: int = TRADING_DAYS_PER_YEAR,
    risk_free_annual: float = 0.0,
) -> dict[str, Any]:
    """Return/risk statistics from a price series (oldest → newest).

    ``periods_per_year`` annualises; the default (240) is the documented NEPSE
    convention. Undefined metrics are ``None`` — never NaN, never invented.
    """
    p = _clean(prices)
    out: dict[str, Any] = {"n": int(p.size), "periods_per_year": periods_per_year}
    if p.size < 2:
        return out | {
            k: None
            for k in (
                "total_return",
                "cagr",
                "annualised_volatility",
                "sharpe",
                "sortino",
                "max_drawdown",
                "max_drawdown_duration",
            )
        }
    if np.any(p <= 0):
        return (
            out
            | {
                k: None
                for k in (
                    "total_return",
                    "cagr",
                    "annualised_volatility",
                    "sharpe",
                    "sortino",
                    "max_drawdown",
                    "max_drawdown_duration",
                )
            }
            | {"note": "non-positive price present; return statistics are undefined"}
        )
    rets = p[1:] / p[:-1] - 1.0
    total = float(p[-1] / p[0] - 1.0)
    years = (p.size - 1) / periods_per_year
    cagr = float((p[-1] / p[0]) ** (1.0 / years) - 1.0) if years > 0 else None
    sd = float(rets.std(ddof=1)) if rets.size > 1 else None
    ann_vol = sd * math.sqrt(periods_per_year) if sd is not None else None
    rf_per = risk_free_annual / periods_per_year
    excess = rets - rf_per
    sharpe = None
    if sd and sd > 0:
        sharpe = float(excess.mean() / sd * math.sqrt(periods_per_year))
    downside = rets[rets < 0]
    sortino = None
    if downside.size > 1:
        dstd = float(downside.std(ddof=1))
        if dstd > 0:
            sortino = float(excess.mean() / dstd * math.sqrt(periods_per_year))
    mdd, ddur = _max_drawdown(p)
    out |= {
        "total_return": total,
        "cagr": cagr,
        "annualised_volatility": ann_vol,
        "sharpe": sharpe,
        "sortino": sortino,
        "max_drawdown": mdd,
        "max_drawdown_duration": ddur,
    }
    if rets.size:
        out["best_period"] = float(rets.max())
        out["worst_period"] = float(rets.min())
        out["mean_period_return"] = float(rets.mean())
        out["skew"] = descriptive(rets).get("skew")
    return out


# --------------------------------------------------------------------- correlation


def pearson(x: Any, y: Any) -> dict[str, Any]:
    """Pearson correlation with a two-sided p-value (Student-t)."""
    a, b = _clean_pair(x, y)
    n = int(a.size)
    if n < 3 or a.std() == 0 or b.std() == 0:
        return {
            "r": None,
            "n": n,
            "p": None,
            "method": "pearson",
            "reason": "fewer than 3 paired points or a constant series",
        }
    r = float(np.corrcoef(a, b)[0, 1])
    df = n - 2
    if abs(r) >= 1.0:
        # Perfect monotone (linear) association: t is infinite, p -> 0.
        return {"r": r, "n": n, "df": df, "t": math.inf, "p": 0.0, "method": "pearson"}
    t = r * math.sqrt(df / (1.0 - r * r))
    return {
        "r": r,
        "n": n,
        "df": df,
        "t": t,
        "p": student_t_two_sided_p(t, df),
        "method": "pearson",
    }


def spearman(x: Any, y: Any) -> dict[str, Any]:
    """Spearman rank correlation with a two-sided p-value."""
    a, b = _clean_pair(x, y)
    n = int(a.size)
    if n < 3:
        return {
            "rho": None,
            "n": n,
            "p": None,
            "method": "spearman",
            "reason": "fewer than 3 paired points",
        }
    ra, rb = _rankdata(a), _rankdata(b)
    out = pearson(ra, rb)
    return {
        "rho": out["r"],
        "n": n,
        "df": out.get("df"),
        "t": out.get("t"),
        "p": out["p"],
        "method": "spearman",
    }


def rolling_correlation(x: Any, y: Any, window: int) -> list[float | None]:
    """Rolling Pearson correlation; ``None`` where the window is degenerate."""
    a, b = _clean_pair(x, y)
    if window < 3:
        raise ValueError("window must be >= 3")
    out: list[float | None] = [None] * a.size
    for i in range(window - 1, a.size):
        wa, wb = a[i - window + 1 : i + 1], b[i - window + 1 : i + 1]
        if wa.std() == 0 or wb.std() == 0:
            continue
        out[i] = float(np.corrcoef(wa, wb)[0, 1])
    return out


def rolling_beta(x: Any, y: Any, window: int) -> list[float | None]:
    """Rolling OLS beta of ``x`` on ``y`` over a trailing window.

    Beta = Cov(x, y) / Var(y), computed on the cleaned, aligned pair. Returns
    ``None`` wherever the window is degenerate (zero benchmark variance, too few
    points, or a non-finite value). Uses returns (or any aligned series) — the
    caller decides; the conventional use is on return series, not price levels.
    """
    a, b = _clean_pair(x, y)
    if window < 3:
        raise ValueError("window must be >= 3")
    out: list[float | None] = [None] * a.size
    for i in range(window - 1, a.size):
        wa, wb = a[i - window + 1 : i + 1], b[i - window + 1 : i + 1]
        if wb.std() == 0:
            continue
        # OLS slope of wa on wb (with intercept).
        wbm = wb - wb.mean()
        wam = wa - wa.mean()
        denom = float(np.dot(wbm, wbm))
        if denom == 0:
            continue
        out[i] = float(np.dot(wbm, wam) / denom)
    return out


def volatility_percentile(series: Any, lookback: int = 250) -> dict[str, Any]:
    """Percentile rank of the last value within its own trailing history.

    Reports where the most recent observation sits relative to the previous
    ``lookback`` observations of the *same* series (a time-series percentile,
    not a cross-sectional one). Returns ``None`` when there are too few
    observations. Missing/non-finite values are dropped.
    """
    a = _clean(series)
    if a.size < 2:
        return {"percentile": None, "n": int(a.size), "lookback": lookback,
                "reason": "too few observations"}
    window = a[-lookback:] if a.size >= lookback else a
    last = float(window[-1])
    # percentile rank: fraction of window values <= last, as a 0-100 score.
    rank = float(np.mean(window <= last) * 100.0)
    return {
        "percentile": round(rank, 2),
        "n": int(window.size),
        "lookback": int(window.size),
        "last_value": round(last, 6),
        "min": round(float(window.min()), 6),
        "max": round(float(window.max()), 6),
        "reason": None,
    }


def autocorrelation(x: Any, lag: int = 1) -> dict[str, Any]:
    """Lag-``lag`` autocorrelation of a series."""
    a = _clean(x)
    if lag < 1:
        raise ValueError("lag must be >= 1")
    if a.size <= lag + 1:
        return {
            "r": None,
            "n": int(a.size),
            "lag": lag,
            "p": None,
            "reason": "series too short for this lag",
        }
    out = pearson(a[:-lag], a[lag:])
    return {"r": out["r"], "n": out["n"], "lag": lag, "t": out.get("t"), "p": out["p"]}


def variance_ratio(x: Any, q: int = 5) -> dict[str, Any]:
    """Lo–MacKinlay variance ratio VR(q) with a heteroskedasticity-robust z.

    VR(q) = var(q-period return) / (q * var(1-period return)). Under a random
    walk VR ≈ 1; > 1 indicates positive serial correlation, < 1 mean reversion.
    """
    a = _clean(x)
    if q < 2:
        raise ValueError("q must be >= 2")
    if a.size <= q + 1:
        return {
            "vr": None,
            "q": q,
            "n": int(a.size),
            "z": None,
            "p": None,
            "reason": "series too short for this q",
        }
    if np.any(a <= 0):
        return {
            "vr": None,
            "q": q,
            "n": int(a.size),
            "z": None,
            "p": None,
            "reason": "non-positive values present",
        }
    r = np.diff(np.log(a))
    n = r.size
    mu = r.mean()
    var1 = float(np.sum((r - mu) ** 2) / (n - 1))
    rq = np.log(a[q:] / a[:-q])
    m = q * (n - q + 1) * (1.0 - q / n)
    varq = float(np.sum((rq - q * mu) ** 2) / m) if m > 0 else None
    if varq is None or var1 == 0:
        return {"vr": None, "q": q, "n": n, "z": None, "p": None, "reason": "degenerate variance"}
    vr = varq / var1
    # Homoskedastic z (Lo–MacKinlay); documented simplification.
    denom = math.sqrt(2 * (2 * q - 1) * (q - 1) / (3 * q * n))
    z = (vr - 1.0) / denom if denom > 0 else None
    return {
        "vr": float(vr),
        "q": q,
        "n": n,
        "z": z,
        "mu": float(mu),
        "var1": var1,
        "varq": varq,
        "p": None if z is None else float(math.erfc(abs(z) / math.sqrt(2.0))),
    }


def correlation_matrix(
    series: Mapping[str, Any],
    *,
    method: str = "pearson",
) -> dict[str, Any]:
    """Pairwise correlation matrix over named aligned series.

    Series are aligned on the shortest length, then pairwise-complete (a symbol
    pair uses only the points where both are finite). Every cell reports its own
    ``n`` so a thin pair is visible.
    """
    if method not in ("pearson", "spearman"):
        raise ValueError("method must be 'pearson' or 'spearman'")
    names = list(series)
    arrays = {k: np.asarray(series[k], dtype=float).ravel() for k in names}
    n = min((a.size for a in arrays.values()), default=0)
    matrix: list[list[float | None]] = []
    counts: list[list[int]] = []
    fn = pearson if method == "pearson" else spearman
    for i, a in enumerate(names):
        row: list[float | None] = []
        crow: list[int] = []
        for j, b in enumerate(names):
            if i == j:
                row.append(1.0)
                crow.append(n)
                continue
            res = fn(arrays[a][:n], arrays[b][:n])
            row.append(res.get("r") if method == "pearson" else res.get("rho"))
            crow.append(int(res.get("n") or 0))
        matrix.append(row)
        counts.append(crow)
    return {"symbols": names, "method": method, "n": n, "matrix": matrix, "pair_n": counts}


# --------------------------------------------------------------------- regression


def ols(x: Any, y: Any) -> dict[str, Any]:
    """Ordinary least squares of ``y`` on ``x`` with standard errors.

    Returns slope, intercept, r², the slope's standard error and t statistic, a
    two-sided p-value, and the sample size. Undefined for n < 3 or a constant x.
    """
    a, b = _clean_pair(x, y)
    n = int(a.size)
    if n < 3 or a.std() == 0:
        return {
            "slope": None,
            "intercept": None,
            "r2": None,
            "n": n,
            "slope_stderr": None,
            "t": None,
            "p": None,
            "reason": "fewer than 3 points or a constant regressor",
        }
    xm, ym = a.mean(), b.mean()
    sxx = float(np.sum((a - xm) ** 2))
    sxy = float(np.sum((a - xm) * (b - ym)))
    slope = sxy / sxx
    intercept = float(ym - slope * xm)
    pred = intercept + slope * a
    resid = b - pred
    ss_res = float(np.sum(resid**2))
    ss_tot = float(np.sum((b - ym) ** 2))
    r2 = None if ss_tot == 0 else float(1.0 - ss_res / ss_tot)
    df = n - 2
    if df > 0 and sxx > 0:
        s2 = ss_res / df
        stderr = math.sqrt(max(0.0, s2 / sxx))
        t = slope / stderr if stderr > 0 else None
        p = student_t_two_sided_p(t, df) if t is not None else None
    else:
        stderr, t, p = None, None, None
    return {
        "slope": float(slope),
        "intercept": intercept,
        "r2": r2,
        "n": n,
        "df": df,
        "slope_stderr": stderr,
        "t": t,
        "p": p,
    }
