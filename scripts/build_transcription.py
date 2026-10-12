"""Build the digital transcription workbook, CSVs and page manifest.

Three inputs, kept strictly separate:

* the **original PDF** (`WRITTENdata.pdf`) — the authority; never modified;
* the **owner's working copy** (`Written_Data_All_52_Pages_Digitized.xlsx`) —
  used only for its page-by-page content-type index and its (weak) OCR text,
  and always treated as a *reference*, never as truth;
* **Apple Vision OCR** over all 52 pages, which is a first pass and nothing more.

Everything produced here is stamped. A page with only machine text is
``ocr_only``. The only figures read by eye are the nine settlements on pages 19,
21 and 23, each checked by subtraction against the page's own boxed net and
circled Paid annotation. **No page is fully transcribed**: ``page_fully_transcribed``
is false for all 52, because every page still holds content that has not been
read — the edge column of boxed figures on page 21, and the transaction tables
on the surrounding pages. Nothing in this script can promote a row to verified
or a page to complete.

Outputs (all git-ignored — this is the owner's private trading record):

    Written_Data_Full_Transcription.xlsx
    data/written_pdf/transcription/transcription_manifest.json
    data/written_pdf/transcription/settlements.csv
    data/written_pdf/transcription/review_queue.csv

Idempotent: re-running overwrites the outputs and creates no duplicates.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
OCR_DIR = ROOT / "data" / "written_pdf" / "vision_ocr"
OUT_DIR = ROOT / "data" / "written_pdf" / "transcription"
WORKBOOK = ROOT / "Written_Data_Full_Transcription.xlsx"
WORKING_COPY = ROOT / "Written_Data_All_52_Pages_Digitized.xlsx"

from megatool.written_pdf import read_vision_page  # noqa: E402
from megatool.written_transcribe import (  # noqa: E402
    ALL_VISUALLY_READ,
    VISUALLY_INSPECTED_PAGES,
    VISUALLY_READ_PAGES,
    extract_settlements,
)

_NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"

#: Content type per page, taken from the owner's working-copy Index sheet.
#: These are *descriptions of the layout*, not verified content.
CONTENT_TYPES: dict[int, str] = {}

#: Where a visual read contradicts the Index, the observed description is kept
#: alongside it rather than replacing it — the Index is a preliminary reference
#: and losing what it said would hide the disagreement.
#:
#: Only pages that have actually been opened appear here. Pages 22, 24, 27, 29
#: and 31 are also labelled "Settlement calculations" by the Index and may well
#: have the same problem, but they have not been looked at and are left alone.
INDEX_CORRECTIONS: dict[int, str] = {
    20: (
        "Buy/sell transaction detail: symbol -> quantity x price per date, with "
        "the day's total in a cloud and a circled settlement label (8C, 8d, 8E). "
        "Index says 'Settlement calculations and payable amounts', which is what "
        "its neighbours are called; observed by eye 2026-10-12. The circled "
        "labels group these dates into exactly the settlements transcribed from "
        "page 19, so this page independently corroborates those block labels."
    ),
}


def _read_working_copy_index() -> None:
    """Pull the page -> content-type hints out of the owner's working copy.

    Read-only, and tolerant: if the working copy is absent or changes shape the
    manifest still builds, with the content type left as ``unknown``.
    """
    if not WORKING_COPY.exists():
        return
    try:
        with zipfile.ZipFile(WORKING_COPY) as z:
            root = ET.fromstring(z.read("xl/worksheets/sheet2.xml"))
    except (KeyError, ET.ParseError, zipfile.BadZipFile):
        return
    sheet_data = root.find(f"{_NS}sheetData")
    if sheet_data is None:
        return
    for row in list(sheet_data)[1:]:  # skip the header row
        cells: list[str] = []
        for c in row:
            if c.get("t") == "inlineStr":
                node = c.find(f"{_NS}is")
                cells.append(
                    "".join(t.text or "" for t in node.iter(f"{_NS}t")) if node is not None else ""
                )
            else:
                node = c.find(f"{_NS}v")
                cells.append((node.text or "") if node is not None else "")
        if len(cells) >= 2 and cells[0].strip().isdigit():
            CONTENT_TYPES[int(cells[0])] = cells[1].strip()


def _ocr_status(page: int) -> dict[str, Any]:
    """Classify one page's machine text honestly."""
    page_data = read_vision_page(page, OCR_DIR)
    if not page_data["exists"]:
        return {
            "ocr_status": "not_run",
            "chars": 0,
            "orientation": "",
            "confidence": 0.0,
            "text": "",
        }
    text = page_data["text"]
    meta = page_data["meta"]
    stripped = re.sub(r"\s", "", text)
    if not stripped:
        status = "empty"
    elif len(stripped) < 60 or len(set(stripped)) < 8:
        # Very short or near-repetitive output is what Vision returns when it
        # has found nothing legible; calling it "text" would overstate it.
        status = "gibberish"
    else:
        status = "text"
    return {
        "ocr_status": status,
        "chars": len(text),
        "orientation": meta.get("orientation", ""),
        "confidence": float(meta.get("mean_confidence", 0.0) or 0.0),
        "text": text,
    }


