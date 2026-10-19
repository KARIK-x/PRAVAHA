"""Reproducible calculation-snapshot tests (mission Phase C / NF-014).

Synthetic prices only. The suite checks that a snapshot records what it claims,
that reproducibility is *classified* rather than asserted, that secrets are never
persisted, and that a rerun either reproduces byte-for-byte or says plainly why
it could not.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from megatool import catalog, snapshots
from megatool.db import get_conn, init_app_db
from megatool.market_store import MarketStore

RETRIEVED = pd.Timestamp("2026-10-16 08:00:00")


@pytest.fixture(autouse=True)
def _reset_provider():
    catalog.set_store_provider(None)
    yield
    catalog.set_store_provider(None)


def _bars(symbol: str, closes: np.ndarray) -> pd.DataFrame:
    dates = pd.bdate_range("2026-01-01", periods=len(closes))
    return pd.DataFrame({
        "symbol": symbol,
        "trading_date": dates,
        "open": closes,
        "high": closes * 1.01,
        "low": closes * 0.99,
        "close": closes,
        "volume": np.full(len(closes), 1_000, dtype=np.int64),
        "turnover": closes * 1_000,
        "percent_change": 0.1,
        "source": "synthetic-test",
        "retrieved_at": RETRIEVED,
        "validation_status": "valid",
    })


@pytest.fixture
def store(tmp_path):
    s = MarketStore(tmp_path / "snap_market.duckdb")
    rng = np.random.default_rng(5)
    for name, base in (("SYN1", 100.0), ("SYN2", 120.0)):
        s.upsert_bars(_bars(name, base * np.exp(np.cumsum(rng.normal(0.0005, 0.011, size=300)))))
    yield s
    s.close()


@pytest.fixture(autouse=True)
def _schema():
    init_app_db()


# --------------------------------------------------------------------------- #
# Capture
# --------------------------------------------------------------------------- #

def test_capture_runs_the_real_engine_and_records_metadata(store):
    snap = snapshots.capture("technical_rating", {"symbol": "SYN1"}, store=store)
    assert snap["id"].startswith("snap-")
    assert snap["feature"] == "technical_rating"
    assert snap["data_cutoff"], "a store-backed snapshot must record its data cutoff"
    assert snap["source_ids"] == ["synthetic-test"]
    assert snap["date_range"]
    assert snap["methodology"]["name"]
    assert snap["code_version"]
    assert snap["reproducibility"] == "fully_reproducible"
    assert snap["results"], "the engine result must be stored, not a placeholder"


def test_capture_classifies_missing_benchmark_as_partial(store):
    # stress_test needs the index series too; this store has none.
    snap = snapshots.capture("stress_test", {"symbols": ["SYN1", "SYN2"]}, store=store)
    assert snap["reproducibility"] == "partially_reproducible"
    assert "index_series" in snap["missing_inputs"]


def test_capture_classifies_absent_history_as_unrecoverable(store):
    snap = snapshots.capture("technical_rating", {"symbol": "NO_SUCH_SYMBOL"}, store=store)
    assert snap["reproducibility"] == "unrecoverable"
    assert "price_bars" in snap["missing_inputs"]


def test_pure_calculation_records_params_and_seed(store):
    snap = snapshots.capture(
        "monte_carlo",
        {"start": 100.0, "drift": 0.08, "volatility": 0.25, "days": 30, "paths": 100, "seed": 42},
        store=store,
    )
    assert snap["seed"] == "42"
    assert snap["params"]["seed"] == 42
    assert snap["reproducibility"] == "fully_reproducible"


# --------------------------------------------------------------------------- #
# Secrets and hashing
# --------------------------------------------------------------------------- #

def test_secrets_are_never_persisted(store):
    # The secret-looking keys are dropped *before* the engine is called, so the
    # call still succeeds; that is itself the proof they never reach storage.
    snap = snapshots.capture(
        "monte_carlo",
        {"start": 100.0, "days": 10, "paths": 10, "seed": 1,
         "api_key": "SUPERSECRET", "authorization_token": "BEARER-123",
         "bearer": "xyz", "password": "hunter2"},
        store=store,
    )
    assert "api_key" not in snap["params"]
    assert "authorization_token" not in snap["params"]
    assert "bearer" not in snap["params"]
    assert "password" not in snap["params"]
    stored = snapshots.get_snapshot(snap["id"])
    blob = str(stored)
    assert "SUPERSECRET" not in blob and "BEARER-123" not in blob and "hunter2" not in blob
    # A benign parameter whose name merely contains 'key' as a substring survives.
    kept = snapshots.create(feature="demo", params={"monkey_rank": 3}, results={"ok": True})
    assert kept["params"] == {"monkey_rank": 3}


def test_input_hash_is_deterministic_and_param_sensitive(store):
    a = snapshots.capture("monte_carlo", {"start": 100.0, "days": 10, "paths": 10, "seed": 3}, store=store)
    b = snapshots.capture("monte_carlo", {"start": 100.0, "days": 10, "paths": 10, "seed": 3}, store=store)
    c = snapshots.capture("monte_carlo", {"start": 100.0, "days": 10, "paths": 10, "seed": 4}, store=store)
    assert a["input_hash"] == b["input_hash"]
    assert a["input_hash"] != c["input_hash"]
    assert a["results_hash"] == b["results_hash"], "same seed must reproduce the same result"
    assert a["results_hash"] != c["results_hash"]


# --------------------------------------------------------------------------- #
# Retrieval, rerun, comparison
# --------------------------------------------------------------------------- #

def test_get_and_list(store):
    a = snapshots.capture("technical_rating", {"symbol": "SYN1"}, store=store)
    b = snapshots.capture("technical_rating", {"symbol": "SYN2"}, store=store)
    assert snapshots.get_snapshot(a["id"])["id"] == a["id"]
    assert snapshots.get_snapshot("does-not-exist") is None
    listed = snapshots.list_snapshots(feature="technical_rating")
    assert {x["id"] for x in listed} >= {a["id"], b["id"]}


def test_rerun_reproduces_deterministically(store):
    snap = snapshots.capture("technical_rating", {"symbol": "SYN1"}, store=store)
    out = snapshots.rerun(snap["id"], store=store)
    assert out["reproduced"] is True
    assert out["stored_hash"] == out["fresh_hash"]


def test_rerun_refuses_when_inputs_are_gone(store):
    snap = snapshots.capture("technical_rating", {"symbol": "MISSING"}, store=store)
    assert snap["reproducibility"] == "unrecoverable"
    out = snapshots.rerun(snap["id"], store=store)
    assert out["reproduced"] is False
    assert "unrecoverable" in out["reason"]


def test_compare_reports_param_and_result_differences(store):
    a = snapshots.capture("monte_carlo", {"start": 100.0, "days": 10, "paths": 10, "seed": 1}, store=store)
    b = snapshots.capture("monte_carlo", {"start": 100.0, "days": 20, "paths": 10, "seed": 1}, store=store)
    diff = snapshots.compare(a["id"], b["id"])
    assert diff["same_feature"] is True
    assert diff["same_input_hash"] is False
    assert "days" in diff["param_diff"]
    assert diff["result_diff"], "a changed horizon should change the result"


def test_compare_detects_a_version_difference(store):
    a = snapshots.capture("monte_carlo", {"start": 100.0, "days": 10, "paths": 10, "seed": 1}, store=store)
    b = snapshots.capture("monte_carlo", {"start": 100.0, "days": 10, "paths": 10, "seed": 1}, store=store)
    with get_conn() as conn:
        conn.execute("UPDATE calculation_snapshots SET code_version = '0.0.0' WHERE id = ?", (b["id"],))
    diff = snapshots.compare(a["id"], b["id"])
    assert "code_version" in diff["meta_diff"]
    assert diff["meta_diff"]["code_version"]["b"] == "0.0.0"


def test_compare_requires_both_snapshots(store):
    a = snapshots.capture("technical_rating", {"symbol": "SYN1"}, store=store)
    with pytest.raises(ValueError):
        snapshots.compare(a["id"], "nope")


def test_classify_is_honest_about_no_inputs():
    assert snapshots.classify([], []) == "fully_reproducible"
    assert snapshots.classify(["price_bars"], []) == "fully_reproducible"
    assert snapshots.classify(["price_bars", "index_series"], ["index_series"]) == "partially_reproducible"
    assert snapshots.classify(["price_bars"], ["price_bars"]) == "unrecoverable"


def test_create_accepts_explicit_results_without_running_an_engine():
    snap = snapshots.create(
        feature="backtest:demo",
        params={"symbol": "SYN1", "strategy": "sma_cross"},
        results={"total_return": 0.12, "trades": 7},
        universe="SYN1", date_range="2026-01-01..2026-06-01",
        required=["price_bars"], missing=[],
        benchmark="NEPSE", costs="0.004", seed="",
    )
    assert snap["reproducibility"] == "fully_reproducible"
    assert snap["benchmark"] == "NEPSE"
    assert snapshots.get_snapshot(snap["id"])["results"]["trades"] == 7


def test_snapshot_ids_are_unique(store):
    ids = {snapshots.capture("technical_rating", {"symbol": "SYN1"}, store=store)["id"] for _ in range(5)}
    assert len(ids) == 5
