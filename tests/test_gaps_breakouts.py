"""Gap + false-breakout detectors: hand-set fixtures rule every label."""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from megatool.api import create_app
from megatool.market_store import MarketStore
from megatool.ta.gaps import GapError, detect_false_breakouts, detect_gaps


def _series(closes):
    high = [c + 0.5 for c in closes]
    low = [c - 0.5 for c in closes]
    return high, low, list(closes)


# ----------------------------------------------------------------------- gaps


def test_gap_up_is_detected_with_facts():
    closes = [10.0] * 20 + [12.0] * 5  # low 11.5 > prior high 10.5 → up gap 1.0
    high, low, close = _series(closes)
    gaps = [
        g
        for g in detect_gaps(high, low, close, common_max_atr=0.25, big_min_atr=0.9)
        if "data_note" not in g
    ]
    assert len(gaps) == 1
    g = gaps[0]
    assert g["direction"] == "up"
    assert g["size"] == pytest.approx(1.0, abs=1e-9)
    assert g["prior_high"] == pytest.approx(10.5, abs=1e-9)
    assert g["gap_low"] == pytest.approx(11.5, abs=1e-9)


def test_gap_class_atr_scale():
    # violent move: 20 flat closes at 10 then a jump to 16 (gap 5.0 on a 1.0 ATR)
    closes = [10.0] * 20 + [16.0, 16.5, 17.0, 16.8, 17.2]
    high, low, close = _series(closes)
    gaps = [
        g
        for g in detect_gaps(high, low, close, big_min_atr=0.9, common_max_atr=0.4)
        if "data_note" not in g
    ]
    g = gaps[0]
    assert g["size_atr"] is not None and g["size_atr"] > 0.9
    # fresh run start (no prior sustained move) → breakaway, not exhaustion
    assert g["class"] == "breakaway"


def test_common_gap_is_noise_scale():
    closes = [100.0] * 20 + [101.3] * 3  # gap 0.8 on ATR ~1.0 → common
    high, low, close = _series(closes)
    gaps = [
        g
        for g in detect_gaps(high, low, close, common_max_atr=0.5, big_min_atr=0.9)
        if "data_note" not in g
    ]
    assert gaps[0]["class"] == "common"


def test_closed_within_bars_is_a_recorded_fact():
    up_gap_then_retrace = [10.0] * 15 + [12.0, 10.2, 10.1]
    high, low, close = _series(up_gap_then_retrace)
    gaps = [
        g
        for g in detect_gaps(high, low, close, common_max_atr=0.25, big_min_atr=0.9)
        if "data_note" not in g
    ]
    g = gaps[0]
    assert g["closed_within_bars"] == 1  # the next session traded back below 10.5


def test_unchanged_gap_reports_open():
    closes = [10.0] * 15 + [12.0] * 5
    high, low, close = _series(closes)
    gaps = [
        g
        for g in detect_gaps(high, low, close, common_max_atr=0.25, big_min_atr=0.9)
        if "data_note" not in g
    ]
    assert gaps[0]["closed_within_bars"] is None


def test_malformed_segment_is_skipped_not_guessed():
    closes = [10.0] * 10 + [float("nan")] + [12.0] * 5
    high = [c + 0.5 for c in closes]
    low = [c - 0.5 for c in closes]
    out = detect_gaps(high, low, list(closes), common_max_atr=0.25, big_min_atr=0.9)
    note = out[0]["data_note"]
    assert "skipped" in note


def test_gap_errors():
    with pytest.raises(GapError, match="same, nonempty"):
        detect_gaps([], [], [])
    with pytest.raises(GapError, match="atr_period"):
        detect_gaps([1.0], [1.0], [1.0], atr_period=0)
    with pytest.raises(GapError, match="thresholds"):
        detect_gaps([1.0] * 40, [1.0] * 40, [1.0] * 40, common_max_atr=0.5, big_min_atr=0.3)


# ------------------------------------------------------------- false breakouts


def test_false_breakout_when_price_returns():
    # 20 bars at 10, then close 11 (level 10.5 → 11 ≥ 10.5×1.005), then back to 10.2
    closes = [10.0] * 20 + [11.0, 10.9, 10.2]
    high, low, close = _series(closes)
    out = detect_false_breakouts(high, low, close, window=10, min_frac=0.005, confirm_bars=3)
    assert len(out) == 1
    b = out[0]
    assert b["side"] == "up" and b["level"] == pytest.approx(10.5, abs=1e-9)
    assert b["status"] == "false" and b["reversed_index"] == 22
    assert b["bars_beyond_level"] == 2


