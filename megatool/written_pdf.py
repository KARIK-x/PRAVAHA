"""Written Data.pdf extraction and integration.

The PDF is a 52-page handwritten trading journal with **no text layer** — it is fully
scanned. Automated OCR (tesseract 5.5.0) was attempted on all 52 pages and **failed on
42 of them** (empty or gibberish output). Tesseract is designed for printed text, not
handwriting.

This module therefore provides:

1. **Page rendering** via PyMuPDF at configurable DPI.
2. **A structured extraction interface** for manual or AI-assisted transcription.
3. **Validation** of extracted financial values.
4. **An import pipeline** that writes reviewed records into the database with full
   provenance (page number, extraction confidence, review status).

No extracted value is treated as verified until it has been reviewed. The module
enforces this with a `review_status` field on every record.

The original PDF is never modified. Nothing is committed to git (see .gitignore).
"""

from __future__ import annotations

import contextlib
import hashlib
import re
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from pathlib import Path
from typing import Any

import pymupdf


class ExtractionConfidence(StrEnum):
    """How confident we are in an extracted value.

    HIGH:     Clearly legible; symbol, digits, decimal points unambiguous.
    MEDIUM:   Legible but one character could be misread (1 vs 7, 0 vs 8).
    LOW:      Partially legible or ambiguous; needs review.
    UNCERTAIN: Cannot be read reliably; placeholder for human review.
    """

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNCERTAIN = "uncertain"


class ReviewStatus(StrEnum):
    """Whether a record has been reviewed by a human.

    UNREVIEWED: Extracted but not yet checked. NOT safe for financial use.
    REVIEWED:   Checked and confirmed by a human.
    CORRECTED:  Checked and corrected by a human.
    REJECTED:   Checked and rejected as unreliable.
    """

    UNREVIEWED = "unreviewed"
    REVIEWED = "reviewed"
    CORRECTED = "corrected"
    REJECTED = "rejected"


class RecordType(StrEnum):
    FUNDAMENTAL = "fundamental"
    PRICE = "price"
    TRADE = "trade"
    SETTLEMENT = "settlement"
    ACCUMULATION = "accumulation"
    NOTE = "note"
    OTHER = "other"


@dataclass
class ExtractedRecord:
    """One extracted record with full provenance.

    Every value is traceable back to its source location in the PDF.
    """

    record_type: RecordType
    page: int
    # Source location: table name, row/column if identifiable
    source_ref: str = ""
    # The original text as it appeared (for handwriting: a transcription)
    raw_text: str = ""
    # The normalized/extracted value
    value: Any = None
    # Field name if this is a structured field (e.g. "eps", "net_worth")
    field_name: str = ""
    # Stock symbol if applicable
    symbol: str | None = None
    # Date if applicable
    record_date: date | None = None
    # Unit (NPR, shares, crore, lakh, ratio, etc.)
    unit: str | None = None
    # Extraction confidence
    confidence: ExtractionConfidence = ExtractionConfidence.UNCERTAIN
    # Has a human reviewed this record?
    review_status: ReviewStatus = ReviewStatus.UNREVIEWED
    # Free-text note
    note: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "record_type": self.record_type.value,
            "page": self.page,
            "source_ref": self.source_ref,
            "raw_text": self.raw_text,
            "value": self.value,
            "field_name": self.field_name,
            "symbol": self.symbol,
            "record_date": self.record_date.isoformat() if self.record_date else None,
            "unit": self.unit,
            "confidence": self.confidence.value,
            "review_status": self.review_status.value,
            "note": self.note,
        }


