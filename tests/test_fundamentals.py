"""Fundamentals Lab tests (Priority 4 of MEGA_TOOL_RESEARCH_REPORT.md).

All records here are synthetic. Nothing asserts anything about real company
financials, and no test claims a ratio predicts anything.
"""

from __future__ import annotations

from datetime import date

import pytest

from megatool.db import init_app_db
from megatool.fundamentals import (
    KNOWN_FIELDS,
    FundamentalError,
    FundamentalRecord,
    compute_symbol_ratios,
    fundamentals_summary,
    import_records,
    query_symbol,
    ratio_dividend_yield,
    ratio_pb,
    ratio_pe,
    records_from_rows,
    review_source,
)

PERIOD = date(2026, 3, 31)
#: price_as_of is now REQUIRED on every ratio, so a ratio can never be computed
#: without saying which date the price belongs to. Without it the staleness
#: guard was skipped entirely and a 2015 EPS divided cleanly into a current
#: price. 2026-03-31 -> 2026-10-12 is 195 days, inside the 400-day limit.
PRICE_DATE = date(2026, 10, 12)


def rec(**kw) -> FundamentalRecord:
    """A valid, verified synthetic record; override any field per test."""
    base = dict(
        symbol="NABIL",
        field="eps",
        value=25.0,
        unit="NPR",
        source="synthetic-test",
        period_end=PERIOD,
        verification="verified",
    )
    base.update(kw)
    return FundamentalRecord(**base)


@pytest.fixture()
def conn(tmp_path):
    path = tmp_path / "state.sqlite"
    init_app_db(path)
    import sqlite3

    c = sqlite3.connect(path)
    c.row_factory = sqlite3.Row
    yield c
    c.close()


# ------------------------------------------------------------------ validation


def test_valid_record_passes():
    rec().validate()


def test_unknown_field_allowed_when_unit_given():
    # Organisations publish metrics outside the built-in list; they are
    # accepted as long as the unit is stated.
    r = rec(field="moon_phase", unit="ratio")
    r.validate()
    assert not r.known_field


def test_known_field_with_wrong_unit_rejected():
    # 'eps' is a known field and must carry NPR, not shares.
    with pytest.raises(FundamentalError, match="unit"):
        rec(field="eps", unit="shares").validate()


def test_empty_unit_rejected():
    with pytest.raises(FundamentalError, match="unit is required"):
        rec(field="moon_phase", unit="").validate()


def test_blank_field_name_rejected():
    with pytest.raises(FundamentalError, match="field"):
        rec(field="").validate()


def test_wrong_unit_rejected():
    with pytest.raises(FundamentalError, match="unit"):
        rec(unit="shares").validate()


def test_missing_source_rejected():
    with pytest.raises(FundamentalError, match="source is required"):
        rec(source="   ").validate()


def test_non_finite_value_rejected():
    with pytest.raises(FundamentalError, match="finite"):
        rec(value=float("nan")).validate()
    with pytest.raises(FundamentalError, match="finite"):
        rec(value=float("inf")).validate()


def test_bool_value_rejected():
    with pytest.raises(FundamentalError, match="numeric"):
        rec(value=True).validate()


def test_bad_symbol_rejected():
    with pytest.raises(FundamentalError, match="symbol"):
        rec(symbol="NAB IL!").validate()


def test_bad_verification_rejected():
    with pytest.raises(FundamentalError, match="verification"):
        rec(verification="probably-right").validate()


def test_every_known_field_has_a_unit():
    for name, spec in KNOWN_FIELDS.items():
        assert spec["unit"], name
        assert spec["label"], name


# ------------------------------------------------------------------ CSV import


def test_rows_to_records_happy_path():
    rows = [
        {
            "symbol": "nabil",
            "field": "EPS",
            "value": "25.5",
            "source": "test-file.csv",
            "period_end": "2026-03-31",
        }
    ]
    (r,) = records_from_rows(rows)
    assert r.symbol == "NABIL"
    assert r.field == "eps"
    assert r.value == 25.5
    assert r.unit == "NPR"  # filled in from KNOWN_FIELDS
    assert r.period_end == PERIOD
    assert r.verification == "extracted"


