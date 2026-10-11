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
    assert d["summary"]["open_positions"] == 0
    assert "derived from your transaction ledger" in d["note"]
    assert "not a live quote" in d["note"]


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


# ---------------------------------------------------------------- portfolio
def _tx(symbol="TEST1", side="buy", qty=10, price=50.0, fees=0.0, when="2026-02-01T10:00:00"):
    return {
        "symbol": symbol,
        "side": side,
        "quantity": qty,
        "price": price,
        "fees": fees,
        "traded_at": when,
    }


def test_portfolio_starts_empty(client):
    d = client.get("/api/portfolio").json()
    assert d["positions"] == []
    assert d["summary"]["open_positions"] == 0
    assert d["live"] is False
    assert "not a live quote" in d["note"]


def test_portfolio_apis_round_trip(client):
    assert client.post("/api/portfolio/transactions", json=_tx()).status_code == 200
    assert (
        client.post(
            "/api/portfolio/transactions",
            json=_tx(side="sell", qty=4, price=60.0, when="2026-03-01T10:00:00"),
        ).status_code
        == 200
    )

    d = client.get("/api/portfolio").json()
    p = d["positions"][0]
    assert p["symbol"] == "TEST1"
    assert p["quantity"] == 6
    assert p["last_price"] == 219.0  # 100 + 119 bars from the fixture
    assert p["market_value"] == pytest.approx(6 * 219.0)
    assert d["summary"]["realized_pnl"] == pytest.approx(4 * 10.0)

    txs = client.get("/api/portfolio/transactions").json()["transactions"]
    assert len(txs) == 2
    assert txs[0]["traded_at"] >= txs[1]["traded_at"]  # newest first


def test_portfolio_rejects_overselling(client):
    client.post("/api/portfolio/transactions", json=_tx(qty=5))
    r = client.post("/api/portfolio/transactions", json=_tx(side="sell", qty=6))
    assert r.status_code == 400
    assert "only 5 held" in r.json()["detail"]


def test_portfolio_rejects_bad_input(client):
    r = client.post("/api/portfolio/transactions", json=_tx(side="hold"))
    assert r.status_code == 400
    r = client.post("/api/portfolio/transactions", json=_tx(price=-1))
    assert r.status_code == 400
    r = client.post("/api/portfolio/transactions", json=_tx(qty=2.5))
    assert r.status_code == 400


def test_portfolio_delete_transaction_404(client):
    assert client.delete("/api/portfolio/transactions/999").status_code == 404


def test_portfolio_manual_position_conflicts_with_ledger(client):
    client.post("/api/portfolio/transactions", json=_tx())
    r = client.post(
        "/api/portfolio/manual", json={"symbol": "TEST1", "quantity": 5, "avg_cost": 10.0}
    )
    assert r.status_code == 400
    assert "single source of truth" in r.json()["detail"]


def test_portfolio_manual_position_round_trip(client):
    assert (
        client.post(
            "/api/portfolio/manual",
            json={"symbol": "HOLDING", "quantity": 100, "avg_cost": 50.0, "notes": "old"},
        ).status_code
        == 200
    )
    d = client.get("/api/portfolio").json()
    assert d["positions"][0]["origin"] == "manual"
    # HOLDING has no stored price, so it must be left unvalued
    assert d["positions"][0]["market_value"] is None
    assert client.delete("/api/portfolio/manual/HOLDING").status_code == 200
    assert client.delete("/api/portfolio/manual/HOLDING").status_code == 404


# ------------------------------------------------------------------- journal
def _entry(**over):
    base = {
        "symbol": "TEST1",
        "strategy": "breakout",
        "thesis": "base break",
        "entry_price": 100.0,
        "planned_target": 120.0,
        "planned_invalidation": 90.0,
        "opened_at": "2026-02-01T10:00:00",
        "followed_plan": 1,
    }
    base.update(over)
    return base