class WrittenPdfExtractor:
    """Extract and manage records from Written Data.pdf.

    Usage:
        extractor = WrittenPdfExtractor("WRITTENdata.pdf")
        page = extractor.render_page(0, dpi=200)
        # ... transcribe visually or manually ...
        record = ExtractedRecord(
            record_type=RecordType.FUNDAMENTAL,
            page=1,
            source_ref="Hydro 01 EPS, row 3, col 2",
            symbol="TPC",
            field_name="eps",
            value=46.0,
            unit="NPR",
            confidence=ExtractionConfidence.HIGH,
        )
        extractor.add_record(record)
        extractor.save_json("extracted.json")
    """

    def __init__(self, pdf_path: str | Path):
        self.pdf_path = Path(pdf_path)
        self._doc: pymupdf.Document | None = None
        self.records: list[ExtractedRecord] = []

    @property
    def doc(self) -> pymupdf.Document:
        if self._doc is None:
            self._doc = pymupdf.open(self.pdf_path)
        return self._doc

    @property
    def page_count(self) -> int:
        return len(self.doc)

    def render_page(self, page_number: int, dpi: int = 300) -> bytes:
        """Render a page to PNG bytes (0-indexed)."""
        page = self.doc[page_number]
        pix = page.get_pixmap(dpi=dpi)
        return pix.tobytes("png")

    def render_page_to_file(self, page_number: int, path: str | Path, dpi: int = 300) -> None:
        """Render a page to a PNG file (0-indexed)."""
        page = self.doc[page_number]
        pix = page.get_pixmap(dpi=dpi)
        pix.save(str(path))

    def page_orientation(self, page_number: int) -> str:
        """Return 'landscape' or 'portrait' (0-indexed)."""
        rect = self.doc[page_number].rect
        return "landscape" if rect.width > rect.height else "portrait"

    def add_record(self, record: ExtractedRecord) -> None:
        """Add one extracted record."""
        self.records.append(record)

    def add_records(self, records: list[ExtractedRecord]) -> None:
        self.records.extend(records)

    def records_for_page(self, page: int) -> list[ExtractedRecord]:
        return [r for r in self.records if r.page == page]

    def records_by_type(self, record_type: RecordType) -> list[ExtractedRecord]:
        return [r for r in self.records if r.record_type == record_type]

    def records_by_symbol(self, symbol: str) -> list[ExtractedRecord]:
        return [r for r in self.records if r.symbol and r.symbol.upper() == symbol.upper()]

    def reviewed_records(self) -> list[ExtractedRecord]:
        return [r for r in self.records if r.review_status != ReviewStatus.UNREVIEWED]

    def to_dicts(self) -> list[dict[str, Any]]:
        return [r.to_dict() for r in self.records]

    def save_json(self, path: str | Path) -> None:
        """Save all records to a JSON file (git-ignored as private)."""
        import json

        path = Path(path)
        path.write_text(
            json.dumps(self.to_dicts(), indent=2, ensure_ascii=False, default=str),
            encoding="utf-8",
        )

    def load_json(self, path: str | Path) -> None:
        """Load records from a JSON file."""
        import json

        data = json.loads(Path(path).read_text(encoding="utf-8"))
        self.records = []
        for d in data:
            self.records.append(
                ExtractedRecord(
                    record_type=RecordType(d["record_type"]),
                    page=d["page"],
                    source_ref=d.get("source_ref", ""),
                    raw_text=d.get("raw_text", ""),
                    value=d.get("value"),
                    field_name=d.get("field_name", ""),
                    symbol=d.get("symbol"),
                    record_date=date.fromisoformat(d["record_date"])
                    if d.get("record_date")
                    else None,
                    unit=d.get("unit"),
                    confidence=ExtractionConfidence(d.get("confidence", "uncertain")),
                    review_status=ReviewStatus(d.get("review_status", "unreviewed")),
                    note=d.get("note", ""),
                )
            )

    def close(self) -> None:
        if self._doc is not None:
            self._doc.close()
            self._doc = None

    def __enter__(self) -> WrittenPdfExtractor:
        return self

    def __exit__(self, *args: Any) -> None:
        self.close()


# ---------------------------------------------------------------------- validation
class PdfValidationError(ValueError):
    """Raised when an extracted value fails validation."""


def validate_nepse_symbol(symbol: str) -> str:
    """Validate and normalise a NEPSE trading symbol.

    NEPSE symbols are 2-6 uppercase alphanumeric characters.
    """
    cleaned = symbol.strip().upper()
    if not re.fullmatch(r"[A-Z0-9]{2,8}", cleaned):
        raise PdfValidationError(f"invalid NEPSE symbol: {symbol!r}")
    return cleaned


def validate_positive_number(value: float, field_name: str) -> float:
    """Reject non-finite and non-positive values for a financial field."""
    import math

    if not math.isfinite(value):
        raise PdfValidationError(f"{field_name} must be finite, got {value}")
    if value <= 0:
        raise PdfValidationError(f"{field_name} must be > 0, got {value}")
    return value


def validate_price(value: float, symbol: str) -> float:
    """Validate a share price: must be a plausible NEPSE price (NPR 1 - 100,000)."""
    validate_positive_number(value, f"price for {symbol}")
    if value > 100_000:
        raise PdfValidationError(f"price {value} for {symbol} is implausibly high")
    return value


