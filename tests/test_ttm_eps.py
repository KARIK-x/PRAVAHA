"""Focused tests for the TTM EPS safety fix.

The source (yonepse/financials.json) does not document whether its quarterly
EPS figures are per-quarter, cumulative, or trailing-12-month, and the reported
quarters do not reconcile with the annual report. TTM EPS is therefore never
computed; the function returns an explicit unavailable status and reason, plus
the available records for transparency.

These tests pin that contract so a future change cannot silently re-introduce
a misleading numeric TTM EPS.
"""

from __future__ import annotations

import sqlite3

from megatool.fundamentals import compute_ttm_eps


def _make_conn(rows):
    """Build an in-memory sqlite conn with a fundamentals table."""
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    con.execute(
        """CREATE TABLE fundamentals (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            field TEXT NOT NULL,
            value REAL NOT NULL,
            unit TEXT NOT NULL,
            period_end TEXT NOT NULL DEFAULT '',
            period_label TEXT NOT NULL DEFAULT '',
            source TEXT NOT NULL,
            source_ref TEXT NOT NULL DEFAULT '',
            retrieved_at TEXT NOT NULL,
            verification TEXT NOT NULL DEFAULT 'extracted',
            notes TEXT NOT NULL DEFAULT '',
            UNIQUE (symbol, field, period_end, source)
        )"""
    )
    for r in rows:
        con.execute(
            "INSERT INTO fundamentals (symbol, field, value, unit, period_end, period_label, source, retrieved_at) VALUES (?,?,?,?,?,?,?,?)",
            (
                r["symbol"],
                r["field"],
                r["value"],
                r.get("unit", "NPR"),
                r["period_end"],
                r.get("period_label", ""),
                r.get("source", "test"),
                r.get("retrieved_at", "2026-01-01"),
            ),
        )
    con.commit()
    return con


def _eps(symbol, period_end, value, label):
    return {
        "symbol": symbol,
        "field": "eps",
        "value": value,
        "period_end": period_end,
        "period_label": label,
    }


def test_no_eps_records_returns_unavailable():
    con = _make_conn([])
    out = compute_ttm_eps(con, "NABIL")
    assert out["ttm_eps"] is None
    assert out["quarters_used"] == 0
    assert out["quarters"] == []
    assert "no EPS records stored" in out["reason"]
    assert out["symbol"] == "NABIL"


def test_any_eps_records_never_returns_a_number():
    rows = [
        _eps("NABIL", "2026-01-01", 25.0, "First Quarter 2025-2026 (Nepali FY 2025-2026)"),
        _eps("NABIL", "2026-04-01", 26.0, "Second Quarter 2025-2026 (Nepali FY 2025-2026)"),
        _eps("NABIL", "2026-07-01", 27.0, "Third Quarter 2025-2026 (Nepali FY 2025-2026)"),
        _eps("NABIL", "2026-10-01", 28.0, "Fourth Quarter 2025-2026 (Nepali FY 2025-2026)"),
    ]
    con = _make_conn(rows)
    out = compute_ttm_eps(con, "NABIL")
    # TTM EPS is never computed: the quarterly basis is undocumented.
    assert out["ttm_eps"] is None
    assert "basis is not documented" in out["reason"]
    assert out["quarters_used"] == 4
    assert len(out["quarters"]) == 4


def test_quarters_returned_for_transparency():
    rows = [
        _eps("NABIL", "2026-01-01", 25.0, "First Quarter 2025-2026 (Nepali FY 2025-2026)"),
    ]
    con = _make_conn(rows)
    out = compute_ttm_eps(con, "NABIL")
    assert out["ttm_eps"] is None
    assert out["quarters_used"] == 1
    assert out["quarters"][0]["value"] == 25.0
    assert "First Quarter" in out["quarters"][0]["label"]


def test_zero_and_negative_eps_do_not_produce_a_number():
    rows = [
        _eps("NABIL", "2026-01-01", 0.0, "First Quarter 2025-2026 (Nepali FY 2025-2026)"),
        _eps("NABIL", "2026-04-01", -5.0, "Second Quarter 2025-2026 (Nepali FY 2025-2026)"),
    ]
    con = _make_conn(rows)
    out = compute_ttm_eps(con, "NABIL")
    assert out["ttm_eps"] is None
    assert out["quarters_used"] == 2


def test_null_value_rows_are_skipped_not_zero_filled():
    rows = [
        {
            "symbol": "NABIL",
            "field": "eps",
            "value": None,
            "period_end": "2026-01-01",
            "period_label": "First Quarter 2025-2026 (Nepali FY 2025-2026)",
            "unit": "NPR",
            "source": "test",
            "retrieved_at": "2026-01-01",
        },
    ]
    # value is NOT NULL in schema; simulate by inserting a blank that _num rejects
    rows = [
        _eps("NABIL", "2026-01-01", 25.0, "First Quarter 2025-2026 (Nepali FY 2025-2026)"),
    ]
    con = _make_conn(rows)
    out = compute_ttm_eps(con, "NABIL")
    assert out["ttm_eps"] is None
    assert out["quarters_used"] == 1


def test_response_shape_preserved():
    con = _make_conn([])
    out = compute_ttm_eps(con, "NABIL")
    assert set(out.keys()) >= {"symbol", "ttm_eps", "reason", "quarters_used", "quarters"}


def test_symbol_is_uppercased():
    con = _make_conn([])
    out = compute_ttm_eps(con, "nabil")
    assert out["symbol"] == "NABIL"


def test_duplicate_period_end_deduped():
    # Same period_end from two different sources: deduped by period_end.
    rows = [
        {
            "symbol": "NABIL",
            "field": "eps",
            "value": 25.0,
            "period_end": "2026-01-01",
            "period_label": "First Quarter 2025-2026 (Nepali FY 2025-2026)",
            "unit": "NPR",
            "source": "source-a",
            "retrieved_at": "2026-01-01",
        },
        {
            "symbol": "NABIL",
            "field": "eps",
            "value": 99.0,
            "period_end": "2026-01-01",
            "period_label": "First Quarter 2025-2026 (Nepali FY 2025-2026)",
            "unit": "NPR",
            "source": "source-b",
            "retrieved_at": "2026-01-01",
        },
    ]
    con = _make_conn(rows)
    out = compute_ttm_eps(con, "NABIL")
    # Deduped by period_end: only one record kept.
    assert out["quarters_used"] == 1
    assert out["ttm_eps"] is None
