"""Tests for the transcription helpers and the v5 provenance columns.

Every expected value here is worked out in the comment above it by ordinary
arithmetic, independently of the code under test, so a change to the parser
cannot silently redefine what "correct" means.
"""

from __future__ import annotations

import json

import pytest

from megatool.db import SCHEMA_VERSION, get_conn, init_app_db
from megatool.written_pdf import (
    ExtractedRecord,
    PdfValidationError,
    ReconciliationStatus,
    RecordType,
    ReviewStatus,
    VerificationStatus,
    append_correction,
    import_records,
    read_vision_page,
    set_review_status,
    set_verification_status,
    usable_records,
)
from megatool.written_transcribe import (
    ALL_VISUALLY_READ,
    VERIFIED_SETTLEMENT_DETAILS,
    VERIFIED_SETTLEMENTS,
    VISUALLY_INSPECTED_PAGES,
    VISUALLY_READ_PAGE_19,
    VISUALLY_READ_PAGE_23,
    VISUALLY_READ_PAGE_28,
    VISUALLY_READ_PAGE_30,
    VISUALLY_READ_PAGES,
    detect_settlement_label,
    extract_settlements,
    parse_money,
    parse_trade_line,
)


# ====================================================================== money
@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        # Plain, correctly punctuated.
        ("52,445.75", 52445.75),
        ("111,993.22", 111993.22),
        ("1,234,567", 1234567.0),
        # Vision reads a decimal point as a comma, a dash or a bullet.
        ("38855,07", 38855.07),  # single separator, 5-digit head
        ("71535-52", 71535.52),
        ("881•06", 881.06),
        ("1275•58", 1275.58),
        # Mixed separators, thousands then decimal.
        ("168,147-83", 168147.83),
        ("226359. 28", 226359.28),  # stray space after the point
        # The real page-21 figures.
        ("77609.76", 77609.76),
        ("12059,43", 12059.43),
        ("65550.33", 65550.33),
        # Parentheses mean negative.
        ("(76,847.01)", -76847.01),
        # Integers.
        ("285", 285.0),
        # A COMMA with a three-digit tail is thousands grouping — the form the
        # notebook actually writes. All 60 distinct tokens of that shape across
        # the 52 Vision pages parse to a plausible amount.
        ("117,142", 117142.0),
        # A DOT with a three-digit tail is refused, not read as thousands.
        # This case used to assert 3690.0, on the reasoning that 3.690 "is not
        # a price that exists on NEPSE". Looking at the page instead: on page 2
        # "# 3.690" sits in a ratios block beside "5,59 cr.", "14.21" and
        # "5.020r", where it reads 3.690. And of the 79 distinct dot+3digit
        # tokens in the corpus, 44 would have parsed to under 1000 under the old
        # rule — a thousands grouping can never be that short — so that rule was
        # provably wrong at least 44 times. Refusing costs one review; a wrong
        # reading multiplies a figure by 1000.
        ("3.690", None),
    ],
)
def test_parse_money_reads_the_forms_vision_actually_produces(raw, expected):
    assert parse_money(raw) == expected


@pytest.mark.parametrize("raw", ["", "Rs", "abc", "55,642.285", "12,34.5678"])
def test_parse_money_refuses_to_guess(raw):
    """An ambiguous token must come back unread, never normalised.

    "55,642.285" mixes a comma and a dot with a three-digit tail, so there is
    no way to tell a decimal from a mis-grouped integer. Guessing either way is
    how a settlement figure gets silently rewritten, so it returns None and
    lands in the review queue.
    """
    assert parse_money(raw) is None


def test_parse_money_never_returns_zero_for_junk():
    assert parse_money("•••") is None
    assert parse_money("-") is None


# ====================================================================== trades
def test_trade_line_parses_and_reconciles_by_hand():
    # 10 x 1,256.00 = 12,560 — a real line from page 22 (clean form; Vision
    # returned the price there as "/256.00", dropping the leading 1).
    t = parse_trade_line("GFCL → 10x 1256.00 → 12,560", page=22, line_no=7)
    assert t is not None
    assert t.symbol == "GFCL"
    assert t.quantity == 10
    assert t.price == 1256.00
    assert t.amount == 12560.0
    assert t.computed_amount == 12560.00
    assert t.reconciliation is ReconciliationStatus.RECONCILED
    assert t.implied_price == 1256.00


