"""Floor-sheet import and analysis tests.

Every percentage and HHI below is computed by hand from the fixture.
"""

from __future__ import annotations

import json

import pytest

from megatool.floorsheet import (
    FloorSheetError,
    _to_float,
    import_floorsheet,
    list_sessions,
    parse_floorsheet,
    summary,
    trend,
)

CSV = """Symbol,Buyer,Seller,Quantity,Rate,Amount
NABIL,B1,B2,100,500,50000
NABIL,B1,B3,200,505,101000
NICA,B2,B3,300,250,75000
"""

# Buyers: B1 300, B2 300 -> 50/50 -> HHI 5000
# Sellers: B2 100, B3 500 -> 16.667/83.333 -> HHI 7222.22


# ------------------------------------------------------------------- parsing
def test_parses_a_standard_sheet():
    p = parse_floorsheet(CSV)
    assert p.total_rows == 3
    assert p.skipped == []
    row = p.rows[0]
    assert (row.symbol, row.buyer, row.seller) == ("NABIL", "B1", "B2")
    assert row.quantity == 100 and row.rate == 500.0 and row.amount == 50000.0


def test_accepts_published_column_aliases():
    aliased = """Scrip,Buy,Sell,Qty,Price
NABIL,B1,B2,100,500
"""
    p = parse_floorsheet(aliased)
    assert p.rows[0].symbol == "NABIL"
    assert p.rows[0].quantity == 100
    assert p.rows[0].amount == 50000.0  # computed: no amount column present


def test_missing_columns_are_reported_with_what_was_found():
    with pytest.raises(FloorSheetError) as exc:
        parse_floorsheet("Symbol,Quantity\nNABIL,100\n")
    message = str(exc.value)
    assert "missing required column(s): buyer, seller, rate" in message
    assert "Columns found: Symbol, Quantity" in message


def test_empty_file_rejected():
    with pytest.raises(FloorSheetError, match="empty"):
        parse_floorsheet("   \n  ")


def test_bad_rows_are_skipped_with_line_numbers_not_silently_dropped():
    csv_text = """Symbol,Buyer,Seller,Quantity,Rate,Amount
NABIL,B1,B2,notanumber,500,0
NABIL,B1,B2,0,500,0
NABIL,B1,B2,-10,500,0
NABIL,B1,B2,100,-5,0
,B1,B2,100,500,0
NABIL,B1,,100,500,0
NABIL,B1,B2,100,500,50000
"""
    p = parse_floorsheet(csv_text)
    assert p.total_rows == 7
    assert len(p.rows) == 1
    assert len(p.skipped) == 6
    assert all("line" in s and "reason" in s for s in p.skipped)
    reasons = " ".join(s["reason"] for s in p.skipped)
    assert "quantity 0 <= 0" in reasons
    assert "quantity -10 <= 0" in reasons
    assert "rate -5.0 <= 0" in reasons
    assert "empty symbol" in reasons


def test_amount_mismatch_is_flagged_and_corrected():
    csv_text = """Symbol,Buyer,Seller,Quantity,Rate,Amount
NABIL,B1,B2,100,500,99999
"""
    p = parse_floorsheet(csv_text)
    assert p.rows[0].amount == 50000.0  # quantity x rate wins
    assert any("disagrees with quantity x rate" in w for w in p.warnings)


def test_thousands_separators_and_currency_signs_parse():
    csv_text = 'Symbol,Buyer,Seller,Quantity,Rate,Amount\nNABIL,B1,B2,"1,000","₨500.50",500500\n'
    p = parse_floorsheet(csv_text)
    assert p.rows[0].quantity == 1000
    assert p.rows[0].rate == 500.50


def test_duplicate_rows_inside_one_file_are_deduplicated():
    csv_text = CSV + "NABIL,B1,B2,100,500,50000\n"
    p = parse_floorsheet(csv_text)
    assert len(p.rows) == 3
    assert any("duplicate row" in s["reason"] for s in p.skipped)


def test_symbol_is_uppercased_and_broker_ids_are_trimmed():
    csv_text = "Symbol,Buyer,Seller,Quantity,Rate,Amount\n  nabil ,  b1 , b2 ,100,500,50000\n"
    p = parse_floorsheet(csv_text)
    assert p.rows[0].symbol == "NABIL"
    # broker IDs are stored exactly as trimmed - never guessed at or rewritten
    assert p.rows[0].buyer == "b1" and p.rows[0].seller == "b2"


