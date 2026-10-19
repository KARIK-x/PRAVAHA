"""Multi-factor ranking tests (Priority 5 of MEGA_TOOL_RESEARCH_REPORT.md).

All data here is synthetic and deterministic. Nothing asserts anything about
real NEPSE prices, and no test claims a ranking predicts future returns.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from megatool.ranking import (
    DEFAULT_WEIGHTS,
    PRICE_FACTORS,
    RELATIVE_STRENGTH_KEY,
    SECTOR_FACTOR_KEY,
    UNAVAILABLE_FACTORS,
    RankConfig,
    build_factor_specs,
    rank_universe,
)


def make_frame(n: int, seed: int, dates: pd.DatetimeIndex) -> pd.DataFrame:
    """Deterministic random-walk OHLCV frame of ``n`` bars."""
    rng = np.random.default_rng(seed)
    if n <= 0:
        return pd.DataFrame(columns=["date", "open", "high", "low", "close", "volume"])
    close = 100.0 * np.cumprod(1.0 + rng.normal(0.0005, 0.012, n))
    return pd.DataFrame(
        {
            "date": dates[:n],
            "open": close,
            "high": close * 1.01,
            "low": close * 0.99,
            "close": close,
            "volume": rng.integers(1_000, 9_000, n).astype(float),
        }
    )


DATES = pd.date_range("2025-01-01", periods=300, freq="B")


@pytest.fixture()
def universe() -> dict[str, pd.DataFrame]:
    return {
        "AAA": make_frame(300, 1, DATES),
        "BBB": make_frame(300, 2, DATES),
        "CCC": make_frame(300, 3, DATES),
        "DDD": make_frame(300, 4, DATES),
    }


# ---------------------------------------------------------------- basics


def test_rank_universe_ranks_every_sufficient_symbol(universe):
    result = rank_universe(universe)
    assert len(result.ranked) == 4
    assert len(result.excluded) == 0
    assert result.universe_size == 4


def test_ranks_are_dense_and_scores_descend(universe):
    result = rank_universe(universe)
    assert [r.rank for r in result.ranked] == [1, 2, 3, 4]
    scores = [r.score for r in result.ranked]
    assert all(s is not None for s in scores)
    assert scores == sorted(scores, reverse=True)


def test_contributions_sum_to_score(universe):
    """Explainability: the per-factor contributions must reproduce the score."""
    for entry in rank_universe(universe).ranked:
        assert entry.contributions
        assert abs(sum(entry.contributions.values()) - entry.score) < 0.01


def test_every_ranked_symbol_carries_percentiles(universe):
    for entry in rank_universe(universe).ranked:
        for key in DEFAULT_WEIGHTS:
            assert key in entry.percentiles
            assert 0.0 <= entry.percentiles[key] <= 100.0


def test_ranking_is_deterministic(universe):
    a = rank_universe(universe)
    b = rank_universe(universe)
    assert [(r.symbol, r.score) for r in a.ranked] == [(r.symbol, r.score) for r in b.ranked]


# ------------------------------------------------------- config & validation


def test_rejects_unknown_factor(universe):
    with pytest.raises(ValueError, match="unknown factor"):
        rank_universe(universe, RankConfig(weights={"not_a_factor": 1.0}))


def test_rejects_all_zero_weights(universe):
    zero = {k: 0.0 for k in DEFAULT_WEIGHTS}
    with pytest.raises(ValueError, match="positive weight"):
        rank_universe(universe, RankConfig(weights=zero))


def test_rejects_negative_weight(universe):
    weights = dict(DEFAULT_WEIGHTS)
    weights["momentum_3m"] = -1.0
    with pytest.raises(ValueError, match="must be >= 0"):
        rank_universe(universe, RankConfig(weights=weights))


def test_rejects_bad_min_bars(universe):
    with pytest.raises(ValueError, match="min_bars"):
        rank_universe(universe, RankConfig(min_bars=0))


def test_rejects_bad_missing_fraction(universe):
    with pytest.raises(ValueError, match="max_missing_fraction"):
        rank_universe(universe, RankConfig(max_missing_fraction=1.5))


# ------------------------------------------------------------ missing data


def test_short_history_symbol_is_excluded_with_reason():
    frames = {
        "AAA": make_frame(300, 1, DATES),
        "TINY": make_frame(30, 2, DATES),
    }
    result = rank_universe(frames, RankConfig(min_bars=60))
    assert [r.symbol for r in result.ranked] == ["AAA"]
    assert [e.symbol for e in result.excluded] == ["TINY"]
    assert "insufficient data" in result.excluded[0].note
    assert "needs 60" in result.excluded[0].note


def test_empty_frame_is_excluded_not_crash():
    frames = {"AAA": make_frame(300, 1, DATES), "GONE": make_frame(0, 2, DATES)}
    result = rank_universe(frames)
    assert [e.symbol for e in result.excluded] == ["GONE"]
    assert "no price history" in result.excluded[0].note


def test_universe_accounting_balances():
    frames = {
        "AAA": make_frame(300, 1, DATES),
        "TINY": make_frame(30, 2, DATES),
        "GONE": make_frame(0, 3, DATES),
    }
    result = rank_universe(frames, RankConfig(min_bars=60))
    assert result.universe_size == 3
    assert len(result.ranked) + len(result.excluded) == 3


def test_missing_factor_is_substituted_and_flagged(universe):
    # Draining the volume column makes volume_trend uncomputable for CCC only.
    broken = {k: v.copy() for k, v in universe.items()}
    broken["CCC"]["volume"] = np.nan
    result = rank_universe(broken)
    entry = next(r for r in result.ranked if r.symbol == "CCC")
    assert entry.complete is False
    assert "volume_trend" in entry.missing
    # Substituted, not zeroed: it still receives a score and a percentile.
    assert entry.score is not None
    assert entry.percentiles["volume_trend"] is not None


def test_symbol_above_missing_threshold_is_excluded(universe):
    broken = {k: v.copy() for k, v in universe.items()}
    # Four of five factors depend on price/volume history beyond the close;
    # wiping volume removes several, pushing CCC past the 50% threshold.
    broken["CCC"]["volume"] = np.nan
    broken["CCC"]["high"] = np.nan
    result = rank_universe(broken, RankConfig(max_missing_fraction=0.0))
    assert "CCC" in [e.symbol for e in result.excluded]
    assert "insufficient data" in next(e for e in result.excluded if e.symbol == "CCC").note


# -------------------------------------------------------- unavailable factors


def test_unavailable_factors_are_declared_not_guessed():
    specs = build_factor_specs()
    unavailable = {s.key for s in specs if not s.available}
    # The static entries plus the two data-driven factors (sector and relative
    # strength), each unavailable with a computed reason whenever its data is
    # not supplied.
    assert unavailable == set(UNAVAILABLE_FACTORS) | {SECTOR_FACTOR_KEY, RELATIVE_STRENGTH_KEY}
    for spec in specs:
        if not spec.available:
            assert spec.weight == 0.0
            assert spec.unavailable_reason


def test_unavailable_factors_surface_in_result(universe):
    result = rank_universe(universe)
    assert set(result.unavailable) == set(UNAVAILABLE_FACTORS) | {
        SECTOR_FACTOR_KEY,
        RELATIVE_STRENGTH_KEY,
    }
    # They must never enter the effective scoring weights.
    assert not (set(result.weights) & set(UNAVAILABLE_FACTORS))
    # The sector reason states the computed no-data condition, not a stale
    # assumption about the store.
    assert "No sector classification data" in result.unavailable[SECTOR_FACTOR_KEY]
    # Relative strength likewise states the measured condition: no benchmark
    # series is connected, so it is not computed against a substitute.
    assert "composite index" in result.unavailable[RELATIVE_STRENGTH_KEY]


def test_price_factors_all_carry_positive_default_weight():
    for key in PRICE_FACTORS:
        if key in (SECTOR_FACTOR_KEY, RELATIVE_STRENGTH_KEY):
            # The two data-driven factors are deliberately weightless by
            # default: they only activate once their data is connected AND the
            # caller chooses a weight, so default rankings are unchanged.
            assert DEFAULT_WEIGHTS.get(key, 0.0) == 0.0
            continue
        assert DEFAULT_WEIGHTS.get(key, 0.0) > 0.0


def test_notes_explain_what_was_dropped(universe):
    result = rank_universe(universe)
    assert any("Unavailable factors" in n for n in result.notes)


# ----------------------------------------------------------------- look-ahead


def test_as_of_truncation_changes_scores():
    """A factor must not see bars after the ranking date."""
    frames = {"AAA": make_frame(300, 1, DATES), "BBB": make_frame(300, 2, DATES)}
    early = rank_universe(frames, RankConfig(as_of="2025-06-30"))
    late = rank_universe(frames, RankConfig(as_of="2026-06-30"))
    assert {r.symbol: r.score for r in early.ranked} != {r.symbol: r.score for r in late.ranked}


def test_as_of_never_reaches_beyond_the_cutoff(universe):
    cutoff = pd.Timestamp("2025-06-30")
    result = rank_universe(universe, RankConfig(as_of="2025-06-30"))
    assert result.as_of == "2025-06-30"
    # Recomputing from an explicitly truncated frame must agree.
    truncated = {k: v[v["date"] <= cutoff] for k, v in universe.items()}
    reference = rank_universe(truncated)
    assert [r.symbol for r in reference.ranked] == [r.symbol for r in result.ranked]


def test_ranking_without_as_of_uses_full_history(universe):
    result = rank_universe(universe)
    assert result.as_of is None


def test_truncation_works_with_store_column_name(universe):
    """MarketStore.get_bars returns ``trading_date``, not ``date``.

    A naming mismatch must not silently disable the look-ahead guard.
    """
    renamed = {k: v.rename(columns={"date": "trading_date"}) for k, v in universe.items()}
    early = rank_universe(renamed, RankConfig(as_of="2025-06-30"))
    late = rank_universe(renamed, RankConfig(as_of="2026-06-30"))
    assert {r.symbol: r.score for r in early.ranked} != {r.symbol: r.score for r in late.ranked}


# -------------------------------------------------------------- factor polarity


def test_higher_is_better_flags_are_declared():
    assert PRICE_FACTORS["volatility"]["higher_is_better"] is False
    for key in ("momentum_3m", "momentum_6m", "volume_trend", "near_52w_high"):
        assert PRICE_FACTORS[key]["higher_is_better"] is True


def test_low_volatility_ranks_higher():
    """Volatility is inverted: the least volatile symbol should not be last."""
    frames = {
        "CALM": make_frame(300, 1, DATES),
        "WILD": make_frame(300, 2, DATES),
    }
    # Make WILD genuinely more volatile.
    wild = frames["WILD"]
    rng = np.random.default_rng(9)
    frames["WILD"] = wild.assign(
        close=wild["close"] * np.cumprod(1.0 + rng.normal(0.0, 0.05, len(wild)))
    )
    result = rank_universe(frames, RankConfig(weights={"volatility": 1.0}))
    vol_pct = {r.symbol: r.percentiles["volatility"] for r in result.ranked}
    assert vol_pct["CALM"] > vol_pct["WILD"]


# ------------------------------------------------------------------ serialisation


def test_result_serialises_to_json_safe_dict(universe):
    import json

    payload = rank_universe(universe).to_dict()
    json.dumps(payload)  # must not raise
    assert payload["universe_size"] == 4
    assert payload["ranked"][0]["rank"] == 1
    assert payload["unavailable"]


def test_weight_override_is_honoured(universe):
    weights = dict(DEFAULT_WEIGHTS)
    weights["momentum_6m"] = 0.0
    result = rank_universe(universe, RankConfig(weights=weights))
    assert "momentum_6m" not in result.weights
    assert all("momentum_6m" not in r.contributions for r in result.ranked)
