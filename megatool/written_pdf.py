"""Written Data.pdf extraction and integration.

The PDF is a 52-page handwritten trading journal with **no text layer** — it is fully
scanned. Two OCR methods have actually been run over it and measured against the
hand-built ground truth in ``data/written_pdf/benchmark/ground_truth.json``:

===========================  ===========  ===========  ===========
method                       numbers      numbers      symbols
                               exact       numeric
===========================  ===========  ===========  ===========
tesseract 5.5.0                3/92          4/92        0/46
apple_vision (as-is)          66/92         83/92       33/46
apple_vision (best of 4       68/92         85/92       33/46
  rotations)
===========================  ===========  ===========  ===========

Tesseract is designed for printed text and is unusable here. Apple Vision
(``scripts/vision_ocr_batch.swift``, driven by ``scripts/run_vision_ocr.py``)
reads all 52 pages and is the first pass for transcription. **Its output is
machine text, not a verified reading**: every OCR file is stamped
``status: OCR_ONLY`` and every record it produces keeps ``verification_status``
below ``verified`` until a human checks it against the page image.

This module therefore provides:

1. **Page rendering** via PyMuPDF at configurable DPI.
2. **A structured extraction interface** for manual or AI-assisted transcription.
3. **Validation** of extracted financial values, including settlement arithmetic.
4. **An import pipeline** that writes reviewed records into the database with full
   provenance (page number, extraction method, verification status, correction
   history, page hash).

No extracted value is treated as verified until it has been reviewed. The module
enforces this with both a `review_status` and a `verification_status` field on
every record, and refuses to let OCR-only records count as usable.

The original PDF is never modified. Nothing is committed to git (see .gitignore).
"""

from __future__ import annotations

import contextlib
import hashlib
import re
from dataclasses import dataclass, field
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


class VerificationStatus(StrEnum):
    """Finer-grained provenance state than :class:`ReviewStatus`.

    The two are related but not redundant:

    * ``review_status`` answers "has a human looked at this?" and drives the
      existing API/UI, so it is kept as-is.
    * ``verification_status`` answers "what kind of evidence backs this
      value?", which is what a financial record actually needs before use.

    A record is only safe for accounting or fundamentals once it is
    ``VERIFIED`` or ``CORRECTED_VERIFIED``; ``OCR_ONLY`` machine text must
    never reach portfolio or fundamentals logic.
    """

    OCR_ONLY = "ocr_only"
    TRANSCRIBED_UNVERIFIED = "transcribed_unverified"
    NEEDS_REVIEW = "needs_review"
    VERIFIED = "verified"
    CORRECTED_VERIFIED = "corrected_verified"
    UNRESOLVABLE = "unresolvable"


#: Statuses that carry enough evidence to be used in financial output.
USABLE_VERIFICATION_STATUSES = frozenset(
    {VerificationStatus.VERIFIED, VerificationStatus.CORRECTED_VERIFIED}
)


