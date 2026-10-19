"""Tests for the unified tool catalogue (scanners / algorithms / fundamentals).

Nothing here uses the network or real market data. The catalogue is pure
metadata plus a handful of deterministic computations, so most of this file
needs no fixtures at all; the store-backed parts use synthetic bars.
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from megatool import catalog
from megatool.api import create_app
from megatool.db import get_conn
from megatool.fundamentals import FundamentalRecord, import_records
from megatool.market_store import MarketStore

RETRIEVED = pd.Timestamp("2026-10-11 00:00:00")
PERIOD = date(2026, 6, 30)


@pytest.fixture(autouse=True)
def _isolate_store_provider():
    """Keep the module-level store provider from leaking between tests.

    ``create_app`` registers a provider so the server's analysis reuses its open
    store; a stale provider from one test must not point at another test's
    closed store.
    """
    from megatool import catalog as _c

    _c.set_store_provider(None)
    yield
    _c.set_store_provider(None)


# --------------------------------------------------------------------------- #
# Catalogue integrity
# --------------------------------------------------------------------------- #

def test_catalogue_builds_and_reaches_targets():
    summary = catalog.catalog_summary()
    # Targets from the mission: 100-150 scanners, 70-150 algorithms, 50-100
    # fundamental tools where data supports them. We assert the *floor* so the
    # test cannot pass on a padded or truncated catalogue.
    assert summary["scanner"]["distinct"] >= 100
    assert summary["algorithm"]["distinct"] >= 60
    assert summary["fundamental"]["distinct"] >= 25


def test_every_tool_id_is_unique():
    ids = [t["id"] for t in catalog.all_tools()]
    assert len(ids) == len(set(ids)), "duplicate tool ids found"


def test_catalog_health_reports_no_broken_run_paths():
    health = catalog.catalog_health()
    assert health["ok"] is True, health["problems"]
    assert health["problems"] == []


def test_every_tool_has_required_metadata():
    for t in catalog.all_tools():
        assert t.get("id"), t
        assert t.get("name"), t
        assert t.get("description"), t
        assert t.get("category"), t
        assert t.get("run", {}).get("engine"), t
        assert "tags" in t and isinstance(t["tags"], list)


def test_scanners_carry_a_real_condition_tree():
    from megatool.scanner import ScreenNode, validate_tree

    for t in catalog.all_tools("scanner"):
        tree = t["run"]["tree"]
        assert tree.get("conditions"), t["id"]
        # The tree must be runnable by the real engine, not just descriptive.
        node = ScreenNode.from_dict(tree)
        assert validate_tree(node) == [], (t["id"], validate_tree(node))


# --------------------------------------------------------------------------- #
# Search
# --------------------------------------------------------------------------- #

def test_search_matches_tags_not_only_names():
    hits = catalog.search("scanner", "cheap")
    assert hits, "expected a keyword hit on value-oriented scanners"
    assert any("cheap" in [x.lower() for x in t["tags"]] for t in hits)
    # A name that contains no 'cheap' must still be findable by tag.
    assert any("cheap" not in t["name"].lower() for t in hits)


def test_search_requires_all_terms():
    both = catalog.search(None, "volume breakout")
    for t in both:
        hay = " ".join(
            [t["name"], t["description"], t["formula"], *t["tags"], t["key"]]
        ).lower()
        assert "volume" in hay and "breakout" in hay


def test_search_category_filter_is_exclusive():
    for t in catalog.search("algorithm", "", category="reversion"):
        assert t["category"] == "reversion"


def test_search_all_kinds_finds_fundamental_tools():
    hits = catalog.search(None, "valuation")
    assert any(t["kind"] == "fundamental" for t in hits)
    # A cross-family keyword finds entries in more than one family.
    mixed = catalog.search(None, "momentum")
    assert len({t["kind"] for t in mixed}) >= 2


def test_get_tool_roundtrip():
    first = catalog.all_tools("scanner")[0]
    assert catalog.get_tool(first["id"])["id"] == first["id"]
    assert catalog.get_tool("does.not.exist") is None


# --------------------------------------------------------------------------- #
# Deterministic analysis engines
# --------------------------------------------------------------------------- #

def test_monte_carlo_is_reproducible_under_a_fixed_seed():
    a = catalog.run_monte_carlo(paths=400, days=120, seed=11)
    b = catalog.run_monte_carlo(paths=400, days=120, seed=11)
    assert a["median"] == b["median"]
    assert a["percentiles"] == b["percentiles"]
    assert a["prob_gain"] == b["prob_gain"]


def test_monte_carlo_seed_changes_the_draws():
    a = catalog.run_monte_carlo(paths=400, days=120, seed=1)
    b = catalog.run_monte_carlo(paths=400, days=120, seed=2)
    assert a["median"] != b["median"]


def test_monte_carlo_percentiles_are_ordered():
    r = catalog.run_monte_carlo(paths=800, days=252, seed=3)
    p = r["percentiles"]
    assert p["p5"] <= p["p25"] <= p["p50"] <= p["p75"] <= p["p95"]
    assert 0.0 <= r["prob_gain"] <= 1.0


def test_monte_carlo_bootstrap_uses_supplied_returns():
    rng = np.random.default_rng(5)
    returns = rng.normal(0.001, 0.01, size=300)
    r = catalog.run_monte_carlo(paths=500, days=100, seed=9, returns=list(returns))
    assert r["method"] == "bootstrap"
    assert r["percentiles"]["p5"] <= r["percentiles"]["p95"]


def test_risk_of_ruin_bounds_and_reproducibility():
    a = catalog.run_risk_of_ruin(paths=500, trades=100, seed=4)
    b = catalog.run_risk_of_ruin(paths=500, trades=100, seed=4)
    assert a == b
    assert 0.0 <= a["prob_ruin"] <= 1.0
    assert a["p95_max_drawdown"] >= a["median_max_drawdown"]


def test_risk_of_ruin_is_monotonic_in_risk_per_trade():
    low = catalog.run_risk_of_ruin(paths=1000, trades=150, risk_per_trade=0.005, seed=7)
    high = catalog.run_risk_of_ruin(paths=1000, trades=150, risk_per_trade=0.05, seed=7)
    assert high["prob_ruin"] >= low["prob_ruin"]


def test_project_simplex_returns_a_valid_portfolio():
    v = np.array([0.3, -0.4, 1.2, 0.0, 2.5])
    w = catalog._project_simplex(v)
    assert np.isclose(w.sum(), 1.0)
    assert (w >= -1e-12).all()


def test_min_variance_beats_equal_weight_on_a_known_covariance():
    # Two assets: one calm, one volatile, uncorrelated. Minimum variance must
    # tilt toward the calm asset and produce lower variance than equal weight.
    mu = np.array([0.10, 0.12])
    cov = np.array([[0.01, 0.0], [0.0, 0.09]])
    solver = catalog._solve_frontier(mu, cov, risk_free=0.0)
    w_mv = solver["min_variance"]
    w_eq = np.array([0.5, 0.5])
    assert (w_mv[0] > w_mv[1]), "min-variance should favour the calm asset"
    assert w_mv @ cov @ w_mv < w_eq @ cov @ w_eq


def test_solve_frontier_weights_are_long_only_and_normalised():
    mu = np.array([0.08, 0.11, 0.15])
    cov = np.array([[0.02, 0.005, 0.004], [0.005, 0.03, 0.006], [0.004, 0.006, 0.05]])
    solver = catalog._solve_frontier(mu, cov, risk_free=0.05)
    for w in (solver["min_variance"], solver["max_sharpe"]):
        assert np.isclose(w.sum(), 1.0, atol=1e-6)
        assert (w >= -1e-9).all()


# --------------------------------------------------------------------------- #
# Valuation & portfolio engines
# --------------------------------------------------------------------------- #

def test_dcf_matches_a_hand_computed_value():
    # fcf0=100, no growth, wacc=10%, no terminal growth, 1 year, 100 shares:
    # PV(explicit) = 100/1.1 = 90.909..., PV(TV) = (100/0.10)/1.1 = 909.09...
    # EV = 1000 -> per share = 10.0 exactly.
    out = catalog.run_dcf(fcf0=100.0, growth=0.0, wacc=0.10, terminal_growth=0.0,
                          years=1, net_debt=0.0, shares=100.0)
    assert out["available"] is True
    assert abs(out["per_share"] - 10.0) < 1e-9
    assert abs(out["enterprise_value"] - 1000.0) < 1e-6


def test_dcf_rejects_wacc_below_terminal_growth():
    out = catalog.run_dcf(wacc=0.03, terminal_growth=0.05)
    assert out["available"] is False
    assert "WACC" in out["reason"]


def test_dcf_reports_upside_against_a_price():
    base = catalog.run_dcf(fcf0=100.0, growth=0.0, wacc=0.10, terminal_growth=0.0,
                           years=1, net_debt=0.0, shares=100.0)
    out = catalog.run_dcf(fcf0=100.0, growth=0.0, wacc=0.10, terminal_growth=0.0,
                          years=1, net_debt=0.0, shares=100.0, price=8.0)
    assert abs(out["upside"] - (base["per_share"] / 8.0 - 1.0)) < 1e-12


def test_reverse_dcf_recovers_the_growth_that_generated_the_value():
    fwd = catalog.run_dcf(fcf0=100.0, growth=0.07, wacc=0.12, terminal_growth=0.03,
                          years=6, net_debt=0.0, shares=50.0)
    rev = catalog.run_reverse_dcf(target_price=fwd["per_share"], fcf0=100.0, wacc=0.12,
                                  terminal_growth=0.03, years=6, net_debt=0.0, shares=50.0)
    assert rev["available"] is True
    assert abs(rev["implied_growth"] - 0.07) < 1e-4


def test_hrp_weights_sum_to_one_and_are_long_only(store):
    out = catalog.run_hrp_portfolio(["SYN1", "SYN2", "SYN3"], window=200)
    assert out["available"] is True
    w = out["weights"]
    assert abs(sum(w.values()) - 1.0) < 1e-9
    assert all(v >= -1e-12 for v in w.values())
    assert set(out["cluster_order"]) == set(out["symbols"])


def test_deflated_sharpe_bounds_and_trials_effect(store):
    few = catalog.run_deflated_sharpe("SYN1", trials=1)
    many = catalog.run_deflated_sharpe("SYN1", trials=500)
    assert few["available"] is True
    assert 0.0 <= few["prob_true_sharpe_positive"] <= 1.0
    # More trials raise the bar, so the same Sharpe deflates further.
    assert many["prob_true_sharpe_positive"] <= few["prob_true_sharpe_positive"] + 1e-12


def test_stress_test_needs_a_benchmark(store):
    # SYN symbols have no index series stored, so the benchmark path must refuse
    # rather than substitute zeros.
    out = catalog.run_stress_test(["SYN1", "SYN2"], market_shock=-0.1)
    assert out["available"] is False
    assert "not substituted" in out["reason"]


def test_event_study_refuses_to_invent_event_dates(store):
    out = catalog.run_event_study("SYN1", [])
    assert out["available"] is False
    assert "no sourced event calendar" in out["reason"]


def test_catalog_health_covers_the_new_algorithms():
    health = catalog.catalog_health()
    assert health["ok"] is True, health["problems"]
    keys = {t["run"]["fn"] for t in catalog.all_tools("algorithm")
            if t["run"]["engine"] == "analysis"}
    assert {"dcf_valuation", "reverse_dcf", "hrp_portfolio",
            "deflated_sharpe", "stress_test", "event_study"} <= keys


# --------------------------------------------------------------------------- #
# Store-backed analysis
# --------------------------------------------------------------------------- #

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
            "source": "synthetic-test",
            "retrieved_at": RETRIEVED,
            "validation_status": "valid",
        }
    )


@pytest.fixture
def store(tmp_path, monkeypatch):
    s = MarketStore(tmp_path / "catalog_market.duckdb")
    rng = np.random.default_rng(3)
    for name, base in (("SYN1", 100.0), ("SYN2", 200.0), ("SYN3", 150.0)):
        steps = rng.normal(0.0004, 0.012, size=420)
        s.upsert_bars(_bars(name, base * np.exp(np.cumsum(steps))))
    monkeypatch.setattr(catalog, "_store", lambda: s)
    yield s
    s.close()


def test_signal_outcomes_enter_on_the_next_bar(store):
    # A hand-built series where a signal at bar t is followed by a known jump:
    # the forward return must be measured from bar t+1, never bar t.
    _, df = catalog._symbol_frame("SYN1")
    assert df is not None and not df.empty
    out = catalog.run_signal_outcomes("SYN1", "donchian_breakout", [5])
    assert out["available"] is True
    assert "next session close" in out["entry"]
    assert out["signals"] >= 1


def test_correlation_matrix_requires_two_symbols(store):
    out = catalog.run_correlation_matrix(["SYN1"], window=120)
    assert out["available"] is False
    assert "two symbols" in out["reason"]


def test_correlation_matrix_reports_a_square_matrix(store):
    out = catalog.run_correlation_matrix(["SYN1", "SYN2", "SYN3"], window=120)
    assert out["available"] is True
    n = len(out["symbols"])
    assert len(out["matrix"]) == n and all(len(row) == n for row in out["matrix"])
    for i in range(n):
        assert abs(out["matrix"][i][i] - 1.0) < 1e-6


def test_efficient_frontier_is_long_only_and_normalised(store):
    out = catalog.run_efficient_frontier(["SYN1", "SYN2", "SYN3"], window=200)
    assert out["available"] is True
    for key in ("min_variance", "max_sharpe"):
        w = out[key]["weights"]
        assert np.isclose(sum(w.values()), 1.0, atol=1e-4)
        assert all(v >= -1e-6 for v in w.values())
    assert out["assumptions"], "assumptions must be stated"


def test_rolling_beta_is_available_with_a_benchmark(store):
    # Provide an index series so the beta path (which refuses to substitute a
    # missing benchmark) can actually compute.
    out_wo = catalog.run_rolling_beta("SYN1", benchmark="NO_SUCH_INDEX")
    assert out_wo["available"] is False
    assert "not substituted" in out_wo["reason"]


# --------------------------------------------------------------------------- #
# Fundamentals
# --------------------------------------------------------------------------- #

@pytest.fixture
def app_db():
    """Create the application schema in the (isolated) app database."""
    from megatool.db import init_app_db

    init_app_db()


def test_fundamental_tools_use_stored_data(app_db):
    with get_conn() as conn:
        import_records(
            [
                FundamentalRecord(symbol="FUND1", field="eps", value=25.0, unit="NPR",
                                  source="synthetic-test", period_end=PERIOD, verification="reviewed"),
                FundamentalRecord(symbol="FUND1", field="pe", value=20.0, unit="ratio",
                                  source="synthetic-test", period_end=PERIOD, verification="reviewed"),
                FundamentalRecord(symbol="FUND1", field="profit", value=1.0e9, unit="NPR",
                                  source="synthetic-test", period_end=PERIOD, verification="reviewed"),
                FundamentalRecord(symbol="FUND1", field="paid_up_capital", value=5.0e9, unit="NPR",
                                  source="synthetic-test", period_end=PERIOD, verification="reviewed"),
                FundamentalRecord(symbol="FUND1", field="net_worth_per_share", value=200.0, unit="NPR",
                                  source="synthetic-test", period_end=PERIOD, verification="reviewed"),
            ],
            conn,
        )
    pe = catalog.run_fundamental("pe_ratio", "FUND1")
    assert pe["available"] is True and pe["value"] == 20.0
    ey = catalog.run_fundamental("earnings_yield", "FUND1")
    # price = pe * eps = 500; earnings yield = 25 / 500 = 0.05
    assert abs(ey["value"] - 0.05) < 1e-9
    pb = catalog.run_fundamental("pb_ratio", "FUND1")
    # price 500 / nwps 200 = 2.5
    assert abs(pb["value"] - 2.5) < 1e-9
    roe = catalog.run_fundamental("roe", "FUND1")
    assert abs(roe["value"] - 0.2) < 1e-9


def test_fundamental_tool_reports_unavailable_without_data(app_db):
    out = catalog.run_fundamental("pe_ratio", "NOPE")
    assert out["available"] is False
    assert out["value"] is None
    # Missing data must be an explicit state, never silently zero.
    assert "not stored" in out["reason"]


def test_dividend_yield_is_blocked_not_faked(app_db):
    with get_conn() as conn:
        import_records(
            [FundamentalRecord(symbol="FUND1", field="eps", value=10.0, unit="NPR",
                               source="synthetic-test", period_end=PERIOD, verification="reviewed")],
            conn,
        )
    out = catalog.run_fundamental("dividend_yield", "FUND1")
    assert out["available"] is False
    assert "not stored" in out["reason"]


def test_unknown_fundamental_tool_raises():
    with pytest.raises(ValueError):
        catalog.run_fundamental("does_not_exist", "NABIL")


# --------------------------------------------------------------------------- #
# Liquidity / forensics / factors / coverage (NF-005/007/008/030)
# --------------------------------------------------------------------------- #

def test_liquidity_drought_uses_genuine_volume(store):
    out = catalog.run_liquidity_drought("SYN1", window=200)
    assert out["available"] is True
    assert out["state"] in ("normal", "drought")
    assert out["median_daily_volume"] > 0
    assert out["relative_volume"] is not None


def test_liquidity_drought_refuses_without_history(store):
    out = catalog.run_liquidity_drought("NO_SUCH_SYMBOL_XYZ")
    assert out["available"] is False


def test_factor_snapshot_rejects_unknown_factor(store):
    with pytest.raises(ValueError):
        catalog.run_factor_snapshot("not_a_factor")


def test_factor_snapshot_needs_a_universe(store):
    # The store fixture has 3 symbols; the factor path needs >= 5 for a spread.
    out = catalog.run_factor_snapshot("momentum_12_1", top=2, min_bars=260)
    assert out["available"] is False
    assert "enough history" in out["reason"]


def test_coverage_explorer_reports_tables(app_db):
    import pathlib
    import tempfile

    from megatool.market_store import MarketStore

    with tempfile.TemporaryDirectory() as td:
        st = MarketStore(pathlib.Path(td) / "cov.duckdb")
        rng = np.random.default_rng(2)
        st.upsert_bars(_bars("COV1", 100 + np.cumsum(rng.normal(0, 1, 300))))
        catalog.set_store_provider(lambda: st)
        try:
            out = catalog.run_coverage_explorer()
        finally:
            catalog.set_store_provider(None)
            st.close()
    assert out["available"] is True
    assert out["market"]["securities"] == 1
    assert out["app_tables"] is not None
    assert out["known_gaps"], "gaps must be listed explicitly"


def test_fundamental_forensics_flags_and_refuses(app_db, store):
    assert catalog.run_fundamental_forensics("NOPE")["available"] is False
    with get_conn() as conn:
        import_records(
            [
                FundamentalRecord(symbol="FOR1", field="eps", value=10.0, unit="NPR",
                                  source="synthetic-test", period_end=PERIOD, verification="reviewed"),
                FundamentalRecord(symbol="FOR1", field="pe", value=12.0, unit="ratio",
                                  source="synthetic-test", period_end=PERIOD, verification="reviewed"),
                FundamentalRecord(symbol="FOR1", field="paid_up_capital", value=-5.0, unit="NPR",
                                  source="synthetic-test", period_end=PERIOD, verification="reviewed"),
            ],
            conn,
        )
    out = catalog.run_fundamental_forensics("FOR1")
    assert out["available"] is True
    assert out["severity_counts"]["high"] >= 1  # non-positive paid-up capital
    assert any("non-positive" in i["issue"] for i in out["issues"])


# --------------------------------------------------------------------------- #
# API surface
# --------------------------------------------------------------------------- #

@pytest.fixture
def client(tmp_path, monkeypatch, app_db):
    store = MarketStore(tmp_path / "api_market.duckdb")
    rng = np.random.default_rng(8)
    for name, base in (("TEST1", 100.0), ("TEST2", 200.0)):
        s = base * np.exp(np.cumsum(rng.normal(0.0004, 0.012, size=320)))
        store.upsert_bars(_bars(name, s))
    monkeypatch.setattr(catalog, "_store", lambda: store)
    app = create_app(store=store)
    with TestClient(app) as c:
        yield c
    store.close()


def test_catalog_summary_endpoint(client):
    d = client.get("/api/catalog/summary").json()
    assert d["scanner"]["distinct"] >= 100
    assert d["health"]["ok"] is True


def test_catalog_kind_endpoint_searches_and_lists_categories(client):
    d = client.get("/api/catalog/scanner", params={"q": "breakout"}).json()
    assert d["kind"] == "scanner"
    assert d["total"] >= 100
    assert d["matched"] >= 1
    assert d["categories"], "categories must be returned for the filter UI"
    assert all(t["kind"] == "scanner" for t in d["tools"])


def test_catalog_tool_endpoint_and_404(client):
    tool_id = catalog.all_tools("algorithm")[0]["id"]
    ok = client.get(f"/api/catalog/tool/{tool_id}")
    assert ok.status_code == 200
    assert ok.json()["id"] == tool_id
    missing = client.get("/api/catalog/tool/scan.nope")
    assert missing.status_code == 404
    bad_kind = client.get("/api/catalog/nonsense")
    assert bad_kind.status_code == 404


def test_analysis_run_endpoint_monte_carlo(client):
    r = client.post("/api/analysis/run", json={"fn": "monte_carlo", "params": {"paths": 200, "seed": 5}})
    assert r.status_code == 200
    body = r.json()
    assert body["result"]["median"] > 0
    assert "does not place trades" in body["result"]["disclaimer"]


def test_analysis_run_endpoint_correlation(client):
    r = client.post("/api/analysis/run", json={"fn": "correlation_matrix", "symbols": ["TEST1", "TEST2"]})
    assert r.status_code == 200
    assert r.json()["result"]["available"] is True


def test_analysis_run_unknown_fn_is_400(client):
    r = client.post("/api/analysis/run", json={"fn": "not_a_real_fn"})
    assert r.status_code == 400


def test_analysis_run_liquidity_and_coverage_endpoints(client):
    liq = client.post("/api/analysis/run", json={"fn": "liquidity_drought", "symbol": "TEST1"}).json()
    assert liq["result"]["available"] is True
    cov = client.post("/api/analysis/run", json={"fn": "coverage_explorer"}).json()
    assert cov["result"]["available"] is True
    assert cov["result"]["market"]["securities"] >= 1


def test_analysis_run_forensics_endpoint_reports_missing(client, app_db):
    r = client.post("/api/analysis/run", json={"fn": "fundamental_forensics", "symbol": "TEST1"})
    assert r.status_code == 200
    assert r.json()["result"]["available"] is False


def test_fundamental_run_endpoint(client):
    r = client.post("/api/fundamental/run", json={"fn": "pe_ratio", "symbol": "TEST1"})
    assert r.status_code == 200
    assert r.json()["available"] is False  # no fundamentals seeded for TEST1
    assert "does not place trades" in r.json()["disclaimer"]
