"""Data-source reconciliation tests (mission Phase B).

Everything here is SYNTHETIC and built inside a throwaway DuckDB/SQLite pair.
No test asserts anything about real NEPSE values. The point of the suite is that
the *comparison logic* behaves: equal values do not conflict, differences beyond
tolerance do, units are never silently reconciled, duplicates and provenance
defects are surfaced, and nothing is ever auto-resolved.
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest

from megatool import reconcile
from megatool.db import get_conn, init_app_db
from megatool.fundamentals import FundamentalRecord, import_records
from megatool.market_store import MarketStore

RETRIEVED = pd.Timestamp("2026-10-16 08:00:00")


def _bars(symbol: str, closes: np.ndarray, *, source: str = "src-a",
          open_outside: bool = False, retrieved: pd.Timestamp | None = None) -> pd.DataFrame:
    dates = pd.bdate_range("2026-01-01", periods=len(closes))
    high = closes * 1.02
    low = closes * 0.98
    open_ = closes.copy()
    if open_outside:
        open_[0] = high[0] * 1.05  # deliberately outside [low, high]
    return pd.DataFrame({
        "symbol": symbol,
        "trading_date": dates,
        "open": open_,
        "high": high,
        "low": low,
        "close": closes,
        "volume": np.full(len(closes), 5_000, dtype=np.int64),
        "turnover": closes * 5_000,
        "percent_change": 0.5,
        "source": source,
        "retrieved_at": retrieved if retrieved is not None else RETRIEVED,
        "validation_status": "valid",
    })


@pytest.fixture
def store(tmp_path):
    """A store with prices, two quote sources and two index sources' worth of data."""
    s = MarketStore(tmp_path / "recon_market.duckdb")
    rng = np.random.default_rng(11)
    closes = 100.0 * np.exp(np.cumsum(rng.normal(0.0004, 0.01, size=60)))
    s.upsert_bars(_bars("SYN1", closes))
    s.upsert_bars(_bars("SYN2", closes * 2, open_outside=True))
    # Two sources report the same quote day; one is far off the other.
    day = closes.size and str(pd.bdate_range("2026-01-01", periods=closes.size)[-1].date())
    s.upsert_quotes([
        {"symbol": "SYN1", "quote_date": day, "ltp": float(closes[-1]), "source": "quotes-a",
         "retrieved_at": RETRIEVED, "source_updated_at": pd.Timestamp("2026-03-01 10:00:00")},
        {"symbol": "SYN1", "quote_date": day, "ltp": float(closes[-1]) * 1.5, "source": "quotes-b",
         "retrieved_at": RETRIEVED, "source_updated_at": pd.Timestamp("2026-03-01 10:00:00")},
    ])
    s.upsert_index_rows([
        {"index_name": "SYNIDX", "trading_date": "2026-03-02", "close": 1000.0,
         "source": "series-a", "retrieved_at": RETRIEVED},
    ])
    yield s
    s.close()


def _seed_fundamentals() -> None:
    init_app_db()
    period = date(2026, 6, 30)
    recs = [
        # Two sources agree on eps -> no conflict.
        FundamentalRecord("SYN1", "eps", 10.0, "NPR", "src-1", period_end=period,
                          retrieved_at="2026-10-16T08:00:00+00:00"),
        FundamentalRecord("SYN1", "eps", 10.0, "NPR", "src-2", period_end=period,
                          retrieved_at="2026-10-16T08:00:00+00:00"),
        # Two sources disagree beyond tolerance on pe.
        FundamentalRecord("SYN1", "pe", 20.0, "ratio", "src-1", period_end=period,
                          retrieved_at="2026-10-16T08:00:00+00:00"),
        FundamentalRecord("SYN1", "pe", 25.0, "ratio", "src-2", period_end=period,
                          retrieved_at="2026-10-16T08:00:00+00:00"),
        # Same field, different units -> must never be numerically reconciled.
        FundamentalRecord("SYN1", "profit", 5.0, "NPR", "src-1", period_end=period,
                          retrieved_at="2026-10-16T08:00:00+00:00"),
        FundamentalRecord("SYN1", "profit", 5.0, "NPR_million", "src-2", period_end=period,
                          retrieved_at="2026-10-16T08:00:00+00:00"),
        # No period -> cannot be compared as the same vintage.
        FundamentalRecord("SYN1", "net_worth_per_share", 30.0, "NPR", "src-1",
                          retrieved_at="2026-10-16T08:00:00+00:00"),
        FundamentalRecord("SYN1", "net_worth_per_share", 31.0, "NPR", "src-2",
                          retrieved_at="2026-10-16T08:00:00+00:00"),
    ]
    with get_conn() as conn:
        import_records(recs, conn)


