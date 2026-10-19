"""Harmonic XABCD pattern tests (spec §7 / Section 13).

Fixtures are hand-built five-swing structures whose ratios are exact by
construction, so every assertion is an independently computed expected value,
not a restatement of the implementation. Each pattern fixture is checked to
match *only* its own definition — the cross-pattern assertions prove the bands
do not leak.

Covers: candidate creation per pattern, schema honesty (certainty, bands,
invalidation, uncertainty note), the confirmed-swings look-ahead rule,
degenerate-leg handling, NO_MATCH/INSUFFICIENT semantics, the documented
``slack`` knob, and the API contract of ``GET /api/bars/{symbol}/harmonic``.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from megatool.api import create_app
from megatool.market_store import MarketStore
from megatool.ta.harmonic import (
    DEFAULT_SPECS,
    METHOD,
    UNCERTAINTY,
    analyze_harmonic,
)
from megatool.ta.swings import Swing

RETRIEVED = pd.Timestamp("2026-10-11 00:00:00")

VALID_STATUSES = {"CANDIDATE_ONLY", "NO_MATCH", "INSUFFICIENT_EVIDENCE"}


def _swing(index: int, kind: str, price: float, confirmed: bool = True) -> Swing:
    confirmed_index = index + 5 if confirmed else index
    return Swing(
        index=index, kind=kind, price=price, confirmed_index=confirmed_index, confirmed=confirmed
    )


# ------------------------------------------------------------ exact fixtures
# X=100 low -> A=200 high (XA = +100). Every leg below is exact by arithmetic.
def _gartley() -> list[Swing]:
    # AB = 0.618*100 = 61.8 -> B = 138.2; BC = 0.5*61.8 = 30.9 -> C = 169.1;
    # completion 0.786 -> D = 200 - 78.6 = 121.4; CD/BC = 47.7/30.9 = 1.544.
    return [
        _swing(0, "low", 100.0),
        _swing(10, "high", 200.0),
        _swing(20, "low", 138.2),
        _swing(30, "high", 169.1),
        _swing(40, "low", 121.4),
    ]


def _bat() -> list[Swing]:
    # AB = 40 (0.400); BC = 32 (0.800, comfortably inside the 0.886 edge);
    # completion 0.886 -> D = 111.4; CD/BC = 80.6/32 = 2.519.
    return [
        _swing(0, "low", 100.0),
        _swing(10, "high", 200.0),
        _swing(20, "low", 160.0),
        _swing(30, "high", 192.0),
        _swing(40, "low", 111.4),
    ]


def _butterfly() -> list[Swing]:
    # AB = 78.6 (0.786); BC = 39.3 (0.500); external 1.27 -> D = 73.0;
    # CD/BC = 87.7/39.3 = 2.232.
    return [
        _swing(0, "low", 100.0),
        _swing(10, "high", 200.0),
        _swing(20, "low", 121.4),
        _swing(30, "high", 160.7),
        _swing(40, "low", 73.0),
    ]


def _crab() -> list[Swing]:
    # AB = 50 (0.500); BC = 43.5 (0.870, inside the 0.886 edge);
    # external 1.618 -> D = 38.2; CD/BC = 155.3/43.5 = 3.570.
    return [
        _swing(0, "low", 100.0),
        _swing(10, "high", 200.0),
        _swing(20, "low", 150.0),
        _swing(30, "high", 193.5),
        _swing(40, "low", 38.2),
    ]


def _cypher() -> list[Swing]:
    # AB = 50 (0.500); BC = 63.5 (1.270, extends past A);
    # DC/XC = 89.2/113.5 = 0.786 -> D = 124.3.
    return [
        _swing(0, "low", 100.0),
        _swing(10, "high", 200.0),
        _swing(20, "low", 150.0),
        _swing(30, "high", 213.5),
        _swing(40, "low", 124.3),
    ]


def _bearish_gartley() -> list[Swing]:
    # Mirror image: X=200 high -> A=100 low (XA = -100), D = 178.6 high.
    return [
        _swing(0, "high", 200.0),
        _swing(10, "low", 100.0),
        _swing(20, "high", 161.8),
        _swing(30, "low", 130.9),
        _swing(40, "high", 178.6),
    ]


def _symmetric_wave() -> list[Swing]:
    """Perfectly symmetrical legs (AB/XA = 1.0): matches nothing by design."""
    return [
        _swing(0, "low", 100.0),
        _swing(10, "high", 200.0),
        _swing(20, "low", 100.0),
        _swing(30, "high", 200.0),
        _swing(40, "low", 100.0),
    ]


# ------------------------------------------------- one exact match per pattern
@pytest.mark.parametrize(
    ("factory", "expected"),
    [
        (_gartley, "Gartley"),
        (_bat, "Bat"),
        (_butterfly, "Butterfly"),
        (_crab, "Crab"),
        (_cypher, "Cypher"),
    ],
)
def test_each_pattern_matches_only_its_own_definition(factory, expected):
    res = analyze_harmonic(factory())
    assert res["status"] == "CANDIDATE_ONLY"
    assert [c["pattern"] for c in res["candidates"]] == [expected]


def test_bullish_direction_from_low_completion():
    res = analyze_harmonic(_gartley())
    assert res["candidates"][0]["direction"] == "bullish"


def test_bearish_direction_from_mirrored_structure():
    res = analyze_harmonic(_bearish_gartley())
    assert res["status"] == "CANDIDATE_ONLY"
    assert [c["pattern"] for c in res["candidates"]] == ["Gartley"]
    assert res["candidates"][0]["direction"] == "bearish"


# -------------------------------------------------------------- schema/honesty
def test_candidate_schema_and_measured_bands_are_self_consistent():
    res = analyze_harmonic(_gartley())
    (c,) = res["candidates"]
    for key in (
        "pattern",
        "direction",
        "label",
        "points",
        "measures",
        "matched_ranges",
        "invalidation",
        "certainty",
        "evidence",
        "method",
        "uncertainty_note",
    ):
        assert key in c, f"missing candidate key {key}"
    # Never asserted as proven: qualitative low certainty + uncertainty note.
    assert c["certainty"] == "low"
    assert "not a guaranteed" in c["uncertainty_note"]
    assert c["method"] == METHOD
    # The invalidation level names a price.
    assert "price closing beyond" in c["invalidation"]
    # Every reported measurement lies inside the band it claims to match.
    for r in c["matched_ranges"]:
        lo, hi = r["range"]
        assert lo <= r["measured"] <= hi, r
    # Points carry the full swing provenance (indices + confirmation state).
    for pt in ("X", "A", "B", "C", "D"):
        assert {"index", "kind", "price", "confirmed_index", "confirmed"} <= set(c["points"][pt])
    # Structure is strictly alternating XABCD.
    kinds = [c["points"][p]["kind"] for p in "XABCD"]
    assert all(kinds[i] != kinds[i + 1] for i in range(4))


def test_result_envelope_is_stable():
    res = analyze_harmonic(_crab())
    for key in (
        "status",
        "candidates",
        "method",
        "uncertainty",
        "evidence",
        "swings_considered",
        "patterns_tested",
        "windows_tested",
        "message",
    ):
        assert key in res, f"missing result key {key}"
    assert res["uncertainty"] == UNCERTAINTY
    assert (
        res["patterns_tested"]
        == [s.name for s in DEFAULT_SPECS]
        == [
            "Gartley",
            "Bat",
            "Butterfly",
            "Crab",
            "Cypher",
        ]
    )


# ------------------------------------------------------- look-ahead & edges
def test_lookahead_unconfirmed_d_is_excluded():
    """Regression: an unconfirmed D point must never be used.

    With D unconfirmed only 4 swings remain, so no XABCD window exists —
    if the unconfirmed pivot leaked in, a Gartley candidate would appear.
    """
    swings = _gartley()
    swings[-1] = _swing(40, "low", 121.4, confirmed=False)
    res = analyze_harmonic(swings)
    assert res["swings_considered"] == 4
    assert res["status"] == "INSUFFICIENT_EVIDENCE"
    assert res["candidates"] == []
    assert "at least 5 confirmed swings" in res["message"]


def test_none_and_empty_input():
    assert analyze_harmonic(None)["status"] == "INSUFFICIENT_EVIDENCE"
    assert analyze_harmonic([])["status"] == "INSUFFICIENT_EVIDENCE"


def test_degenerate_leg_is_skipped_not_approximated():
    """B == A makes AB zero-length: the window is unmeasurable, never forced."""
    swings = [
        _swing(0, "low", 100.0),
        _swing(10, "high", 200.0),
        _swing(20, "low", 200.0),  # degenerate: same price as A
        _swing(30, "high", 180.0),
        _swing(40, "low", 121.4),
    ]
    res = analyze_harmonic(swings)
    assert res["status"] == "INSUFFICIENT_EVIDENCE"
    assert res["windows_tested"] == 0
    assert "No measurable XABCD window" in res["message"]
    assert res["candidates"] == []


def test_no_match_is_distinct_from_insufficient_evidence():
    res = analyze_harmonic(_symmetric_wave())
    assert res["status"] == "NO_MATCH"
    assert res["windows_tested"] == 1
    assert res["candidates"] == []
    assert "tested against 5 published definitions" in res["message"]


def test_non_alternating_window_is_skipped():
    swings = [
        _swing(0, "low", 100.0),
        _swing(10, "low", 200.0),  # same kind as previous -> not XABCD
        _swing(20, "low", 138.2),
        _swing(30, "high", 169.1),
        _swing(40, "low", 121.4),
    ]
    res = analyze_harmonic(swings)
    assert res["windows_tested"] == 0
    assert res["candidates"] == []


def test_slack_widens_bands_documented_and_bounded():
    # Near-miss Gartley: AB/XA = 0.72, just outside the 0.50-0.700 band.
    swings = [
        _swing(0, "low", 100.0),
        _swing(10, "high", 200.0),
        _swing(20, "low", 128.0),
        _swing(30, "high", 164.0),
        _swing(40, "low", 121.4),
    ]
    assert analyze_harmonic(swings)["status"] == "NO_MATCH"
    slack_res = analyze_harmonic(swings, slack=0.03)
    assert slack_res["status"] == "CANDIDATE_ONLY"
    assert [c["pattern"] for c in slack_res["candidates"]] == ["Gartley"]
    # The widened band is reported honestly, not the published one.
    ab = next(r for r in slack_res["candidates"][0]["matched_ranges"] if r["measure"] == "AB/XA")
    assert ab["range"] == [0.47, 0.73]
    with pytest.raises(ValueError):
        analyze_harmonic(swings, slack=-0.01)


def test_extra_swings_slide_windows_deterministically():
    """Six swings => two windows; identical input gives identical output."""
    swings = _gartley() + [_swing(50, "high", 150.0)]
    a = analyze_harmonic(swings)
    b = analyze_harmonic(swings)
    assert a == b
    assert a["windows_tested"] == 2
    assert [c["pattern"] for c in a["candidates"]] == ["Gartley"]


# ------------------------------------------------------------------- API layer
def _mk_bars(symbol: str, n: int = 160, period: int = 12) -> pd.DataFrame:
    t = np.arange(n)
    tri = np.abs(2 * ((t / period) % 1.0) - 1)
    close = 100.0 + 40.0 * tri
    df = pd.DataFrame(
        {
            "symbol": symbol,
            "trading_date": pd.bdate_range("2025-01-01", periods=n),
            "open": close,
            "high": close + 1.5,
            "low": close - 1.5,
            "close": close,
            "volume": np.full(n, 1000, dtype=np.int64),
        }
    )
    df["turnover"] = df["close"] * df["volume"]
    df["percent_change"] = 1.0
    df["source"] = "synthetic-harmonic-fixture"
    df["retrieved_at"] = RETRIEVED
    df["validation_status"] = "valid"
    return df


@pytest.fixture
def client(tmp_path):
    store = MarketStore(tmp_path / "harmonic.duckdb")
    store.upsert_bars(_mk_bars("ZIG"))
    app = create_app(store=store)
    with TestClient(app) as c:
        yield c
    store.close()


def test_harmonic_route_registered():
    import megatool.api as a

    paths = {getattr(r, "path", None) for r in a.app.routes}
    assert "/api/bars/{symbol}/harmonic" in paths


def test_harmonic_endpoint_contract(client):
    r = client.get("/api/bars/ZIG/harmonic")
    assert r.status_code == 200
    d = r.json()
    for key in (
        "symbol",
        "status",
        "method",
        "uncertainty",
        "evidence",
        "swings_considered",
        "windows_tested",
        "patterns_tested",
        "candidates",
        "message",
    ):
        assert key in d, f"missing envelope key {key}"
    assert d["symbol"] == "ZIG"
    assert d["status"] in VALID_STATUSES
    assert d["patterns_tested"] == ["Gartley", "Bat", "Butterfly", "Crab", "Cypher"]
    # A perfectly symmetric triangle wave retraces 100% on every leg, so it
    # cannot satisfy any harmonic band — a deterministic NO_MATCH.
    assert d["status"] == "NO_MATCH"
    assert d["windows_tested"] > 0
    assert d["uncertainty"]
    for c in d["candidates"]:
        assert c["certainty"] == "low"
        assert c["matched_ranges"]


def test_harmonic_endpoint_errors(client):
    assert client.get("/api/bars/NOSUCH/harmonic").status_code == 404
    assert client.get("/api/bars/THISISWAYTOOLONGSYMBOLXYZ/harmonic").status_code == 400


def test_harmonic_endpoint_insufficient_history(tmp_path):
    store = MarketStore(tmp_path / "short.duckdb")
    df = pd.DataFrame(
        [
            {
                "symbol": "SHRT",
                "trading_date": f"2026-01-0{i + 1}",
                "open": 100 + i,
                "high": 101 + i,
                "low": 99 + i,
                "close": 100 + i,
                "volume": 100,
                "turnover": (100 + i) * 100,
                "percent_change": 1.0,
                "source": "synthetic-harmonic-fixture",
                "retrieved_at": RETRIEVED,
                "validation_status": "valid",
            }
            for i in range(2)
        ]
    )
    store.upsert_bars(df)
    app = create_app(store=store)
    with TestClient(app) as c:
        assert c.get("/api/bars/SHRT/harmonic").status_code == 404
    store.close()
