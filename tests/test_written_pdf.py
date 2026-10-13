"""Tests for the Written Data.pdf extraction module.

The PDF is private handwritten trading records, so tests use synthetic records
that mirror the real structure without exposing any personal data.
"""

from __future__ import annotations

import json

import pytest

from megatool.db import get_conn, init_app_db
from megatool.written_pdf import (
    ExtractedRecord,
    ExtractionConfidence,
    PdfValidationError,
    RecordType,
    ReviewStatus,
    VerificationStatus,
    WrittenPdfExtractor,
    append_correction,
    build_manifest,
    import_records,
    parse_nepse_number,
    query_records,
    set_review_status,
    validate_eps,
    validate_nepse_symbol,
    validate_price,
    validate_quantity,
    validate_settlement_reconciliation,
)


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "pdf_test.sqlite"
    init_app_db(path)
    return path


# ---------------------------------------------------------------- validation


def test_validate_symbol_accepts_real_nepse_symbols():
    assert validate_nepse_symbol("NABIL") == "NABIL"
    assert validate_nepse_symbol("nabil") == "NABIL"
    assert validate_nepse_symbol("ACLBSL") == "ACLBSL"


def test_validate_symbol_rejects_garbage():
    with pytest.raises(PdfValidationError):
        validate_nepse_symbol("")
    with pytest.raises(PdfValidationError):
        validate_nepse_symbol("X")
    with pytest.raises(PdfValidationError):
        validate_nepse_symbol("TOOLONGSYMBOL123")


def test_validate_price_rejects_non_finite():
    with pytest.raises(PdfValidationError):
        validate_price(float("nan"), "NABIL")
    with pytest.raises(PdfValidationError):
        validate_price(float("inf"), "NABIL")
    with pytest.raises(PdfValidationError):
        validate_price(-100.0, "NABIL")


def test_validate_price_rejects_implausibly_high():
    with pytest.raises(PdfValidationError, match="implausibly high"):
        validate_price(500_000.0, "NABIL")


def test_validate_price_accepts_normal_range():
    assert validate_price(316.0, "ADBL") == 316.0
    assert validate_price(1.5, "SOME") == 1.5


def test_validate_quantity_requires_whole_positive():
    assert validate_quantity(100, "NABIL") == 100
    with pytest.raises(PdfValidationError):
        validate_quantity(0, "NABIL")
    with pytest.raises(PdfValidationError):
        validate_quantity(-5, "NABIL")
    with pytest.raises(PdfValidationError):
        validate_quantity(10**15, "NABIL")


def test_validate_eps_allows_negative_for_losses():
    # Companies can have negative EPS (losses)
    assert validate_eps(-3.84, "MKJC") == -3.84
    assert validate_eps(46.0, "TPC") == 46.0
    with pytest.raises(PdfValidationError):
        validate_eps(float("nan"), "NABIL")
    with pytest.raises(PdfValidationError, match="implausible"):
        validate_eps(500_000.0, "NABIL")


def test_validate_settlement_reconciliation_passes_when_balanced():
    # sell 226,359.28 - buy 168,147.83 = 58,211.45
    validate_settlement_reconciliation(168_147.83, 226_359.28, 58_211.45)


def test_validate_settlement_reconciliation_catches_discrepancy():
    with pytest.raises(PdfValidationError, match="does not reconcile"):
        validate_settlement_reconciliation(100_000.0, 200_000.0, 50_000.0)


# Regression: "Net Payable" on page 21 is buy - sell, not sell - buy. The
# original implementation signed the comparison and rejected all four correct
# settlements on that page.
def test_settlement_reconciliation_accepts_net_payable_convention():
    # 106,186.34 (buy) - 88,169.68 (sell) = 18,016.66 payable
    validate_settlement_reconciliation(106_186.34, 88_169.68, 18_016.66)


def test_settlement_reconciliation_all_four_page21_settlements():
    page21 = [
        (186_129.76, 120_579.43, 65_550.33),
        (106_186.34, 88_169.68, 18_016.66),
        (189_763.58, 157_168.39, 32_595.19),
        (54_157.24, 45_035.39, 9_121.85),
    ]
    for buy, sell, net in page21:
        validate_settlement_reconciliation(buy, sell, net)


