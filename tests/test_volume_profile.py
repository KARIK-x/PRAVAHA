"""Volume profile: exact distribution arithmetic + endpoint contract.

The bars here are synthetic and hand-set so every landmark is checkable; the
live endpoint is separately exercised against the real store in the closing
tests of this file.
"""

from __future__ import annotations

import pandas as pd
import pytest
from fastapi.testclient import TestClient

from megatool.api import create_app
from megatool.market_store import MarketStore
from megatool.ta.profile import ProfileError, volume_profile

# ------------------------------------------------------------------ arithmetic


def test_poc_and_value_area_on_hand_set_bins():
    # bins: 4 over [5, 35] → width 7.5 (edges 5 | 12.5 | 20 | 27.5 | 35)
    # A [10,20] vol 200: overlap 2.5 → 50 to bin0, 7.5 → 150 to bin1
    # B [20,30] vol 150: 7.5 → 112.5 to bin2, 2.5 → 37.5 to bin3
    # C [5,35] vol 200: 7.5 in every bin → 50 each; totals [100, 200, 162.5, 87.5]
    highs = [20.0, 30.0, 35.0]
    lows = [10.0, 20.0, 5.0]
    vols = [200.0, 150.0, 200.0]
    p = volume_profile(highs, lows, vols, bins=4)
    assert p["bins_count"] == 4
    assert p["total_volume"] == pytest.approx(550.0, abs=1e-6)
    assert p["poc"]["bin"] == 1
    assert p["poc"]["price"] == pytest.approx(16.25, abs=1e-6)
    # value area from bin1: +bin2 (162.5 beats bin0's 100) → 362.5 < 385,
    # then +bin0 → 462.5 ≥ 385 → VA spans bins 0..2
    assert p["value_area"]["low"] == pytest.approx(5.0, abs=1e-6)
    assert p["value_area"]["high"] == pytest.approx(27.5, abs=1e-6)
    assert p["value_area"]["volume_pct"] == pytest.approx(462.5 / 550.0 * 100.0, abs=0.05)
    assert p["usable_bars"] == 3 and p["skipped_bars"] == 0


def test_poc_tie_resolves_to_the_lower_price():
    # two bins over [1,3]; bar A [1,2] → bin0, bar B [2,3] → bin1, equal volume
    highs = [2.0, 3.0]
    lows = [1.0, 2.0]
    vols = [100.0, 100.0]
    p = volume_profile(highs, lows, vols, bins=2)
    assert p["poc"]["bin"] == 0  # tie → the lower price, as documented
    assert p["poc"]["tie_policy"] == "equal bins resolve to the lower price"


def test_tie_does_not_favour_the_later_bar():
    # the same two bars, listed in the opposite order (each bar still has
    # low <= high): the POC must not drift to the later one
    highs = [3.0, 2.0]
    lows = [2.0, 1.0]
    vols = [100.0, 100.0]
    p = volume_profile(highs, lows, vols, bins=2)
    assert p["poc"]["bin"] == 0


def test_hvn_lvn_strict_local_rules():
    # five single-price bars spread over their own 5-bin range [1.72, 4.28]
    # (width 0.512; the fixture re-derives the range from the bars, so the
    # expected centres below are the profile's actual ones).
    centres = [1.72, 2.36, 3.0, 3.64, 4.28]
    vols = [10.0, 100.0, 20.0, 5.0, 60.0]
    p = volume_profile(centres, centres, vols, bins=5)
    # each bar is one price → one bin: sums [10, 100, 20, 5, 60]
    # strict-peak HVN at bin1 = 2.488; edges excluded; LVN bin3 = 3.512.
    assert p["high_volume_nodes"] == [pytest.approx(2.488, abs=1e-6)]
    assert p["low_volume_nodes"] == [pytest.approx(3.512, abs=1e-6)]


def test_plateau_is_neither_hvn_nor_lvn():
    highs = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]
    lows_array = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]
    vols = [50.0, 100.0, 100.0, 100.0, 50.0, 70.0]
    p = volume_profile(highs, lows_array, vols, bins=6)
    # 6 bins over [1,6] have width 5/6; the single-price bars land in bins
    # [50,100,100,100,50,70]: middle plateau ⇒ no strict peak; edges excluded;
    # bin4 (50) is strictly below its neighbours 100 and 70 → its centre 4.75.
    assert p["high_volume_nodes"] == []
    assert p["low_volume_nodes"] == [pytest.approx(4.75, abs=1e-6)]