def test_rows_reject_missing_required_column():
    with pytest.raises(FundamentalError, match="source"):
        records_from_rows([{"symbol": "NABIL", "field": "eps", "value": 1}])


def test_zero_value_is_a_value_not_a_missing_column():
    """A real 0 must survive; only blank/None is missing.

    Regression: ``row.get(c, "") or ""`` collapses ``0`` to ``""``, so a P/E of
    exactly zero (a company with no earnings) or a nil dividend was reported as
    a missing column and the entire file was refused.
    """
    rows = [
        {"symbol": "NABIL", "field": "eps", "value": 0.0, "source": "s"},
        {"symbol": "NABIL", "field": "pe", "value": 0, "unit": "ratio", "source": "s"},
    ]
    out = records_from_rows(rows)
    assert [r.value for r in out] == [0.0, 0.0]
    assert all(r.field in ("eps", "pe") for r in out)


def test_blank_value_is_still_rejected_as_missing():
    """The other half of the rule: '' and None remain missing."""
    for bad in ("", None, "   "):
        with pytest.raises(FundamentalError, match="missing required column"):
            records_from_rows([{"symbol": "NABIL", "field": "eps", "value": bad, "source": "s"}])


def test_rows_reject_bad_date():
    with pytest.raises(FundamentalError, match="date"):
        records_from_rows(
            [
                {
                    "symbol": "NABIL",
                    "field": "eps",
                    "value": 1,
                    "source": "s",
                    "period_end": "last Tuesday",
                }
            ]
        )


def test_rows_reject_non_numeric_value():
    with pytest.raises(FundamentalError, match="not numeric"):
        records_from_rows([{"symbol": "NABIL", "field": "eps", "value": "n/a", "source": "s"}])


def test_rows_reject_duplicate_identity():
    row = {"symbol": "NABIL", "field": "eps", "value": 1, "source": "s", "period_end": "2026-03-31"}
    with pytest.raises(FundamentalError, match="duplicate"):
        records_from_rows([row, dict(row, value=2)])


def test_unknown_field_requires_explicit_unit():
    with pytest.raises(FundamentalError, match="explicit unit"):
        records_from_rows([{"symbol": "NABIL", "field": "odd_metric", "value": 1, "source": "s"}])


def test_unknown_field_accepted_with_unit():
    (r,) = records_from_rows(
        [
            {
                "symbol": "NABIL",
                "field": "odd_metric",
                "value": 1,
                "source": "s",
                "unit": "ratio",
            }
        ]
    )
    assert r.unit == "ratio"


def test_error_message_names_the_row():
    with pytest.raises(FundamentalError, match="row 2"):
        records_from_rows([{"symbol": "NABIL", "field": "nope", "value": 1, "source": "s"}])


def test_empty_input_rejected():
    with pytest.raises(FundamentalError, match="no rows"):
        records_from_rows([])


# -------------------------------------------------------------------- storage


def test_import_and_query(conn):
    import_records([rec()], conn)
    rows = query_symbol(conn, "NABIL")
    assert len(rows) == 1
    assert rows[0]["field"] == "eps"
    assert rows[0]["period_end"] == "2026-03-31"
    assert rows[0]["period_known"] is True
    assert rows[0]["source"] == "synthetic-test"


def test_reimport_is_idempotent(conn):
    import_records([rec()], conn)
    import_records([rec()], conn)
    assert len(query_symbol(conn, "NABIL")) == 1


def test_reimport_updates_value(conn):
    import_records([rec(value=25.0)], conn)
    import_records([rec(value=27.5)], conn)
    rows = query_symbol(conn, "NABIL")
    assert len(rows) == 1
    assert rows[0]["value"] == 27.5