def test_trade_line_flags_a_misread_price_without_rewriting_it():
    # Page 24: "HIDELP -> 350 x 159.6 0 -> 55650".
    # 350 x 159.60 = 55,860, but the written amount is 55,650, so the row is
    # flagged. 55,650 / 350 = 159.00 exactly, which is the hypothesis a human
    # confirms against the page — it is NOT substituted in.
    t = parse_trade_line("HIDELP → 350x 159.6 0→ 55650", page=24, line_no=3)
    assert t is not None
    assert t.quantity == 350
    assert t.computed_amount == 55860.00
    assert t.amount == 55650.0
    assert t.reconciliation is ReconciliationStatus.DISCREPANCY
    assert t.implied_price == 159.00
    # The parsed price is untouched: the flag is a question, not an edit.
    assert t.price == 159.60


def test_parenthesised_quantity_marks_a_sell():
    t = parse_trade_line("MANDU → (60)x 1275.58 → 76,534.80", page=20)
    assert t is not None
    assert t.side == "sell"
    # 60 x 1,275.58 = 76,534.80 exactly.
    assert t.computed_amount == 76534.80


def test_trade_line_without_an_amount_is_unreconcilable_not_wrong():
    # Vision often drops the amount column; that is missing data, not a defect.
    t = parse_trade_line("CITY → 20x 1050.0 →", page=20)
    assert t is not None
    assert t.amount is None
    assert t.reconciliation is ReconciliationStatus.UNRECONCILABLE
    assert t.implied_price is None


def test_prose_never_becomes_a_trade():
    assert parse_trade_line("Inspiring Young Minds") is None
    assert parse_trade_line("Date:") is None
    assert parse_trade_line("Net Payable = 65,550.33") is None


def test_a_date_line_is_not_a_trade():
    # "22 sep -> 54157.24 - Buy" has no quantity, so it must not parse.
    assert parse_trade_line("22 sep → 54157.24 - Buy", page=21) is None


# ======================================================= verified settlements
def test_every_verified_settlement_balances_by_hand():
    """Plain subtraction, done here rather than by calling the module."""
    expected = [
        (77_609.76, 12_059.43, 65_550.33),
        (106_186.34, 88_169.68, 18_016.66),
        (189_763.58, 157_168.39, 32_595.19),
        (54_157.24, 45_035.39, 9_121.85),
    ]
    assert expected == VERIFIED_SETTLEMENTS
    for buy, sell, net in expected:
        assert round(buy - sell, 2) == net


def test_verified_settlements_are_exactly_the_four_on_page_21():
    """Pinned so 'verified' cannot quietly widen without changing a test."""
    assert len(VERIFIED_SETTLEMENTS) == 4
    assert {d["page"] for d in VERIFIED_SETTLEMENT_DETAILS} == {21}
    assert {d["label"] for d in VERIFIED_SETTLEMENT_DETAILS} == {"9A", "9B", "9C", "9D"}
    for d in VERIFIED_SETTLEMENT_DETAILS:
        assert d["verification_status"] == VerificationStatus.VERIFIED.value
        assert "visual read of" in d["evidence"]


def test_the_withdrawn_9a_figure_is_not_lurking_in_the_verified_set():
    """B-02: 186,129.76 was fabricated to make an equation balance."""
    withdrawn = 186_129.76
    for buy, sell, _net in VERIFIED_SETTLEMENTS:
        assert buy != withdrawn
        assert sell != 120_579.43


def test_settlement_label_detection_tolerates_the_observed_ocr():
    # A letter Vision actually spelled is trusted as-is.
    assert detect_settlement_label("Settlement 9A") == "9A"
    # "g" is a misread 9, but the letter must still be a real A–H.
    assert detect_settlement_label("Seltlement gE") == "9E"
    assert detect_settlement_label("Inspiring Young Minds") is None
    # "settlement 9Đ" used to assert "9D". Reading page 21 by eye, that line
    # heads the FIRST block of the page, which is 9A — the figures under it are
    # 77,609.76 / 12,059.43 / 65,550.33, the visually verified 9A. Mapping Đ to
    # D renamed it 9D and collided with the real 9D at the foot of the page, so
    # an unread letter now comes back None instead of being guessed.
    assert detect_settlement_label("settlement 9Đ") is None
    # A digit where a letter belongs is also unread, not mapped (91 is 9C).
    assert detect_settlement_label("settlement 91") is None


