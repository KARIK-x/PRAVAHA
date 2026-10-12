# Written Data.pdf — Import Guide

How to get records from the handwritten journal into Mega Tool, and
what guarantees the import provides.

## Important: nothing is auto-imported

The PDF is **private handwritten trading records**. No page is ever
imported automatically. Records enter the system only through the
explicit JSON-import path below, and every record is stored with
`review_status: unreviewed` until a human confirms it.

The original PDF is never modified. It is git-ignored
(`WRITTENdata.pdf` in `.gitignore`) so it is never committed.

## Step 1 — render a page

```python
from megatool.written_pdf import WrittenPdfExtractor

with WrittenPdfExtractor("WRITTENdata.pdf") as ext:
    ext.render_page_to_file(0, "page_01.png", dpi=300)  # 0-indexed
```

## Step 2 — transcribe (by eye or by a future OCR tool)

Automated OCR was attempted with tesseract 5.5.0 on all 52 pages and
**failed on 42 of them** — the document is handwritten, and tesseract
is designed for printed text. Transcription is therefore visual.

When transcribing, preserve the original term and mark uncertainty:

```python
from datetime import date
from megatool.written_pdf import (
    ExtractionConfidence,
    ExtractedRecord,
    RecordType,
    ReviewStatus,
)

record = ExtractedRecord(
    record_type=RecordType.FUNDAMENTAL,
    page=1,  # 1-indexed
    source_ref="Hydro 01 EPS, row 1, col 1",  # where in the page
    raw_text="TPC  46",  # exactly as transcribed
    symbol="TPC",
    field_name="eps",
    value=46.0,
    unit="NPR",
    confidence=ExtractionConfidence.HIGH,  # HIGH/MEDIUM/LOW/UNCERTAIN
    review_status=ReviewStatus.UNREVIEWED,  # always start here
)
```

## Step 3 — save and import

```python
import json

records = [record, ...]
Path("extraction.json").write_text(json.dumps([r.to_dict() for r in records], indent=2))
```

```bash
megatool pdf import extraction.json
megatool pdf summary
megatool pdf list --symbol TPC --limit 20
```

Or over HTTP:

```bash
curl http://127.0.0.1:8710/api/written-pdf/records?symbol=TPC
curl http://127.0.0.1:8710/api/written-pdf/summary
```

## Step 4 — review

Only after a human confirms a record is it safe for analytical use:

- Mark `review_status` to `reviewed` (or `corrected`) and re-import.
- Re-import is **idempotent**: the same `(source_file, content_hash)`
  with the same `(page, source_ref, field_name, symbol)` updates the
  existing row instead of creating a duplicate.
- Query reviewed-only records with `--reviewed` or
  `?reviewed_only=true`.

## What the import validates

Every record passes through validators before storage:

| Check | Function |
| --- | --- |
| NEPSE symbol shape (2-8 alphanumeric) | `validate_nepse_symbol` |
| Price finite, > 0, ≤ 100,000 | `validate_price` |
| Quantity a positive whole number ≤ 10¹² | `validate_quantity` |
| EPS finite, \|value\| ≤ 100,000 (losses allowed) | `validate_eps` |
| Settlement reconciliation: `sell − buy ≈ net` | `validate_settlement_reconciliation` |
| Number parsing with `Rs.` prefixes, `cr`/`L` multipliers, `(x)` negatives | `parse_nepse_number` |

A value that fails validation raises `PdfValidationError` and is
**not** stored — it is never silently coerced into something plausible.

## What the import does NOT do

- It does not verify the value against any external source. Cross-
  validation is a separate, manual step (see
  `docs/WRITTEN_DATA_VALIDATION_REPORT.md`).
- It does not correct OCR or transcription errors.
- It does not import into the portfolio ledger or the trading journal.
  Those tables only accept records entered through their own validated
  routes, so an uncertain PDF value can never silently corrupt
  accounting.

## Reviewing before use

The Research Assistant includes PDF records only when they are
`reviewed`, and always labels them:

> "Personal journal record. Descriptive, not independently verified."

Until a record reaches `reviewed`, it appears in `pdf summary` counts
but never in analytical output.