def validate_quantity(value: int, symbol: str) -> int:
    """Validate a share quantity: whole number, positive, plausible."""
    if not isinstance(value, int) or value <= 0:
        raise PdfValidationError(f"quantity for {symbol} must be a positive whole number")
    if value > 10**12:
        raise PdfValidationError(f"quantity {value} for {symbol} is implausibly large")
    return value


def validate_amount(value: float, symbol: str) -> float:
    """Validate a monetary amount: finite, non-negative (negatives are P&L losses)."""
    import math

    if not math.isfinite(value):
        raise PdfValidationError(f"amount for {symbol} must be finite")
    return value


def validate_eps(value: float, symbol: str) -> float:
    """Validate EPS: finite, can be negative (losses)."""
    import math

    if not math.isfinite(value):
        raise PdfValidationError(f"EPS for {symbol} must be finite")
    if abs(value) > 100_000:
        raise PdfValidationError(f"EPS {value} for {symbol} is implausible")
    return value


def validate_settlement_reconciliation(
    buy_total: float, sell_total: float, net_amount: float, tolerance: float = 0.02
) -> None:
    """Check that a settlement reconciles: sell_total - buy_total ≈ net_amount.

    A discrepancy greater than `tolerance` NPR is flagged, not silently accepted.
    """
    expected = sell_total - buy_total
    if abs(expected - net_amount) > tolerance:
        raise PdfValidationError(
            f"settlement does not reconcile: sell {sell_total} - buy {buy_total} "
            f"= {expected}, but net recorded as {net_amount}"
        )


def parse_nepse_number(raw: str) -> float:
    """Parse a number that may carry thousand separators or a currency sign.

    Handles: "Rs. 1,000", "1.2cr", "15L", "(50)" for negative 50, "1,00.50" etc.
    """
    text = raw.strip()
    # Parentheses mean negative
    negative = False
    if text.startswith("(") and text.endswith(")"):
        negative = True
        text = text[1:-1]
    text = re.sub(r"(?i)\b(rs|npr|nrs|inr|usd|np)\b\.?", "", text)
    text = re.sub(r"[^\d.,\-]", "", text)
    text = text.replace("-", "")

    # Handle Indian digit grouping (1,00,000 vs 100,000)
    if "," in text and "." in text:
        if text.rfind(",") > text.rfind("."):
            text = text.replace(".", "").replace(",", ".")
        else:
            text = text.replace(",", "")
    else:
        text = text.replace(",", "")

    if text in ("", ".") or not any(ch.isdigit() for ch in text):
        raise PdfValidationError(f"not a number: {raw!r}")
    value = float(text)
    if negative:
        value = -value

    # Apply unit multipliers from the original string
    if "(cr)" in raw.lower().replace(" ", "") or "cr" in raw.lower():
        value *= 10_000_000
    elif "lac" in raw.lower() or re.search(r"\dL\b", raw):
        value *= 100_000

    return value


# ---------------------------------------------------------------------- provenance
def page_sha256(page_number: int, pdf_path: str | Path) -> str:
    """Content hash of a rendered page, for deduplication and provenance."""
    extractor = WrittenPdfExtractor(pdf_path)
    try:
        data = extractor.render_page(page_number, dpi=150)
        return hashlib.sha256(data).hexdigest()
    finally:
        extractor.close()


def build_manifest(pdf_path: str | Path) -> dict[str, Any]:
    """Build a page-by-page manifest of the PDF.

    Records orientation, dimensions, and whether the page has a text layer.
    """
    extractor = WrittenPdfExtractor(pdf_path)
    try:
        pages = []
        for i in range(extractor.page_count):
            page = extractor.doc[i]
            has_text = bool((page.get_text() or "").strip())
            rect = page.rect
            pages.append(
                {
                    "page": i + 1,
                    "orientation": "landscape" if rect.width > rect.height else "portrait",
                    "width_pt": round(rect.width, 1),
                    "height_pt": round(rect.height, 1),
                    "has_text_layer": has_text,
                }
            )
        return {
            "filename": Path(pdf_path).name,
            "page_count": extractor.page_count,
            "pages": pages,
        }
    finally:
        extractor.close()


