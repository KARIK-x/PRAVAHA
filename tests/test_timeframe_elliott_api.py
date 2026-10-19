"""Regression tests for the weekly / monthly / Elliott bar endpoints.

These exercise the real ``create_app`` factory with an injected, isolated
DuckDB store (never the owner's database). They would have failed before the
repair, when the three routes were module-level, opened a second writer-mode
DuckDB connection against a hard-coded absolute path, the Elliott route passed
the ``close`` array as ``find_swings``'s positional ``left`` argument, and all
three returned a bare pandas list that ``loadChart`` cannot consume.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from megatool.api import create_app
from megatool.market_store import MarketStore

RETRIEVED = pd.Timestamp("2026-10-11 00:00:00")


def _mk_bars(symbol: str, rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows)
    df["symbol"] = symbol
    df["turnover"] = df["close"] * df["volume"]
    df["percent_change"] = 1.0
    df["source"] = "synthetic-aggregation-fixture"
    df["retrieved_at"] = RETRIEVED
    df["validation_status"] = "valid"
    return df


# A dataset whose calendar grouping is unambiguous under pandas' W-SUN weeks.
# March 2026: Mar 2 (Mon), 4 (Wed), 6 (Fri) = week A; Mar 9 (Mon), 11 (Wed) = week B.
# April 2026: Apr 6 (Mon), 8 (Wed) = week C.
_AGG_ROWS = [
    {
        "trading_date": "2026-03-02",
        "open": 100,
        "high": 105,
        "low": 98,
        "close": 103,
        "volume": 1000,
    },
    {
        "trading_date": "2026-03-04",
        "open": 103,
        "high": 108,
        "low": 101,
        "close": 107,
        "volume": 1500,
    },
    {
        "trading_date": "2026-03-06",
        "open": 107,
        "high": 110,
        "low": 104,
        "close": 109,
        "volume": 1200,
    },
    {
        "trading_date": "2026-03-09",
        "open": 109,
        "high": 112,
        "low": 106,
        "close": 111,
        "volume": 900,
    },
    {
        "trading_date": "2026-03-11",
        "open": 111,
        "high": 115,
        "low": 110,
        "close": 114,
        "volume": 1100,
    },
    {
        "trading_date": "2026-04-06",
        "open": 114,
        "high": 118,
        "low": 112,
        "close": 117,
        "volume": 800,
    },
    {
        "trading_date": "2026-04-08",
        "open": 117,
        "high": 120,
        "low": 115,
        "close": 119,
        "volume": 1000,
    },
]


@pytest.fixture
def agg_client(tmp_path):
    store = MarketStore(tmp_path / "agg.duckdb")
    store.upsert_bars(_mk_bars("AGG", _AGG_ROWS))
    app = create_app(store=store)
    with TestClient(app) as c:
        yield c
    store.close()


@pytest.fixture
def elliott_client(tmp_path):
    """A long triangle wave producing several confirmed swing points."""
    store = MarketStore(tmp_path / "elliott.duckdb")
    n, period = 160, 12
    t = np.arange(n)
    tri = np.abs(2 * ((t / period) % 1.0) - 1)  # 0..1..0 triangle
    close = 100.0 + 40.0 * tri
    dates = pd.bdate_range("2025-01-01", periods=n)
    df = pd.DataFrame(
        {
            "symbol": "ZIG",
            "trading_date": dates,
            "open": close,
            "high": close + 1.5,
            "low": close - 1.5,
            "close": close,
            "volume": np.full(n, 1000, dtype=np.int64),
        }
    )
    df["turnover"] = df["close"] * df["volume"]
    df["percent_change"] = 1.0
    df["source"] = "synthetic-elliott-fixture"
    df["retrieved_at"] = RETRIEVED
    df["validation_status"] = "valid"
    store.upsert_bars(df)
    app = create_app(store=store)
    with TestClient(app) as c:
        yield c
    store.close()


# --------------------------------------------------------------- registration
def test_routes_are_registered():
    import megatool.api as a

    paths = {getattr(r, "path", None) for r in a.app.routes}
    assert "/api/bars/{symbol}/weekly" in paths
    assert "/api/bars/{symbol}/monthly" in paths
    assert "/api/bars/{symbol}/elliott" in paths


# ------------------------------------------------------------------- weekly
def test_weekly_aggregation_expected_values(agg_client):
    r = agg_client.get("/api/bars/AGG/weekly")
    assert r.status_code == 200
    d = r.json()
    assert d["symbol"] == "AGG"
    assert d["timeframe"] == "weekly"
    assert d["count"] == 3  # three calendar weeks: Mar2, Mar9, Apr6
    bars = d["bars"]
    assert len(bars) == 3

    # Week A (Mar 2,4,6): open=first, high=max, low=min, close=last, volume=sum.
    a = bars[0]
    assert a["open"] == 100
    assert a["high"] == 110
    assert a["low"] == 98
    assert a["close"] == 109
    assert a["volume"] == 3700  # 1000+1500+1200
    assert a["time"] == "2026-03-02"  # week start

    b = bars[1]
    assert b["open"] == 109
    assert b["high"] == 115
    assert b["low"] == 106
    assert b["close"] == 114
    assert b["volume"] == 2000  # 900+1100
    assert b["time"] == "2026-03-09"

    c = bars[2]
    assert c["volume"] == 1800  # 800+1000
    assert c["time"] == "2026-04-06"


def test_weekly_envelope_matches_daily_contract(agg_client):
    """loadChart reads data.symbol/count/bars/first_date/last_date/sources."""
    d = agg_client.get("/api/bars/AGG/weekly").json()
    for key in (
        "symbol",
        "count",
        "sources",
        "first_date",
        "last_date",
        "adjustment_status",
        "bars",
    ):
        assert key in d, f"missing envelope key {key}"
    assert d["first_date"] == "2026-03-02"
    assert d["last_date"] == "2026-04-06"
    assert isinstance(d["sources"], list) and d["sources"]


# ------------------------------------------------------------------ monthly
def test_monthly_aggregation_expected_values(agg_client):
    r = agg_client.get("/api/bars/AGG/monthly")
    assert r.status_code == 200
    d = r.json()
    assert d["timeframe"] == "monthly"
    assert d["count"] == 2  # March and April
    mar, apr = d["bars"]
    # March = week A + week B
    assert mar["open"] == 100
    assert mar["high"] == 115
    assert mar["low"] == 98
    assert mar["close"] == 114
    assert mar["volume"] == 5700  # 3700 + 2000
    assert mar["time"] == "2026-03-01"  # month start
    # April = week C
    assert apr["open"] == 114
    assert apr["high"] == 120
    assert apr["low"] == 112
    assert apr["close"] == 119
    assert apr["volume"] == 1800
    assert apr["time"] == "2026-04-01"


def test_monthly_limit_returns_most_recent_periods(agg_client):
    d = agg_client.get("/api/bars/AGG/monthly?limit=1").json()
    assert d["count"] == 1
    assert d["bars"][0]["time"] == "2026-04-01"


# ------------------------------------------------------------------- errors
def test_weekly_too_long_symbol_400(agg_client):
    r = agg_client.get("/api/bars/THISISWAYTOOLONGSYMBOLXYZ/weekly")
    assert r.status_code == 400


def test_weekly_unknown_symbol_404(agg_client):
    r = agg_client.get("/api/bars/NOSUCH/weekly")
    assert r.status_code == 404


def test_monthly_unknown_symbol_404(agg_client):
    r = agg_client.get("/api/bars/NOSUCH/monthly")
    assert r.status_code == 404


# ------------------------------------------------------------------ elliott
def test_elliott_returns_candidates_not_swallowed_failure(elliott_client):
    r = elliott_client.get("/api/bars/ZIG/elliott")
    assert r.status_code == 200
    d = r.json()
    # The old route swallowed the find_swings misuse and returned "FAILED".
    assert "error" not in d
    assert d["symbol"] == "ZIG"
    assert d["status"] in {"CANDIDATE_ONLY", "INSUFFICIENT_EVIDENCE"}
    assert d["method"] == "elliott_extended_v1.0"
    assert isinstance(d["candidates"], list)
    assert d["uncertainty"]  # honest uncertainty is surfaced


def test_elliott_response_schema_is_stable(elliott_client):
    d = elliott_client.get("/api/bars/ZIG/elliott").json()
    for key in (
        "symbol",
        "status",
        "method",
        "uncertainty",
        "evidence",
        "swings_considered",
        "candidates",
    ):
        assert key in d, f"missing elliott key {key}"


def test_elliott_unknown_symbol_404(elliott_client):
    assert elliott_client.get("/api/bars/NOSUCH/elliott").status_code == 404


def test_elliott_too_long_symbol_400(elliott_client):
    assert elliott_client.get("/api/bars/THISISWAYTOOLONGSYMBOLXYZ/elliott").status_code == 400


def test_elliott_insufficient_history_404(tmp_path):
    store = MarketStore(tmp_path / "short.duckdb")
    rows = [
        {
            "trading_date": f"2026-01-0{i + 1}",
            "open": 100 + i,
            "high": 101 + i,
            "low": 99 + i,
            "close": 100 + i,
            "volume": 100,
        }
        for i in range(2)
    ]
    store.upsert_bars(_mk_bars("SHORT", rows))
    app = create_app(store=store)
    with TestClient(app) as c:
        assert c.get("/api/bars/SHORT/elliott").status_code == 404
    store.close()
