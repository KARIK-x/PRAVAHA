"""Ingestion-pipeline tests: failure isolation, provenance, honest run log.

The properties under test are the ones the spec's Section 5.5 demands:

* one bad symbol never aborts the run;
* every stored row carries provenance (source, URL, retrieval time);
* the ingestion log tells the TRUTH about the run - including when the run
  achieved nothing (a "success" row for a run that stored zero rows would
  be the worst kind of lie: a green light over an empty database);
* re-ingesting the same source is idempotent.

All frames here are SYNTHETIC-TEST-FIXTURES (DataSource.SYNTHETIC_TEST) with
hand-set prices. No assertion is made about any real market.
"""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from megatool.datasources.base import BaseAdapter, SourceConfig, SourceError
from megatool.db import get_conn, init_app_db
from megatool.ingest import ingest, ingest_local_csv
from megatool.market_store import MarketStore
from megatool.models import DataSource


def _frame(symbol: str, closes: list[float], start: str = "2026-01-05") -> pd.DataFrame:
    n = len(closes)
    return pd.DataFrame(
        {
            "symbol": [symbol] * n,
            "trading_date": pd.bdate_range(start, periods=n),
            "open": closes,
            "high": [c * 1.01 for c in closes],
            "low": [c * 0.99 for c in closes],
            "close": closes,
            "volume": [1000] * n,
            "turnover": [c * 1000 for c in closes],
            "percent_change": [0.5] * n,
        }
    )


class FakeAdapter(BaseAdapter):
    """In-memory adapter; specific symbols fail on demand."""

    config = SourceConfig(
        source_id=DataSource.SYNTHETIC_TEST,
        label="SYNTHETIC-TEST-FIXTURE adapter",
        access_method="local-file",
        base_url="fixture://synthetic",
    )

    def __init__(self, frames: dict[str, pd.DataFrame], fail: set[str] | None = None):
        self.frames = frames
        self.fail = set(fail or ())

    def list_symbols(self) -> list[str]:
        return list(self.frames)

    def fetch_history(self, symbol: str) -> pd.DataFrame:
        if symbol in self.fail:
            raise SourceError(f"{symbol}: fixture failure on purpose")
        return self.frames[symbol]


class BlockedListAdapter(FakeAdapter):
    def list_symbols(self) -> list[str]:
        raise SourceError("HTTP 401: UNAUTHORIZED ACCESS (fixture)")


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "state.sqlite"
    init_app_db(path)
    return path


@pytest.fixture
def store():
    s = MarketStore(":memory:")
    yield s
    s.close()


def _log_rows(db):
    with get_conn(db) as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM ingestion_log").fetchall()]


def _master_symbols(store) -> set[str]:
    # security_master lives in the DuckDB market store, not the SQLite app db
    return set(store.query_df("SELECT symbol FROM security_master")["symbol"])


# ----------------------------------------------------------------- happy path
def test_happy_path_stores_bars_with_full_provenance_and_a_truthful_log(db, store):
    adapter = FakeAdapter({"AAA": _frame("AAA", [100.0, 101.0, 102.0])})
    res = ingest(adapter, store=store, db_path=db)

    assert res.symbols_succeeded == 1 and res.symbols_failed == 0
    assert res.rows_read == 3 and res.rows_inserted == 3 and res.rows_updated == 0
    assert res.coverage_start == date(2026, 1, 5)
    assert res.synthetic is True
    assert res.errors == [] and res.warnings == []

    bars = store.get_bars("AAA")
    assert len(bars) == 3
    assert set(bars["source"]) == {DataSource.SYNTHETIC_TEST.value}
    assert set(bars["source_url"]) == {"fixture://synthetic"}
    assert set(bars["adjustment_status"]) == {"unadjusted"}
    assert bars["retrieved_at"].notna().all()

    log = _log_rows(db)
    assert len(log) == 1
    assert log[0]["status"] == "success"
    assert log[0]["synthetic"] == 1
    assert log[0]["rows_inserted"] == 3
    assert _master_symbols(store) == {"AAA"}


def test_reingesting_the_same_source_updates_instead_of_duplicating(db, store):
    adapter = FakeAdapter({"AAA": _frame("AAA", [100.0, 101.0, 102.0])})
    first = ingest(adapter, store=store, db_path=db)
    second = ingest(adapter, store=store, db_path=db)
    assert first.rows_inserted == 3
    assert second.rows_inserted == 0 and second.rows_updated == 3
    assert len(store.get_bars("AAA")) == 3  # never doubled


