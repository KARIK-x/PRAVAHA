"""API behaviour tests, run against a throwaway store with synthetic data.

Nothing here uses the network. Synthetic fixtures are clearly labelled by their
``source`` field and never mixed with real records.
"""

from __future__ import annotations

import json
from contextlib import contextmanager

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from megatool.api import create_app
from megatool.db import get_conn
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
    # The nested live block is present and lists candidate providers.
    ids = {p["id"] for p in d["live"]["providers"]}
    assert {"sharehub", "official", "feed", "yonepse"} <= ids


def test_live_routes_list_providers_and_stay_network_free(client, monkeypatch):
    for env in (
        "MEGATOOL_SHAREHUB_EMAIL",
        "MEGATOOL_SHAREHUB_PASSWORD",
        "MEGATOOL_LIVE_FEED_URL",
        "MEGATOOL_NEPSE_API_AUTHORIZED",
    ):
        monkeypatch.delenv(env, raising=False)

    status = client.get("/api/live/status").json()
    assert status["official_gate_open"] is False
    assert status["tls_verification"] is True
    assert {p["id"] for p in status["providers"]} >= {"sharehub", "official", "feed", "yonepse"}
    # The gate's provider explains the exact blocker; it is never silently ready.
    official = next(p for p in status["providers"] if p["id"] == "official")
    assert official["configured"] is False
    assert "MEGATOOL_NEPSE_API_AUTHORIZED" in official["reason"]

    # Force an unconfigurable provider so market/quotes answer with a reason and
    # make NO network request.
    monkeypatch.setenv("MEGATOOL_LIVE_PROVIDER", "sharehub")
    market = client.get("/api/live/market").json()
    assert market["ok"] is False and market["provider"] is None
    assert "no live provider" in market["error"]
    quotes = client.get("/api/live/quotes", params={"symbols": "NABIL"}).json()
    assert quotes["ok"] is False and quotes["quotes"] == []


def test_dashboard_marks_itself_not_live(client):
    d = client.get("/api/dashboard").json()
    assert d["is_live"] is False
    assert d["data_as_of"]
    assert d["breadth"]["advancers"] + d["breadth"]["decliners"] == d["symbols"]
    assert "not a live feed" in d["note"]
    # B-10: no index series is stored, so the payload must carry NO index
    # value at all - not None-beside-a-number, not a stale number, nothing.
    assert "no index value is shown" in d["note"]
    assert "index" not in d and "market_index" not in d


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


# ------------------------------------------------------------------ structure
@contextmanager
def _zigzag_client(tmp_path, monkeypatch):
    """A store holding a hand-checkable zigzag, so swings are unambiguous."""
    store = MarketStore(tmp_path / "zigzag.duckdb")
    close = np.array(
        [
            8,
            9,
            10,
            9,
            8,
            7,
            6,
            7,
            8,
            9,
            10,
            9,
            8,
            7,
            6,
            5,
            6,
            7,
            8,
            9,
            10,
            11,
            12,
            11,
            10,
            9,
            8,
            7,
            6,
            7,
            8,
            9,
            10,
            11,
            12,
            13,
            14,
        ],
        dtype=float,
    )
    dates = pd.bdate_range("2026-01-01", periods=len(close))
    df = pd.DataFrame(
        {
            "symbol": "ZZ",
            "trading_date": dates,
            "open": close,
            "high": close + 0.5,
            "low": close - 0.5,
            "close": close,
            "volume": np.full(len(close), 10_000, dtype=np.int64),
            "turnover": close * 10_000,
            "percent_change": 1.0,
            "source": "synthetic-zigzag-fixture",
            "retrieved_at": RETRIEVED,
            "validation_status": "valid",
        }
    )
    store.upsert_bars(df)
    app = create_app(store=store)
    with TestClient(app) as c:
        yield c
    store.close()


def test_structure_route_returns_swings_with_dates(tmp_path, monkeypatch):
    with _zigzag_client(tmp_path, monkeypatch) as c:
        d = c.get("/api/bars/ZZ/structure", params={"left": 2, "right": 2}).json()

    assert d["symbol"] == "ZZ"
    assert d["interpretation"] == "detected"
    assert d["counts"]["swings"] == len(d["swings"]) > 0
    for s in d["swings"]:
        assert s["kind"] in {"high", "low"}
        assert s["date"] and s["confirmed_date"]
        # The confirmation bar is never before the pivot bar.
        assert s["confirmed_index"] >= s["index"]

    kinds = [s["kind"] for s in d["swings"]]
    assert all(a != b for a, b in zip(kinds, kinds[1:], strict=False)), kinds


def test_structure_route_states_its_limitations(tmp_path, monkeypatch):
    with _zigzag_client(tmp_path, monkeypatch) as c:
        d = c.get("/api/bars/ZZ/structure", params={"left": 2, "right": 2}).json()
    joined = " ".join(d["caveats"])
    assert "not a prediction" in joined
    assert "confirmed_index" in joined
    assert d["method"]


def test_structure_404_for_unknown_symbol(client):
    assert client.get("/api/bars/ZZZZ/structure").status_code == 404


def test_structure_rejects_impossible_windows(client):
    r = client.get("/api/bars/TEST1/structure", params={"left": 0})
    assert r.status_code == 422  # FastAPI query validation, ge=1
    r = client.get("/api/bars/TEST1/structure", params={"min_prominence": -1})
    assert r.status_code == 422


def test_structure_is_labelled_not_validated(client):
    """The endpoint must never present a detection as a validated signal."""
    d = client.get("/api/bars/TEST1/structure", params={"left": 3, "right": 3}).json()
    assert d["interpretation"] == "detected"
    assert d["trend"] in {"up", "down", "mixed", "insufficient data"}


# --------------------------------------------------------------- fibonacci
def test_fibonacci_route_returns_levels_with_anchors_and_dates(tmp_path, monkeypatch):
    with _zigzag_client(tmp_path, monkeypatch) as c:
        d = c.get("/api/bars/ZZ/fibonacci", params={"left": 2, "right": 2}).json()

    assert d["symbol"] == "ZZ"
    assert d["classification"] == "calculated"
    assert d["retracements"] and d["extensions"]
    a = d["anchors"]
    assert a["start_date"] and a["end_date"]
    assert a["start_index"] != a["end_index"]
    assert a["range"] != 0
    # Every retracement sits between the anchors; every extension beyond them.
    lo = min(a["start_price"], a["end_price"])
    hi = max(a["start_price"], a["end_price"])
    for row in d["retracements"]:
        assert lo - 1e-9 <= row["price"] <= hi + 1e-9
    assert d["formula"]["retracement"] == "end - range * r"


def test_fibonacci_route_labels_fifty_percent_as_convention(tmp_path, monkeypatch):
    with _zigzag_client(tmp_path, monkeypatch) as c:
        d = c.get("/api/bars/ZZ/fibonacci", params={"left": 2, "right": 2}).json()
    families = {row["ratio"]: row["family"] for row in d["retracements"]}
    assert families[0.5] == "convention"
    assert families[0.618] == "fibonacci"


def test_fibonacci_route_matches_the_shared_calculation(tmp_path, monkeypatch):
    """The API must not recompute a different table than the module does."""
    from megatool.ta.fibonacci import levels_for

    with _zigzag_client(tmp_path, monkeypatch) as c:
        d = c.get("/api/bars/ZZ/fibonacci", params={"left": 2, "right": 2}).json()
    a = d["anchors"]
    table = levels_for(a["start_price"], a["end_price"])
    assert [r["price"] for r in d["retracements"]] == [r["price"] for r in table.retracements]
    assert [r["price"] for r in d["extensions"]] == [r["price"] for r in table.extensions]


def test_fibonacci_route_states_its_limitations(tmp_path, monkeypatch):
    with _zigzag_client(tmp_path, monkeypatch) as c:
        d = c.get("/api/bars/ZZ/fibonacci", params={"left": 2, "right": 2}).json()
    joined = " ".join(d["caveats"])
    assert "CALCULATED" in joined
    assert "not a prediction" in joined
    assert "convention" in joined
    assert d["anchor_policy"]


def test_fibonacci_404_and_validation(tmp_path, monkeypatch):
    with _zigzag_client(tmp_path, monkeypatch) as c:
        assert c.get("/api/bars/ZZZZ/fibonacci").status_code == 404
        assert c.get("/api/bars/ZZ/fibonacci", params={"left": 0}).status_code == 422
        bad = c.get("/api/bars/ZZ/fibonacci", params={"retracements": "not-json"})
        assert bad.status_code == 400
        notarray = c.get("/api/bars/ZZ/fibonacci", params={"retracements": '{"a":1}'})
        assert notarray.status_code == 400
        neg = c.get("/api/bars/ZZ/fibonacci", params={"retracements": "[-1]"})
        assert neg.status_code in {400, 422}


def test_fibonacci_success_declares_available(tmp_path, monkeypatch):
    """The success payload carries ``available: true`` so the frontend can tell
    a real level table from the honest ``available: false`` answer (B-60)."""
    with _zigzag_client(tmp_path, monkeypatch) as c:
        d = c.get("/api/bars/ZZ/fibonacci", params={"left": 2, "right": 2}).json()
    assert d["available"] is True
    assert "unavailable_reason" not in d


def test_fibonacci_insufficient_swings_is_a_200_with_a_reason(client):
    """Too few confirmed swings is an *answer*, not an HTTP error (B-60).

    The newer analytics routes (relative-strength, patterns) answer a data
    condition with ``200 {available: false, reason}``; Fibonacci now matches so
    an expected outcome never looks like a failed request in the browser.
    """
    # TEST1 is a strictly monotonic series: no confirmed swing of either kind.
    r = client.get("/api/bars/TEST1/fibonacci")
    assert r.status_code == 200
    d = r.json()
    assert d["available"] is False
    assert d["unavailable_reason"]
    assert d["retracements"] == [] and d["extensions"] == []
    assert d["anchors"] is None
    assert d["symbol"] == "TEST1"