def test_unknown_period_rows_do_not_duplicate(conn):
    """'' must behave as a real key value, not as SQL NULL."""
    a = rec(period_end=None, source="s1")
    import_records([a], conn)
    import_records([a], conn)
    rows = query_symbol(conn, "NABIL")
    assert len(rows) == 1
    assert rows[0]["period_end"] is None
    assert rows[0]["period_known"] is False


def test_two_sources_same_period_both_kept(conn):
    import_records([rec(source="alpha")], conn)
    import_records([rec(source="beta")], conn)
    rows = query_symbol(conn, "NABIL")
    assert len(rows) == 2
    assert {r["source"] for r in rows} == {"alpha", "beta"}


def test_query_is_case_insensitive(conn):
    import_records([rec()], conn)
    assert query_symbol(conn, "nabil")


def test_summary_counts(conn):
    import_records([rec(), rec(field="dps", unit="NPR", value=5.0)], conn)
    import_records([rec(period_end=None, verification="extracted", source="pdf")], conn)
    s = fundamentals_summary(conn)
    assert s["total"] == 3
    assert s["symbols"] == 1
    # two verified (synthetic-test) + one merely extracted (pdf)
    assert s["by_verification"]["verified"] == 2
    assert s["by_verification"]["extracted"] == 1
    assert s["by_field"]["eps"] == 2
    assert s["without_period"] == 1
    assert "trustworthy" in s["note"]


# -------------------------------------------------------------- P/E ratio math


def test_pe_is_price_over_eps():
    eps = rec(field="eps", value=25.0)
    assert ratio_pe(500.0, eps, price_as_of=PRICE_DATE) == pytest.approx(20.0)


def test_pe_refuses_zero_eps():
    with pytest.raises(FundamentalError, match="not positive"):
        ratio_pe(500.0, rec(value=0.0), price_as_of=PRICE_DATE)


def test_pe_refuses_negative_eps():
    with pytest.raises(FundamentalError, match="not positive"):
        ratio_pe(500.0, rec(value=-4.0), price_as_of=PRICE_DATE)


def test_pe_refuses_unreviewed_eps():
    with pytest.raises(FundamentalError, match="not reviewed"):
        ratio_pe(500.0, rec(verification="extracted"), price_as_of=PRICE_DATE)


def test_pe_refuses_unknown_period():
    with pytest.raises(FundamentalError, match="reporting period"):
        ratio_pe(500.0, rec(period_end=None), price_as_of=PRICE_DATE)


def test_pe_refuses_mismatched_periods():
    eps = rec(period_end=date(2026, 3, 31))
    price = rec(field="price", period_end=date(2024, 3, 31), value=500.0)
    with pytest.raises(FundamentalError, match="differ by"):
        ratio_pe(price, eps, price_as_of=PRICE_DATE)


def test_pe_refuses_stale_input_when_price_date_given():
    eps = rec(period_end=date(2020, 3, 31))
    with pytest.raises(FundamentalError, match="stale"):
        ratio_pe(500.0, eps, price_as_of=PRICE_DATE)


def test_pe_accepts_compatible_periods():
    eps = rec(period_end=date(2026, 3, 31))
    price = rec(field="price", period_end=date(2026, 2, 28), value=500.0)
    assert ratio_pe(price, eps, price_as_of=PRICE_DATE) == pytest.approx(20.0)


def test_pe_refuses_zero_denominator():
    with pytest.raises(FundamentalError, match="not positive"):
        ratio_pe(500.0, rec(value=0.0), price_as_of=PRICE_DATE)


# ------------------------------------------------------------------ other ratios


def test_pb_is_price_over_net_worth():
    nw = rec(field="net_worth_per_share", value=250.0)
    assert ratio_pb(500.0, nw, price_as_of=PRICE_DATE) == pytest.approx(2.0)


