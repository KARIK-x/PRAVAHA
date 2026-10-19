"""Focused tests for the data-driven ``sector_percentile`` factor (T-M3).

Availability must be derived from the sector data actually supplied for the
run — never from a hard-coded assumption about the store. Three states are
pinned: unavailable data (no usable mapping), insufficient coverage (mapping
present, below the configured threshold), and successfully computed
within-sector percentiles. No value is ever fabricated for a symbol without a
usable sector, and a percentile is never computed inside a group of one.

All data here is synthetic and deterministic; nothing asserts anything about
real NEPSE prices.
"""

from __future__ import annotations

import pandas as pd
import pytest

from megatool.ranking import (
    DEFAULT_WEIGHTS,
    SECTOR_FACTOR_KEY,
    RankConfig,
    rank_universe,
    sector_availability,
)

#: Slopes chosen so return_60d is strictly ordered: strong > mid > weak.
STRONG, MID, WEAK = 0.01, 0.005, 0.001


def _ramp(slope: float, n: int = 121, start: str = "2025-01-01") -> pd.DataFrame:
    """Monotonic close ramp; return over any fixed window rises with slope."""
    closes = [100.0 + slope * i for i in range(n)]
    dates = pd.bdate_range(start, periods=n)
    return pd.DataFrame(
        {
            "date": dates,
            "open": closes,
            "high": [c * 1.001 for c in closes],
            "low": [c * 0.999 for c in closes],
            "close": closes,
            "volume": [1000.0] * n,
        }
    ).sort_values("date")


def _two_sector_universe():
    """Six symbols: three in 'Hydro', three in 'Bank', same slope pattern."""
    frames = {
        "A1": _ramp(STRONG),
        "A2": _ramp(MID),
        "A3": _ramp(WEAK),
        "B1": _ramp(STRONG),
        "B2": _ramp(MID),
        "B3": _ramp(WEAK),
    }
    sectors = {
        "A1": "Hydro",
        "A2": "Hydro",
        "A3": "Hydro",
        "B1": "Bank",
        "B2": "Bank",
        "B3": "Bank",
    }
    return frames, sectors


# --------------------------------------------------------------- unavailable


def test_no_sector_data_is_unavailable_not_computed():
    frames, _ = _two_sector_universe()
    result = rank_universe(frames, RankConfig())
    assert SECTOR_FACTOR_KEY in result.unavailable
    assert "No sector classification data" in result.unavailable[SECTOR_FACTOR_KEY]
    assert result.weights.get(SECTOR_FACTOR_KEY, 0.0) == 0.0
    for entry in result.ranked:
        assert SECTOR_FACTOR_KEY not in entry.contributions
        assert SECTOR_FACTOR_KEY not in entry.percentiles


def test_blank_sectors_are_never_treated_as_a_classification():
    frames, _ = _two_sector_universe()
    # NULL-like values (None / blank strings) are ignored entirely.
    result = rank_universe(
        frames,
        RankConfig(),
        sectors={"A1": None, "A2": "  ", "A3": "", "B1": None, "B2": "", "B3": None},
    )
    assert "No sector classification data" in result.unavailable[SECTOR_FACTOR_KEY]


def test_default_ranking_is_unchanged_without_sector_data():
    frames, sectors = _two_sector_universe()
    baseline = rank_universe(frames, RankConfig())
    explicit_none = rank_universe(frames, RankConfig(), sectors=None)
    empty = rank_universe(frames, RankConfig(), sectors={})
    assert [r.score for r in baseline.ranked] == [r.score for r in explicit_none.ranked]
    assert [r.score for r in baseline.ranked] == [r.score for r in empty.ranked]
    assert [r.rank for r in baseline.ranked] == [r.rank for r in empty.ranked]


def test_empty_universe_is_unavailable_and_reports_no_crash():
    result = rank_universe({}, RankConfig(), sectors={"A1": "Hydro"})
    assert result.universe_size == 0
    assert SECTOR_FACTOR_KEY in result.unavailable
    assert result.ranked == [] and result.excluded == []


# --------------------------------------------------------- insufficient data


def test_insufficient_coverage_is_reported_with_measured_numbers():
    frames, sectors = _two_sector_universe()
    # Only one of six symbols classified: 1/6 = 17% < 50% default threshold.
    sparse = {"A1": "Hydro"}
    result = rank_universe(frames, RankConfig(), sectors=sparse)
    reason = result.unavailable[SECTOR_FACTOR_KEY]
    assert "17%" in reason and "1/6" in reason and "50%" in reason


def test_insufficient_coverage_drops_an_explicit_weight():
    frames, sectors = _two_sector_universe()
    # Even a user who explicitly weights the factor gets honesty, not a
    # percentile computed from 1/6 coverage.
    weights = {**DEFAULT_WEIGHTS, SECTOR_FACTOR_KEY: 0.5}
    result = rank_universe(frames, RankConfig(weights=weights), sectors={"A1": "Hydro"})
    assert "17%" in result.unavailable[SECTOR_FACTOR_KEY]
    assert result.weights.get(SECTOR_FACTOR_KEY, 0.0) == 0.0
    for entry in result.ranked:
        assert SECTOR_FACTOR_KEY not in entry.contributions