def test_skips_malformed_rows_and_zero_volume_without_estimating():
    highs = [1.0, float("nan"), 3.0]
    lows = [0.5, 2.0, 3.0]
    vols = [100.0, 5.0, 0.0]
    p = volume_profile(highs, lows, vols, bins=2)
    assert p["usable_bars"] == 1  # only the well-formed bar with volume>0
    assert p["skipped_bars"] == 2
    assert p["total_volume"] == pytest.approx(100.0, abs=1e-9)


def test_errors():
    with pytest.raises(ProfileError, match="no usable bars"):
        volume_profile([], [], [], bins=10)
    with pytest.raises(ProfileError, match="bins must be >= 2"):
        volume_profile([1.0], [1.0], [10.0], bins=1)
    with pytest.raises(ProfileError, match="same length"):
        volume_profile([1.0, 2.0], [1.0], [10.0, 20.0], bins=4)
    with pytest.raises(ProfileError, match="every supplied bar is unusable"):
        volume_profile([float("nan")], [1.0], [10.0], bins=4)
    with pytest.raises(ProfileError, match="every supplied bar is unusable"):
        volume_profile([1.0], [1.0], [-1.0], bins=4)


def test_single_price_window_is_flat_and_honest():
    p = volume_profile([2.0, 2.0], [2.0, 2.0], [10.0, 20.0], bins=10)
    assert p["bins_count"] == 1
    assert p["poc"]["price"] == 2.0
    assert p["value_area"]["high"] == 2.0 and p["value_area"]["low"] == 2.0
    assert p["total_volume"] == pytest.approx(30.0, abs=1e-9)


# ------------------------------------------------------------------- the API


def _store_with_bars(tmp_path, closes=((100.0, 10.0), (110.0, 40.0), (95.0, 5.0))):
    store = MarketStore(tmp_path / "market.duckdb")
    dates = pd.bdate_range("2026-01-01", periods=len(closes))
    highs, vols = [], []
    lows = []
    for c, v in closes:
        highs.append(c * 1.05)
        lows.append(c * 0.95)
        vols.append(v)
    store.upsert_bars(
        pd.DataFrame(
            {
                "symbol": "AAA",
                "trading_date": dates,
                "open": [c for (c, _) in closes],
                "high": highs,
                "low": lows,
                "close": [c for (c, _) in closes],
                "volume": vols,
                "turnover": [c * v for (c, v) in closes],
                "percent_change": 0.5,
                "source": "fixture",
                "retrieved_at": pd.Timestamp("2026-10-11"),
                "validation_status": "valid",
            }
        )
    )
    return store, create_app(store=store)


def test_volume_profile_endpoint_for_a_known_symbol(tmp_path):
    store, app = _store_with_bars(tmp_path)
    with TestClient(app) as c:
        d = c.get("/api/bars/AAA/volume-profile", params={"bins": 10}).json()
    prof = d["profile"]
    assert d["sessions_used"] == 3
    assert prof["poc"]["price"] > 0 and prof["total_volume"] > 0
    assert prof["poc"]["price"] >= prof["value_area"]["low"]
    assert prof["poc"]["price"] <= prof["value_area"]["high"]
    assert "allocation model" in prof["allocation_model"]
    assert d["first_date"] == "2026-01-01" and d["last_date"]
    assert "not a forecast" in d["source"]
    store.close()


def test_volume_profile_endpoint_404_unknown_symbol(tmp_path):
    store, app = _store_with_bars(tmp_path)
    with TestClient(app) as c:
        r = c.get("/api/bars/ZZZ/volume-profile")
    assert r.status_code == 404
    store.close()


def test_volume_profile_endpoint_rejects_bad_bins(tmp_path):
    store, app = _store_with_bars(tmp_path)
    with TestClient(app) as c:
        assert c.get("/api/bars/AAA/volume-profile", params={"bins": 3}).status_code == 422
        assert c.get("/api/bars/AAA/volume-profile", params={"bins": 900}).status_code == 422
    store.close()