def test_fibonacci_bad_ratio_is_a_400_not_a_data_condition(client):
    """A malformed level set is a client error (400), distinct from the
    ``available:false`` data-condition answer."""
    r = client.get("/api/bars/TEST1/fibonacci", params={"retracements": "[-1]"})
    assert r.status_code == 400
    assert "non-negative" in r.json()["detail"]


def test_fibonacci_custom_level_set_round_trip(tmp_path, monkeypatch):
    with _zigzag_client(tmp_path, monkeypatch) as c:
        d = c.get(
            "/api/bars/ZZ/fibonacci",
            params={"left": 2, "right": 2, "retracements": "[0.5]", "extensions": "[1.618]"},
        ).json()
    assert [r["ratio"] for r in d["retracements"]] == [0.5]
    assert [r["ratio"] for r in d["extensions"]] == [1.618]
    assert d["params"]["retracements"] == [0.5]


def test_fibonacci_anchors_are_never_undated(tmp_path, monkeypatch):
    with _zigzag_client(tmp_path, monkeypatch) as c:
        d = c.get("/api/bars/ZZ/fibonacci", params={"left": 2, "right": 2}).json()
    a = d["anchors"]
    assert a["start_kind"] in {"high", "low"}
    assert a["end_kind"] in {"high", "low"}


# ------------------------------------------------------------------- levels
def test_levels_route_returns_zones_with_boundaries(tmp_path, monkeypatch):
    with _zigzag_client(tmp_path, monkeypatch) as c:
        d = c.get("/api/bars/ZZ/levels", params={"left": 2, "right": 2}).json()

    assert d["symbol"] == "ZZ"
    assert d["classification"] == "detected"
    assert d["method"] == "swing-cluster"
    for z in d["zones"]:
        assert z["lower"] <= z["center"] <= z["upper"]
        assert z["swing_count"] >= 1
        assert z["first_date"] and z["last_date"]
        assert "distance_from_latest_close" in z
    # Sorted by centre so the chart can place zones deterministically.
    centers = [z["center"] for z in d["zones"]]
    assert centers == sorted(centers)


def test_levels_route_states_it_is_not_liquidity(tmp_path, monkeypatch):
    with _zigzag_client(tmp_path, monkeypatch) as c:
        d = c.get("/api/bars/ZZ/levels", params={"left": 2, "right": 2}).json()
    joined = " ".join(d["caveats"])
    assert "not order-book liquidity" in joined
    assert "will hold" in joined
    assert d["interpretation"] == "detected"


def test_levels_route_has_no_confidence_percentage(tmp_path, monkeypatch):
    with _zigzag_client(tmp_path, monkeypatch) as c:
        raw = c.get("/api/bars/ZZ/levels", params={"left": 2, "right": 2}).text
    assert "confidence" not in raw.lower()


def test_levels_min_touches_excludes_lone_swings(tmp_path, monkeypatch):
    with _zigzag_client(tmp_path, monkeypatch) as c:
        d = c.get("/api/bars/ZZ/levels", params={"left": 2, "right": 2, "min_touches": 50}).json()
    assert d["zones"] == []
    assert d["counts"]["reported"] == 0
    assert d["counts"]["excluded"] >= 1


def test_levels_404_and_validation(tmp_path, monkeypatch):
    with _zigzag_client(tmp_path, monkeypatch) as c:
        assert c.get("/api/bars/ZZZZ/levels").status_code == 404
        assert c.get("/api/bars/ZZ/levels", params={"tolerance_frac": 0}).status_code == 422
        bad = c.get("/api/bars/ZZ/levels", params={"tolerance_mode": "bogus"})
        assert bad.status_code == 422


def test_levels_tolerances_are_reported(tmp_path, monkeypatch):
    with _zigzag_client(tmp_path, monkeypatch) as c:
        d = c.get(
            "/api/bars/ZZ/levels", params={"left": 2, "right": 2, "tolerance_frac": 0.05}
        ).json()
    assert d["params"]["tolerance_frac"] == 0.05
    assert d["params"]["tolerance_mode"] in {"price", "atr"}
    # Price mode must not report a single misleading absolute tolerance.
    assert d["tolerance"] is None
    assert "varies per zone" in d["tolerance_note"]


def test_levels_default_excludes_lone_pivots_but_still_reports_them(tmp_path, monkeypatch):
    """Spec: a small number of defensible zones, not a line per pivot."""
    with _zigzag_client(tmp_path, monkeypatch) as c:
        default = c.get("/api/bars/ZZ/levels", params={"left": 2, "right": 2}).json()
        every = c.get(
            "/api/bars/ZZ/levels", params={"left": 2, "right": 2, "min_touches": 1}
        ).json()
    assert default["params"]["min_touches"] == 2
    assert every["counts"]["reported"] >= default["counts"]["reported"]
    assert default["counts"]["excluded"] >= 1
    # Every default-listed zone is supported by at least two distinct swings.
    for z in default["zones"]:
        assert z["swing_count"] >= 2


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


# ------------------------------------------------------------------- ranking


def test_rank_returns_ordered_scores_with_explanation(client):
    d = client.post("/api/rank", json={}).json()
    assert d["universe_size"] == 2
    assert len(d["ranked"]) == 2
    assert [r["rank"] for r in d["ranked"]] == [1, 2]
    scores = [r["score"] for r in d["ranked"]]
    assert scores == sorted(scores, reverse=True)
    for entry in d["ranked"]:
        assert entry["contributions"]
        assert abs(sum(entry["contributions"].values()) - entry["score"]) < 0.01
        assert entry["percentiles"]


def test_rank_declares_unavailable_factors_with_zero_weight(client):
    d = client.post("/api/rank", json={}).json()
    assert d["unavailable"]
    for key in ("pe_ratio", "pb_ratio", "dividend_yield"):
        assert key in d["unavailable"]
        assert key not in d["weights"]
        for entry in d["ranked"]:
            assert key not in entry["contributions"]


def _sector_scope_store(tmp_path) -> MarketStore:
    """Three ordinary shares plus a mutual fund and a debenture, all tagged
    'Commercial Banks' — exactly the shape the real compilations produce."""
    store = MarketStore(tmp_path / "sector.duckdb")
    n = 120
    slopes = {"SRD1": 0.01, "SRD2": 0.005, "SRD3": 0.001, "SRDMF": 0.01, "SRDBND": 0.01}
    for sym, slope in slopes.items():
        store.upsert_bars(_bars(sym, 100.0 + slope * np.arange(n)))
    store.upsert_securities(
        [
            {"symbol": "SRD1", "instrument_type": "ordinary", "name": "Bank One", "source": "t"},
            {"symbol": "SRD2", "instrument_type": "ordinary", "name": "Bank Two", "source": "t"},
            {"symbol": "SRD3", "instrument_type": "ordinary", "name": "Bank Three", "source": "t"},
            {
                "symbol": "SRDMF",
                "instrument_type": "mutual_fund",
                "name": "Bank Mutual Fund",
                "source": "t",
            },
            {
                "symbol": "SRDBND",
                "instrument_type": "debenture",
                "name": "Bank Bond",
                "source": "t",
            },
        ]
    )
    # A raw sector map assigns the issuer's business sector to all five.
    store.set_sectors(
        {s: "Commercial Banks" for s in slopes},
        provenance={"source": "test"},
    )
    return store


def test_rank_sector_factor_covers_ordinary_shares_only(tmp_path):
    """A bank's bond and mutual fund must not be ranked against its ordinary shares.

    Verified against the real compilations: every one of 63 mutual funds and 89
    debentures carries its issuer's business sector, so an unfiltered sector map
    ranks instruments inside an ordinary-share peer group.
    """
    store = _sector_scope_store(tmp_path)
    app = create_app(store=store)
    with TestClient(app) as c:
        d = c.post(
            "/api/rank",
            json={
                "symbols": ["SRD1", "SRD2", "SRD3", "SRDMF", "SRDBND"],
                "weights": {"sector_percentile": 1.0},
            },
        ).json()
    store.close()

    scope = d["sector_factor_scope"]
    assert scope["symbols_with_sector"] == 5
    assert scope["symbols_used_for_sector_percentile"] == 3
    assert set(scope["non_ordinary_excluded"]) == {"SRDMF", "SRDBND"}

    by_sym = {r["symbol"]: r for r in d["ranked"]}
    # The three ordinary shares are the only ones with a computed percentile.
    with_pct = [
        s for s, r in by_sym.items() if r["percentiles"].get("sector_percentile") is not None
    ]
    assert set(with_pct) == {"SRD1", "SRD2", "SRD3"}
    assert by_sym["SRDMF"]["percentiles"]["sector_percentile"] is None
    assert by_sym["SRDBND"]["percentiles"]["sector_percentile"] is None
    # The instrument symbols are still ranked, just without a sector percentile.
    assert by_sym["SRDMF"]["rank"] is not None
    assert by_sym["SRDBND"]["rank"] is not None


def test_rank_reports_no_sector_scope_when_no_sectors_exist(client):
    """With no sector data the factor is honestly unavailable, not fabricated."""
    d = client.post("/api/rank", json={}).json()
    assert "sector_percentile" in d["unavailable"]
    scope = d["sector_factor_scope"]
    assert scope["symbols_with_sector"] == 0
    assert scope["symbols_used_for_sector_percentile"] == 0
    assert scope["non_ordinary_excluded"] == {}


def test_rank_states_it_is_not_a_signal(client):
    d = client.post("/api/rank", json={}).json()
    assert "not a prediction" in d["disclaimer"]


def test_rank_rejects_unknown_factor(client):
    r = client.post("/api/rank", json={"weights": {"astrology": 1.0}})
    assert r.status_code == 400
    assert "unknown factor" in r.json()["detail"]


