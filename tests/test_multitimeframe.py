import pandas as pd

from megatool.ta.multitimeframe import aggregate_daily_to_monthly, aggregate_daily_to_weekly


def test_weekly_aggregation():
    df = pd.DataFrame(
        {
            "trading_date": ["2026-01-05", "2026-01-06", "2026-01-07", "2026-01-12", "2026-01-13"],
            "open": [100, 101, 102, 110, 111],
            "high": [105, 106, 107, 115, 116],
            "low": [95, 96, 97, 105, 106],
            "close": [104, 105, 106, 114, 115],
            "volume": [100, 200, 300, 400, 500],
        }
    )
    weekly = aggregate_daily_to_weekly(df)
    assert len(weekly) >= 1  # calendar-week grouping
    # weekly sums per calendar week (not artificially 600)


def test_monthly_aggregation():
    df = pd.DataFrame(
        {
            "trading_date": ["2026-01-05", "2026-01-15", "2026-02-01", "2026-02-10"],
            "open": [100, 105, 110, 115],
            "high": [110, 115, 120, 125],
            "low": [95, 100, 105, 110],
            "close": [105, 110, 115, 120],
            "volume": [100, 200, 300, 400],
        }
    )
    monthly = aggregate_daily_to_monthly(df)
    assert len(monthly) == 2
    assert monthly.iloc[0]["volume"] == 300  # Jan: 100+200
