"""API contract tests for the chart-pattern and statistics endpoints.

Fixtures are synthetic price paths with hand-placed pivots; nothing here is
evidence about real NEPSE prices.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from fastapi.testclient import TestClient

from megatool.api import create_app
from megatool.market_store import MarketStore


def _bars(symbol: str, closes: np.ndarray) -> pd.DataFrame:
    dates = pd.bdate_range("2025-01-01", periods=len(closes))
    vol = np.full(len(closes), 10_000.0)
    return pd.DataFrame(
        {
            "symbol": symbol,
            "trading_date": dates,
            "open": closes,
            "high": closes * 1.005,
            "low": closes * 0.995,
            "close": closes,
            "volume": vol.astype(np.int64),
            "turnover": closes * vol,
            "percent_change": np.nan,
            "source": "fixture",
            "retrieved_at": pd.Timestamp("2026-01-01"),
        }
    )


def _client(tmp_path):
    store = MarketStore(tmp_path / "market.duckdb")
    n = 140
    # A double-top shape (peaks at index 10 and 30, neckline ~102).
    double_top = np.interp(
        np.arange(n, dtype=float),
        [0, 10, 20, 30, 40, 139],
        [100, 110, 102, 110, 95, 95],
    )
    store.upsert_bars(_bars("AAA", double_top))
    store.upsert_bars(_bars("BBB", np.linspace(100.0, 150.0, n)))
    store.upsert_bars(_bars("CCC", np.linspace(150.0, 100.0, n)))
    return store, create_app(store=store)


# ------------------------------------------------------------------- patterns


def test_patterns_endpoint_reports_a_double_top(tmp_path):
    store, app = _client(tmp_path)
    with TestClient(app) as c:
        r = c.get("/api/bars/AAA/patterns")
    assert r.status_code == 200
    d = r.json()
    assert d["symbol"] == "AAA"
    assert d["available"] is True
    names = {p["pattern"] for p in d["patterns"]}
    assert "double_top" in names
    assert "double_top" in d["catalogue"]
    assert d["parameters"]["min_bars"] == 60
    store.close()


def test_patterns_endpoint_filters_to_the_requested_subset(tmp_path):
    """``patterns=`` narrows the result; an unknown name is a 400, not silence."""
    store, app = _client(tmp_path)
    with TestClient(app) as c:
        full = c.get("/api/bars/AAA/patterns").json()
        only = c.get("/api/bars/AAA/patterns", params={"patterns": "double_top"}).json()
        none = c.get("/api/bars/AAA/patterns", params={"patterns": "head_and_shoulders"}).json()
        bad = c.get("/api/bars/AAA/patterns", params={"patterns": "not_a_pattern"})
    assert only["available"] is True
    assert {p["pattern"] for p in only["patterns"]} <= {"double_top"}
    assert len(only["patterns"]) <= len(full["patterns"])
    # Filtering can legitimately return nothing; that is an honest empty list.
    assert none["patterns"] == []
    assert none["catalogue"] == full["catalogue"]
    assert bad.status_code == 400
    assert "not_a_pattern" in bad.json()["detail"]
    store.close()


def test_patterns_endpoint_404s_on_unknown_symbol(tmp_path):
    store, app = _client(tmp_path)
    with TestClient(app) as c:
        r = c.get("/api/bars/NOPE/patterns")
    assert r.status_code == 404
    store.close()


def test_patterns_endpoint_reports_unavailable_when_history_is_short(tmp_path):
    store, app = _client(tmp_path)
    with TestClient(app) as c:
        r = c.get("/api/bars/AAA/patterns", params={"min_bars": 1000})
    assert r.status_code == 200
    d = r.json()
    assert d["available"] is False
    assert "required" in d["unavailable_reason"]
    assert d["patterns"] == []
    store.close()


# --------------------------------------------------------------- statistics


def test_statistics_endpoint_returns_price_and_return_stats(tmp_path):
    store, app = _client(tmp_path)
    with TestClient(app) as c:
        r = c.get("/api/bars/BBB/statistics")
    assert r.status_code == 200
    d = r.json()
    assert d["symbol"] == "BBB"
    assert d["bars"] == 140
    assert d["price"]["n"] == 140
    assert d["returns"]["total_return"] is not None
    assert d["assumptions"]["periods_per_year"] == 240
    store.close()


def test_statistics_endpoint_404s_on_unknown_symbol(tmp_path):
    store, app = _client(tmp_path)
    with TestClient(app) as c:
        assert c.get("/api/bars/NOPE/statistics").status_code == 404
    store.close()


# --------------------------------------------------------------- correlation


def test_correlation_endpoint_builds_a_matrix(tmp_path):
    store, app = _client(tmp_path)
    with TestClient(app) as c:
        r = c.get("/api/stats/correlation", params={"symbols": "AAA,BBB,CCC"})
    assert r.status_code == 200
    d = r.json()
    assert d["symbols"] == ["AAA", "BBB", "CCC"]
    assert d["matrix"][0][0] == 1.0
    # BBB rises and CCC falls: their correlation should be strongly negative.
    assert d["matrix"][1][2] < -0.8
    assert d["pair_n"][0][1] == d["common_bars"]
    store.close()


def test_correlation_endpoint_needs_at_least_two_symbols(tmp_path):
    store, app = _client(tmp_path)
    with TestClient(app) as c:
        assert c.get("/api/stats/correlation", params={"symbols": "AAA"}).status_code == 400
    store.close()


def test_correlation_endpoint_404s_when_others_have_no_history(tmp_path):
    store, app = _client(tmp_path)
    with TestClient(app) as c:
        r = c.get("/api/stats/correlation", params={"symbols": "AAA,NOPE"})
    assert r.status_code == 404
    store.close()


def test_correlation_endpoint_rejects_an_unknown_method(tmp_path):
    store, app = _client(tmp_path)
    with TestClient(app) as c:
        r = c.get("/api/stats/correlation", params={"symbols": "AAA,BBB", "method": "kendall"})
    assert r.status_code == 422  # query-pattern validation, not a silent fallback
    store.close()


# --------------------------------------------------------------------- symbol validation
#
# Regression for a real inconsistency found during QA: six per-symbol endpoints
# hard-capped the symbol at 10 characters while four others did not, so a stored
# symbol longer than 10 chars (e.g. an 11-char ticker) returned 200 on
# `/api/bars/{symbol}` but 400 on `/api/bars/{symbol}/weekly`. Every per-symbol
# route must agree: well-formed -> 200/404, malformed or oversized -> 400.

LONG_BUT_VALID = "QA11CHARSYM"  # 11 chars: well-formed, and stored in this fixture
OVERSIZED = "A" * 25  # 25 chars: over the documented cap


def test_eleven_char_symbol_is_accepted_by_every_per_symbol_route(tmp_path):
    store = MarketStore(tmp_path / "market.duckdb")
    n = 120
    store.upsert_bars(_bars(LONG_BUT_VALID, np.linspace(100.0, 130.0, n)))
    app = create_app(store=store)
    with TestClient(app) as c:
        for ep in ("", "/patterns", "/statistics", "/structure", "/levels", "/indicator?name=rsi"):
            r = c.get(f"/api/bars/{LONG_BUT_VALID}{ep}")
            assert r.status_code == 200, (ep, r.status_code, r.text[:120])
    store.close()


def test_oversized_symbol_is_rejected_by_every_per_symbol_route(tmp_path):
    store, app = _client(tmp_path)
    with TestClient(app) as c:
        for ep in ("", "/patterns", "/statistics", "/structure", "/weekly", "/monthly", "/elliott"):
            r = c.get(f"/api/bars/{OVERSIZED}{ep}")
            assert r.status_code == 400, (ep, r.status_code)
    store.close()


def test_malformed_symbol_is_rejected_but_wellformed_unknown_is_404(tmp_path):
    store, app = _client(tmp_path)
    with TestClient(app) as c:
        # A well-formed but unknown symbol is a 404 (not a 400): the format is
        # fine, the data simply does not exist.
        assert c.get("/api/bars/NOSUCHSYM/patterns").status_code == 404
        # A malformed value is a 400.
        assert c.get("/api/bars/%20/patterns").status_code == 400
    store.close()
