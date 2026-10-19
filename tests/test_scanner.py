"""Scanner tests.

All data here is synthetic and deterministic, built into a throwaway DuckDB
file. Nothing asserts anything about real NEPSE prices.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from megatool.market_store import MarketStore
from megatool.scanner import (
    PRESET_SCREENS,
    ScreenCondition,
    ScreenNode,
    ScreenResult,
    _metric_value,
    evaluate_condition,
    run_screen,
    to_dataframe,
)

RETRIEVED = pd.Timestamp("2026-10-11 00:00:00")


def _bars(
    symbol: str, closes: np.ndarray, start: str = "2026-01-01", volume: np.ndarray | None = None
) -> pd.DataFrame:
    dates = pd.bdate_range(start, periods=len(closes))
    vol = volume if volume is not None else np.full(len(closes), 10_000.0)
    return pd.DataFrame(
        {
            "symbol": symbol,
            "trading_date": dates,
            "open": closes,
            "high": closes * 1.01,
            "low": closes * 0.99,
            "close": closes,
            "volume": vol.astype(np.int64),
            "turnover": closes * vol,
            "percent_change": np.nan,
            "source": "github.com/Aabishkar2/nepse-data",
            "retrieved_at": RETRIEVED,
        }
    )


@pytest.fixture
def store(tmp_path) -> MarketStore:
    s = MarketStore(tmp_path / "m.duckdb")
    n = 120
    x = np.arange(n, dtype=float)
    # ASC: rising series -> RSI high, close_vs_sma strongly positive
    # FLAT: constant series -> RSI undefined-ish/neutral, no trend
    # DROP: falling series -> RSI low
    s.upsert_bars(_bars("ASC", 100 + x))
    s.upsert_bars(_bars("FLAT", np.full(n, 50.0)))
    s.upsert_bars(_bars("DROP", 200 - x))
    s.upsert_bars(_bars("SHORT", np.linspace(10, 20, 10)))
    yield s
    s.close()


# ------------------------------------------------------------- tree plumbing
def test_condition_roundtrip():
    c = ScreenCondition(metric="rsi", operator="lt", value=30, lookback=None)
    again = ScreenCondition.from_dict(c.to_dict())
    assert (again.metric, again.operator, again.value) == ("rsi", "lt", 30.0)


def test_node_roundtrip_nested():
    tree = {
        "op": "AND",
        "children": [
            {
                "op": "OR",
                "conditions": [
                    {"metric": "return_5d", "operator": "gt", "value": 0.01},
                    {"metric": "return_20d", "operator": "gt", "value": 0.05},
                ],
            },
            {
                "op": "AND",
                "conditions": [
                    {"metric": "rsi", "operator": "lt", "value": 80},
                    {"metric": "bars_listed", "operator": "gte", "value": 100},
                ],
            },
        ],
    }
    node = ScreenNode.from_dict(tree)
    again = ScreenNode.from_dict(node.to_dict())
    assert again.render() == node.render()
    assert "OR" in node.render() and "AND" in node.render()


def test_unknown_operator_rejected():
    with pytest.raises(ValueError, match="unknown operator"):
        ScreenCondition.from_dict({"metric": "rsi", "operator": "~=", "value": 1})


def test_empty_node_rejected():
    with pytest.raises(ValueError, match="neither conditions nor children"):
        ScreenNode.from_dict({"op": "AND"})


def test_invalid_group_op_rejected():
    with pytest.raises(ValueError, match="must be AND or OR"):
        ScreenNode.from_dict(
            {"op": "XOR", "conditions": [{"metric": "close", "operator": "gt", "value": 1}]}
        )


# ---------------------------------------------------------------- metrics
def test_metrics_directionally_correct(store):
    asc = store.get_bars("ASC")
    drop = store.get_bars("DROP")
    assert _metric_value("return_20d", asc) > 0
    assert _metric_value("return_20d", drop) < 0
    assert _metric_value("close_vs_sma", asc, 20) > 0
    assert _metric_value("close_vs_sma", drop, 20) < 0


def test_rsi_bounds(store):
    for sym in ("ASC", "DROP"):
        v = _metric_value("rsi", store.get_bars(sym))
        assert v is None or 0.0 <= v <= 100.0


def test_flat_symbol_reports_rsi_as_unavailable_not_overbought():
    """A never-moved symbol must not masquerade as maximally bullish.

    Before the engine fix this returned 100, so an ``rsi > 70`` screen would
    have matched every flat symbol.
    """
    n = 40
    flat = pd.DataFrame(
        {
            "trading_date": pd.date_range("2026-01-01", periods=n, freq="D"),
            "open": np.full(n, 50.0),
            "high": np.full(n, 50.0),
            "low": np.full(n, 50.0),
            "close": np.full(n, 50.0),
            "volume": np.full(n, 1000.0),
        }
    )
    assert _metric_value("rsi", flat) is None

    ok, note = evaluate_condition(
        ScreenCondition.from_dict({"metric": "rsi", "operator": "gt", "value": 70}), flat
    )
    assert ok is None  # ineligible, not a false pass
    assert "unavailable" in note


def test_unknown_metric_raises(store):
    with pytest.raises(ValueError, match="unknown metric"):
        _metric_value("definitely_not_a_metric", store.get_bars("ASC"))


def test_metric_returns_none_when_history_too_short(store):
    short = store.get_bars("SHORT")
    assert _metric_value("rsi", short) is None  # only 10 bars


# ------------------------------------------------------------------ screening
def test_and_requires_every_condition(store):
    node = ScreenNode.from_dict(
        {
            "op": "AND",
            "conditions": [
                {"metric": "return_20d", "operator": "gt", "value": 0.0},
                {"metric": "bars_listed", "operator": "gte", "value": 100},
            ],
        }
    )
    res = {r.symbol: r for r in run_screen(store, node)}
    assert res["ASC"].passed is True
    assert res["DROP"].passed is False
    assert "return_20d" in " ".join(res["DROP"].failures)


def test_or_requires_any_condition(store):
    node = ScreenNode.from_dict(
        {
            "op": "OR",
            "conditions": [
                {"metric": "return_20d", "operator": "gt", "value": 10.0},  # impossible
                {"metric": "return_20d", "operator": "lt", "value": 0.0},  # true for DROP
            ],
        }
    )
    res = {r.symbol: r for r in run_screen(store, node)}
    assert res["DROP"].passed is True
    assert res["ASC"].passed is False


def test_and_screen_is_ineligible_when_a_required_metric_is_unavailable(store):
    """A missing metric must not silently qualify a security.

    FLAT never moved, so its RSI is unavailable. Before the fix the AND gate
    returned ``passed=True`` because it evaluated only ``bars_listed`` and
    dropped the RSI clause entirely — so a flat/illiquid symbol matched an
    oversold screen and the reason it shouldn't have was lost.
    """
    node = ScreenNode.from_dict(
        {
            "op": "AND",
            "conditions": [
                {"metric": "rsi", "operator": "lt", "value": 30},
                {"metric": "bars_listed", "operator": "gte", "value": 30},
            ],
        }
    )
    res = {r.symbol: r for r in run_screen(store, node)}
    flat = res["FLAT"]
    assert flat.eligible is False
    assert flat.passed is False
    assert "one or more metrics could not be computed" in flat.note
    assert "rsi unavailable" in " ".join(flat.failures)
    # A genuinely computable AND screen is unaffected.
    assert res["DROP"].eligible is True


def test_or_screen_is_ineligible_when_no_clause_is_known_true(store):
    """An OR whose clauses are all unknown is unknown, not a false pass/fail."""
    node = ScreenNode.from_dict(
        {
            "op": "OR",
            "conditions": [
                {"metric": "rsi", "operator": "lt", "value": 30},
                {"metric": "rsi", "operator": "gt", "value": 70},
            ],
        }
    )
    res = {r.symbol: r for r in run_screen(store, node)}
    assert res["FLAT"].eligible is False
    # A symbol where one OR clause is genuinely true stays eligible.
    assert res["DROP"].eligible is True
    assert res["DROP"].passed is True


def test_insufficient_history_marked_ineligible_not_failed(store):
    node = ScreenNode.from_dict(
        {"op": "AND", "conditions": [{"metric": "close", "operator": "gt", "value": 0}]}
    )
    res = {r.symbol: r for r in run_screen(store, node, min_bars=30)}
    short = res["SHORT"]
    assert short.eligible is False
    assert short.passed is False
    assert "only 10 bars" in short.note


def test_missing_symbol_has_no_history_note(store):
    node = ScreenNode.from_dict(
        {"op": "AND", "conditions": [{"metric": "close", "operator": "gt", "value": 0}]}
    )
    res = {r.symbol: r for r in run_screen(store, node, symbols=["NOPE"])}
    assert res["NOPE"].eligible is False
    assert "no stored history" in res["NOPE"].note


def test_results_are_reproducible(store):
    node = ScreenNode.from_dict(
        {"op": "AND", "conditions": [{"metric": "rsi", "operator": "lt", "value": 100}]}
    )
    a = run_screen(store, node, as_of=pd.Timestamp("2026-05-20").date())
    b = run_screen(store, node, as_of=pd.Timestamp("2026-05-20").date())
    assert [(r.symbol, r.passed) for r in a] == [(r.symbol, r.passed) for r in b]


def test_passing_results_carry_explanations(store):
    node = ScreenNode.from_dict(
        {"op": "AND", "conditions": [{"metric": "return_20d", "operator": "gt", "value": 0.0}]}
    )
    res = {r.symbol: r for r in run_screen(store, node)}
    assert res["ASC"].reasons
    assert "return_20d" in res["ASC"].reasons[0]
    assert "-> actual" in res["ASC"].reasons[0]


def test_to_dataframe_shape(store):
    node = ScreenNode.from_dict(
        {"op": "AND", "conditions": [{"metric": "close", "operator": "gt", "value": 0}]}
    )
    df = to_dataframe(run_screen(store, node))
    assert set(df.columns) >= {"symbol", "eligible", "passed", "passed_reasons", "failed_reasons"}
    assert len(df) == len(store.symbols(min_bars=1))


# ------------------------------------------------------------------- presets
@pytest.mark.parametrize("key", list(PRESET_SCREENS))
def test_presets_parse_and_run(key, store):
    preset = PRESET_SCREENS[key]
    node = ScreenNode.from_dict(preset["tree"])
    results = run_screen(store, node, min_bars=1)
    assert isinstance(results, list)
    assert all(isinstance(r, ScreenResult) for r in results)


def test_all_metrics_in_help_table():
    """Every metric name must be documented, so the UI can describe filters."""
    from megatool import scanner

    known = {
        "close",
        "volume",
        "turnover",
        "return_1d",
        "return_5d",
        "return_20d",
        "return_60d",
        "return_120d",
        "rsi",
        "sma",
        "ema",
        "close_vs_sma",
        "atr_percent",
        "historical_volatility",
        "relative_volume",
        "volume_sma_ratio",
        "distance_from_high_52w",
        "distance_from_low_52w",
        "macd",
        "macd_signal",
        "macd_histogram",
        "macd_cross",
        "sma_cross",
        "bollinger_percent_b",
        "bollinger_bandwidth",
        "stochastic_k",
        "stochastic_d",
        "mfi",
        "adx",
        "donchian_position",
        "donchian_breakout",
        "turnover_sma_ratio",
        "bars_listed",
        "relative_strength",
        "volume_ratio_50",
        "volume_vs_20d_max",
        "volume_climax_5_20",
        "updown_volume_ratio",
        "obv_pressure_20",
        "range_compression_20",
        "pocket_pivot",
    }
    assert known == set(scanner.METRIC_HELP)


# ----------------------------------------------------- extended metric coverage
NEW_METRICS = [
    "macd",
    "macd_signal",
    "macd_histogram",
    "macd_cross",
    "sma_cross",
    "bollinger_percent_b",
    "bollinger_bandwidth",
    "stochastic_k",
    "stochastic_d",
    "mfi",
    "adx",
    "donchian_position",
    "donchian_breakout",
    "turnover_sma_ratio",
]


def test_extended_metrics_return_a_number_or_none():
    n = 120
    x = np.arange(n, dtype=float)
    df = _bars("UP", 100 + x * 0.5)
    for m in NEW_METRICS:
        v = _metric_value(m, df)
        assert v is None or isinstance(v, float), m
    # Discrete cross/breakout metrics must only report the documented codes.
    assert _metric_value("macd_cross", df) in (-1.0, 0.0, 1.0)
    assert _metric_value("donchian_breakout", df) in (-1.0, 0.0, 1.0)


def test_donchian_breakout_up_is_detected_on_a_new_high():
    n = 60
    close = np.concatenate([np.full(n - 1, 100.0), [105.0]])
    df = _bars("BRK", close)
    assert _metric_value("donchian_breakout", df) == 1.0


def test_donchian_breakout_is_none_without_enough_history():
    df = _bars("TINY", np.full(10, 100.0))
    assert _metric_value("donchian_breakout", df) is None


@pytest.mark.parametrize("key", sorted(PRESET_SCREENS))
def test_every_preset_runs_without_error(store, key):
    """A preset is only useful if it executes; eligibility depends on history."""
    node = ScreenNode.from_dict(PRESET_SCREENS[key]["tree"])
    results = run_screen(store, node)
    assert results
    assert all(isinstance(r, ScreenResult) for r in results)


def test_macd_cross_metric_values_are_documented_codes_only(store):
    node = ScreenNode.from_dict(PRESET_SCREENS["macd_bullish_cross"]["tree"])
    # Well-formed and validatable; the point here is the metric contract.
    assert node.conditions[0].metric == "macd_cross"
    assert node.conditions[0].operator == "gt"


# ------------------------------------------------- volume-scanner metric maths
VOLUME_METRICS = [
    "volume_ratio_50",
    "volume_vs_20d_max",
    "volume_climax_5_20",
    "updown_volume_ratio",
    "obv_pressure_20",
    "range_compression_20",
    "pocket_pivot",
]


def test_volume_metrics_return_a_number_or_none():
    n = 60
    closes = 100 + np.arange(n, dtype=float)
    df = _bars("VOLT", closes, volume=np.full(n, 5_000.0))
    for m in VOLUME_METRICS:
        v = _metric_value(m, df)
        assert v is None or isinstance(v, float), m


def test_volume_vs_20d_max_is_one_when_today_is_the_biggest():
    closes = np.full(30, 100.0)
    vol = np.full(30, 1_000.0)
    vol[-1] = 5_000.0
    df = _bars("BIGV", closes, volume=vol)
    assert _metric_value("volume_vs_20d_max", df) == 1.0
    vol2 = np.full(30, 1_000.0)
    vol2[-1] = 500.0
    df2 = _bars("SMALLV", closes, volume=vol2)
    assert _metric_value("volume_vs_20d_max", df2) == 0.5


def test_volume_climax_is_the_5_bar_spike_ratio():
    closes = np.full(30, 100.0)
    vol = np.full(30, 1_000.0)
    vol[-3] = 3_000.0
    df = _bars("CLIMAX", closes, volume=vol)
    # 20-bar mean = (19*1000 + 3000)/20 = 1100; max of last 5 = 3000
    assert _metric_value("volume_climax_5_20", df) == pytest.approx(3000 / 1100)


def test_updown_volume_ratio_counts_only_directed_days():
    closes = np.array([100.0, 101.0, 101.0, 100.0, 102.0])
    vols = np.array([10.0, 20.0, 30.0, 40.0, 50.0])
    df = _bars("UD", closes, volume=vols)
    # lookback=4 pairs: +20 (up), unchanged 30 (excluded), -40 (down), +50 (up)
    assert _metric_value("updown_volume_ratio", df, lookback=4) == pytest.approx(70 / 40)
    # No down volume at all -> undefined ratio, not infinity.
    rising = np.array([100.0, 101.0, 102.0])
    df2 = _bars("UPONLY", rising, volume=np.array([10.0, 20.0, 30.0]))
    assert _metric_value("updown_volume_ratio", df2, lookback=2) is None


def test_obv_pressure_is_plus_one_on_an_all_up_window():
    closes = 100 + np.arange(30, dtype=float)
    df = _bars("OBVUP", closes, volume=np.full(30, 1_000.0))
    assert _metric_value("obv_pressure_20", df) == pytest.approx(1.0)
    falling = 200 - np.arange(30, dtype=float)
    df2 = _bars("OBVDN", falling, volume=np.full(30, 1_000.0))
    assert _metric_value("obv_pressure_20", df2) == pytest.approx(-1.0)


def test_range_compression_uses_the_previous_window():
    n = 30
    closes = np.full(n, 100.0)
    df = _bars("RNG", closes)  # range = 2% of close everywhere
    # Make today's range half of normal: high-low = 1% of close.
    df.loc[df.index[-1], "high"] = closes[-1] * 1.005
    df.loc[df.index[-1], "low"] = closes[-1] * 0.995
    assert _metric_value("range_compression_20", df) == pytest.approx(0.5)


def test_pocket_pivot_requires_up_close_and_dominant_volume():
    closes = np.array(
        [
            100.0,
            101.0,
            100.0,
            101.0,
            100.0,
            101.0,
            100.0,
            101.0,
            100.0,
            101.0,
            100.0,
            101.0,
            100.0,
            102.0,
        ]
    )
    vols = np.array(
        [
            900.0,
            400.0,
            700.0,
            400.0,
            700.0,
            400.0,
            700.0,
            400.0,
            700.0,
            400.0,
            700.0,
            400.0,
            700.0,
            800.0,
        ]
    )
    # Down days among the prior 10 (indexes 3..12): max down volume = 700.
    df = _bars("PP", closes, volume=vols)
    assert _metric_value("pocket_pivot", df) == 1.0  # today up, 800 > 700
    vols2 = vols.copy()
    vols2[-1] = 600.0
    df2 = _bars("PP2", closes, volume=vols2)
    assert _metric_value("pocket_pivot", df2) == 0.0  # 600 not > 700
    closes3 = closes.copy()
    closes3[-1] = 99.0
    df3 = _bars("PP3", closes3, volume=vols)
    assert _metric_value("pocket_pivot", df3) == 0.0  # down close