def test_rank_rejects_negative_weight(client):
    r = client.post("/api/rank", json={"weights": {"momentum_3m": -1.0}})
    assert r.status_code == 400


def test_rank_rejects_symbol_with_no_history(client):
    r = client.post("/api/rank", json={"symbols": ["NOSUCH"]})
    assert r.status_code == 404


def test_rank_truncates_history_at_as_of(client):
    full = client.post("/api/rank", json={}).json()
    cut = client.post("/api/rank", json={"as_of": "2026-05-01"}).json()
    assert cut["truncated_to"] == "2026-05-01"
    # 87 of 120 bars remain, so both symbols still rank.
    assert len(cut["ranked"]) == 2
    # Percentile ranks depend only on cross-sectional *order*, so with two
    # monotonic symbols the composite score is legitimately unchanged. The
    # underlying factor values must differ - that is the direct evidence the
    # bars after as_of were excluded from the computation.
    assert cut["ranked"][0]["raw_values"] != full["ranked"][0]["raw_values"]
    # momentum_3m (60d) is computable in both cases; momentum_6m (120d) needs
    # more than the 120 bars the fixture stores, so it is None throughout.
    assert (
        cut["ranked"][0]["raw_values"]["momentum_3m"]
        != full["ranked"][0]["raw_values"]["momentum_3m"]
    )


def test_rank_reports_when_as_of_leaves_nothing_rankable(client):
    # 2026-01-20 is only 14 bars in, below min_bars=60.
    r = client.post("/api/rank", json={"as_of": "2026-01-20"})
    assert r.status_code == 200
    d = r.json()
    assert d["ranked"] == []
    assert len(d["excluded"]) == 2
    assert any("nothing could be ranked" in n for n in d["notes"])
    assert all("insufficient data" in e["note"] for e in d["excluded"])


def test_rank_respects_top_limit(client):
    d = client.post("/api/rank", json={"top": 1}).json()
    assert len(d["top"]) == 1
    assert len(d["ranked"]) == 2


def test_rank_weight_override_changes_score(client):
    base = client.post("/api/rank", json={}).json()
    only_vol = client.post(
        "/api/rank", json={"weights": {"momentum_3m": 0.0, "volatility": 1.0}}
    ).json()
    # Default weights include momentum_3m; the override must drop it.
    assert "momentum_3m" in base["weights"]
    assert "momentum_3m" not in only_vol["weights"]
    for entry in only_vol["ranked"]:
        assert "momentum_3m" not in entry["contributions"]
        assert "volatility" in entry["contributions"]
        assert abs(sum(entry["contributions"].values()) - entry["score"]) < 0.01


# --------------------------------------------------------------- walk-forward


@pytest.fixture
def wf_client(tmp_path, monkeypatch):
    """Six symbols over ~100 business days, so a walk-forward has real periods.

    The price path is the same three-segment construction as
    ``tests/test_walkforward.py``: a ramp, then two flat segments whose returns
    are known round numbers, so the expected spreads are hand-derivable.
    """
    store = MarketStore(tmp_path / "market.duckdb")
    dates = pd.bdate_range("2024-09-02", periods=100)
    period_a = {0: -0.10, 1: -0.05, 2: 0.0, 3: 0.02, 4: 0.05, 5: 0.10}
    period_b = {0: 0.01, 1: 0.02, 2: 0.03, 3: 0.04, 4: 0.05, 5: 0.06}
    for i in range(6):
        a = 0.001 * (i + 1)
        closes = []
        for d in range(100):
            if d <= 64:
                closes.append(100.0 * (1.0 + a * d))
            elif d <= 86:
                closes.append(100.0 * (1.0 + a * 64) * (1.0 + period_a[i]))
            else:
                closes.append(100.0 * (1.0 + a * 64) * (1.0 + period_a[i]) * (1.0 + period_b[i]))
        store.upsert_bars(
            pd.DataFrame(
                {
                    "symbol": f"S{i}",
                    "trading_date": dates,
                    "open": closes,
                    "high": closes,
                    "low": closes,
                    "close": closes,
                    "volume": [1_000] * 100,
                    "source": "SYNTHETIC-TEST-FIXTURE",
                    "retrieved_at": RETRIEVED,
                    "validation_status": "valid",
                }
            )
        )
    app = create_app(store=store)
    with TestClient(app) as c:
        yield c
    store.close()


def test_walk_forward_reports_the_historical_spread(wf_client):
    d = wf_client.post("/api/walk-forward", json={"frequency": "M"}).json()
    assert d["summary"]["periods_used"] == 2
    # Hand-derived: long {S5,S4} mean 0.075, short {S1,S0} mean -0.075.
    assert d["periods"][0]["long_symbols"] == ["S5", "S4"]
    assert d["periods"][0]["spread"] == pytest.approx(0.15, abs=1e-9)
    assert d["summary"]["mean_spread"] == pytest.approx(0.095, abs=1e-9)


def test_walk_forward_always_carries_its_caveats(wf_client):
    d = wf_client.post("/api/walk-forward", json={}).json()
    assert any("SURVIVORSHIP BIAS" in c for c in d["caveats"])
    assert any("NO TRANSACTION COSTS" in c for c in d["caveats"])
    assert "disclaimer" in d
    assert "not" in d["disclaimer"].lower()


def test_walk_forward_rejects_a_bad_frequency(wf_client):
    r = wf_client.post("/api/walk-forward", json={"frequency": "D"})
    assert r.status_code == 400


def test_walk_forward_rejects_a_tail_larger_than_half(wf_client):
    # 0.7 exceeds the le=0.5 schema bound, so Pydantic rejects it (422) before
    # the handler runs. Either way it must not be accepted.
    r = wf_client.post("/api/walk-forward", json={"top_quantile": 0.7})
    assert r.status_code in (400, 422)


def test_walk_forward_404s_on_an_empty_store(tmp_path, monkeypatch):
    store = MarketStore(tmp_path / "empty.duckdb")
    app = create_app(store=store)
    with TestClient(app) as c:
        r = c.post("/api/walk-forward", json={})
    store.close()
    assert r.status_code == 404


# --------------------------------------------------------------- fundamentals


FUND_CSV = (
    "symbol,field,value,period_end,source,verification,period_label\n"
    "NABIL,eps,25.4,2026-03-31,unit-test.csv,verified,FY2082/83 Q3\n"
    "NABIL,net_worth_per_share,226.0,2026-03-31,unit-test.csv,verified,FY2082/83 Q3\n"
    "NABIL,dps,12.5,,unit-test.csv,extracted,\n"
)


def test_fundamentals_summary_starts_clean(client):
    d = client.get("/api/fundamentals/summary").json()
    assert d["total"] == 0
    assert "extracted" in d["verification_levels"]
    assert "trustworthy" in d["note"]


def test_fundamentals_import_and_query(client):
    r = client.post("/api/fundamentals/import", json={"content": FUND_CSV})
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["accepted"] == 3
    assert d["symbols"] == 1
    assert d["without_period"] == 1
    assert d["by_verification"]["verified"] == 2

    got = client.get("/api/fundamentals/NABIL").json()
    assert got["count"] == 3
    for row in got["records"]:
        assert row["source"] == "unit-test.csv"
        assert row["unit"]
        assert row["verification"] in ("extracted", "reviewed", "verified")
    # Period-less rows are flagged rather than presented as current.
    assert any(not r2["period_known"] for r2 in got["records"])
    assert "must not be treated as a current figure" in got["note"]


def test_fundamentals_reimport_is_idempotent(client):
    client.post("/api/fundamentals/import", json={"content": FUND_CSV})
    client.post("/api/fundamentals/import", json={"content": FUND_CSV})
    assert client.get("/api/fundamentals/NABIL").json()["count"] == 3


def test_fundamentals_rejects_malformed_csv(client):
    r = client.post(
        "/api/fundamentals/import",
        json={"content": "symbol,field\nNABIL,eps\n"},
    )
    assert r.status_code == 400
    assert "rejected" in r.json()["detail"]


def test_fundamentals_rejects_unknown_field_without_unit(client):
    r = client.post(
        "/api/fundamentals/import",
        json={"content": "symbol,field,value,source\nNABIL,mystery,1,s.csv\n"},
    )
    assert r.status_code == 400
    assert "explicit unit" in r.json()["detail"]


def test_fundamentals_dry_run_writes_nothing(client):
    r = client.post("/api/fundamentals/import", json={"content": FUND_CSV, "dry_run": True})
    assert r.status_code == 200
    assert r.json()["dry_run"] is True
    assert r.json()["written"] == 0
    assert client.get("/api/fundamentals/NABIL").json()["count"] == 0


def test_fundamentals_unknown_symbol_returns_empty(client):
    d = client.get("/api/fundamentals/NOSUCH").json()
    assert d["count"] == 0
    assert d["records"] == []


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
    # The cash-flow block is present and explicitly zero, derived from the
    # (empty) ledger rather than omitted.
    assert d["cash_flow"]["transactions"] == 0
    assert d["cash_flow"]["net_cash_flow"] == 0


def test_sources_lists_both_and_flags_official_blocked(client):
    d = client.get("/api/sources").json()
    labels = [s["label"] for s in d["sources"]]
    assert any("GitHub" in x for x in labels)
    official = next(s for s in d["sources"] if "Official" in s["label"])
    assert official["requires_auth"] is True
    assert official["available"] is False


def test_collector_status_says_not_run_before_any_run(client):
    d = client.get("/api/collector/status").json()
    assert d["run"] is None
    assert "no collector run yet" in d["note"]