def test_pb_refuses_non_positive_net_worth():
    with pytest.raises(FundamentalError, match="not positive"):
        ratio_pb(500.0, rec(field="net_worth_per_share", value=-10.0), price_as_of=PRICE_DATE)


def test_dividend_yield_is_percentage():
    dps = rec(field="dps", value=12.5)
    assert ratio_dividend_yield(dps, 250.0, price_as_of=PRICE_DATE) == pytest.approx(5.0)


def test_dividend_yield_refuses_unreviewed():
    with pytest.raises(FundamentalError, match="not reviewed"):
        ratio_dividend_yield(
            rec(field="dps", verification="extracted"), 250.0, price_as_of=PRICE_DATE
        )


def test_dividend_yield_refuses_negative_dps():
    with pytest.raises(FundamentalError, match="negative"):
        ratio_dividend_yield(rec(field="dps", value=-1.0), 250.0, price_as_of=PRICE_DATE)


def test_dividend_yield_refuses_non_positive_price():
    with pytest.raises(FundamentalError, match="not positive"):
        ratio_dividend_yield(rec(field="dps"), 0.0, price_as_of=PRICE_DATE)


def test_ratio_never_returns_nan_or_inf():
    for fn, args in (
        (ratio_pe, (500.0, rec(value=1e-9))),
        (ratio_pb, (500.0, rec(field="net_worth_per_share", value=1e-9))),
    ):
        out = fn(*args, price_as_of=PRICE_DATE)
        assert out == out and out not in (float("inf"), float("-inf"))


# -------------------------------------------------- price_as_of is not optional
# Regression tests for the bypass: price_as_of used to default to None, which
# disabled the staleness guard and returned P/E = 20.00 for a 2015 EPS against
# a 2026 price. The argument is now mandatory on all three ratios.


@pytest.mark.parametrize("fn,args", [("ratio_pe", (500.0,)), ("ratio_pb", (500.0,))])
def test_ratio_refuses_to_run_without_a_price_date(fn, args):
    fn_mod = ratio_pe if fn == "ratio_pe" else ratio_pb
    operand = rec(value=25.0) if fn == "ratio_pe" else rec(field="net_worth_per_share", value=250.0)
    with pytest.raises(TypeError):
        fn_mod(*args, operand)  # no price_as_of


def test_yield_refuses_to_run_without_a_price_date():
    with pytest.raises(TypeError):
        ratio_dividend_yield(rec(field="dps"), 250.0)


def test_omitting_price_date_cannot_reproduce_the_old_bypass():
    """The exact reproduction from the audit: 2015 EPS into a current price."""
    stale = rec(period_end=date(2015, 3, 31), value=25.0)
    # With the date given, the stale EPS is refused (this is the whole point).
    with pytest.raises(FundamentalError, match="stale"):
        ratio_pe(500.0, stale, price_as_of=date(2026, 10, 12))
    # And there is no way to ask for the old behaviour: omitting the date is a
    # TypeError, not a silent pass-through of 20.00.
    with pytest.raises(TypeError):
        ratio_pe(500.0, stale)


def test_dividend_yield_refuses_a_stale_dps():
    stale = rec(field="dps", value=12.5, period_end=date(2018, 3, 31))
    with pytest.raises(FundamentalError, match="stale"):
        ratio_dividend_yield(stale, 250.0, price_as_of=PRICE_DATE)


def test_dividend_yield_refuses_a_dps_of_unknown_vintage():
    with pytest.raises(FundamentalError, match="reporting period"):
        ratio_dividend_yield(rec(field="dps", period_end=None), 250.0, price_as_of=PRICE_DATE)


# ------------------------------------------------- operands must be the right field
# KNOWN_FIELDS stores a unit per field "so a ratio can refuse to divide
# mismatched quantities". These pin that promise. Before it was enforced,
# ratio_pe(500.0, revenue_record) returned 0.1000 and was presented as a P/E.


