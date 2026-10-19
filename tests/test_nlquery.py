"""Natural-language query tests (mission Phase E / NF-016).

The security properties are the point: a question that cannot be expressed as a
supported plan is rejected, and there is no path from user text to arbitrary SQL.
Everything is synthetic.
"""

from __future__ import annotations

from datetime import date

import numpy as np
import pandas as pd
import pytest

from megatool import nlquery
from megatool.db import get_conn, init_app_db
from megatool.fundamentals import FundamentalRecord, import_records
from megatool.market_store import MarketStore

RETRIEVED = pd.Timestamp("2026-10-16 08:00:00")


@pytest.fixture
def store(tmp_path):
    s = MarketStore(tmp_path / "nlq_market.duckdb")
    rng = np.random.default_rng(21)
    for name, base in (("SYN1", 100.0), ("SYN2", 250.0)):
        closes = base * np.exp(np.cumsum(rng.normal(0.0004, 0.01, size=50)))
        dates = pd.bdate_range("2026-01-01", periods=len(closes))
        s.upsert_bars(pd.DataFrame({
            "symbol": name, "trading_date": dates, "open": closes, "high": closes * 1.01,
            "low": closes * 0.99, "close": closes,
            "volume": np.arange(len(closes), dtype="int64") + 1,
            "turnover": closes * 10, "percent_change": 0.0, "source": "synthetic-test",
            "retrieved_at": RETRIEVED, "validation_status": "valid",
        }))
    yield s
    s.close()


@pytest.fixture(autouse=True)
def _schema():
    init_app_db()
    with get_conn() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO securities (symbol, name, sector, delisted, source, first_seen) "
            "VALUES ('SYN1', 'Synthetic One', 'Banking', 0, 'synthetic-test', '2026-01-01')"
        )
        conn.execute(
            "INSERT OR IGNORE INTO securities (symbol, name, sector, delisted, source, first_seen) "
            "VALUES ('SYN2', 'Synthetic Two', 'Hydropower', 0, 'synthetic-test', '2026-01-01')"
        )
    with get_conn() as conn:
        import_records([
            FundamentalRecord("SYN1", "eps", 12.5, "NPR", "src-1", period_end=date(2026, 6, 30),
                              retrieved_at="2026-10-16T08:00:00+00:00"),
            FundamentalRecord("SYN1", "eps", 11.0, "NPR", "src-1", period_end=date(2025, 6, 30),
                              retrieved_at="2026-10-16T08:00:00+00:00"),
        ], conn)


# --------------------------------------------------------------------------- #
# Parsing and execution
# --------------------------------------------------------------------------- #

def test_count_securities(store):
    out = nlquery.run("how many securities are stored", store=store)
    assert out["status"] == "ok"
    assert out["rows"][0]["n"] == 2


def test_list_securities_with_limit(store):
    out = nlquery.run("list 1 securities", store=store)
    assert out["status"] == "ok"
    assert out["row_count"] == 1
    assert out["plan"]["limit"] == 1


def test_latest_price(store):
    out = nlquery.run("price of SYN1", store=store)
    assert out["status"] == "ok"
    assert out["rows"][0]["symbol"] == "SYN1"
    assert out["rows"][0]["close"] > 0


def test_price_on_a_date(store):
    day = str(pd.bdate_range("2026-01-01", periods=50)[10].date())
    out = nlquery.run(f"close of SYN1 on {day}", store=store)
    assert out["status"] == "ok"
    assert out["rows"][0]["trading_date"][:10] == day


def test_average_close_over_a_window(store):
    out = nlquery.run("average close of SYN1 over last 10 days", store=store)
    assert out["status"] == "ok"
    assert out["rows"][0]["bars"] == 10


def test_highest_close_in_a_year(store):
    out = nlquery.run("highest close of SYN1 in 2026", store=store)
    assert out["status"] == "ok"
    assert out["rows"][0]["value"] > 0


def test_bar_count_and_coverage(store):
    bars = nlquery.run("how many bars for SYN1", store=store)
    assert bars["rows"][0]["bars"] == 50
    cov = nlquery.run("date range for SYN1", store=store)
    assert cov["rows"][0]["first_date"][:10] == "2026-01-01"


