"""Focused tests for the explanatory alert engine (Phase 2, feature 9).

Synthetic fixtures only. The suite pins: condition vocabulary behaviour with
hand-computed numbers, the fire-once dedup contract (UNIQUE(alert_key,
symbol)), owner-clear re-arming, validation rejections, and the API routes.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from megatool.alerts import (
    clear_alerts,
    evaluate_conditions,
    make_alert_key,
    validate_condition,
)
from megatool.api import create_app
from megatool.db import init_app_db
from megatool.market_store import MarketStore

RETRIEVED = pd.Timestamp("2026-10-11 00:00:00")
N_BARS = 300


def _bars(symbol: str, closes: np.ndarray, volumes: np.ndarray | None = None) -> pd.DataFrame:
    n = len(closes)
    return pd.DataFrame(
        {
            "symbol": symbol,
            "trading_date": pd.bdate_range("2024-01-01", periods=n),
            "open": closes,
            "high": closes * 1.02,
            "low": closes * 0.98,
            "close": closes,
            "volume": volumes if volumes is not None else np.full(n, 10_000, dtype=np.int64),
            "turnover": closes * 10_000,
            "source": "SYNTHETIC-TEST-FIXTURE",
            "retrieved_at": RETRIEVED,
            "validation_status": "valid",
        }
    )


@pytest.fixture
def env(tmp_path):
    store = MarketStore(tmp_path / "market.duckdb")
    # Steady uptrend for ALERT1, flat for FLAT1.
    store.upsert_bars(_bars("ALERT1", 100.0 + np.arange(N_BARS, dtype=float)))
    store.upsert_bars(_bars("FLAT1", np.full(N_BARS, 50.0)))
    app_db = tmp_path / "state.sqlite"
    init_app_db(app_db)
    yield store, app_db
    store.close()


def _conn(app_db):
    import sqlite3

    return sqlite3.connect(app_db)


# --------------------------------------------------------------- condition logic
def test_price_above_fires_with_explainable_numbers(env):
    store, app_db = env
    cond = {"key": "price_above", "symbol": "ALERT1", "params": {"threshold": 250.0}}
    assert validate_condition(cond) == []
    with _conn(app_db) as conn:
        result = evaluate_conditions(store, conn, [cond])
    assert result.evaluated == 1 and len(result.fired) == 1
    alert = result.fired[0]
    assert alert.symbol == "ALERT1" and alert.condition == "price_above"
    assert "above the 250.0 threshold" in alert.message
    assert alert.value == pytest.approx(100.0 + N_BARS - 1)


def test_price_below_does_not_fire_when_false(env):
    store, app_db = env
    cond = {"key": "price_below", "symbol": "ALERT1", "params": {"threshold": 10.0}}
    with _conn(app_db) as conn:
        result = evaluate_conditions(store, conn, [cond])
    assert result.fired == [] and result.already_active == 0


def test_volume_spike_is_hand_computed(env):
    store, app_db = env
    vols = np.full(N_BARS, 10_000, dtype=np.int64)
    vols[-1] = 50_000  # 5x the 20-day median
    store.upsert_bars(_bars("VOL1", np.full(N_BARS, 100.0), volumes=vols))
    cond = {"key": "volume_spike", "symbol": "VOL1", "params": {"multiple": 3.0}}
    with _conn(app_db) as conn:
        result = evaluate_conditions(store, conn, [cond])
    assert len(result.fired) == 1
    assert "5.0×" in result.fired[0].message


def test_momentum_conditions_use_the_trailing_window(env):
    store, app_db = env
    # ALERT1 closes run 100..399: the last 60-session return is
    # 399/339 - 1 ≈ +17.7% → above +10%, not below -10%.
    above = {"key": "momentum_above", "symbol": "ALERT1", "params": {"pct": 10.0}}
    below = {"key": "momentum_below", "symbol": "ALERT1", "params": {"pct": 10.0}}
    with _conn(app_db) as conn:
        result = evaluate_conditions(store, conn, [above, below])
    assert [a.condition for a in result.fired] == ["momentum_above"]
    assert result.fired[0].value == pytest.approx(399 / 339 - 1.0)
    assert "+17.7%" in result.fired[0].message


def test_new_high_and_new_low(env):
    store, app_db = env
    high = {"key": "new_high", "symbol": "ALERT1", "params": {}}
    low = {"key": "new_low", "symbol": "ALERT1", "params": {}}
    with _conn(app_db) as conn:
        result = evaluate_conditions(store, conn, [high, low])
    # The last close is both the 250-session max and min of an uptrend's tail?
    # It is the max; the min is the window's first close → only new_high fires.
    assert [a.condition for a in result.fired] == ["new_high"]
    assert "250-session high" in result.fired[0].message


def test_unknown_condition_and_missing_params_are_rejected(env):
    store, app_db = env
    bad_key = {"key": "telepathy", "symbol": "ALERT1", "params": {}}
    no_param = {"key": "price_above", "symbol": "ALERT1", "params": {}}
    no_symbol = {"key": "price_above", "params": {"threshold": 1.0}}
    with _conn(app_db) as conn:
        result = evaluate_conditions(store, conn, [bad_key, no_param, no_symbol])
    assert result.evaluated == 0 and result.fired == []
    assert len(result.rejected) == 3
    assert any("unknown condition" in p for r in result.rejected for p in r["problems"])


def test_dedup_contract_fires_once_until_owner_clears(env):
    store, app_db = env
    cond = {"key": "price_above", "symbol": "ALERT1", "params": {"threshold": 250.0}}
    with _conn(app_db) as conn:
        first = evaluate_conditions(store, conn, [cond])
        second = evaluate_conditions(store, conn, [cond])
    assert len(first.fired) == 1
    assert second.fired == [] and second.already_active == 1
    # Owner clears → the same condition can fire again.
    with _conn(app_db) as conn:
        assert clear_alerts(conn) == 1
        third = evaluate_conditions(store, conn, [cond])
    assert len(third.fired) == 1


def test_alert_key_is_stable_per_condition_and_symbol(env):
    a = {"key": "price_above", "symbol": "alert1", "params": {"threshold": 1.0}}
    b = {"key": "price_above", "symbol": "ALERT1", "params": {"threshold": 1.0}}
    c = {"key": "price_below", "symbol": "ALERT1", "params": {"threshold": 1.0}}
    d = {"key": "price_above", "symbol": "ALERT1", "params": {"threshold": 999.0}}
    assert make_alert_key(a) == make_alert_key(b)  # case-insensitive symbol
    assert make_alert_key(a) != make_alert_key(c)  # different condition
    assert make_alert_key(a) != make_alert_key(d)  # different threshold = different alert


# ------------------------------------------------------------------ API routes
def _client(tmp_path, monkeypatch):
    store = MarketStore(tmp_path / "market.duckdb")
    closes = 100.0 + np.arange(320, dtype=float)
    for i in range(12):
        store.upsert_bars(_bars(f"S{i}", closes * (1 + i * 0.01)))
    app_db = tmp_path / "state.sqlite"
    init_app_db(app_db)
    app = create_app(store=store)
    return TestClient(app), store


def test_alerts_api_evaluate_history_clear(tmp_path, monkeypatch):
    client, store = _client(tmp_path, monkeypatch)
    try:
        conds = [
            {"key": "price_above", "symbol": "S1", "params": {"threshold": 200.0}},
            {"key": "price_above", "symbol": "S1", "params": {"threshold": 9999.0}},
            {"key": "bogus", "symbol": "S1", "params": {}},
        ]
        r = client.post("/api/alerts/evaluate", json={"conditions": conds})
        assert r.status_code == 200
        d = r.json()
        assert d["evaluated"] == 2 and len(d["fired"]) == 1 and len(d["rejected"]) == 1
        assert "not evidence of future performance" in d["disclaimer"]
        # Second evaluate: the fired one is now already_active, no duplicates.
        d2 = client.post("/api/alerts/evaluate", json={"conditions": conds}).json()
        assert d2["fired"] == [] and d2["already_active"] == 1
        # History lists the fired alert; clear re-arms.
        h = client.get("/api/alerts/history").json()
        assert len(h["alerts"]) == 1 and "above the 200.0 threshold" in h["alerts"][0]["message"]
        assert client.delete("/api/alerts/clear").json()["cleared"] == 1
        d3 = client.post("/api/alerts/evaluate", json={"conditions": conds}).json()
        assert len(d3["fired"]) == 1
    finally:
        store.close()


def test_alerts_api_rejects_empty_conditions(tmp_path, monkeypatch):
    client, store = _client(tmp_path, monkeypatch)
    try:
        r = client.post("/api/alerts/evaluate", json={"conditions": []})
        assert r.status_code == 400
    finally:
        store.close()


# --------------------------------------------- severity, cooldown, acknowledge
def test_severity_defaults_to_warning_and_is_validated(env):
    store, _app_db = env
    # Omitting severity is valid: it defaults to "warning".
    assert (
        validate_condition({"key": "price_above", "symbol": "ALERT1", "params": {"threshold": 1}})
        == []
    )
    from megatool.alerts import DEFAULT_SEVERITY, condition_severity

    assert DEFAULT_SEVERITY == "warning"
    assert condition_severity({"key": "price_above"}) == "warning"
    assert condition_severity({"key": "price_above", "severity": "bogus"}) == "warning"
    for sev in ("info", "warning", "critical"):
        assert (
            validate_condition(
                {
                    "key": "price_above",
                    "symbol": "ALERT1",
                    "params": {"threshold": 1},
                    "severity": sev,
                }
            )
            == []
        )
    bad = validate_condition(
        {"key": "price_above", "symbol": "ALERT1", "params": {"threshold": 1}, "severity": "urgent"}
    )
    assert any("severity" in p for p in bad)


def test_cooldown_minutes_must_be_a_non_negative_integer(env):
    store, _app_db = env
    for bad in (-1, 1.5, True, "5"):
        problems = validate_condition(
            {
                "key": "price_above",
                "symbol": "ALERT1",
                "params": {"threshold": 1},
                "cooldown_minutes": bad,
            }
        )
        assert any("cooldown_minutes" in p for p in problems), bad
    assert (
        validate_condition(
            {
                "key": "price_above",
                "symbol": "ALERT1",
                "params": {"threshold": 1},
                "cooldown_minutes": 0,
            }
        )
        == []
    )


def test_fired_alert_carries_its_severity(env):
    store, app_db = env
    cond = {
        "key": "price_above",
        "symbol": "ALERT1",
        "params": {"threshold": 250.0},
        "severity": "critical",
    }
    with _conn(app_db) as conn:
        res = evaluate_conditions(store, conn, [cond])
        assert len(res.fired) == 1
        assert res.fired[0].severity == "critical"
        assert res.fired[0].fire_count == 1
        rows = conn.execute("SELECT severity, fire_count FROM alert_history").fetchall()
    assert rows == [("critical", 1)]


def test_cooldown_rearms_only_after_the_interval(env):
    store, app_db = env
    cond = {
        "key": "price_above",
        "symbol": "ALERT1",
        "params": {"threshold": 250.0},
        "cooldown_minutes": 60,
    }
    t0 = pd.Timestamp("2026-01-01T00:00:00Z")
    with _conn(app_db) as conn:
        assert len(evaluate_conditions(store, conn, [cond], now=t0).fired) == 1
        # 30 minutes later: inside the cooldown, so it must not fire again.
        held = evaluate_conditions(store, conn, [cond], now=t0 + pd.Timedelta(minutes=30))
        assert held.fired == []
        assert held.already_active == 1
        # 61 minutes later: the cooldown has elapsed; it re-fires and the row is
        # updated in place (one row per condition+symbol, count incremented).
        again = evaluate_conditions(store, conn, [cond], now=t0 + pd.Timedelta(minutes=61))
        assert len(again.fired) == 1
        assert again.fired[0].fire_count == 2
        assert conn.execute("SELECT COUNT(*) FROM alert_history").fetchone()[0] == 1


def test_no_cooldown_keeps_the_once_until_cleared_contract(env):
    store, app_db = env
    cond = {"key": "price_above", "symbol": "ALERT1", "params": {"threshold": 250.0}}
    t0 = pd.Timestamp("2026-01-01T00:00:00Z")
    with _conn(app_db) as conn:
        assert len(evaluate_conditions(store, conn, [cond], now=t0).fired) == 1
        later = evaluate_conditions(store, conn, [cond], now=t0 + pd.Timedelta(days=10))
        assert later.fired == []
        assert later.already_active == 1
        assert later.cooldown_held == 0


def test_zero_cooldown_rearms_immediately(env):
    store, app_db = env
    cond = {
        "key": "price_above",
        "symbol": "ALERT1",
        "params": {"threshold": 250.0},
        "cooldown_minutes": 0,
    }
    t0 = pd.Timestamp("2026-01-01T00:00:00Z")
    with _conn(app_db) as conn:
        evaluate_conditions(store, conn, [cond], now=t0)
        second = evaluate_conditions(store, conn, [cond], now=t0)
        assert len(second.fired) == 1
        assert second.fired[0].fire_count == 2


def test_corrupt_timestamp_suppresses_rather_than_spams(env):
    from megatool.alerts import cooldown_elapsed

    assert cooldown_elapsed(None, 60) is True
    assert cooldown_elapsed("not-a-date", 60) is False
    assert cooldown_elapsed("not-a-date", None) is False


def test_acknowledge_marks_rows_without_deleting_or_rearming(env):
    from megatool.alerts import acknowledge_alerts, list_alerts

    store, app_db = env
    cond = {"key": "price_above", "symbol": "ALERT1", "params": {"threshold": 250.0}}
    with _conn(app_db) as conn:
        evaluate_conditions(store, conn, [cond])
        listed = list_alerts(conn)
        assert listed[0]["acknowledged"] is False
        assert acknowledge_alerts(conn, alert_ids=[listed[0]["id"]]) == 1
        after = list_alerts(conn)
        assert after[0]["acknowledged"] is True
        assert after[0]["acknowledged_at"]
        # Idempotent: a second ack of the same row changes nothing.
        assert acknowledge_alerts(conn, alert_ids=[after[0]["id"]]) == 0
        # History is intact and the alert has NOT re-armed.
        assert len(list_alerts(conn)) == 1
        assert evaluate_conditions(store, conn, [cond]).already_active == 1


def test_acknowledge_all_and_api_route(tmp_path, monkeypatch):
    client, store = _client(tmp_path, monkeypatch)
    try:
        conds = [
            {"key": "price_above", "symbol": "S1", "params": {"threshold": 200.0}},
            {"key": "price_above", "symbol": "S2", "params": {"threshold": 200.0}},
        ]
        assert (
            len(client.post("/api/alerts/evaluate", json={"conditions": conds}).json()["fired"])
            == 2
        )
        bad = client.post("/api/alerts/acknowledge", json={})
        assert bad.status_code == 400
        bad2 = client.post("/api/alerts/acknowledge", json={"alert_ids": ["nope"]})
        assert bad2.status_code == 400
        ids = [a["id"] for a in client.get("/api/alerts/history").json()["alerts"]]
        one = client.post("/api/alerts/acknowledge", json={"alert_ids": ids[:1]}).json()
        assert one["acknowledged"] == 1
        rest = client.post("/api/alerts/acknowledge", json={"all": True}).json()
        assert rest["acknowledged"] == 1
        history = client.get("/api/alerts/history").json()["alerts"]
        assert all(a["acknowledged"] for a in history)
        # New columns are present in the history contract.
        assert {"id", "severity", "fire_count", "acknowledged", "acknowledged_at"} <= set(
            history[0]
        )
    finally:
        store.close()


def test_alert_history_route_counts_fires_across_cooldowns(tmp_path, monkeypatch):
    client, store = _client(tmp_path, monkeypatch)
    try:
        cond = {
            "key": "price_above",
            "symbol": "S1",
            "params": {"threshold": 200.0},
            "cooldown_minutes": 0,
        }
        client.post("/api/alerts/evaluate", json={"conditions": [cond]})
        d = client.post("/api/alerts/evaluate", json={"conditions": [cond]}).json()
        assert d["fired"][0]["fire_count"] == 2
        assert d["cooldown_held"] == 1
        history = client.get("/api/alerts/history").json()["alerts"]
        assert len(history) == 1 and history[0]["fire_count"] == 2
    finally:
        store.close()