def test_coverage_counts_only_usable_sectors_of_ranked_symbols():
    frames, _ = _two_sector_universe()
    # Extra unranked symbols in the mapping must not inflate coverage, and a
    # symbol that fails the min_bars gate is not part of the denominator.
    tiny = _ramp(WEAK, n=10)
    frames["TINY"] = tiny
    status = sector_availability(
        {"A1": "Hydro", "ZZZ": "Bank"}, ["A1", "A2", "A3", "B1", "B2", "B3"], 0.5
    )
    assert status.classified == 1
    assert status.coverage == pytest.approx(1 / 6)


def test_coverage_threshold_is_configurable():
    frames, sectors = _two_sector_universe()
    half = {s: v for s, v in list(sectors.items())[:3]}  # 3/6 = 50%
    at_default = rank_universe(frames, RankConfig(), sectors=half)
    assert SECTOR_FACTOR_KEY not in at_default.unavailable  # meets the 50% bar
    strict = rank_universe(frames, RankConfig(sector_min_coverage=0.9), sectors=half)
    assert "50%" in strict.unavailable[SECTOR_FACTOR_KEY]


def test_invalid_coverage_threshold_is_rejected():
    cfg = RankConfig(sector_min_coverage=1.5)
    assert any("sector_min_coverage" in p for p in cfg.validate())


# ------------------------------------------------------------------ available


def test_within_sector_percentiles_are_computed_not_assumed():
    frames, sectors = _two_sector_universe()
    weights = {**{k: 0.0 for k in DEFAULT_WEIGHTS}, SECTOR_FACTOR_KEY: 1.0}
    result = rank_universe(frames, RankConfig(weights=weights), sectors=sectors)
    assert SECTOR_FACTOR_KEY not in result.unavailable
    by_sym = {r.symbol: r for r in result.ranked}
    # Same slope pattern in both sectors -> identical within-sector percentiles
    # (100 / 66.67 / 33.33), proving the ranking happens inside each sector.
    expected = {
        "A1": 100.0,
        "B1": 100.0,
        "A2": 200 / 3,
        "B2": 200 / 3,
        "A3": 100 / 3,
        "B3": 100 / 3,
    }
    for sym, want in expected.items():
        assert by_sym[sym].percentiles[SECTOR_FACTOR_KEY] == pytest.approx(want), sym
    # Scores reproduce from the single weighted factor.
    assert by_sym["A1"].score == pytest.approx(100.0)
    assert [r.symbol for r in result.ranked][0] == "A1"


def test_symbols_without_sector_are_median_substituted_and_flagged():
    frames, sectors = _two_sector_universe()
    frames["C1"] = _ramp(MID)
    frames["C2"] = _ramp(WEAK)
    weights = {**DEFAULT_WEIGHTS, SECTOR_FACTOR_KEY: 0.3}
    result = rank_universe(frames, RankConfig(weights=weights), sectors=sectors)
    by_sym = {r.symbol: r for r in result.ranked}
    for sym in ("C1", "C2"):
        # No sector -> the factor value is missing, never a guessed number.
        assert SECTOR_FACTOR_KEY in by_sym[sym].missing
        assert by_sym[sym].percentiles[SECTOR_FACTOR_KEY] is None
        assert SECTOR_FACTOR_KEY not in by_sym[sym].contributions
        assert by_sym[sym].complete is False


def test_singleton_sector_is_not_a_fabricated_percentile():
    frames, sectors = _two_sector_universe()
    frames["D1"] = _ramp(STRONG)
    sectors["D1"] = "Solo"  # a group of one has no percentile
    weights = {**DEFAULT_WEIGHTS, SECTOR_FACTOR_KEY: 0.3}
    result = rank_universe(frames, RankConfig(weights=weights), sectors=sectors)
    by_sym = {r.symbol: r for r in result.ranked}
    assert by_sym["D1"].percentiles[SECTOR_FACTOR_KEY] is None
    assert SECTOR_FACTOR_KEY in by_sym["D1"].missing
    # The three-member sectors still compute normally.
    assert by_sym["A1"].percentiles[SECTOR_FACTOR_KEY] == pytest.approx(100.0)


def test_two_member_sector_gets_the_pair_percentiles():
    frames = {"P1": _ramp(WEAK), "P2": _ramp(STRONG)}
    sectors = {"P1": "Pair", "P2": "Pair"}
    result = rank_universe(frames, RankConfig(weights={SECTOR_FACTOR_KEY: 1.0}), sectors=sectors)
    by_sym = {r.symbol: r for r in result.ranked}
    assert by_sym["P1"].percentiles[SECTOR_FACTOR_KEY] == pytest.approx(50.0)
    assert by_sym["P2"].percentiles[SECTOR_FACTOR_KEY] == pytest.approx(100.0)
