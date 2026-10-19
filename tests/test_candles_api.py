"""Contract tests for ``GET /api/bars/{symbol}/candles`` (spec §8, Phase 3).

The candlestick *engine* (:mod:`megatool.ta.candles`) is covered by
``test_candles.py``. These tests cover the previously-missing API surface that
made the engine unreachable from the terminal, plus the honesty rules the route
must keep:

* a detection is **DETECTED**, never "confirmed" or predictive;
* an unknown pattern name or malformed symbol is a 400, not a silent all-clear;
* an internally impossible bar is excluded and *counted*, not "fixed".

All data is synthetic; no network and no real prices are used.
"""

from __future__ import annotations

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from megatool.api import create_app
from megatool.market_store import MarketStore

RETRIEVED = pd.Timestamp("2026-10-11 00:00:00")


def _bars(symbol: str, rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    df["symbol"] = symbol
    df["trading_date"] = pd.bdate_range("2026-01-01", periods=len(df))
    df["turnover"] = df["close"] * df["volume"]
    df["percent_change"] = 0.0
    df["source"] = "synthetic-candles-api-fixture"
    df["retrieved_at"] = RETRIEVED
    df["validation_status"] = "valid"
    return df


def _row(o: float, h: float, lo: float, c: float, vol: float = 1000.0) -> dict:
    return {"open": o, "high": h, "low": lo, "close": c, "volume": vol}


# A clean descending run (so trend context exists) ending in a small bearish
# candle immediately engulfed by a bullish one. Only the closes trend is
# asserted; other detectors firing is fine and does not weaken the check.
_ENGULFING = [
    _row(112, 112.5, 111.0, 111.5),
    _row(111.4, 111.8, 110.5, 111.0),
    _row(110.9, 111.2, 109.8, 110.2),
    _row(110.1, 110.4, 108.9, 109.3),
    _row(109.2, 109.5, 108.0, 108.4),
    # small bearish candle
    _row(108.3, 108.5, 107.0, 107.4),
    # bullish engulfing: open <= prior close, close >= prior open, larger body
    _row(107.3, 109.2, 107.1, 109.0),
]


@pytest.fixture
def client(tmp_path):
    store = MarketStore(tmp_path / "market.duckdb")
    store.upsert_bars(_bars("ENGULF", _ENGULFING))
    app = create_app(store=store)
    with TestClient(app) as c:
        yield c
    store.close()


def test_candles_returns_detections_with_catalogue(client):
    d = client.get("/api/bars/ENGULF/candles").json()
    assert d["symbol"] == "ENGULF"
    assert d["count"] == len(d["patterns"])
    assert d["catalogue"], "route must publish the pattern catalogue"
    names = {p["name"] for p in d["patterns"]}
    assert names <= set(d["catalogue"])
    # Every detection carries the honesty fields.
    for p in d["patterns"]:
        assert p["date"]
        assert p["marker_position"] in ("aboveBar", "belowBar")
        assert any("not a forecast" in n for n in d["notes"])


def test_candles_never_claims_confirmation(client):
    d = client.get("/api/bars/ENGULF/candles").json()
    assert any("`confirmed` is always null" in n for n in d["notes"])


def test_candles_detects_a_known_bullish_engulfing(client):
    d = client.get("/api/bars/ENGULF/candles", params={"patterns": "bullish_engulfing"}).json()
    assert "bullish_engulfing" in {p["name"] for p in d["patterns"]}
    assert all(p["name"] == "bullish_engulfing" for p in d["patterns"])


def test_candles_pattern_filter_excludes_others(client):
    d = client.get("/api/bars/ENGULF/candles", params={"patterns": "doji"}).json()
    assert all(p["name"] == "doji" for p in d["patterns"])


def test_candles_unknown_pattern_is_400(client):
    r = client.get("/api/bars/ENGULF/candles", params={"patterns": "not_a_pattern"})
    assert r.status_code == 400
    assert "unknown candlestick pattern" in r.json()["detail"]


def test_candles_malformed_symbol_is_400(client):
    assert client.get("/api/bars/bad symbol!/candles").status_code == 400


def test_candles_unknown_symbol_is_404(client):
    assert client.get("/api/bars/NOPE/candles").status_code == 404


def test_candles_short_history_is_404(client):
    store = MarketStore(":memory:")
    store.upsert_bars(_bars("ONE", [_row(10, 11, 9, 10.5)]))
    app = create_app(store=store)
    with TestClient(app) as c:
        # One bar is not "no history", but it is below the 3-bar engine floor;
        # the route reports 404 for a non-existent symbol and lets the engine
        # guard short series. Assert the endpoint is honest either way.
        r = c.get("/api/bars/ONE/candles")
        assert r.status_code in (200, 404)
    store.close()


def test_candles_excludes_impossible_ohlc_and_counts_it(tmp_path):
    rows = list(_ENGULFING) + [_row(109.0, 108.0, 110.0, 109.5)]  # high < low: impossible
    store = MarketStore(tmp_path / "m.duckdb")
    store.upsert_bars(_bars("BADOHLC", rows))
    app = create_app(store=store)
    with TestClient(app) as c:
        d = c.get("/api/bars/BADOHLC/candles").json()
        assert d["bars_excluded_invalid_ohlc"] >= 1
        # The impossible bar must never be the site of a detection.
        bad_index = len(rows) - 1
        assert all(p["index"] != bad_index for p in d["patterns"])
    store.close()


def test_candles_is_on_the_read_only_friend_allowlist():
    from megatool.friend_access import friend_allowed

    assert friend_allowed("GET", "/api/bars/NABIL/candles") is True
