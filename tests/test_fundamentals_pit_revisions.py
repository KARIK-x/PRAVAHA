"""Fundamental revision history and point-in-time tests (NF-028 / NF-025).

Synthetic values only. The tests pin the two honesty guarantees: a revision is
recorded only when a value actually changes (and only from the moment recording
began), and the point-in-time view uses the *ingestion* timestamp as knowledge
time, which is reported as a limitation rather than presented as publication time.
"""

from __future__ import annotations

from datetime import date

import pytest

from megatool.db import get_conn, init_app_db
from megatool.fundamentals import (
    FundamentalRecord,
    import_records,
    point_in_time_coverage,
    query_revisions,
    query_symbol_as_of,
    revision_monitor,
)


@pytest.fixture(autouse=True)
def _schema():
    init_app_db()


def _rec(value, *, retrieved="2026-10-16T08:00:00+00:00", source="src-1",
         period=date(2026, 6, 30)) -> FundamentalRecord:
    return FundamentalRecord("SYN1", "eps", value, "NPR", source, period_end=period,
                             retrieved_at=retrieved)


def test_first_import_records_no_revision():
    with get_conn() as conn:
        out = import_records([_rec(10.0)], conn)
        assert out == {"inserted": 1, "updated": 0, "total": 1}
        monitor = revision_monitor(conn)
    assert monitor["revision_count"] == 0
    assert monitor["status"] == "no_revisions_recorded"
    assert "does not prove the stored values were never revised" in monitor["note"]


def test_reimporting_the_same_value_records_no_revision():
    with get_conn() as conn:
        import_records([_rec(10.0)], conn)
        out = import_records([_rec(10.0)], conn)
        assert out["updated"] == 1 and out["inserted"] == 0
        assert revision_monitor(conn)["revision_count"] == 0


def test_changed_value_records_old_and_new():
    with get_conn() as conn:
        import_records([_rec(10.0)], conn)
        import_records([_rec(12.5)], conn)
        monitor = revision_monitor(conn)
    assert monitor["revision_count"] == 1
    row = monitor["revisions"][0]
    assert row["old_value"] == 10.0
    assert row["new_value"] == 12.5
    assert row["symbol"] == "SYN1" and row["field"] == "eps"
    assert row["changed_at"]


def test_second_source_change_is_tracked_per_source():
    with get_conn() as conn:
        import_records([_rec(10.0, source="src-1"), _rec(10.0, source="src-2")], conn)
        import_records([_rec(11.0, source="src-2")], conn)
        rows = query_revisions(conn)
    assert len(rows) == 1
    assert rows[0]["source"] == "src-2"


def test_revisions_filter_by_symbol():
    with get_conn() as conn:
        import_records([_rec(10.0)], conn)
        import_records([_rec(20.0)], conn)
        other = FundamentalRecord("SYN2", "eps", 5.0, "NPR", "src-1",
                                  period_end=date(2026, 6, 30),
                                  retrieved_at="2026-10-16T08:00:00+00:00")
        import_records([other], conn)
        import_records([FundamentalRecord("SYN2", "eps", 6.0, "NPR", "src-1",
                                          period_end=date(2026, 6, 30),
                                          retrieved_at="2026-10-16T08:00:00+00:00")], conn)
        assert len(query_revisions(conn)) == 2
        assert len(query_revisions(conn, symbol="SYN2")) == 1


def test_revision_monitor_states_its_coverage_limit():
    with get_conn() as conn:
        import_records([_rec(10.0)], conn)
        import_records([_rec(11.0)], conn)
        monitor = revision_monitor(conn)
    assert "cannot be reconstructed" in monitor["coverage"]


# --------------------------------------------------------------------------- #
# Point in time
# --------------------------------------------------------------------------- #

def test_as_of_excludes_rows_ingested_later():
    with get_conn() as conn:
        import_records([_rec(10.0, retrieved="2026-01-15T00:00:00+00:00")], conn)
        import_records([_rec(11.0, retrieved="2026-09-15T00:00:00+00:00", source="src-2")], conn)
        early = query_symbol_as_of(conn, "SYN1", "2026-06-01")
        late = query_symbol_as_of(conn, "SYN1", "2026-12-01")
    assert len(early) == 1 and early[0]["value"] == 10.0
    assert len(late) == 2
    assert {r["value"] for r in late} == {10.0, 11.0}


def test_as_of_before_any_ingestion_returns_nothing_not_a_guess():
    with get_conn() as conn:
        import_records([_rec(10.0)], conn)
        assert query_symbol_as_of(conn, "SYN1", "2020-01-01") == []


def test_point_in_time_coverage_is_explicitly_about_ingestion_time():
    with get_conn() as conn:
        import_records([_rec(10.0)], conn)
        cov = point_in_time_coverage(conn, "SYN1")
    assert cov["knowledge_time"] == "retrieved_at (ingestion timestamp)"
    assert "NOT IMPLEMENTED" in cov["limitation"]
    assert cov["records"] == 1
    assert cov["first_ingested"] and cov["last_ingested"]


def test_unknown_symbol_as_of_is_empty_and_explained():
    with get_conn() as conn:
        import_records([_rec(10.0)], conn)
        rows = query_symbol_as_of(conn, "NOPE", "2026-12-01")
        cov = point_in_time_coverage(conn, "NOPE")
    assert rows == []
    assert cov["records"] == 0
    assert cov["first_ingested"] is None
