"""Backend overlay/date-mapping regression tests.

Replaces a vacuous placeholder whose "invariants" were tautologies
(``assert all(d is not None or d is None for d in [None])``) and a range check
(``len(w) in (1, 2)``) that could not distinguish correct from incorrect
grouping. This file tests the BACKEND computation only — calendar-week and
calendar-month aggregation, date-keyed (not index-keyed) mapping, gap handling
and partial periods. Frontend chart rendering by date is deferred to Phase 2.
"""

from __future__ import annotations

import pandas as pd

from megatool.ta.multitimeframe import aggregate_daily_to_monthly, aggregate_daily_to_weekly


def _df(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def _row(date: str, o: float, h: float, low: float, c: float, v: int) -> dict:
    return {"trading_date": date, "open": o, "high": h, "low": low, "close": c, "volume": v}


# ------------------------------------------------------- date-keyed mapping
def test_mapping_is_by_date_not_input_order():
    """Shuffling input rows must not change the aggregation: mapping is date-keyed."""
    rows = [
        _row("2026-03-08", 18, 19, 17, 17, 300),  # Sunday (latest)
        _row("2026-03-04", 10, 15, 9, 12, 100),  # Wednesday (earliest)
        _row("2026-03-06", 12, 20, 8, 18, 200),  # Friday
    ]
    a = aggregate_daily_to_weekly(_df(rows)).reset_index(drop=True)
    b = aggregate_daily_to_weekly(_df(list(reversed(rows)))).reset_index(drop=True)
    pd.testing.assert_frame_equal(a, b)


def test_weekly_ohlc_maps_from_dates_not_row_position():
    """open = first *by date*, high = max, low = min, close = last *by date*."""
    rows = [
        _row("2026-03-08", 18, 19, 17, 17, 300),  # latest -> close
        _row("2026-03-04", 10, 15, 9, 12, 100),  # earliest -> open
        _row("2026-03-06", 12, 20, 8, 18, 200),  # high/low
    ]
    w = aggregate_daily_to_weekly(_df(rows))
    assert len(w) == 1  # Mon 2026-03-02 .. Sun 2026-03-08 is one W-SUN week
    r = w.iloc[0]
    assert r["open"] == 10  # earliest date's open, not first row's
    assert r["high"] == 20  # max high
    assert r["low"] == 8  # min low
    assert r["close"] == 17  # latest date's close, not last row's
    assert r["volume"] == 600  # 100+200+300


# ------------------------------------------------------- calendar boundaries
def test_calendar_week_boundary_splits_groups():
    # Fri 2026-03-06 and Sun 2026-03-08 share the Mon-Sun week; Mon 2026-03-09 does not.
    rows = [
        _row("2026-03-06", 1, 2, 0.5, 1.5, 10),
        _row("2026-03-08", 1.5, 3, 1, 2, 10),
        _row("2026-03-09", 2, 4, 1.5, 3, 10),
    ]
    w = aggregate_daily_to_weekly(_df(rows))
    assert len(w) == 2
    assert str(pd.Timestamp(w.iloc[0]["trading_date"]).date()) == "2026-03-02"
    assert str(pd.Timestamp(w.iloc[1]["trading_date"]).date()) == "2026-03-09"


def test_calendar_month_boundary_splits_groups():
    rows = [
        _row("2026-03-31", 10, 12, 9, 11, 10),
        _row("2026-04-01", 11, 13, 10, 12, 10),
    ]
    m = aggregate_daily_to_monthly(_df(rows))
    assert len(m) == 2
    assert str(pd.Timestamp(m.iloc[0]["trading_date"]).date()) == "2026-03-01"
    assert str(pd.Timestamp(m.iloc[1]["trading_date"]).date()) == "2026-04-01"
    assert m.iloc[0]["volume"] == 10
    assert m.iloc[1]["volume"] == 10


# ------------------------------------------------------------ gaps & partial
def test_missing_month_is_not_fabricated():
    """A gap (no February sessions) yields no February period — never padded."""
    rows = [
        _row("2026-01-15", 10, 11, 9, 10, 10),
        _row("2026-03-16", 10, 11, 9, 10, 10),
    ]
    m = aggregate_daily_to_monthly(_df(rows))
    months = {str(pd.Timestamp(r["trading_date"]).date())[:7] for _, r in m.iterrows()}
    assert months == {"2026-01", "2026-03"}
    assert "2026-02" not in months


def test_partial_week_is_single_period_not_padded():
    # A lone Tuesday is one week carrying only that day's values.
    rows = [_row("2026-03-03", 5, 7, 4, 6, 42)]
    w = aggregate_daily_to_weekly(_df(rows))
    assert len(w) == 1
    r = w.iloc[0]
    assert (r["open"], r["high"], r["low"], r["close"], r["volume"]) == (5, 7, 4, 6, 42)


def test_gappy_daily_series_still_aggregates_existing_sessions():
    rows = [
        _row("2026-01-05", 1, 2, 0.5, 1.5, 10),  # Mon wk1
        _row("2026-01-12", 1.5, 3, 1, 2, 10),  # Mon wk2 (wk gap: Jan 6-9 absent)
        _row("2026-01-13", 2, 4, 1.5, 3, 10),  # Tue wk2
    ]
    w = aggregate_daily_to_weekly(_df(rows))
    # Jan 5 alone (wk1); Jan 12+13 (wk2). The absent Jan 6-9 creates no extra week.
    assert len(w) == 2
    assert w.iloc[0]["volume"] == 10
    assert w.iloc[1]["volume"] == 20


def test_output_columns_are_the_ohlcv_contract():
    w = aggregate_daily_to_weekly(_df([_row("2026-03-04", 1, 2, 0.5, 1.5, 10)]))
    assert list(w.columns) == ["trading_date", "open", "high", "low", "close", "volume"]
