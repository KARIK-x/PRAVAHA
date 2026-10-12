"""Research Assistant tests - every expected number is computed by hand."""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from megatool.research import (
    TOPICS,
    _max_drawdown,
    _sma,
    _swing_levels,
    _volatility,
    answer,
    build_report,
)


def _bars(closes, dates=None, volume=1000.0, high=None, low=None):
    closes = np.asarray(closes, dtype=float)
    n = len(closes)
    if dates is None:
        dates = pd.bdate_range("2026-01-01", periods=n)
    return pd.DataFrame(
        {
            "trading_date": pd.to_datetime(list(dates)),
            "open": closes,
            "high": np.asarray(high if high is not None else closes, dtype=float),
            "low": np.asarray(low if low is not None else closes, dtype=float),
            "close": closes,
            "volume": np.full(n, volume, dtype=float),
        }
    )


# ----------------------------------------------------------------- primitives
def test_sma_needs_a_full_window():
    assert _sma(np.arange(1.0, 11.0), 5) == pytest.approx(8.0)
    assert _sma(np.arange(1.0, 4.0), 5) is None


def test_max_drawdown_is_peak_to_trough():
    # peak 110, trough 90 -> (90/110 - 1) * 100
    assert _max_drawdown(np.array([100.0, 110.0, 90.0, 120.0])) == pytest.approx(
        (90 / 110 - 1) * 100
    )


def test_max_drawdown_none_for_short_series():
    assert _max_drawdown(np.array([100.0])) is None


def test_volatility_none_when_returns_are_constant():
    assert _volatility(np.full(50, 100.0), 30) is None


def test_volatility_is_annualised_not_raw():
    rng = np.random.default_rng(3)
    closes = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, 400)))
    v = _volatility(closes, 250)
    assert v is not None
    # daily vol ~1% -> annualised ~16%; assert a plausible band, not a point
    assert 5 < v < 40


def test_swing_levels_detect_an_inverted_v():
    closes = np.concatenate([np.linspace(100, 120, 30), np.linspace(120, 100, 30)])
    levels = _swing_levels(closes, closes)
    assert levels["resistance"], "expected at least one pivot high near 120"
    assert all(p == pytest.approx(120.0) for _, p in levels["resistance"])
    assert levels["support"] == []


def test_swing_levels_need_two_sidebars():
    assert _swing_levels(np.arange(10.0), np.arange(10.0)) == {
        "support": [],
        "resistance": [],
    }


# -------------------------------------------------------------------- report
def test_report_cites_every_finding():
    df = _bars(np.linspace(100, 150, 300))
    r = build_report(df, "TEST")
    assert r.symbol == "TEST"
    assert r.bars == 300
    assert r.findings
    for f in r.findings:
        assert f.window, f.name
        assert f.source, f.name
        assert f.topic in TOPICS


def test_report_is_json_serialisable_with_nested_values():
    df = _bars(np.linspace(100, 150, 300))
    payload = json.dumps(build_report(df, "TEST").to_dict())
    assert "recent_swing_supports" in payload and "weekday_gaps" in payload


def test_trend_figures_match_hand_calculation():
    closes = np.arange(1.0, 201.0)  # 1..200, last = 200
    df = _bars(closes)
    r = build_report(df, "TEST")
    by = {f.name: f.value for f in r.findings}
    assert by["sma_20"] == pytest.approx(float(np.mean(closes[-20:])))  # 190.5
    assert by["price_vs_sma_20_pct"] == pytest.approx((200 / 190.5 - 1) * 100, abs=1e-3)
    assert by["sma_200"] == pytest.approx(100.5)
    assert by["high_250s"] == 200.0
    assert by["low_250s"] == 1.0
    assert by["position_in_52w_range_pct"] == 100.0
    assert by["pct_off_250s_high"] == 0.0