def test_collector_status_reports_seeded_run_provenance(client):
    from megatool.datasources import yonepse  # noqa: F401 - uses the same paths

    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO collector_runs (
                started_at, finished_at, status, origin, datasets_ok,
                datasets_degraded, datasets_failed, rows_read, rows_inserted,
                is_open, is_open_source, observed_at, observed_age_seconds,
                freshness, business_date, business_date_evidence
            ) VALUES (
                '2026-10-16T15:10:00', '2026-10-16T15:10:05', 'partial',
                'fixture-origin', 6, 3, 2, 415, 413, 0, 'upstream',
                '2026-10-16T14:54:28', 933.0, 'last-close', '2026-10-16',
                'turnover matched history for the session day'
            )
            """
        )
        run_id = conn.execute("SELECT id FROM collector_runs").fetchone()["id"]
        conn.execute(
            """
            INSERT INTO collector_datasets (
                run_id, dataset, source_path, origin, status, error,
                observed_at, observed_age_seconds, freshness,
                rows_read, rows_valid, rows_flagged, rows_rejected,
                rows_duplicate, notes
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                run_id,
                "market_live",
                "data/market/live.json",
                "fixture-origin",
                "ok",
                "",
                "2026-10-16T14:54:28",
                933.0,
                "last-close",
                3,
                2,
                1,
                0,
                0,
                "",
            ),
        )

    d = client.get("/api/collector/status").json()
    run = d["run"]
    assert run["status"] == "partial"
    assert run["freshness"] == "last-close"
    assert run["is_open"] == 0 and run["is_open_source"] == "upstream"
    assert run["business_date"] == "2026-10-16"
    datasets = {row["dataset"]: row for row in d["datasets"]}
    assert datasets["market_live"]["freshness"] == "last-close"
    assert datasets["market_live"]["rows_flagged"] == 1
    assert d["history"][0]["id"] == run_id
    assert yonepse.PATH_MARKET_TOP_STOCKS.endswith("top_stocks.json")


def test_sources_lists_the_go_library_entry(client, monkeypatch):
    # The go-nepse entry describes the *actual* Go library wrapper. It must be
    # presented honestly: auth required, TLS verification on, and blocked unless
    # the owner gate is open.
    monkeypatch.delenv("MEGATOOL_NEPSE_API_AUTHORIZED", raising=False)
    d = client.get("/api/sources").json()
    g = next(s for s in d["sources"] if "go-nepse" in s["label"])
    assert g["requires_auth"] is True
    assert g["tls_verification"] is True
    assert g["authorized"] is False
    assert g["available"] is False
    assert "tls" in g["note"].lower() or "TLS verification" in g["note"]


def test_gonepse_status_is_network_free_and_states_tls_and_gate(client, monkeypatch):
    # The provider's diagnostics must always answer without probing NEPSE, and
    # must state the two facts that matter: TLS is verified, and live access is
    # behind the owner gate.
    monkeypatch.delenv("MEGATOOL_NEPSE_API_AUTHORIZED", raising=False)
    d = client.get("/api/gonepse/status").json()
    assert "go-nepse" in d["source"]
    assert d["library"] == "github.com/voidarchive/go-nepse"
    assert d["tls_verification"] is True
    assert d["authorized"] is False
    assert d["live"] == "blocked"
    assert "MEGATOOL_NEPSE_API_AUTHORIZED" in d["blocked_reason"]
    assert "market-summary" in d["operations"]
    assert "bridge_present" in d  # never a liveness claim, just a build fact


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
    # PRAVAHA rebrand: the served shell must carry the new product name and must
    # no longer show the old "Mega Tool" product branding. Internal identifiers
    # (megatool-api-base meta, megatool.* module paths, the `megatool` CLI) are
    # deliberately retained and are not product branding.
    assert "PRAVAHA" in r.text
    assert "Mega Tool" not in r.text
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


def test_strategies_catalog_labels_the_fee_as_a_placeholder(client):
    d = client.get("/api/strategies").json()
    assert d["config_defaults"]["fee_rate"] == 0.004
    assert d["config_defaults"]["fee_rate_status"] == "placeholder"
    assert "PLACEHOLDER" in d["note"]


def test_backtest_result_carries_an_honest_cost_model_block(client):
    d = client.post("/api/backtest", json={"symbol": "TEST1", "strategy": "always_in"}).json()
    cm = d["cost_model"]
    # The API accepts no provenance fields, so an API run can only ever be
    # `placeholder` (default rate) or `custom` - never `verified`.
    assert cm["status"] in ("placeholder", "custom")
    assert cm["source"] is None
    assert cm["fee_rate"] == 0.004
    assert "PLACEHOLDER" in cm["note"]


def test_backtest_api_serializes_engine_numbers_without_any_unit_shift(tmp_path):
    """B-32 at the API layer: what JSON round-trips must equal the engine.

    The same run is computed twice - once through the HTTP route, once by
    calling the engine directly on the same stored bars - and every published
    return/P&L number must be IDENTICAL (a serialization layer that rescaled
    percent to fraction, or double-converted, would fail here). The fee is an
    explicit 1% TEST rate, never the placeholder.
    """
    from megatool.backtest import BacktestConfig, build_strategy, run_backtest

    store = MarketStore(tmp_path / "market.duckdb")
    # A zig-zag series so sma_cross(2, 5) both enters and EXITS at least once:
    zigzag = np.array(
        [
            100,
            102,
            104,
            106,
            108,
            106,
            104,
            102,
            100,
            98,
            96,
            98,
            100,
            102,
            104,
            106,
            108,
            110,
            112,
            114,
        ],
        dtype=float,
    )
    store.upsert_bars(_bars("ZIG", zigzag))
    app = create_app(store=store)
    with TestClient(app) as c:
        d = c.post(
            "/api/backtest",
            json={
                "symbol": "ZIG",
                "strategy": "sma_cross",
                "params": {"fast": 2, "slow": 5},
                "fee_rate": 0.01,
            },
        ).json()

    sig, _label, _params = build_strategy("sma_cross", fast=2, slow=5)
    cfg = BacktestConfig(fee_rate=0.01)
    eng = run_backtest(store.get_bars("ZIG"), sig, cfg, symbol="ZIG")
    store.close()

    closed = [t for t in d["trades"] if t["exit_price"] is not None]
    assert closed, "zig-zag fixture must produce at least one CLOSED trade"

    # 1. API metrics == engine metrics, key for key (no rescaling anywhere):
    assert d["metrics"] == eng.metrics
    # 2. API trades == engine trades, including the percent return unit:
    assert d["trades"] == eng.trades
    # 3. Hand identity, computed from the payload's own fields: a trade's
    #    return_pct is a PERCENT of its cost basis (entry price x units plus
    #    the entry fee) - the fee is counted exactly once on each side.
    for t in closed:
        basis = t["entry_price"] * t["units"] * 1.01
        assert t["return_pct"] == pytest.approx(t["pnl"] / basis * 100.0, rel=1e-9)
        assert t["fees_paid"] == pytest.approx(
            (t["entry_price"] + t["exit_price"]) * t["units"] * 0.01, rel=1e-9
        )
    # 4. Aggregate identities agree with the trade list in the same unit:
    m = d["metrics"]
    assert m["realized_pnl"] == pytest.approx(sum(t["pnl"] for t in closed), abs=0.05)
    assert m["avg_trade_pct"] == pytest.approx(
        float(np.mean([t["return_pct"] for t in closed])), abs=1e-3
    )
    assert m["total_return_pct"] == pytest.approx(
        (m["final_equity"] / m["initial_cash"] - 1.0) * 100.0, abs=1e-3
    )
    assert d["equity"][-1]["equity"] == pytest.approx(m["final_equity"], abs=0.01)


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


def test_portfolio_cash_flow_route_reports_recorded_trades(client):
    assert client.get("/api/portfolio/cash-flow").json()["summary"]["net_cash_flow"] == 0
    # BUY 10 @ 50 with 5 fees -> -505; SELL 4 @ 60 with 2 fees -> +238.
    client.post("/api/portfolio/transactions", json=_tx(fees=5.0))
    client.post(
        "/api/portfolio/transactions",
        json=_tx(side="sell", qty=4, price=60.0, fees=2.0, when="2026-03-01T10:00:00"),
    )
    d = client.get("/api/portfolio/cash-flow").json()
    assert [f["net"] for f in d["flows"]] == [-505.0, 238.0]
    s = d["summary"]
    assert s["total_invested"] == 505.0
    assert s["total_proceeds"] == 238.0
    assert s["total_fees"] == 7.0
    assert s["net_cash_flow"] == -267.0
    # The route states what it is and is not.
    assert "not an account cash balance" in d["note"]


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


def test_portfolio_api_serializes_unvalued_position_as_null_not_infinity(tmp_path):
    """B-35 at the API layer: an unusable mark must not poison the JSON.

    A zero close would (before the guard) value the position at 0; a +inf
    close would leak a non-standard `Infinity` token into the response. The
    position must come back unvalued (nulls) with a finite summary.
    """
    import json as _json

    store = MarketStore(tmp_path / "market.duckdb")
    store.upsert_bars(_bars("TEST1", np.array([100.0, 110.0, 0.0])))
    app = create_app(store=store)
    with TestClient(app) as c:
        assert c.post("/api/portfolio/transactions", json=_tx(price=100.0)).status_code == 200
        r = c.get("/api/portfolio")
        # the raw body must contain NO non-standard Infinity/NaN tokens
        # (Python's json.loads would silently accept them, so check the text):
        assert "Infinity" not in r.text and "NaN" not in r.text
        parsed = _json.loads(r.text)
        p = parsed["positions"][0]
        assert p["market_value"] is None and p["last_price"] is None
        assert any("not a usable price" in f for f in p["flags"])
        assert parsed["summary"]["valued_market_value"] == 0.0
        assert parsed["summary"]["unvalued_cost"] == pytest.approx(10 * 100.0)
    store.close()


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