def test_unread_labels_are_assigned_by_position_and_marked_as_such():
    """Position recovers the label; it must never pass as a transcribed one."""
    text = (
        "settlement 9Đ\n11 sep - 77609.76 By\n"
        "Settlement 9 B\n16 ger - 106186.34 - Виц\n"
        "settlement\n91\n18 бер - 189763,58 - Виц\n"
        "Settlement\n22 бер → 54157.24 - Виу\n"
    )
    blocks = extract_settlements(21, text)
    assert [b.label for b in blocks] == ["9A", "9B", "9C", "9D"]
    # The verbatim reading is preserved next to the assigned label.
    assert [b.label_raw for b in blocks] == ["9Đ", "9 B", "91", ""]
    # Only the one Vision spelled out claims to be transcribed.
    assert [b.label_source for b in blocks] == [
        "position",
        "ocr",
        "position",
        "position",
    ]
    assert blocks[1].as_dict()["label_raw"] == "9 B"


# ---------------------------------------------------- reading real OCR lines
# The four tests below quote page text exactly as Apple Vision returned it.
# They check what the reader does with the page's own words — nothing here
# asserts that an unverified figure is *true*, only that it is read, refused,
# or kept as the page and the rules say.


def test_page21_first_settlement_reads_despite_its_unreadable_header():
    """Page 21's first block (9A, the visually verified settlement)."""
    text = (
        "settlement 9Đ\n"
        "11 sep - 77609.76 By\n"
        "I sep - 12059,43 sen\n"
        "Paid 65550.33\n"
        "Not Payable → 65550.337\n"
        "on 12th sep\n"
        "27\n"
        "28\n"
    )
    [b] = extract_settlements(21, text)

    # Without the lookarounds on the day pattern, "76 By" reads as a day beside
    # a month and 77609.76 loses its tail.
    assert b.buy == [77609.76]
    assert b.sell == [12059.43]
    # Three decimals: unread rather than rounded to 65550.33 or expanded to
    # 65550337. The verbatim line is still kept as evidence.
    assert b.net is None
    assert b.net_raw == "Not Payable → 65550.337"
    # So the notebook's own "Paid" note becomes the reference.
    assert b.paid == 65550.33
    assert b.reference == 65550.33
    # 77,609.76 − 12,059.43 = 65,550.33, checked against that note.
    assert b.reconciliation.value == "reconciled"
    # 27 and 28 are a day and a page number, not settlement figures.
    assert 27.0 not in b.buy + b.sell + b.unplaced
    assert 28.0 not in b.buy + b.sell + b.unplaced
    # Nothing on this block spelled a series digit, so none is invented.
    assert (b.label, b.label_raw, b.label_source) == ("?A", "9Đ", "position")


def test_a_net_split_across_a_colon_is_refused_rather_than_joined():
    """Page 21's third block: "32595: 19" is 32595.19, and joining is worse."""
    text = (
        "settlement\n"
        "91\n"
        "18 бер - 189763,58 - Виц\n"
        "18 sep- 157 168.39 - 50\n"
        "Paid 32595.19\n"
        "Net Payable 32595: 19)\n"
    )
    [b] = extract_settlements(21, text)

    # Joining the colon-separated tokens gives 3259519 — a thousandfold error.
    assert b.net is None
    assert b.net_raw == "Net Payable 32595: 19)"
    assert b.paid == 32595.19
    assert b.reference == 32595.19
    # "157 168.39" is one figure split at its thousands boundary, so the reader
    # must see 157168.39 — not 168.39, which is what survives if the day
    # pattern or a naive tokenizer gets there first.
    assert 157168.39 in b.buy + b.sell + b.unplaced
    assert 168.39 not in b.buy + b.sell + b.unplaced


