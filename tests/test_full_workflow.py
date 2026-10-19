"""Full analytical-workflow integration test.

Relocated from a stray ``test_integration_final.py`` at the repository root
(which pytest never collected) and repaired. The original was broken four ways:
it imported a nonexistent ``detect_candlestick_patterns`` (ImportError), passed
the ``close`` array as ``find_swings``'s positional ``left`` argument, handed a
DataFrame to ``levels_for`` (which takes two float anchors), and asserted
tautologies (``len(swings) >= 0``, ``len(fib) > 0 or True``).

This version chains the real engines end to end on a deterministic fixture and
asserts observable, non-vacuous outcomes.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from megatool.quality import validate_bar
from megatool.ta.candles import detect_patterns
from megatool.ta.fibonacci import levels_for
from megatool.ta.multitimeframe import aggregate_daily_to_monthly, aggregate_daily_to_weekly
from megatool.ta.swings import find_swings


def _zigzag_ohlcv(n: int = 60, period: int = 12) -> dict[str, np.ndarray]:
    t = np.arange(n)
    tri = np.abs(2 * ((t / period) % 1.0) - 1)  # triangle wave -> real pivots
    close = 100.0 + 40.0 * tri
    open_ = np.empty(n)
    open_[0] = close[0]
    open_[1:] = close[:-1]
    high = np.maximum(open_, close) + 1.5
    low = np.minimum(open_, close) - 1.5
    volume = np.full(n, 1000, dtype=np.int64)
    return {"open": open_, "high": high, "low": low, "close": close, "volume": volume}


def _frame(arrays: dict[str, np.ndarray]) -> pd.DataFrame:
    n = len(arrays["close"])
    df = pd.DataFrame(
        {
            "symbol": ["WF"] * n,
            "trading_date": pd.bdate_range("2025-01-01", periods=n),
            "open": arrays["open"],
            "high": arrays["high"],
            "low": arrays["low"],
            "close": arrays["close"],
            "volume": arrays["volume"],
        }
    )
    df["turnover"] = df["close"] * df["volume"]
    df["percent_change"] = 1.0
    df["source"] = "synthetic-workflow-fixture"
    df["retrieved_at"] = pd.Timestamp("2026-10-11")
    df["validation_status"] = "valid"
    return df


def test_full_workflow_swings_fibonacci_candles_timeframes_quality():
    a = _zigzag_ohlcv()
    df = _frame(a)

    # 1. Swings — correct call: high and low only (no close array).
    swings = find_swings(a["high"], a["low"], left=2, right=2)
    assert len(swings) > 0  # the zigzag yields real pivots
    assert any(s.kind == "high" for s in swings) and any(s.kind == "low" for s in swings)

    # 2. Fibonacci — anchors are two float prices, not a DataFrame.
    fib = levels_for(float(a["low"].min()), float(a["high"].max()))
    assert fib.direction in {"up", "down"}
    assert fib.retracements  # default retracement ratios computed
    assert all("price" in r for r in fib.retracements)

    # 3. Candles — the real entry point is detect_patterns, returning Patterns.
    patterns = detect_patterns(a["open"], a["high"], a["low"], a["close"])
    assert isinstance(patterns, list)
    for p in patterns:
        assert p.name and p.index is not None
        assert p.direction in {"bullish", "bearish", "neutral"}

    # 4. Timeframes — calendar aggregation over the same frame.
    weekly = aggregate_daily_to_weekly(df)
    monthly = aggregate_daily_to_monthly(df)
    assert 0 < len(monthly) <= len(weekly) <= len(df)
    assert list(weekly.columns) == ["trading_date", "open", "high", "low", "close", "volume"]

    # 5. Quality — every synthetic bar is individually valid.
    for i in range(len(df)):
        flags, status = validate_bar(
            a["open"][i], a["high"][i], a["low"][i], a["close"][i], int(a["volume"][i])
        )
        assert status == "valid", f"bar {i} unexpectedly {status}: {flags}"


def test_fibonacci_expected_value_is_independent_of_workflow():
    """Anchors 100 -> 150: a 0.382 retracement is end - range*r = 150 - 50*0.382."""
    fib = levels_for(100.0, 150.0, retracements=[0.382], extensions=[])
    r = fib.retracements[0]
    assert abs(r["price"] - (150.0 - 50.0 * 0.382)) < 1e-9