def test_momentum_figures_match_hand_calculation():
    # The step from 100 to 110 happens 21 sessions before the end.
    closes = np.concatenate([np.full(49, 100.0), np.full(21, 110.0)])
    df = _bars(closes)
    r = build_report(df, "TEST")
    by = {f.name: f.value for f in r.findings}
    assert by["return_21d_pct"] == pytest.approx(10.0)
    # 63 sessions back is still in the 100 block, so the same 10% applies.
    assert by["return_63d_pct"] == pytest.approx(10.0)
    assert by["pct_below_20d_high"] == 0.0


def test_risk_figures_match_hand_calculation():
    df = _bars([100.0, 110.0, 90.0, 120.0] + [120.0] * 30)
    r = build_report(df, "TEST")
    by = {f.name: f.value for f in r.findings}
    assert by["worst_day_pct"] == pytest.approx((90 / 110 - 1) * 100)
    # +10.0%, -18.18% and +33.33% all clear the 9.5% detection threshold.
    assert by["limit_move_days"] == 3
    assert by["max_drawdown_all_pct"] == pytest.approx((90 / 110 - 1) * 100)


def test_volume_ratios_match_hand_calculation():
    closes = np.full(100, 100.0)
    volume = np.concatenate([np.full(99, 1000.0), np.array([2000.0])])
    df = _bars(closes, volume=1000.0)
    df["volume"] = volume
    r = build_report(df, "TEST")
    by = {f.name: f.value for f in r.findings}
    # The final 20 sessions are 19 x 1000 + one 2000 = 1050 average.
    assert by["volume_20d_avg"] == pytest.approx(1050.0)
    avg90 = (89 * 1000.0 + 2000.0) / 90.0
    assert by["volume_vs_90d_ratio"] == pytest.approx(1050.0 / avg90, abs=1e-3)
    assert by["last_day_vs_20d_ratio"] == pytest.approx(2000.0 / 1050.0, abs=1e-3)


def test_levels_report_the_pivot_with_its_date_and_distance():
    closes = np.concatenate([np.linspace(120, 80, 30), np.linspace(80, 120, 30)])
    r = build_report(_bars(closes), "TEST")
    supports = next(f.value for f in r.findings if f.name == "recent_swing_supports")
    assert supports, "expected a pivot low"
    assert supports[0]["price"] == pytest.approx(80.0, abs=1e-3)
    assert supports[0]["distance_pct"] == pytest.approx((80 / 120 - 1) * 100, abs=1e-3)
    assert supports[0]["date"].startswith("2026-")


def test_relative_strength_ranks_against_the_universe():
    n = 80
    df = _bars(np.linspace(100, 130, n))
    uni = pd.DataFrame(
        {
            "AAA": np.linspace(100, 130, n),
            "BBB": np.linspace(100, 110, n),
            "CCC": np.linspace(100, 90, n),
        },
        index=pd.bdate_range("2026-01-01", periods=n),
    )
    r = build_report(df, "AAA", universe=uni)
    rel = {f.name: f for f in r.findings if f.topic == "relative"}
    by = {k: f.value for k, f in rel.items()}
    assert by["rank_of_stored_symbols"] == 1
    assert rel["rank_of_stored_symbols"].unit == "of 3"
    window = uni.iloc[-63:]
    rets = {c: (window[c].iloc[-1] / window[c].iloc[0] - 1) * 100 for c in uni.columns}
    assert by["return_3m_pct"] == pytest.approx(rets["AAA"], abs=1e-3)
    assert by["peer_median_3m_pct"] == pytest.approx(
        float(np.median([rets["BBB"], rets["CCC"]])), abs=1e-3
    )


def test_relative_strength_measures_the_window_not_the_lifetime():
    # A stock that doubled long ago but is flat over the ranking window must
    # not be reported as a strong 3-month performer.
    n = 200
    closes = np.concatenate([np.full(100, 100.0), np.full(100, 200.0), np.full(40, 200.0)])
    closes = closes[:200]
    closes[-63:] = 200.0  # flat across the ranking window
    df = _bars(closes)
    uni = pd.DataFrame(
        {"AAA": closes, "BBB": np.full(n, 50.0)}, index=pd.bdate_range("2026-01-01", periods=n)
    )
    r = build_report(df, "AAA", universe=uni)
    by = {f.name: f.value for f in r.findings if f.topic == "relative"}
    assert by["return_3m_pct"] == pytest.approx(0.0, abs=1e-9)


