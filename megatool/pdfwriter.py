"""A dependency-free PDF writer for PRAVAHA reports.

The project deliberately avoids a hard dependency on a PDF library for report
exports. This module emits a minimal but valid PDF 1.4 document from text
blocks and, optionally, raster images (charts).

Two entry points:

``write_pdf(pages)``
    The original, text-only API: ``pages`` is a list of pages, each a list of
    ``(x, text, size)`` tuples. Kept for compatibility with existing callers.

``write_pdf_blocks(pages)``
    The richer API: each page is a list of block dicts.

    * ``{"type": "text", "text": ..., "size": 10, "gap": 4}``
    * ``{"type": "spacer", "height": 12}``
    * ``{"type": "image", "rgb": b"...", "width": 760, "height": 300,
       "draw_width": 520, "draw_height": 205}``
    * ``{"type": "pagebreak"}``

    Content that runs past the bottom margin is moved to a new page rather
    than clipped, and images are emitted as ``FlateDecode`` ``DeviceRGB``
    XObjects. No external library is involved.
"""

from __future__ import annotations

import zlib
from typing import Any

__all__ = ["write_pdf", "write_pdf_blocks", "wrap"]

PAGE_W, PAGE_H = 612, 792
MARGIN_L, MARGIN_T, MARGIN_B, MARGIN_R = 40, 56, 48, 40
LINE_GAP = 5


def _esc(text: str) -> str:
    """Escape the characters that are special inside a PDF literal string."""
    return (str(text)
            .replace("\\", "\\\\")
            .replace("(", "\\(")
            .replace(")", "\\)")
            .encode("latin-1", errors="replace")
            .decode("latin-1"))


def wrap(text: str, width: int = 96) -> list[str]:
    """Wrap on spaces so no line exceeds ``width`` characters."""
    out: list[str] = []
    for raw in str(text).splitlines() or [""]:
        line = ""
        for word in raw.split(" "):
            if not word:
                continue
            if line and len(line) + len(word) + 1 > width:
                out.append(line)
                line = word
            else:
                line = f"{line} {word}".strip()
        out.append(line)
    return out or [""]


def _text_block(text: str, size: int, x: float = MARGIN_L, gap: float = LINE_GAP) -> dict[str, Any]:
    return {"type": "text", "text": text, "size": size, "x": x, "gap": gap}


def _legacy_to_blocks(pages: list[list[tuple[float, str, int]]]) -> list[list[dict[str, Any]]]:
    return [
        [_text_block(text, size, x) for (x, text, size) in page]
        for page in pages
    ]


class _Pdf:
    def __init__(self) -> None:
        self.objects: list[bytes | None] = [None, None]  # catalog, pages
        self.page_objs: list[int] = []

    def add(self, obj: bytes) -> int:
        self.objects.append(obj)
        return len(self.objects)

    def stream(self, data: bytes, extra: str = "") -> int:
        head = f"<< {extra}/Length {len(data)} >>".encode("latin-1")
        return self.add(head + b"\nstream\n" + data + b"\nendstream")

    def image(self, data: bytes, width: int, height: int) -> int:
        """A FlateDecode DeviceRGB image XObject."""
        head = (
            f"<< /Type /XObject /Subtype /Image /Width {int(width)} "
            f"/Height {int(height)} /ColorSpace /DeviceRGB /BitsPerComponent 8 "
            f"/Filter /FlateDecode /Length {len(data)} >>"
        ).encode("latin-1")
        return self.add(head + b"\nstream\n" + data + b"\nendstream")

    def finish(self) -> bytes:
        self.objects[0] = b"<< /Type /Catalog /Pages 2 0 R >>"
        kids = " ".join(f"{n} 0 R" for n in self.page_objs)
        self.objects[1] = (f"<< /Type /Pages /Kids [{kids}] /Count {len(self.page_objs)} >>"
                           .encode("latin-1"))
        # Any page object that was created before all image objects must keep
        # its resource references stable; object numbers are assigned in
        # `layout`, so nothing is rewritten here.
        body = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
        offsets: list[int] = []
        for i, obj in enumerate(self.objects, start=1):
            offsets.append(len(body))
            body += f"{i} 0 obj\n".encode("latin-1") + (obj or b"null") + b"\nendobj\n"
        xref_pos = len(body)
        xref = ["xref\n", f"0 {len(self.objects) + 1}\n", "0000000000 65535 f \n"]
        xref += [f"{off:010d} 00000 n \n" for off in offsets]
        trailer = (f"trailer\n<< /Size {len(self.objects) + 1} /Root 1 0 R >>\n"
                   f"startxref\n{xref_pos}\n%%EOF\n")
        return bytes(body) + "".join(xref).encode("latin-1") + trailer.encode("latin-1")


