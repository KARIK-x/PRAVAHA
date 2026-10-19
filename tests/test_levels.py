"""Tests for support/resistance zone clustering.

Fixtures are SYNTHETIC swing points with hand-chosen prices so the expected
zones can be worked out on paper. No market data and no database are touched.
"""

from __future__ import annotations

import pytest

from megatool.ta.levels import build_zones
from megatool.ta.swings import Swing


# SYNTHETIC FIXTURE — explicit prices, not market data.
def swing(index: int, price: float, kind: str = "high") -> Swing:
    return Swing(index=index, kind=kind, price=price, confirmed_index=index + 5, confirmed=True)


def test_empty_swings_is_an_honest_empty_answer_not_an_error():
    out = build_zones([])
    assert out["zones"] == []
    assert out["excluded"] == []
    assert out["interpretation"] == "detected"
    assert any("No swing points" in w for w in out["warnings"])


def test_repeated_nearby_levels_cluster_into_one_zone():
    # Three highs within 1% of each other -> one zone spanning them.
    swings = [swing(1, 100.0), swing(3, 100.5), swing(5, 101.0)]
    out = build_zones(swings, tolerance_frac=0.02)
    assert len(out["zones"]) == 1
    zone = out["zones"][0]
    assert zone["swing_count"] == 3
    assert zone["lower"] == pytest.approx(100.0)
    assert zone["upper"] == pytest.approx(101.0)
    assert zone["center"] == pytest.approx(100.5)
    assert zone["reactions"] == 3


def test_widely_separated_levels_stay_separate_zones():
    swings = [swing(1, 100.0), swing(3, 200.0), swing(5, 300.0)]
    out = build_zones(swings, tolerance_frac=0.02)
    assert len(out["zones"]) == 3
    assert sorted(z["center"] for z in out["zones"]) == [100.0, 200.0, 300.0]


def test_single_swing_is_excluded_from_primary_but_still_reported():
    out = build_zones([swing(1, 100.0)], min_touches=2)
    assert out["zones"] == []
    assert len(out["excluded"]) == 1
    assert out["counts"] == {"total": 1, "reported": 0, "excluded": 1}
    assert any("excluded" in w for w in out["warnings"])


def test_single_swing_is_kept_when_min_touches_is_one():
    out = build_zones([swing(1, 100.0)], min_touches=1)
    assert len(out["zones"]) == 1
    assert out["zones"][0]["swing_count"] == 1


def test_equal_prices_cluster_together_and_do_not_divide_by_zero():
    swings = [swing(1, 50.0), swing(2, 50.0), swing(3, 50.0)]
    out = build_zones(swings, tolerance_frac=0.01)
    assert len(out["zones"]) == 1
    assert out["zones"][0]["center"] == pytest.approx(50.0)
    assert out["zones"][0]["width"] == pytest.approx(0.0)
    assert out["zones"][0]["span"] == pytest.approx(0.0)


def test_output_is_sorted_by_center_ascending_and_deterministic():
    swings = [swing(1, 300.0), swing(2, 100.0), swing(3, 200.0)]
    a = build_zones(swings, tolerance_frac=0.01)
    b = build_zones(list(reversed(swings)), tolerance_frac=0.01)
    centers = [z["center"] for z in a["zones"]]
    assert centers == sorted(centers)
    # Input order must not change the result.
    assert [z["center"] for z in b["zones"]] == centers
    assert a["zones"] == b["zones"]


def test_tighter_tolerance_produces_more_zones():
    swings = [swing(1, 100.0), swing(3, 101.5), swing(5, 103.0)]
    wide = build_zones(swings, tolerance_frac=0.05)
    tight = build_zones(swings, tolerance_frac=0.005)
    assert len(tight["zones"]) >= len(wide["zones"])


def test_tolerance_boundary_is_inclusive():
    # Centre starts at 100; a swing 2.0 away with tolerance exactly 2.0 joins.
    swings = [swing(1, 100.0), swing(2, 102.0)]
    joined = build_zones(swings, tolerance_frac=0.02)
    assert len(joined["zones"]) == 1
    # Just outside the same tolerance, it splits.
    split = build_zones(swings, tolerance_frac=0.019)
    assert len(split["zones"]) == 2


