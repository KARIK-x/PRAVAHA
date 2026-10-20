"""Tests for the calendar event-window study.

These build a small synthetic calendar dataset and a synthetic stored-bar
series so the window arithmetic can be checked exactly, without depending on
the network or on the extracted Hamro Patro dataset.
"""

from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import pytest

from megatool.seasonality import calendar_event_study


class _FakeStore:
    """Just enough of MarketStore for ``load_close_series``."""

    def __init__(self, dates, closes):
        self._dates = dates
        self._closes = closes

    def index_names(self):
        return []

    def index_closes(self, name):
        import pandas as pd

        return pd.DataFrame({"trading_date": [], "close": []})

    def get_bars(self, symbol):
        import pandas as pd

        return pd.DataFrame({"trading_date": self._dates, "close": self._closes})


def _write_calendar(tmp_path: Path, records: list[dict]) -> Path:
    p = tmp_path / "cal.json"
    p.write_text(json.dumps({"records": records}), encoding="utf-8")
    return p


def test_unresolved_events_are_skipped_not_guessed(tmp_path):
    """A record with no Gregorian date must be counted as skipped, not dropped."""
    p = _write_calendar(tmp_path, [
        {"gregorian_date": "2020-01-10", "classification": "festival",
         "market_closure": "not_independently_verified"},
        {"gregorian_date": None, "classification": "festival",
         "market_closure": "not_independently_verified"},
    ])
    # No store at all: the study must report availability without inventing data.
    res = calendar_event_study(_FakeStore([], []), "TEST", p)
    assert res["available"] is False
    assert res["events_considered"] == 2
    assert res["events_unresolved_skipped"] == 1


def test_missing_calendar_is_an_honest_unavailable(tmp_path):
    res = calendar_event_study(_FakeStore([], []), "TEST", tmp_path / "nope.json")
    assert res["available"] is False
    assert "not found" in res["reason"]


def test_event_outside_history_produces_no_event(tmp_path):
    p = _write_calendar(tmp_path, [{"gregorian_date": "1990-01-05"}])
    res = calendar_event_study(_FakeStore([date(2020, 1, 2)], [100.0]), "TEST", p)
    assert res["available"] is False
    assert res.get("events_used", 0) == 0
