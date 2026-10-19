"""Breadth-history tests.

Synthetic stores only; nothing here asserts anything about real NEPSE data.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from megatool.breadth import breadth_history
from megatool.market_store import MarketStore

RETRIEVED = pd.Timestamp("2026-10-11 00:00:00")


def _bars(symbol: str, closes, volume, start: str = "2026-01-05") -> pd.DataFrame:
    dates = pd.bdate_range(start, periods=len(closes))
    return pd.DataFrame(
        {
            "symbol": symbol,
            "trading_date": dates,
            "open": closes,
            "high": np.asarray(closes) * 1.01,
            "low": np.asarray(closes) * 0.99,
            "close": closes,
            "volume": np.asarray(volume, dtype=np.int64),
            "turnover": np.asarray(closes) * np.asarray(volume),
            "percent_change": np.nan,
            "source": "github.com/Aabishkar2/nepse-data",
            "retrieved_at": RETRIEVED,
        }
    )


@pytest.fixture
def store(tmp_path) -> MarketStore:
    s = MarketStore(tmp_path / "breadth.duckdb")
    s.upsert_bars(_bars("AAA", [10, 11, 12, 13, 14, 15], [100, 110, 120, 130, 140, 150]))
    s.upsert_bars(_bars("BBB", [15, 14, 13, 12, 11, 10], [200, 190, 180, 170, 160, 150]))
    s.upsert_bars(_bars("CCC", [12, 12, 12, 12, 12, 12], [50, 50, 50, 50, 50, 50]))
    yield s
    s.close()


def test_counts_and_ad_line(store):
    out = breadth_history(store, sma_windows=(2,), high_low_window=2)
    s = out["series"]
    assert out["trading_days"] == 6
    assert s["universe"] == [3] * 6
    # Day 1 has no previous close for anyone, so all three buckets are zero.
    assert s["advances"] == [0, 1, 1, 1, 1, 1]
    assert s["declines"] == [0, 1, 1, 1, 1, 1]
    assert s["unchanged"] == [0, 1, 1, 1, 1, 1]
    # AAA up, BBB down, CCC flat every day -> the line nets to zero.
    assert s["ad_line"] == [0, 0, 0, 0, 0, 0]


def test_pct_above_sma_with_availability(store):
    out = breadth_history(store, sma_windows=(2,), high_low_window=2)
    pct = out["series"]["pct_above_sma_2"]
    avail = out["available"]["sma_2"]
    assert pct[0] is None  # no SMA yet on day 1 -> no fabricated 0%
    assert avail == [0, 3, 3, 3, 3, 3]
    # AAA is always above its 2-bar SMA, BBB always below, CCC exactly equal
    # (equality is NOT "above").
    for v in pct[1:]:
        assert v == pytest.approx(100.0 / 3.0)


def test_new_highs_and_lows_window(store):
    out = breadth_history(store, sma_windows=(2,), high_low_window=2)
    s = out["series"]
    # Day 2: AAA and CCC equal their 2-bar max; BBB and CCC equal their 2-bar
    # min. CCC flat counts in both, per the stated equality rule.
    assert s["new_highs_2"][1] == 2
    assert s["new_lows_2"][1] == 2
    assert s["net_new_highs"][1] == 0
    assert s["new_highs_2"][0] is None  # window not full yet


def test_ad_volume_line_uses_directional_volume(store):
    out = breadth_history(store, sma_windows=(2,), high_low_window=2)
    s = out["series"]
    assert s["ad_volume_up"][1] == pytest.approx(110.0)  # AAA's up-bar volume
    assert s["ad_volume_down"][1] == pytest.approx(190.0)  # BBB's down-bar volume
    assert s["ad_volume_line"][1] == pytest.approx(-80.0)
    # Deltas shrink as the two series converge: -80, -60, -40, -20, 0 -> -200.
    assert s["ad_volume_line"][-1] == pytest.approx(-200.0)


def test_range_uses_prior_bars_for_comparisons(store):
    """A windowed request must not zero out the first returned day."""
    day3 = pd.Timestamp("2026-01-07").date()
    windowed = breadth_history(store, start=day3, sma_windows=(2,), high_low_window=2)
    assert len(windowed["dates"]) == 4
    # Day 3 is an advance day for AAA even though it is the first RETURNED row.
    assert windowed["series"]["advances"][0] == 1
    full = breadth_history(store, sma_windows=(2,), high_low_window=2)
    assert windowed["series"]["advances"] == full["series"]["advances"][2:]
    assert windowed["series"]["ad_line"] == full["series"]["ad_line"][2:]


def test_end_filter_matches_prefix(store):
    day4 = pd.Timestamp("2026-01-08").date()
    clipped = breadth_history(store, end=day4, sma_windows=(2,), high_low_window=2)
    full = breadth_history(store, sma_windows=(2,), high_low_window=2)
    for key, vals in clipped["series"].items():
        assert vals == full["series"][key][: len(vals)], key


def test_missing_symbol_is_not_counted(tmp_path):
    store = MarketStore(tmp_path / "gappy.duckdb")
    a = _bars("AAA", [10, 11, 12, 13], [100, 110, 120, 130])
    # BBB is missing the third session entirely.
    b = _bars("BBB", [20, 21, 23], [200, 210, 230])
    b.loc[b.index[-1], "trading_date"] = pd.Timestamp("2026-01-08")
    store.upsert_bars(a)
    store.upsert_bars(b)
    try:
        out = breadth_history(store, sma_windows=(2,), high_low_window=2)
        # Sessions: 01-05, 01-06, 01-07, 01-08 with BBB absent on 01-07.
        assert out["series"]["universe"] == [2, 2, 1, 2]
        # BBB is absent on 01-07, so it contributes nothing that day (not even
        # a carry-forward of 01-06's close).
        assert out["series"]["advances"][2] == 1  # only AAA rose
        assert out["series"]["declines"][2] == 0
    finally:
        store.close()


def test_empty_store_returns_empty_payload(tmp_path):
    store = MarketStore(tmp_path / "empty.duckdb")
    try:
        out = breadth_history(store)
        assert out["trading_days"] == 0
        assert out["dates"] == []
        assert out["series"] == {}
    finally:
        store.close()