# --------------------------------------------------------------------------- #
# Inventory and profile
# --------------------------------------------------------------------------- #

def test_inventory_reports_real_sources(store):
    inv = reconcile.inventory(store)
    by = {d["dataset"]: d for d in inv["datasets"]}
    assert by["price_bars"]["rows"] == 120
    assert by["price_bars"]["source_count"] == 1
    assert by["market_quotes"]["source_count"] == 2
    assert by["price_bars"]["multi_source"] is False
    assert by["market_quotes"]["multi_source"] is True


def test_profile_counts_missing_values(store):
    p = reconcile.profile("price_bars", store)
    assert p["rows"] == 120
    assert p["missing_by_field"]["close"] == 0
    assert p["first_observed"] and p["last_observed"]
    assert p["adjustment"] == "adjustment_status"


def test_profile_rejects_unknown_dataset(store):
    with pytest.raises(ValueError):
        reconcile.profile("not_a_dataset", store)


# --------------------------------------------------------------------------- #
# Fundamentals comparisons
# --------------------------------------------------------------------------- #

def test_equal_values_do_not_conflict():
    _seed_fundamentals()
    conflicts = [f for f in reconcile.compare_fundamentals() if f["classification"] == "conflict"]
    assert not [f for f in conflicts if f["key"]["field"] == "eps"]
    matches = reconcile.compare_fundamentals(include_matches=True)
    assert any(f["classification"] == "match" and f["key"]["field"] == "eps" for f in matches)


def test_conflicting_values_are_reported_beyond_tolerance():
    _seed_fundamentals()
    findings = reconcile.compare_fundamentals(tolerance_pct=0.0)
    pe = [f for f in findings if f["key"]["field"] == "pe"]
    assert len(pe) == 1
    assert pe[0]["classification"] == "conflict"
    assert pe[0]["severity"] in ("medium", "high")
    # 20 vs 25 is a 20% spread -> high severity.
    assert pe[0]["severity"] == "high"
    # A very loose tolerance reclassifies the same observation, proving the
    # tolerance is actually applied rather than ignored.
    loose = reconcile.compare_fundamentals(tolerance_pct=50.0)
    pe_loose = [f for f in loose if f["key"]["field"] == "pe" and f["classification"] == "within_tolerance"]
    assert pe_loose, "tolerance must be configurable"


def test_unit_mismatch_is_never_reconciled_numerically():
    _seed_fundamentals()
    findings = reconcile.compare_fundamentals(tolerance_pct=100.0)
    profit = [f for f in findings if f["key"]["field"] == "profit"]
    assert len(profit) == 1
    assert profit[0]["classification"] == "unit_mismatch"
    assert profit[0]["severity"] == "high"


def test_unperiodised_values_are_flagged_not_compared():
    _seed_fundamentals()
    findings = reconcile.compare_fundamentals()
    unper = [f for f in findings if f["classification"] == "unperiodised"]
    assert unper, "a blank period must be reported as uncomparable"
    assert all(f["key"]["period_end"] == "" for f in unper)


