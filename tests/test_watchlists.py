"""Watchlist storage + API tests (directive M1 §8.2, Phase 2).

Two layers:

* the storage module (:mod:`megatool.watchlists`) against an isolated SQLite
  file, checking validation, ordering, and de-duplication;
* the HTTP routes against a synthetic market store, checking that a symbol with
  no stored bar is reported as **missing**, never as a fabricated zero.

All data is synthetic; the owner's real databases are never touched.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

import megatool.watchlists as wl
from megatool.api import create_app
from megatool.market_store import MarketStore

RETRIEVED = pd.Timestamp("2026-10-11 00:00:00")


@pytest.fixture(autouse=True)
def _init_schema(db_path):
    """Create the app schema in the isolated SQLite file for the storage tests."""
    from megatool.db import init_app_db

    init_app_db(db_path)
    return db_path


# ------------------------------------------------------------------ storage
def test_create_list_get_delete_roundtrip(db_path):
    created = wl.create_watchlist("Core", ["NABIL", "SCB"], db_path=db_path)
    assert created["symbols"] == ["NABIL", "SCB"]
    assert created["count"] == 2

    listed = wl.list_watchlists(db_path=db_path)
    assert [w["name"] for w in listed] == ["Core"]

    got = wl.get_watchlist("Core", db_path=db_path)
    assert got["symbols"] == ["NABIL", "SCB"]

    assert wl.delete_watchlist("Core", db_path=db_path) is True
    assert wl.delete_watchlist("Core", db_path=db_path) is False
    assert wl.list_watchlists(db_path=db_path) == []


def test_symbols_are_upper_cased_deduped_and_ordered(db_path):
    w = wl.create_watchlist("Mix", "nabil, scb, NABIL ,  HIDCL", db_path=db_path)
    assert w["symbols"] == ["NABIL", "SCB", "HIDCL"]


def test_malformed_symbol_is_rejected_not_dropped(db_path):
    with pytest.raises(wl.WatchlistError):
        wl.create_watchlist("Bad", ["NABIL", "not a symbol"], db_path=db_path)
    # a rejected create must leave nothing behind
    assert wl.list_watchlists(db_path=db_path) == []


def test_blank_and_duplicate_names_are_rejected(db_path):
    with pytest.raises(wl.WatchlistError):
        wl.create_watchlist("   ", ["NABIL"], db_path=db_path)
    wl.create_watchlist("Core", ["NABIL"], db_path=db_path)
    with pytest.raises(wl.WatchlistError):
        wl.create_watchlist("Core", ["SCB"], db_path=db_path)


def test_update_add_remove_replace_and_rename(db_path):
    wl.create_watchlist("Core", ["NABIL"], db_path=db_path)

    added = wl.update_watchlist("Core", add=["SCB"], db_path=db_path)
    assert added["symbols"] == ["NABIL", "SCB"]

    removed = wl.update_watchlist("Core", remove=["NABIL"], db_path=db_path)
    assert removed["symbols"] == ["SCB"]

    replaced = wl.update_watchlist("Core", symbols=["HIDCL", "NTC"], db_path=db_path)
    assert replaced["symbols"] == ["HIDCL", "NTC"]

    renamed = wl.update_watchlist("Core", new_name="Watch 2", db_path=db_path)
    assert renamed["name"] == "Watch 2"
    assert [w["name"] for w in wl.list_watchlists(db_path=db_path)] == ["Watch 2"]


def test_update_allows_explicit_clear(db_path):
    wl.create_watchlist("Core", ["NABIL"], db_path=db_path)
    cleared = wl.update_watchlist("Core", symbols=[], db_path=db_path)
    assert cleared["symbols"] == []


def test_get_missing_watchlist_raises(db_path):
    with pytest.raises(wl.WatchlistError):
        wl.get_watchlist("nope", db_path=db_path)


# ---------------------------------------------------------------------- API
def _bars(symbol: str, closes: np.ndarray) -> pd.DataFrame:
    dates = pd.bdate_range("2026-01-01", periods=len(closes))
    vol = np.full(len(closes), 10_000, dtype=np.int64)
    return pd.DataFrame(
        {
            "symbol": symbol,
            "trading_date": dates,
            "open": closes,
            "high": closes * 1.02,
            "low": closes * 0.98,
            "close": closes,
            "volume": vol,
            "turnover": closes * vol,
            "percent_change": 1.0,
            "source": "synthetic-watchlist-fixture",
            "retrieved_at": RETRIEVED,
            "validation_status": "valid",
        }
    )


@pytest.fixture
def client(tmp_path):
    store = MarketStore(tmp_path / "market.duckdb")
    n = 30
    store.upsert_bars(_bars("TEST1", 100.0 + np.arange(n)))
    app = create_app(store=store)
    with TestClient(app) as c:
        yield c
    store.close()


def test_api_create_and_list(client):
    r = client.post("/api/watchlists", json={"name": "Mine", "symbols": ["TEST1", "MISSING"]})
    assert r.status_code == 200
    assert r.json()["symbols"] == ["TEST1", "MISSING"]

    listed = client.get("/api/watchlists").json()
    assert listed["count"] == 1
    assert listed["watchlists"][0]["name"] == "Mine"


def test_api_detail_enriches_present_and_flags_missing(client):
    client.post("/api/watchlists", json={"name": "Mine", "symbols": ["TEST1", "MISSING"]})
    d = client.get("/api/watchlists/Mine").json()
    rows = {r["symbol"]: r for r in d["rows"]}

    # present symbol: a real close and the bar's date
    assert rows["TEST1"]["close"] is not None
    assert rows["TEST1"]["data_as_of"]

    # missing symbol: null close, and an explicit reason - never a fake 0
    assert rows["MISSING"]["close"] is None
    assert rows["MISSING"]["data_as_of"] is None
    assert "no stored bar" in rows["MISSING"]["note"]


def test_api_patch_add_and_delete(client):
    client.post("/api/watchlists", json={"name": "Mine", "symbols": ["TEST1"]})
    r = client.patch("/api/watchlists/Mine", json={"add": ["TEST2"]})
    assert r.json()["symbols"] == ["TEST1", "TEST2"]

    assert client.delete("/api/watchlists/Mine").status_code == 200
    assert client.get("/api/watchlists").json()["count"] == 0


def test_api_patch_rename(client):
    client.post("/api/watchlists", json={"name": "Mine", "symbols": ["TEST1"]})
    r = client.patch("/api/watchlists/Mine", json={"new_name": "Yours"})
    assert r.json()["name"] == "Yours"
    assert client.get("/api/watchlists/Yours").status_code == 200


def test_api_missing_watchlist_is_404(client):
    assert client.get("/api/watchlists/nope").status_code == 404
    assert client.delete("/api/watchlists/nope").status_code == 404


def test_api_duplicate_name_is_400(client):
    client.post("/api/watchlists", json={"name": "Mine", "symbols": []})
    r = client.post("/api/watchlists", json={"name": "Mine", "symbols": []})
    assert r.status_code == 400


def test_api_malformed_symbol_is_400(client):
    r = client.post("/api/watchlists", json={"name": "Mine", "symbols": ["bad sym"]})
    assert r.status_code == 400


def test_watchlists_are_not_friend_facing():
    from megatool.friend_access import friend_allowed

    assert friend_allowed("GET", "/api/watchlists") is False
    assert friend_allowed("POST", "/api/watchlists") is False