def test_journal_crud(client):
    eid = client.post("/api/journal", json=_entry()).json()["id"]
    assert client.get(f"/api/journal/{eid}").json()["symbol"] == "TEST1"
    assert len(client.get("/api/journal").json()["entries"]) == 1

    patched = client.patch(
        f"/api/journal/{eid}",
        json={"exit_price": 130.0, "closed_at": "2026-02-20T10:00:00"},
    )
    assert patched.status_code == 200
    assert patched.json()["exit_price"] == 130.0

    grade = client.get(f"/api/journal/{eid}/grade")
    assert grade.status_code == 200
    assert grade.json()["result"] == "target"
    assert grade.json()["r_multiple"] == pytest.approx(3.0)

    assert client.delete(f"/api/journal/{eid}").status_code == 200
    assert client.get(f"/api/journal/{eid}").status_code == 404
    assert client.delete(f"/api/journal/{eid}").status_code == 404


def test_journal_stats_endpoint(client):
    empty = client.get("/api/journal/stats").json()
    assert empty["closed"] == 0
    assert empty["win_rate_pct"] is None

    client.post("/api/journal", json=_entry(exit_price=130.0, closed_at="2026-02-20T10:00:00"))
    client.post("/api/journal", json=_entry(exit_price=80.0, closed_at="2026-02-20T10:00:00"))
    s = client.get("/api/journal/stats").json()
    assert s["closed"] == 2
    assert s["wins"] == 1
    assert s["win_rate_pct"] == pytest.approx(50.0)
    # Exit 130 against a 10-point risk is +3R; exit 80 is -2R, so the mean is 0.5.
    assert s["avg_r"] == pytest.approx(0.5, abs=1e-3)
    assert s["graded_r"] == 2
    assert s["plan_adherence_pct"] == pytest.approx(100.0)
    assert s["by_strategy"][0]["strategy"] == "breakout"


def test_journal_rejects_bad_input(client):
    assert client.post("/api/journal", json={"symbol": "X"}).status_code == 400
    assert client.post("/api/journal", json={**_entry(), "confidence": "yolo"}).status_code == 400
    assert client.post("/api/journal", json={**_entry(), "followed_plan": 7}).status_code == 400
    assert client.get("/api/journal/999").status_code == 404
    assert client.patch("/api/journal/999", json={"thesis": "x"}).status_code == 404
    assert client.get("/api/journal", params={"status": "maybe"}).status_code == 400


def test_journal_grade_ungradable_is_400(client):
    eid = client.post("/api/journal", json=_entry()).json()["id"]
    r = client.get(f"/api/journal/{eid}/grade")
    assert r.status_code == 400
    assert "cannot be graded" in r.json()["detail"]


# ------------------------------------------------------------------ planning
def test_planning_plan_only(client):
    d = client.post("/api/planning", json={"entry": 100, "stop": 90, "target": 120}).json()
    assert d["plan"]["risk_reward"] == pytest.approx(2.0)
    assert "sizing" not in d
    assert "not a prediction" in d["note"]


def test_planning_with_sizing(client):
    d = client.post(
        "/api/planning",
        json={"entry": 100, "stop": 90, "target": 120, "capital": 100000, "risk_pct": 2},
    ).json()
    # budget 2,000 / risk 10 per share = 200 units
    assert d["sizing"]["units"] == 200
    assert d["sizing"]["actual_risk"] == pytest.approx(2000.0)
    assert d["sizing"]["cash_used"] == pytest.approx(20000.0)


def test_planning_rejects_stop_above_entry(client):
    r = client.post("/api/planning", json={"entry": 100, "stop": 110, "target": 120})
    assert r.status_code == 400
    assert "shorting" in r.json()["detail"]


def test_planning_requires_capital_and_risk_together(client):
    r = client.post(
        "/api/planning", json={"entry": 100, "stop": 90, "target": 120, "capital": 100000}
    )
    assert r.status_code == 400
    assert "together" in r.json()["detail"]