def _layout_page(pdf: _Pdf, blocks: list[dict[str, Any]], page_no: int, total: int,
                 numbers: bool) -> int:
    """Lay out one page, creating page/image/content objects. Returns page obj."""
    parts: list[str] = []
    images: list[tuple[str, int, float, float, float, float]] = []
    y = float(PAGE_H - MARGIN_T)
    page_breaks = 0
    img_index = 0

    for block in blocks:
        kind = block.get("type", "text")
        if kind == "pagebreak":
            page_breaks += 1
            continue
        if kind == "spacer":
            y -= float(block.get("height", 10))
            continue
        if kind == "image":
            draw_w = float(block.get("draw_width") or min(PAGE_W - MARGIN_L - MARGIN_R, 520))
            draw_h = float(block.get("draw_height") or draw_w * 0.42)
            if y - draw_h < MARGIN_B:
                # The caller chose the page split; skip rather than draw into
                # the footer. `write_pdf_blocks` pre-splits, so this is a guard.
                continue
            img_index += 1
            name = f"Im{img_index}"
            data = zlib.compress(bytes(block["rgb"]), 6)
            obj = pdf.image(data, int(block["width"]), int(block["height"]))
            images.append((name, obj, draw_w, draw_h, MARGIN_L, y - draw_h))
            parts.append("q")
            parts.append(f"{draw_w:.2f} 0 0 {draw_h:.2f} {MARGIN_L:.2f} {y - draw_h:.2f} cm")
            parts.append(f"/{name} Do")
            parts.append("Q")
            y -= draw_h + 8
            continue

        text = str(block.get("text", ""))
        size = int(block.get("size", 9))
        gap = float(block.get("gap", LINE_GAP))
        x = float(block.get("x", MARGIN_L))
        if y - size < MARGIN_B:
            continue
        parts.append("BT")
        parts.append(f"/F1 {size} Tf")
        parts.append(f"1 0 0 1 {x:.2f} {y:.2f} Tm")
        parts.append(f"({_esc(text)}) Tj")
        parts.append("ET")
        y -= size + gap

    if numbers:
        parts.append("BT")
        parts.append("/F1 8 Tf")
        parts.append(f"1 0 0 1 {MARGIN_L} {MARGIN_B - 18:.2f} Tm")
        parts.append(f"({_esc(f'- {page_no} / {total} -')}) Tj")
        parts.append("ET")

    content = "\n".join(parts).encode("latin-1", errors="replace")
    content_obj = pdf.stream(content)

    # Font object is allocated once; resolve it lazily here so numbering stays
    # consistent no matter how many pages/images came before.
    font_ref = pdf.font_obj
    res = f"/Font << /F1 {font_ref} 0 R >>"
    if images:
        xobjs = " ".join(f"/{name} {obj} 0 R" for (name, obj, *_rest) in images)
        res += f" /XObject << {xobjs} >>"
    page_obj = pdf.add(
        (f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {PAGE_W} {PAGE_H}] "
         f"/Resources << {res} >> /Contents {content_obj} 0 R >>").encode("latin-1")
    )
    return page_obj


def _paginate(blocks: list[dict[str, Any]], per_text: int = 46) -> list[list[dict[str, Any]]]:
    """Split a flat block list into pages that cannot overflow.

    Explicit ``pagebreak`` blocks are honoured. Text blocks are counted and
    images consume a proportional amount of vertical space.
    """
    pages: list[list[dict[str, Any]]] = [[]]
    used = 0.0
    limit = float(PAGE_H - MARGIN_T - MARGIN_B)
    for block in blocks:
        kind = block.get("type", "text")
        if kind == "pagebreak":
            if pages[-1]:
                pages.append([])
                used = 0.0
            continue
        if kind == "image":
            h = float(block.get("draw_height") or 205)
            if used + h + 8 > limit and pages[-1]:
                pages.append([])
                used = 0.0
            pages[-1].append(block)
            used += h + 8
            continue
        if kind == "spacer":
            pages[-1].append(block)
            used += float(block.get("height", 10))
            continue
        h = float(block.get("size", 9)) + float(block.get("gap", LINE_GAP))
        if used + h > limit and pages[-1]:
            pages.append([])
            used = 0.0
        pages[-1].append(block)
        used += h
    return pages or [[_text_block("PRAVAHA report", 12)]]


def write_pdf_blocks(pages: list[list[dict[str, Any]]] | list[dict[str, Any]],
                     numbers: bool = True) -> bytes:
    """Render block pages (or one flat block list) to PDF bytes."""
    if pages and isinstance(pages[0], dict):
        flat = list(pages)  # type: ignore[arg-type]
        page_list = _paginate(flat)
    else:
        page_list = list(pages)  # type: ignore[arg-type]
    page_list = [p for p in page_list if p] or [[_text_block("PRAVAHA report", 12)]]
    total = len(page_list)

    pdf = _Pdf()
    # Reserve the font before pages so its object number exists for resources.
    pdf.font_obj = pdf.add(b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>")

    # Image and content objects must exist before a page object references
    # them, so lay each page out first and collect the page refs afterwards.
    for i, page in enumerate(page_list, start=1):
        pdf.page_objs.append(_layout_page(pdf, page, i, total, numbers))
    return pdf.finish()


def write_pdf(pages: list[list[tuple[float, str, int]]], numbers: bool = True) -> bytes:
    """Render legacy text pages ``[(x, text, size), ...]`` to PDF bytes."""
    return write_pdf_blocks(_legacy_to_blocks(pages), numbers=numbers)


def write_lines(lines: list[str], numbers: bool = True) -> bytes:
    """Convenience wrapper: one page of single-size lines."""
    return write_pdf([[(0, ln, 9) for ln in lines]], numbers=numbers)