def test_figures_whose_column_marker_is_unread_are_kept_not_dropped():
    """Page 21's fourth block: OCR reads no buy/sell marker, so no column is
    claimed — but the figures are still recorded for the review queue."""
    text = (
        "Settlement\n"
        "72 бер → 54157.24 - Виу\n"
        "22 ер = 45035.39 - 104\n"
        "net Payable *\n"
        "1912185\n"
        "paid 9121•85\n"
        "on 25th sep\n"
    )
    [b] = extract_settlements(21, text)

    assert b.buy == [] and b.sell == []  # no column invented
    assert 54157.24 in b.unplaced
    assert 45035.39 in b.unplaced
    assert b.paid == 9121.85
    assert b.reference == 9121.85
    # Without columns there is nothing to check, so it is not called reconciled.
    assert b.reconciliation.value == "unreconcilable"


def test_the_net_is_taken_after_the_last_equals_not_from_the_front():
    """The first number on a net equation is a column total, not the net."""
    text = (
        "Setlement\n"
        "8C\n"
        "Buy\n"
        "52,445.75\n"
        "Sol\n"
        "154824.76\n"
        "Net receivate = 226359.28-168,4783 = 158, 211.43)\n"
    )
    [b] = extract_settlements(19, text)

    # Reading the front of the line would record 226359.28 — a column total
    # already present elsewhere on the page — as the net.
    assert b.net == 158211.43
    assert b.net != 226359.28
    # This is the OCR's own reading of an unverified page, kept as written.
    assert b.net_raw.endswith("= 158, 211.43)")


# ------------------------------------------------- page 19 read by eye
# Page 19 was read off raw_pages/page_19.png on 2026-10-12. Two of its three
# settlements balance exactly; one does not, and the notebook itself is the
# source of that.


def test_page19_settlements_read_by_eye():
    by_label = {d["label"]: d for d in VISUALLY_READ_PAGE_19}
    assert set(by_label) == {"8C", "8D", "8E"}
    assert all(d["page"] == 19 for d in VISUALLY_READ_PAGE_19)

    # 8D and 8E add up in every direction and agree with their own Paid notes.
    for label, buy, sell, net in [
        ("8D", 111_993.22, 111_175.43, 817.79),
        ("8E", 217_495.28, 148_478.38, 69_016.90),
    ]:
        d = by_label[label]
        assert round(sum(d["buy_components"]), 2) == d["buy_total"] == buy
        assert round(sum(d["sell_components"]), 2) == d["sell_total"] == sell
        assert round(d["buy_total"] - d["sell_total"], 2) == d["net"] == net
        assert d["settled"] == net
        assert d["source_discrepancies"] == []


def test_page19_8c_shortfall_is_recorded_as_a_source_fact_not_repaired():
    """The sell column is 1.00 short on the page itself; nothing is adjusted."""
    c = next(d for d in VISUALLY_READ_PAGE_19 if d["label"] == "8C")

    component_sum = round(sum(c["sell_components"]), 2)
    assert component_sum == 226_360.28
    assert c["sell_total"] == 226_359.28
    assert round(component_sum - c["sell_total"], 2) == 1.00
    assert c["components_ok"] == {"buy": True, "sell": False}
    # The notebook takes its net from the written total, and that is exact.
    assert c["net_matches_written_totals"] is True
    assert round(c["sell_total"] - c["buy_total"], 2) == c["net"] == 58_211.45
    # Both source defects are stated rather than smoothed over.
    assert any("1.00" in s for s in c["source_discrepancies"])
    assert any("8.03" in s for s in c["source_discrepancies"])
    # The figures as written are untouched.
    assert c["sell_components"] == [154_824.76, 71_535.52]
    assert c["settled"] == 58_203.42


def test_page19_8e_keeps_the_authors_superseded_reading():
    """8E carries a strike-through correction; both readings survive."""
    e = next(d for d in VISUALLY_READ_PAGE_19 if d["label"] == "8E")

    superseded = {s["field"]: s for s in e["superseded_readings"]}
    assert superseded["sell_total"]["original_reading"] == 148_503.38
    assert superseded["sell_total"]["corrected_value"] == e["sell_total"] == 148_478.38
    assert superseded["sell_components"]["original_reading"] == 73_872.10
    # A reason is recorded for every superseded reading, and the corrected
    # figures are the ones the page's own arithmetic supports.
    assert all(s["reason"] for s in e["superseded_readings"])
    assert round(sum(e["sell_components"]), 2) == e["sell_total"]