def test_fractional_quantity_is_reported_not_rounded_away():
    csv_text = "Symbol,Buyer,Seller,Quantity,Rate,Amount\nNABIL,B1,B2,2.5,500,0\n"
    p = parse_floorsheet(csv_text)
    assert p.rows[0].quantity == 2  # round-half-to-even
    assert any("quantity 2.5 is fractional; stored as 2" in w for w in p.warnings)


def test_overflowing_quantity_skips_the_row_instead_of_aborting_the_file():
    csv_text = (
        "Symbol,Buyer,Seller,Quantity,Rate,Amount\n"
        "NABIL,B1,B2,1e400,500,0\n"  # quantity overflows a float -> skip
        "HEX,B1,B2,100,1e400,0\n"  # rate parses to inf -> skip
        "NICA,B1,B2,100,500,50000\n"  # good row still imports
    )
    p = parse_floorsheet(csv_text)
    assert [r.symbol for r in p.rows] == ["NICA"]
    assert [s["line"] for s in p.skipped] == [2, 3]
    reasons = " ".join(s["reason"] for s in p.skipped)
    assert "not a usable price" in reasons


def test_scientific_notation_is_not_silently_mangled():
    # The pre-fix parser stripped the "e" and returned 15 for "1e5" - a
    # plausible-looking wrong quantity that would flow into every total.
    csv_text = "Symbol,Buyer,Seller,Quantity,Rate,Amount\nNABIL,B1,B2,1e5,5e2,0\n"
    p = parse_floorsheet(csv_text)
    assert p.rows[0].quantity == 100_000
    assert p.rows[0].rate == 500.0


def test_to_float_full_input_taxonomy_is_hand_checked():
    """B-36: the parser itself, over every input class it must handle.

    Each expected value below is derived by hand from the literal shown -
    none is read off the implementation. The two previously-reported
    corruptions (``1e5`` -> 15 and ``1e400`` -> 1400) are pinned explicitly.
    """
    import math

    # ordinary integers and decimals parse verbatim
    assert _to_float("123") == 123.0
    assert _to_float("123.45") == 123.45
    assert _to_float("5.5") == 5.5
    assert _to_float("  42  ") == 42.0  # surrounding whitespace is trimmed

    # negatives parse (the sign is meaningful for rates only via <=0 checks)
    assert _to_float("-5") == -5.0
    assert _to_float("-5.25") == -5.25

    # scientific notation survives intact - the two reported regressions:
    assert _to_float("1e5") == 100_000.0  # was 15 before B-36
    assert _to_float("5e2") == 500.0
    assert _to_float("1e308") == 1e308  # finite, still a real magnitude
    # 1e400 overflows to +inf; the parser must NOT return a finite 1400.
    # The caller (parse_floorsheet) rejects non-finite rates/quantities.
    assert math.isinf(_to_float("1e400")) and _to_float("1e400") > 0
    assert math.isinf(_to_float("3e308"))  # a smaller overflow also -> inf

    # thousands separators and currency signs (the verbatim path rejects
    # these, so the fallback strips them WITHOUT corrupting the digits)
    assert _to_float("1,000") == 1000.0
    assert _to_float("Rs. 1,000") == 1000.0  # was 0.1 before the fix
    assert _to_float("₨500.50") == 500.5

    # NaN and infinities are returned as-is (never coerced to a finite
    # number); the caller's isfinite() guard is what rejects them.
    assert math.isnan(_to_float("nan"))
    assert math.isnan(_to_float("NaN"))
    assert math.isinf(_to_float("inf")) and _to_float("inf") > 0
    assert math.isinf(_to_float("-inf")) and _to_float("-inf") < 0

    # malformed / empty strings raise so the row is skipped, never zero:
    for bad in ("", "   ", "abc", "1.5.2", ".", "-", "--", "1,2,3.4.5"):
        with pytest.raises(ValueError, match="not a number"):
            _to_float(bad)

    # B-40: scientific notation that ALSO carries a currency marker must be
    # rejected, never stripped to a plausible wrong number ("1e5 USD" was
    # becoming 15.0 via the separator-stripping fallback).
    for bad in ("1e5 USD", "Rs 1e5", "1,000e2", "5e2 NPR"):
        with pytest.raises(ValueError, match="not a number"):
            _to_float(bad)


