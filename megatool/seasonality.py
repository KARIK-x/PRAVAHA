"""Seasonality statistics from stored daily closes.

WHAT THIS IS (AND IS NOT)
-------------------------
Descriptive history, not a forecast. Every number below is computed from the
stored bars of one symbol (or index) and quotes its own sample size. Where a
statistic needs a reference this module does not have (a holiday list, a
benchmark), it reports the gap instead of estimating around it.

DEFINITIONS
-----------
* **Month return** — last stored close of the calendar month divided by the
  last stored close of the *previous stored* month, minus one, in percent.
  The first month of the series has no predecessor and produces no return.
* **Partial month** — a calendar month with fewer than ``min_month_bars``
  stored bars (default 10) is flagged. A month is excluded from the aggregate
  tables when it, or its predecessor, is partial; the exclusion count is
  reported so a thin month cannot silently masquerade as evidence.
* **Weekday return** — close / previous stored close - 1, grouped by the
  calendar weekday of the date. Only weekdays present in the data appear;
  NEPSE's Sunday-Thursday week means Friday/Saturday rarely exist and are
  never synthesised.
* **Holiday effect** — requires an actual holiday list. The bundled
  ``trading_calendar.json`` currently has NO holidays, so this section returns
  ``available: False`` with the reason; nothing is approximated.

No look-ahead: every statistic uses the stored history as it stands; a return
attributed to a day uses only that day's close and the previous stored close.
"""

from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from megatool.market_store import MarketStore

#: Bars a calendar month needs to count as complete for aggregate statistics.
DEFAULT_MIN_MONTH_BARS = 10

#: Bundled calendar path (project convention: the MI package owns the file).
DEFAULT_CALENDAR_PATH = (
    Path(__file__).resolve().parent / "market_intelligence" / "config" / "trading_calendar.json"
)

_WEEKDAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def _f(x: Any) -> float | None:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return None if np.isnan(v) else v


def _iso(value: Any) -> str:
    if isinstance(value, (datetime, date, pd.Timestamp)):
        return pd.Timestamp(value).date().isoformat()
    return str(value)


def load_close_series(store: MarketStore, symbol: str) -> dict[str, Any]:
    """Resolve a symbol to its stored close series.

    Indices are matched case-insensitively against stored index names first,
    because 'NEPSE' is an index, not a security. Returns
    {kind, dates, closes} with ascending unique dates and non-null closes.
    Raises KeyError when nothing is stored under that name.
    """
    sym = (symbol or "").strip().upper()
    if not sym:
        raise KeyError("empty symbol")
    for name in store.index_names():
        if str(name).strip().upper() == sym:
            df = store.index_closes(name)
            if df.empty:
                raise KeyError(f"index '{name}' has no stored closes")
            df = df.dropna(subset=["close"])
            return {
                "kind": "index",
                "dates": [pd.Timestamp(d).date() for d in df["trading_date"]],
                "closes": [float(c) for c in df["close"]],
            }
    df = store.get_bars(sym)
    if df.empty:
        raise KeyError(f"no stored history for '{sym}'")
    df = df.dropna(subset=["close"])
    if df.empty:
        raise KeyError(f"'{sym}' has no stored closes")
    return {
        "kind": "security",
        "dates": [pd.Timestamp(d).date() for d in df["trading_date"]],
        "closes": [float(c) for c in df["close"]],
    }