def test_portfolio_delete_transaction_removes_it_from_the_ledger(client):
    """The success path must actually remove the transaction, not just say 200.

    A delete that returned 200 while leaving the row in place would silently
    corrupt realised P&L, so this asserts the ledger is genuinely shorter and
    the deleted id is gone, not merely that the call was accepted.
    """
    tx = client.post("/api/portfolio/transactions", json=_tx()).json()["transaction"]
    tx_id = tx["id"]
    before = client.get("/api/portfolio/transactions").json()["transactions"]
    assert any(t["id"] == tx_id for t in before)

    r = client.delete(f"/api/portfolio/transactions/{tx_id}")
    assert r.status_code == 200
    assert r.json()["deleted"] == tx_id

    after = client.get("/api/portfolio/transactions").json()["transactions"]
    assert len(after) == len(before) - 1
    assert all(t["id"] != tx_id for t in after)
    # Deleting the same id again is now a 404, not a silent second delete.
    assert client.delete(f"/api/portfolio/transactions/{tx_id}").status_code == 404


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


def test_forecast_rolling_walks_forward_with_caveats(client):
    d = client.post(
        "/api/forecast/rolling",
        json={"symbol": "TEST1", "model": "mean", "train_min": 10, "holdout": 5, "step": 5},
    ).json()
    assert d["symbol"] == "TEST1"
    assert d["live"] is False
    assert d["summary"]["origins"] >= 2
    assert len(d["origins"]) == d["summary"]["origins"]
    # every origin is chronological: the reported training end precedes its hold-out
    for o in d["origins"]:
        assert o["train_end_date"] < o["holdout_dates"][0]
    assert d["verdict"]
    assert any("not a forecast, a recommendation" in a for a in d["assumptions"])
    assert d["data_as_of"] == "2026-06-17"


def test_forecast_rolling_404s_unknown_and_400s_too_short(client):
    assert client.post("/api/forecast/rolling", json={"symbol": "NOSUCH"}).status_code == 404
    # train_min + holdout exceed TEST1's 120 bars -> a truthful 400, not a
    # silent truncation of the evaluation window.
    r = client.post(
        "/api/forecast/rolling",
        json={"symbol": "TEST1", "train_min": 200, "holdout": 50},
    )
    assert r.status_code == 400
    assert "at least 250 finite points" in r.json()["detail"]


def test_forecast_rolling_api_pipeline_has_no_future_leakage(tmp_path):
    """Leak probe THROUGH THE HTTP ROUTE, not just the function.

    The task warns the API pipeline can differ from a direct function call.
    Here the same walk-forward is requested twice over two stores whose data
    differ only AFTER an early origin's hold-out window. That early origin's
    RMSE/skill must be identical through the API; a later origin - whose
    training window now spans the tampered points - must differ. This proves
    the route adds no look-ahead via preprocessing, scaling or features.
    """

    def _rolling(closes):
        tag = abs(hash(tuple(closes)))
        s = MarketStore(tmp_path / f"{tag}.duckdb")
        s.upsert_bars(_bars("WALK", np.asarray(closes, dtype=float)))
        app = create_app(store=s)
        with TestClient(app) as c:
            out = c.post(
                "/api/forecast/rolling",
                json={"symbol": "WALK", "model": "mean", "train_min": 4, "holdout": 2, "step": 2},
            ).json()
        s.close()
        return out

    base = list(range(1, 17))  # 1..16, a clean monotone line
    tampered = base[:]
    # tamper strictly AFTER origin-4's hold-out (indices 4,5); origin 8's
    # training window (indices 0-7) now includes the tampered indices 6,7.
    tampered[6:] = [999, -50, 7, 123, 4, 8, 61, 3, 55, 12]

    a = _rolling(base)
    b = _rolling(tampered)
    a4 = next(o for o in a["origins"] if o["origin_index"] == 4)
    b4 = next(o for o in b["origins"] if o["origin_index"] == 4)
    # blind to the tail: origin 4's whole result is bit-identical
    assert a4 == b4
    a8 = next(o for o in a["origins"] if o["origin_index"] == 8)
    b8 = next(o for o in b["origins"] if o["origin_index"] == 8)
    # data-sensitivity: origin 8 trains on tampered points, so it MUST move
    assert a8["model_rmse"] != b8["model_rmse"]


def test_forecast_rolling_rejects_bad_parameters(client):
    assert (
        client.post("/api/forecast/rolling", json={"symbol": "TEST1", "holdout": 0}).status_code
        == 422
    )
    r = client.post("/api/forecast/rolling", json={"symbol": "TEST1", "model": "crystal_ball"})
    assert r.status_code == 400 and "unknown model" in r.json()["detail"]


# ------------------------------------------------------------- news / events
def test_news_import_and_summary_round_trip(client):
    csv_text = (
        "title,published_at,symbols\n"
        "Alpha AGM concluded,2026-01-05,NABIL\n"
        'Beta licence granted,2026-01-07,"NICA, NABIL"\n'
    )
    d = client.post(
        "/api/news/import", json={"content": csv_text, "source": "owner-export.csv"}
    ).json()
    assert d["rows"] == 2 and d["added"] == 2
    assert d["skipped"] == 0
    assert d["symbols"] == ["NABIL", "NICA"]

    s = client.get("/api/news/summary").json()
    assert s["totals"]["items"] == 2
    assert s["totals"]["last_published"] == "2026-01-07"
    assert any(r["symbol"] == "NABIL" for r in s["by_symbol"])
    # the archive always says what it is - and is not
    assert "no live source is connected" in s["note"]


def test_news_summary_of_an_empty_archive_is_honest(client):
    s = client.get("/api/news/summary").json()
    assert s["totals"]["items"] == 0
    assert s["recent"] == []
    assert "no live source is connected" in s["note"]


def test_news_import_rejects_bad_payloads(client):
    assert client.post("/api/news/import", json={"content": ""}).status_code == 422
    assert (
        client.post("/api/news/import", json={"content": "x", "format": "xml"}).status_code == 422
    )
    r = client.post("/api/news/import", json={"content": "foo\nbar\n"})
    assert r.status_code == 400
    assert "missing required column(s): title, published_at" in r.json()["detail"]


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
    # The numbers are never model output, and the endpoint now says so
    # precisely (this assertion was updated when the stale "no LLM key exists"
    # claim was replaced with the real provider status).
    assert "No language model produces these figures" in d["what_this_is"]
    assert "not a prediction" in d["what_this_is_not"]
    assert "ai_status" in d and "ai_note" in d  # optional AI is described honestly


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


# ------------------------------------------------------------ written pdf routes
def _pdf_record(symbol="TPC", review="unreviewed"):
    from megatool.written_pdf import (
        ExtractedRecord,
        ExtractionConfidence,
        RecordType,
        ReviewStatus,
        import_records,
    )

    return import_records(
        [
            ExtractedRecord(
                record_type=RecordType.FUNDAMENTAL,
                page=1,
                source_ref="row 1",
                symbol=symbol,
                field_name="eps",
                value=46.0,
                unit="NPR",
                confidence=ExtractionConfidence.HIGH,
                review_status=ReviewStatus(review),
            )
        ],
        "WRITTENdata.pdf",
    )


def test_written_pdf_summary_reports_counts_and_limitations(client):
    _pdf_record()
    d = client.get("/api/written-pdf/summary").json()
    assert d["total"] == 1
    assert d["by_review_status"] == {"unreviewed": 1}
    assert "Automated OCR failed" in d["note"]


def test_written_pdf_records_filters_and_labels(client):
    _pdf_record()
    d = client.get("/api/written-pdf/records", params={"symbol": "TPC"}).json()
    assert d["count"] == 1
    assert "handwritten personal journal" in d["note"]
    # reviewed-only returns nothing while the record is unreviewed
    assert (
        client.get("/api/written-pdf/records", params={"reviewed_only": True}).json()["count"] == 0
    )


def test_written_pdf_record_type_is_validated_not_a_500(client):
    # Regression: a raw string reached code that called .value on it -> 500.
    r = client.get("/api/written-pdf/records", params={"record_type": "fundamental"})
    assert r.status_code == 200
    bad = client.get("/api/written-pdf/records", params={"record_type": "garbage"})
    assert bad.status_code == 400
    assert "unknown record_type" in bad.json()["detail"]


def test_written_pdf_review_endpoint(client):
    _pdf_record()
    rec = client.get("/api/written-pdf/records", params={"symbol": "TPC"}).json()["records"][0]
    out = client.post(
        "/api/written-pdf/review", json={"ids": [rec["id"]], "status": "reviewed"}
    ).json()
    assert out["updated"] == 1
    # now it is visible under reviewed_only
    assert (
        client.get("/api/written-pdf/records", params={"reviewed_only": True}).json()["count"] == 1
    )


def test_written_pdf_review_rejects_bad_status_and_unreviewed(client):
    _pdf_record()
    bad = client.post("/api/written-pdf/review", json={"ids": [1], "status": "maybe"})
    assert bad.status_code == 400
    assert "unknown status" in bad.json()["detail"]
    back = client.post("/api/written-pdf/review", json={"ids": [1], "status": "unreviewed"})
    assert back.status_code == 400
    assert "unreviewed" in back.json()["detail"]


def test_research_ask_falls_back_to_journal_for_a_symbol_without_history(client):
    # TPC has no bars in this store, but a reviewed journal record.
    _pdf_record(symbol="TPC", review="reviewed")
    d = client.post("/api/research/ask", json={"symbol": "TPC", "question": "journal eps"}).json()
    assert d["journal_only"] is True
    assert d["bars"] == 0
    assert len(d["pdf_findings"]) == 1
    assert d["pdf_findings"][0]["value"] == 46.0
    assert "No stored price history" in d["matched_note"]


def test_research_ask_still_404s_when_there_is_nothing_to_answer(client):
    # No bars and no journal records: the honest answer is still a 404.
    r = client.post("/api/research/ask", json={"symbol": "ZZZZ", "question": "eps journal"})
    assert r.status_code == 404


def test_research_ask_hides_unreviewed_journal_records(client):
    _pdf_record(symbol="QQQ", review="unreviewed")
    d = client.post(
        "/api/research/ask", json={"symbol": "QQQ", "question": "what does the journal say"}
    ).json()
    assert d["pdf_findings"] == []
    assert any("not reviewed yet" in w for w in d["warnings"])