def test_no_relative_block_without_a_universe():
    r = build_report(_bars(np.linspace(100, 150, 300)), "TEST")
    assert not any(f.topic == "relative" for f in r.findings)


def test_gaps_count_missing_weekdays():
    dates = pd.bdate_range("2026-01-01", periods=10).delete([3, 4])  # drop two sessions
    r = build_report(_bars(np.full(8, 100.0), dates=dates), "TEST")
    gaps = next(f.value for f in r.findings if f.name == "weekday_gaps")
    assert gaps["missing_weekdays"] == 2
    assert "upper bound" in gaps["note"]


def test_short_history_is_warned_about():
    r = build_report(_bars(np.full(30, 100.0)), "TEST")
    assert any("only 30 bars" in w for w in r.warnings)
    assert any("fewer than 250" in w for w in r.warnings)


def test_limits_are_present_and_honest():
    r = build_report(_bars(np.linspace(100, 150, 300)), "TEST")
    joined = " ".join(r.limits).lower()
    assert "not a language model" in joined
    assert "unadjusted" in joined
    assert "predict" in joined
    assert "investment advice" in joined


def test_report_is_deterministic():
    df = _bars(np.linspace(100, 150, 300))
    assert build_report(df, "TEST").to_dict() == build_report(df, "TEST").to_dict()


# ------------------------------------------------------------------- answers
def test_answer_routes_by_keyword():
    df = _bars(np.linspace(100, 150, 300))
    out = answer(df, "TEST", "what is the trend?")
    assert out["refused"] is False
    assert out["topics"] == ["trend"]
    assert out["findings"]
    assert all(f["topic"] == "trend" for f in out["findings"])


def test_answer_returns_everything_for_an_overview():
    n = 300
    closes = np.linspace(100, 150, n)
    uni = pd.DataFrame(
        {"TEST": closes, "PEER": closes * 1.1},
        index=pd.bdate_range("2026-01-01", periods=n),
    )
    out = answer(_bars(closes), "TEST", "give me an overview", universe=uni)
    assert out["topics"] == list(TOPICS)
    assert {f["topic"] for f in out["findings"]} == set(TOPICS)


def test_overview_without_a_universe_omits_relative_and_says_so():
    out = answer(_bars(np.linspace(100, 150, 300)), "TEST", "overview")
    assert out["topics"] == list(TOPICS)
    assert "relative" not in {f["topic"] for f in out["findings"]}
    # The help for every requested topic is still returned, including the one
    # with no data behind it.
    assert set(out["topic_help"]) == set(TOPICS)


def test_answer_refuses_predictions_and_lists_what_it_offers():
    out = answer(_bars(np.linspace(100, 150, 300)), "TEST", "will NABIL go up next week?")
    assert out["refused"] is True
    assert out["findings"] == []
    assert "will not produce one" in out["refusal_reason"]
    assert set(out["instead_offer"]) == set(TOPICS)


def test_answer_refuses_buy_instructions():
    out = answer(_bars(np.linspace(100, 150, 300)), "TEST", "should I buy now?")
    assert out["refused"] is True


def test_answer_explains_when_nothing_matched():
    out = answer(_bars(np.linspace(100, 150, 300)), "TEST", "wibble")
    assert out["refused"] is False
    assert out["topics"] == []
    assert out["findings"] == []
    assert "Ask about:" in out["matched_note"]


def test_answer_carries_the_limits():
    out = answer(_bars(np.linspace(100, 150, 300)), "TEST", "risk please")
    assert any("investment advice" in x for x in out["limits"])