def test_missing_observation_is_reported_per_source():
    init_app_db()
    period = date(2026, 6, 30)
    with get_conn() as conn:
        import_records([
            FundamentalRecord("SYN9", "eps", 1.0, "NPR", "src-1", period_end=period,
                              retrieved_at="2026-10-16T08:00:00+00:00"),
            FundamentalRecord("SYN9", "pe", 9.0, "ratio", "src-1", period_end=period,
                              retrieved_at="2026-10-16T08:00:00+00:00"),
            FundamentalRecord("SYN9", "eps", 1.0, "NPR", "src-2", period_end=period,
                              retrieved_at="2026-10-16T08:00:00+00:00"),
        ], conn)
    findings = reconcile.compare_fundamentals_coverage()
    missing = [f for f in findings if f["classification"] == "missing_observation"]
    assert any(f["key"]["source"] == "src-2" and f["key"]["field"] == "pe" for f in missing)
    assert not any(f["key"]["field"] == "eps" for f in missing), "eps is present in both sources"


def test_fundamental_timestamp_after_period_end_is_a_provenance_defect():
    init_app_db()
    with get_conn() as conn:
        import_records([
            # The period had not ended when the row was allegedly retrieved.
            FundamentalRecord("SYN8", "eps", 2.0, "NPR", "src-1", period_end=date(2027, 1, 1),
                              retrieved_at="2026-06-01T00:00:00+00:00"),
        ], conn)
    findings = reconcile.compare_timestamps("fundamentals")
    assert any(f["symbol"] == "SYN8" for f in findings)


def test_stale_fundamentals_are_flagged():
    init_app_db()
    with get_conn() as conn:
        import_records([
            FundamentalRecord("SYN7", "eps", 3.0, "NPR", "src-1", period_end=date(2015, 1, 1),
                              retrieved_at="2016-01-01T00:00:00+00:00"),
        ], conn)
    findings = reconcile.compare_fundamentals_staleness(as_of="2026-10-16")
    assert any(f["symbol"] == "SYN7" and f["classification"] == "stale" for f in findings)


# --------------------------------------------------------------------------- #
# Price comparisons
# --------------------------------------------------------------------------- #

def test_cross_source_close_vs_quote_conflict(store):
    findings = reconcile.compare_price_sources(tolerance_bps=25.0, store=store)
    conflicts = [f for f in findings if f["id"].startswith("price_bars~market_quotes")]
    assert conflicts, "a 50% quote difference must be reported"
    assert conflicts[0]["classification"] == "conflict"


def test_structural_defects_are_aggregated_not_repeated_per_bar(store):
    findings = reconcile.compare_price_sources(store=store)
    structural = [f for f in findings if f["classification"] == "invalid"]
    assert len(structural) == 1, "one finding per subtype, not one per bar"
    assert structural[0]["key"]["subtype"] == "open outside [low, high]"
    assert structural[0]["key"]["count"] == 1
    # The NEPSE daily 'open outside range' convention is a low-severity note.
    assert structural[0]["severity"] == "low"


def test_price_ingested_before_the_session_is_flagged(store):
    s2 = MarketStore(store.path.parent / "ts_probe.duckdb")
    try:
        s2.upsert_bars(_bars("TSY", np.full(5, 10.0), retrieved=pd.Timestamp("2000-01-01")))
        findings = reconcile.compare_timestamps("price_bars", store=s2)
        assert any(f["symbol"] == "TSY" for f in findings)
    finally:
        s2.close()