def test_top_by_volume(store):
    out = nlquery.run("top 2 symbols by volume", store=store)
    assert out["status"] == "ok"
    assert out["row_count"] == 2


def test_fundamental_latest_value(store):
    out = nlquery.run("eps of SYN1", store=store)
    assert out["status"] == "ok"
    assert out["rows"][0]["field"] == "eps"


def test_fundamental_history(store):
    out = nlquery.run("eps history of SYN1", store=store)
    assert out["status"] == "ok"
    assert out["row_count"] == 2


def test_empty_result_reports_what_is_missing(store):
    out = nlquery.run("price of ZZZ9", store=store)
    assert out["status"] == "ok"
    assert out["row_count"] == 0
    assert out["missing"], "an empty result must name what was not found"


# --------------------------------------------------------------------------- #
# Security
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize("question", [
    "drop table price_bars",
    "select * from users",
    "'; DROP TABLE price_bars; --",
    "price of SYN1'; DELETE FROM securities; --",
    "show me all rows from sqlite_master",
    "list everything from information_schema.tables",
])
def test_malicious_or_unsupported_questions_are_rejected(question, store):
    out = nlquery.run(question, store=store)
    assert out["status"] == "rejected"
    with get_conn() as conn:  # the tables still exist afterwards
        assert conn.execute("SELECT COUNT(*) FROM securities").fetchone()[0] >= 2


def test_rejection_lists_the_supported_shapes(store):
    out = nlquery.run("what is the meaning of life", store=store)
    assert out["status"] == "rejected"
    assert out["supported"]


def test_plan_with_a_non_allowlisted_table_is_refused(store):
    with pytest.raises(nlquery.QueryError):
        nlquery.execute({"intent": "count_securities", "dataset": "users",
                         "fields": ["symbol"], "filters": {}, "limit": 1,
                         "calculation": "count"}, store=store)


def test_plan_with_a_non_allowlisted_column_is_refused(store):
    with pytest.raises(nlquery.QueryError):
        nlquery.execute({"intent": "list_securities", "dataset": "securities",
                         "fields": ["symbol", "password"], "filters": {}, "limit": 1,
                         "calculation": "list"}, store=store)


def test_excessive_limit_is_refused(store):
    with pytest.raises(nlquery.QueryError):
        nlquery.validate({"intent": "list_securities", "dataset": "securities",
                          "fields": ["symbol"], "filters": {}, "limit": 10_000,
                          "calculation": "list"})


def test_invalid_symbol_in_a_plan_is_refused(store):
    with pytest.raises(nlquery.QueryError):
        nlquery.validate({"intent": "latest_price", "dataset": "price_bars",
                          "fields": ["symbol", "close"],
                          "filters": {"symbol": "SYN; DROP"}, "limit": 1,
                          "calculation": "latest"})


def test_invalid_date_in_a_plan_is_refused(store):
    with pytest.raises(nlquery.QueryError):
        nlquery.validate({"intent": "price_on_date", "dataset": "price_bars",
                          "fields": ["symbol", "close"],
                          "filters": {"symbol": "SYN1", "date": "2026-13-99; --"},
                          "limit": 1, "calculation": "point"})


def test_allowlist_is_the_only_way_to_reach_a_table():
    assert set(nlquery._ALLOW) == {"securities", "fundamentals", "collector_quotes",
                                   "price_bars", "index_series"}
    # No dataset on the allowlist is writable.
    for spec in nlquery._ALLOW.values():
        assert spec["table"] not in ("users", "sqlite_master")


# --------------------------------------------------------------------------- #
# Provenance and history
# --------------------------------------------------------------------------- #

def test_result_carries_provenance_and_limitations(store):
    out = nlquery.run("price of SYN1", store=store)
    assert out["provenance"]
    assert out["limitations"]
    assert "as_of" in out


def test_runs_are_recorded_including_rejections(store):
    nlquery.run("price of SYN1", store=store)
    nlquery.run("please delete everything", store=store)
    hist = nlquery.history()
    statuses = {h["status"] for h in hist}
    assert "ok" in statuses and "rejected" in statuses


def test_parse_rejects_empty_question():
    with pytest.raises(nlquery.QueryError):
        nlquery.parse("   ")