# --------------------------------------------------------------- failure paths
def test_one_bad_symbol_never_aborts_the_run(db, store):
    adapter = FakeAdapter(
        {"AAA": _frame("AAA", [100.0, 101.0]), "BAD": _frame("BAD", [50.0, 51.0])},
        fail={"BAD"},
    )
    seen: list[tuple[str, int, int]] = []
    res = ingest(adapter, store=store, db_path=db, progress=lambda s, i, t: seen.append((s, i, t)))

    assert res.symbols_succeeded == 1 and res.symbols_failed == 1
    assert any("BAD" in e and "fixture failure" in e for e in res.errors)
    assert any("partial success" in w for w in res.warnings)
    assert seen == [("AAA", 1, 2), ("BAD", 2, 2)]

    # the good symbol is fully stored; the bad one left nothing behind
    assert len(store.get_bars("AAA")) == 2
    assert store.get_bars("BAD").empty
    # the security master claims data only for what actually delivered bars
    assert _master_symbols(store) == {"AAA"}

    log = _log_rows(db)
    assert log[0]["status"] == "partial"
    assert log[0]["symbols_failed"] == 1 and log[0]["symbols_succeeded"] == 1


def test_every_symbol_failing_is_a_failed_run_not_a_green_one(db, store):
    adapter = FakeAdapter({"AAA": _frame("AAA", [100.0])}, fail={"AAA"})
    res = ingest(adapter, store=store, db_path=db)
    assert res.symbols_succeeded == 0 and res.symbols_failed == 1
    assert "every symbol failed" in res.errors
    assert _log_rows(db)[0]["status"] == "failed"
    assert _master_symbols(store) == set()


def test_a_malformed_response_is_counted_as_a_failure_not_a_crash(db, store):
    """B-37/38: a symbol whose payload is structurally broken must not abort.

    A frame missing ``trading_date`` raises a non-SourceError deep inside
    validation; the defensive handler must count it as a failed symbol (not
    a run-crashing exception), keep the good symbol, and log the truth.
    """
    good = _frame("AAA", [100.0, 101.0])
    malformed = _frame("BAD", [50.0, 51.0]).drop(columns=["trading_date"])

    class MalformedAdapter(FakeAdapter):
        def fetch_history(self, symbol: str) -> pd.DataFrame:
            return malformed if symbol == "BAD" else self.frames[symbol]

    adapter = MalformedAdapter({"AAA": good, "BAD": malformed})
    res = ingest(adapter, store=store, db_path=db)

    assert res.symbols_succeeded == 1 and res.symbols_failed == 1
    assert any("BAD" in e and "unexpected" in e for e in res.errors)
    assert len(store.get_bars("AAA")) == 2
    assert store.get_bars("BAD").empty
    assert _master_symbols(store) == {"AAA"}  # only the good symbol is claimed
    assert _log_rows(db)[0]["status"] == "partial"


def test_an_empty_source_response_is_a_failure_not_a_silent_no_op(db, store):
    adapter = FakeAdapter({"AAA": _frame("AAA", [])})
    res = ingest(adapter, store=store, db_path=db)
    assert res.symbols_failed == 1
    assert any("no rows" in e for e in res.errors)
    assert _log_rows(db)[0]["status"] == "failed"


def test_a_blocked_symbol_list_never_logs_a_success(db, store):
    """The list-symbols failure path stores nothing: the log must say so.

    Before the fix this run was logged as status="success" with zero rows
    inserted - a green light over an empty database.
    """
    adapter = BlockedListAdapter({"AAA": _frame("AAA", [100.0])})
    res = ingest(adapter, store=store, db_path=db)
    assert res.symbols_requested == 0 and res.rows_inserted == 0
    assert any("UNAUTHORIZED ACCESS" in e for e in res.errors)
    log = _log_rows(db)
    assert log[0]["status"] == "failed"
    assert log[0]["rows_inserted"] == 0


def test_an_empty_universe_is_reported_not_silently_succeeded(db, store):
    adapter = FakeAdapter({})
    res = ingest(adapter, store=store, db_path=db)
    assert "no symbols to ingest" in res.errors
    assert _log_rows(db)[0]["status"] == "failed"


# --------------------------------------------------------------- local CSV path
def test_ingest_local_csv_round_trip(db, store, tmp_path):
    csv_path = tmp_path / "NABIL.csv"
    csv_path.write_text(
        "date,open,high,low,close,volume,turnover,percent_change\n"
        "2026-01-05,100,101,99,100.5,1000,100500,0.5\n"
        "2026-01-06,100.5,102,100,101.5,1100,111650,1.0\n"
    )
    res = ingest_local_csv(csv_path, symbol="NABIL", store=store, db_path=db)
    assert res.symbols_succeeded == 1
    bars = store.get_bars("NABIL")
    assert len(bars) == 2
    assert set(bars["source"]) == {DataSource.LOCAL_IMPORT.value}
    # the filename travels with every row so a stored bar can be traced back
    # to the exact file the owner imported
    assert set(bars["source_url"]) == {"NABIL.csv"}


def test_local_csv_with_a_bad_symbol_field_fails_that_symbol_only(db, store, tmp_path):
    csv_path = tmp_path / "OTHER.csv"
    csv_path.write_text("date,close\n2026-01-05,100\n")
    res = ingest_local_csv(csv_path, symbol="NABIL", store=store, db_path=db)
    assert res.symbols_succeeded == 1
    assert len(store.get_bars("NABIL")) == 1
    assert _master_symbols(store) == {"NABIL"}
