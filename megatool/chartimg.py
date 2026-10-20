"""Tiny, dependency-free chart rasteriser for PDF/XLSX research reports.

The project deliberately avoids pulling in a plotting library. This module
draws an RGB raster with integer arithmetic (Bresenham lines, filled
rectangles) and encodes it either as:

* a PNG (stdlib ``zlib`` + ``struct``), for embedding in XLSX; or
* a PDF image XObject stream (``FlateDecode``, ``DeviceRGB``), for the
  dependency-free PDF writer.

It is intentionally small: line and bar charts over a single numeric series
(plus an optional second overlay series), with axes, a light grid and a title.
That is enough for a research report and it cannot misrepresent data — every
point drawn is a value supplied by the caller, in order.
"""

from __future__ import annotations

import struct
import zlib
from typing import Any

__all__ = ["rgb_line_chart", "rgb_bar_chart", "png_bytes", "pdf_image_stream", "chart_from_section"]

# Palette (PRAVAHA dark-on-light print palette).
BG = (255, 255, 255)
GRID = (226, 232, 230)
AXIS = (120, 134, 130)
INK = (18, 38, 34)
SERIES = (16, 122, 96)
OVERLAY = (196, 92, 40)


class _Canvas:
    def __init__(self, width: int, height: int) -> None:
        self.w = max(1, int(width))
        self.h = max(1, int(height))
        self.buf = bytearray(BG * (self.w * self.h))

    def pixel(self, x: int, y: int, color: tuple[int, int, int]) -> None:
        if 0 <= x < self.w and 0 <= y < self.h:
            i = (y * self.w + x) * 3
            self.buf[i:i + 3] = bytes(color)

    def rect(self, x0: int, y0: int, x1: int, y1: int, color: tuple[int, int, int]) -> None:
        x0, x1 = sorted((max(0, x0), min(self.w - 1, x1)))
        y0, y1 = sorted((max(0, y0), min(self.h - 1, y1)))
        row = bytes(color) * (x1 - x0 + 1)
        for y in range(y0, y1 + 1):
            i = (y * self.w + x0) * 3
            self.buf[i:i + len(row)] = row

    def line(self, x0: int, y0: int, x1: int, y1: int, color: tuple[int, int, int]) -> None:
        dx, dy = abs(x1 - x0), -abs(y1 - y0)
        sx = 1 if x0 < x1 else -1
        sy = 1 if y0 < y1 else -1
        err = dx + dy
        while True:
            self.pixel(x0, y0, color)
            if x0 == x1 and y0 == y1:
                break
            e2 = 2 * err
            if e2 >= dy:
                err += dy
                x0 += sx
            if e2 <= dx:
                err += dx
                y0 += sy

    def vline(self, x: int, y0: int, y1: int, color: tuple[int, int, int]) -> None:
        self.rect(x, y0, x, y1, color)

    def hline(self, x0: int, x1: int, y: int, color: tuple[int, int, int]) -> None:
        self.rect(x0, y, x1, y, color)


def _finite(values: Any) -> list[float | None]:
    out: list[float | None] = []
    for v in values or []:
        try:
            f = float(v)
        except (TypeError, ValueError):
            out.append(None)
            continue
        out.append(f if f == f and abs(f) != float("inf") else None)
    return out


def _frame(width: int = 760, height: int = 300) -> tuple[_Canvas, int, int, int, int]:
    c = _Canvas(width, height)
    left, right = 56, width - 14
    top, bottom = 16, height - 30
    return c, left, right, top, bottom


def _axes(c: _Canvas, left: int, right: int, top: int, bottom: int, lo: float, hi: float) -> None:
    c.hline(left, right, bottom, AXIS)
    c.vline(left, top, bottom, AXIS)
    for i in range(5):
        y = int(bottom - (bottom - top) * i / 4)
        c.hline(left, right, y, GRID)
        label = lo + (hi - lo) * i / 4
        _text(c, 4, y - 4, f"{label:.2f}", scale=1)


# 5x7 bitmap font for tiny axis labels (digits, dot, minus).
_GLYPHS = {
    "0": ["111", "101", "101", "101", "111"],
    "1": ["010", "110", "010", "010", "111"],
    "2": ["111", "001", "111", "100", "111"],
    "3": ["111", "001", "111", "001", "111"],
    "4": ["101", "101", "111", "001", "001"],
    "5": ["111", "100", "111", "001", "111"],
    "6": ["111", "100", "111", "101", "111"],
    "7": ["111", "001", "010", "010", "010"],
    "8": ["111", "101", "111", "101", "111"],
    "9": ["111", "101", "111", "001", "111"],
    ".": ["000", "000", "000", "000", "010"],
    "-": ["000", "000", "111", "000", "000"],
    "K": ["101", "110", "100", "110", "101"],
    "M": ["101", "111", "111", "101", "101"],
}


def _text(c: _Canvas, x: int, y: int, text: str, scale: int = 1, color: tuple[int, int, int] = AXIS) -> None:
    cx = x
    for ch in str(text):
        rows = _GLYPHS.get(ch)
        if rows:
            for ry, row in enumerate(rows):
                for rx, bit in enumerate(row):
                    if bit == "1":
                        c.rect(cx + rx * scale, y + ry * scale,
                               cx + rx * scale + scale - 1, y + ry * scale + scale - 1, color)
        cx += 4 * scale


