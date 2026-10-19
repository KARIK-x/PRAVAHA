"""Coverage-model tests.

Synthetic only. The point of these tests is to pin the *shape* of the
coverage calculation so the 78.3%-style conflation cannot come back: each
metric is a separate fraction with its own denominator, and an
unresolved-on-purpose record stays in the denominator instead of being
dropped to inflate the percentage.
"""

from __future__ import annotations

import pandas as pd

from megatool.coverage import coverage_report
from megatool.market_store import MarketStore


def _seed(tmp_path) -> MarketStore:
    store = MarketStore(tmp_path / "cov.duckdb")
    store.upsert_securities(
        [
            {
                "symbol": "AAA",
                "name": "Alpha Bank",
                "sector": "Banking",
                "instrument_type": "ordinary",
                "source": "test",
            },
            {
                "symbol": "BBB",
                "name": "Beta Hydro",
                "sector": "Hydro Power",
                "instrument_type": "ordinary",
                "source": "test",
            },
            # ordinary but deliberately unclassified
            {
                "symbol": "CCC",
                "name": "Gamma Finance",
                "sector": None,
                "instrument_type": "ordinary",
                "source": "test",
            },
            # non-ordinary instrument: classified by instrument, not sector
            {
                "symbol": "MF1",
                "name": "Some Mutual Fund",
                "sector": None,
                "instrument_type": "mutual_fund",
                "source": "test",
            },
            # a merged ticker WITH a successor
            {
                "symbol": "OLD1",
                "name": "Old Bank",
                "status": "MERGED",
                "successor_symbol": "AAA",
                "source": "test",
            },
            # a merged ticker WITHOUT a successor (unresolved on purpose)
            {"symbol": "OLD2", "name": "Vanished Bank", "status": "MERGED", "source": "test"},
        ]
    )
    return store


def _add_bars(store: MarketStore, symbol: str, n: int) -> None:
    rows = [
        {
            "symbol": symbol,
            "trading_date": f"2026-01-{(i % 28) + 1:02d}",
            "open": 100.0 + i,
            "high": 101.0 + i,
            "low": 99.0 + i,
            "close": 100.0 + i,
            "volume": 1000,
            "source": "test",
            "retrieved_at": "2026-01-01T00:00:00",
        }
        for i in range(n)
    ]
    # distinct trading_date per row is required by the PK
    for i, r in enumerate(rows):
        r["trading_date"] = f"2026-{(i // 28) + 1:02d}-{(i % 28) + 1:02d}"
    store.upsert_bars(pd.DataFrame(rows))


def test_metrics_are_separate_fractions(tmp_path):
    store = _seed(tmp_path)
    _add_bars(store, "AAA", 70)
    _add_bars(store, "BBB", 70)
    _add_bars(store, "CCC", 70)
    rep = coverage_report(store, min_bars=60)
    m = rep["metrics"]

    # identity: all 6 rows carry a name
    assert m["security_identity"]["numerator"] == 6
    assert m["security_identity"]["denominator"] == 6
    assert m["security_identity"]["pct"] == 100.0

    # active ordinary = AAA, BBB, CCC (mutual fund + 2 merged excluded)
    assert m["active_ordinary_identity"]["denominator"] == 3
    assert m["active_ordinary_identity"]["numerator"] == 3

    # sectors: 2 of 3 ordinary are classified -> 66.67%, NOT dropped
    assert m["sector_classification"]["numerator"] == 2
    assert m["sector_classification"]["denominator"] == 3
    assert m["sector_classification"]["pct"] == 66.6667

    # retired identity: both merged rows carry a name
    assert m["inactive_identity"]["numerator"] == 2
    assert m["inactive_identity"]["denominator"] == 2

    # successor mapping: 1 of 2 retired resolved; the unresolved one is kept
    assert m["historical_symbol_mapping"]["numerator"] == 1
    assert m["historical_symbol_mapping"]["denominator"] == 2
    assert m["historical_symbol_mapping"]["unresolved"] == ["OLD2"]

    # rankable ordinary with a sector: AAA, BBB (CCC has no sector)
    assert m["sector_rank_eligibility"]["numerator"] == 2
    assert m["sector_rank_eligibility"]["denominator"] == 3


def test_bar_floor_excludes_symbols(tmp_path):
    store = _seed(tmp_path)
    _add_bars(store, "AAA", 70)
    _add_bars(store, "BBB", 10)  # below the floor
    rep = coverage_report(store, min_bars=60)
    m = rep["metrics"]
    # only AAA clears the floor, and it is sectored
    assert m["sector_rank_eligibility"]["numerator"] == 1
    assert m["sector_rank_eligibility"]["denominator"] == 1


def test_report_explains_783_origin(tmp_path):
    store = _seed(tmp_path)
    rep = coverage_report(store)
    assert "401/512" in rep["origin_of_783"]
    assert "not a coverage metric" in rep["origin_of_783"]


def test_tolerates_premigration_schema(tmp_path):
    """A DB without the status column must not raise; status defaults UNKNOWN."""
    store = _seed(tmp_path)
    store.conn.execute("ALTER TABLE security_master DROP COLUMN status")
    rep = coverage_report(store)
    # every row now reads as active/unknown, so all 6 rows become "ordinary"?
    # No: instrument_type is untouched, so only the 3 ordinary rows stay eligible.
    assert rep["metrics"]["active_ordinary_identity"]["denominator"] == 3
    assert rep["totals"]["retired"] == 0
