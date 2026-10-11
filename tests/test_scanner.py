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
        "bars_listed",
    }
    assert known == set(scanner.METRIC_HELP)