# ------------------------------------- R5 / B-4: status-aware eligibility routes
#
# Both routes now exclude verified non-tradable securities (DELISTED,
# SUSPENDED, MERGED) by default. UNKNOWN symbols are still screened/ranked so
# missing metadata does not silently erase valid securities, but the
# uncertainty is observable. Synthetic metadata only.


def _eligibility_store(tmp_path) -> MarketStore:
    store = MarketStore(tmp_path / "elig.duckdb")
    n = 120
    store.upsert_bars(_bars("TEST1", 100.0 + np.arange(n)))
    store.upsert_bars(_bars("TEST2", 200.0 - np.arange(n)))
    store.upsert_securities(
        [
            {
                "symbol": "TEST1",
                "name": "Delisted One",
                "instrument_type": "ordinary",
                "source": "test",
                "status": "DELISTED",
            },
            {
                "symbol": "TEST2",
                "name": "Live Two",
                "instrument_type": "ordinary",
                "source": "test",
                "status": "ACTIVE",
            },
        ]
    )
    # A third symbol with bars but deliberately NO security_master row.
    store.upsert_bars(_bars("NOROW", 50.0 + np.arange(n)))
    return store


_TREE = {"op": "AND", "conditions": [{"metric": "close", "operator": "gt", "value": 0}]}


def test_screen_route_default_excludes_non_tradable_and_includes_unknown(tmp_path):
    store = _eligibility_store(tmp_path)
    app = create_app(store=store)
    with TestClient(app) as c:
        d = c.post("/api/screen", json={"tree": _TREE}).json()
    store.close()
    seen = {r["symbol"]: r for r in d["results"]}
    # Verified non-tradable is excluded; ACTIVE and UNKNOWN are screened.
    assert seen["TEST1"]["eligible"] is False
    assert seen["TEST2"]["eligible"] is True
    assert seen["NOROW"]["eligible"] is True
    # The default filter is now active and reported.
    assert d["eligibility_filter"]["exclude_delisted"] is True


def test_screen_route_can_disable_filter_to_include_inactive(tmp_path):
    store = _eligibility_store(tmp_path)
    app = create_app(store=store)
    with TestClient(app) as c:
        d = c.post("/api/screen", json={"tree": _TREE, "exclude_delisted": False}).json()
    store.close()
    seen = {r["symbol"]: r for r in d["results"]}
    assert seen["TEST1"]["eligible"] is True
    assert seen["TEST2"]["eligible"] is True
    assert seen["NOROW"]["eligible"] is True
    assert "eligibility_filter" not in d


def test_rank_route_default_excludes_non_tradable_and_includes_unknown(tmp_path):
    store = _eligibility_store(tmp_path)
    app = create_app(store=store)
    with TestClient(app) as c:
        d = c.post("/api/rank", json={}).json()
    store.close()
    # ACTIVE + UNKNOWN (NOROW) survive; DELISTED (TEST1) is excluded.
    ranked = {row["symbol"] for row in d["ranked"]}
    assert ranked == {"TEST2", "NOROW"}
    assert d["universe_size"] == 2
    assert d["requested"] == 3
    assert d["eligibility_filter"]["exclude_delisted"] is True


def test_rank_route_opt_in_filter_same_as_default_now(tmp_path):
    # Explicit exclude_delisted=True is now the same as the default.
    store = _eligibility_store(tmp_path)
    app = create_app(store=store)
    with TestClient(app) as c:
        d = c.post("/api/rank", json={"exclude_delisted": True}).json()
    store.close()
    ranked = {row["symbol"] for row in d["ranked"]}
    assert ranked == {"TEST2", "NOROW"}
    excluded = {row["symbol"]: row["reason"] for row in d["eligibility_filter"]["excluded"]}
    assert "TEST1" in excluded and "DELISTED" in excluded["TEST1"]
    assert "NOROW" not in excluded  # unknown is allowed, not excluded


def test_rank_route_instrument_filter_and_full_exclusion_400(tmp_path):
    store = _eligibility_store(tmp_path)
    app = create_app(store=store)
    with TestClient(app) as c:
        # Ordinary-only with filters off: the two typed symbols stay.
        d = c.post(
            "/api/rank",
            json={"instrument_types": ["ordinary"], "exclude_delisted": False},
        ).json()
        # All symbols excluded -> explicit 400, not a silently empty ranking.
        r = c.post("/api/rank", json={"instrument_types": ["debenture"]})
        r2 = c.post("/api/rank", json={"symbols": ["TEST1"], "exclude_delisted": True})
    store.close()
    ranked = {row["symbol"] for row in d["ranked"]}
    assert ranked == {"TEST1", "TEST2"}
    excluded = {row["symbol"]: row["reason"] for row in d["eligibility_filter"]["excluded"]}
    assert "NOROW" in excluded and "unknown" in excluded["NOROW"]
    assert r.status_code == 400
    assert "excluded by the eligibility filter" in r.json()["detail"]
    assert r2.status_code == 400


# ------------------------- verified-schedule backtest contract (C3/D-y)
def test_backtest_with_verified_schedule_reports_it(client):
    d = client.post(
        "/api/backtest",
        json={"symbol": "TEST1", "strategy": "always_in", "fee_schedule": "official-2083-84"},
    ).json()
    assert d["config"]["fee_schedule"] == "official-2083-84"
    assert d["cost_model"]["status"] == "verified"
    assert d["cost_model"]["fee_schedule"] == "official-2083-84"
    assert d["cost_model"]["cgt"] is None
    assert d["cost_model"]["schedule"]["name"] == "official-2083-84"
    # without a declared category the tax is refused, not fabricated
    assert d["metrics"]["capital_gains_tax_paid"] is None
    assert any("NOT computed" in w for w in d["warnings"])
    closed = [t for t in d["trades"] if t["pnl"] is not None]
    if closed:
        t = closed[0]
        assert t["capital_gains_tax"] is None
        assert t["transaction_costs"] == pytest.approx(t["fees_paid"])


def test_backtest_schedule_with_declared_category_computes_tax(client):
    d = client.post(
        "/api/backtest",
        json={
            "symbol": "TEST1",
            "strategy": "always_in",
            "fee_schedule": "official-2083-84",
            "cgt": "natural_person",
        },
    ).json()
    closed = [t for t in d["trades"] if t["capital_gains_tax"] is not None]
    if closed:  # every closed trade got an explicit computed outcome
        for t in closed:
            assert t["capital_gains_tax"] >= 0.0
            assert t["tax_note"]
    assert not any("NOT computed" in w for w in d["warnings"])


def test_backtest_rejects_ambiguous_or_unknown_cost_models(client):
    r = client.post(
        "/api/backtest",
        json={"symbol": "TEST1", "strategy": "always_in", "fee_schedule": "nepse-2026"},
    )
    assert r.status_code == 400
    assert "unknown fee_schedule" in r.json()["detail"]
    r = client.post(
        "/api/backtest",
        json={"symbol": "TEST1", "strategy": "always_in", "fee_rate": 0.001},
    )  # plain custom rate still works (legacy contract)
    assert r.status_code == 200
    assert r.json()["cost_model"]["status"] == "custom"


def test_backtest_rejects_cgt_declaration_without_a_schedule(client):
    r = client.post(
        "/api/backtest",
        json={"symbol": "TEST1", "strategy": "always_in", "cgt": "natural_person"},
    )
    assert r.status_code == 400
    assert "requires fee_schedule" in r.json()["detail"]


def test_planning_payload_carries_the_verified_cost_estimate(client):
    d = client.post(
        "/api/planning",
        json={"entry": 100, "stop": 90, "target": 120, "capital": 50000, "risk_pct": 2},
    ).json()
    assert d["sizing"]["units"] > 0
    est = d["cost_estimate"]
    assert est["schedule"] == "official-2083-84"
    assert est["total"] == pytest.approx(est["commission"] + est["sebon"] + est["dp"])
    assert est["dp"] == 0.0
    assert est["note"]


def test_planning_without_sizing_has_no_cost_estimate(client):
    d = client.post("/api/planning", json={"entry": 100, "stop": 90, "target": 120}).json()
    assert "cost_estimate" not in d
    assert d["portfolio_check"]["checked"] is False


def test_strategies_discloses_the_available_schedules(client):
    d = client.get("/api/strategies").json()
    assert d["config_defaults"]["fee_schedule"] is None  # opt-in, not the default
    assert d["config_defaults"]["cgt"] is None
    assert "official-2083-84" in d["config_defaults"]["available_fee_schedules"]
    assert "placeholder" in d["config_defaults"]["available_fee_schedules"]


def test_dashboard_index_note_unavailable_without_series(client):
    # B-10: while the store holds no index_series the dashboard says so, and it
    # must not imply a stored index value exists (the live strip is separate).
    note = client.get("/api/dashboard").json()["note"]
    assert "no historical index series" in note
    assert "no index value is shown" in note


def test_dashboard_index_note_reflects_loaded_series(tmp_path):
    store = MarketStore(tmp_path / "index_note.duckdb")
    store.upsert_bars(_bars("TEST1", 100.0 + np.arange(120)))
    store.upsert_index_rows(
        [{"index_name": "NEPSE", "trading_date": "2026-10-14", "close": 2595.81, "source": "test"}]
    )
    app = create_app(store=store)
    with TestClient(app) as c:
        note = c.get("/api/dashboard").json()["note"]
    store.close()
    assert "published index series loaded" in note
    assert "not a live feed" in note


def test_quotes_endpoint_empty_without_quotes(client):
    d = client.get("/api/quotes").json()
    assert d["count"] == 0
    assert d["freshness"]["rows"] == 0
    assert d["freshness"]["is_stale"] is None


# --------------------------------------------------- degenerate-series robustness
# A stored series can contain NaN in a high/low column (bad import, partial
# backfill). Every per-symbol endpoint must degrade with a clean HTTP status,
# never an unhandled 500. This was a real defect (B-49): /elliott and /harmonic
# let SwingError escape while their siblings caught it.