def test_pe_refuses_a_record_that_is_not_eps():
    for field in ("revenue", "profit", "dps", "net_worth_per_share", "total_shares"):
        with pytest.raises(FundamentalError, match="requires eps"):
            ratio_pe(500.0, rec(field=field), price_as_of=PRICE_DATE)


def test_pe_refuses_an_eps_measured_in_the_wrong_unit():
    for unit in ("shares", "crore", "lakh", "ratio"):
        with pytest.raises(FundamentalError, match="requires 'NPR'"):
            ratio_pe(500.0, rec(unit=unit), price_as_of=PRICE_DATE)


def test_pb_refuses_a_record_that_is_not_book_value():
    for field in ("eps", "revenue", "dps", "paid_up_capital"):
        with pytest.raises(FundamentalError, match="requires net_worth_per_share"):
            ratio_pb(500.0, rec(field=field), price_as_of=PRICE_DATE)


def test_pb_accepts_either_book_value_field():
    for field in ("net_worth_per_share", "book_value_per_share"):
        assert ratio_pb(500.0, rec(field=field, value=250.0), price_as_of=PRICE_DATE) == (
            pytest.approx(2.0)
        )


def test_yield_refuses_a_record_that_is_not_dps():
    for field in ("eps", "profit", "net_worth_per_share"):
        with pytest.raises(FundamentalError, match="requires dps"):
            ratio_dividend_yield(rec(field=field), 250.0, price_as_of=PRICE_DATE)


def test_ratio_cannot_present_revenue_divided_by_price_as_pe():
    """The exact nonsense the audit found, asserted as impossible."""
    revenue = rec(field="revenue", value=5000.0)
    with pytest.raises(FundamentalError):
        ratio_pe(500.0, revenue, price_as_of=PRICE_DATE)


# ------------------------------------------------- ratio assistant (F10)
@pytest.fixture()
def store(tmp_path):
    import numpy as np
    import pandas as pd

    from megatool.market_store import MarketStore

    s = MarketStore(tmp_path / "market.duckdb")
    closes = np.linspace(200.0, 250.0, 30)
    s.upsert_bars(
        pd.DataFrame(
            {
                "symbol": ["NABIL"] * 30,
                "trading_date": pd.bdate_range(end="2026-10-12", periods=30),
                "open": closes,
                "high": closes * 1.01,
                "low": closes * 0.99,
                "close": closes,
                "volume": [10_000] * 30,
                "turnover": closes * 10_000,
                "source": ["SYNTHETIC-TEST-FIXTURE"] * 30,
                "retrieved_at": [pd.Timestamp("2026-10-12")] * 30,
                "validation_status": ["valid"] * 30,
            }
        )
    )
    yield s
    s.close()


def test_ratio_report_derives_pe_pb_and_yield_from_stored_inputs(conn, store):
    import_records(
        [
            rec(field="eps", value=25.0),
            rec(field="net_worth_per_share", value=50.0),
            rec(field="dps", value=10.0),
        ],
        conn,
    )
    report = compute_symbol_ratios(conn, store, "nabil")
    assert report["status"] == "ok"
    assert report["price"]["value"] == pytest.approx(250.0)
    assert report["price"]["date"] == "2026-10-12"
    assert report["ratios"]["pe"]["value"] == pytest.approx(10.0)
    assert report["ratios"]["pb"]["value"] == pytest.approx(5.0)
    assert report["ratios"]["dividend_yield_pct"]["value"] == pytest.approx(4.0)
    # reported vs derived is explicit on every figure.
    assert report["ratios"]["pe"]["kind"] == "derived"
    inp = report["ratios"]["pe"]["inputs"][0]
    assert inp["kind"] == "reported" and inp["field"] == "eps"
    assert inp["verification"] == "verified" and inp["period_end"] == "2026-03-31"
    assert {f["field"] for f in report["reported_fields"]} == {
        "eps",
        "net_worth_per_share",
        "dps",
    }


