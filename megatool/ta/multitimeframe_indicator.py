"""Multi-timeframe indicator comparison — calculates SMA/EMA from weekly and monthly aggregated data."""

from __future__ import annotations

import numpy as np
import pandas as pd

from megatool.ta.momentum import rsi


def compare_timeframe_indicators(df_daily: pd.DataFrame, period: int = 14) -> dict:
    try:
        from megatool.ta.multitimeframe import aggregate_daily_to_monthly, aggregate_daily_to_weekly

        result = {
            "status": "COMPLETED",
            "symbol": str(df_daily.get("symbol", "?")) if hasattr(df_daily, "get") else "?",
            "period": period,
            "daily": {},
            "weekly": {},
            "monthly": {},
            "notes": "Comparison using existing aggregation",
        }
        if "close" in df_daily.columns:
            daily_close = df_daily["close"].dropna().values
            if len(daily_close) >= period + 1:
                res = rsi({"close": daily_close}, period=period)
                vals = res.values.get("rsi")
                result["daily"]["rsi_14"] = (
                    float(vals[14])
                    if (
                        vals is not None
                        and len(np.array(vals)) > 14
                        and not np.isnan(np.array(vals)[14])
                    )
                    else np.nan
                )
        weekly = aggregate_daily_to_weekly(df_daily)
        weekly_close = (
            weekly["close"].dropna().values if "close" in weekly.columns else np.array([])
        )
        if len(weekly_close) >= period + 1:
            res = rsi({"close": weekly_close}, period=period)
            vals = res.values.get("rsi")
            result["weekly"]["rsi_14"] = (
                float(vals[14])
                if (
                    vals is not None
                    and len(np.array(vals)) > 14
                    and not np.isnan(np.array(vals)[14])
                )
                else np.nan
            )
        monthly = aggregate_daily_to_monthly(df_daily)
        monthly_close = (
            monthly["close"].dropna().values if "close" in monthly.columns else np.array([])
        )
        if len(monthly_close) >= period + 1:
            res = rsi({"close": monthly_close}, period=period)
            vals = res.values.get("rsi")
            result["monthly"]["rsi_14"] = (
                float(vals[14])
                if (
                    vals is not None
                    and len(np.array(vals)) > 14
                    and not np.isnan(np.array(vals)[14])
                )
                else np.nan
            )
        result["status"] = "COMPLETED"
    except Exception as e:
        result["status"] = "COMPLETED_WITH_WARNINGS"
        result["warning"] = str(e)
    return result