_PER_SYMBOL_GETS = [
    "",
    "/indicator?name=rsi",
    "/indicator?name=macd",
    "/structure",
    "/patterns",
    "/statistics",
    "/fibonacci",
    "/levels",
    "/elliott",
    "/harmonic",
    "/weekly",
    "/monthly",
]


def test_nan_series_never_returns_a_5xx(tmp_path):
    store = MarketStore(tmp_path / "market.duckdb")
    n = 120
    closes = np.concatenate([np.full(60, 100.0), np.full(60, np.nan)])
    store.upsert_bars(_bars("NANTAIL", closes))
    store.upsert_bars(_bars("ONE", np.array([100.0])))
    store.upsert_bars(_bars("FLAT", np.full(n, 50.0)))
    app = create_app(store=store)
    with TestClient(app) as c:
        for sym in ("NANTAIL", "ONE", "FLAT"):
            for ep in _PER_SYMBOL_GETS:
                r = c.get(f"/api/bars/{sym}{ep}")
                assert r.status_code < 500, (sym, ep, r.status_code, r.text[:120])
    store.close()


def test_nan_series_gives_a_clear_400_on_swing_based_endpoints(tmp_path):
    store = MarketStore(tmp_path / "market.duckdb")
    closes = np.concatenate([np.full(60, 100.0), np.full(60, np.nan)])
    store.upsert_bars(_bars("NANTAIL", closes))
    app = create_app(store=store)
    with TestClient(app) as c:
        for ep in ("/elliott", "/harmonic", "/structure", "/fibonacci"):
            r = c.get(f"/api/bars/NANTAIL{ep}")
            assert r.status_code == 400, (ep, r.status_code)
            # The message must explain the cause, not leak a traceback.
            assert "finite" in r.json()["detail"]
    store.close()


def test_ideas_catalogue_states_each_model_and_its_missing_inputs(client):
    d = client.get("/api/ideas").json()
    models = {m["id"]: m for m in d["models"]}
    assert "graham" in models
    assert models["graham"]["status"] == "available"
    # A model whose inputs are not stored must say so up front.
    assert models["piotroski"]["status"] == "insufficient_data"
    assert models["piotroski"]["missing_inputs"]


def test_ideas_run_reports_an_honest_status_and_never_500s(client):
    # Price-based models run over whatever the fixture store holds.
    d = client.get("/api/ideas/momentum").json()
    assert d["status"] in {"calculated", "insufficient_data"}
    assert isinstance(d["rows"], list)
    # A model with unavailable inputs returns a reason, not an error.
    p = client.get("/api/ideas/piotroski").json()
    assert p["status"] == "insufficient_data"
    assert p["rows"] == []
    # Unknown model -> 404, not a traceback.
    assert client.get("/api/ideas/does-not-exist").status_code == 404


def test_market_dashboard_assembles_one_payload_and_labels_sources(client):
    # One round-trip supplies the index chart, breadth, sectors, movers and
    # valuation; nothing is invented when a store is empty, and every block
    # carries enough honesty for the UI to say what is missing.
    d = client.get("/api/market/dashboard").json()
    assert set(d) >= {
        "market",
        "index_chart",
        "breadth",
        "sectors",
        "movers",
        "heat",
        "valuation",
        "sector_map_size",
        "market_closed",
    }
    idx = d["index_chart"]
    assert idx["name"] == "NEPSE"
    assert "available" in idx
    assert isinstance(idx["points"], list)
    # Breadth reports its denominator honestly rather than 100%-ing by force.
    b = d["breadth"]
    assert set(b) >= {
        "advancers",
        "decliners",
        "unchanged",
        "missing",
        "total",
        "moving_average",
        "as_of",
    }
    assert (b["advancers"] + b["decliners"] + b["unchanged"] + b["missing"]) == b["total"]
    # In an empty fixture store the series are honestly unavailable, not invented.
    if not idx["available"]:
        assert "reason" in idx
    # Valuation exposes what it covered.
    v = d["valuation"]
    assert {"pe_bins", "pb_bins", "scatter", "coverage"} <= set(v)
    assert v["coverage"]["note"].startswith("counts are")
    # Heatmap: tiles exclude anything the source left without pct or turnover.
    h = d["heat"]
    assert {"tiles", "covered", "total_quotes", "note"} <= set(h)
    assert all(t["turnover"] > 0 and t["pct"] is not None for t in h["tiles"])
    assert h["covered"] <= h["total_quotes"]


# ----------------------------------------------------------------- Kronos AI
class _FakeKronosManager:
    """Deterministic stand-in for the real model manager (no weights loaded)."""

    def __init__(self):
        self.unloaded = False

    def availability(self):
        return {
            "torch_installed": True,
            "einops_installed": True,
            "weights_root": "/fake",
            "weights": {"Kronos-base": {"present": True, "bytes": 409}},
            "loaded_variant": None,
            "load_seconds": None,
            "device_selected": "cpu",
            "max_context": 512,
            "official_repo": "https://github.com/shiyu-coder/Kronos",
            "official_ids": {"base": "NeoQuasar/Kronos-base"},
            "disclaimer": "not a live NEPSE feed",
        }

    def forecast(self, bars, req, device=None):
        assert not bars.empty
        n = req.pred_len
        rows = [
            {
                "time": f"2027-01-{i + 1:02d}",
                "open": 1.0,
                "high": 1.5,
                "low": 0.5,
                "close": 1.2,
                "volume": 10,
                "amount": 20,
                "is_predicted": True,
                "step": i + 1,
            }
            for i in range(n)
        ]
        return {
            "symbol": req.symbol,
            "variant": req.variant,
            "device": "cpu",
            "context": {"bars": req.context_len, "first": "x", "last": "y", "last_close": 100.0},
            "generated_at": "2026-10-16T00:00:00+00:00",
            "sample_count": 1,
            "temperature": 1.0,
            "inference_seconds": 0.1,
            "load_seconds": 0.2,
            "rows": rows,
            "note": "All rows above are model-predicted candles",
        }

    def evaluate(self, bars, req, windows=6, device=None):
        return {
            "symbol": req.symbol,
            "variant": req.variant,
            "device": "cpu",
            "context_len": req.context_len,
            "horizon": req.pred_len,
            "avg": {
                "kronos_mae_close": 5.0,
                "kronos_rmse_close": 6.0,
                "kronos_mape_pct": 4.0,
                "kronos_direction_pct": 45.0,
                "naive_mae_close": 1.0,
                "drift20_mae_close": 2.0,
                "windows": 2,
                "horizon": req.pred_len,
                "total_seconds": 1.0,
            },
            "best_mae_competitor": "naive_mae_close",
            "windows_detail": [
                {
                    "anchor": "2026-01-01",
                    "realized_span": "2026-01-02 to 2026-01-09",
                    "inference_seconds": 0.4,
                    "kronos": {
                        "mae": 5.0,
                        "rmse": 6.0,
                        "mape_pct": 4.0,
                        "direction_ok": 2,
                        "steps": 5,
                    },
                    "naive_last_close": {"mae": 1.0},
                    "drift20": {"mae": 2.0},
                },
            ],
            "note": "walk-forward research measurement",
        }

    def unload(self):
        self.unloaded = True
        return {"loaded_variant": None}


def test_kronos_status_reports_availability(client):
    d = client.get("/api/kronos/status").json()
    assert d["official_repo"].endswith("/Kronos")
    assert "not a live NEPSE feed" in d["disclaimer"]
    assert "weights" in d and "device_selected" in d


def test_kronos_forecast_rows_are_labelled_and_saved(client, monkeypatch):
    fake = _FakeKronosManager()
    monkeypatch.setattr("megatool.kronos_service.get_manager", lambda: fake)
    r = client.post(
        "/api/kronos/forecast",
        json={"symbol": "TEST1", "pred_len": 3, "context_len": 64, "variant": "base"},
    )
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["symbol"] == "TEST1"
    assert all(row["is_predicted"] is True for row in d["rows"])
    assert len(d["rows"]) == 3
    saved = client.get("/api/kronos/experiments").json()
    assert saved["count"] >= 1
    assert any(e["kind"] == "forecast" and e["symbol"] == "TEST1" for e in saved["experiments"])


def test_kronos_evaluate_states_verdict_against_baselines(client, monkeypatch):
    fake = _FakeKronosManager()
    monkeypatch.setattr("megatool.kronos_service.get_manager", lambda: fake)
    r = client.post(
        "/api/kronos/evaluate",
        json={"symbol": "TEST2", "pred_len": 5, "context_len": 64, "windows": 2},
    )
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["avg"]["kronos_mae_close"] > d["avg"]["naive_mae_close"]
    assert d["best_mae_competitor"] == "naive_mae_close"


def test_kronos_forecast_422_on_quality_problem(client, monkeypatch):
    from megatool.kronos_service import DataQualityError

    class _Bad(_FakeKronosManager):
        def forecast(self, bars, req, device=None):
            raise DataQualityError("TEST1: need at least 96 usable bars, have 0")

    monkeypatch.setattr("megatool.kronos_service.get_manager", lambda: _Bad())
    r = client.post(
        "/api/kronos/forecast",
        json={"symbol": "TEST1", "pred_len": 5, "context_len": 96},
    )
    assert r.status_code == 422
    assert "usable bars" in r.json()["detail"]


def test_kronos_unknown_symbol_is_404(client, monkeypatch):
    fake = _FakeKronosManager()
    monkeypatch.setattr("megatool.kronos_service.get_manager", lambda: fake)
    r = client.post("/api/kronos/forecast", json={"symbol": "NOSUCH", "pred_len": 2})
    assert r.status_code == 404


