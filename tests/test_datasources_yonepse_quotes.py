"""YONEPSE market-live conversion tests (synthetic).

These pin the validation rules: a quote with no timestamp is dropped (freshness
cannot be asserted), a missing price is NULL+``missing`` (not a valid zero), a
non-positive or non-finite price is NULL+``invalid``, and every row carries the
source timestamp plus the observation time.
"""

from __future__ import annotations

from datetime import UTC, datetime

from megatool.datasources.yonepse import (
    market_live_to_quote_rows,
    market_status_summary,
)

NOW = datetime(2026, 10, 15, 14, 0, 0, tzinfo=UTC)


def _rec(**kw) -> dict:
    base = {
        "symbol": "AAA",
        "name": "Alpha Ltd",
        "ltp": 100.0,
        "previous_close": 99.0,
        "high": 102.0,
        "low": 98.0,
        "change": 1.0,
        "percent_change": 1.01,
        "volume": 500,
        "turnover": 50000.0,
        "trades": 5,
        "market_cap": 1e9,
        "last_updated": "2026-10-12T14:59:59.986662",
    }
    base.update(kw)
    return base


def test_valid_record_converts():
    rows, stats = market_live_to_quote_rows([_rec()], retrieved_at=NOW)
    assert stats["rows_out"] == 1 and stats["records_in"] == 1
    r = rows[0]
    assert r["symbol"] == "AAA"
    assert r["quote_date"] == "2026-10-12"
    assert r["ltp"] == 100.0
    assert r["validation_status"] == "valid"
    assert r["source_updated_at"] == "2026-10-12T14:59:59"
    assert r["retrieved_at"] == "2026-10-15T14:00:00"
    assert r["source"] == "yonepse/market/live.json"


def test_blank_symbol_rejected():
    rows, stats = market_live_to_quote_rows([_rec(symbol="  ")], retrieved_at=NOW)
    assert rows == [] and stats["no_symbol"] == 1


def test_missing_timestamp_rejected():
    rows, stats = market_live_to_quote_rows([_rec(last_updated=None)], retrieved_at=NOW)
    assert rows == [] and stats["missing_timestamp"] == 1


def test_missing_ltp_is_null_not_zero():
    rows, stats = market_live_to_quote_rows([_rec(ltp=None)], retrieved_at=NOW)
    assert rows[0]["ltp"] is None
    assert rows[0]["validation_status"] == "missing"
    assert stats["missing_ltp"] == 1


def test_non_positive_ltp_is_invalid():
    rows, _ = market_live_to_quote_rows([_rec(ltp=0)], retrieved_at=NOW)
    assert rows[0]["ltp"] is None
    assert rows[0]["validation_status"] == "invalid"


def test_non_finite_values_become_null():
    rows, _ = market_live_to_quote_rows(
        [_rec(turnover=float("inf"), market_cap=float("nan"))], retrieved_at=NOW
    )
    assert rows[0]["turnover"] is None
    assert rows[0]["market_cap"] is None


def test_high_below_low_is_suspect():
    rows, stats = market_live_to_quote_rows([_rec(high=90.0, low=99.0)], retrieved_at=NOW)
    assert rows[0]["validation_status"] == "suspect"
    assert stats["suspect"] == 1


def test_status_summary_does_not_assert_liveness():
    s = market_status_summary({"is_open": False, "last_checked": "2026-10-12T10:17:11.259676"})
    assert s["is_open"] is False
    assert s["last_checked"] == "2026-10-12T10:17:11.259676"
    assert "not the time of this request" in s["note"]