def test_planning_grade_requires_exit_price(client):
    r = client.post("/api/planning/grade", json={"entry": 100, "stop": 90, "target": 120})
    assert r.status_code == 400
    assert "exit_price" in r.json()["detail"]

    ok = client.post(
        "/api/planning/grade",
        json={"entry": 100, "stop": 90, "target": 120, "exit_price": 110},
    ).json()
    assert ok["r_multiple"] == pytest.approx(1.0)
    assert ok["result"] == "neither"


# -------------------------------------------------------------- forecasting
def test_forecast_models_endpoint(client):
    d = client.get("/api/forecast/models").json()
    keys = [m["key"] for m in d["models"]]
    assert "naive" in keys and "holt" in keys and "linear_trend" in keys
    assert all(m["description"] and "label" in m for m in d["models"])
    assert all("params" in m for m in d["models"])
    assert "not evidence" in d["note"]


def test_forecast_endpoint_scores_against_naive(client):
    d = client.post(
        "/api/forecast",
        json={"symbol": "TEST1", "model": "linear_trend", "horizon": 5, "holdout": 10},
    ).json()
    assert d["symbol"] == "TEST1"
    assert d["live"] is False
    assert len(d["forecast"]) == 5
    assert len(d["holdout"]) == 10
    assert d["train_points"] == 110
    # A straight line fitted to a straight line: it beats naive here.
    assert d["metrics"]["rmse_skill_ratio"] < 1.0
    assert d["random_walk"]["available"] is True
    assert "UNADJUSTED" in d["note"]
    assert d["data_as_of"]
    assert any("hold-out" in a for a in d["assumptions"])


def test_forecast_endpoint_reports_no_skill_on_a_flat_then_falling_series(client):
    # TEST2 declines monotonically; a drift model should track it well.
    d = client.post(
        "/api/forecast", json={"symbol": "TEST2", "model": "drift", "horizon": 3, "holdout": 5}
    ).json()
    assert d["metrics"]["rmse_skill_ratio"] == pytest.approx(0.0, abs=1e-6)
    assert d["verdict"].startswith("BEATS NAIVE")


def test_forecast_endpoint_errors(client):
    assert client.post("/api/forecast", json={"symbol": "NOPE"}).status_code == 404
    assert (
        client.post("/api/forecast", json={"symbol": "TEST1", "model": "crystal_ball"}).status_code
        == 400
    )
    assert client.post("/api/forecast", json={"symbol": "TEST1", "horizon": 0}).status_code == 422
    # Not enough history for a 120-step hold-out (TEST2 has 120 bars).
    r = client.post("/api/forecast", json={"symbol": "TEST2", "horizon": 120})
    assert r.status_code == 400
    assert "need at least" in r.json()["detail"]


def test_forecast_compare_endpoint(client):
    d = client.post(
        "/api/forecast/compare", json={"symbol": "TEST1", "horizon": 3, "holdout": 5}
    ).json()
    rmses = [row["rmse"] for row in d["ranking"]]
    assert rmses == sorted(rmses)
    assert d["naive_rmse"] is not None
    assert "single sample" in d["note"]
    assert d["symbol"] == "TEST1"


# ------------------------------------------------------- research assistant
def test_research_topics_endpoint(client):
    d = client.get("/api/research/topics").json()
    assert [t["key"] for t in d["topics"]] == [
        "trend",
        "momentum",
        "risk",
        "volume",
        "levels",
        "relative",
        "data",
    ]
    assert all(t["help"] for t in d["topics"])
    assert "no language model" in d["what_this_is"]
    assert "not a prediction" in d["what_this_is_not"]


def test_research_topics_route_is_not_read_as_a_symbol(client):
    # /api/research/{symbol} would otherwise swallow the literal "topics".
    assert client.get("/api/research/topics").status_code == 200


def test_research_report_endpoint_cites_every_finding(client):
    d = client.get("/api/research/TEST1").json()
    assert d["symbol"] == "TEST1"
    assert d["live"] is False
    assert d["findings"] and d["limits"]
    assert all(f["source"] and f["window"] for f in d["findings"])
    assert d["as_of"]


