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


#: Nepal's financial year runs Shrawan 1 – Ashadh end, which falls in mid-July.
#: The stored bars are Gregorian, so the boundary is DEFINED on the Gregorian
#: calendar as 16 July: FY N covers 16 Jul (N-1) .. 15 Jul (N). This is a stated
#: convention, not something inferred from the price data.
FY_START_MONTH, FY_START_DAY = 7, 16


def fiscal_year_of(d: date) -> int:
    """The Nepali financial year a Gregorian date belongs to (see FY_START_*)."""
    return d.year + 1 if (d.month, d.day) >= (FY_START_MONTH, FY_START_DAY) else d.year


def _period_seasonality(store: MarketStore, symbol: str, period_of, *, kind: str,
                        season_of=None, min_bars: int = 1) -> dict[str, Any]:
    """Shared engine for quarterly / financial-year seasonality.

    ``period_of`` identifies one concrete period (e.g. ``"2026-Q3"``); ``season_of``
    (optional) maps a date to the RECURRING label the statistics pool on (e.g.
    ``"Q3"``). Without it each period stands alone — correct for a financial year,
    wrong for a quarter, which must pool Q1 across every year.

    Groups stored bars into periods, takes the LAST STORED CLOSE of each period,
    computes period-over-period percentage returns, and aggregates them by the
    period's label. A period with fewer than ``min_bars`` stored bars is marked
    partial and excluded from the aggregates together with its successor (the
    return between them is not comparable) — the same rule monthly uses.
    """
    series = load_close_series(store, symbol)
    dates = series["dates"]
    closes = series["closes"]
    if not dates:
        return {"symbol": symbol.strip().upper(), "kind": kind, "periods": [],
                "by_period": [], "excluded_periods": 0,
                "definitions": {"period_return": "no stored bars"}}

    buckets: dict[Any, list[tuple[date, float]]] = {}
    for d, c in zip(dates, closes, strict=False):
        buckets.setdefault(period_of(d), []).append((d, float(c)))

    periods: list[dict[str, Any]] = []
    for label in sorted(buckets):
        rows = buckets[label]
        periods.append({
            "period": label,
            "season": (season_of(rows[-1][0]) if season_of else None),
            "bars": len(rows),
            "last_close": rows[-1][1],
            "first_date": _iso(rows[0][0]),
            "last_date": _iso(rows[-1][0]),
            "partial": bool(len(rows) < min_bars),
        })
    for i, per in enumerate(periods):
        if i == 0:
            per["prev_last_close"] = None
            per["return_pct"] = None
        else:
            prev = periods[i - 1]
            per["prev_last_close"] = prev["last_close"]
            per["return_pct"] = (
                100.0 * (per["last_close"] / prev["last_close"] - 1.0)
                if prev["last_close"] else None
            )
        per["excluded_from_aggregates"] = bool(
            per["return_pct"] is None or per["partial"] or (i > 0 and periods[i - 1]["partial"])
        )

    usable = [p2 for p2 in periods if not p2["excluded_from_aggregates"]]
    # Pool on the RECURRING label when one exists (Q1..Q4 across years); otherwise
    # each period stands alone (a financial year is not a recurring season).
    key_of = (lambda x: x["season"]) if season_of else (lambda x: x["period"])
    by_period: list[dict[str, Any]] = []
    for label in sorted({key_of(p2) for p2 in usable}):
        rets = [p2["return_pct"] for p2 in usable if key_of(p2) == label]
        if not rets:
            continue
        arr = pd.Series(rets, dtype="float64")
        by_period.append({
            "period": label,
            "n": int(arr.size),
            "mean_pct": float(arr.mean()),
            "median_pct": float(arr.median()),
            "stdev_pct": float(arr.std(ddof=1)) if arr.size > 1 else None,
            "positive": int((arr > 0).sum()),
            "positive_pct": float((arr > 0).mean() * 100.0),
            "best_pct": float(arr.max()),
            "worst_pct": float(arr.min()),
        })

    return {
        "symbol": symbol.strip().upper(),
        "kind": kind,
        "observations": len(dates),
        "first_date": _iso(dates[0]),
        "last_date": _iso(dates[-1]),
        "periods": periods,
        "by_period": by_period,
        "excluded_periods": sum(1 for p2 in periods if p2["excluded_from_aggregates"]),
        "definitions": {
            "period_return": "last stored close of the period / last stored close of the "
            "previous stored period - 1, in percent",
            "quarterly": "calendar quarters (Jan-Mar, Apr-Jun, Jul-Sep, Oct-Dec)",
            "fiscal_year": f"FY N = {FY_START_DAY} Jul (N-1) .. {FY_START_DAY - 1} Jul (N) "
                           "(Nepal's Shrawan–Ashadh year, stated on the Gregorian calendar)",
            "partial_period": f"fewer than {int(min_bars)} stored bars; excluded with its successor",
        },
    }