def test_currency_plus_scientific_notation_skips_the_row_honestly():
    """B-40 end-to-end: the corrupt-value row is skipped with a reason."""
    csv_text = (
        "Symbol,Buyer,Seller,Quantity,Rate,Amount\n"
        "NABIL,B1,B2,100,Rs 1e5,0\n"  # must NOT become rate 15
        "NICA,B2,B3,100,500,50000\n"  # good row still imports
    )
    p = parse_floorsheet(csv_text)
    assert [r.symbol for r in p.rows] == ["NICA"]
    assert len(p.skipped) == 1
    assert "not a number" in p.skipped[0]["reason"]
    assert p.rows[0].amount == 50_000.0  # 100 x 500, the good row is intact


def test_semicolon_delimiter_is_detected():
    csv_text = "Symbol;Buyer;Seller;Quantity;Rate;Amount\nNABIL;B1;B2;100;500;50000\n"
    assert parse_floorsheet(csv_text).rows[0].symbol == "NABIL"


def test_row_date_column_is_taken_when_present():
    csv_text = """Date,Symbol,Buyer,Seller,Quantity,Rate,Amount
2026-10-09,NABIL,B1,B2,100,500,50000
"""
    p = parse_floorsheet(csv_text)
    assert p.rows[0].date == "2026-10-09"


# ------------------------------------------------------------------ importing
def test_import_stores_every_row(db_path):
    out = import_floorsheet(CSV, "2026-10-09", source="test sheet", db_path=db_path)
    assert out["already_imported"] is False
    assert out["rows_imported"] == 3
    assert out["rows_skipped"] == 0
    assert out["stored_trades"] == 3


def test_reimporting_the_same_file_adds_nothing(db_path):
    import_floorsheet(CSV, "2026-10-09", db_path=db_path)
    second = import_floorsheet(CSV, "2026-10-09", db_path=db_path)
    assert second["already_imported"] is True
    assert second["rows_imported"] == 0
    assert second["stored_trades"] == 3
    assert "already imported" in second["note"]
    assert summary(db_path=db_path)["totals"]["trades"] == 3


def test_the_same_trade_in_a_different_file_is_not_double_counted(db_path):
    import_floorsheet(CSV, "2026-10-09", db_path=db_path)
    # A re-published copy: different bytes (so a different content hash) but
    # the same three prints.
    republished = CSV.replace("\n", "  \n")
    out = import_floorsheet(republished, "2026-10-09", db_path=db_path)
    assert out["already_imported"] is False
    assert out["rows_imported"] == 0  # every row was already stored
    assert summary(db_path=db_path)["totals"]["trades"] == 3


def test_a_second_session_is_added_not_merged(db_path):
    import_floorsheet(CSV, "2026-10-09", db_path=db_path)
    other = "Symbol,Buyer,Seller,Quantity,Rate,Amount\nNICA,B9,B8,50,250,12500\n"
    import_floorsheet(other, "2026-10-08", db_path=db_path)
    s = summary(db_path=db_path)
    assert s["totals"]["sessions"] == 2
    assert s["totals"]["trades"] == 4


def test_skipped_rows_are_returned_to_the_caller(db_path):
    csv_text = "Symbol,Buyer,Seller,Quantity,Rate,Amount\nNABIL,B1,B2,oops,500,0\n"
    out = import_floorsheet(csv_text, "2026-10-09", db_path=db_path)
    assert out["rows_imported"] == 0
    assert out["skipped"][0]["line"] == 2
    assert "not a number" in out["skipped"][0]["reason"]


# ------------------------------------------------------------------- summary
def test_summary_ranks_and_shares(db_path):
    import_floorsheet(CSV, "2026-10-09", db_path=db_path)
    s = summary(db_path=db_path)

    assert s["totals"] == {
        "trades": 3,
        "symbols": 2,
        "sessions": 1,
        "quantity": 600,
        "amount": 226000.0,
    }

    buyers = {row["buyer"]: row for row in s["top_buyers"]}
    assert set(buyers) == {"B1", "B2"}
    assert buyers["B1"]["quantity"] == 300
    assert buyers["B1"]["share_of_quantity_pct"] == pytest.approx(50.0)
    assert buyers["B1"]["amount"] == pytest.approx(151000.0)
    assert buyers["B1"]["share_of_amount_pct"] == pytest.approx(151000 / 226000 * 100)

    sellers = {row["seller"]: row for row in s["top_sellers"]}
    assert sellers["B3"]["quantity"] == 500
    assert sellers["B3"]["share_of_quantity_pct"] == pytest.approx(500 / 600 * 100)

    symbols = {row["symbol"]: row for row in s["top_symbols"]}
    assert symbols["NABIL"]["quantity"] == 300
    assert symbols["NABIL"]["prints"] == 2
    assert symbols["NABIL"]["distinct_buyers"] == 1
    assert symbols["NABIL"]["distinct_sellers"] == 2

    pairs = s["top_counterparties"]
    assert pairs[0]["buyer"] == "B1" and pairs[0]["seller"] == "B3"
    assert pairs[0]["amount"] == 101000.0