def test_settlement_reconciliation_still_rejects_wrong_net_when_buy_exceeds_sell():
    # buy > sell, but the net is wrong - must still raise.
    with pytest.raises(PdfValidationError, match="does not reconcile"):
        validate_settlement_reconciliation(106_186.34, 88_169.68, 99_999.99)


# ---------------------------------------------------------------- number parsing


def test_parse_nepse_number_plain():
    assert parse_nepse_number("1000") == 1000.0
    assert parse_nepse_number("1,000") == 1000.0
    assert parse_nepse_number("1,00,000") == 100_000.0


def test_parse_nepse_number_currency_prefix():
    assert parse_nepse_number("Rs. 1,000") == 1000.0
    assert parse_nepse_number("NPR 500") == 500.0


def test_parse_nepse_number_parentheses_negative():
    assert parse_nepse_number("(50)") == -50.0
    assert parse_nepse_number("(3.84)") == -3.84


def test_parse_nepse_number_crore_multiplier():
    assert parse_nepse_number("2.2cr") == 22_000_000.0
    assert parse_nepse_number("17cr") == 170_000_000.0


def test_parse_nepse_number_lakh_multiplier():
    assert parse_nepse_number("15L") == 1_500_000.0
    assert parse_nepse_number("18L") == 1_800_000.0


def test_parse_nepse_number_lakh_word_multiplier():
    """lakh (the word) must multiply by 100,000.

    The branch used to look for "lac" (with a c) and a digit followed by an
    uppercase L, so "2 lakh" returned 2.0 - a 100,000x understatement of a real
    Nepali amount. Every spelling that appears in Nepali financial documents
    is pinned here against a hand-written expected value.
    """
    cases = [
        ("2 lakh", 200_000.0),
        ("2 Lakh", 200_000.0),
        ("2 LAKH", 200_000.0),
        ("2 lakh.", 200_000.0),
        ("Rs 2.5 lakh", 250_000.0),
        ("2 lac", 200_000.0),
        ("2L", 200_000.0),
        ("2l", 200_000.0),
        ("2 L", 200_000.0),
        ("15L", 1_500_000.0),
        ("0.75 lakh", 75_000.0),
    ]
    for text, expected in cases:
        assert parse_nepse_number(text) == pytest.approx(expected), text


def test_parse_nepse_number_crore_still_wins_when_both_present():
    # crore is checked first; a value must not be scaled twice.
    assert parse_nepse_number("2 crore") == 20_000_000.0
    assert parse_nepse_number("2.5 cr") == 25_000_000.0


def test_parse_nepse_number_does_not_multiply_plain_amounts():
    # No unit word -> no multiplier. An ordinary rupee figure must be exact.
    for text in ("1,00,000", "1000", "Rs. 1,000", "NPR 500", "1,23,456.78"):
        assert parse_nepse_number(text) == float(
            text.replace(",", "").replace("Rs.", "").replace("NPR", "").strip()
        )


def test_parse_nepse_number_rejects_garbage():
    with pytest.raises(PdfValidationError):
        parse_nepse_number("")
    with pytest.raises(PdfValidationError):
        parse_nepse_number("abc")
    with pytest.raises(PdfValidationError):
        parse_nepse_number("...")


# ---------------------------------------------------------------- extraction


def _sample_records() -> list[ExtractedRecord]:
    """Synthetic records mirroring the real structure (no personal data)."""
    return [
        ExtractedRecord(
            record_type=RecordType.FUNDAMENTAL,
            page=1,
            source_ref="Hydro 01 EPS, row 1, col 1",
            symbol="TPC",
            field_name="eps",
            value=46.0,
            unit="NPR",
            confidence=ExtractionConfidence.HIGH,
        ),
        ExtractedRecord(
            record_type=RecordType.FUNDAMENTAL,
            page=1,
            source_ref="Hydro 01 EPS, row 1, col 2",
            symbol="SAHAS",
            field_name="eps",
            value=39.0,
            unit="NPR",
            confidence=ExtractionConfidence.MEDIUM,
        ),
        ExtractedRecord(
            record_type=RecordType.TRADE,
            page=18,
            source_ref="Trading record, Aug 2024",
            symbol="NABIL",
            field_name="buy_price",
            value=300.0,
            unit="NPR",
            confidence=ExtractionConfidence.HIGH,
            record_date=None,
        ),
        ExtractedRecord(
            record_type=RecordType.NOTE,
            page=17,
            source_ref="MACD checklist",
            raw_text="Divergence, Momentum check around 0 line",
            confidence=ExtractionConfidence.LOW,
        ),
    ]


