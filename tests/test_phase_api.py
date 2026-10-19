"""API-surface tests for the mission Phase B-E endpoints.

Uses the in-process TestClient with a synthetic store and the isolated app
database, so no server and no real data are involved.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from megatool import catalog
from megatool.api import create_app
from megatool.db import init_app_db
from megatool.market_store import MarketStore

RETRIEVED = pd.Timestamp("2026-10-16 08:00:00")


def _bars(symbol: str, closes: np.ndarray) -> pd.DataFrame:
    dates = pd.bdate_range("2026-01-01", periods=len(closes))
    return pd.DataFrame({
        "symbol": symbol, "trading_date": dates, "open": closes, "high": closes * 1.01,
        "low": closes * 0.99, "close": closes,
        "volume": np.full(len(closes), 2_000, dtype="int64"), "turnover": closes * 2_000,
        "percent_change": 0.0, "source": "synthetic-test", "retrieved_at": RETRIEVED,
        "validation_status": "valid", "adjustment_status": "unadjusted",
    })


@pytest.fixture(autouse=True)
def _reset_provider():
    catalog.set_store_provider(None)
    yield
    catalog.set_store_provider(None)


@pytest.fixture
def client(tmp_path, monkeypatch):
    store = MarketStore(tmp_path / "phase_api.duckdb")
    rng = np.random.default_rng(77)
    for name, base in (("TEST1", 100.0), ("TEST2", 220.0)):
        store.upsert_bars(_bars(name, base * np.exp(np.cumsum(rng.normal(0.0004, 0.012, size=320)))))
    monkeypatch.setattr(catalog, "_store", lambda: store)
    init_app_db()
    app = create_app(store=store)
    with TestClient(app) as c:
        yield c
    store.close()


# --------------------------------------------------------------------------- #
# Reconciliation
# --------------------------------------------------------------------------- #

def test_reconciliation_datasets_endpoint(client):
    d = client.get("/api/reconciliation/datasets").json()
    names = {x["dataset"] for x in d["datasets"]}
    assert {"price_bars", "fundamentals"} <= names


def test_reconciliation_profile_and_run(client):
    prof = client.get("/api/reconciliation/profile", params={"dataset": "price_bars"}).json()
    assert prof["rows"] == 640
    run = client.post("/api/reconciliation/run", json={"dataset": "price_bars"}).json()
    assert run["dataset"] == "price_bars"
    assert "disclaimer" in run


def test_reconciliation_unknown_dataset_is_400(client):
    r = client.post("/api/reconciliation/run", json={"dataset": "nope"})
    assert r.status_code == 400


def test_reconciliation_resolve_and_history(client):
    run = client.post("/api/reconciliation/run", json={"dataset": "fundamentals"}).json()
    assert run["findings"] == 0
    rec = client.post("/api/reconciliation/resolve", json={
        "dataset": "fundamentals", "finding_key": "manual:1", "classification": "conflict",
        "resolution": "left_open", "note": "watching",
    }).json()
    assert rec["resolution"] == "left_open"
    hist = client.get("/api/reconciliation/history", params={"dataset": "fundamentals"}).json()
    assert hist["runs"] and hist["resolutions"]


def test_reconciliation_resolve_validation_is_400(client):
    r = client.post("/api/reconciliation/resolve", json={
        "dataset": "fundamentals", "finding_key": "x", "resolution": "accepted"})
    assert r.status_code == 400


# --------------------------------------------------------------------------- #
# Snapshots
# --------------------------------------------------------------------------- #

def test_snapshot_capture_get_rerun_compare(client):
    cap = client.post("/api/snapshots/capture",
                      json={"feature": "technical_rating", "params": {"symbol": "TEST1"}})
    assert cap.status_code == 200
    snap = cap.json()
    assert snap["reproducibility"] in ("fully_reproducible", "partially_reproducible")
    got = client.get(f"/api/snapshots/{snap['id']}")
    assert got.status_code == 200 and got.json()["id"] == snap["id"]
    rerun = client.post(f"/api/snapshots/{snap['id']}/rerun").json()
    assert rerun["reproduced"] is True
    cap2 = client.post("/api/snapshots/capture",
                       json={"feature": "monte_carlo", "params": {"paths": 50, "seed": 2}}).json()
    diff = client.get("/api/snapshots/compare", params={"a": snap["id"], "b": cap2["id"]}).json()
    assert diff["same_feature"] is False
    assert client.get("/api/snapshots").json()["snapshots"]


def test_snapshot_create_and_missing_id_404(client):
    created = client.post("/api/snapshots", json={
        "feature": "demo", "params": {"symbol": "TEST1"}, "results": {"x": 1},
        "required": ["price_bars"], "missing": []}).json()
    assert created["reproducibility"] == "fully_reproducible"
    assert client.get("/api/snapshots/does-not-exist").status_code == 404
    assert client.post("/api/snapshots/does-not-exist/rerun").status_code == 404


def test_snapshot_capture_unknown_feature_is_400(client):
    r = client.post("/api/snapshots/capture", json={"feature": "not_a_fn", "params": {}})
    assert r.status_code == 400


# --------------------------------------------------------------------------- #
# Research desk
# --------------------------------------------------------------------------- #

def test_research_evidence_endpoint(client):
    d = client.get("/api/research-desk/evidence", params={"symbol": "TEST1"}).json()
    assert d["symbol"] == "TEST1"
    assert d["items"]
    assert "disclaimer" in d


def test_research_run_without_provider_returns_evidence(client):
    d = client.post("/api/research-desk/run",
                    json={"question": "Is TEST1 expensive?", "symbol": "TEST1"}).json()
    assert d["available"] is False
    assert d["error"]
    assert d["evidence"]["items"]


def test_research_review_endpoint_flags_overclaim(client):
    d = client.post("/api/research-desk/review", json={
        "text": "This will definitely double, guaranteed.", "symbol": "TEST1"}).json()
    assert d["review"]["verdict"] in ("needs_review", "unsupported")
    assert d["evidence"]["symbol"] == "TEST1"


def test_research_history_endpoint(client):
    client.post("/api/research-desk/run", json={"question": "q", "symbol": "TEST1"})
    assert client.get("/api/research-desk/history").json()["runs"]


# --------------------------------------------------------------------------- #
# Natural-language query
# --------------------------------------------------------------------------- #

def test_query_endpoint_supported(client):
    d = client.post("/api/query/run", json={"question": "price of TEST1"}).json()
    assert d["status"] == "ok"
    assert d["rows"][0]["symbol"] == "TEST1"
    assert "disclaimer" in d


def test_query_endpoint_rejects_injection(client):
    d = client.post("/api/query/run",
                    json={"question": "'; DROP TABLE securities; --"}).json()
    assert d["status"] == "rejected"
    # The securities table is still queryable.
    assert client.get("/api/query/history").status_code == 200


def test_query_history_endpoint(client):
    client.post("/api/query/run", json={"question": "how many securities"})
    assert client.get("/api/query/history").json()["runs"]


# --------------------------------------------------------------------------- #
# Fundamentals revisions & point-in-time
# --------------------------------------------------------------------------- #

def test_fundamentals_revisions_endpoint(client):
    d = client.get("/api/fundamentals/revisions").json()
    assert d["status"] in ("ok", "no_revisions_recorded")
    assert "coverage" in d


def test_fundamentals_as_of_endpoint(client):
    d = client.get("/api/fundamentals/as-of",
                   params={"symbol": "TEST1", "as_of": "2026-12-01"}).json()
    assert d["row_count"] == 0
    assert d["coverage"]["knowledge_time"].startswith("retrieved_at")


def test_fundamentals_symbol_route_is_not_shadowed(client):
    d = client.get("/api/fundamentals/TEST1").json()
    assert d["symbol"] == "TEST1"
    assert "records" in d
