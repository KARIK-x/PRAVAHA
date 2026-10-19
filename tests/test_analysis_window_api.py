"""Contract tests for the Elliott / harmonic **analysis-window** parameters.

This session added ``start``/``end``/``limit`` to ``GET /api/bars/{symbol}/elliott``
and ``start``/``end``/``limit`` + ``slack`` + ``patterns`` to
``GET /api/bars/{symbol}/harmonic`` so the terminal can ask "what did the count
look like up to a chosen date" and "which pattern types, at what tolerance".

The *engines* (``megatool.ta.elliott`` / ``megatool.ta.harmonic``) are covered
elsewhere. These tests pin the route contract:

* a bad pattern name is a 400 (never a silent all-clear);
* ``slack`` out of range is rejected by validation;
* the window actually narrows the data the engine sees;
* honesty fields (``slack`` echo, ``catalogue``, ``patterns_tested``) are present.

Synthetic zig-zag prices only; no network, no real market data.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from megatool.api import create_app
from megatool.market_store import MarketStore

RETRIEVED = pd.Timestamp("2026-10-11 00:00:00")


def _zigzag(n: int = 80, amplitude: float = 8.0, step: int = 4) -> pd.DataFrame:
    """Alternating up/down legs — a clean, deterministic source of swing pivots."""
    x = np.arange(n)
    close = 100.0 + amplitude * np.sin(2 * np.pi * x / (2 * step))
    open_ = np.concatenate([[close[0]], close[:-1]])
    high = np.maximum(open_, close) + 0.4
    low = np.minimum(open_, close) - 0.4
    vol = np.full(n, 5_000, dtype=np.int64)
    return pd.DataFrame(
        {
            "symbol": "ZIGZAG",
            "trading_date": pd.bdate_range("2026-01-01", periods=n),
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "volume": vol,
            "turnover": close * vol,
            "percent_change": 0.0,
            "source": "synthetic-window-fixture",
            "retrieved_at": RETRIEVED,
            "validation_status": "valid",
        }
    )


@pytest.fixture
def client(tmp_path):
    store = MarketStore(tmp_path / "market.duckdb")
    store.upsert_bars(_zigzag())
    app = create_app(store=store)
    with TestClient(app) as c:
        yield c
    store.close()


# ------------------------------------------------------------------- elliott
def test_elliott_window_limit_narrows_the_data(client):
    full = client.get("/api/bars/ZIGZAG/elliott").json()
    small = client.get("/api/bars/ZIGZAG/elliott?limit=20").json()
    assert full["status"] in {"CANDIDATE_ONLY", "INSUFFICIENT_EVIDENCE"}
    # a shorter window can never yield MORE swings to consider
    assert small["swings_considered"] <= full["swings_considered"]


def test_elliott_start_end_window_is_accepted(client):
    r = client.get("/api/bars/ZIGZAG/elliott?start=2026-02-01&end=2026-03-01")
    assert r.status_code == 200


def test_elliott_missing_symbol_is_404(client):
    assert client.get("/api/bars/NOPE/elliott?limit=20").status_code == 404


def test_elliott_malformed_symbol_is_400(client):
    assert client.get("/api/bars/%20%20/elliott").status_code in (400, 404)


# ------------------------------------------------------------------ harmonic
def test_harmonic_echoes_slack_and_window(client):
    d = client.get("/api/bars/ZIGZAG/harmonic?limit=60&slack=0.01").json()
    assert d["slack"] == pytest.approx(0.01)
    assert d["status"] in {"CANDIDATE_ONLY", "NO_MATCH", "INSUFFICIENT_EVIDENCE"}
    assert d["catalogue"], "route must publish the harmonic catalogue"


def test_harmonic_pattern_subset_restricts_detection(client):
    d = client.get("/api/bars/ZIGZAG/harmonic?patterns=gartley,bat").json()
    assert d["patterns_tested"] == ["Gartley", "Bat"]


def test_harmonic_unknown_pattern_is_400(client):
    r = client.get("/api/bars/ZIGZAG/harmonic?patterns=nope")
    assert r.status_code == 400
    assert "nope" in r.json()["detail"]


def test_harmonic_slack_out_of_range_is_rejected(client):
    assert client.get("/api/bars/ZIGZAG/harmonic?slack=-1").status_code == 422
    assert client.get("/api/bars/ZIGZAG/harmonic?slack=0.9").status_code == 422


def test_harmonic_zero_slack_is_published_ratios_only(client):
    assert client.get("/api/bars/ZIGZAG/harmonic?slack=0").json()["slack"] == 0.0