def test_import_records_and_query(db):
    records = _sample_records()
    out = import_records(records, "WRITTENdata.pdf", db_path=db)
    assert out["records_total"] == 4
    assert out["records_inserted"] == 4
    assert out["unreviewed"] == 4

    # Query by symbol
    rows = query_records(db_path=db, symbol="TPC")
    assert len(rows) == 1
    assert rows[0]["field_name"] == "eps"
    assert rows[0]["value"] == 46.0

    # Query by type
    rows = query_records(db_path=db, record_type=RecordType.FUNDAMENTAL)
    assert len(rows) == 2

    # Query by page
    rows = query_records(db_path=db, page=17)
    assert len(rows) == 1
    assert rows[0]["record_type"] == "note"


def test_import_is_idempotent(db):
    records = _sample_records()
    out1 = import_records(records, "WRITTENdata.pdf", db_path=db)
    out2 = import_records(records, "WRITTENdata.pdf", db_path=db)
    assert out1["records_inserted"] == 4
    # Second import updates rather than duplicates
    assert out2["records_inserted"] == 0
    assert out2["records_updated"] == 4
    # Total rows in DB is still 4
    rows = query_records(db_path=db)
    assert len(rows) == 4


def test_extraction_method_is_stored_and_retrieved(db):
    """Every record remembers HOW it was read, not just what it says.

    A number that cannot be traced back to a reading method cannot be audited,
    so an empty ``extraction_method`` is preserved verbatim rather than
    defaulted to something reassuring.
    """
    records = _sample_records()
    records[0].extraction_method = "apple_vision_ocr"
    records[1].extraction_method = "manual_visual"
    import_records(records, "WRITTENdata.pdf", db_path=db)

    rows = {r["symbol"]: r for r in query_records(db_path=db)}
    assert rows["TPC"]["extraction_method"] == "apple_vision_ocr"
    assert rows["SAHAS"]["extraction_method"] == "manual_visual"
    # The others were imported with no method recorded; that stays empty,
    # not invented.
    assert rows["NABIL"]["extraction_method"] == ""


def test_append_correction_preserves_the_original_reading(db):
    """A correction must never destroy what was there before.

    ``value`` (the original) and ``raw_text`` are untouched; the new figure
    goes to ``corrected_value`` and the change is appended to the history, so
    the record can always be reconstructed back to its pre-correction state.
    """
    records = _sample_records()
    records[0].extraction_method = "apple_vision_ocr"
    import_records(records, "WRITTENdata.pdf", db_path=db)

    before = query_records(db_path=db, symbol="TPC")[0]
    original_value = before["value"]
    assert original_value == 46.0

    out = append_correction(
        before["id"],
        45.0,
        "OCR read 46 but the digit is a 45 at full resolution",
        db_path=db,
    )
    assert out["record_id"] == before["id"]
    assert out["entries"] == 1

    after = query_records(db_path=db, symbol="TPC")[0]
    # The original value and raw text are untouched.
    assert after["value"] == original_value
    assert after["raw_text"] == before["raw_text"]
    assert after["extraction_method"] == "apple_vision_ocr"
    # The new figure lives in corrected_value, not over the original.
    assert json.loads(after["corrected_value"]) == 45.0

    history = json.loads(after["correction_history"])
    assert len(history) == 1
    assert history[0]["from"] == original_value
    assert history[0]["to"] == 45.0
    assert history[0]["reason"].startswith("OCR read 46")
    assert history[0]["original_reading"] == before["raw_text"]


def test_append_correction_is_append_only_across_multiple_corrections(db):
    """Two corrections produce two history entries; the first is not replaced."""
    records = _sample_records()
    import_records(records, "WRITTENdata.pdf", db_path=db)
    row = query_records(db_path=db, symbol="TPC")[0]

    append_correction(row["id"], 45.0, "first fix", db_path=db)
    append_correction(row["id"], 44.5, "second fix", db_path=db)

    final = query_records(db_path=db, symbol="TPC")[0]
    history = json.loads(final["correction_history"])
    assert [h["to"] for h in history] == [45.0, 44.5]
    assert [h["reason"] for h in history] == ["first fix", "second fix"]
    # Each entry records the value it replaced, so the chain is walkable back.
    assert [h["from"] for h in history] == [46.0, 45.0]
    # The ORIGINAL original survives both corrections.
    assert final["value"] == 46.0


