"""Multi-timeframe relative-strength rows for one aligned stock/index series.

ONE calculation, applied at several lookbacks, so the UI never re-derives it
differently from the single-window view. For each lookback ``L``:

* the aligned series is cut to its most recent ``L + 1`` dates (a date must be
  present in **both** the stock and the benchmark series — the same inner-join
  rule as the single-window view, never forward-filled);
* ``stock_return_pct  = (stock[-1] / stock[-1-L] − 1) × 100``
* ``benchmark_return_pct`` is defined identically on the benchmark series;
* ``excess_return_pct = stock_return_pct − benchmark_return_pct`` — a
  *difference of percentage returns*, explicitly not labelled alpha and never
  annualised;
* a lookback longer than the aligned history is reported ``available: false``
  with the exact reason rather than shortened silently.

Pure arithmetic on an already-aligned frame: no loading, no caching, no
substitution — the caller owns 100% of where the data came from.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any

import pandas as pd

__all__ = ["MAX_LOOKBACKS", "timeframe_rows", "parse_lookbacks"]

#: Hard ceiling on how many lookbacks one request may ask for (keeps the
#: response bounded and the UI table readable).
MAX_LOOKBACKS = 6

#: Per-lookback row keys the endpoint exposes.
_ROW_KEYS = (
    "lookback",
    "available",
    "unavailable_reason",
    "stock_return_pct",
    "benchmark_return_pct",
    "excess_return_pct",
    "base_date",
    "last_date",
    "window_bars_used",
)


def parse_lookbacks(raw: str | None) -> list[int] | None:
    """Parse a comma-separated lookback list into validated unique ints.

    ``None``/empty → ``None`` (caller falls back to the single-window view).
    Raises ``ValueError`` with a precise message on anything unusable; bounds
    match the endpoint's single ``window`` parameter (2..2000).
    """
    if raw is None or not raw.strip():
        return None
    values: list[int] = []
    for part in raw.split(","):
        token = part.strip()
        if not token:
            raise ValueError("empty lookback entry in the list")
        try:
            value = int(token)
        except ValueError:
            raise ValueError(f"lookback {token!r} is not an integer") from None
        if not 2 <= value <= 2000:
            raise ValueError(f"lookback {value} is out of bounds 2..2000")
        values.append(value)
    if len(values) > MAX_LOOKBACKS:
        raise ValueError(f"at most {MAX_LOOKBACKS} lookbacks per request, got {len(values)}")
    # Deduplicate but preserve order: a repeated lookback says nothing new and
    # would otherwise make the UI table ambiguous.
    return list(dict.fromkeys(values))


def _window_return(series: pd.Series, lookback: int) -> float | None:
    """Close-to-close percentage return over exactly ``lookback`` observations."""
    if len(series) < lookback + 1:
        return None
    start = float(series.iloc[-1 - lookback])
    end = float(series.iloc[-1])
    if not math.isfinite(start) or start <= 0.0:
        return None
    if not math.isfinite(end) or end <= 0.0:
        return None
    return (end / start - 1.0) * 100.0


def timeframe_rows(merged: pd.DataFrame, lookbacks: Sequence[int]) -> list[dict[str, Any]]:
    """Compute per-lookback rows from an aligned, ascending stock/bench frame.

    ``merged`` must carry ``trading_date`` (datetime-like), ``stock`` and
    ``bench`` close columns sorted by date — exactly what the endpoint's
    inner join produces. Alignment is the caller's responsibility; this
    function only measures.
    """
    rows: list[dict[str, Any]] = []
    if merged is None or merged.empty:
        for lookback in lookbacks:
            rows.append(
                {
                    "lookback": int(lookback),
                    "available": False,
                    "unavailable_reason": "no dates are present in both series",
                    "stock_return_pct": None,
                    "benchmark_return_pct": None,
                    "excess_return_pct": None,
                    "base_date": None,
                    "last_date": None,
                    "window_bars_used": 0,
                }
            )
        return rows
    for lookback in lookbacks:
        lookback = int(lookback)
        used = merged.tail(max(lookback + 1, 2))
        n = int(len(used))
        stock_ret = _window_return(used["stock"], lookback)
        bench_ret = _window_return(used["bench"], lookback)
        available = stock_ret is not None and bench_ret is not None and n >= lookback + 1
        if available:
            reason = ""
        elif n < lookback + 1:
            reason = (
                f"only {n} aligned dates are available; a {lookback}-bar "
                "comparison needs at least "
                f"{lookback + 1} dates present in both series"
            )
        else:
            reason = (
                "a return could not be computed from the aligned bars "
                "(non-finite or nonpositive close)"
            )
        stock_ret = None if stock_ret is None or not math.isfinite(stock_ret) else stock_ret
        bench_ret = None if bench_ret is None or not math.isfinite(bench_ret) else bench_ret
        rows.append(
            {
                "lookback": lookback,
                "available": available,
                "unavailable_reason": reason,
                "stock_return_pct": None if stock_ret is None else round(stock_ret, 4),
                "benchmark_return_pct": None if bench_ret is None else round(bench_ret, 4),
                "excess_return_pct": (
                    None
                    if stock_ret is None or bench_ret is None
                    else round(stock_ret - bench_ret, 4)
                ),
                "base_date": str(used["trading_date"].iloc[0].date()),
                "last_date": str(used["trading_date"].iloc[-1].date()),
                "window_bars_used": n,
            }
        )
    return rows
