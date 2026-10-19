"""Focused tests for portfolio risk analytics (Phase 2, feature 6).

Synthetic fixtures only. The suite pins: the value-series construction against
an independent formula, hand-computed drawdown/VaR/Sharpe figures, explainable
limit breaches, explicit insufficient-data handling, and the API route.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from megatool.api import create_app
from megatool.db import init_app_db
from megatool.market_store import MarketStore
from megatool.portfolio import add_transaction
from megatool.risk import MIN_POINTS, portfolio_risk, portfolio_value_series, risk_metrics

RETRIEVED = pd.Timestamp("2026-10-11 00:00:00")


def _bars(symbol: str, closes: np.ndarray) -> pd.DataFrame:
    n = len(closes)
    return pd.DataFrame(
        {
            "symbol": symbol,
            "trading_date": pd.bdate_range("2024-01-01", periods=n),
            "open": closes,
            "high": closes * 1.02,
            "low": closes * 0.98,
            "close": closes,
            "volume": np.full(n, 10_000, dtype=np.int64),
            "turnover": closes * 10_000,
            "source": "SYNTHETIC-TEST-FIXTURE",
            "retrieved_at": RETRIEVED,
            "validation_status": "valid",
        }
    )


@pytest.fixture
def env(tmp_path):
    store = MarketStore(tmp_path / "market.duckdb")
    n = 120
    # A rises 1%/session from 100; B falls 0.5%/session from 200.
    a = 100.0 * 1.01 ** np.arange(n)
    b = 200.0 * 0.995 ** np.arange(n)
    store.upsert_bars(_bars("AAA", a))
    store.upsert_bars(_bars("BBB", b))
    app_db = tmp_path / "state.sqlite"
    init_app_db(app_db)
    add_transaction(
        {
            "symbol": "AAA",
            "side": "buy",
            "quantity": 10,
            "price": 100.0,
            "traded_at": "2024-01-02T10:00:00",
        },
        db_path=app_db,
    )
    add_transaction(
        {
            "symbol": "BBB",
            "side": "buy",
            "quantity": 5,
            "price": 200.0,
            "traded_at": "2024-01-02T10:00:00",
        },
        db_path=app_db,
    )
    yield store, app_db
    store.close()


def test_value_series_matches_independent_construction(env):
    store, app_db = env
    series, coverage = portfolio_value_series(store, app_db)
    assert series is not None
    assert coverage["contributing"] == ["AAA", "BBB"] and coverage["excluded"] == []
    # Independent construction: 10 × 100×1.01^t + 5 × 200×0.995^t
    expected = 10 * 100.0 * 1.01 ** np.arange(120) + 5 * 200.0 * 0.995 ** np.arange(120)
    assert len(series) == 120
    assert series.iloc[0] == pytest.approx(expected[0])
    assert series.iloc[-1] == pytest.approx(expected[-1])
    assert series.iloc[60] == pytest.approx(expected[60])


def test_metrics_on_a_known_series():
    value = pd.Series(
        [100.0, 110.0, 99.0, 108.0, 80.0, 90.0],
        index=pd.bdate_range("2024-01-01", periods=6),
    )
    m = risk_metrics(value)
    # peak 110 → trough 80: max drawdown -27.27%; current 90 vs peak 110: -18.18%
    assert m["max_drawdown_pct"] == pytest.approx(-27.27, abs=0.01)
    assert m["current_drawdown_pct"] == pytest.approx(-18.18, abs=0.01)
    rets = value.pct_change().dropna()
    assert m["daily_var_95_pct"] == pytest.approx(float(rets.quantile(0.05)) * 100, abs=0.01)
    assert m["daily_cvar_95_pct"] == pytest.approx(
        float(rets[rets <= rets.quantile(0.05)].mean()) * 100, abs=0.01
    )
    expected_vol = float(rets.std()) * math.sqrt(250)
    assert m["annualized_volatility_pct"] == pytest.approx(expected_vol * 100, abs=0.01)
    expected_sharpe = float(rets.mean() / rets.std() * math.sqrt(250))
    assert m["sharpe_rf0"] == pytest.approx(expected_sharpe, abs=1e-3)


def test_limits_breach_names_measured_and_threshold(env):
    store, app_db = env
    # One symbol only → weight 100% > 40% default → breach, explainably.
    report = portfolio_risk(store, db_path=app_db, limits={"max_weight_pct": 40.0})
    assert report["status"] == "ok"
    weight_breach = next(b for b in report["breaches"] if b["limit"] == "max_weight_pct")
    assert weight_breach["measured_pct"] == pytest.approx(
        100.0 * (10 * 100 * 1.01**119) / (10 * 100 * 1.01**119 + 5 * 200 * 0.995**119), abs=0.1
    )
    assert weight_breach["threshold_pct"] == 40.0
    assert "meaning" in weight_breach


def test_insufficient_data_is_explicit(env):
    store, app_db = env
    # Shrink history below MIN_POINTS by using a fresh store with few bars.
    from megatool.market_store import MarketStore as MS

    small = MS(app_db.parent / "small.duckdb")
    small.upsert_bars(_bars("AAA", 100.0 * 1.01 ** np.arange(MIN_POINTS - 5)))
    small.close()
    report = portfolio_risk(small, db_path=app_db)
    assert report["status"] == "insufficient_data"
    assert "metrics" not in report
    assert str(MIN_POINTS - 5) in report["reason"]


def test_symbol_without_history_is_excluded_not_fabricated(tmp_path):
    store = MarketStore(tmp_path / "market.duckdb")
    store.upsert_bars(_bars("AAA", 100.0 * 1.01 ** np.arange(120)))
    app_db = tmp_path / "state.sqlite"
    init_app_db(app_db)
    add_transaction(
        {
            "symbol": "AAA",
            "side": "buy",
            "quantity": 10,
            "price": 100.0,
            "traded_at": "2024-01-02T10:00:00",
        },
        db_path=app_db,
    )
    add_transaction(
        {
            "symbol": "GHOST",
            "side": "buy",
            "quantity": 5,
            "price": 50.0,
            "traded_at": "2024-01-02T10:00:00",
        },
        db_path=app_db,
    )
    series, coverage = portfolio_value_series(store, app_db)
    assert coverage["contributing"] == ["AAA"]
    assert coverage["excluded"] == ["GHOST"]
    assert series is not None  # AAA alone still yields a series
    store.close()


def test_no_positions_is_insufficient(tmp_path):
    store = MarketStore(tmp_path / "market.duckdb")
    store.upsert_bars(_bars("AAA", 100.0 * 1.01 ** np.arange(120)))
    app_db = tmp_path / "state.sqlite"
    init_app_db(app_db)
    report = portfolio_risk(store, db_path=app_db)
    assert report["status"] == "insufficient_data"
    assert "no open positions" in report["reason"]
    store.close()


# ------------------------------------------------------------------ API route
def test_risk_route_reports_metrics_and_breaches(tmp_path, monkeypatch):
    from megatool.config import Paths

    store = MarketStore(tmp_path / "market.duckdb")
    n = 120
    # AAA rises 1%/session for 80 sessions, then falls 2%/session: the
    # portfolio peaks mid-window, so both drawdown figures are negative.
    a_path = np.concatenate(
        [100.0 * 1.01 ** np.arange(80), 100.0 * 1.01**80 * 0.98 ** np.arange(1, 41)]
    )
    store.upsert_bars(_bars("AAA", a_path))
    store.upsert_bars(_bars("BBB", 200.0 * 0.995 ** np.arange(n)))
    app_db = tmp_path / "state.sqlite"
    init_app_db(app_db)
    # The route reads the app DB through PATHS; point it at this fixture.
    monkeypatch.setattr(Paths, "app_db", property(lambda self: app_db))
    add_transaction(
        {
            "symbol": "AAA",
            "side": "buy",
            "quantity": 10,
            "price": 100.0,
            "traded_at": "2024-01-02T10:00:00",
        },
        db_path=app_db,
    )
    add_transaction(
        {
            "symbol": "BBB",
            "side": "buy",
            "quantity": 5,
            "price": 200.0,
            "traded_at": "2024-01-02T10:00:00",
        },
        db_path=app_db,
    )
    app = create_app(store=store)
    with TestClient(app) as client:
        d = client.get("/api/portfolio/risk").json()
        assert d["status"] == "ok"
        assert d["metrics"]["max_drawdown_pct"] < 0
        assert d["metrics"]["sessions"] == n
        assert any(b["limit"] == "max_weight_pct" for b in d["breaches"])
        # Tightening a limit via the query parameter is honoured.
        d2 = client.get("/api/portfolio/risk", params={"max_weight_pct": 90.0}).json()
        assert all(
            b["threshold_pct"] == 90.0 for b in d2["breaches"] if b["limit"] == "max_weight_pct"
        )
    store.close()