def test_append_correction_marks_the_record_corrected_and_requires_a_reason(db):
    """A correction without a stated reason is a guess, so it is rejected."""
    records = _sample_records()
    import_records(records, "WRITTENdata.pdf", db_path=db)
    row = query_records(db_path=db, symbol="TPC")[0]

    with pytest.raises(PdfValidationError):
        append_correction(row["id"], 45.0, "   ", db_path=db)

    # Nothing was recorded by the rejected call.
    assert json.loads(query_records(db_path=db, symbol="TPC")[0]["correction_history"]) == []

    # An accepted correction is visibly marked corrected_verified, the status
    # that gates use in financial output.
    append_correction(row["id"], 45.0, "visual check", db_path=db)
    after = query_records(db_path=db, symbol="TPC")[0]
    assert after["verification_status"] == VerificationStatus.CORRECTED_VERIFIED.value
    assert after["review_status"] == ReviewStatus.CORRECTED.value


def test_correction_on_an_unknown_record_fails_loudly(db):
    """A correction to a row that does not exist must not silently succeed."""
    with pytest.raises(PdfValidationError):
        append_correction(999_999, 1.0, "nonexistent", db_path=db)


def test_review_status_filter(db):
    records = _sample_records()
    import_records(records, "WRITTENdata.pdf", db_path=db)
    # Mark one as reviewed
    records[0].review_status = ReviewStatus.REVIEWED
    import_records(records, "WRITTENdata.pdf", db_path=db)
    rows = query_records(db_path=db, review_status=ReviewStatus.REVIEWED)
    assert len(rows) == 1


def test_extracted_record_to_dict():
    r = ExtractedRecord(
        record_type=RecordType.FUNDAMENTAL,
        page=1,
        symbol="TPC",
        field_name="eps",
        value=46.0,
        confidence=ExtractionConfidence.HIGH,
    )
    d = r.to_dict()
    assert d["record_type"] == "fundamental"
    assert d["page"] == 1
    assert d["symbol"] == "TPC"
    assert d["confidence"] == "high"
    assert d["review_status"] == "unreviewed"


# ---------------------------------------------------------------- PDF loading


def test_pdf_manifest():
    manifest = build_manifest("WRITTENdata.pdf")
    assert manifest["page_count"] == 52
    assert manifest["filename"] == "WRITTENdata.pdf"
    assert manifest["pages"][0]["orientation"] == "landscape"
    assert manifest["pages"][25]["orientation"] == "portrait"
    # No text layer in any page
    assert all(not p["has_text_layer"] for p in manifest["pages"])


def test_extractor_renders_page():
    with WrittenPdfExtractor("WRITTENdata.pdf") as ext:
        data = ext.render_page(0, dpi=150)
        assert len(data) > 0
        assert data[:4] == b"\x89PNG"
        assert ext.page_orientation(0) == "landscape"
        assert ext.page_orientation(25) == "portrait"


def test_extractor_save_load_json(tmp_path):
    records = _sample_records()
    path = tmp_path / "extracted.json"
    with WrittenPdfExtractor("WRITTENdata.pdf") as ext:
        ext.add_records(records)
        ext.save_json(path)
    with WrittenPdfExtractor("WRITTENdata.pdf") as ext:
        ext.load_json(path)
        assert len(ext.records) == 4
        assert ext.records[0].symbol == "TPC"


# ---------------------------------------------------------------- audit B fixes


def test_import_records_stores_the_real_page_count(db):
    """The import must record the PDF's actual page count, not a constant."""
    records = _sample_records()
    out = import_records(records, "WRITTENdata.pdf", db_path=db)
    assert out["records_total"] == 4
    with get_conn(db) as conn:
        row = conn.execute("SELECT page_count FROM pdf_imports LIMIT 1").fetchone()
        # WRITTENdata.pdf has 52 pages; the value must come from the file.
        assert row["page_count"] == 52