class ReconciliationStatus(StrEnum):
    """Outcome of an arithmetic self-check on a handwritten figure.

    RECONCILED:      the recorded arithmetic balances within tolerance.
    DISCREPANCY:     it does not balance; the original reading is kept.
    UNRECONCILABLE:  no arithmetic is available to check it (e.g. a lone figure).
    NOT_APPLICABLE:  the check has not been run.
    """

    RECONCILED = "reconciled"
    DISCREPANCY = "discrepancy"
    UNRECONCILABLE = "unreconcilable"
    NOT_APPLICABLE = "not_applicable"


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
    # --- provenance (schema v5) ------------------------------------------------
    # How the value was obtained. Never blank for a machine-produced record.
    extraction_method: str = ""
    # What kind of evidence backs the value.
    verification_status: VerificationStatus = VerificationStatus.OCR_ONLY
    # The untouched machine reading, kept even after a correction.
    original_reading: str = ""
    # The corrected normalized value, separate from ``value``.
    corrected_value: Any = None
    # Append-only JSON list of {at, from, to, reason}.
    correction_history: list[dict[str, Any]] = field(default_factory=list)
    # Outcome of the arithmetic self-check, if one applies.
    reconciliation: ReconciliationStatus = ReconciliationStatus.NOT_APPLICABLE
    # SHA-256 of the rendered source page, for provenance and dedupe.
    page_sha256: str = ""
    # Why this verification status was chosen.
    verification_note: str = ""

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
            "extraction_method": self.extraction_method,
            "verification_status": self.verification_status.value,
            "original_reading": self.original_reading,
            "corrected_value": self.corrected_value,
            "correction_history": self.correction_history,
            "reconciliation": self.reconciliation.value,
            "page_sha256": self.page_sha256,
            "verification_note": self.verification_note,
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
                    extraction_method=d.get("extraction_method", ""),
                    verification_status=VerificationStatus(
                        d.get("verification_status", "ocr_only")
                    ),
                    original_reading=d.get("original_reading", ""),
                    corrected_value=d.get("corrected_value"),
                    correction_history=d.get("correction_history", []) or [],
                    reconciliation=ReconciliationStatus(d.get("reconciliation", "not_applicable")),
                    page_sha256=d.get("page_sha256", ""),
                    verification_note=d.get("verification_note", ""),
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
    """Check that a settlement reconciles: |buy - sell| must equal |net|.

    NEPSE settlements produce a single net amount whose *direction* depends on
    which side is larger:

      * ``buy > sell`` -> a **net payable** (you owe), sign positive
      * ``sell > buy`` -> a **net receivable** (you are owed), sign positive

    The document under extraction ("Written Data.pdf", page 21) labels these
    "Net Payable" and writes ``buy - sell``; other records write ``sell - buy``.
    Comparing signed values therefore rejects settlements that are in fact
    correct, so the magnitude is what reconciles.

    A discrepancy greater than `tolerance` NPR is flagged, not silently
    accepted - a genuinely wrong net still raises.
    """
    expected_magnitude = abs(buy_total - sell_total)
    if abs(abs(net_amount) - expected_magnitude) > tolerance:
        raise PdfValidationError(
            f"settlement does not reconcile: buy {buy_total} vs sell {sell_total} "
            f"differs by {expected_magnitude}, but net recorded as {net_amount}"
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

    # Apply unit multipliers from the original string. The letters are removed
    # by the ``[^\d.,-]`` strip above, so the unit has to be read from ``raw``.
    # "lakh" contains no "c", so it must be matched as a word in its own right;
    # "2l"/"2L" has no word boundary before the "l", so a digit lookbehind is
    # also needed. Missing this returned 2.0 for "2 lakh" - a 100,000x
    # understatement of a real Nepali amount.
    lower = raw.lower()
    if "(cr)" in lower.replace(" ", "") or "cr" in lower:
        value *= 10_000_000
    elif re.search(r"(?i)\b(?:lakh?|lac|l)\b|(?<=\d)l\b", raw):
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
    # Derive the page count from the document itself, never a magic number.
    with WrittenPdfExtractor(pdf_path) as ext:
        page_count = ext.page_count

    with get_conn(db_path) as conn:
        # Register the import
        cur = conn.execute(
            "INSERT OR IGNORE INTO pdf_imports (source_file, content_hash, page_count, imported_at) "
            "VALUES (?, ?, ?, ?)",
            (pdf_path.name, content_hash, page_count, now_iso()),
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
        # Existing correction history, keyed the same way as the unique
        # constraint. Re-importing must never discard an earlier correction,
        # so histories are merged rather than overwritten.
        prior_history: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
        for row in conn.execute(
            "SELECT page, source_ref, field_name, symbol, correction_history "
            "FROM pdf_records WHERE import_id=?",
            (import_id,),
        ):
            try:
                hist = json.loads(row["correction_history"] or "[]")
            except json.JSONDecodeError:
                hist = []
            key = (row["page"], row["source_ref"], row["field_name"], row["symbol"] or "")
            prior_history[key] = hist

        for r in records:
            value_json = (
                json.dumps(r.value, ensure_ascii=False, default=str)
                if r.value is not None
                else None
            )
            corrected_json = (
                json.dumps(r.corrected_value, ensure_ascii=False, default=str)
                if r.corrected_value is not None
                else None
            )
            key = (r.page, r.source_ref, r.field_name, r.symbol or "")
            merged = list(prior_history.get(key, []))
            for entry in r.correction_history:
                if entry not in merged:
                    merged.append(entry)
            conn.execute(
                "INSERT INTO pdf_records "
                "(import_id, record_type, page, source_ref, raw_text, value, field_name,"
                " symbol, record_date, unit, confidence, review_status, note,"
                " extraction_method, verification_status, original_reading,"
                " corrected_value, correction_history, reconciliation, page_sha256,"
                " verification_note) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(import_id, page, source_ref, field_name, symbol) "
                "DO UPDATE SET "
                "  raw_text=excluded.raw_text, value=excluded.value, "
                "  record_date=excluded.record_date, unit=excluded.unit, "
                "  confidence=excluded.confidence, review_status=excluded.review_status, "
                "  note=excluded.note, "
                "  extraction_method=excluded.extraction_method, "
                "  verification_status=excluded.verification_status, "
                "  original_reading=excluded.original_reading, "
                "  corrected_value=excluded.corrected_value, "
                "  correction_history=excluded.correction_history, "
                "  reconciliation=excluded.reconciliation, "
                "  page_sha256=excluded.page_sha256, "
                "  verification_note=excluded.verification_note",
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
                    r.extraction_method,
                    r.verification_status.value,
                    r.original_reading,
                    corrected_json,
                    json.dumps(merged, ensure_ascii=False),
                    r.reconciliation.value,
                    r.page_sha256,
                    r.verification_note,
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
        # Confidence is ordered: uncertain < low < medium < high.
        # A minimum of X means X and every level above it.
        order = ["uncertain", "low", "medium", "high"]
        allowed = order[order.index(min_confidence.value) :]
        where.append(f"confidence IN ({', '.join('?' for _ in allowed)})")
        params.extend(allowed)

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


def set_review_status(
    record_ids: list[int],
    status: ReviewStatus,
    db_path: Any = None,
) -> dict[str, Any]:
    """Set the review status of specific extracted records.

    This is the human-review step: a record starts `unreviewed` and only after
    a human confirms it does it become usable in analytical output. Only
    `reviewed`, `corrected` and `rejected` are allowed as targets — a record
    cannot be sent back to `unreviewed` to hide that it was once checked.
    """
    if not record_ids:
        raise PdfValidationError("no record ids given")
    if status in (ReviewStatus.UNREVIEWED,):
        raise PdfValidationError("cannot set a record back to 'unreviewed'")

    from megatool.db import get_conn

    placeholders = ", ".join("?" for _ in record_ids)
    with get_conn(db_path) as conn:
        cur = conn.execute(
            f"UPDATE pdf_records SET review_status = ? WHERE id IN ({placeholders})",
            [status.value, *record_ids],
        )
        changed = cur.rowcount or 0
        missing = len(record_ids) - changed
    return {
        "requested": len(record_ids),
        "updated": changed,
        "not_found": missing,
        "status": status.value,
    }


# ----------------------------------------------------------------- OCR first pass
DEFAULT_OCR_DIR = Path("data") / "written_pdf" / "vision_ocr"


def read_vision_page(page: int, ocr_dir: str | Path | None = None) -> dict[str, Any]:
    """Read one page's Apple Vision OCR output with its provenance header.

    Returns ``{"exists", "meta", "text"}``. ``meta`` carries the engine,
    chosen orientation, per-line confidence and the ``OCR_ONLY`` status stamp
    written by ``scripts/run_vision_ocr.py``. Raises ``FileNotFoundError``
    only via ``exists=False`` — a missing page is a normal, reportable state
    for this document, not an error.
    """
    ocr_dir = Path(ocr_dir) if ocr_dir else DEFAULT_OCR_DIR
    path = ocr_dir / f"page_{page:02d}.txt"
    if not path.exists():
        return {"exists": False, "meta": {}, "text": ""}
    raw = path.read_text(encoding="utf-8", errors="replace")
    head, sep, body = raw.partition("\n---\n")
    if not sep:
        body = ""
    meta: dict[str, str] = {}
    for line in head.splitlines():
        if not line.startswith("# "):
            continue
        key, _, val = line[2:].partition(": ")
        meta[key.strip()] = val.strip()
    return {"exists": True, "meta": meta, "text": body.strip("\n")}


def set_verification_status(
    record_ids: list[int],
    status: VerificationStatus,
    note: str,
    db_path: Any = None,
) -> dict[str, Any]:
    """Record *why* a set of records reached a verification status.

    ``note`` is mandatory: a record cannot become ``verified`` (or any other
    status) without a stated reason, so the audit trail cannot be blank.
    """
    if not record_ids:
        raise PdfValidationError("no record ids given")
    if (
        status in (VerificationStatus.VERIFIED, VerificationStatus.CORRECTED_VERIFIED)
        and not note.strip()
    ):
        raise PdfValidationError(
            "a note stating the supporting evidence is required to mark a record verified"
        )

    from megatool.db import get_conn, now_iso

    placeholders = ", ".join("?" for _ in record_ids)
    stamped = f"{now_iso()} {note.strip()}"
    with get_conn(db_path) as conn:
        cur = conn.execute(
            f"UPDATE pdf_records SET verification_status=?, verification_note=? "
            f"WHERE id IN ({placeholders})",
            [status.value, stamped, *record_ids],
        )
        changed = cur.rowcount or 0
        missing = len(record_ids) - changed
    return {
        "requested": len(record_ids),
        "updated": changed,
        "not_found": missing,
        "status": status.value,
        "note": stamped,
    }


def append_correction(
    record_id: int,
    corrected_value: Any,
    reason: str,
    db_path: Any = None,
) -> dict[str, Any]:
    """Correct a record without losing the reading it replaces.

    The original ``raw_text``/``original_reading`` are never touched; the new
    value goes to ``corrected_value`` and a dated entry is appended to
    ``correction_history``. A correction without a stated reason is rejected,
    because "it did not balance" is not a reason to change a handwritten
    figure — only the page image is.
    """
    if not reason.strip():
        raise PdfValidationError("a correction must state its reason")

    import json as _json

    from megatool.db import get_conn, now_iso

    with get_conn(db_path) as conn:
        row = conn.execute(
            "SELECT id, value, corrected_value, correction_history, raw_text "
            "FROM pdf_records WHERE id=?",
            (record_id,),
        ).fetchone()
        if row is None:
            raise PdfValidationError(f"no record with id {record_id}")
        try:
            history = _json.loads(row["correction_history"] or "[]")
        except _json.JSONDecodeError:
            history = []

        def _decode(raw: Any) -> Any:
            """``value``/``corrected_value`` are stored JSON-encoded."""
            if raw is None:
                return None
            with contextlib.suppress(_json.JSONDecodeError, TypeError):
                return _json.loads(raw)
            return raw

        entry = {
            "at": now_iso(),
            "from": _decode(row["corrected_value"])
            if row["corrected_value"]
            else _decode(row["value"]),
            "to": corrected_value,
            "reason": reason.strip(),
            "original_reading": row["raw_text"],
        }
        history.append(entry)
        conn.execute(
            "UPDATE pdf_records SET corrected_value=?, correction_history=?, "
            "verification_status=?, review_status=? WHERE id=?",
            (
                _json.dumps(corrected_value, ensure_ascii=False, default=str),
                _json.dumps(history, ensure_ascii=False),
                VerificationStatus.CORRECTED_VERIFIED.value,
                ReviewStatus.CORRECTED.value,
                record_id,
            ),
        )
    return {"record_id": record_id, "entries": len(history), "entry": entry}


def usable_records(db_path: Any = None) -> list[dict[str, Any]]:
    """Records with enough evidence to be used in financial output.

    OCR-only and unverified readings are deliberately excluded: they are
    searchable and reviewable, but must never reach portfolio accounting or
    current fundamentals.
    """
    import json as _json

    from megatool.db import get_conn

    allowed = sorted(s.value for s in USABLE_VERIFICATION_STATUSES)
    with get_conn(db_path) as conn:
        rows = conn.execute(
            f"SELECT * FROM pdf_records WHERE verification_status IN "
            f"({', '.join('?' for _ in allowed)}) ORDER BY page, source_ref",
            allowed,
        ).fetchall()
    out = []
    for r in rows:
        d = dict(r)
        for key in ("value", "corrected_value"):
            if d.get(key):
                with contextlib.suppress(_json.JSONDecodeError, TypeError):
                    d[key] = _json.loads(d[key])
        with contextlib.suppress(_json.JSONDecodeError, TypeError):
            d["correction_history"] = _json.loads(d.get("correction_history") or "[]")
        out.append(d)
    return out