def quarterly_seasonality(store: MarketStore, symbol: str) -> dict[str, Any]:
    """Per-calendar-quarter return statistics."""
    return _period_seasonality(
        store, symbol,
        lambda d: f"{d.year}-Q{(d.month - 1) // 3 + 1}",
        kind="quarterly",
        # Pool Q1/Q2/Q3/Q4 ACROSS years — that is what quarterly seasonality means.
        season_of=lambda d: f"Q{(d.month - 1) // 3 + 1}",
    )


def fiscal_year_seasonality(store: MarketStore, symbol: str) -> dict[str, Any]:
    """Per-Nepali-financial-year return statistics."""
    return _period_seasonality(store, symbol, fiscal_year_of, kind="fiscal_year")


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


def calendar_event_study(
    store: MarketStore,
    symbol: str,
    calendar_path: Path | str | None = None,
    *,
    pre_days: int = 5,
    post_days: int = 5,
    classifications: list[str] | None = None,
) -> dict[str, Any]:
    """Event-window study over the extracted Hamro Patro calendar.

    For every calendar record whose Gregorian date resolved and falls inside
    the symbol's stored history, this measures the return across a pre-event
    window and a post-event window, using **only sessions actually present in
    the stored bars**. Nothing is forward-filled and no bar is invented.

    Honesty properties:
      * An event is only used when enough real sessions exist on both sides;
        the count that qualified is reported next to the statistics.
      * Windows are labelled with the session dates that produced them, so a
        reader can re-derive every number.
      * The result is an association over a small sample. It is never described
        as causation, and no significance claim is made without a stated test.
      * Calendar events, public holidays and confirmed NEPSE closures are
        kept as distinct classifications; a red calendar cell is never
        promoted to a market closure.
    """
    path = Path(calendar_path) if calendar_path is not None else DEFAULT_CALENDAR_PATH
    out_base: dict[str, Any] = {
        "symbol": symbol.strip().upper(),
        "calendar_path": str(path),
        "pre_days": pre_days,
        "post_days": post_days,
    }
    if not path.is_file():
        return {**out_base, "available": False, "events_considered": 0,
                "reason": f"calendar dataset not found at {path}"}
    try:
        records = (json.loads(path.read_text(encoding="utf-8")).get("records")) or []
    except (json.JSONDecodeError, OSError) as exc:
        return {**out_base, "available": False, "reason": f"unreadable calendar: {exc}"}

    events: list[date] = []
    seen: set[date] = set()
    skipped_unresolved = skipped_class = 0
    for r in records:
        gd = r.get("gregorian_date")
        if not gd:
            skipped_unresolved += 1
            continue
        try:
            d = date.fromisoformat(str(gd))
        except ValueError:
            skipped_unresolved += 1
            continue
        if classifications and r.get("classification") not in classifications:
            skipped_class += 1
            continue
        if d not in seen:
            seen.add(d)
            events.append(d)
    events.sort()

    dates: list[date] = []
    closes: list[float] = []
    try:
        series = load_close_series(store, symbol)
    except KeyError as exc:
        # A symbol with no stored history is an honest "unavailable", not a crash.
        # The summary dict is built first so this path reports the same fields.
        dates, closes = [], []
        out = {**out_base,
               "events_considered": len(records),
               "events_unresolved_skipped": skipped_unresolved,
               "events_class_skipped": skipped_class,
               "events_distinct": len(events),
               "first_date": None,
               "last_date": None}
        return {**out, "available": False, "reason": str(exc)}
    dates = series["dates"]
    closes = series["closes"]
    n = len(dates)
    out = {**out_base,
           "events_considered": len(records),
           "events_unresolved_skipped": skipped_unresolved,
           "events_class_skipped": skipped_class,
           "events_distinct": len(events),
           "first_date": _iso(dates[0]) if dates else None,
           "last_date": _iso(dates[-1]) if dates else None}
    if n < pre_days + post_days + 2:
        return {**out, "available": False, "reason": "not enough stored history"}

    rows: list[dict[str, Any]] = []
    for ev in events:
        # Last session strictly before the event, first session after it.
        pre_i = None
        post_i = None
        for i, d in enumerate(dates):
            if d < ev:
                pre_i = i
            elif d > ev and post_i is None:
                post_i = i
                break
        if pre_i is None or post_i is None:
            continue
        if pre_i - pre_days < 0 or post_i + post_days > n - 1:
            continue  # not enough real sessions on one side: skip, never pad
        pre_close = closes[pre_i]
        if not pre_close:
            continue
        pre_win = 100.0 * (pre_close / closes[pre_i - pre_days] - 1.0)
        post_win = 100.0 * (closes[post_i + post_days] / pre_close - 1.0)
        # The session immediately after the event, when there is one.
        event_day = None
        if post_i == pre_i + 1:
            event_day = 100.0 * (closes[post_i] / pre_close - 1.0)
        rows.append({
            "event": ev.isoformat(),
            "last_session_before": _iso(dates[pre_i]),
            "first_session_after": _iso(dates[post_i]),
            "sessions_before": pre_days,
            "sessions_after": post_days,
            "pre_window_pct": pre_win,
            "post_window_pct": post_win,
            "event_day_pct": event_day,
            "market_closure_status": next(
                (r.get("market_closure") for r in records
                 if r.get("gregorian_date") == ev.isoformat()), "not_independently_verified"),
        })

    if not rows:
        return {**out, "available": False,
                "reason": "no resolved calendar event has enough stored history on both sides"}

    def _stats(key: str) -> dict[str, Any]:
        vals = np.array([r[key] for r in rows if r[key] is not None], dtype=float)
        if vals.size == 0:
            return {"n": 0}
        return {
            "n": int(vals.size),
            "mean_pct": float(vals.mean()),
            "median_pct": float(np.median(vals)),
            "stdev_pct": float(vals.std(ddof=1)) if vals.size > 1 else None,
            "positive": int((vals > 0).sum()),
            "positive_pct": float((vals > 0).mean() * 100.0),
            "best_pct": float(vals.max()),
            "worst_pct": float(vals.min()),
        }

    return {
        **out,
        "available": True,
        "events_used": len(rows),
        "pre_window": _stats("pre_window_pct"),
        "post_window": _stats("post_window_pct"),
        "event_day": _stats("event_day_pct"),
        "events": rows,
        "definitions": {
            "pre_window_pct": f"close of the last session before the event / close "
                             f"{pre_days} sessions earlier - 1, percent",
            "post_window_pct": f"close {post_days} sessions after the last session before "
                              f"the event / that close - 1, percent",
            "event_day_pct": "close of the first session after the event / the last close "
                             "before it - 1, percent",
            "session": "a session actually present in the stored bars; no session is "
                       "forward-filled and none is invented",
            "scope": "association over a small sample; not causation, and no significance "
                     "claim is made",
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
        "quarterly": quarterly_seasonality(store, symbol),
        "fiscal_year": fiscal_year_seasonality(store, symbol),
        "holiday": holiday_effect(store, symbol, calendar_path=calendar_path),
        "event_study": calendar_event_study(store, symbol, calendar_path=calendar_path),
        "disclaimer": "Descriptive historical statistics over the stored range; "
        "sample sizes are quoted everywhere. Not a forecast.",
    }
