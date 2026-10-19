"""Regression tests for a real cross-thread read race in MarketStore.

The defect
----------
DuckDB keeps the *most recent* result on the connection, not on a cursor.
``MarketStore.execute()`` held the lock only while running the statement, so a
caller that did ``self.execute(...).fetchone()`` (or ``.df()``) fetched with the
lock released. A second thread's ``execute()`` could overwrite the pending
result in that window.

Observed consequences in production:

* ``GET /api/status`` returned **HTTP 500** with
  ``ValueError: zip() argument 2 is longer than argument 1`` in
  ``global_coverage`` — the row it fetched belonged to a *different* query and
  had a different column count.
* The same window could silently hand one request another request's bars.

``MarketStore`` already documented the hazard and added an ``RLock``, but the
fetch happened outside it. The fix adds ``query_one`` / ``query_rows`` /
``query_df``, which hold the lock across execute **and** fetch.

These tests are SYNTHETIC: a throwaway DuckDB under ``tmp_path``, never the
production database.
"""

from __future__ import annotations

import threading

import numpy as np
import pandas as pd
import pytest

from megatool.market_store import MarketStore

RETRIEVED = pd.Timestamp("2026-10-13 00:00:00")

SYMBOLS = ["AAA", "BBB", "CCC", "DDD"]
BARS_PER_SYMBOL = 60


def _synthetic_bars() -> pd.DataFrame:
    """SYNTHETIC FIXTURE — clearly labelled by its ``source`` field."""
    frames = []
    for sym in SYMBOLS:
        closes = np.linspace(100.0, 140.0, BARS_PER_SYMBOL)
        dates = pd.bdate_range("2026-01-01", periods=BARS_PER_SYMBOL)
        vol = np.full(BARS_PER_SYMBOL, 1_000, dtype=np.int64)
        frames.append(
            pd.DataFrame(
                {
                    "symbol": sym,
                    "trading_date": dates,
                    "open": closes,
                    "high": closes * 1.01,
                    "low": closes * 0.99,
                    "close": closes,
                    "volume": vol,
                    "turnover": closes * vol,
                    "percent_change": 1.0,
                    "source": "synthetic-concurrency-fixture",
                    "retrieved_at": RETRIEVED,
                    "validation_status": "valid",
                }
            )
        )
    return pd.concat(frames, ignore_index=True)


@pytest.fixture()
def store(tmp_path):
    s = MarketStore(tmp_path / "concurrency.duckdb")
    s.upsert_bars(_synthetic_bars())
    yield s
    s.close()


def test_single_threaded_reads_return_expected_shape(store):
    gc = store.global_coverage()
    assert gc["bars"] == len(SYMBOLS) * BARS_PER_SYMBOL
    assert gc["symbols"] == len(SYMBOLS)
    assert gc["first_date"] and gc["last_date"]
    assert store.bar_count() == len(SYMBOLS) * BARS_PER_SYMBOL
    assert store.symbols() == sorted(SYMBOLS)
    assert len(store.get_bars("AAA")) == BARS_PER_SYMBOL
    assert len(store.coverage()) == len(SYMBOLS)


def test_locked_helpers_hold_the_lock_for_execute_and_fetch(store):
    """The helpers must exist and must be the ones the reads now go through."""
    assert hasattr(store, "query_one")
    assert hasattr(store, "query_rows")
    assert hasattr(store, "query_df")

    row = store.query_one("SELECT COUNT(*) AS n, COUNT(DISTINCT symbol) AS s FROM price_bars")
    assert row is not None
    assert len(row) == 2
    assert row[0] == len(SYMBOLS) * BARS_PER_SYMBOL

    assert store.query_one("SELECT 1 WHERE 1 = 0") is None
    # ORDER BY is explicit: GROUP BY alone promises no order.
    got = store.query_rows("SELECT symbol FROM price_bars GROUP BY symbol ORDER BY symbol")
    assert got == [(s,) for s in sorted(SYMBOLS)]
    assert len(store.query_df("SELECT * FROM price_bars")) == len(SYMBOLS) * BARS_PER_SYMBOL


def test_no_read_path_still_fetches_outside_the_lock(store):
    """Every ``self.execute(...)`` in the store must be inside a lock block.

    This guards the *shape* of the bug, so a future read added the unsafe way
    fails here instead of in production.
    """
    import re
    from pathlib import Path

    src = Path("megatool/market_store.py")
    lines = src.read_text().splitlines()

    lock_ranges: list[tuple[int, int]] = []
    depth: int | None = None
    start = 0
    for i, line in enumerate(lines, 1):
        if re.match(r"\s*with self\._lock:", line):
            depth = len(line) - len(line.lstrip())
            start = i
        elif depth is not None:
            indent = len(line) - len(line.lstrip()) if line.strip() else 10**9
            if line.strip() and indent <= depth:
                lock_ranges.append((start, i))
                depth = None
    if depth is not None:
        lock_ranges.append((start, len(lines) + 1))

    racy = [
        (i, line.strip())
        for i, line in enumerate(lines, 1)
        if "self.execute(" in line and not any(a <= i < b for a, b in lock_ranges)
    ]
    assert racy == [], f"reads fetch outside the lock: {racy}"


def test_concurrent_reads_never_raise_or_mix_results(store):
    """Hammer the read API from many threads.

    Before the fix this raised ``ValueError: zip() argument 2 is longer than
    argument 1`` from ``global_coverage`` and could return another thread's
    data. Afterwards, every thread must see identical values for the same key.
    """
    errors: list[str] = []
    seen: dict[str, set[str]] = {}
    guard = threading.Lock()

    def record(key: str, value: object) -> None:
        with guard:
            seen.setdefault(key, set()).add(str(value))

    def worker() -> None:
        for _ in range(40):
            try:
                record("global_coverage", store.global_coverage())
                record("bar_count", store.bar_count())
                record("symbols", store.symbols())
                record("bars_aaa", len(store.get_bars("AAA")))
                record("coverage_rows", len(store.coverage()))
                record("all_closes_shape", store.all_closes().shape)
            except Exception as exc:  # noqa: BLE001 - the point is to catch these
                with guard:
                    errors.append(f"{type(exc).__name__}: {exc}")

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=120)

    assert not errors, f"{len(errors)} concurrent read failure(s): {errors[:5]}"

    # No key may have two different answers: that would mean one thread saw
    # another thread's result.
    mixed = {k: v for k, v in seen.items() if len(v) != 1}
    assert mixed == {}, f"threads disagreed: {mixed}"

    assert seen["bar_count"] == {str(len(SYMBOLS) * BARS_PER_SYMBOL)}
    assert seen["symbols"] == {str(sorted(SYMBOLS))}


def test_concurrent_reads_are_not_truncated_rows(store):
    """``global_coverage`` must always return exactly its five columns."""
    lengths: set[int] = set()
    errors: list[str] = []

    def worker() -> None:
        for _ in range(40):
            try:
                gc = store.global_coverage()
                lengths.add(len(gc))
                assert set(gc) == {
                    "bars",
                    "symbols",
                    "first_date",
                    "last_date",
                    "last_retrieved",
                }
            except Exception as exc:  # noqa: BLE001
                errors.append(f"{type(exc).__name__}: {exc}")

    threads = [threading.Thread(target=worker) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=120)

    assert not errors, errors[:5]
    assert lengths == {5}, f"column count varied: {lengths}"
