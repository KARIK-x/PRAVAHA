"""Tests for per-sector moving-average participation (market_dashboard).

Reference parity with the SastaShare "Percentage of stocks above Moving Average"
table. The important honesty property is the denominator: a security with fewer
than N stored closes must be EXCLUDED from that window, never counted as below.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from megatool.market_dashboard import sector_ma_participation
from megatool.market_store import MarketStore


def _bars(symbol: str, closes):
    n = len(closes)
    dates = pd.bdate_range("2026-01-01", periods=n)
    vol = np.full(n, 1000, dtype=np.int64)
    return pd.DataFrame(
        {
            "symbol": symbol,
            "trading_date": dates,
            "open": closes,
            "high": np.asarray(closes) * 1.01,
            "low": np.asarray(closes) * 0.99,
            "close": closes,
            "volume": vol,
            "turnover": np.asarray(closes) * vol,
            "percent_change": 1.0,
            "source": "SYNTHETIC-TEST-FIXTURE",
            "retrieved_at": pd.Timestamp("2026-10-11"),
            "validation_status": "valid",
        }
    )


@pytest.fixture
def store(tmp_path):
    s = MarketStore(tmp_path / "market.duckdb")
    yield s
    s.close()


def test_a_symbol_with_too_little_history_is_excluded_not_counted_as_below(store):
    """The denominator is what matters: 5 bars cannot say anything about SMA200."""
    # RISING: 5 bars, close always rising -> above any SMA it can compute.
    store.upsert_bars(_bars("RISING", 10.0 + np.arange(5)))
    # FALLING: 5 bars, close always falling.
    store.upsert_bars(_bars("FALLING", 100.0 - np.arange(5)))
    out = sector_ma_participation(store, {"RISING": "Banks", "FALLING": "Banks"})
    assert out["available"] is True
    row = next(e for e in out["sectors"] if e["sector"] == "Banks")
    # Only 5 bars: neither symbol can be judged against a 200-day SMA.
    assert row["denominator_200"] == 0
    assert row["pct_above_200"] is None      # not 0% and not 100%
    # The 10-day window needs 10 bars, so it is also empty here.
    assert row["denominator_10"] == 0
    assert row["pct_above_10"] is None


def test_participation_percentages_use_the_sector_denominator(store):
    # Four banks: two clearly above their SMA20, two clearly below.
    up = 100.0 + np.arange(30)          # rising
    down = 200.0 - np.arange(30)        # falling
    store.upsert_bars(_bars("UP1", up))
    store.upsert_bars(_bars("UP2", up))
    store.upsert_bars(_bars("DN1", down))
    store.upsert_bars(_bars("DN2", down))
    out = sector_ma_participation(
        store, {"UP1": "Banks", "UP2": "Banks", "DN1": "Banks", "DN2": "Banks"}
    )
    row = next(e for e in out["sectors"] if e["sector"] == "Banks")
    assert row["denominator_20"] == 4
    assert row["above_20"] == 2
    assert row["pct_above_20"] == pytest.approx(50.0)
    assert row["denominator_200"] == 0   # only 30 bars stored
    assert row["pct_above_200"] is None


def test_unclassified_symbols_are_reported_not_bucketed(store):
    store.upsert_bars(_bars("AAA", 100.0 + np.arange(30)))
    store.upsert_bars(_bars("BBB", 100.0 + np.arange(30)))
    out = sector_ma_participation(store, {"AAA": "Banks"})   # BBB has no sector
    assert out["unclassified"] == 1
    sectors = [e["sector"] for e in out["sectors"]]
    assert sectors == ["Banks"]


def test_empty_store_is_an_honest_unavailable_state(store):
    out = sector_ma_participation(store, {})
    assert out["available"] is False
    assert out["reason"]
    assert out["sectors"] == []


def test_above_50_and_200_requires_both(store):
    # 260 bars so both windows are computable.
    rising = 50.0 + np.arange(260) * 0.5
    falling = 300.0 - np.arange(260) * 0.5
    store.upsert_bars(_bars("R1", rising))
    store.upsert_bars(_bars("R2", rising))
    store.upsert_bars(_bars("F1", falling))
    store.upsert_bars(_bars("F2", falling))
    smap = {s: "Banks" for s in ("R1", "R2", "F1", "F2")}
    out = sector_ma_participation(store, smap)
    row = next(e for e in out["sectors"] if e["sector"] == "Banks")
    assert row["denominator_50"] == 4 and row["denominator_200"] == 4
    assert row["above_50"] == 2 and row["above_200"] == 2
    assert row["above_50_and_200"] == 2
    assert row["pct_above_50_and_200"] == pytest.approx(50.0)