def test_true_breakout_when_it_holds():
    closes = [10.0] * 20 + [11.0, 11.2, 11.1, 11.3]
    high, low, close = _series(closes)
    out = detect_false_breakouts(high, low, close, window=10, min_frac=0.005, confirm_bars=3)
    assert out[0]["status"] == "true"


def test_unconfirmed_breakout_at_window_end():
    closes = [10.0] * 20 + [11.0]
    high, low, close = _series(closes)
    out = detect_false_breakouts(high, low, close, window=10, min_frac=0.005, confirm_bars=3)
    assert out[0]["status"].startswith("unconfirmed")


def test_downside_breakout_symmetry():
    closes = [10.0] * 20 + [9.0, 9.1, 9.6]
    high, low, close = _series(closes)
    out = detect_false_breakouts(high, low, close, window=10, min_frac=0.005, confirm_bars=3)
    b = out[0]
    assert b["side"] == "down"
    assert b["level"] == pytest.approx(9.5, abs=1e-9)
    assert b["status"] == "false"


def test_run_beyond_level_is_measured():
    closes = [10.0] * 20 + [11.0, 12.0, 10.0]
    high = [c + 0.5 for c in closes]
    low = [c - 0.5 for c in closes]
    out = detect_false_breakouts(high, low, list(closes), window=10, min_frac=0.005, confirm_bars=3)
    b = out[0]
    # level = prior-window high 10.5; the peak high reached = 12.5 → run beyond 2.0
    assert b["status"] == "false"
    assert b["run_beyond_level"] == pytest.approx(2.0, abs=1e-9)


def test_breakout_errors():
    with pytest.raises(GapError, match="window"):
        detect_false_breakouts([1.0], [1.0], [1.0], window=1)
    with pytest.raises(GapError, match="min_frac"):
        detect_false_breakouts([1.0] * 40, [1.0] * 40, [1.0] * 40, min_frac=0.9)
    with pytest.raises(GapError, match="confirm_bars"):
        detect_false_breakouts([1.0] * 40, [1.0] * 40, [1.0] * 40, confirm_bars=99)


# ------------------------------------------------------------------- the API


def _client(tmp_path, closes=None):
    import pandas as pd

    store = MarketStore(tmp_path / "market.duckdb")
    if closes is None:
        closes = [100.0 + (i % 5) * 0.3 for i in range(40)]
    dates = pd.bdate_range("2026-01-01", periods=len(closes))
    store.upsert_bars(
        pd.DataFrame(
            {
                "symbol": "AAA",
                "trading_date": dates,
                "open": closes,
                # additive spreads so hand-set levels (prior-high + 0.5) match
                # the module fixtures; gaps/breakouts are priced off real
                # range geometry, not a fixed percent
                "high": [c + 0.5 for c in closes],
                "low": [c - 0.5 for c in closes],
                "close": closes,
                "volume": 1000.0,
                "turnover": [c * 1000.0 for c in closes],
                "percent_change": 0.4,
                "source": "fixture",
                "retrieved_at": pd.Timestamp("2026-10-11"),
                "validation_status": "valid",
            }
        )
    )
    return store, create_app(store=store)


def test_gaps_endpoint_contract(tmp_path):
    store, app = _client(tmp_path)
    with TestClient(app) as c:
        d = c.get("/api/bars/AAA/gaps").json()
    assert d["symbol"] == "AAA"
    assert "gaps" in d or d.get("count", 0) == 0
    for g in d.get("gaps", []):
        assert "class" in g and "size_atr" in g
    store.close()


def test_breakouts_endpoint_contract(tmp_path):
    closes = [10.0] * 20 + [11.0, 10.9, 10.2]
    store, app = _client(tmp_path, closes)
    with TestClient(app) as c:
        d = c.get("/api/bars/AAA/breakouts", params={"window": 10}).json()
    assert d["breakouts"], "the planted false breakout must be found"
    assert d["breakouts"][0]["status"] == "false"
    store.close()