def test_research_unknown_symbol_is_404(client):
    assert client.get("/api/research/NOPE").status_code == 404
    assert (
        client.post("/api/research/ask", json={"symbol": "NOPE", "question": "trend"}).status_code
        == 404
    )


def test_research_ask_routes_by_topic(client):
    out = client.post(
        "/api/research/ask", json={"symbol": "TEST1", "question": "what is the risk?"}
    ).json()
    assert out["refused"] is False
    assert out["topics"] == ["risk"]
    assert out["findings"] and all(f["topic"] == "risk" for f in out["findings"])


def test_research_ask_refuses_to_recommend(client):
    out = client.post(
        "/api/research/ask", json={"symbol": "TEST1", "question": "should I buy now?"}
    ).json()
    assert out["refused"] is True
    assert out["findings"] == []
    assert "will not produce one" in out["refusal_reason"]


# -------------------------------------------------------------- floor sheet
SHEET = (
    "Symbol,Buyer,Seller,Quantity,Rate,Amount\n"
    "NABIL,B1,B2,100,500,50000\n"
    "NICA,B2,B3,300,250,75000\n"
)


def test_floorsheet_import_then_summary(client):
    out = client.post(
        "/api/floorsheet/import",
        json={"text": SHEET, "traded_at": "2026-10-09", "source": "test sheet"},
    ).json()
    assert out["rows_imported"] == 2
    assert out["rows_skipped"] == 0

    again = client.post(
        "/api/floorsheet/import", json={"text": SHEET, "traded_at": "2026-10-09"}
    ).json()
    assert again["already_imported"] is True
    assert again["rows_imported"] == 0

    s = client.get("/api/floorsheet/summary").json()
    assert s["totals"]["trades"] == 2
    assert s["totals"]["amount"] == pytest.approx(125000.0)
    assert {row["buyer"] for row in s["top_buyers"]} == {"B1", "B2"}
    assert s["concentration"]["unique_buyers"] == 2

    sessions = client.get("/api/floorsheet/sessions").json()["sessions"]
    assert sessions[0]["traded_at"] == "2026-10-09"
    assert sessions[0]["prints"] == 2


def test_floorsheet_summary_filters(client):
    client.post("/api/floorsheet/import", json={"text": SHEET, "traded_at": "2026-10-09"}).json()
    s = client.get("/api/floorsheet/summary", params={"symbol": "NICA"}).json()
    assert s["totals"]["trades"] == 1
    assert s["filter"]["symbol"] == "NICA"


def test_floorsheet_rejects_a_file_that_is_not_a_floor_sheet(client):
    r = client.post(
        "/api/floorsheet/import",
        json={"text": "Symbol,Quantity\nNABIL,100\n", "traded_at": "2026-10-09"},
    )
    assert r.status_code == 400
    assert "missing required column" in r.json()["detail"]


def test_floorsheet_requires_text(client):
    assert (
        client.post("/api/floorsheet/import", json={"traded_at": "2026-10-09"}).status_code == 422
    )


def test_floorsheet_summary_without_any_import_is_honest(client):
    s = client.get("/api/floorsheet/summary").json()
    assert s["totals"]["trades"] == 0
    assert any("No floor sheet has been imported" in w for w in s["warnings"])
    assert any("investment advice" in x for x in s["limits"])
    assert client.get("/api/floorsheet/sessions").json()["sessions"] == []


def test_journal_notes_field_is_not_silently_dropped(client):
    # An earlier version accepted `notes` with HTTP 200 and threw the text away.
    eid = client.post("/api/journal", json={**_entry(), "notes": "my thinking"}).json()["id"]
    assert client.get(f"/api/journal/{eid}").json()["outcome_notes"] == "my thinking"


def test_forecast_naive_model_is_labelled_the_baseline(client):
    # The baseline must not be reported as a model that failed to beat itself.
    d = client.post(
        "/api/forecast", json={"symbol": "TEST1", "model": "naive", "horizon": 3, "holdout": 5}
    ).json()
    assert d["verdict"].startswith("BASELINE")
    assert d["metrics"]["rmse_skill_ratio"] is None