def test_the_visually_read_set_grows_without_losing_page_membership():
    """Page 21's four are a subset; page membership is carried per record."""
    assert len(VERIFIED_SETTLEMENT_DETAILS) == 4
    assert len(VISUALLY_READ_PAGE_19) == 3
    assert len(VISUALLY_READ_PAGE_23) == 2
    assert len(VISUALLY_READ_PAGE_28) == 3
    assert len(VISUALLY_READ_PAGE_30) == 3
    assert len(ALL_VISUALLY_READ) == 15
    assert sorted(VISUALLY_READ_PAGES) == [19, 21, 23, 28, 30]
    assert all(d["verification_status"] == "verified" for d in ALL_VISUALLY_READ)
    # Every record still names the page it came from.
    assert all("page" in d for d in ALL_VISUALLY_READ)


def test_every_visually_read_record_shapes_itself_the_same_way():
    """One shape across pages, so no consumer has to branch on the page.

    Written after page 21's records (``net_payable``/``paid``) and pages 19 and
    23's (``net``/``settled``) disagreed, and settlements.csv briefly carried an
    empty ``net`` column for all four page-21 rows.
    """
    shapes = {tuple(sorted(d)) for d in ALL_VISUALLY_READ}
    assert len(shapes) == 1, f"record shapes differ: {len(shapes)} variants"

    required = {
        "label",
        "page",
        "dates",
        "buy_components",
        "buy_total",
        "buy_total_is_written",
        "sell_components",
        "sell_total",
        "net",
        "direction",
        "settled",
        "settled_label",
        "settled_on",
        "components_ok",
        "net_matches_written_totals",
        "source_discrepancies",
        "superseded_readings",
        "ocr_notes",
        "verification_status",
        "evidence",
    }
    assert shapes == {tuple(sorted(required))}

    # The direction field is what makes |buy - sell| the right balance check.
    assert {d["direction"] for d in ALL_VISUALLY_READ} == {"payable", "receivable"}
    assert all(
        d["direction"] == "receivable"
        for d in ALL_VISUALLY_READ
        if d["page"] == 19 and d["label"] == "8C"
    )


def test_inspecting_a_page_is_not_the_same_as_transcribing_it():
    """Page 20 was opened and identified, but no record came off it.

    Kept separate because the manifest has to say "inspected, nothing
    transcribed" rather than silently counting page 20 among the pages whose
    settlements were read.
    """
    assert sorted(VISUALLY_INSPECTED_PAGES) == [19, 20, 21, 23, 28, 30]
    # Anything read must also have been looked at.
    assert VISUALLY_READ_PAGES <= VISUALLY_INSPECTED_PAGES
    # Page 20 is the gap between the two sets.
    assert sorted(VISUALLY_INSPECTED_PAGES - VISUALLY_READ_PAGES) == [20]
    assert not any(d["page"] == 20 for d in ALL_VISUALLY_READ)


def test_page23_closes_exactly_and_explains_the_refused_ocr_token():
    by_label = {d["label"]: d for d in VISUALLY_READ_PAGE_23}
    assert set(by_label) == {"9E", "9F"}

    e, f = by_label["9E"], by_label["9F"]
    for d in (e, f):
        assert round(sum(d["buy_components"]), 2) == d["buy_total"]
        assert round(sum(d["sell_components"]), 2) == d["sell_total"]
        assert round(d["buy_total"] - d["sell_total"], 2) == d["net"] == d["settled"]
        assert d["source_discrepancies"] == []

    # 9E's buy total is a sum, not something the notebook writes: the record
    # says so instead of presenting it as a transcribed figure.
    assert e["buy_total_is_written"] is False
    assert round(sum(e["buy_components"]), 2) == 121_894.12
    assert f["buy_total_is_written"] is True

    # The ambiguous OCR token was refused, and the page supplies the real value.
    assert parse_money("55, 642.285") is None
    assert parse_money("55,642.28") == 55_642.28
    assert f["sell_total"] == 55_642.28
    assert any("refused" in n for n in f["ocr_notes"])