def build_manifest() -> list[dict[str, Any]]:
    """One entry per page: what it is, what OCR found, what is actually verified.

    Nothing here can promote a page. A page counts as visually read only if a
    settlement has been taken off its image, and even then it is *not* marked
    complete — every page carries content beyond its settlement blocks (an edge
    column of boxed figures, a transaction table) that has not been transcribed.
    ``page_fully_transcribed`` is therefore false for all 52 pages today, and
    the field exists so that claiming otherwise later has to be deliberate.
    """
    _read_working_copy_index()
    manifest: list[dict[str, Any]] = []
    for page in range(1, 53):
        ocr = _ocr_status(page)
        blocks = extract_settlements(page, ocr["text"])
        read_by_eye = [d for d in ALL_VISUALLY_READ if d["page"] == page]
        reconciled = [b for b in blocks if b.reconciliation.value == "reconciled"]
        flagged = [b for b in blocks if b.reconciliation.value == "discrepancy"]
        unplaced = sum(len(b.unplaced) for b in blocks)
        inferred = sum(1 for b in blocks if b.label_source == "position")

        if read_by_eye:
            transcription = "settlements_transcribed"
            verification = "partial"
        elif page in VISUALLY_INSPECTED_PAGES:
            # Opened and identified, but nothing taken off it: an inspection is
            # not a transcription and must not read like one.
            transcription = "inspected_not_transcribed"
            verification = "inspected"
        elif ocr["ocr_status"] == "text":
            transcription = "partial"
            verification = "ocr_only"
        else:
            transcription = "none"
            verification = "not_started"

        manifest.append(
            {
                "page": page,
                "content_type": CONTENT_TYPES.get(page, "unknown"),
                "content_type_observed": INDEX_CORRECTIONS.get(page),
                "visually_inspected": page in VISUALLY_INSPECTED_PAGES,
                "ocr_status": ocr["ocr_status"],
                "ocr_chars": ocr["chars"],
                "ocr_orientation": ocr["orientation"],
                "ocr_mean_confidence": ocr["confidence"],
                "transcription_status": transcription,
                "verification_status": verification,
                "page_fully_transcribed": False,  # see the docstring above
                "records_extracted": len(blocks),
                "records_verified": len(read_by_eye),
                "settlements_reconciled": len(reconciled),
                "settlements_flagged": len(flagged),
                "settlement_labels_inferred": inferred,
                "figures_unplaced": unplaced,
                # Nothing is complete, so every page still needs work — including
                # 19/21/23, whose settlement blocks are read but whose remaining
                # content is not.
                "needs_review": True,
                "work_remaining": (
                    "transcribe the rest of the page: settlement blocks are read, "
                    "edge figures and any table are not"
                    if read_by_eye
                    else "page opened and identified only — no record transcribed from it yet"
                    if transcription == "inspected_not_transcribed"
                    else "visual transcription of the whole page"
                    if transcription == "none"
                    else "review flagged rows, then transcribe the page by eye"
                ),
            }
        )
    return manifest