def test_summary_concentration_is_hand_computable(db_path):
    import_floorsheet(CSV, "2026-10-09", db_path=db_path)
    c = summary(db_path=db_path)["concentration"]
    assert c["unique_buyers"] == 2
    assert c["unique_sellers"] == 2
    assert c["buyer_hhi"] == pytest.approx(50.0**2 + 50.0**2)  # 5000
    assert c["seller_hhi"] == pytest.approx(
        (100 / 600 * 100) ** 2 + (500 / 600 * 100) ** 2, abs=0.01
    )
    assert "not beneficial owners" in c["interpretation"]


def test_summary_warns_when_concentration_is_high(db_path):
    import_floorsheet(CSV, "2026-10-09", db_path=db_path)
    warnings = summary(db_path=db_path)["warnings"]
    assert any("concentration is high" in w for w in warnings)
    assert any("NOT evidence of accumulation" in w for w in warnings)


def test_summary_of_an_empty_database_says_so(db_path):
    s = summary(db_path=db_path)
    assert s["totals"]["trades"] == 0
    assert any("No floor sheet has been imported" in w for w in s["warnings"])
    assert s["top_buyers"] == [] and s["top_symbols"] == []


def test_summary_warns_when_sessions_are_mixed(db_path):
    import_floorsheet(CSV, "2026-10-09", db_path=db_path)
    other = "Symbol,Buyer,Seller,Quantity,Rate,Amount\nNICA,B9,B8,50,250,12500\n"
    import_floorsheet(other, "2026-10-08", db_path=db_path)
    warnings = summary(db_path=db_path)["warnings"]
    assert any("spans 2 sessions" in w for w in warnings)
    # Filtering to one session removes the warning and the mixing.
    one = summary(db_path=db_path, traded_at="2026-10-09")
    assert one["totals"]["trades"] == 3
    assert not any("spans" in w for w in one["warnings"])


def test_summary_filters_by_symbol(db_path):
    import_floorsheet(CSV, "2026-10-09", db_path=db_path)
    s = summary(db_path=db_path, symbol="nica")
    assert s["totals"]["trades"] == 1
    assert s["totals"]["quantity"] == 300
    assert s["top_sellers"][0]["seller"] == "B3"


def test_summary_limits_are_present_and_honest(db_path):
    import_floorsheet(CSV, "2026-10-09", db_path=db_path)
    joined = " ".join(summary(db_path=db_path)["limits"]).lower()
    assert "not why" in joined
    assert "beneficial owner" in joined
    assert "unadjusted" in joined
    assert "investment advice" in joined


def test_summary_is_json_serialisable(db_path):
    import_floorsheet(CSV, "2026-10-09", db_path=db_path)
    assert json.loads(json.dumps(summary(db_path=db_path)))["totals"]["trades"] == 3


def test_list_sessions(db_path):
    import_floorsheet(CSV, "2026-10-09", db_path=db_path)
    other = "Symbol,Buyer,Seller,Quantity,Rate,Amount\nNICA,B9,B8,50,250,12500\n"
    import_floorsheet(other, "2026-10-08", db_path=db_path)
    sessions = list_sessions(db_path=db_path)
    assert [s["traded_at"] for s in sessions] == ["2026-10-09", "2026-10-08"]
    assert sessions[0]["prints"] == 3
    assert sessions[1]["symbols"] == 1


def test_list_sessions_empty(db_path):
    assert list_sessions(db_path=db_path) == []


# ------------------------------------------------- multi-session trend (F3)
CSV_A = "Symbol,Buyer,Seller,Quantity,Rate,Amount\nNABIL,B1,B2,100,500,50000\nNICA,B1,B3,300,250,75000\n"
# Session A (2026-10-08): 2 prints, qty 400, turnover 125,000, buyers {B1},
# sellers {B2, B3}. Session B (CSV above): 3 prints, qty 600, turnover
# 226,000, buyers {B1, B2}, sellers {B2, B3}.
# Broker nets over both sessions (hand-computed):
#   B1 bought 700, sold 0   -> +700 net_buyer
#   B2 bought 300, sold 200 -> +100 net_buyer
#   B3 bought 0, sold 800   -> -800 net_seller (sums to 0)


def _two_sessions(db_path):
    import_floorsheet(CSV_A, "2026-10-08", source="fixture A", db_path=db_path)
    import_floorsheet(CSV, "2026-10-09", source="fixture B", db_path=db_path)