def test_page30_records_say_what_they_did_not_read_instead_of_guessing():
    """An un-resolvable annotation becomes ``None``, never a plausible number.

    The red Received/Paid clouds on 12D and 12F are small cursive. Choosing a
    figure because it would fit the net is exactly the failure mode that
    produced the withdrawn 186,129.76, so the fields stay ``None`` and the
    reason goes in ``ocr_notes``.
    """
    by_label = {d["label"]: d for d in VISUALLY_READ_PAGE_30}
    assert set(by_label) == {"12D", "12E", "12F"}

    d, e, f = by_label["12D"], by_label["12E"], by_label["12F"]

    # 12E's Paid note is legible and equals its net to the paisa.
    assert e["settled"] == e["net"] == 28_201.56
    assert e["settled_on"] == "29 Dec"
    assert e["ocr_notes"] == []

    # The other two were not read, and say so rather than offering a number.
    for block in (d, f):
        assert block["settled"] is None
        assert block["settled_on"] is None
        assert any("not" in n.lower() and "gu" in n.lower() for n in block["ocr_notes"])
        assert "NOT read" in block["evidence"]

    # A None is "not read", never zero: it must not look like a settled 0.
    assert all(block["settled"] != 0 for block in (d, e, f))

    # 12F's sell line items were not resolved, so the list is empty and
    # components_ok says False — with a note that no sum disagreed.
    assert f["sell_components"] == []
    assert f["components_ok"] == {"buy": True, "sell": False}
    assert any("nothing to check" in n for n in f["ocr_notes"])

    # What was read closes on the written totals for all three. 12D is a
    # receivable, so its net is sell − buy while the two payables are
    # buy − sell — |buy − sell| is the check that fits both.
    for block in (d, e, f):
        assert block["net_matches_written_totals"] is True
        assert round(abs(block["buy_total"] - block["sell_total"]), 2) == block["net"]

    # 12D's 0.01 buy gap is recorded, not closed by editing a component.
    assert d["components_ok"] == {"buy": False, "sell": True}
    assert len(d["source_discrepancies"]) == 1
    assert "0.01" in d["source_discrepancies"][0]
    assert d["buy_total"] == 283_457.42


def test_page28_12c_reports_a_disagreement_instead_of_nudging_a_figure():
    """12C doesn't close as read. That is recorded, not resolved.

    ``77793.55 - 68832.46 = 8961.09`` against a written net of ``8963.09``.
    Arithmetic tells us *that* one of the three readings is wrong; it cannot
    say which, so nothing here picks a number to make it balance.
    """
    by_label = {d["label"]: d for d in VISUALLY_READ_PAGE_28}
    assert set(by_label) == {"12A", "12B", "12C"}

    a, b, c = by_label["12A"], by_label["12B"], by_label["12C"]

    # The two that close, close on every check.
    for block in (a, b):
        assert round(sum(block["buy_components"]), 2) == block["buy_total"]
        assert round(sum(block["sell_components"]), 2) == block["sell_total"]
        assert round(block["buy_total"] - block["sell_total"], 2) == block["net"]
        assert block["net_matches_written_totals"] is True
        assert block["source_discrepancies"] == []
        assert block["settled"] == block["net"]

    # 12C does not close, and the record says so.
    assert c["net_matches_written_totals"] is False
    assert round(c["buy_total"] - c["sell_total"], 2) == 8_961.09
    assert c["net"] == 8_963.09  # what the page writes, unchanged
    assert len(c["source_discrepancies"]) == 1
    assert "2.00" in c["source_discrepancies"][0]

    # No figure was adjusted to close it, and no cause was assigned.
    assert c["buy_total"] == 77_793.55
    assert c["sell_total"] == 68_832.46
    assert any("does not say which" in n for n in c["ocr_notes"])
    assert any("not as a proven mistake" in n for n in c["ocr_notes"])

    # The Paid note is withheld for the same reason: with the block in doubt,
    # a cloud figure would be a guess.
    assert c["settled"] is None
    assert c["settled_on"] is None
    assert "NOT read" in c["evidence"]


# ================================================================ provenance
def _make_pdf(path):
    """A minimal valid one-page PDF, because ``import_records`` reads the page count."""
    import pymupdf

    doc = pymupdf.open()
    doc.new_page()
    doc.save(str(path))
    doc.close()
    return path