def write_csvs(manifest: list[dict[str, Any]]) -> dict[str, int]:
    """Export the structured slices. Notes and prose are deliberately not forced
    into a CSV — they live on the page sheets in the workbook instead."""
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    counts: dict[str, int] = {}

    # The three pages were recorded at different times, so their records do not
    # share a key set. Write the union rather than whichever shape came first.
    keys: list[str] = []
    for d in ALL_VISUALLY_READ:
        for k in d:
            if k not in keys:
                keys.append(k)
    settlements = [{k: d.get(k, "") for k in keys} for d in ALL_VISUALLY_READ]
    with (OUT_DIR / "settlements.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=keys)
        w.writeheader()
        w.writerows(settlements)
    counts["settlements.csv"] = len(settlements)

    queue = [
        {
            "page": m["page"],
            "content_type": m["content_type"],
            "ocr_status": m["ocr_status"],
            "verification_status": m["verification_status"],
            "page_fully_transcribed": m["page_fully_transcribed"],
            "records_verified": m["records_verified"],
            "settlements_flagged": m["settlements_flagged"],
            "work_remaining": m["work_remaining"],
        }
        for m in manifest
        if m["needs_review"]
    ]
    with (OUT_DIR / "review_queue.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(queue[0]))
        w.writeheader()
        w.writerows(queue)
    counts["review_queue.csv"] = len(queue)
    return counts


def write_workbook(manifest: list[dict[str, Any]]) -> int:
    """One sheet per page plus Summary / Manifest / Settlements.

    Each page sheet carries the provenance header, the machine text, and the
    page's verification state, so a reader can never mistake OCR for a
    transcription.
    """
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Font
    except ImportError:
        print("openpyxl is not installed; skipping the workbook.", file=sys.stderr)
        print("  install it with:  uv sync --group xlsx", file=sys.stderr)
        return 0

    wb = Workbook()
    bold = Font(bold=True)
    wrap = Alignment(vertical="top", wrap_text=True)

    # ---- Summary ----------------------------------------------------------
    ws = wb.active
    ws.title = "Summary"
    pages_read = sorted(VISUALLY_READ_PAGES)
    summary = [
        ("WRITTEN DATA — FULL TRANSCRIPTION", ""),
        ("", ""),
        ("Source document", "WRITTENdata.pdf (52 pages, authoritative)"),
        (
            "Working reference",
            "Written_Data_All_52_Pages_Digitized.xlsx (preliminary, NOT verified)",
        ),
        ("First-pass OCR", "Apple Vision, best of 4 orientations, all 52 pages"),
        ("Generated by", "scripts/build_transcription.py"),
        ("", ""),
        ("Pages processed (OCR)", 52),
        ("Pages with machine text", sum(1 for m in manifest if m["ocr_status"] == "text")),
        ("Pages with no usable OCR", sum(1 for m in manifest if m["ocr_status"] != "text")),
        (
            "Pages opened and inspected by eye",
            f"{len(VISUALLY_INSPECTED_PAGES)} of 52 — pages "
            f"{', '.join(str(p) for p in sorted(VISUALLY_INSPECTED_PAGES))}",
        ),
        (
            "Pages with a settlement read by eye",
            f"{len(pages_read)} of 52 — pages {', '.join(str(p) for p in pages_read)}",
        ),
        ("Settlements read by eye", len(ALL_VISUALLY_READ)),
        ("Pages FULLY transcribed", 0),
        ("Pages still needing review", sum(1 for m in manifest if m["needs_review"])),
        ("", ""),
        ("PROGRESS WARNING", ""),
        ("", "No page is fully transcribed. Pages 19, 21 and 23 have their"),
        ("", "settlement blocks read off the image and checked, but each also"),
        ("", "carries content that has not been transcribed — an edge column of"),
        ("", "boxed figures on page 21, and the transaction tables on the"),
        ("", "surrounding pages. Page 20 was opened and identified but nothing"),
        ("", "was transcribed from it. 'page_fully_transcribed' is false for all 52."),
        ("", ""),
        ("ACCURACY WARNING", ""),
        ("", "Every row not listed as read-by-eye is machine OCR of handwriting and"),
        ("", "is WRONG often enough to matter. Numeric recall measured at 94.6% on"),
        ("", "the 5 benchmarked pages; dense transaction pages are worse (page 18:"),
        ("", "84%). Do not use any unverified figure for accounting, portfolio or"),
        ("", "fundamentals. Review against the page image first."),
        ("", ""),
        ("VERIFIED SETTLEMENTS", "Pages 19 (8C, 8D, 8E), 21 (9A-9D), 23 (9E, 9F)."),
        ("", "Each was read from raw_pages/page_NN.png and then confirmed:"),
        ("", "|buy - sell| = net exactly, matching the boxed Net Payable and the"),
        ("", "circled Paid/Received annotation."),
        ("", ""),
        ("KNOWN SOURCE DEFECTS", "Recorded, never corrected:"),
        ("", "page 19, 8C — sell components sum to 226,360.28 but the written"),
        ("", "total is 226,359.28 (1.00). The page computes its net from the"),
        ("", "written total, so that part is exact."),
        ("", "page 19, 8C — received 58,203.42 against a net receivable of"),
        ("", "58,211.45 (8.03). The page states both and explains neither."),
        ("", "page 19, 8E — the author struck 148,503.38 out and wrote"),
        ("", "148,478.38; both readings are kept."),
        ("", ""),
        ("WITHDRAWN VALUE", "186,129.76 — an earlier audit 'corrected' settlement 9A's"),
        ("", "buy to this figure because it balanced. It is not on the page and"),
        ("", "must never be imported. See KNOWN_BUGS.md B-02."),
    ]
    for r, (a, b) in enumerate(summary, start=1):
        ws.cell(r, 1, a).font = bold
        ws.cell(r, 2, b).alignment = wrap
    ws.column_dimensions["A"].width = 32
    ws.column_dimensions["B"].width = 96

    # ---- Manifest ---------------------------------------------------------
    ws = wb.create_sheet("Manifest")
    cols = [
        "page",
        "content_type",
        "content_type_observed",
        "ocr_status",
        "ocr_chars",
        "ocr_orientation",
        "ocr_mean_confidence",
        "visually_inspected",
        "transcription_status",
        "verification_status",
        "page_fully_transcribed",
        "records_extracted",
        "records_verified",
        "settlements_reconciled",
        "settlements_flagged",
        "settlement_labels_inferred",
        "figures_unplaced",
        "work_remaining",
    ]
    ws.append(cols)
    for c in ws[1]:
        c.font = bold
    for m in manifest:
        ws.append([m[c] for c in cols])
    for i in range(1, len(cols) + 1):
        ws.column_dimensions[chr(64 + i) if i <= 26 else "A"].width = 18
    ws.freeze_panes = "A2"

    # ---- Settlements ------------------------------------------------------
    # Every visually read settlement shares one record shape, so the sheet is a
    # straight projection. Direction matters: 8C is a receivable, so its net is
    # sell − buy while every other entry here is buy − sell, and the check is
    # therefore on |buy − sell|.
    ws = wb.create_sheet("Settlements")
    ws.append([f"VISUALLY READ — pages {', '.join(str(p) for p in sorted(VISUALLY_READ_PAGES))}"])
    ws["A1"].font = bold
    fields = [
        "label",
        "page",
        "dates",
        "buy_total",
        "sell_total",
        "net",
        "direction",
        "settled",
        "settled_on",
        "source_discrepancies",
        "superseded_readings",
        "ocr_notes",
        "evidence",
    ]
    ws.append([])
    ws.append(fields)
    for c in ws[3]:
        c.font = bold

    def _row(d: dict[str, Any]) -> list[Any]:
        # Direct indexing is deliberate: a record with a different shape fails
        # loudly here instead of being written out as blanks.
        return [
            d["label"],
            d["page"],
            d["dates"],
            d["buy_total"],
            d["sell_total"],
            d["net"],
            d["direction"],
            d["settled"],
            d["settled_on"],
            "; ".join(d["source_discrepancies"]),
            "; ".join(
                f"{s['field']}: {s['original_reading']} -> {s['corrected_value']}"
                for s in d["superseded_readings"]
            ),
            "; ".join(d["ocr_notes"]),
            d["evidence"],
        ]

    rows_data = [_row(d) for d in ALL_VISUALLY_READ]
    for row in rows_data:
        ws.append(row)

    # Columns: A label, B page, C dates, D buy, E sell, F net, G dir,
    #          H settled, I settled_on, J discrepancies, K superseded,
    #          L ocr_notes, M evidence
    ws.cell(3, 14, "|buy - sell|").font = bold
    ws.cell(3, 15, "check").font = bold
    for i in range(len(ALL_VISUALLY_READ)):
        r = 4 + i
        buy, sell, net = ws.cell(r, 4).value, ws.cell(r, 5).value, ws.cell(r, 6).value
        if not all(isinstance(v, (int, float)) for v in (buy, sell, net)):
            ws.cell(r, 14, "n/a")
            ws.cell(r, 15, "n/a")
            continue
        diff = round(abs(buy - sell), 2)
        ws.cell(r, 14, diff)
        ws.cell(r, 15, "OK" if diff == round(net, 2) else "MISMATCH")
    ws.column_dimensions["J"].width = 70
    ws.column_dimensions["K"].width = 45
    ws.column_dimensions["L"].width = 60
    ws.column_dimensions["M"].width = 90

    # ---- One sheet per page ----------------------------------------------
    for m in manifest:
        page = m["page"]
        ocr = _ocr_status(page)
        ws = wb.create_sheet(f"Page {page:02d}")
        rows = [
            ("PDF page", page),
            ("Source", "WRITTENdata.pdf"),
            ("Page image", f"data/written_pdf/raw_pages/page_{page:02d}.png"),
            ("Content type (from working copy)", m["content_type"]),
            ("OCR engine", "Apple Vision, best of 4 orientations"),
            ("OCR orientation chosen", m["ocr_orientation"]),
            ("OCR mean confidence", m["ocr_mean_confidence"]),
            ("OCR status", m["ocr_status"]),
            ("Transcription status", m["transcription_status"]),
            ("Verification status", m["verification_status"]),
            ("Work remaining", m["work_remaining"]),
        ]
        for r, (k, v) in enumerate(rows, start=1):
            ws.cell(r, 1, k).font = bold
            ws.cell(r, 2, v).alignment = wrap
        ws.cell(len(rows) + 2, 1, "MACHINE OCR — NOT A VERIFIED TRANSCRIPTION").font = bold
        ws.cell(len(rows) + 3, 1, ocr["text"]).alignment = wrap
        ws.column_dimensions["A"].width = 34
        ws.column_dimensions["B"].width = 110

    wb.save(WORKBOOK)
    return len(manifest)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-workbook", action="store_true", help="skip the xlsx output")
    args = ap.parse_args()

    manifest = build_manifest()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "transcription_manifest.json").write_text(
        json.dumps(manifest, indent=2), encoding="utf-8"
    )
    counts = write_csvs(manifest)

    print(f"manifest: {len(manifest)} pages -> {OUT_DIR / 'transcription_manifest.json'}")
    for name, n in counts.items():
        print(f"csv: {n:>4} rows -> {OUT_DIR / name}")
    if not args.no_workbook:
        n = write_workbook(manifest)
        if n:
            print(f"workbook: {n} page sheets -> {WORKBOOK}")

    read_pages = sorted(VISUALLY_READ_PAGES)
    inspected = sorted(VISUALLY_INSPECTED_PAGES)
    text = [m for m in manifest if m["ocr_status"] == "text"]
    verified_records = sum(m["records_verified"] for m in manifest)
    fully = sum(1 for m in manifest if m["page_fully_transcribed"])
    print()
    print(f"  pages with machine text     : {len(text)}/52")
    print(f"  pages opened and inspected  : {len(inspected)}/52 -> {inspected}")
    print(f"  pages with a settlement read: {len(read_pages)}/52 -> {read_pages}")
    print(f"  settlements read by eye     : {verified_records}")
    print(f"  pages FULLY transcribed     : {fully}/52")
    print(f"  pages needing review        : {sum(1 for m in manifest if m['needs_review'])}/52")
    return 0


if __name__ == "__main__":
    sys.exit(main())