def test_min_confidence_filter_includes_that_level_and_above(db):
    """min_confidence must include the requested level and everything
    above it — never a fixed set."""
    records = [
        ExtractedRecord(
            record_type=RecordType.FUNDAMENTAL,
            page=1,
            source_ref=f"row {i}",
            symbol="TPC",
            field_name="eps",
            value=10.0 + i,
            confidence=c,
        )
        for i, c in enumerate(
            [
                ExtractionConfidence.UNCERTAIN,
                ExtractionConfidence.LOW,
                ExtractionConfidence.MEDIUM,
                ExtractionConfidence.HIGH,
            ]
        )
    ]
    import_records(records, "WRITTENdata.pdf", db_path=db)

    # min=high -> only the high record
    rows = query_records(db_path=db, min_confidence=ExtractionConfidence.HIGH)
    assert len(rows) == 1
    assert rows[0]["confidence"] == "high"

    # min=medium -> medium and high
    rows = query_records(db_path=db, min_confidence=ExtractionConfidence.MEDIUM)
    assert len(rows) == 2
    assert {r["confidence"] for r in rows} == {"medium", "high"}

    # min=low -> low, medium, high
    rows = query_records(db_path=db, min_confidence=ExtractionConfidence.LOW)
    assert len(rows) == 3
    assert {r["confidence"] for r in rows} == {"low", "medium", "high"}

    # min=uncertain -> all four
    rows = query_records(db_path=db, min_confidence=ExtractionConfidence.UNCERTAIN)
    assert len(rows) == 4


# ---------------------------------------------------------------- review workflow


def test_review_status_can_be_set(db):
    records = _sample_records()
    import_records(records, "WRITTENdata.pdf", db_path=db)
    ids = [r["id"] for r in query_records(db_path=db)]
    out = set_review_status(ids[:2], ReviewStatus.REVIEWED, db_path=db)
    assert out["updated"] == 2
    assert out["not_found"] == 0
    assert len(query_records(db_path=db, review_status=ReviewStatus.REVIEWED)) == 2


def test_review_status_refuses_returning_to_unreviewed(db):
    records = _sample_records()
    import_records(records, "WRITTENdata.pdf", db_path=db)
    with pytest.raises(PdfValidationError, match="unreviewed"):
        set_review_status([1], ReviewStatus.UNREVIEWED, db_path=db)


def test_review_status_reports_missing_ids(db):
    out = set_review_status([999, 1000], ReviewStatus.REJECTED, db_path=db)
    assert out["updated"] == 0
    assert out["not_found"] == 2


def test_review_status_requires_ids(db):
    with pytest.raises(PdfValidationError, match="no record ids"):
        set_review_status([], ReviewStatus.REVIEWED, db_path=db)


# ------------------------------------------------------------------ pdf CLI
def _cli_records() -> None:
    """Load the synthetic sample into the same store the CLI writes to."""
    import_records(_sample_records(), "WRITTENdata.pdf")


def test_pdf_review_cli_marks_a_record_reviewed(capsys):
    from megatool.cli import main

    _cli_records()
    assert main(["pdf", "review", "--ids", "1", "--status", "reviewed"]) == 0
    assert "Set 1 record(s) to reviewed" in capsys.readouterr().out
    assert len(query_records(review_status=ReviewStatus.REVIEWED)) == 1


def test_pdf_review_cli_rejects_an_unknown_status(capsys):
    from megatool.cli import main

    _cli_records()
    assert main(["pdf", "review", "--ids", "1", "--status", "maybe"]) == 1
    err = capsys.readouterr().err
    assert "unknown status" in err
    assert "reviewed" in err
    # nothing was changed
    assert len(query_records(review_status=ReviewStatus.UNREVIEWED)) == len(_sample_records())


def test_pdf_review_cli_refuses_sending_a_record_back_to_unreviewed(capsys):
    from megatool.cli import main

    _cli_records()
    assert main(["pdf", "review", "--ids", "1", "--status", "unreviewed"]) == 1
    assert "unreviewed" in capsys.readouterr().err


def test_pdf_review_cli_refuses_a_non_numeric_id(capsys):
    from megatool.cli import main

    _cli_records()
    assert main(["pdf", "review", "--ids", "abc", "--status", "reviewed"]) == 1
    assert "not a record id" in capsys.readouterr().err


def test_pdf_review_cli_reports_ids_that_do_not_exist(capsys):
    from megatool.cli import main

    _cli_records()
    assert main(["pdf", "review", "--ids", "9999", "--status", "reviewed"]) == 1
    captured = capsys.readouterr()
    assert "not found: 1" in captured.err
    assert "Set 0 record(s)" in captured.out
