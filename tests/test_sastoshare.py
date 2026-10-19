"""Sasto Share workspace tests.

The workspace assembles reference-platform views (market pulse, movers, historical
P/E and P/B, valuation models, support/resistance risk framing, a volatility
cone, sector rotation, dividends and a strategy-vs-buy-and-hold comparison) from
the same stores the rest of the tool uses.

These tests pin the *contract*, and in particular the honesty rules:

* a missing input is ``null`` plus a reason — never a placeholder number;
* derived figures (market cap, relative volume, sector index, the cone) say so;
* the buy-and-hold comparison shares the strategy's dates and entry cost.

Everything here is synthetic and deterministic. No test asserts anything about
real NEPSE prices, and no test reaches the network.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from megatool import sastoshare as ss
from megatool.api import create_app
from megatool.db import get_conn, init_app_db
from megatool.market_store import MarketStore

RETRIEVED = pd.Timestamp("2026-10-11 00:00:00")


def _bars(symbol: str, closes, volume=None, start: str = "2025-06-02") -> pd.DataFrame:
    closes = [float(c) for c in closes]
    n = len(closes)
    dates = pd.bdate_range(start, periods=n)
    vol = volume if volume is not None else [1000 + 10 * i for i in range(n)]
    return pd.DataFrame(
        {
            "symbol": symbol,
            "trading_date": dates,
            "open": closes,
            "high": [c * 1.01 for c in closes],
            "low": [c * 0.99 for c in closes],
            "close": closes,
            "volume": np.asarray(vol, dtype=np.int64),
            "turnover": np.asarray(closes) * np.asarray(vol, dtype=float),
            "percent_change": np.nan,
            "source": "github.com/Aabishkar2/nepse-data",
            "retrieved_at": RETRIEVED,
        }
    )


def _wave(n: int, start: float = 100.0, drift: float = 0.002, amp: float = 4.0) -> list[float]:
    """A deterministic, gently trending series with a repeatable oscillation."""
    out = []
    price = start
    for i in range(n):
        price *= 1.0 + drift
        price += amp * np.sin(i / 4.0)
        out.append(round(price, 4))
    return out


def _fund(conn, symbol: str, field: str, value: float, period_end: str, label: str = "FY") -> None:
    conn.execute(
        "INSERT INTO fundamentals (symbol, field, value, period_end, period_label, unit, "
        "source, verification, retrieved_at) VALUES (?, ?, ?, ?, ?, 'NPR', 'test', 'reviewed', "
        "'2026-01-01')",
        (symbol, field, float(value), period_end, label),
    )


# --------------------------------------------------------------------------- #
# Pure helpers
# --------------------------------------------------------------------------- #
def test_point_in_time_picks_the_newest_period_not_after_the_date():
    series = [("2024-06-30", 10.0), ("2025-06-30", 12.0), ("2026-06-30", 15.0)]
    assert ss._point_in_time(series, "2025-12-31") == 12.0
    assert ss._point_in_time(series, "2025-06-30") == 12.0
    assert ss._point_in_time(series, "2024-01-01") is None
    assert ss._point_in_time([], "2026-01-01") is None


def test_histogram_is_empty_for_no_trades_and_one_bin_for_a_flat_run():
    assert ss._histogram([])["count"] == 0
    flat = ss._histogram([5.0, 5.0, 5.0])
    assert flat["count"] == 3 and len(flat["bins"]) == 1


def test_histogram_counts_sum_to_the_sample_size():
    h = ss._histogram([-10, -2, 0, 3, 7, 11, 20])
    assert h["count"] == 7
    assert sum(b["count"] for b in h["bins"]) == 7


def test_rsi_is_bounded_and_high_for_a_monotone_rise():
    rising = np.asarray([100.0 + i for i in range(40)])
    r = ss._rsi(rising, 14)
    assert r is not None and 0 <= r <= 100
    assert r > 95
    assert ss._rsi(np.asarray([1.0, 2.0]), 14) is None


def test_macd_state_follows_recent_momentum():
    up = np.asarray([100.0 * (1.004**i) for i in range(120)])
    assert ss._macd(up)["state"] == "bullish"
    # A long climb that turns sharply down at the end.
    down = np.asarray(
        [100.0 + i * 0.5 for i in range(100)] + [150.0 - i * 5.0 for i in range(1, 21)]
    )
    assert ss._macd(down)["state"] == "bearish"
    assert ss._macd(np.asarray([1.0, 2.0]))["state"] is None


# --------------------------------------------------------------------------- #
# Fixtures
# --------------------------------------------------------------------------- #
@pytest.fixture
def store(tmp_path) -> MarketStore:
    s = MarketStore(tmp_path / "sasto.duckdb")
    # Two sectors, three members each, all with long enough history for SMA-200.
    for sym in ("AAA", "BBB", "CCC", "DDD", "EEE", "FFF"):
        s.upsert_bars(_bars(sym, _wave(260, start=100.0 + len(sym) * 5)))
    # One short-history symbol for the unavailable paths.
    s.upsert_bars(_bars("SHORT", _wave(12)))
    # A stored NEPSE index series so beta has something to regress against.
    idx = [
        {
            "index_name": "NEPSE",
            "trading_date": str(pd.Timestamp(d).date()),
            "close": 2000.0 + i,
            "source": "test",
            "retrieved_at": RETRIEVED,
        }
        for i, d in enumerate(pd.bdate_range("2025-06-02", periods=260))
    ]
    s.upsert_index_rows(idx)
    return s


@pytest.fixture
def client(store: MarketStore, monkeypatch):
    # The sector map normally comes from a live securities feed. Pin it so the
    # tests are offline and deterministic.
    monkeypatch.setattr(
        "megatool.market_dashboard._sector_map",
        lambda: {
            "AAA": "Alpha",
            "BBB": "Alpha",
            "CCC": "Alpha",
            "DDD": "Beta",
            "EEE": "Beta",
            "FFF": "Beta",
            "SHORT": "Beta",
        },
    )
    app = create_app(store=store)
    with TestClient(app) as c:
        yield c


@pytest.fixture
def seeded(client):
    """Fundamentals for AAA (full set) and DDD (EPS only), in the app DB."""
    annual = "Annual Report (Nepali FY 2025-2026)"
    with get_conn() as conn:
        _fund(conn, "AAA", "eps", 20.0, "2024-06-30", annual)
        _fund(conn, "AAA", "eps", 25.0, "2025-06-30", annual)
        _fund(conn, "AAA", "eps", 30.0, "2026-06-30", annual)
        _fund(conn, "AAA", "net_worth_per_share", 300.0, "2026-06-30", annual)
        _fund(conn, "AAA", "paid_up_capital", 10_000_000.0, "2026-06-30", annual)
        _fund(conn, "AAA", "pe", 30.0, "2026-06-30", annual)
        _fund(conn, "DDD", "eps", 5.0, "2026-06-30", annual)
    return client


# --------------------------------------------------------------------------- #
# Market pulse
# --------------------------------------------------------------------------- #
def test_pulse_reports_denominators_and_a_definition(seeded):
    d = seeded.get("/api/sastoshare/pulse").json()
    for key in ("barometer", "sentiment", "golden_cross", "sector_ma", "pe_ranges"):
        assert key in d
    assert d["sentiment"]["above_50"]["denominator"] > 0
    # The denominator is the symbols that actually had the window, never the
    # whole market.
    assert d["sentiment"]["above_200"]["denominator"] <= 6
    assert "52-week position" in d["barometer"]["definition"]
    assert d["universe"]["symbols_with_bars"] == 7


def test_pulse_sector_breadth_denominator_matches_its_own_members(seeded):
    d = seeded.get("/api/sastoshare/pulse").json()
    alpha = next(r for r in d["sector_ma"] if r["sector"] == "Alpha")
    assert alpha["above_sma_50"]["denominator"] == 3
    beta = next(r for r in d["sector_ma"] if r["sector"] == "Beta")
    # SHORT has only 12 bars, so it cannot enter any window.
    assert beta["above_sma_10"]["denominator"] == 3


def test_pulse_pe_uses_stored_pe_then_falls_back_to_close_over_eps(seeded):
    d = seeded.get("/api/sastoshare/pulse").json()
    bins = {
        b["label"]: b["count"] for r in d["pe_ranges"] if r["sector"] == "Alpha" for b in r["bins"]
    }
    assert sum(bins.values()) >= 1
    # DDD has an EPS but no stored P/E, so it must still be placed.
    beta = next((r for r in d["pe_ranges"] if r["sector"] == "Beta"), None)
    assert beta is not None and beta["n"] >= 1


# --------------------------------------------------------------------------- #
# Valuation history
# --------------------------------------------------------------------------- #
def test_valuation_history_steps_the_ratio_at_its_period_end(seeded):
    d = seeded.get("/api/sastoshare/valuation-history/AAA?limit=400").json()
    assert d["available"] is True
    assert len(d["dates"]) == len(d["pe"]) == len(d["close"])
    vals = [v for v in d["pe"] if v is not None]
    assert vals, "a stored EPS series must produce a P/E series"
    # The last bar uses the newest EPS whose period end is on or before it.
    assert d["latest"]["eps"] in (25.0, 30.0)
    # The series is rounded to 3 dp from the raw close while the price column is
    # rounded to 2 dp, so the comparison carries the rounding difference.
    assert d["pe"][-1] == pytest.approx(d["close"][-1] / d["latest"]["eps"], abs=0.01)
    assert "period end" in d["alignment_note"]


def test_valuation_history_is_honest_when_no_fundamental_is_stored(seeded):
    d = seeded.get("/api/sastoshare/valuation-history/BBB?limit=120").json()
    assert d["available"] is False
    assert "no eps record stored" in d["reason"]
    assert all(v is None for v in d["pe"])


def test_valuation_history_unknown_symbol_is_still_explicit(seeded):
    d = seeded.get("/api/sastoshare/valuation-history/NOPE?limit=60").json()
    assert d["available"] is False
    assert "no stored history" in d["reason"]


def test_valuation_history_rejects_a_bad_symbol(seeded):
    assert seeded.get("/api/sastoshare/valuation-history/%20%20").status_code in (400, 404)


def test_valuation_history_caps_the_axis_and_flags_a_suspect_period(client):
    """A near-zero EPS is flagged, and its enormous P/E is not left to own the axis."""
    annual = "Annual Report (Nepali FY 2025-2026)"
    with get_conn() as conn:
        for v, end in ((20.0, "2024-06-30"), (22.0, "2025-06-30"), (25.0, "2026-06-30")):
            _fund(conn, "AAA", "eps", v, end, annual)
        # A partial / mislabelled annual figure: well under a fifth of the median.
        _fund(conn, "AAA", "eps", 0.05, "2025-12-15", annual)
    d = client.get("/api/sastoshare/valuation-history/AAA?limit=400").json()
    assert d["pe_axis"]["cap"] > 0
    assert d["pe_axis"]["points_above_cap"] >= 1
    assert d["pe_axis"]["largest"]["value"] > d["pe_axis"]["cap"]
    assert d["pe_axis"]["largest"]["eps"] == pytest.approx(0.05, abs=1e-9)
    assert any(s["eps"] == pytest.approx(0.05) for s in d["suspect_periods"])
    # The outlier is still in the series — it is flagged, not hidden.
    assert max(v for v in d["pe"] if v is not None) > d["pe_axis"]["cap"]


def test_valuation_history_does_not_flag_a_normal_series(client):
    annual = "Annual Report (Nepali FY 2025-2026)"
    with get_conn() as conn:
        for v, end in ((20.0, "2024-06-30"), (22.0, "2025-06-30"), (25.0, "2026-06-30")):
            _fund(conn, "AAA", "eps", v, end, annual)
    d = client.get("/api/sastoshare/valuation-history/AAA?limit=400").json()
    assert d["suspect_periods"] == []
    assert d["pe_axis"]["points_above_cap"] == 0


def test_growth_uses_annual_periods_only(client):
    """Quarterly figures must not masquerade as years in the CAGR."""
    with get_conn() as conn:
        _fund(
            conn, "AAA", "eps", 10.0, "2024-06-30", "First Quarter 2024-2025 (Nepali FY 2024-2025)"
        )
        _fund(
            conn, "AAA", "eps", 12.0, "2024-09-30", "Second Quarter 2024-2025 (Nepali FY 2024-2025)"
        )
        _fund(
            conn, "AAA", "eps", 14.0, "2024-12-31", "Third Quarter 2024-2025 (Nepali FY 2024-2025)"
        )
        _fund(conn, "AAA", "eps", 16.0, "2025-06-30", "Annual Report (Nepali FY 2024-2025)")
        _fund(conn, "AAA", "eps", 20.0, "2026-06-30", "Annual Report (Nepali FY 2025-2026)")
    d = client.get("/api/sastoshare/valuation/AAA").json()
    # Only two annual periods exist, so a CAGR is refused rather than computed
    # from the four quarterly rows.
    assert d["growth_pct"] is None
    assert "annual" in (d["growth_basis"] or "").lower()


# --------------------------------------------------------------------------- #
# Valuation models
# --------------------------------------------------------------------------- #
def test_valuation_models_compute_graham_and_margin_of_safety(seeded):
    d = seeded.get("/api/sastoshare/valuation/AAA").json()
    by = {m["model"]: m for m in d["models"]}
    # sqrt(22.5 * 30 * 300) = 450
    assert by["Graham number"]["value"] == pytest.approx(450.0, abs=0.01)
    assert by["Margin of safety"]["value"] is not None
    assert by["Margin of safety"]["inputs"]["price"] == d["price"]


def test_gordon_is_unavailable_with_a_reason_when_no_dps_is_stored(seeded):
    d = seeded.get("/api/sastoshare/valuation/AAA").json()
    gordon = next(m for m in d["models"] if m["model"] == "Gordon growth")
    assert gordon["value"] is None
    assert "no dps record stored" in gordon["missing"]


def test_peg_needs_a_positive_growth_rate(seeded):
    d = seeded.get("/api/sastoshare/valuation/AAA").json()
    peg = next(m for m in d["models"] if m["model"] == "PEG ratio")
    assert d["growth_pct"] is not None and d["growth_pct"] > 0
    assert peg["value"] == pytest.approx(round(30.0 / d["growth_pct"], 2), abs=0.01)


def test_growth_override_is_echoed_as_an_assumption(seeded):
    d = seeded.get("/api/sastoshare/valuation/AAA?growth_pct=8&required_return_pct=11").json()
    assert d["growth_pct"] == 8.0
    assert d["growth_basis"] == "user-supplied growth assumption"
    assert d["assumptions"]["required_return_pct"] == 11.0


def test_valuation_models_are_explicit_when_nothing_is_stored(seeded):
    d = seeded.get("/api/sastoshare/valuation/BBB").json()
    graham = next(m for m in d["models"] if m["model"] == "Graham number")
    assert graham["value"] is None and graham["missing"]


# --------------------------------------------------------------------------- #
# Movers
# --------------------------------------------------------------------------- #
def test_movers_endpoint_ranks_and_labels_its_sparklines(seeded, monkeypatch):
    def _fake_snapshot(force=False):
        return {
            "quotes": [
                {"symbol": "AAA", "ltp": 500.0, "percent_change": 4.0, "volume": 12_000},
                {"symbol": "DDD", "ltp": 90.0, "percent_change": -3.0, "volume": 8_000},
            ]
        }

    monkeypatch.setattr(
        "megatool.live.get_service",
        lambda: type("S", (), {"snapshot": staticmethod(_fake_snapshot)})(),
    )
    d = seeded.get("/api/sastoshare/movers?limit=3").json()
    assert [r["symbol"] for r in d["gainers"]][0] == "AAA"
    assert [r["symbol"] for r in d["losers"]][0] == "DDD"
    assert d["coverage"]["note"].startswith("Sparklines are stored daily closes")


def test_movers_cap_and_range_come_from_stored_rows(store, monkeypatch):
    monkeypatch.setattr("megatool.market_dashboard._sector_map", lambda: {})
    init_app_db()
    with get_conn() as conn:
        _fund(conn, "AAA", "paid_up_capital", 10_000_000.0, "2026-06-30")
        d = ss.movers_context(
            store,
            conn,
            [{"symbol": "AAA", "ltp": 500.0, "percent_change": 4.0, "volume": 9000}],
            limit=1,
            spark=10,
        )
    row = d["gainers"][0]
    assert len(row["sparkline"]) == 10
    assert row["range_52w"]["low"] <= row["range_52w"]["high"]
    assert row["market_cap"]["kind"] == "derived"
    # 10,000,000 / 100 * 500
    assert row["market_cap"]["value_npr"] == pytest.approx(50_000_000.0, rel=1e-6)


def test_movers_cap_is_unavailable_with_a_reason_without_paid_up_capital(store, monkeypatch):
    monkeypatch.setattr("megatool.market_dashboard._sector_map", lambda: {})
    init_app_db()
    with get_conn() as conn:
        d = ss.movers_context(
            store,
            conn,
            [{"symbol": "AAA", "ltp": 500.0, "percent_change": 1.0, "volume": 1}],
            limit=1,
        )
    cap = d["gainers"][0]["market_cap"]
    assert cap["value_npr"] is None
    assert "paid-up capital" in cap["unavailable_reason"]


# --------------------------------------------------------------------------- #
# Risk and levels
# --------------------------------------------------------------------------- #
def test_risk_frames_a_level_or_explains_why_not(seeded):
    d = seeded.get("/api/sastoshare/risk/AAA?limit=250").json()
    assert d["available"] is True
    daily = d["daily"]
    assert daily["bars"] >= 200
    # Either a reward:risk was framed, or the engine's reason is present.
    assert (daily["reward_risk"] is not None) or daily["framing_reason"]
    # Sizing only exists alongside a framed level.
    if daily["position_shares"] is None:
        assert daily["sizing_reason"]


def test_risk_weekly_is_explicit_when_there_is_not_enough_history(seeded):
    d = seeded.get("/api/sastoshare/risk/SHORT?limit=60").json()
    assert d["available"] is False
    assert "not enough stored history" in d["reason"]


# --------------------------------------------------------------------------- #
# Volatility
# --------------------------------------------------------------------------- #
def test_volatility_cone_widens_with_the_horizon(seeded):
    d = seeded.get("/api/sastoshare/volatility/AAA?limit=400").json()
    assert d["available"] is True
    horizons = [c["horizon_days"] for c in d["cone"]]
    assert horizons == sorted(horizons)
    moves = [c["sigma_move_pct"] for c in d["cone"]]
    assert moves == sorted(moves)
    for c in d["cone"]:
        lo1, hi1 = c["band_1sigma"]
        lo2, hi2 = c["band_2sigma"]
        assert lo2 <= lo1 <= d["last_close"] <= hi1 <= hi2


def test_beta_is_computed_against_a_stored_index(seeded):
    d = seeded.get("/api/sastoshare/volatility/AAA?limit=400").json()
    # The index rises 1 point a day while the symbol oscillates, so beta is a
    # real number rather than None.
    assert d["beta_3m"] is not None
    assert d["beta_note"] is None


def test_volatility_is_unavailable_with_a_reason_for_a_short_history(seeded):
    d = seeded.get("/api/sastoshare/volatility/SHORT?limit=60").json()
    assert d["available"] is False
    assert "not enough stored history" in d["reason"]


# --------------------------------------------------------------------------- #
# Sector rotation
# --------------------------------------------------------------------------- #
def test_rotation_index_is_labelled_derived(seeded):
    d = seeded.get("/api/sastoshare/rotation").json()
    assert d["available"] is True
    assert "equal-weight index" in d["method"]
    assert any("not the exchange's sector index" in c for c in d["caveats"])
    alpha = next(r for r in d["sectors"] if r["sector"] == "Alpha")
    assert alpha["members"] == 3
    assert len(alpha["index_series"]) >= 2
    assert alpha["regime"] in {
        "leading (positive 1m and 3m)",
        "improving (1m positive, 3m negative)",
        "weakening (1m negative, 3m positive)",
        "lagging (negative 1m and 3m)",
        "insufficient history",
    }


def test_rotation_refuses_a_sector_with_too_few_members(seeded):
    # Beta holds DDD, EEE, FFF and SHORT; SHORT lacks the 60-bar minimum but the
    # other three are enough, so Beta is present while a lone member is not.
    d = seeded.get("/api/sastoshare/rotation").json()
    assert {r["sector"] for r in d["sectors"]} == {"Alpha", "Beta"}


# --------------------------------------------------------------------------- #
# Dividends
# --------------------------------------------------------------------------- #
def test_dividends_is_honest_when_no_notice_or_dps_is_stored(seeded):
    d = seeded.get("/api/sastoshare/dividends").json()
    assert d["coverage"]["symbols_with_dps"] == 0
    assert d["yields"] == []
    assert d["blocker"] is not None
    assert "nothing is inferred from price history" in d["blocker"]
    # The calculator is explicitly data-independent.
    assert "not a stored quote" in d["scenario"]["note"] or "not a stored" in d["scenario"]["note"]


def test_dividends_yield_is_derived_when_dps_exists(client):
    with get_conn() as conn:
        _fund(conn, "AAA", "dps", 20.0, "2025-06-30")
        _fund(conn, "AAA", "eps", 40.0, "2025-06-30")
    d = client.get("/api/sastoshare/dividends?symbol=AAA").json()
    assert d["yield_denominator"] == 1
    y = d["yields"][0]
    assert y["kind"] == "derived"
    assert y["yield_pct"] == pytest.approx(round(20.0 / y["price"] * 100.0, 2), abs=0.02)
    assert y["payout_pct"] == pytest.approx(50.0, abs=0.01)


def test_dividends_rejects_a_bad_symbol(seeded):
    assert seeded.get("/api/sastoshare/dividends?symbol=%20%20").status_code in (400, 404)


# --------------------------------------------------------------------------- #
# Backtest vs buy & hold
# --------------------------------------------------------------------------- #
def test_backtest_vs_hold_shares_dates_and_entry_cost(seeded):
    r = seeded.post(
        "/api/sastoshare/backtest-vs-hold",
        json={"symbol": "AAA", "strategy": "sma_cross", "initial_cash": 100_000},
    )
    assert r.status_code == 200
    d = r.json()
    assert d["available"] is True
    curve = d["curve"]
    assert len(curve) > 10
    assert curve[0]["date"] == d["start"] and curve[-1]["date"] == d["end"]
    assert all(p["buy_hold"] is not None for p in curve)
    cmp_ = d["comparison"]
    assert cmp_["strategy_final"] == pytest.approx(curve[-1]["strategy"], abs=0.01)
    assert cmp_["buy_hold_final"] == pytest.approx(curve[-1]["buy_hold"], abs=0.01)
    # Buy & hold starts below the initial cash because it pays the entry cost.
    assert curve[0]["buy_hold"] < 100_000
    assert d["histogram"]["count"] == d["trades"]
    assert "same one-off entry cost" in d["method"]


def test_backtest_vs_hold_rejects_an_unknown_strategy(seeded):
    r = seeded.post(
        "/api/sastoshare/backtest-vs-hold", json={"symbol": "AAA", "strategy": "not_a_strategy"}
    )
    assert r.status_code >= 400


def test_backtest_vs_hold_needs_a_stored_series(seeded):
    r = seeded.post(
        "/api/sastoshare/backtest-vs-hold", json={"symbol": "NOPE", "strategy": "sma_cross"}
    )
    assert r.status_code >= 400


def test_backtest_vs_hold_units_helper_is_declared():
    """The module exposes the documented public surface."""
    for name in (
        "market_pulse",
        "movers_context",
        "price_valuation_history",
        "valuation_models",
        "levels_and_risk",
        "volatility_projection",
        "sector_rotation",
        "dividends",
        "backtest_vs_hold",
    ):
        assert name in ss.__all__
        assert callable(getattr(ss, name))