def _record(page: int = 21, ref: str = "9A", value=65_550.33) -> ExtractedRecord:
    return ExtractedRecord(
        record_type=RecordType.SETTLEMENT,
        page=page,
        source_ref=ref,
        raw_text="77609.76 - 12059.43",
        value=value,
        field_name="net_payable",
        unit="NPR",
        extraction_method="manual_visual",
        verification_status=VerificationStatus.VERIFIED,
        original_reading="77609.76",
        page_sha256="abc123",
        verification_note="read from page_21.png 2026-10-12",
    )


def test_v5_columns_are_created_on_a_fresh_database(tmp_path):
    db = tmp_path / "fresh.sqlite"
    init_app_db(db)
    with get_conn(db) as conn:
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(pdf_records)")}
    for name in (
        "extraction_method",
        "verification_status",
        "original_reading",
        "corrected_value",
        "correction_history",
        "reconciliation",
        "page_sha256",
        "verification_note",
    ):
        assert name in cols, name


def test_v5_migration_adds_columns_to_a_v4_database(tmp_path):
    """A database created before v5 must gain the columns, not fail to import."""
    db = tmp_path / "v4.sqlite"
    init_app_db(db)
    with get_conn(db) as conn:
        # Simulate a v4 table: drop the provenance columns SQLite can drop.
        # ALTER TABLE cannot drop, so rebuild the table the way v4 left it.
        conn.execute("ALTER TABLE pdf_records RENAME TO pdf_records_old")
        conn.execute(
            """
            CREATE TABLE pdf_records (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                import_id     INTEGER NOT NULL REFERENCES pdf_imports(id),
                record_type   TEXT NOT NULL,
                page          INTEGER NOT NULL,
                source_ref    TEXT NOT NULL DEFAULT '',
                raw_text      TEXT NOT NULL DEFAULT '',
                value         TEXT,
                field_name    TEXT NOT NULL DEFAULT '',
                symbol        TEXT,
                record_date   TEXT,
                unit          TEXT,
                confidence    TEXT NOT NULL DEFAULT 'uncertain',
                review_status TEXT NOT NULL DEFAULT 'unreviewed',
                note          TEXT NOT NULL DEFAULT '',
                UNIQUE (import_id, page, source_ref, field_name, symbol)
            )
            """
        )
        conn.execute("DROP TABLE pdf_records_old")
    # Re-running init must migrate the table in place.
    assert init_app_db(db) == SCHEMA_VERSION
    with get_conn(db) as conn:
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(pdf_records)")}
    assert "verification_status" in cols
    assert "correction_history" in cols


def test_import_persists_every_provenance_field(tmp_path):
    db = tmp_path / "state.sqlite"
    init_app_db(db)
    pdf = _make_pdf(tmp_path / "WRITTENdata.pdf")
    summary = import_records([_record()], pdf, db)
    assert summary["records_total"] == 1

    with get_conn(db) as conn:
        row = dict(conn.execute("SELECT * FROM pdf_records").fetchone())
    assert row["extraction_method"] == "manual_visual"
    assert row["verification_status"] == "verified"
    assert row["original_reading"] == "77609.76"
    assert row["page_sha256"] == "abc123"
    assert json.loads(row["correction_history"]) == []
    assert row["reconciliation"] == "not_applicable"


def test_reimporting_does_not_duplicate_and_keeps_history(tmp_path):
    db = tmp_path / "state.sqlite"
    init_app_db(db)
    pdf = _make_pdf(tmp_path / "WRITTENdata.pdf")

    first = import_records([_record()], pdf, db)
    assert first["records_inserted"] == 1

    with get_conn(db) as conn:
        rid = conn.execute("SELECT id FROM pdf_records").fetchone()["id"]
    append_correction(rid, 65_551.00, "re-read of page 21", db)

    again = import_records([_record()], pdf, db)
    assert again["records_inserted"] == 0
    with get_conn(db) as conn:
        rows = conn.execute("SELECT * FROM pdf_records").fetchall()
    assert len(rows) == 1
    hist = json.loads(rows[0]["correction_history"])
    assert len(hist) == 1
    assert hist[0]["from"] == 65_550.33
    assert hist[0]["to"] == 65_551.00
    assert hist[0]["reason"] == "re-read of page 21"


