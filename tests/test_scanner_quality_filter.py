"""Scanner pipeline regression tests against the real ``run_screen``.

Replaces a vacuous placeholder that asserted about a *local* ``DATA_QUALITY``
dict literal (with ``or True`` tautologies) and never imported the scanner.
The real data-quality policy lives in ``MarketStore.get_bars``'s default
``_NOT_INVALID`` filter: rows flagged ``invalid`` are excluded from screening,
``suspect`` rows are retained. These tests exercise the actual pipeline.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from megatool.market_store import MarketStore
from megatool.scanner import (
    MIN_BARS_FOR_SCREEN,
    ScreenCondition,
    ScreenNode,
    deduplicate_symbols,
    run_screen,
    validate_tree,
)

RETRIEVED = pd.Timestamp("2026-10-11 00:00:00")


def _bars(symbol: str, closes: np.ndarray, last_status: str | None = None) -> pd.DataFrame:
    n = len(closes)
    df = pd.DataFrame(
        {
            "symbol": symbol,
            "trading_date": pd.bdate_range("2026-01-01", periods=n),
            "open": closes,
            "high": closes + 1.0,
            "low": closes - 1.0,
            "close": closes,
            "volume": np.full(n, 1000, dtype=np.int64),
        }
    )
    df["turnover"] = df["close"] * df["volume"]
    df["percent_change"] = 1.0
    df["source"] = "synthetic-scanner-fixture"
    df["retrieved_at"] = RETRIEVED
    df["validation_status"] = "valid"
    if last_status is not None:
        df.loc[df.index[-1], "validation_status"] = last_status
    return df


def _close_gt(value: float) -> ScreenNode:
    return ScreenNode(op="AND", conditions=[ScreenCondition("close", "gt", value)])


def _bars_listed_gte(value: float) -> ScreenNode:
    return ScreenNode(op="AND", conditions=[ScreenCondition("bars_listed", "gte", value)])


@pytest.fixture
def store(tmp_path):
    s = MarketStore(tmp_path / "scanner.duckdb")
    n = 50
    s.upsert_bars(_bars("WIN", 100.0 + np.arange(n)))  # last close 149
    s.upsert_bars(_bars("LOSEC", 150.0 - np.arange(n)))  # last close 101
    s.upsert_bars(_bars("BADLAST", 100.0 + np.arange(n), last_status="invalid"))
    s.upsert_bars(_bars("SUSPLAST", 100.0 + np.arange(n), last_status="suspect"))
    s.upsert_bars(_bars("SHORT", 100.0 + np.arange(10)))  # 10 bars < MIN_BARS
    yield s
    s.close()


# ------------------------------------------------------------ data quality
def test_invalid_last_row_is_excluded_from_screening(store):
    """A row flagged ``invalid`` must not count toward the screened history."""
    res = run_screen(store, _bars_listed_gte(50), symbols=["BADLAST"])
    (r,) = res
    assert r.eligible is True
    # 50 stored rows, but the invalid last one is filtered -> only 49 screened.
    assert r.passed is False  # 49 >= 50 is false


def test_suspect_last_row_is_retained_for_screening(store):
    """``suspect`` rows are uncertain, not impossible, and stay in the series."""
    res = run_screen(store, _bars_listed_gte(50), symbols=["SUSPLAST"])
    (r,) = res
    assert r.eligible is True
    assert r.passed is True  # all 50 rows (suspect retained) -> 50 >= 50


def test_get_bars_quality_filter_is_the_mechanism(store):
    # The scanner reads through get_bars, whose default excludes invalid only.
    assert len(store.get_bars("BADLAST")) == 49
    assert len(store.get_bars("SUSPLAST")) == 50


# ----------------------------------------------------------- deduplication
def test_duplicate_symbols_are_screened_once(store):
    res = run_screen(store, _close_gt(120), symbols=["WIN", "WIN", "WIN"])
    assert [r.symbol for r in res] == ["WIN"]


def test_deduplicate_symbols_preserves_order():
    assert deduplicate_symbols(["B", "A", "B", "C", "A"]) == ["B", "A", "C"]


# ------------------------------------------------------------- eligibility
def test_insufficient_history_is_marked_ineligible_not_dropped(store):
    res = run_screen(store, _close_gt(120), symbols=["SHORT"])
    (r,) = res
    assert r.symbol == "SHORT"
    assert r.eligible is False
    assert r.passed is False
    assert str(MIN_BARS_FOR_SCREEN) in r.note  # explains why, not a silent drop


def test_unknown_symbol_is_marked_ineligible(store):
    res = run_screen(store, _close_gt(120), symbols=["NOSUCH"])
    (r,) = res
    assert r.eligible is False
    assert "no stored history" in r.note


def test_one_bad_symbol_does_not_crash_the_others(store):
    res = run_screen(store, _close_gt(120), symbols=["WIN", "NOSUCH", "LOSEC"])
    by = {r.symbol: r for r in res}
    assert set(by) == {"WIN", "NOSUCH", "LOSEC"}
    assert by["WIN"].eligible and by["WIN"].passed
    assert by["LOSEC"].eligible and not by["LOSEC"].passed
    assert not by["NOSUCH"].eligible


# ---------------------------------------------------------- pass/fail reasons
def test_passing_and_failing_symbols_carry_reasons(store):
    res = {r.symbol: r for r in run_screen(store, _close_gt(120), symbols=["WIN", "LOSEC"])}
    assert res["WIN"].passed and res["WIN"].reasons
    assert not res["LOSEC"].passed and res["LOSEC"].failures
    # The rejection reason names the metric and the operator.
    assert any("close" in f and ">" in f for f in res["LOSEC"].failures)


# --------------------------------------------------------------- determinism
def test_screen_is_deterministic(store):
    node = _close_gt(120)
    a = run_screen(store, node, symbols=["WIN", "LOSEC", "BADLAST"])
    b = run_screen(store, node, symbols=["WIN", "LOSEC", "BADLAST"])
    key = lambda rs: [(r.symbol, r.eligible, r.passed) for r in rs]  # noqa: E731
    assert key(a) == key(b)


# ---------------------------------------------------------------- no lookahead
def test_as_of_caps_history_so_future_bars_are_not_used(store):
    """``as_of`` bounds the bars read; a later bar must not change an earlier screen."""
    full = run_screen(store, _bars_listed_gte(50), symbols=["WIN"])
    assert full[0].passed is True  # 50 bars available

    # Cap at the 40th bar's date: only 40 bars are then visible.
    as_of = pd.bdate_range("2026-01-01", periods=50)[39].date()
    capped = run_screen(store, _bars_listed_gte(50), symbols=["WIN"], as_of=as_of)
    assert capped[0].passed is False  # 40 >= 50 is false -> future not peeked


# --------------------------------------------------------------- validation
def test_validate_tree_rejects_unknown_metric():
    node = ScreenNode(op="AND", conditions=[ScreenCondition("not_a_metric", "gt", 1)])
    problems = validate_tree(node)
    assert problems and "unknown metric" in problems[0]


def test_validate_tree_accepts_real_metric():
    assert validate_tree(_close_gt(120)) == []