def _map_points(xs: int, left: int, right: int, top: int, bottom: int,
                values: list[float | None], lo: float, hi: float) -> list[tuple[int, int] | None]:
    span = (hi - lo) or 1.0
    pts: list[tuple[int, int] | None] = []
    n = max(1, xs - 1)
    for i, v in enumerate(values):
        if v is None:
            pts.append(None)
            continue
        x = int(left + (right - left) * i / n)
        y = int(bottom - (bottom - top) * (v - lo) / span)
        pts.append((x, y))
    return pts


def rgb_line_chart(series: list[float], *, overlay: list[float] | None = None,
                   width: int = 760, height: int = 300, zero_line: bool = False) -> bytes:
    """Render a line chart and return raw RGB bytes (row-major, 3 bytes/pixel)."""
    c, left, right, top, bottom = _frame(width, height)
    vals = _finite(series)
    ov = _finite(overlay) if overlay else []
    usable = [v for v in vals if v is not None] + [v for v in ov if v is not None]
    if not usable:
        return bytes(c.buf)
    lo, hi = min(usable), max(usable)
    if zero_line:
        lo, hi = min(lo, 0.0), max(hi, 0.0)
    if hi == lo:
        pad = abs(hi) * 0.05 or 1.0
        lo, hi = lo - pad, hi + pad
    else:
        pad = (hi - lo) * 0.08
        lo, hi = lo - pad, hi + pad
    _axes(c, left, right, top, bottom, lo, hi)
    if zero_line and lo < 0 < hi:
        zy = int(bottom - (bottom - top) * (0 - lo) / (hi - lo))
        c.hline(left, right, zy, AXIS)

    def draw(vals_in: list[float | None], color: tuple[int, int, int]) -> None:
        pts = _map_points(len(vals_in), left, right, top, bottom, vals_in, lo, hi)
        prev: tuple[int, int] | None = None
        for p in pts:
            if p is None:
                prev = None
                continue
            if prev is not None:
                c.line(prev[0], prev[1], p[0], p[1], color)
            prev = p

    draw(vals, SERIES)
    if ov:
        draw(ov, OVERLAY)
    return bytes(c.buf)


def rgb_bar_chart(values: list[float], *, width: int = 760, height: int = 300) -> bytes:
    """Render a bar chart and return raw RGB bytes."""
    c, left, right, top, bottom = _frame(width, height)
    vals = _finite(values)
    usable = [v for v in vals if v is not None]
    if not usable:
        return bytes(c.buf)
    lo, hi = min(0.0, min(usable)), max(0.0, max(usable))
    if hi == lo:
        hi = lo + 1.0
    pad = (hi - lo) * 0.08
    lo, hi = lo - pad, hi + pad
    _axes(c, left, right, top, bottom, lo, hi)
    zero_y = int(bottom - (bottom - top) * (0 - lo) / (hi - lo))
    n = max(1, len(vals))
    slot = (right - left) / n
    bar_w = max(1, int(slot * 0.62))
    for i, v in enumerate(vals):
        if v is None:
            continue
        x = int(left + slot * i + (slot - bar_w) / 2)
        y = int(bottom - (bottom - top) * (v - lo) / (hi - lo))
        c.rect(x, min(y, zero_y), x + bar_w - 1, max(y, zero_y), SERIES)
    return bytes(c.buf)


def png_bytes(rgb: bytes, width: int, height: int) -> bytes:
    """Encode raw RGB bytes as a PNG using only the standard library."""
    w, h = int(width), int(height)
    raw = bytearray()
    stride = w * 3
    for y in range(h):
        raw.append(0)
        raw.extend(rgb[y * stride:(y + 1) * stride])

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (struct.pack(">I", len(data)) + tag + data
                + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))

    ihdr = struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(bytes(raw), 6)) + chunk(b"IEND", b""))


def pdf_image_stream(rgb: bytes, width: int, height: int) -> tuple[bytes, bytes]:
    """Return ``(stream, dict)`` for a PDF image XObject with FlateDecode."""
    data = zlib.compress(bytes(rgb), 6)
    info = (f"<< /Type /XObject /Subtype /Image /Width {int(width)} "
            f"/Height {int(height)} /ColorSpace /DeviceRGB /BitsPerComponent 8 "
            f"/Filter /FlateDecode /Length {len(data)} >>").encode("latin-1")
    return data, info


def _numeric_rows(section: dict[str, Any]) -> list[float]:
    """Pull the numeric column out of a chart section's declared series."""
    chart = section.get("chart") or {}
    ys = _finite(chart.get("y"))
    if ys:
        return [v if v is not None else float("nan") for v in ys]
    # Fall back to the second column of `rows` (the first is usually a date).
    out: list[float] = []
    for row in section.get("rows") or []:
        if len(row) >= 2:
            try:
                out.append(float(row[1]))
            except (TypeError, ValueError):
                continue
    return out


def chart_from_section(section: dict[str, Any], *, width: int = 760, height: int = 300) -> tuple[bytes, int, int] | None:
    """Render any chart-shaped report section. Returns ``(rgb, w, h)`` or None."""
    if not isinstance(section, dict) or not section.get("available", False):
        return None
    kind = str((section.get("chart") or {}).get("kind") or "").lower()
    values = _numeric_rows(section)
    if len(values) < 2:
        return None
    if kind == "bar":
        rgb = rgb_bar_chart(values, width=width, height=height)
    else:
        rgb = rgb_line_chart(values, width=width, height=height)
    return rgb, width, height