# ---------------------------------------------------------------------- import
def import_records(
    records: list[ExtractedRecord],
    pdf_path: str | Path,
    db_path: Any = None,
) -> dict[str, Any]:
    """Import extracted records into the database with full provenance.

    Idempotent: re-importing the same (source_file, content_hash) with the same
    records updates existing rows rather than duplicating them.

    Only records with review_status != UNREVIEWED are marked as safe for financial
    use. Unreviewed records are stored but flagged.
    """
    import json

    from megatool.db import get_conn, init_app_db, now_iso

    init_app_db(db_path)
    pdf_path = Path(pdf_path)
    content_hash = hashlib.sha256(pdf_path.read_bytes()).hexdigest()

    with get_conn(db_path) as conn:
        # Register the import
        cur = conn.execute(
            "INSERT OR IGNORE INTO pdf_imports (source_file, content_hash, page_count, imported_at) "
            "VALUES (?, ?, ?, ?)",
            (pdf_path.name, content_hash, 52, now_iso()),
        )
        if cur.rowcount == 0:
            row = conn.execute(
                "SELECT id FROM pdf_imports WHERE source_file=? AND content_hash=?",
                (pdf_path.name, content_hash),
            ).fetchone()
            import_id = int(row["id"])
        else:
            import_id = int(cur.lastrowid or 0)

        inserted = 0
        updated = 0
        # Count existing rows before import so we can distinguish insert vs update.
        before = conn.execute(
            "SELECT COUNT(*) c FROM pdf_records WHERE import_id=?", (import_id,)
        ).fetchone()["c"]
        for r in records:
            value_json = (
                json.dumps(r.value, ensure_ascii=False, default=str)
                if r.value is not None
                else None
            )
            conn.execute(
                "INSERT INTO pdf_records "
                "(import_id, record_type, page, source_ref, raw_text, value, field_name, "
                " symbol, record_date, unit, confidence, review_status, note) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(import_id, page, source_ref, field_name, symbol) "
                "DO UPDATE SET "
                "  raw_text=excluded.raw_text, value=excluded.value, "
                "  record_date=excluded.record_date, unit=excluded.unit, "
                "  confidence=excluded.confidence, review_status=excluded.review_status, "
                "  note=excluded.note",
                (
                    import_id,
                    r.record_type.value,
                    r.page,
                    r.source_ref,
                    r.raw_text,
                    value_json,
                    r.field_name,
                    r.symbol or "",
                    r.record_date.isoformat() if r.record_date else None,
                    r.unit,
                    r.confidence.value,
                    r.review_status.value,
                    r.note,
                ),
            )
        after = conn.execute(
            "SELECT COUNT(*) c FROM pdf_records WHERE import_id=?", (import_id,)
        ).fetchone()["c"]
        inserted = after - before
        updated = len(records) - inserted

        return {
            "import_id": import_id,
            "source_file": pdf_path.name,
            "content_hash": content_hash,
            "records_total": len(records),
            "records_inserted": inserted,
            "records_updated": updated,
            "reviewed": sum(1 for r in records if r.review_status != ReviewStatus.UNREVIEWED),
            "unreviewed": sum(1 for r in records if r.review_status == ReviewStatus.UNREVIEWED),
        }


def query_records(
    db_path: Any = None,
    symbol: str | None = None,
    record_type: RecordType | None = None,
    page: int | None = None,
    review_status: ReviewStatus | None = None,
    min_confidence: ExtractionConfidence | None = None,
) -> list[dict[str, Any]]:
    """Query extracted records with filters."""
    import json

    from megatool.db import get_conn

    where: list[str] = []
    params: list[Any] = []
    if symbol:
        where.append("symbol = ?")
        params.append(symbol.upper())
    if record_type:
        where.append("record_type = ?")
        params.append(record_type.value)
    if page:
        where.append("page = ?")
        params.append(page)
    if review_status:
        where.append("review_status = ?")
        params.append(review_status.value)
    if min_confidence:
        where.append("confidence IN (?, ?, ?)")
        params.extend([min_confidence.value, "high", "medium"])

    clause = f"WHERE {' AND '.join(where)}" if where else ""
    with get_conn(db_path) as conn:
        rows = conn.execute(
            f"SELECT * FROM pdf_records {clause} ORDER BY page, source_ref",
            params,
        ).fetchall()

    out = []
    for r in rows:
        d = dict(r)
        if d.get("value"):
            with contextlib.suppress(json.JSONDecodeError, TypeError):
                d["value"] = json.loads(d["value"])
        out.append(d)
    return out