def test_ratio_report_carries_the_refusal_reason_for_unreviewed_inputs(conn, store):
    import_records([rec(field="eps", value=25.0, verification="extracted")], conn)
    report = compute_symbol_ratios(conn, store, "NABIL")
    pe = report["ratios"]["pe"]
    assert pe["value"] is None
    assert "extracted" in pe["unavailable_reason"]
    # Missing inputs state their own reason instead of being omitted.
    assert report["ratios"]["pb"]["value"] is None
    assert (
        "no net_worth_per_share or book_value_per_share record"
        in (report["ratios"]["pb"]["unavailable_reason"])
    )
    assert report["ratios"]["dividend_yield_pct"]["value"] is None


def test_ratio_report_never_invents_a_price(conn, store):
    import_records([rec(field="eps", value=25.0)], conn)
    # The stored symbol is NABIL; GHOST has no bars at all.
    report = compute_symbol_ratios(conn, store, "GHOST")
    assert report["price"]["value"] is None
    assert "no usable stored close for GHOST" in report["price"]["unavailable_reason"]
    for name, r in report["ratios"].items():
        assert r["value"] is None, name
        assert "no usable stored close" in r["unavailable_reason"]


def test_ratio_report_on_unknown_symbol_is_explicit_no_data(conn, store):
    report = compute_symbol_ratios(conn, store, "NEVER")
    assert report["status"] == "no_data"
    assert report["reported_fields"] == []
    assert all(r["value"] is None for r in report["ratios"].values())


# ---------------------------------------------------------------- F10 routes
def test_ratios_and_compare_routes(tmp_path, monkeypatch):
    import numpy as np
    import pandas as pd
    from fastapi.testclient import TestClient

    from megatool.api import create_app
    from megatool.market_store import MarketStore

    store = MarketStore(tmp_path / "market.duckdb")
    closes = np.linspace(200.0, 250.0, 30)
    for sym in ("NABIL", "ADBL"):
        store.upsert_bars(
            pd.DataFrame(
                {
                    "symbol": [sym] * 30,
                    "trading_date": pd.bdate_range(end="2026-10-12", periods=30),
                    "open": closes,
                    "high": closes * 1.01,
                    "low": closes * 0.99,
                    "close": closes,
                    "volume": [10_000] * 30,
                    "turnover": closes * 10_000,
                    "source": ["SYNTHETIC-TEST-FIXTURE"] * 30,
                    "retrieved_at": [pd.Timestamp("2026-10-12")] * 30,
                    "validation_status": ["valid"] * 30,
                }
            )
        )
    from megatool.db import get_conn, init_app_db

    init_app_db()  # isolated app DB (conftest points PATHS at tmp)
    with get_conn() as conn:
        import_records(
            [
                rec(symbol="NABIL", field="eps", value=25.0),
                rec(symbol="NABIL", field="dps", value=10.0),
                rec(symbol="ADBL", field="eps", value=20.0),
            ],
            conn,
        )
    app = create_app(store=store)
    with TestClient(app) as client:
        d = client.get("/api/fundamentals/NABIL/ratios").json()
        assert d["ratios"]["pe"]["value"] == pytest.approx(10.0)
        assert d["ratios"]["dividend_yield_pct"]["value"] == pytest.approx(4.0)
        # /compare must not be swallowed by the /{symbol} parameterised route.
        cmp = client.get("/api/fundamentals/compare", params={"symbols": "NABIL,ADBL"})
        assert cmp.status_code == 200
        reports = cmp.json()["symbols"]
        assert [r["symbol"] for r in reports] == ["NABIL", "ADBL"]
        assert reports[1]["ratios"]["pe"]["value"] == pytest.approx(12.5)
        # An over-long request is rejected rather than silently truncated.
        too_many = ",".join(["X"] * 11)
        assert (
            client.get("/api/fundamentals/compare", params={"symbols": too_many}).status_code == 400
        )
    store.close()