def monthly_seasonality(
    store: MarketStore,
    symbol: str,
    min_month_bars: int = DEFAULT_MIN_MONTH_BARS,
) -> dict[str, Any]:
    """Per-calendar-month return statistics plus the per-year return matrix."""
    series = load_close_series(store, symbol)
    dates = series["dates"]
    closes = series["closes"]

    frame = pd.DataFrame({"date": dates, "close": closes})
    frame["year"] = [d.year for d in dates]
    frame["month"] = [d.month for d in dates]

    months: list[dict[str, Any]] = []
    for (year, month), grp in frame.groupby(["year", "month"], sort=True):
        months.append(
            {
                "year": int(year),
                "month": int(month),
                "bars": int(len(grp)),
                "last_close": float(grp["close"].iloc[-1]),
                "partial": bool(len(grp) < min_month_bars),
            }
        )
    months.sort(key=lambda m: (m["year"], m["month"]))

    for i, m in enumerate(months):
        if i == 0:
            m["prev_last_close"] = None  # first month: no predecessor
            m["return_pct"] = None
        else:
            prev = months[i - 1]
            m["prev_last_close"] = prev["last_close"]
            m["return_pct"] = (
                100.0 * (m["last_close"] / prev["last_close"] - 1.0) if prev["last_close"] else None
            )
        # A return straddling a partial month (itself or its predecessor) is
        # not comparable; the flag travels with the month.
        m["excluded_from_aggregates"] = bool(
            m["return_pct"] is None or m["partial"] or (i > 0 and months[i - 1]["partial"])
        )

    usable = [m for m in months if not m["excluded_from_aggregates"]]

    by_month: list[dict[str, Any]] = []
    for month in range(1, 13):
        rets = [m["return_pct"] for m in usable if m["month"] == month]
        rets = [r for r in rets if r is not None]
        if rets:
            arr = np.array(rets, dtype=float)
            by_month.append(
                {
                    "month": month,
                    "name": pd.Timestamp(2026, month, 1).strftime("%B"),
                    "count": len(rets),
                    "mean_pct": float(arr.mean()),
                    "median_pct": float(np.median(arr)),
                    "std_pct": float(arr.std(ddof=1)) if len(rets) > 1 else None,
                    "hit_rate_pct": 100.0 * float((arr > 0).mean()),
                    "best_pct": float(arr.max()),
                    "worst_pct": float(arr.min()),
                }
            )
        else:
            by_month.append(
                {
                    "month": month,
                    "name": pd.Timestamp(2026, month, 1).strftime("%B"),
                    "count": 0,
                    "mean_pct": None,
                    "median_pct": None,
                    "std_pct": None,
                    "hit_rate_pct": None,
                    "best_pct": None,
                    "worst_pct": None,
                }
            )

    year_matrix: dict[str, dict[str, float | None]] = {}
    for m in months:
        if m["return_pct"] is None:
            continue
        year_matrix.setdefault(str(m["year"]), {})[f"{m['month']:02d}"] = float(m["return_pct"])

    return {
        "symbol": symbol.strip().upper(),
        "kind": series["kind"],
        "observations": len(dates),
        "first_date": _iso(dates[0]) if dates else None,
        "last_date": _iso(dates[-1]) if dates else None,
        "min_month_bars": int(min_month_bars),
        "months": months,
        "by_month": by_month,
        "year_matrix": year_matrix,
        "excluded_months": sum(1 for m in months if m["excluded_from_aggregates"]),
        "definitions": {
            "month_return": "last stored close of the month / last stored close of the "
            "previous stored month - 1, in percent",
            "partial_month": f"fewer than {int(min_month_bars)} stored bars; excluded together "
            "with any month whose predecessor is partial",
            "first_month": "no predecessor -> no return is invented for it",
        },
    }


def weekday_seasonality(store: MarketStore, symbol: str) -> dict[str, Any]:
    """Daily returns grouped by calendar weekday."""
    series = load_close_series(store, symbol)
    dates = series["dates"]
    closes = series["closes"]

    buckets: dict[int, list[float]] = {}
    for i in range(1, len(dates)):
        prev = closes[i - 1]
        if not prev:
            continue
        ret = 100.0 * (closes[i] / prev - 1.0)
        buckets.setdefault(dates[i].weekday(), []).append(ret)

    by_weekday = []
    for wd in range(7):
        rets = buckets.get(wd, [])
        if rets:
            arr = np.array(rets, dtype=float)
            by_weekday.append(
                {
                    "weekday": wd,
                    "name": _WEEKDAY_NAMES[wd],
                    "count": len(rets),
                    "mean_pct": float(arr.mean()),
                    "median_pct": float(np.median(arr)),
                    "std_pct": float(arr.std(ddof=1)) if len(rets) > 1 else None,
                    "hit_rate_pct": 100.0 * float((arr > 0).mean()),
                }
            )
        else:
            by_weekday.append(
                {
                    "weekday": wd,
                    "name": _WEEKDAY_NAMES[wd],
                    "count": 0,
                    "mean_pct": None,
                    "median_pct": None,
                    "std_pct": None,
                    "hit_rate_pct": None,
                }
            )

    return {
        "symbol": symbol.strip().upper(),
        "kind": series["kind"],
        "observations": len(dates),
        "by_weekday": by_weekday,
        "definitions": {
            "weekday_return": "close / previous stored close - 1, percent, grouped by the "
            "weekday of the later date",
            "missing_weekdays": "a weekday absent from the stored data is reported with "
            "count 0, never filled in",
        },
    }