def test_duplicate_identity_is_detected(store, monkeypatch):
    # The shipped schema enforces uniqueness, so a probe table is used to prove
    # the detector itself works rather than asserting an impossible state.
    store.execute(
        "CREATE TABLE duplicate_probe (symbol VARCHAR, trading_date DATE, close DOUBLE, "
        "source VARCHAR, retrieved_at TIMESTAMP)"
    )
    store.execute("INSERT INTO duplicate_probe VALUES ('DUP', DATE '2026-01-05', 10.0, 'src', TIMESTAMP '2026-01-06')")
    store.execute("INSERT INTO duplicate_probe VALUES ('DUP', DATE '2026-01-05', 11.0, 'src', TIMESTAMP '2026-01-06')")
    monkeypatch.setitem(reconcile.DATASETS, "duplicate_probe", {
        "label": "probe", "backend": "duckdb", "table": "duplicate_probe",
        "identity": ("symbol", "trading_date"), "source_col": "source",
        "value_cols": ("close",), "unit_col": None, "observed_col": "trading_date",
        "ingested_col": "retrieved_at", "multi_source": False,
        "expected_cadence_days": 10, "adjustment": "not_applicable",
    })
    findings = reconcile.find_duplicates("duplicate_probe", store=store)
    assert len(findings) == 1
    assert findings[0]["classification"] == "duplicate"


def test_index_sources_are_compared(store, tmp_path):
    # index_ohlc_history lives in SQLite; seed one row that disagrees with the
    # DuckDB index_series row by far more than the tolerance.
    init_app_db()
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO index_ohlc_history (index_name, trading_date, close, ohlc_status, source) "
            "VALUES ('SYNIDX', '2026-03-02', 1500.0, 'close_only', 'history-src')"
        )
    findings = reconcile.compare_index(tolerance_bps=5.0, store=store)
    assert len(findings) == 1
    assert findings[0]["classification"] == "conflict"
    assert findings[0]["symbol"] == "SYNIDX"


# --------------------------------------------------------------------------- #
# Runs, tolerances and resolutions
# --------------------------------------------------------------------------- #

def test_run_persists_a_summary_and_returns_findings(store):
    out = reconcile.run("price_bars", store=store)
    assert out["dataset"] == "price_bars"
    assert out["findings"] == len(out["items"])
    assert out["by_classification"]
    hist = reconcile.history(dataset="price_bars")
    assert hist["runs"], "a run must be recorded"


def test_run_rejects_unknown_bucket(store):
    with pytest.raises(ValueError):
        reconcile.run("nope", store=store)


def test_resolve_records_a_decision_and_is_not_automatic(store):
    out = reconcile.run("price_bars", store=store)
    conflict = next(f for f in out["items"] if f["classification"] == "conflict")
    # Nothing was resolved by running the comparison.
    assert reconcile.history(dataset="price_bars")["resolutions"] == []
    rec = reconcile.resolve(
        dataset="price_bars", finding_key=conflict["id"],
        classification=conflict["classification"], resolution="accepted",
        chosen_source="quotes-a", note="settled close preferred for this session",
    )
    assert rec["id"] > 0
    hist = reconcile.history(dataset="price_bars")
    assert hist["resolutions"][0]["chosen_source"] == "quotes-a"


def test_resolve_validates_input():
    with pytest.raises(ValueError):
        reconcile.resolve(dataset="price_bars", finding_key="x", classification="conflict",
                          resolution="accepted")  # missing chosen_source
    with pytest.raises(ValueError):
        reconcile.resolve(dataset="price_bars", finding_key="x", classification="conflict",
                          resolution="whatever")
    with pytest.raises(ValueError):
        reconcile.resolve(dataset="price_bars", finding_key="", classification="conflict",
                          resolution="left_open")


def test_newer_source_is_not_automatically_preferred():
    """A conflict stays open; recency must not decide it."""
    init_app_db()
    period = date(2026, 6, 30)
    with get_conn() as conn:
        import_records([
            FundamentalRecord("SYN6", "eps", 1.0, "NPR", "old-src", period_end=period,
                              retrieved_at="2026-01-01T00:00:00+00:00"),
            FundamentalRecord("SYN6", "eps", 2.0, "NPR", "new-src", period_end=period,
                              retrieved_at="2026-09-01T00:00:00+00:00"),
        ], conn)
    findings = [f for f in reconcile.compare_fundamentals() if f["key"]["symbol"] == "SYN6"]
    assert len(findings) == 1
    assert findings[0]["classification"] == "conflict"
    assert "chosen_source" not in findings[0]