# --------------------------------------------------------------- bulk review
def _extracted(symbol="AAA", field="eps", value=10.0, unit="NPR", source="yonepse/financials.json"):
    return {
        "symbol": symbol,
        "field": field,
        "value": value,
        "unit": unit,
        "period_end": "2026-03-31",
        "period_label": "2026-03-31",
        "source": source,
        "verification": "extracted",
    }


def test_review_source_promotes_only_that_source(conn):
    recs = records_from_rows(
        [
            _extracted("AAA"),
            _extracted("BBB", source="other/source.json"),
        ]
    )
    import_records(recs, conn)
    out = review_source(conn, "yonepse/financials.json")
    assert out == {"source": "yonepse/financials.json", "level": "reviewed", "promoted": 1}
    levels = {
        r["symbol"]: r["verification"]
        for r in query_symbol(conn, "AAA") + query_symbol(conn, "BBB")
    }
    assert levels["AAA"] == "reviewed"
    assert levels["BBB"] == "extracted"  # a different source is untouched


def test_review_source_refuses_a_bad_level_or_empty_source(conn):
    import_records(records_from_rows([_extracted()]), conn)
    with pytest.raises(FundamentalError):
        review_source(conn, "yonepse/financials.json", level="extracted")
    with pytest.raises(FundamentalError):
        review_source(conn, "  ")


def test_review_source_is_idempotent(conn):
    import_records(records_from_rows([_extracted()]), conn)
    assert review_source(conn, "yonepse/financials.json")["promoted"] == 1
    # Already reviewed -> nothing left to promote, and no error.
    assert review_source(conn, "yonepse/financials.json")["promoted"] == 0


# --- Historical P/E lookahead prevention tests ---

def test_eps_available_as_of_returns_latest_before_date(db_path):
    """eps_available_as_of returns the most recent EPS on or before as_of."""
    import sqlite3
    from datetime import date
    from megatool.fundamentals import eps_available_as_of
    from megatool.db import init_app_db
    init_app_db(db_path)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    # Insert test EPS records
    conn.execute("INSERT INTO fundamentals (symbol, field, value, period_end, period_label, unit, source, verification, retrieved_at) VALUES (?, 'eps', ?, ?, ?, 'NPR', 'test', 'reviewed', '2026-01-01')", ("TESTCO", 10.0, "2025-01-15", "Q1"))
    conn.execute("INSERT INTO fundamentals (symbol, field, value, period_end, period_label, unit, source, verification, retrieved_at) VALUES (?, 'eps', ?, ?, ?, 'NPR', 'test', 'reviewed', '2026-01-01')", ("TESTCO", 12.0, "2025-04-15", "Q2"))
    conn.execute("INSERT INTO fundamentals (symbol, field, value, period_end, period_label, unit, source, verification, retrieved_at) VALUES (?, 'eps', ?, ?, ?, 'NPR', 'test', 'reviewed', '2026-01-01')", ("TESTCO", 14.0, "2025-07-15", "Q3"))
    conn.commit()
    # As of 2025-05-01, should return Q2 (April)
    rec = eps_available_as_of(conn, "TESTCO", date(2025, 5, 1))
    assert rec is not None
    assert rec.value == 12.0
    assert rec.period_end == date(2025, 4, 15)
    conn.close()


def test_eps_available_as_of_returns_none_when_no_eps(db_path):
    """eps_available_as_of returns None when no EPS available before as_of."""
    import sqlite3
    from datetime import date
    from megatool.fundamentals import eps_available_as_of
    from megatool.db import init_app_db
    init_app_db(db_path)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("INSERT INTO fundamentals (symbol, field, value, period_end, period_label, unit, source, verification, retrieved_at) VALUES (?, 'eps', ?, ?, ?, 'NPR', 'test', 'reviewed', '2026-01-01')", ("TESTCO2", 10.0, "2025-06-15", "Q1"))
    conn.commit()
    # As of 2025-01-01, no EPS available
    rec = eps_available_as_of(conn, "TESTCO2", date(2025, 1, 1))
    assert rec is None
    conn.close()