def holiday_effect(
    store: MarketStore,
    symbol: str,
    calendar_path: Path | str | None = None,
) -> dict[str, Any]:
    """Returns around market holidays, or an honest 'unavailable'.

    The bundled calendar's holiday list is empty, so the default call reports
    ``available: False`` and why. With a populated list, each holiday yields
    the return from the last close before it to the first close after it
    (the reopen), plus the count of calendar days covered.
    """
    path = Path(calendar_path) if calendar_path is not None else DEFAULT_CALENDAR_PATH
    if not path.exists():
        return {
            "available": False,
            "reason": f"trading calendar not found at {path}",
            "calendar_path": str(path),
        }
    data = json.loads(path.read_text())
    raw = data.get("holidays", [])
    holidays: list[date] = []
    for item in raw:
        try:
            holidays.append(date.fromisoformat(str(item)))
        except ValueError:
            continue  # unparseable entries are ignored, not guessed

    if not holidays:
        return {
            "available": False,
            "reason": "the bundled trading_calendar.json has no holiday entries; a "
            "holiday study cannot be computed from stored bars alone and is not estimated",
            "calendar_path": str(path),
            "holidays_configured": 0,
        }

    series = load_close_series(store, symbol)
    dates = series["dates"]
    closes = series["closes"]
    if len(dates) < 3:
        return {
            "available": False,
            "reason": "not enough stored history",
            "calendar_path": str(path),
        }

    events: list[dict[str, Any]] = []
    for h in sorted(set(holidays)):
        pre_i = None
        post_i = None
        for i, d in enumerate(dates):
            if d < h:
                pre_i = i
            elif d > h and post_i is None:
                post_i = i
                break
        if pre_i is None or post_i is None:
            continue  # holiday outside the stored range
        pre_close = closes[pre_i]
        post_close = closes[post_i]
        if not pre_close:
            continue
        events.append(
            {
                "holiday": h.isoformat(),
                "last_session_before": _iso(dates[pre_i]),
                "first_session_after": _iso(dates[post_i]),
                "calendar_days_covered": (dates[post_i] - dates[pre_i]).days,
                "return_pct": 100.0 * (post_close / pre_close - 1.0),
            }
        )

    if not events:
        return {
            "available": False,
            "reason": "no configured holiday falls inside the stored history",
            "calendar_path": str(path),
            "holidays_configured": len(set(holidays)),
        }

    arr = np.array([e["return_pct"] for e in events], dtype=float)
    return {
        "available": True,
        "calendar_path": str(path),
        "holidays_configured": len(set(holidays)),
        "events": events,
        "summary": {
            "count": len(events),
            "mean_pct": float(arr.mean()),
            "median_pct": float(np.median(arr)),
            "hit_rate_pct": 100.0 * float((arr > 0).mean()),
        },
        "definitions": {
            "return_pct": "first close after the holiday / last close before it - 1, percent",
            "scope": "only holidays inside the stored date range produce events",
        },
    }


def seasonality_report(
    store: MarketStore,
    symbol: str,
    min_month_bars: int = DEFAULT_MIN_MONTH_BARS,
    calendar_path: Path | str | None = None,
) -> dict[str, Any]:
    """Monthly + weekday + holiday sections in one payload for the UI."""
    return {
        "symbol": symbol.strip().upper(),
        "monthly": monthly_seasonality(store, symbol, min_month_bars=min_month_bars),
        "weekday": weekday_seasonality(store, symbol),
        "holiday": holiday_effect(store, symbol, calendar_path=calendar_path),
        "disclaimer": "Descriptive historical statistics over the stored range; "
        "sample sizes are quoted everywhere. Not a forecast.",
    }
