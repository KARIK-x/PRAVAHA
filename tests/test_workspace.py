"""Tests for the unified research workspace and its honest module states.

The store fixture is a SYNTHETIC zigzag with hand-chosen closes, so swing
detection and therefore Fibonacci/S-R anchoring are unambiguous. No production
database is opened.
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from megatool.api import create_app
from megatool.market_store import MarketStore

RETRIEVED = pd.Timestamp("2026-10-13 00:00:00")

VALID_STATES = {
    "NOT_STARTED",
    "QUEUED",
    "RUNNING",
    "COMPLETED",
    "COMPLETED_WITH_WARNINGS",
    "FAILED",
    "BLOCKED_BY_MISSING_DATA",
    "CANCELLED",
    "CACHED_RESULT_AVAILABLE",
}

# SYNTHETIC FIXTURE — a zigzag with unambiguous turning points.
CLOSE = np.array(
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


@pytest.fixture()
def ws_client(tmp_path):
    store = MarketStore(tmp_path / "ws.duckdb")
    dates = pd.bdate_range("2026-01-01", periods=len(CLOSE))
    df = pd.DataFrame(
        {
            "symbol": "ZZ",
            "trading_date": dates,
            "open": CLOSE,
            "high": CLOSE + 0.5,
            "low": CLOSE - 0.5,
            "close": CLOSE,
            "volume": np.full(len(CLOSE), 10_000, dtype=np.int64),
            "turnover": CLOSE * 10_000,
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


def test_workspace_returns_overview_and_modules(ws_client):
    d = ws_client.get("/api/research/workspace/ZZ").json()
    assert d["symbol"] == "ZZ"
    assert d["method"] == "research-workspace"
    assert d["overall_state"] in VALID_STATES
    assert len(d["modules"]) >= 6
    for m in d["modules"]:
        assert m["name"]
        assert m["label"]
        assert m["state"] in VALID_STATES, m["name"]
        assert m["started_at"] and m["completed_at"]
        assert m["elapsed_ms"] is not None and m["elapsed_ms"] >= 0


def test_workspace_overview_is_dated_and_not_called_live(ws_client):
    d = ws_client.get("/api/research/workspace/ZZ").json()
    ov = d["overview"]
    assert ov["last_close"] == pytest.approx(CLOSE[-1])
    assert ov["observation_date"]
    assert ov["first_date"] and ov["last_date"]
    assert "not a live price" in ov["price_kind"]
    # Change must come from the last two stored closes.
    assert ov["change"] == pytest.approx(CLOSE[-1] - CLOSE[-2])
    # Overview rounds to 4 dp, so the tolerance must match that precision.
    assert ov["change_percent"] == pytest.approx(
        (CLOSE[-1] - CLOSE[-2]) / CLOSE[-2] * 100, abs=1e-4
    )
    assert ov["provenance"]["source"] == "synthetic-zigzag-fixture"


def test_workspace_does_not_invent_a_percentage_or_recommendation(ws_client):
    raw = ws_client.get("/api/research/workspace/ZZ").text.lower()
    assert "confidence" not in raw
    assert '"buy"' not in raw and '"sell"' not in raw


def test_workspace_is_deterministic_in_structure(ws_client):
    a = ws_client.get("/api/research/workspace/ZZ").json()
    b = ws_client.get("/api/research/workspace/ZZ").json()
    assert [m["name"] for m in a["modules"]] == [m["name"] for m in b["modules"]]
    assert a["symbol"] == b["symbol"]
    assert a["overall_state"] == b["overall_state"]


def test_workspace_module_filter_runs_only_requested_modules(ws_client):
    d = ws_client.get("/api/research/workspace/ZZ", params={"modules": "overview"}).json()
    states = {m["name"]: m["state"] for m in d["modules"]}
    assert states["overview"] in {"COMPLETED", "COMPLETED_WITH_WARNINGS"}
    # Everything not requested is honestly NOT_STARTED, not faked as complete.
    for name, state in states.items():
        if name != "overview":
            assert state == "NOT_STARTED", (name, state)


def test_workspace_rejects_unknown_module_name(ws_client):
    r = ws_client.get("/api/research/workspace/ZZ", params={"modules": "nonsense"})
    assert r.status_code == 400
    assert "unknown module" in r.json()["detail"]


def test_workspace_404_for_unknown_symbol(ws_client):
    assert ws_client.get("/api/research/workspace/ZZZZ").status_code == 404


def test_workspace_rejects_impossible_limit(ws_client):
    assert ws_client.get("/api/research/workspace/ZZ", params={"limit": 1}).status_code == 422


def test_workspace_records_input_window_and_timestamp(ws_client):
    d = ws_client.get("/api/research/workspace/ZZ").json()
    inp = d["input"]
    assert inp["start"] and inp["end"] and inp["latest"]
    assert inp["bars"] == len(CLOSE)
    assert d["calculated_at"]
    # `limit_applied` is the requested bound, so it can only be >= actual bars.
    assert d["limit_applied"] >= d["input"]["bars"]


def test_workspace_structure_module_carries_swings_with_dates(ws_client):
    d = ws_client.get("/api/research/workspace/ZZ", params={"modules": "structure"}).json()
    mod = next(m for m in d["modules"] if m["name"] == "structure")
    assert mod["state"] in {"COMPLETED", "COMPLETED_WITH_WARNINGS"}, (
        mod["state"],
        mod["error"],
    )
    swings = mod["result"]["swings"]
    assert swings
    for s in swings:
        assert s["date"] and s["confirmed_date"]
        assert s["confirmed_index"] >= s["index"]


def test_workspace_fibonacci_module_is_labelled_calculated(ws_client):
    d = ws_client.get("/api/research/workspace/ZZ", params={"modules": "overview,fibonacci"}).json()
    mod = next(m for m in d["modules"] if m["name"] == "fibonacci")
    assert mod["state"] in {"COMPLETED", "COMPLETED_WITH_WARNINGS"}, (
        mod["state"],
        mod["error"],
    )
    assert mod["classification"] == "CALCULATED"
    assert mod["result"]["anchors"]["start_date"]
    assert any("convention" in w for w in mod["warnings"])


def test_workspace_levels_module_is_labelled_detected(ws_client):
    d = ws_client.get("/api/research/workspace/ZZ", params={"modules": "overview,levels"}).json()
    mod = next(m for m in d["modules"] if m["name"] == "levels")
    assert mod["state"] in {"COMPLETED", "COMPLETED_WITH_WARNINGS"}, (
        mod["state"],
        mod["error"],
    )
    assert mod["classification"] == "DETECTED"
    assert mod["result"]["method"] == "swing-cluster"


def test_workspace_records_failed_modules_without_hiding_them(ws_client):
    """A failing module must be visible with an error, not silently dropped."""
    d = ws_client.get("/api/research/workspace/ZZ").json()
    for m in d["modules"]:
        if m["state"] in {"FAILED", "BLOCKED_BY_MISSING_DATA"}:
            assert m["error"], m["name"]
            assert m["result"] is None
            assert m["name"] in {f["name"] for f in d["failed"]}


def test_workspace_overall_state_reflects_module_failures(ws_client):
    d = ws_client.get("/api/research/workspace/ZZ").json()
    failures = [m for m in d["modules"] if m["state"] in {"FAILED", "BLOCKED_BY_MISSING_DATA"}]
    if failures:
        assert d["overall_state"] in {"FAILED", "COMPLETED_WITH_WARNINGS"}
    assert set(d["state_counts"]) <= VALID_STATES
    assert sum(d["state_counts"].values()) == len(d["modules"])


def test_workspace_caveats_state_historical_not_live(ws_client):
    d = ws_client.get("/api/research/workspace/ZZ").json()
    joined = " ".join(d["caveats"])
    assert "not live quotes" in joined
    assert "investment advice" in joined
    assert d["classification_note"]


def test_workspace_respects_bar_limit(ws_client):
    d = ws_client.get("/api/research/workspace/ZZ", params={"limit": 30}).json()
    assert d["input"]["bars"] == 30
    assert d["limit_applied"] == 30
    assert d["input"]["end"]  # window is still dated


# ---------------------------------------------------------------------------
# Trend / momentum / volatility summary
#
# Every expected value below is recomputed here from the textbook definition
# rather than by calling the implementation a second time: a bug that cancels
# out across two calls to the same code would survive a round-trip check.
# ---------------------------------------------------------------------------

SUMMARY = "trend_momentum_volatility"


def _summary_module(d):
    hits = [m for m in d["modules"] if m["name"] == SUMMARY]
    assert hits, f"{SUMMARY} module missing from the workspace payload"
    return hits[0]


def _wilder_rsi(close, period=14):
    """Textbook Wilder RSI: seed with the simple mean of the first `period`
    gains and losses, then smooth recursively. Written from the definition."""
    c = np.asarray(close, dtype=float)
    delta = np.diff(c)
    gain = np.where(delta > 0, delta, 0.0)
    loss = np.where(delta < 0, -delta, 0.0)
    ag = [gain[:period].mean()]
    al = [loss[:period].mean()]
    alpha = 1.0 / period
    for i in range(period, len(delta)):
        ag.append(ag[-1] * (1 - alpha) + gain[i] * alpha)
        al.append(al[-1] * (1 - alpha) + loss[i] * alpha)
    # One reading per bar from the seed onward; the summary reports the last.
    series = 100.0 - 100.0 / (1.0 + np.array(ag) / np.array(al))
    return float(series[-1])


def _true_range(high, low, close):
    """Standard TR: the largest of (h-l), |h-prev close|, |l-prev close|."""
    hi, lo, cl = (pd.Series(x) for x in (high, low, close))
    prev = cl.shift()
    prev.iloc[0] = cl.iloc[0]
    return pd.concat([hi - lo, (hi - prev).abs(), (lo - prev).abs()], axis=1).max(axis=1)


def test_workspace_summary_module_completes(ws_client):
    d = ws_client.get("/api/research/workspace/ZZ").json()
    m = _summary_module(d)
    assert m["state"] in {"COMPLETED", "COMPLETED_WITH_WARNINGS"}, m["error"]
    assert m["error"] is None
    assert m["elapsed_ms"] is not None and m["elapsed_ms"] >= 0
    r = m["result"]
    for section in ("trend", "momentum", "volatility", "volume_stats", "interpretation"):
        assert section in r, f"missing {section}"
    assert r["generated_from"] == f"ohlc({len(CLOSE)} bars)"


def test_workspace_summary_reaches_the_latest_stored_bar(ws_client):
    """A "current state" summary that stops early is stale, not merely shorter.
    Regression: when one corrupt bar split the window, the summary used to end
    five months before the latest bar on real data."""
    d = ws_client.get("/api/research/workspace/ZZ").json()
    latest = str(pd.bdate_range("2026-01-01", periods=len(CLOSE))[-1].date())
    assert _summary_module(d)["result"]["last_time"] == latest


def test_workspace_summary_matches_textbook_computations(ws_client):
    d = ws_client.get("/api/research/workspace/ZZ").json()
    r = _summary_module(d)["result"]
    closes = pd.Series(CLOSE)

    sma_short = closes.rolling(10).mean().iloc[-1]
    sma_long = closes.rolling(30).mean().iloc[-1]
    assert r["trend"]["sma_short"] == pytest.approx(sma_short, abs=1e-9)
    assert r["trend"]["sma_long"] == pytest.approx(sma_long, abs=1e-9)
    assert r["trend"]["price_vs_sma_short_pct"] == pytest.approx(
        (CLOSE[-1] / sma_short - 1) * 100, abs=1e-9
    )

    # ROC(12): change against the close 12 bars earlier.
    assert r["momentum"]["roc_pct"] == pytest.approx((CLOSE[-1] / CLOSE[-13] - 1) * 100, abs=1e-9)

    # RSI must follow Wilder's definition specifically — a different smoothing
    # (e.g. an ewm seeded from its own first observation) lands in the same
    # band and would look plausible while being wrong.
    assert r["momentum"]["rsi"] == pytest.approx(_wilder_rsi(CLOSE), abs=1e-9)

    tr = _true_range(CLOSE + 0.5, CLOSE - 0.5, CLOSE)
    assert r["volatility"]["atr"] == pytest.approx(tr.rolling(14).mean().iloc[-1], abs=1e-9)
    assert r["volatility"]["atr"] > 0


def test_workspace_summary_numbers_stay_inside_their_documented_ranges(ws_client):
    d = ws_client.get("/api/research/workspace/ZZ").json()
    r = _summary_module(d)["result"]
    mom, vol, tr_ = r["momentum"], r["volatility"], r["trend"]

    assert 0.0 <= mom["rsi"] <= 100.0
    # The zone label must agree with the number it describes.
    if mom["rsi"] >= 70:
        assert mom["rsi_zone"] == "overbought"
    elif mom["rsi"] <= 30:
        assert mom["rsi_zone"] == "oversold"
    else:
        assert mom["rsi_zone"] == "neutral"
    # MACD histogram is an identity, not an independent reading.
    assert mom["macd_histogram"] == pytest.approx(mom["macd"] - mom["macd_signal"], abs=1e-9)
    assert vol["atr"] >= 0 and vol["historical_volatility_pct_annual"] >= 0
    assert tr_["sma_short"] is None or isinstance(tr_["sma_short"], float)


def test_workspace_summary_labels_are_classification_not_recommendation(ws_client):
    d = ws_client.get("/api/research/workspace/ZZ").json()
    m = _summary_module(d)
    r = m["result"]
    assert m["classification"] in {"CALCULATED", "DETECTED", "INTERPRETIVE"}

    # Sections carry their own class: raw arithmetic is CALCULATED, the labels
    # derived from thresholds are DETECTED, and the prose combination is
    # INTERPRETIVE. Collapsing them would overstate the first two.
    assert r["trend"]["label"] == "CALCULATED"
    assert r["momentum"]["label"] == "CALCULATED"
    assert r["volatility"]["label"] == "CALCULATED"
    assert r["trend"]["classification_label"] in {"DETECTED", None}
    assert r["interpretation"]["label"] == "INTERPRETIVE"
    assert r["limitations"], "a summary must state its own limits"


def test_workspace_summary_does_not_fabricate(ws_client):
    d = ws_client.get("/api/research/workspace/ZZ").json()
    m = _summary_module(d)
    blob = json.dumps(m, default=str).lower()
    assert "confidence" not in blob
    assert '"buy"' not in blob and '"sell"' not in blob
    # Nothing invented where the window is too short to measure it.
    trend = m["result"]["trend"]
    if trend.get("intermediate_change_pct") is None:
        assert trend["intermediate_direction"] is None
    if trend.get("adx") is None:
        assert trend["strength"] is None


@pytest.fixture()
def ws_client_bad_ohlc(tmp_path):
    """Same fixture with one bar whose close sits above its own high — the
    exact defect measured across the real store as B-20 (40,446 such bars)."""
    store = MarketStore(tmp_path / "ws_bad.duckdb")
    dates = pd.bdate_range("2026-01-01", periods=len(CLOSE))
    close = CLOSE.copy()
    close[20] = CLOSE[20] + 5.0  # close > high: a candle that cannot trade
    df = pd.DataFrame(
        {
            "symbol": "ZZ",
            "trading_date": dates,
            "open": CLOSE,
            "high": CLOSE + 0.5,
            "low": CLOSE - 0.5,
            "close": close,
            "volume": np.full(len(CLOSE), 10_000, dtype=np.int64),
            "turnover": CLOSE * 10_000,
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


def test_workspace_summary_excludes_the_bad_bar_and_says_so(ws_client_bad_ohlc):
    d = ws_client_bad_ohlc.get("/api/research/workspace/ZZ").json()
    m = _summary_module(d)
    assert m["state"] in {"COMPLETED", "COMPLETED_WITH_WARNINGS"}, m["error"]

    r = m["result"]
    # The bad bar is dropped from the statistics, but the summary must still
    # reach the final bar — otherwise it reports a stale "current" view.
    assert r["generated_from"] == f"ohlc({len(CLOSE) - 1} bars)"
    latest = str(pd.bdate_range("2026-01-01", periods=len(CLOSE))[-1].date())
    assert r["last_time"] == latest

    joined = " ".join(m["warnings"])
    assert "1 of 37 bar(s)" in joined, joined
    assert "were excluded from these statistics" in joined
    assert "were not modified" in joined
    # The window actually used is stated with both ends, not just a count.
    assert str(pd.bdate_range("2026-01-01", periods=len(CLOSE))[0].date()) in joined
    assert latest in joined


def test_workspace_summary_failure_is_reported_not_hidden(ws_client, monkeypatch):
    """When the summary cannot be computed the module must report FAILED with
    the real message — and the other seven modules must still complete."""
    import megatool.ta.summary as summary_mod

    def _boom(*args, **kwargs):
        raise summary_mod.SummaryError("sentinel: summary refused this input")

    monkeypatch.setattr(summary_mod, "build_summary", _boom)

    d = ws_client.get("/api/research/workspace/ZZ").json()
    m = _summary_module(d)
    assert m["state"] == "FAILED"
    assert "sentinel" in m["error"]
    assert m["result"] is None
    assert m["cached"] is False
    # One module failing does not take the page down with it.
    completed = [x for x in d["modules"] if x["state"].startswith("COMPLETED")]
    assert len(completed) >= 5, [x["name"] for x in d["modules"]]
    assert SUMMARY in {entry["name"] for entry in d["failed"]}