def test_historical_pe_lookahead_prevention(db_path):
    """historical_pe does not use future-reported EPS."""
    import sqlite3
    from datetime import date
    from megatool.fundamentals import historical_pe
    from megatool.db import init_app_db
    init_app_db(db_path)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    # Insert EPS records
    conn.execute("INSERT INTO fundamentals (symbol, field, value, period_end, period_label, unit, source, verification, retrieved_at) VALUES (?, 'eps', ?, ?, ?, 'NPR', 'test', 'reviewed', '2026-01-01')", ("TESTCO3", 10.0, "2025-01-15", "Q1 2025"))
    conn.execute("INSERT INTO fundamentals (symbol, field, value, period_end, period_label, unit, source, verification, retrieved_at) VALUES (?, 'eps', ?, ?, ?, 'NPR', 'test', 'reviewed', '2026-01-01')", ("TESTCO3", 12.0, "2025-04-15", "Q2 2025"))
    conn.commit()
    # Historical PE as of 2025-02-01 should use Q1 EPS (10.0), not Q2 (12.0)
    result = historical_pe(conn, "TESTCO3", 500.0, date(2025, 2, 1))
    assert result["pe"] is not None
    assert result["eps_used"] == 10.0
    assert result["eps_period_end"] == "2025-01-15"
    # Historical PE as of 2025-05-01 should use Q2 EPS (12.0)
    result2 = historical_pe(conn, "TESTCO3", 500.0, date(2025, 5, 1))
    assert result2["pe"] is not None
    assert result2["eps_used"] == 12.0
    conn.close()


def test_historical_pe_no_eps_available(db_path):
    """historical_pe returns None when no EPS available."""
    import sqlite3
    from datetime import date
    from megatool.fundamentals import historical_pe
    from megatool.db import init_app_db
    init_app_db(db_path)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("INSERT INTO fundamentals (symbol, field, value, period_end, period_label, unit, source, verification, retrieved_at) VALUES (?, 'eps', ?, ?, ?, 'NPR', 'test', 'reviewed', '2026-01-01')", ("TESTCO4", 10.0, "2025-06-15", "Q1"))
    conn.commit()
    result = historical_pe(conn, "TESTCO4", 500.0, date(2025, 1, 1))
    assert result["pe"] is None
    assert "no EPS record available" in result["reason"]
    conn.close()


def test_historical_pe_negative_eps(db_path):
    """historical_pe refuses negative EPS."""
    import sqlite3
    from datetime import date
    from megatool.fundamentals import historical_pe
    from megatool.db import init_app_db
    init_app_db(db_path)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("INSERT INTO fundamentals (symbol, field, value, period_end, period_label, unit, source, verification, retrieved_at) VALUES (?, 'eps', ?, ?, ?, 'NPR', 'test', 'reviewed', '2026-01-01')", ("TESTCO5", -5.0, "2025-01-15", "Q1"))
    conn.commit()
    result = historical_pe(conn, "TESTCO5", 500.0, date(2025, 2, 1))
    assert result["pe"] is None
    assert "not positive" in result["reason"]
    conn.close()


def test_historical_pe_stale_eps(db_path):
    """historical_pe refuses stale EPS (>400 days)."""
    import sqlite3
    from datetime import date
    from megatool.fundamentals import historical_pe
    from megatool.db import init_app_db
    init_app_db(db_path)
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    conn.execute("INSERT INTO fundamentals (symbol, field, value, period_end, period_label, unit, source, verification, retrieved_at) VALUES (?, 'eps', ?, ?, ?, 'NPR', 'test', 'reviewed', '2026-01-01')", ("TESTCO6", 10.0, "2024-01-15", "Q1"))
    conn.commit()
    result = historical_pe(conn, "TESTCO6", 500.0, date(2026, 1, 1))
    assert result["pe"] is None
    assert "stale" in result["reason"]
    conn.close()
