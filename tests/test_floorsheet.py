"""Floor-sheet import and analysis tests.

Every percentage and HHI below is computed by hand from the fixture.
"""

from __future__ import annotations

import json

import pytest

from megatool.floorsheet import (
    FloorSheetError,
    import_floorsheet,
    list_sessions,
    parse_floorsheet,
    summary,
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
