"""Reproducible-experiment storage + API tests (directive M4 §11.5, Phase 4).

The mandate is not merely to *save* a run but to be able to **reproduce** it and
**compare** it honestly. These tests pin:

* the config hash is deterministic and sensitive to every parameter;
* a saved experiment round-trips its config and result;
* ``reproduce`` re-runs through the same backtest path and reports every metric
  as unchanged;
* ``compare`` reports a real delta when a parameter changes (it never claims two
  different runs are identical);
* Markdown export carries the hash and data cut-off.

Synthetic data only.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

import megatool.experiments as ex
from megatool.api import create_app
from megatool.market_store import MarketStore

RETRIEVED = pd.Timestamp("2026-10-11 00:00:00")


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
            "source": "synthetic-experiments-fixture",
            "retrieved_at": RETRIEVED,
            "validation_status": "valid",
        }
    )


@pytest.fixture
def client(tmp_path):
    store = MarketStore(tmp_path / "market.duckdb")
    n = 260
    up = 100.0 * np.exp(np.cumsum(np.sin(np.arange(n) / 9.0) * 0.01 + 0.001))
    store.upsert_bars(_bars("WAVE", up))
    app = create_app(store=store)
    with TestClient(app) as c:
        yield c
    store.close()


def _config(**over):
    cfg = {"symbol": "WAVE", "strategy": "sma_cross", "params": {"fast": 5, "slow": 20}}
    cfg.update(over)
    return cfg


# --------------------------------------------------------------- hashing
def test_config_hash_is_deterministic_and_sensitive():
    a = _config()
    b = dict(a)
    assert ex.config_hash(a) == ex.config_hash(b)

    c = _config(params={"fast": 6, "slow": 20})
    assert ex.config_hash(a) != ex.config_hash(c)


def test_config_hash_ignores_key_order():
    a = {"symbol": "WAVE", "strategy": "sma_cross", "params": {"fast": 5, "slow": 20}}
    b = {"strategy": "sma_cross", "params": {"slow": 20, "fast": 5}, "symbol": "WAVE"}
    assert ex.config_hash(a) == ex.config_hash(b)


def test_save_rejects_a_config_without_symbol_or_strategy(db_path):
    with pytest.raises(ex.ExperimentError):
        ex.save_experiment("x", {"symbol": "WAVE"}, {}, db_path=db_path)


# ------------------------------------------------------------------- API
def _backtest(client, **over):
    r = client.post("/api/backtest", json=_config(**over))
    assert r.status_code == 200, r.text
    return r.json()


def test_backtest_then_save_list_get(client):
    result = _backtest(client)
    cfg = _config()
    saved = client.post(
        "/api/experiments", json={"label": "first", "config": cfg, "result": result}
    )
    assert saved.status_code == 200, saved.text
    eid = saved.json()["id"]
    assert saved.json()["config_hash"] == ex.config_hash(cfg)

    listed = client.get("/api/experiments").json()
    assert listed["count"] == 1
    assert listed["experiments"][0]["label"] == "first"

    got = client.get(f"/api/experiments/{eid}").json()
    assert got["config"]["symbol"] == "WAVE"
    assert got["result"]["metrics"]["final_equity"] == result["metrics"]["final_equity"]
    assert got["parameter_changes"]  # non-empty: lists the knobs the run carried


def test_reproduce_reports_no_change_for_the_same_config(client):
    result = _backtest(client)
    eid = client.post(
        "/api/experiments", json={"label": "first", "config": _config(), "result": result}
    ).json()["id"]

    rep = client.post(f"/api/experiments/{eid}/reproduce").json()
    assert rep["experiment"] == eid
    assert rep["comparison"]["identical_config"] is True
    changed = [m for m in rep["comparison"]["metrics"] if not m["same"]]
    assert changed == [], f"reproduction diverged: {changed}"


def test_compare_reports_a_real_delta(client):
    slow = _backtest(client)
    fast = _backtest(client, params={"fast": 10, "slow": 40})
    a = client.post(
        "/api/experiments", json={"label": "f5s20", "config": _config(), "result": slow}
    ).json()
    b = client.post(
        "/api/experiments",
        json={
            "label": "f10s40",
            "config": _config(params={"fast": 10, "slow": 40}),
            "result": fast,
        },
    ).json()

    cmp = client.get("/api/experiments/compare", params={"a": a["id"], "b": b["id"]}).json()
    assert cmp["identical_config"] is False
    assert any(not m["same"] for m in cmp["metrics"])
    # the config hash of the two saved runs is genuinely different
    assert a["config_hash"] != b["config_hash"]


def test_export_markdown_carries_hash_and_cutoff(client):
    result = _backtest(client)
    eid = client.post(
        "/api/experiments", json={"label": "first", "config": _config(), "result": result}
    ).json()["id"]

    md = client.get(f"/api/experiments/{eid}/export", params={"format": "markdown"})
    assert md.status_code == 200
    assert md.headers["content-type"].startswith("text/markdown")
    assert "# Experiment" in md.text
    assert "Config hash" in md.text
    assert result["data_as_of"] in md.text

    js = client.get(f"/api/experiments/{eid}/export", params={"format": "json"}).json()
    assert js["id"] == eid


def test_delete_experiment(client):
    result = _backtest(client)
    eid = client.post(
        "/api/experiments", json={"label": "first", "config": _config(), "result": result}
    ).json()["id"]
    assert client.delete(f"/api/experiments/{eid}").status_code == 200
    assert client.get(f"/api/experiments/{eid}").status_code == 404


def test_get_unknown_experiment_is_404(client):
    assert client.get("/api/experiments/999").status_code == 404


def test_experiments_are_not_friend_facing():
    from megatool.friend_access import friend_allowed

    assert friend_allowed("GET", "/api/experiments") is False
    assert friend_allowed("POST", "/api/experiments") is False
