"""Market breadth history computed from stored daily closes.

WHY A HISTORY
-------------
The dashboard already shows *today's* breadth counts. Research needs the
*series*: did breadth confirm the index rally, how many stocks were above
their 200-day line during the drawdown, is the advance/decline line making
new highs. This module derives those series from the same stored bars the
chart uses — nothing is fetched live and nothing is synthesised.

DEFINITIONS (fixed here, echoed in every API response)
-------------------------------------------------------
* **Universe on date t** — every symbol with a valid close on ``t`` (the store
  already excludes physically impossible rows).
* **Advances / declines / unchanged** — a symbol's close at ``t`` compared
  with its **previous stored close**. A symbol with no previous stored close
  contributes to none of the three.
* **% above SMA(n)** — symbols whose close at ``t`` exceeds the simple mean
  of the last *n stored trading dates* (``min_periods = n``; a symbol missing
  bars in that window is not counted as above). The denominator is the number
  of symbols where the SMA exists at ``t`` — reported as ``available`` so the
  percentage is auditable.
* **A/D line** — cumulative ``advances - declines`` over the returned range,
  starting at 0 at the first returned date. The *shape* is meaningful; the
  level is relative to the window requested.
* **A/D volume line** — cumulative ``up_volume - down_volume``, where a bar's
  volume counts as up when its close rose versus the symbol's previous stored
  close and down when it fell. Bars without stored volume contribute nothing.
* **New highs / lows (window w)** — symbols whose close equals the maximum /
  minimum of their last *w stored trading dates* (``min_periods = w``). A
  perfectly flat series therefore counts as both — that equality rule is
  stated rather than special-cased, because "flat is not a high" is a
  judgement call, not arithmetic.

No look-ahead: every value at ``t`` uses only bars dated ``t`` or earlier.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

import numpy as np
import pandas as pd

from megatool.market_store import MarketStore

DEFAULT_SMA_WINDOWS: tuple[int, ...] = (20, 50, 200)
DEFAULT_HIGH_LOW_WINDOW = 250


def _iso(value: Any) -> str:
    if isinstance(value, (datetime, date, pd.Timestamp)):
        return pd.Timestamp(value).date().isoformat()
    return str(value)


def _f(x: Any) -> float | None:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return None if np.isnan(v) else v


def _i(x: Any) -> int | None:
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return None if np.isnan(v) else int(v)


def definitions(sma_windows: tuple[int, ...], high_low_window: int) -> dict[str, str]:
    return {
        "universe": "symbols with a valid close on the date",
        "advances": "close > previous stored close for the same symbol",
        "declines": "close < previous stored close",
        "unchanged": "close == previous stored close",
        "pct_above_sma_n": f"100 * above / available, SMA over the last n stored trading dates "
        f"(windows: {', '.join(str(w) for w in sma_windows)})",
        "ad_line": "cumulative advances - declines over all stored history; the level is "
        "arbitrary, the shape is the signal",
        "ad_volume_line": "cumulative up_volume - down_volume "
        "(up = the bar's close rose versus the symbol's previous stored close)",
        "new_highs": f"close == max of the last {high_low_window} stored trading dates",
        "new_lows": f"close == min of the last {high_low_window} stored trading dates",
        "gaps": "a symbol missing a bar is excluded from that date's counts, never filled",
        "range": "start/end limit the RETURNED dates only; earlier stored bars still supply "
        "the comparisons and warm-ups every value at t depends on",
    }


def breadth_history(
    store: MarketStore,
    start: date | None = None,
    end: date | None = None,
    sma_windows: tuple[int, ...] = DEFAULT_SMA_WINDOWS,
    high_low_window: int = DEFAULT_HIGH_LOW_WINDOW,
) -> dict[str, Any]:
    """Compute the breadth series. Deterministic for fixed stored data."""
    windows = tuple(int(w) for w in sma_windows if int(w) >= 2)
    if not windows:
        windows = DEFAULT_SMA_WINDOWS
    if high_low_window < 2:
        raise ValueError("high_low_window must be >= 2")

    closes = store.all_closes()
    if closes.empty:
        return {
            "start": None,
            "end": None,
            "trading_days": 0,
            "definitions": definitions(windows, high_low_window),
            "dates": [],
            "series": {},
            "available": {},
        }

    closes = closes.set_index("trading_date")
    closes.index = pd.to_datetime(closes.index)
    closes = closes.sort_index()
    if closes.empty:
        return {
            "start": None,
            "end": None,
            "trading_days": 0,
            "definitions": definitions(windows, high_low_window),
            "dates": [],
            "series": {},
            "available": {},
        }

    prev = closes.shift(1)
    pairs = closes.notna() & prev.notna()
    advances = ((closes > prev) & pairs).sum(axis=1)
    declines = ((closes < prev) & pairs).sum(axis=1)
    unchanged = ((closes == prev) & pairs).sum(axis=1)
    universe = closes.notna().sum(axis=1)

    series: dict[str, list[float | int | None]] = {
        "universe": [_i(v) for v in universe],
        "advances": [_i(v) for v in advances],
        "declines": [_i(v) for v in declines],
        "unchanged": [_i(v) for v in unchanged],
    }

    available: dict[str, list[int | None]] = {}
    for w in windows:
        sma = closes.rolling(w, min_periods=w).mean()
        both = closes.notna() & sma.notna()
        above = ((closes > sma) & both).sum(axis=1)
        avail = both.sum(axis=1)
        pct = [
            100.0 * float(a) / float(b) if b > 0 else None
            for a, b in zip(above, avail, strict=True)
        ]
        series[f"pct_above_sma_{w}"] = pct
        available[f"sma_{w}"] = [_i(v) for v in avail]

    ad_line = (advances - declines).astype(float).cumsum()
    series["ad_line"] = [_f(v) for v in ad_line]

    volumes = store.all_volumes()
    if not volumes.empty:
        volumes = volumes.set_index("trading_date")
        volumes.index = pd.to_datetime(volumes.index)
        volumes = volumes.sort_index().reindex(closes.index)
        cols = closes.columns.intersection(volumes.columns)
        if len(cols):
            v_up = volumes[cols].where(closes[cols] > prev[cols]).sum(axis=1)
            v_dn = volumes[cols].where(closes[cols] < prev[cols]).sum(axis=1)
            adv = (v_up - v_dn).astype(float)
            series["ad_volume_up"] = [_f(v) for v in v_up]
            series["ad_volume_down"] = [_f(v) for v in v_dn]
            series["ad_volume_line"] = [_f(v) for v in adv.cumsum()]
        else:
            series["ad_volume_up"] = []
            series["ad_volume_down"] = []
            series["ad_volume_line"] = []
    else:
        series["ad_volume_up"] = [_f(np.nan)] * len(closes)
        series["ad_volume_down"] = [_f(np.nan)] * len(closes)
        series["ad_volume_line"] = [_f(np.nan)] * len(closes)

    w = high_low_window
    roll_max = closes.rolling(w, min_periods=w).max()
    roll_min = closes.rolling(w, min_periods=w).min()
    is_high = (closes == roll_max) & roll_max.notna()
    is_low = (closes == roll_min) & roll_min.notna()
    ready = roll_max.notna().sum(axis=1)  # symbols with a full window
    highs = is_high.sum(axis=1)
    lows = is_low.sum(axis=1)
    ready_arr = ready.to_numpy()
    highs_arr = highs.to_numpy()
    lows_arr = lows.to_numpy()
    series[f"new_highs_{w}"] = [
        None if ready_arr[i] == 0 else int(v) for i, v in enumerate(highs_arr)
    ]
    series[f"new_lows_{w}"] = [
        None if ready_arr[i] == 0 else int(v) for i, v in enumerate(lows_arr)
    ]
    series["net_new_highs"] = [
        None if ready_arr[i] == 0 else int(h - lo)
        for i, (h, lo) in enumerate(zip(highs_arr, lows_arr, strict=True))
    ]
    available[f"high_low_ready_{w}"] = [_i(v) for v in ready_arr]

    # The statistics above were computed on ALL stored history so that the
    # first returned date still has its real previous close, SMA window and
    # volume comparisons. start/end now select which dates to RETURN.
    idx = closes.index
    keep = np.ones(len(idx), dtype=bool)
    if start is not None:
        keep &= idx >= pd.Timestamp(start)
    if end is not None:
        keep &= idx <= pd.Timestamp(end)
    keep_pos = np.where(keep)[0]

    dates = [_iso(idx[i]) for i in keep_pos]
    series_out = {k: [v[i] for i in keep_pos] for k, v in series.items()}
    available_out = {k: [v[i] for i in keep_pos] for k, v in available.items()}
    return {
        "start": dates[0] if dates else None,
        "end": dates[-1] if dates else None,
        "trading_days": len(dates),
        "definitions": definitions(windows, high_low_window),
        "dates": dates,
        "series": series_out,
        "available": available_out,
    }
