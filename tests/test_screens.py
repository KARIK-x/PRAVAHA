"""Saved custom screens / analytical rules (Phase 5 custom-analysis builder).

The *evaluation* engine (:mod:`megatool.scanner`) is already covered elsewhere.
These tests cover the previously-missing **persistence** layer and its HTTP
surface, and the safety property that matters most: a stored rule is only ever a
data tree, re-validated on load — never code.

Synthetic data only.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

import megatool.screens as sc
from megatool.api import create_app
from megatool.market_store import MarketStore

RETRIEVED = pd.Timestamp("2026-10-11 00:00:00")

_TREE = {
    "op": "AND",
    "conditions": [{"metric": "rsi", "operator": "lt", "value": 70.0}],
}


@pytest.fixture(autouse=True)
def _init_schema(db_path):
    from megatool.db import init_app_db

    init_app_db(db_path)
    return db_path


# ------------------------------------------------------------------ storage
def test_save_list_get_delete_roundtrip(db_path):
    saved = sc.save_screen("Oversold", _TREE, db_path=db_path)
    assert saved["name"] == "Oversold"
    assert saved["definition"]["conditions"][0]["metric"] == "rsi"
    assert "rsi" in saved["rendered"]

    listed = sc.list_screens(db_path=db_path)
    assert [s["name"] for s in listed] == ["Oversold"]
    assert listed[0]["rendered"]

    got = sc.get_screen(saved["id"], db_path=db_path)
    assert got["id"] == saved["id"]

    assert sc.delete_screen(saved["id"], db_path=db_path) is True
    assert sc.delete_screen(saved["id"], db_path=db_path) is False


def test_unknown_metric_is_rejected_at_save(db_path):
    bad = {"op": "AND", "conditions": [{"metric": "not_a_metric", "operator": "gt", "value": 1}]}
    with pytest.raises(sc.ScreenError):
        sc.save_screen("Bad", bad, db_path=db_path)
    assert sc.list_screens(db_path=db_path) == []


def test_unknown_operator_is_rejected(db_path):
    bad = {"op": "AND", "conditions": [{"metric": "rsi", "operator": "≈", "value": 1}]}
    with pytest.raises(sc.ScreenError):
        sc.save_screen("Bad", bad, db_path=db_path)


def test_blank_and_duplicate_names(db_path):
    with pytest.raises(sc.ScreenError):
        sc.save_screen("   ", _TREE, db_path=db_path)
    sc.save_screen("Dup", _TREE, db_path=db_path)
    with pytest.raises(sc.ScreenError):
        sc.save_screen("Dup", _TREE, db_path=db_path)
    # overwrite=True updates in place instead of duplicating
    updated = sc.save_screen("Dup", _TREE, overwrite=True, db_path=db_path)
    assert updated["name"] == "Dup"
    assert len(sc.list_screens(db_path=db_path)) == 1


def test_rename_replace_duplicate_and_conflict(db_path):
    a = sc.save_screen("A", _TREE, db_path=db_path)
    sc.save_screen("B", _TREE, db_path=db_path)

    renamed = sc.update_screen(a["id"], new_name="A2", db_path=db_path)
    assert renamed["name"] == "A2"

    with pytest.raises(sc.ScreenError):
        sc.update_screen(a["id"], new_name="B", db_path=db_path)

    new_tree = {"op": "OR", "conditions": [{"metric": "close", "operator": "gt", "value": 100.0}]}
    replaced = sc.update_screen(a["id"], definition=new_tree, db_path=db_path)
    assert replaced["definition"]["op"] == "OR"

    copy = sc.duplicate_screen(a["id"], "A2 copy", db_path=db_path)
    assert copy["name"] == "A2 copy"
    assert copy["definition"] == replaced["definition"]


def test_get_missing_screen_raises(db_path):
    with pytest.raises(sc.ScreenError):
        sc.get_screen(999, db_path=db_path)


def test_nested_and_or_tree_roundtrips(db_path):
    tree = {
        "op": "AND",
        "children": [
            {
                "op": "OR",
                "conditions": [
                    {"metric": "rsi", "operator": "lt", "value": 30},
                    {"metric": "close", "operator": "lt", "value": 200},
                ],
            },
            {"op": "AND", "conditions": [{"metric": "volume", "operator": "gt", "value": 1000}]},
        ],
    }
    saved = sc.save_screen("Nested", tree, db_path=db_path)
    got = sc.get_screen(saved["id"], db_path=db_path)
    assert "OR" in got["rendered"] and "AND" in got["rendered"]


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
            "source": "synthetic-screens-fixture",
            "retrieved_at": RETRIEVED,
            "validation_status": "valid",
        }
    )


@pytest.fixture
def client(tmp_path):
    store = MarketStore(tmp_path / "market.duckdb")
    store.upsert_bars(_bars("UP", 100.0 + np.arange(120)))
    store.upsert_bars(_bars("DOWN", 200.0 - np.arange(120)))
    app = create_app(store=store)
    with TestClient(app) as c:
        yield c
    store.close()


def test_api_save_list_get_delete(client):
    saved = client.post("/api/screens", json={"name": "R1", "definition": _TREE})
    assert saved.status_code == 200, saved.text
    sid = saved.json()["id"]

    listed = client.get("/api/screens").json()
    assert listed["count"] == 1
    assert "rsi" in listed["metrics"]  # catalogue embedded for the UI

    got = client.get(f"/api/screens/{sid}").json()
    assert got["definition"]["conditions"][0]["metric"] == "rsi"

    assert client.delete(f"/api/screens/{sid}").status_code == 200
    assert client.get(f"/api/screens/{sid}").status_code == 404


def test_api_saved_rule_runs_against_real_data(client):
    # close > 150 selects only "UP" (latest close 219); "DOWN" closes at 81.
    tree = {"op": "AND", "conditions": [{"metric": "close", "operator": "gt", "value": 150.0}]}
    client.post("/api/screens", json={"name": "Above150", "definition": tree})

    # reload the saved definition and execute it through the EXISTING screen route
    reloaded = client.get("/api/screens").json()["screens"][0]["definition"]
    run = client.post("/api/screen", json={"tree": reloaded})
    assert run.status_code == 200, run.text
    passed = {r["symbol"] for r in run.json()["results"] if r["passed"]}
    assert passed == {"UP"}


def test_api_rename_and_duplicate(client):
    sid = client.post("/api/screens", json={"name": "R1", "definition": _TREE}).json()["id"]
    renamed = client.patch(f"/api/screens/{sid}", json={"new_name": "R1b"})
    assert renamed.json()["name"] == "R1b"

    dup = client.post(f"/api/screens/{sid}/duplicate", json={"new_name": "R1 copy"})
    assert dup.status_code == 200
    assert dup.json()["name"] == "R1 copy"
    assert client.get("/api/screens").json()["count"] == 2


def test_api_bad_metric_is_400(client):
    bad = {
        "name": "Bad",
        "definition": {
            "op": "AND",
            "conditions": [{"metric": "nope", "operator": "gt", "value": 1}],
        },
    }
    assert client.post("/api/screens", json=bad).status_code == 400


def test_api_missing_screen_is_404(client):
    assert client.get("/api/screens/424242").status_code == 404
    assert client.delete("/api/screens/424242").status_code == 404
    assert client.patch("/api/screens/424242", json={"new_name": "x"}).status_code == 404


def test_saved_screens_are_not_friend_facing():
    from megatool.friend_access import friend_allowed

    assert friend_allowed("GET", "/api/screens") is False
    assert friend_allowed("POST", "/api/screens") is False


# ------------------------------------------------- assistant rule proposal
# The chat assistant's "propose rule" action is a *deterministic grammar*, not
# a model and not generated code. These tests pin that: the output is a data
# tree that re-validates, unmappable clauses are reported with a reason, and
# the endpoint never runs a screen.
def test_propose_route_returns_validated_tree(client):
    r = client.post("/api/screens/propose", json={"question": "rsi below 30 and price above 200"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["operator"] == "AND"
    assert body["tree"]["op"] == "AND"
    metrics = {c["metric"] for c in body["tree"]["conditions"]}
    assert metrics == {"rsi", "close"}
    assert body["unmatched"] == []
    # The proposal must itself be a runnable, valid tree.
    run = client.post("/api/screen", json={"tree": body["tree"]})
    assert run.status_code == 200, run.text


def test_propose_route_or_operator(client):
    r = client.post("/api/screens/propose", json={"question": "rsi below 30 or adx above 40"})
    assert r.status_code == 200, r.text
    assert r.json()["tree"]["op"] == "OR"


def test_propose_route_reports_unmappable_clause(client):
    r = client.post("/api/screens/propose", json={"question": "pe below 10 and rsi under 40"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert [c["metric"] for c in body["tree"]["conditions"]] == ["rsi"]
    assert body["unmatched"], "an unmappable clause must be reported, never dropped silently"
    assert "P/E" in body["unmatched"][0]["reason"]


def test_propose_route_unusable_question_is_400(client):
    r = client.post("/api/screens/propose", json={"question": "relative strength above 1.2"})
    assert r.status_code == 400
    assert "relative strength" in r.json()["detail"].lower()


def test_propose_route_rejects_empty_question(client):
    assert client.post("/api/screens/propose", json={"question": ""}).status_code == 422


def test_propose_is_not_friend_facing():
    from megatool.friend_access import friend_allowed

    assert friend_allowed("POST", "/api/screens/propose") is False


def test_parse_question_is_pure_and_needs_no_store():
    from megatool.rule_parse import parse_question

    out = parse_question("volume above its average, adx above 25")
    assert {c["metric"] for c in out["tree"]["conditions"]} == {"volume_sma_ratio", "adx"}
    assert "deterministic" in out["basis"]