def test_distance_from_latest_close_and_side():
    swings = [swing(1, 90.0, "low"), swing(2, 110.0, "high")]
    out = build_zones(swings, close=[100.0], tolerance_frac=0.01, min_touches=1)
    by_center = {z["center"]: z for z in out["zones"]}
    support = by_center[90.0]
    resistance = by_center[110.0]
    assert support["distance_from_latest_close"] == pytest.approx(10.0)
    assert support["side"] == "support"
    assert resistance["distance_from_latest_close"] == pytest.approx(-10.0)
    assert resistance["side"] == "resistance"
    assert out["latest_close"] == pytest.approx(100.0)


def test_distance_is_unknown_without_close_prices():
    out = build_zones([swing(1, 100.0)], min_touches=1)
    assert out["latest_close"] is None
    assert out["zones"][0]["distance_from_latest_close"] is None
    assert out["zones"][0]["side"] == "unknown"
    assert any("distance from latest close is unknown" in w for w in out["warnings"])


def test_atr_mode_uses_atr_when_supplied():
    swings = [swing(1, 100.0), swing(2, 104.0), swing(3, 108.0)]
    price_mode = build_zones(swings, tolerance_frac=0.01)
    atr_mode = build_zones(swings, tolerance_mode="atr", atr_multiple=1.0, atr=[2.0, 2.0, 2.0])
    # tolerance 1*2.0 = 2.0 (a real constant), reported as an absolute.
    assert atr_mode["params"]["tolerance_mode"] == "atr"
    assert atr_mode["tolerance"] == pytest.approx(2.0)
    assert "ATR" in atr_mode["tolerance_note"]
    # Price mode has no single absolute: it varies per zone, and says so
    # rather than reporting one misleading number.
    assert price_mode["params"]["tolerance_mode"] == "price"
    assert price_mode["tolerance"] is None
    assert "varies per zone" in price_mode["tolerance_note"]


def test_atr_mode_falls_back_and_warns_when_no_atr_given():
    out = build_zones([swing(1, 100.0), swing(2, 100.5)], tolerance_mode="atr")
    assert out["params"]["tolerance_mode"] == "price"
    assert any("fell back" in w for w in out["warnings"])


def test_method_and_version_are_reported():
    out = build_zones([swing(1, 100.0)], min_touches=1)
    assert out["method"] == "swing-cluster"
    assert out["method_version"] == "1.0"


def test_caveats_state_the_zone_is_not_liquidity():
    out = build_zones([swing(1, 100.0)], min_touches=1)
    assert any("not order-book liquidity" in c for c in out["caveats"])
    assert any("will hold" in c for c in out["caveats"])


def test_no_confidence_percentage_anywhere_in_the_output():
    out = build_zones([swing(1, 100.0), swing(2, 100.2)], min_touches=1)

    def walk(node):
        if isinstance(node, dict):
            for k, v in node.items():
                assert "confidence" not in str(k).lower()
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(out)


@pytest.mark.parametrize(
    "kwargs",
    [
        {"tolerance_frac": 0.0},
        {"tolerance_frac": -0.1},
        {"tolerance_mode": "bogus"},
        {"atr_multiple": 0.0},
        {"min_touches": 0},
    ],
)
def test_invalid_parameters_rejected(kwargs):
    from megatool.ta.levels import ZonesError

    with pytest.raises(ZonesError):
        build_zones([swing(1, 100.0)], **kwargs)


def test_non_finite_prices_rejected():
    from megatool.ta.levels import ZonesError

    with pytest.raises(ZonesError, match="finite"):
        build_zones([swing(1, float("nan"))], min_touches=1)


def test_large_price_moves_do_not_break_clustering():
    swings = [swing(i, 100.0 * (1.5**i)) for i in range(6)]
    out = build_zones(swings, tolerance_frac=0.01, min_touches=1)
    assert len(out["zones"]) == 6
    for zone in out["zones"]:
        assert zone["lower"] <= zone["upper"]


def test_zone_boundaries_bracket_every_member_price():
    swings = [swing(1, 100.0), swing(2, 100.4), swing(3, 99.8)]
    out = build_zones(swings, tolerance_frac=0.02, min_touches=1)
    zone = out["zones"][0]
    for price in (100.0, 100.4, 99.8):
        assert zone["lower"] <= price <= zone["upper"]
