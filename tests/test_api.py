"""API behaviour tests, run against a throwaway store with synthetic data.

Nothing here uses the network. Synthetic fixtures are clearly labelled by their
``source`` field and never mixed with real records.
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

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
            "source": "github.com/Aabishkar2/nepse-data",
            "retrieved_at": RETRIEVED,
            "validation_status": "valid",
        }
    )


@pytest.fixture
def client(tmp_path, monkeypatch):
    store = MarketStore(tmp_path / "market.duckdb")
    n = 120
    store.upsert_bars(_bars("TEST1", 100.0 + np.arange(n)))
    store.upsert_bars(_bars("TEST2", 200.0 - np.arange(n)))

    app = create_app(store=store)
    with TestClient(app) as c:
        yield c
    store.close()


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    d = r.json()
    assert d["status"] == "ok"
    assert d["market_db_open"] is True
    assert d["bars_stored"] == 240
    assert "does not place trades" in d["disclaimer"]


def test_status_never_claims_live_data(client):
    d = client.get("/api/status").json()
    assert d["live_feed_connected"] is False
    assert d["data_as_of"] is not None
    assert "no live NEPSE feed" in d["note"]


def test_dashboard_marks_itself_not_live(client):
    d = client.get("/api/dashboard").json()
    assert d["is_live"] is False
    assert d["data_as_of"]
    assert d["breadth"]["advancers"] + d["breadth"]["decliners"] == d["symbols"]
    assert "not a live feed" in d["note"]


def test_securities_search(client):
    d = client.get("/api/securities", params={"q": "test1"}).json()
    assert d["count"] == 1
    assert d["securities"][0]["symbol"] == "TEST1"
    assert d["securities"][0]["bars"] == 120


def test_bars_returns_sorted_history(client):
    d = client.get("/api/bars/TEST1").json()
    assert d["count"] == 120
    times = [b["time"] for b in d["bars"]]
    assert times == sorted(times)
    assert d["sources"] == ["github.com/Aabishkar2/nepse-data"]
    assert d["adjustment_status"] == ["unadjusted"]


def test_bars_404_for_unknown_symbol(client):
    r = client.get("/api/bars/NOSUCH")
    assert r.status_code == 404


def test_bars_limit_returns_most_recent_window(client):
    # "limit" is the charting-terminal meaning: the last N bars. It previously
    # returned the OLDEST N, which made every chart range show decade-old data.
    d = client.get("/api/bars/TEST1", params={"limit": 5}).json()
    assert d["count"] == 5
    assert d["bars"][-1]["time"] == "2026-06-17"  # newest window, still ascending
    times = [b["time"] for b in d["bars"]]
    assert times == sorted(times)
    assert d["last_date"] == "2026-06-17"
    assert d["first_date"] != "2026-01-01"  # not the head of history


def test_indicator_endpoint_shape(client):
    d = client.get("/api/bars/TEST1/indicator", params={"name": "rsi"}).json()
    assert d["indicator"] == "rsi"
    assert len(d["dates"]) == 120
    assert len(d["series"]["rsi"]) == 120
    assert d["series"]["rsi"][0] is None  # warm-up is null, never filled
    assert d["series"]["rsi"][-1] is not None
    assert d["output_warmup"]["rsi"] == 14


def test_indicator_unknown_name_is_404(client):
    r = client.get("/api/bars/TEST1/indicator", params={"name": "not_real"})
    assert r.status_code == 404


def test_indicator_rejects_bad_params(client):
    r = client.get("/api/bars/TEST1/indicator", params={"name": "sma", "params": '{"period": 0}'})
    assert r.status_code == 400
    assert "must be > 0" in r.json()["detail"]


def test_indicator_rejects_malformed_params_json(client):
    r = client.get("/api/bars/TEST1/indicator", params={"name": "sma", "params": "not json"})
    assert r.status_code == 400
    assert "not valid JSON" in r.json()["detail"]


def test_indicator_accepts_param_overrides(client):
    d = client.get(
        "/api/bars/TEST1/indicator",
        params={"name": "sma", "params": '{"period": 10}'},
    ).json()
    assert d["params"]["period"] == 10
    assert d["output_warmup"]["sma"] == 9
    assert d["series"]["sma"][8] is None
    assert d["series"]["sma"][9] is not None


def test_screen_pass_and_explanations(client):
    tree = {
        "op": "AND",
        "conditions": [{"metric": "return_20d", "operator": "gt", "value": 0}],
    }
    d = client.post("/api/screen", json={"tree": tree}).json()
    assert d["passed"] == 1  # TEST1 rises, TEST2 falls
    assert d["rendered"] == "return_20d > 0"
    winner = next(r for r in d["results"] if r["passed"])
    assert winner["reasons"] and "-> actual" in winner["reasons"][0]


def test_screen_rejects_unknown_metric_with_400(client):
    tree = {"op": "AND", "conditions": [{"metric": "nope", "operator": "lt", "value": 1}]}
    r = client.post("/api/screen", json={"tree": tree})
    assert r.status_code == 400
    assert "unknown metric" in r.json()["detail"]


def test_screen_rejects_malformed_tree(client):
    r = client.post("/api/screen", json={"tree": {"op": "XOR", "conditions": []}})
    assert r.status_code == 400


def test_screen_presets_all_runnable(client):
    presets = client.get("/api/screen/presets").json()["presets"]
    assert presets
    for p in presets:
        r = client.post("/api/screen", json={"tree": p["tree"]})
        assert r.status_code == 200, f"{p['key']} failed: {r.text}"
        assert r.json()["evaluated"] == 2


def test_screen_csv_export(client):
    tree = {"op": "AND", "conditions": [{"metric": "bars_listed", "operator": "gte", "value": 1}]}
    r = client.get("/api/screen/export.csv", params={"tree": json.dumps(tree)})
    assert r.status_code == 200
    assert "text/csv" in r.headers["content-type"]
    assert "symbol,eligible,passed" in r.text
    assert "TEST1" in r.text and "TEST2" in r.text


def test_quality_endpoint_reports_flags(client):
    d = client.get("/api/quality", params={"symbol": "TEST1"}).json()
    assert d["symbols_checked"] == 1
    rep = d["reports"][0]
    assert rep["symbol"] == "TEST1"
    assert rep["rows_checked"] == 120
    assert rep["clean"] is True


def test_portfolio_empty_is_explicit(client):
    d = client.get("/api/portfolio").json()
    assert d["positions"] == []
    assert "No positions recorded" in d["note"]


def test_sources_lists_both_and_flags_official_blocked(client):
    d = client.get("/api/sources").json()
    labels = [s["label"] for s in d["sources"]]
    assert any("GitHub" in x for x in labels)
    official = next(s for s in d["sources"] if "Official" in s["label"])
    assert official["requires_auth"] is True
    assert official["available"] is False


def test_indicators_catalog_has_metadata(client):
    d = client.get("/api/indicators").json()
    assert len(d["indicators"]) >= 25
    rsi = next(i for i in d["indicators"] if i["name"] == "rsi")
    assert rsi["reference"] and rsi["formula"]
    assert rsi["output_warmup"] == {"rsi": 14}
    # Multi-output indicators must expose a warm-up for every output, not just
    # the slowest one, so a chart pane can tell when its line becomes valid.
    macd = next(i for i in d["indicators"] if i["name"] == "macd")
    assert set(macd["output_warmup"]) == {"macd", "signal", "histogram"}
    assert macd["output_warmup"]["macd"] < macd["output_warmup"]["signal"]
    assert "close_vs_sma" in d["metrics"]


def test_ui_is_served(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "Mega Tool" in r.text
    assert "Lightweight Charts" in r.text  # attribution present


# ---------------------------------------------------------------- backtest
def test_strategies_catalog_states_defaults_and_disclaimer(client):
    d = client.get("/api/strategies").json()
    keys = {s["key"] for s in d["strategies"]}
    assert {"sma_cross", "rsi_threshold", "always_in"} <= keys
    for s in d["strategies"]:
        assert s["label"] and s["description"] and isinstance(s["params"], dict)
    assert "not predictions" in d["note"]


def test_backtest_returns_metrics_curve_and_assumptions(client):
    d = client.post(
        "/api/backtest",
        json={"symbol": "TEST1", "strategy": "sma_cross", "params": {"fast": 5, "slow": 20}},
    ).json()
    assert d["symbol"] == "TEST1"
    assert d["live"] is False
    assert d["data_as_of"] == "2026-06-17"
    assert len(d["equity"]) == 120
    assert d["equity"][0]["date"] <= d["equity"][-1]["date"]
    for key in ("total_return_pct", "max_drawdown_pct", "final_equity", "exposure_pct"):
        assert key in d["metrics"], key
    joined = " ".join(d["assumptions"])
    assert "PLACEHOLDER" in joined
    assert "UNADJUSTED" in joined
    assert "Past performance" in joined
    assert d["note"]


def test_backtest_never_reports_live_data(client):
    d = client.post("/api/backtest", json={"symbol": "TEST1", "strategy": "always_in"}).json()
    assert d["live"] is False
    assert d["start"] and d["end"]


def test_backtest_unknown_symbol_is_404(client):
    r = client.post("/api/backtest", json={"symbol": "NOSUCH", "strategy": "always_in"})
    assert r.status_code == 404


def test_backtest_unknown_strategy_is_400(client):
    r = client.post("/api/backtest", json={"symbol": "TEST1", "strategy": "moon_phases"})
    assert r.status_code == 400
    assert "unknown strategy" in r.json()["detail"]


def test_backtest_rejects_shorting_request(client):
    # shorting is deliberately unsupported; the model exposes no field for it
    d = client.post("/api/backtest", json={"symbol": "TEST1", "strategy": "always_in"}).json()
    assert d["config"]["allow_short"] is False


def test_backtest_rejects_bad_execution_mode(client):
    r = client.post(
        "/api/backtest",
        json={"symbol": "TEST1", "strategy": "always_in", "execution": "whenever"},
    )
    assert r.status_code == 400
    assert "execution" in r.json()["detail"]


def test_backtest_rejects_unknown_param(client):
    r = client.post(
        "/api/backtest",
        json={"symbol": "TEST1", "strategy": "sma_cross", "params": {"fast": 5, "banana": 1}},
    )
    assert r.status_code == 400
    assert "unknown parameter" in r.json()["detail"]


def test_backtest_benchmark_is_reported_alongside(client):
    d = client.post("/api/backtest", json={"symbol": "TEST2", "strategy": "always_in"}).json()
    m = d["metrics"]
    assert m["benchmark_total_return_pct"] is not None
    # TEST2 declines monotonically, so buy-and-hold must be negative
    assert m["benchmark_total_return_pct"] < 0
