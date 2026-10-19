"""Seasonality tests.

Synthetic stores only. The holiday section is exercised BOTH with the bundled
(empty) calendar — which must report 'unavailable' rather than invent anything
— and with a temporary populated calendar.
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import pytest

from megatool.market_store import MarketStore
from megatool.seasonality import (
    DEFAULT_CALENDAR_PATH,
    holiday_effect,
    monthly_seasonality,
    seasonality_report,
    weekday_seasonality,
)

RETRIEVED = pd.Timestamp("2026-10-11 00:00:00")


def _bars(symbol: str, rows: list[tuple[str, float]], volume: float = 1_000.0) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "symbol": symbol,
            "trading_date": [pd.Timestamp(d) for d, _ in rows],
            "open": [c for _, c in rows],
            "high": [c * 1.01 for _, c in rows],
            "low": [c * 0.99 for _, c in rows],
            "close": [c for _, c in rows],
            "volume": np.full(len(rows), volume, dtype=np.int64),
            "turnover": [c * volume for _, c in rows],
            "percent_change": np.nan,
            "source": "github.com/Aabishkar2/nepse-data",
            "retrieved_at": RETRIEVED,
        }
    )


MONTHLY = [
    ("2022-12-15", 100.0),
    ("2023-01-15", 110.0),
    ("2023-02-15", 121.0),
    ("2023-03-15", 121.0),
    ("2023-04-15", 113.74),
]


@pytest.fixture
def store(tmp_path) -> MarketStore:
    s = MarketStore(tmp_path / "season.duckdb")
    s.upsert_bars(_bars("MON", MONTHLY))
    yield s
    s.close()


def test_monthly_returns_and_aggregates(store):
    out = monthly_seasonality(store, "MON", min_month_bars=1)
    months = {f"{m['year']}-{m['month']:02d}": m for m in out["months"]}
    assert months["2022-12"]["return_pct"] is None  # first month, no predecessor
    assert months["2023-01"]["return_pct"] == pytest.approx(10.0)
    assert months["2023-02"]["return_pct"] == pytest.approx(10.0)
    assert months["2023-03"]["return_pct"] == pytest.approx(0.0)
    assert months["2023-04"]["return_pct"] == pytest.approx(-6.0)

    by = {m["month"]: m for m in out["by_month"]}
    assert by[1]["count"] == 1 and by[1]["mean_pct"] == pytest.approx(10.0)
    assert by[3]["mean_pct"] == pytest.approx(0.0)
    assert by[3]["hit_rate_pct"] == pytest.approx(0.0)
    assert by[4]["mean_pct"] == pytest.approx(-6.0)
    assert by[12]["count"] == 0 and by[12]["mean_pct"] is None  # never fabricated
    assert out["excluded_months"] == 1  # only 2022-12
    assert out["year_matrix"]["2023"]["01"] == pytest.approx(10.0)


def test_partial_months_are_excluded_from_aggregates(store):
    out = monthly_seasonality(store, "MON", min_month_bars=2)
    # Every month has 1 bar < 2 -> all partial; each month's return also
    # involves the previous partial month, so nothing reaches the aggregates.
    assert all(m["count"] == 0 for m in out["by_month"])
    assert out["excluded_months"] == len(out["months"])
    assert out["months"][1]["partial"] is True


def test_weekday_grouping(store):
    s = MarketStore(store.path.parent / "wd.duckdb")
    rows = [
        ("2023-01-02", 100.0),  # Monday
        ("2023-01-03", 110.0),  # Tuesday
        ("2023-01-04", 121.0),  # Wednesday
        ("2023-01-09", 133.1),  # Monday
        ("2023-01-10", 146.41),  # Tuesday
    ]
    s.upsert_bars(_bars("WD", rows))
    try:
        out = weekday_seasonality(s, "WD")
        by = {d["weekday"]: d for d in out["by_weekday"]}
        assert by[0]["count"] == 1  # Monday: 2023-01-09's return
        assert by[0]["mean_pct"] == pytest.approx(10.0)
        assert by[1]["count"] == 2  # Tue: returns of 01-03 and 01-10
        assert by[1]["mean_pct"] == pytest.approx(10.0)
        assert by[2]["count"] == 1
        assert by[4]["count"] == 0 and by[4]["mean_pct"] is None  # Friday: no fake data
    finally:
        s.close()


def test_default_calendar_reports_holiday_study_unavailable(store):
    out = holiday_effect(store, "MON")
    assert out["available"] is False
    assert "no holiday entries" in out["reason"]
    assert out["holidays_configured"] == 0


def test_holiday_effect_with_configured_calendar(tmp_path):
    cal = tmp_path / "cal.json"
    cal.write_text(json.dumps({"holidays": ["2023-01-04"]}))
    s = MarketStore(tmp_path / "hol.duckdb")
    s.upsert_bars(
        _bars(
            "HOL",
            [
                ("2023-01-02", 100.0),
                ("2023-01-03", 110.0),
                ("2023-01-05", 121.0),
                ("2023-01-06", 133.1),
            ],
        )
    )
    try:
        out = holiday_effect(s, "HOL", calendar_path=cal)
        assert out["available"] is True
        assert out["summary"]["count"] == 1
        ev = out["events"][0]
        assert ev["holiday"] == "2023-01-04"
        assert ev["last_session_before"] == "2023-01-03"
        assert ev["first_session_after"] == "2023-01-05"
        assert ev["return_pct"] == pytest.approx(10.0)
    finally:
        s.close()


def test_holiday_outside_history_is_reported_not_dropped(tmp_path):
    cal = tmp_path / "cal.json"
    cal.write_text(json.dumps({"holidays": ["2020-01-01"]}))
    s = MarketStore(tmp_path / "hol2.duckdb")
    s.upsert_bars(
        _bars("HOL2", [("2023-01-02", 100.0), ("2023-01-03", 110.0), ("2023-01-04", 120.0)])
    )
    try:
        out = holiday_effect(s, "HOL2", calendar_path=cal)
        assert out["available"] is False
        assert "inside the stored history" in out["reason"]
    finally:
        s.close()


def test_report_combines_sections(store):
    out = seasonality_report(store, "MON", min_month_bars=1)
    assert set(out) >= {"monthly", "weekday", "holiday", "disclaimer"}
    assert out["monthly"]["symbol"] == "MON"
    assert out["holiday"]["available"] is False


def test_index_series_is_resolved_by_name(tmp_path):
    s = MarketStore(tmp_path / "idx.duckdb")
    s.upsert_index_rows(
        [
            {
                "index_name": "NEPSE",
                "trading_date": "2023-01-15",
                "close": 2000.0,
                "source": "test",
                "retrieved_at": RETRIEVED,
            },
            {
                "index_name": "NEPSE",
                "trading_date": "2023-02-15",
                "close": 2100.0,
                "source": "test",
                "retrieved_at": RETRIEVED,
            },
        ]
    )
    try:
        out = monthly_seasonality(s, "nepse", min_month_bars=1)
        assert out["kind"] == "index"
        assert out["symbol"] == "NEPSE"
        feb = next(m for m in out["months"] if m["month"] == 2)
        assert feb["return_pct"] == pytest.approx(5.0)
    finally:
        s.close()


def test_unknown_symbol_raises_keyerror(store):
    with pytest.raises(KeyError):
        monthly_seasonality(store, "NOPE")
    assert DEFAULT_CALENDAR_PATH.exists()  # the bundled calendar is present and readable