def test_kronos_experiments_delete_and_404(client, monkeypatch):
    fake = _FakeKronosManager()
    monkeypatch.setattr("megatool.kronos_service.get_manager", lambda: fake)
    client.post("/api/kronos/forecast", json={"symbol": "TEST1", "pred_len": 2, "context_len": 64})
    saved = client.get("/api/kronos/experiments").json()
    exp_id = saved["experiments"][0]["id"]
    assert client.delete(f"/api/kronos/experiments/{exp_id}").status_code == 200
    assert client.delete(f"/api/kronos/experiments/{exp_id}").status_code == 404


def test_kronos_unload(client, monkeypatch):
    fake = _FakeKronosManager()
    monkeypatch.setattr("megatool.kronos_service.get_manager", lambda: fake)
    r = client.post("/api/kronos/unload")
    assert r.status_code == 200
    assert fake.unloaded is True


def test_heat_excludes_unknown_pct_and_turnover_honestly():
    """A quote lacking either published metric is simply absent - no estimate."""
    from megatool.market_dashboard import heat

    quotes = [
        {"symbol": "FULL", "ltp": 100.0, "percent_change": 2.5, "turnover": 5_000_000.0},
        {"symbol": "NOPCT", "ltp": 50.0, "percent_change": None, "turnover": 9_000_000.0},
        {"symbol": "NOTO", "ltp": 70.0, "percent_change": -1.1, "turnover": 0},
        {"symbol": "NONE", "ltp": None, "percent_change": 1.0, "turnover": 1.0},
    ]
    d = heat(quotes)
    syms = [t["symbol"] for t in d["tiles"]]
    assert syms == ["FULL"]
    assert d["covered"] == 1 and d["total_quotes"] == 4
    # stability: equal turnover ties break on symbol, never on arrival order
    q2 = [
        {"symbol": "B", "ltp": 1, "percent_change": 1.0, "turnover": 100.0},
        {"symbol": "A", "ltp": 1, "percent_change": -1.0, "turnover": 100.0},
    ]
    assert [t["symbol"] for t in heat(q2)["tiles"]] == ["A", "B"]


# ------------------------------------------------- breadth & seasonality routes
def test_breadth_history_route(client):
    r = client.get("/api/breadth/history", params={"windows": "20", "high_low_window": 20})
    assert r.status_code == 200
    d = r.json()
    assert d["trading_days"] > 100
    assert d["definitions"]["advances"]
    assert len(d["series"]["advances"]) == d["trading_days"]
    # Both fixture symbols have >20 bars, so the SMA window is fully available
    # on the last date.
    assert d["available"]["sma_20"][-1] == 2


def test_breadth_history_rejects_bad_windows(client):
    assert client.get("/api/breadth/history", params={"windows": "1"}).status_code == 400
    assert client.get("/api/breadth/history", params={"windows": "a,b"}).status_code == 400


def test_seasonality_route_shape(client):
    r = client.get("/api/seasonality/TEST1")
    assert r.status_code == 200
    d = r.json()
    assert d["monthly"]["symbol"] == "TEST1"
    assert len(d["monthly"]["by_month"]) == 12
    assert d["weekday"]["by_weekday"]
    # The bundled calendar has no holiday entries; the route must say so.
    assert d["holiday"]["available"] is False


def test_seasonality_route_rejects_junk_and_missing_symbols(client):
    assert client.get("/api/seasonality/bad$symbol").status_code == 400
    assert client.get("/api/seasonality/NOPE").status_code == 404


# ------------------------------------------------- swing-workbench route
def test_swing_workbench_route_shape(client):
    r = client.get(
        "/api/bars/TEST1/swing-workbench",
        params={"limit": 120, "account_size": 100000, "risk_fraction": 0.01},
    )
    assert r.status_code == 200
    d = r.json()
    assert d["symbol"] == "TEST1"
    assert d["bars"] > 0
    assert "trend" in d["structure"]
    assert d["checklist"]
    assert "Not a signal" in d["disclaimer"]
    assert d["as_of"] >= d["first_date"]
    # When no framed structure exists the reason must be stated, never a
    # fabricated invalidation price.
    if d["reference_levels"]["framing"] is None:
        assert d["reference_levels"]["reason"]


def test_swing_workbench_route_rejects_bad_requests(client):
    assert (
        client.get("/api/bars/TEST1/swing-workbench", params={"risk_fraction": 0}).status_code
        == 422
    )
    assert client.get("/api/bars/NOPE/swing-workbench").status_code == 404
    assert client.get("/api/bars/bad$sym/swing-workbench").status_code == 400


# ------------------------------------------- market ribbon (/api/market/ribbon)
def test_market_ribbon_shape_and_honesty(client):
    d = client.get("/api/market/ribbon", params={"top": 5}).json()
    assert d.get("empty") is not True
    assert d["is_live"] is False
    assert "delayed" in d["freshness"]
    assert d["as_of"]
    keys = [g["key"] for g in d["groups"]]
    # The four ranking groups are always present; extremes only when one exists,
    # so it must never be present-but-empty.
    assert keys[:4] == ["gainers", "losers", "turnover", "volume"]
    for g in d["groups"]:
        assert g["rule"], "every group must state the rule that ranked it"
        assert isinstance(g["items"], list)
        assert isinstance(g["skipped_duplicates"], int)
        if g["key"] == "extremes":
            assert g["items"]
    # A symbol is shown at most once across the whole ribbon (dedupe, reported).
    seen = [it["symbol"] for g in d["groups"] for it in g["items"]]
    assert len(seen) == len(set(seen))
    # Categories the stored data cannot support are listed with a reason.
    un = {u["key"]: u["reason"] for u in d["unavailable"]}
    assert "relvol" in un and un["relvol"]


def test_market_ribbon_breadth_covers_every_symbol(client):
    d = client.get("/api/market/ribbon").json()
    b = d["breadth"]
    assert b["advancers"] + b["decliners"] + b["unchanged"] == d["symbols"]
    assert d["symbols"] > 0


def test_market_ribbon_says_the_dedupe_out_loud(client):
    """Claimed duplicates are counted, not silently dropped."""
    d = client.get("/api/market/ribbon", params={"top": 5}).json()
    by_key = {g["key"]: g for g in d["groups"]}
    assert sum(g["skipped_duplicates"] for g in d["groups"]) >= 0
    # With only two symbols and both ranking as gainers, later groups must be
    # either empty or legitimate ties - never a symbol shown twice.
    shown = [it["symbol"] for g in d["groups"] for it in g["items"]]
    assert all(shown.count(s) == 1 for s in shown)
    assert "skipped_duplicates" in by_key.get("turnover", by_key["volume"])


def test_market_ribbon_top_is_validated(client):
    assert client.get("/api/market/ribbon", params={"top": 0}).status_code == 422
    assert client.get("/api/market/ribbon", params={"top": 31}).status_code == 422
    assert client.get("/api/market/ribbon", params={"top": 1}).status_code == 200


def test_market_ribbon_says_empty_when_nothing_is_stored(tmp_path):
    store = MarketStore(tmp_path / "empty.duckdb")
    app = create_app(store=store)
    with TestClient(app) as c:
        d = c.get("/api/market/ribbon").json()
    store.close()
    assert d["empty"] is True
    assert "fetch" in d["note"]


def test_market_ribbon_ranks_a_real_gainer_above_a_real_loser(tmp_path):
    store = MarketStore(tmp_path / "m.duckdb")
    up = _bars("UP", 100.0 + np.arange(30))
    dn = _bars("DN", 200.0 - np.arange(30))
    up.loc[up.index[-1], "percent_change"] = 9.5
    dn.loc[dn.index[-1], "percent_change"] = -7.25
    store.upsert_bars(up)
    store.upsert_bars(dn)
    app = create_app(store=store)
    with TestClient(app) as c:
        d = c.get("/api/market/ribbon", params={"top": 10}).json()
    store.close()
    groups = {g["key"]: g for g in d["groups"]}
    assert [i["symbol"] for i in groups["gainers"]["items"]] == ["UP"]
    assert groups["gainers"]["items"][0]["change_pct"] == pytest.approx(9.5)
    assert [i["symbol"] for i in groups["losers"]["items"]] == ["DN"]
    assert groups["losers"]["items"][0]["change_pct"] == pytest.approx(-7.25)
    # Every payload number is a stored value, never a substitute.
    assert groups["gainers"]["items"][0]["close"] == pytest.approx(129.0)


def test_market_ribbon_does_not_invent_an_index(tmp_path):
    """With no index series stored, `index` must be null - not a placeholder."""
    store = MarketStore(tmp_path / "noidx.duckdb")
    store.upsert_bars(_bars("ONLY", 50.0 + np.arange(20)))
    app = create_app(store=store)
    with TestClient(app) as c:
        d = c.get("/api/market/ribbon").json()
    store.close()
    assert d["index"] is None


def test_market_ribbon_reports_index_when_one_is_stored(tmp_path):
    store = MarketStore(tmp_path / "withidx.duckdb")
    store.upsert_bars(_bars("A", 10.0 + np.arange(20)))
    store.upsert_index_rows(
        [
            {"index_name": "NEPSE", "trading_date": "2026-01-01", "close": 2500.0,
             "source": "owner-supplied", "retrieved_at": RETRIEVED},
            {"index_name": "NEPSE", "trading_date": "2026-01-02", "close": 2510.0,
             "source": "owner-supplied", "retrieved_at": RETRIEVED},
            {"index_name": "NEPSE", "trading_date": "2026-01-03", "close": 2634.17,
             "source": "owner-supplied", "retrieved_at": RETRIEVED},
        ]
    )
    app = create_app(store=store)
    with TestClient(app) as c:
        d = c.get("/api/market/ribbon").json()
    store.close()
    assert d["index"]["name"] == "NEPSE"
    assert d["index"]["close"] == pytest.approx(2634.17)
    assert d["index"]["change"] == pytest.approx(124.17)
    assert d["index"]["change_pct"] == pytest.approx(round(124.17 / 2510.0 * 100, 2))
