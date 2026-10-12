"""Tests for the Written Data.pdf extraction module.

The PDF is private handwritten trading records, so tests use synthetic records
that mirror the real structure without exposing any personal data.
"""

from __future__ import annotations

import pytest

from megatool.db import init_app_db
from megatool.written_pdf import (
    ExtractedRecord,
    ExtractionConfidence,
    PdfValidationError,
    RecordType,
    ReviewStatus,
    WrittenPdfExtractor,
    build_manifest,
    import_records,
    parse_nepse_number,
    query_records,
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
