"""Regression guard: a quote can never reach a consumer without its freshness.

The dashboard/API path must never emit a quote that looks current when it is
stale, delayed or undefined. These tests pin that invariant at both the store
and the HTTP layer, and re-assert that *unavailable* is never coerced to zero.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone

from fastapi.testclient import TestClient

from megatool.api import create_app
from megatool.market_store import MarketStore

NPT = timezone(timedelta(hours=5, minutes=45))


def _npt_at(offset: timedelta, now: datetime) -> str:
    """A naive NPT timestamp string ``offset`` away from ``now``."""
    return (now + offset).astimezone(NPT).replace(tzinfo=None).isoformat(timespec="seconds")


def _store(tmp_path) -> MarketStore:
    return MarketStore(tmp_path / "freshness.duckdb")


def _quote(symbol: str, ltp, updated: str | None) -> dict:
    return {
        "symbol": symbol,
        "quote_date": (updated or "2026-10-15")[:10],
        "ltp": ltp,
        "previous_close": 100.0,
        "high": 105.0,
        "low": 95.0,
        "change": None,
        "percent_change": None,
        "volume": 10,
        "turnover": 1000.0,
        "trades": None,
        "market_cap": None,
        "name": symbol,
        "source": "nepalstock.com.np/api/nots/lives-market",
        "source_updated_at": updated,
        "retrieved_at": "2026-10-15T09:15:00",
    }


def test_store_never_emits_a_quote_without_a_freshness_flag(tmp_path):
    store = _store(tmp_path)
    store.upsert_quotes(
        [
            _quote("FRESH", 101.0, "2026-10-15T15:00:00"),
            _quote("STALE", 55.0, "2026-10-10T15:00:00"),
            _quote("UNKNOWN", 77.0, None),  # no source timestamp at all
        ]
    )
    rows = store.latest_quotes(now=datetime(2026, 10, 15, 9, 15, tzinfo=UTC))
    assert len(rows) == 3
    for r in rows:
        assert "freshness_class" in r and "age_minutes" in r and "is_stale" in r
        assert r["freshness_class"] in {"fresh", "delayed", "stale", "unknown"}

    by = {r["symbol"]: r for r in rows}
    assert by["FRESH"]["freshness_class"] == "fresh"
    assert by["STALE"]["freshness_class"] == "stale"
    # A quote with no source timestamp is 'unknown' — never silently 'fresh'.
    assert by["UNKNOWN"]["freshness_class"] == "unknown"
    assert by["UNKNOWN"]["age_minutes"] is None


def test_unavailable_price_is_never_zero(tmp_path):
    store = _store(tmp_path)
    store.upsert_quotes([_quote("MISSING", None, "2026-10-15T15:00:00")])
    row = store.latest_quotes(now=datetime(2026, 10, 15, 9, 15, tzinfo=UTC))[0]
    assert row["ltp"] is None  # not 0.0
    assert row["ltp"] != 0.0


def test_api_quotes_every_row_carries_freshness_and_summary_has_class(tmp_path):
    now = datetime.now(UTC)
    store = _store(tmp_path)
    store.upsert_quotes(
        [
            _quote("FRESH", 101.0, _npt_at(timedelta(0), now)),
            _quote("STALE", 55.0, _npt_at(timedelta(days=-10), now)),
        ]
    )
    app = create_app(store=store)
    with TestClient(app) as c:
        r = c.get("/api/quotes")
        assert r.status_code == 200
        d = r.json()
        assert "freshness" in d and "freshness_class" in d["freshness"]
        for q in d["quotes"]:
            assert "freshness_class" in q and "age_minutes" in q and "is_stale" in q
        # A stale quote must carry a non-fresh class.
        stale = next(q for q in d["quotes"] if q["symbol"] == "STALE")
        assert stale["freshness_class"] == "stale"
        fresh = next(q for q in d["quotes"] if q["symbol"] == "FRESH")
        assert fresh["freshness_class"] in {"fresh", "delayed"}


def test_max_age_filter_excludes_stale_rows(tmp_path):
    now = datetime.now(UTC)
    store = _store(tmp_path)
    store.upsert_quotes(
        [
            _quote("FRESH", 101.0, _npt_at(timedelta(0), now)),
            _quote("STALE", 55.0, _npt_at(timedelta(days=-10), now)),
        ]
    )
    app = create_app(store=store)
    with TestClient(app) as c:
        d = c.get("/api/quotes", params={"max_age_minutes": 60}).json()
        assert {q["symbol"] for q in d["quotes"]} == {"FRESH"}
