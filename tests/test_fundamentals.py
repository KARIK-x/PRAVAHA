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
    fundamentals_summary,
    import_records,
    query_symbol,
    ratio_dividend_yield,
    ratio_pb,
    ratio_pe,
    records_from_rows,
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