def test_trend_needs_two_sessions_and_says_so(db_path):
    import_floorsheet(CSV, "2026-10-09", db_path=db_path)
    out = trend(db_path=db_path)
    assert out["status"] == "insufficient_sessions"
    assert out["sessions_found"] == 1
    assert out["broker_net"] == []
    assert "at least 2" in out["reason"]
    assert "not that nothing traded" in out["note"]


def test_trend_with_nothing_imported_is_explicit_not_a_flat_trend(db_path):
    out = trend(db_path=db_path)
    assert out["status"] == "insufficient_sessions"
    assert out["sessions_found"] == 0
    assert out["activity"] == []


def test_trend_reports_observed_activity_and_hand_computed_flow(db_path):
    _two_sessions(db_path)
    out = trend(db_path=db_path)
    assert out["status"] == "ok"
    # Chronological (oldest first), observed prints.
    assert [s["traded_at"] for s in out["activity"]] == ["2026-10-08", "2026-10-09"]
    a, b = out["activity"]
    assert (a["prints"], a["quantity"], a["turnover"], a["buyers"], a["sellers"]) == (
        2,
        400,
        125000.0,
        1,
        2,
    )
    assert (b["prints"], b["quantity"], b["turnover"], b["buyers"], b["sellers"]) == (
        3,
        600,
        226000.0,
        2,
        2,
    )
    # Direction: 226,000 / median(125,000) = 1.81 > 1.2 -> rising, basis stated.
    trend_part = out["activity_trend"]
    assert trend_part["direction"] == "rising"
    assert trend_part["kind"] == "observed_activity"
    assert "ratio 1.81" in trend_part["basis"]
    assert "125,000.00" in trend_part["basis"]
    # Per-broker flow, hand-computed above, ordered by |net|.
    nets = [(f["broker"], f["net"], f["flow"]) for f in out["broker_net"]]
    assert nets == [("B3", -800, "net_seller"), ("B1", 700, "net_buyer"), ("B2", 100, "net_buyer")]
    assert out["integrity"] is None  # whole-sheet scope: no per-symbol invariant
    joined = " ".join(out["limits"])
    assert "inferences" in joined and "NOT evidence of accumulation" in joined
    assert "beneficial owner" in joined


def test_trend_symbol_scope_nets_must_sum_to_zero(db_path):
    _two_sessions(db_path)
    out = trend(db_path=db_path, symbol="nabil")
    assert out["status"] == "ok" and out["symbol"] == "NABIL"
    assert [s["traded_at"] for s in out["activity"]] == ["2026-10-08", "2026-10-09"]
    a, b = out["activity"]
    assert (a["prints"], a["turnover"]) == (1, 50000.0)
    assert (b["prints"], b["turnover"]) == (2, 151000.0)
    assert out["activity_trend"]["direction"] == "rising"
    nets = [(f["broker"], f["net"]) for f in out["broker_net"]]
    assert nets == [("B1", 400), ("B2", -200), ("B3", -200)]
    assert out["integrity"] == {"net_sums_to_zero": True}


def test_trend_empty_symbol_scope_is_insufficient_not_an_error(db_path):
    _two_sessions(db_path)
    out = trend(db_path=db_path, symbol="NONE")
    assert out["status"] == "insufficient_sessions"
    assert out["sessions_found"] == 0
    assert out["symbol"] == "NONE"


# ---------------------------------------------------------------- F3 route
def test_trend_route_end_to_end(tmp_path):
    from fastapi.testclient import TestClient

    from megatool.api import create_app
    from megatool.market_store import MarketStore

    # Imports go to the isolated PATHS.app_db the route reads.
    _two_sessions(db_path=None)
    store = MarketStore(tmp_path / "market.duckdb")
    app = create_app(store=store)
    with TestClient(app) as client:
        d = client.get("/api/floorsheet/trend", params={"symbol": "NABIL"}).json()
        assert d["status"] == "ok"
        assert d["integrity"] == {"net_sums_to_zero": True}
        assert d["broker_net"][0]["broker"] == "B1"
        # A one-session window can never show a trend -> rejected up front
        # (422: FastAPI's Query validation status).
        assert client.get("/api/floorsheet/trend", params={"sessions": 1}).status_code == 422
        # Empty scope still 200s with an honest insufficient status.
        fresh = trend(db_path=tmp_path / "fresh.sqlite")
        assert fresh["status"] == "insufficient_sessions"
    store.close()
