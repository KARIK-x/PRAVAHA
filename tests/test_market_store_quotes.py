"""Near-live quote store tests (synthetic).

Pin the two properties that matter for the YONEPSE path: re-running a
snapshot is idempotent, and freshness is computed from the *source*
timestamp (Nepal time, UTC+05:45) rather than the wall clock.
"""

from __future__ import annotations

from datetime import UTC, datetime

from megatool.market_store import MarketStore


def _store(tmp_path) -> MarketStore:
    return MarketStore(tmp_path / "quotes.duckdb")


def _row(symbol: str, ltp: float | None, updated: str, status: str = "valid") -> dict:
    return {
        "symbol": symbol,
        "quote_date": updated[:10],
        "ltp": ltp,
        "previous_close": 100.0,
        "high": 105.0,
        "low": 95.0,
        "change": 1.0,
        "percent_change": 1.0,
        "volume": 1000,
        "turnover": 100000.0,
        "trades": 10,
        "market_cap": 1e9,
        "name": symbol + " Ltd",
        "source": "yonepse/market/live.json",
        "source_updated_at": updated,
        "retrieved_at": "2026-10-15T14:00:00",
        "validation_status": status,
    }


def test_upsert_is_idempotent(tmp_path):
    store = _store(tmp_path)
    rows = [_row("AAA", 101.0, "2026-10-12T14:59:59"), _row("BBB", 55.5, "2026-10-12T14:59:59")]
    assert store.upsert_quotes(rows) == 2
    assert store.upsert_quotes(rows) == 2  # same snapshot again
    assert store.quote_freshness()["rows"] == 2
    assert store.quote_freshness()["distinct_symbols"] == 2


def test_refresh_overwrites_in_place(tmp_path):
    store = _store(tmp_path)
    store.upsert_quotes([_row("AAA", 101.0, "2026-10-12T12:00:00")])
    store.upsert_quotes([_row("AAA", 102.0, "2026-10-12T14:59:59")])
    q = store.latest_quotes()
    assert len(q) == 1
    assert q[0]["ltp"] == 102.0


def test_freshness_uses_source_timestamp_in_npt(tmp_path):
    store = _store(tmp_path)
    # 2026-10-12T14:59:59 NPT == 09:14:59 UTC on 2026-10-12
    store.upsert_quotes([_row("AAA", 101.0, "2026-10-12T14:59:59")])
    now = datetime(2026, 10, 12, 9, 44, 59, tzinfo=UTC)  # 30 min after the quote
    f = store.quote_freshness(now=now)
    assert f["age_minutes"] == 30.0
    assert f["is_stale"] is False
    assert "Nepal" in f["timestamp_basis"]


def test_stale_flag_after_a_day(tmp_path):
    store = _store(tmp_path)
    store.upsert_quotes([_row("AAA", 101.0, "2026-10-12T14:59:59")])
    now = datetime(2026, 10, 15, 14, 0, 0, tzinfo=UTC)  # ~3 days later
    q = store.latest_quotes(now=now)[0]
    assert q["is_stale"] is True
    assert q["age_minutes"] > 24 * 60


def test_missing_and_valid_zero_are_distinct(tmp_path):
    store = _store(tmp_path)
    store.upsert_quotes(
        [
            _row("AAA", None, "2026-10-12T14:59:59", status="missing"),
            _row("BBB", 0.0, "2026-10-12T14:59:59", status="valid"),
        ]
    )
    by = {q["symbol"]: q for q in store.latest_quotes()}
    # unavailable (NULL) is stored and read back distinctly from a genuine 0.0
    assert by["AAA"]["ltp"] is None and by["AAA"]["validation_status"] == "missing"
    assert by["BBB"]["ltp"] == 0.0 and by["BBB"]["validation_status"] == "valid"


def test_quotes_do_not_touch_price_bars(tmp_path):
    store = _store(tmp_path)
    store.upsert_quotes([_row("AAA", 101.0, "2026-10-12T14:59:59")])
    bars = store.query_one("SELECT COUNT(*) FROM price_bars")
    assert bars[0] == 0


def test_readers_tolerate_absent_table(tmp_path):
    """A DB without market_quotes must read as empty, not raise."""
    store = _store(tmp_path)
    store.conn.execute("DROP TABLE market_quotes")
    assert store.latest_quotes() == []
    assert store.quote_freshness()["rows"] == 0