def test_correction_preserves_the_original_reading(tmp_path):
    db = tmp_path / "state.sqlite"
    init_app_db(db)
    pdf = _make_pdf(tmp_path / "WRITTENdata.pdf")
    import_records([_record()], pdf, db)
    with get_conn(db) as conn:
        rid = conn.execute("SELECT id FROM pdf_records").fetchone()["id"]

    append_correction(rid, 65_551.00, "re-read of page 21", db)
    with get_conn(db) as conn:
        row = dict(conn.execute("SELECT * FROM pdf_records WHERE id=?", (rid,)).fetchone())
    # The untouched reading survives beside the corrected one.
    assert row["raw_text"] == "77609.76 - 12059.43"
    assert row["original_reading"] == "77609.76"
    assert row["value"] == json.dumps(65_550.33)
    assert json.loads(row["corrected_value"]) == 65_551.00
    assert row["verification_status"] == "corrected_verified"
    assert row["review_status"] == "corrected"


def test_a_correction_without_a_reason_is_rejected(tmp_path):
    db = tmp_path / "state.sqlite"
    init_app_db(db)
    pdf = _make_pdf(tmp_path / "WRITTENdata.pdf")
    import_records([_record()], pdf, db)
    with get_conn(db) as conn:
        rid = conn.execute("SELECT id FROM pdf_records").fetchone()["id"]
    with pytest.raises(PdfValidationError, match="must state its reason"):
        append_correction(rid, 1.0, "   ", db)


def test_marking_verified_requires_stated_evidence(tmp_path):
    db = tmp_path / "state.sqlite"
    init_app_db(db)
    pdf = _make_pdf(tmp_path / "WRITTENdata.pdf")
    import_records([_record()], pdf, db)
    with get_conn(db) as conn:
        rid = conn.execute("SELECT id FROM pdf_records").fetchone()["id"]
    with pytest.raises(PdfValidationError, match="supporting evidence"):
        set_verification_status([rid], VerificationStatus.VERIFIED, "  ", db)
    out = set_verification_status([rid], VerificationStatus.VERIFIED, "read page 21 image", db)
    assert out["updated"] == 1
    assert "read page 21 image" in out["note"]


def test_ocr_only_records_are_not_usable(tmp_path):
    """The whole point of the status: machine text stays out of the ledger."""
    db = tmp_path / "state.sqlite"
    init_app_db(db)
    pdf = _make_pdf(tmp_path / "WRITTENdata.pdf")

    verified = _record(ref="9A")
    machine = ExtractedRecord(
        record_type=RecordType.SETTLEMENT,
        page=19,
        source_ref="8C",
        raw_text="168,147.83",
        value=168_147.83,
        field_name="buy_total",
        unit="NPR",
        extraction_method="apple_vision_ocr",
        verification_status=VerificationStatus.OCR_ONLY,
    )
    import_records([verified, machine], pdf, db)
    rows = usable_records(db)
    assert len(rows) == 1
    assert rows[0]["source_ref"] == "9A"
    assert rows[0]["verification_status"] == "verified"


def test_review_status_still_refuses_to_go_backwards(tmp_path):
    db = tmp_path / "state.sqlite"
    init_app_db(db)
    pdf = _make_pdf(tmp_path / "WRITTENdata.pdf")
    import_records([_record()], pdf, db)
    with get_conn(db) as conn:
        rid = conn.execute("SELECT id FROM pdf_records").fetchone()["id"]
    with pytest.raises(PdfValidationError, match="cannot set a record back"):
        set_review_status([rid], ReviewStatus.UNREVIEWED, db)


# ====================================================================== ocr io
def test_vision_page_reader_exposes_the_status_stamp():
    page = read_vision_page(21)
    assert page["exists"] is True
    assert page["meta"]["status"] == "OCR_ONLY"
    assert page["meta"]["orientation"] in {"up", "down", "left", "right"}
    assert page["text"]


def test_vision_page_reader_reports_a_missing_page_instead_of_raising():
    out = read_vision_page(999)
    assert out == {"exists": False, "meta": {}, "text": ""}
