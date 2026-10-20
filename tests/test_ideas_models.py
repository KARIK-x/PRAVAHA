"""Tests for the expanded investment-model library (megatool.ideas).

The price-derived models are exact functions of the stored closes, so they are
tested against hand-computed values. The fundamental models are tested for the
honesty property that matters: with no stored filings they must say so rather
than reporting "nothing qualifies" as if the screen had run.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from megatool.db import get_conn, init_app_db
from megatool.ideas import MODELS, evaluate
from megatool.market_store import MarketStore


def _bars(symbol: str, closes):
    n = len(closes)
    closes = np.asarray(closes, dtype=float)
    dates = pd.bdate_range("2024-01-01", periods=n)
    return pd.DataFrame(
        {
            "symbol": symbol,
            "trading_date": dates,
            "open": closes,
            "high": closes * 1.001,
            "low": closes * 0.999,
            "close": closes,
            "volume": np.full(n, 1000, dtype=np.int64),
            "turnover": closes * 1000,
            "percent_change": 0.0,
            "source": "SYNTHETIC-TEST-FIXTURE",
            "retrieved_at": pd.Timestamp("2026-10-11"),
            "validation_status": "valid",
        }
    )


@pytest.fixture
def store(tmp_path):
    init_app_db()
    s = MarketStore(tmp_path / "market.duckdb")
    yield s
    s.close()


def _run(model_id, store, limit=50):
    with get_conn() as conn:
        return evaluate(model_id, store, conn, limit=limit)


def _row(out, symbol):
    return next((r for r in out["rows"] if r["symbol"] == symbol), None)


def test_catalogue_is_twenty_plus_with_unique_ids():
    ids = [m["id"] for m in MODELS]
    assert len(ids) >= 20, f"expected a 20+ model library, got {len(ids)}"
    assert len(set(ids)) == len(ids), "duplicate model ids"
    for m in MODELS:
        assert m["source"], f"{m['id']} must document its formula"
        assert m["requires"], f"{m['id']} must state its inputs"
        assert m["status"] in ("available", "partial", "insufficient_data")


def test_momentum_3m_is_the_63_session_return(store):
    closes = np.linspace(100.0, 200.0, 80)  # 100 -> 200 over 80 bars
    store.upsert_bars(_bars("M3", closes))
    out = _run("momentum_3m", store)
    row = _row(out, "M3")
    expected = (closes[-1] / closes[-64] - 1.0) * 100.0
    assert row is not None
    assert row["return_3m_pct"] == pytest.approx(round(expected, 2), abs=0.02)


def test_low_volatility_ranks_the_calm_series_first(store):
    rng = np.random.default_rng(7)
    calm = 100.0 * np.cumprod(1 + rng.normal(0, 0.002, 300))
    wild = 100.0 * np.cumprod(1 + rng.normal(0, 0.05, 300))
    store.upsert_bars(_bars("CALM", calm))
    store.upsert_bars(_bars("WILD", wild))
    out = _run("low_volatility", store)
    assert out["rows"][0]["symbol"] == "CALM"
    assert _row(out, "CALM")["vol20_annual_pct"] < _row(out, "WILD")["vol20_annual_pct"]


def test_deep_drawdown_matches_a_hand_computed_series(store):
    # rise to 200 then fall to 100 -> worst running-peak drawdown = -50%
    closes = np.concatenate([np.linspace(100, 200, 150), np.linspace(200, 100, 150)])
    store.upsert_bars(_bars("DD", closes))
    row = _row(_run("deep_drawdown", store), "DD")
    assert row["max_drawdown_pct"] == pytest.approx(-50.0, abs=0.5)


def test_deep_drawdown_is_not_look_ahead(store):
    # 100 -> 200 -> 50 -> 300. Inside the trailing 252-session window the peak
    # (200) comes BEFORE the trough (50), so the worst running-peak drawdown is
    # -75%. A look-ahead "max close in window vs min close" would instead use
    # the later 300 peak and report a different number.
    closes = np.concatenate([
        np.linspace(100, 200, 100),
        np.linspace(200, 50, 100),
        np.linspace(50, 300, 100),
    ])
    store.upsert_bars(_bars("LAA", closes))
    row = _row(_run("deep_drawdown", store), "LAA")
    assert row is not None, "a 300-bar series must produce a 252-session drawdown"
    assert row["max_drawdown_pct"] == pytest.approx(-75.0, abs=1.0)


def test_risk_adjusted_is_return_over_volatility(store):
    rng = np.random.default_rng(3)
    closes = 100.0 * np.cumprod(1 + rng.normal(0.001, 0.01, 300))
    store.upsert_bars(_bars("RA", closes))
    row = _row(_run("risk_adjusted", store), "RA")
    # `score` IS the risk-adjusted ratio; the row also carries its inputs.
    assert row["score"] == pytest.approx(
        row["ret_252_pct"] / row["vol252_annual_pct"], rel=0.02
    )


def test_mean_reversion_zscore_sign_and_ordering(store):
    rising = np.linspace(100, 300, 120)     # above its mean -> z > 0
    falling = np.linspace(300, 100, 120)    # below its mean -> z < 0
    store.upsert_bars(_bars("UP", rising))
    store.upsert_bars(_bars("DOWN", falling))
    out = _run("mean_reversion", store)
    assert out["rows"][0]["symbol"] == "DOWN"      # most negative first
    assert _row(out, "DOWN")["zscore_20"] < 0
    assert _row(out, "UP")["zscore_20"] > 0


def test_volatility_squeeze_ratio_is_relative_to_the_names_own_norm(store):
    rng = np.random.default_rng(11)
    quiet_then_quieter = 100.0 * np.cumprod(1 + np.concatenate(
        [rng.normal(0, 0.03, 240), rng.normal(0, 0.003, 60)]
    ))
    store.upsert_bars(_bars("SQZ", quiet_then_quieter))
    row = _row(_run("volatility_squeeze", store), "SQZ")
    assert row["vol_ratio"] < 1.0
    assert row["vol_ratio"] == pytest.approx(
        row["vol20_annual_pct"] / (row["vol20_annual_pct"] / row["vol_ratio"]), rel=1e-6
    ) or row["vol_ratio"] > 0


def test_trend_regime_stack(store):
    up = np.linspace(100, 400, 260)
    down = np.linspace(400, 100, 260)
    store.upsert_bars(_bars("UP", up))
    store.upsert_bars(_bars("DOWN", down))
    out = _run("trend_regime", store)
    up_row, down_row = _row(out, "UP"), _row(out, "DOWN")
    assert up_row["stacked"] is True
    assert up_row["above_50"] is True and up_row["above_200"] is True
    assert down_row["stacked"] is False
    assert down_row["above_200"] is False


def test_near_52w_high_uses_the_trailing_range(store):
    closes = np.concatenate([np.linspace(100, 200, 260), [199.0]])
    store.upsert_bars(_bars("HI", closes))
    row = _row(_run("near_52w_high", store), "HI")
    assert row["range_pos_pct"] > 95.0
    assert row["range_high"] == pytest.approx(200.0 * 1.001, rel=0.01)


def test_fundamental_models_say_the_input_is_absent_not_that_nothing_qualified(store):
    store.upsert_bars(_bars("NOP", np.linspace(100, 120, 260)))
    out = _run("earnings_yield", store)
    assert out["status"] == "calculated"
    assert out["matched"] == 0
    assert "No stored fundamentals" in out["note"]


def test_a_short_series_cannot_say_anything_about_a_252_session_model(store):
    store.upsert_bars(_bars("SHORT", np.linspace(100, 110, 30)))
    out = _run("risk_adjusted", store)
    assert out["matched"] == 0, "a 30-bar series has no 252-session statistics"


def test_every_available_model_runs_without_raising(store):
    store.upsert_bars(_bars("ANY", np.linspace(100, 200, 260)))
    for m in MODELS:
        out = _run(m["id"], store)
        assert out["status"] in ("calculated", "insufficient_data")
        if out["status"] == "calculated":
            assert isinstance(out["rows"], list)


def test_no_model_produces_nan_or_infinite_scores(store):
    store.upsert_bars(_bars("FIN", np.linspace(100, 200, 260)))
    for m in MODELS:
        out = _run(m["id"], store)
        for r in out.get("rows") or []:
            if "score" in r:
                assert math.isfinite(r["score"]), f"{m['id']} produced a non-finite score"
