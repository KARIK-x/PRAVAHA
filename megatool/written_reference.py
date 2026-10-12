"""Secondary digitizations of ``WRITTENdata.pdf``, parsed into labelled records.

Three supplementary files describe the same handwritten notebook that
:mod:`megatool.written_transcribe` reads by eye:

``digitized_trading_ledger_and_notes.md``
    NotebookLM's narrative digitization: trade registers, broker settlements,
    multi-year EPS, sector valuation tables, indicator scoreboards, strategy
    rules and watchlists.
``trading_ledger_master_data.xlsx``
    NotebookLM's structured workbook: a trades register that carries an
    explicit settlement label per trade, plus banking/microfinance and
    hydropower EPS sheets.
``Written_Data_All_52_Pages_Digitized.xlsx``
    ChatGPT's page-by-page workbook of images plus preliminary OCR.

**These are not ground truth.** They are other machines reading the same
handwriting, so every record leaving this module carries three labels that a
consumer must not strip:

``provenance``
    always ``secondary_digitization`` — never ``manual_visual``.
``verification``
    ``unverified`` by default; ``cross_checked`` only where a value was
    matched against a settlement a human read off the page image.
``data_vintage``
    always ``historical_handwritten``. A "Market Price" here is what the
    notebook wrote on an unknown date, **not** a current NEPSE price. Feeding
    it to anything that implies liveness would be a lie.

Nothing in this module touches the database. Records carry ``source_file`` and
``source_section`` rather than a PDF page number, because the reference files
do not say which page a figure came from and inventing one would break the
"every record keeps its PDF page number" rule that :mod:`megatool.written_pdf`
depends on. The settlements whose pages *are* known already live in
:mod:`megatool.written_transcribe` as visually read records.

What this module is for is the opposite direction: checking those other
readings against ours with :func:`cross_check_settlements`, and turning their
tables into something Mega Tool can search without pretending they are verified.
"""

from __future__ import annotations

import csv
import re
from pathlib import Path
from typing import Any

__all__ = [
    "DATA_VINTAGE",
    "MD_FILENAME",
    "PROVENANCE",
    "REFERENCE_FILES",
    "VERIFICATION_UNVERIFIED",
    "XLSX_FILENAME",
    "cross_check_components",
    "cross_check_settlements",
    "load_reference",
    "parse_markdown",
    "reference_summary",
]

#: Provenance stamped on every record this module produces.
PROVENANCE = "secondary_digitization"
#: Default verification. Raised to ``cross_checked`` only by a human-read match.
VERIFICATION_UNVERIFIED = "unverified"
#: Every figure here is a historical handwritten value, never live market data.
DATA_VINTAGE = "historical_handwritten"

MD_FILENAME = "digitized_trading_ledger_and_notes.md"
XLSX_FILENAME = "trading_ledger_master_data.xlsx"

#: Files this module reads, in the order they are consulted.
REFERENCE_FILES = (MD_FILENAME, XLSX_FILENAME)

_PROJECT_ROOT = Path(__file__).resolve().parent.parent

#: ``NPR 58,211.45`` / ``(59)`` / ``—`` → float | None.
_MONEY_RE = re.compile(r"-?\d[\d,]*\.?\d*")
_HEADING_RE = re.compile(r"^(#{1,4})\s+\**(.*?)\**\s*$")
_TABLE_SEP_RE = re.compile(r"^\|[\s:|-]+\|$")
_SETTLEMENT_HEAD_RE = re.compile(r"^\s*-\s+\*\*Settlement\s+([0-9A-Z]+):?\*\*")


# --------------------------------------------------------------------------
# small parsers
# --------------------------------------------------------------------------
def _clean(cell: str) -> str:
    """Strip markdown decoration from one table cell."""
    return cell.replace("**", "").replace("`", "").strip()


def _number(text: str) -> float | None:
    """First number in ``text``, or ``None`` when there is no usable one.

    ``—``, ``(59)`` with no digits, and empty cells give ``None``. Parenthesised
    values are kept as the number they contain: the notebook writes a negative
    P/E as ``(59)``, which is a real reading, not a missing one.
    """
    m = _MONEY_RE.search(text.replace(",", ""))
    if not m:
        return None
    try:
        return float(m.group())
    except ValueError:
        return None


def parse_markdown(text: str) -> dict[str, Any]:
    """Split a NotebookLM markdown document into headings, tables and bullets.

    Returns ``{"sections": {heading: {"tables": [...], "bullets": [...]}}}``.
    Tables keep their column headers so a consumer can tell a "Float (Shares)"
    column from a "Float" column without guessing.
    """
    sections: dict[str, dict[str, Any]] = {}
    heading = ""
    lines = text.splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]

        h = _HEADING_RE.match(line)
        if h:
            heading = _clean(h.group(2))
            sections.setdefault(heading, {"tables": [], "bullets": []})
            i += 1
            continue

        if (
            line.lstrip().startswith("|")
            and i + 1 < len(lines)
            and _TABLE_SEP_RE.match(lines[i + 1].strip())
        ):
            header = [_clean(c) for c in line.strip().strip("|").split("|")]
            rows: list[list[str]] = []
            i += 2
            while i < len(lines) and lines[i].lstrip().startswith("|"):
                cells = [_clean(c) for c in lines[i].strip().strip("|").split("|")]
                # Torn rows (fewer cells than the header) are kept as read
                # rather than padded — a padded cell would invent a value.
                rows.append(cells)
                i += 1
            sections.setdefault(heading, {"tables": [], "bullets": []})["tables"].append(
                {"header": header, "rows": rows}
            )
            continue

        stripped = line.strip()
        if stripped.startswith("- "):
            sections.setdefault(heading, {"tables": [], "bullets": []})["bullets"].append(
                stripped[2:].strip()
            )
        elif stripped.startswith("  - "):
            sections.setdefault(heading, {"tables": [], "bullets": []})["bullets"].append(
                stripped[4:].strip()
            )

        i += 1

    return {"sections": sections}


def _records_from_table(
    table: dict[str, Any],
    *,
    source_file: str,
    source_section: str,
    kind: str,
) -> list[dict[str, Any]]:
    """Turn one parsed markdown table into labelled records."""
    header = table["header"]
    out = []
    for n, row in enumerate(table["rows"], start=1):
        if not any(c for c in row):
            continue
        out.append(
            {
                "kind": kind,
                "source_file": source_file,
                "source_section": source_section,
                "source_row": n,
                "columns": header,
                "values": row,
                "provenance": PROVENANCE,
                "verification": VERIFICATION_UNVERIFIED,
                "data_vintage": DATA_VINTAGE,
            }
        )
    return out


def _heading_for(sections: dict[str, Any], needle: str) -> str | None:
    for h in sections:
        if needle.lower() in h.lower():
            return h
    return None


# --------------------------------------------------------------------------
# settlements
# --------------------------------------------------------------------------
#: ``Buy NPR x``, ``Buy (23-24 Sep): NPR x`` and ``Sell: NPR x`` are all
#: forms the document uses for the same thing.
_MONEY_AFTER = r"\s*(?:\([^)]*\)\s*)?:?\s*NPR\s+([\d,]+\.\d{2})"
_BUY_INLINE_RE = re.compile(r"Buy" + _MONEY_AFTER)
_SELL_INLINE_RE = re.compile(r"Sell" + _MONEY_AFTER)


def _settlement_blocks(md_text: str) -> dict[str, dict[str, Any]]:
    """Parse both settlement layouts the document uses.

    August writes a multi-line block per settlement; September writes one line.
    Both are recognised because a cross-check that only understood one would
    silently skip half the corpus.

    Two traps this has to avoid, both of which produced wrong output before:

    * **The last August settlement is never reset.** Only a new
      ``- **Settlement X:**`` line changed ``current``, so once 8E was open
      every later line in the document was scanned — including September's
      trade-register table rows — and *overwrote* 8E's totals with September
      figures. Headings and non-bullet lines now close or are skipped.
    * **A settlement label can appear with a date range.** ``Buy (23-24 Sep):
      NPR …`` does not match ``Buy NPR …``, which is why 9E and 9F read as
      empty.
    """
    blocks: dict[str, dict[str, Any]] = {}
    current: str | None = None
    for raw in md_text.splitlines():
        if raw.lstrip().startswith("#"):
            current = None
            continue

        head = _SETTLEMENT_HEAD_RE.match(raw)
        if head:
            current = head.group(1)
            blocks[current] = {"label": current, "raw_line": raw.strip()}
            inline_fields = 0
            # Single-line form: "Settlement 9A: Buy NPR x | Sell NPR y -> ..."
            inline = raw.split(":", 1)[-1]
            for key, pat in (("buy_total", _BUY_INLINE_RE), ("sell_total", _SELL_INLINE_RE)):
                m = pat.search(inline)
                if m:
                    blocks[current][key] = _number(m.group(1))
                    inline_fields += 1
            m = re.search(r"\*\*Net (Payable|Receivable|Clear):?\*\*\s*NPR\s+([\d,]+\.\d{2})", raw)
            if m:
                blocks[current]["direction"] = m.group(1).lower()
                blocks[current]["net"] = _number(m.group(2))
                inline_fields += 1
            m = re.search(r"\*\(([^)]*)\)\*", raw)
            if m:
                blocks[current]["settlement_note"] = _clean(m.group(1))
            # The multi-line form ("Settlement 8C:" on its own line) keeps the
            # block open so the following bullets attach to it; the inline form
            # is complete here, and leaving it open would let the *next*
            # section's bullets land in this block.
            if inline_fields:
                current = None
            continue

        if current is None:
            continue

        # Only the settlement's own bullet sub-items are read. Table rows,
        # prose and headings are not part of the block.
        stripped = raw.strip()
        if not (stripped.startswith("- ") or stripped.startswith("  - ")):
            continue
        line = stripped.lstrip("- ").strip()

        m = re.search(r"Total Buy[^:]*:\s*NPR\s+([\d,]+\.\d{2})", line)
        if m:
            blocks[current]["buy_total"] = _number(m.group(1))
            m2 = re.search(r"Total Buy\s*\(([^)]*)\)", line)
            if m2:
                blocks[current]["buy_dates"] = _clean(m2.group(1))
            continue
        m = re.search(r"Total Sell[^:]*:\s*NPR\s+([\d,]+\.\d{2})", line)
        if m:
            blocks[current]["sell_total"] = _number(m.group(1))
            m2 = re.search(r"Total Sell\s*\(([^)]*)\)", line)
            if m2:
                blocks[current]["sell_dates"] = _clean(m2.group(1))
            continue
        m = re.search(r"\*\*Net (Payable|Receivable|Clear):?\*\*\s*NPR\s+([\d,]+\.\d{2})", line)
        if m:
            blocks[current]["direction"] = m.group(1).lower()
            blocks[current]["net"] = _number(m.group(2))
            continue

        # An unrecognised bullet means this block is over — a day-line such as
        # "- **15 Jan:** … → **Net Payable:** NPR 21,091.29" would otherwise be
        # read as the settlement's own net and silently overwrite a real one.
        current = None
    return blocks


# --------------------------------------------------------------------------
# per-day trades -> component-level cross-check
# --------------------------------------------------------------------------
_MONTHS = {
    "jan": "Jan",
    "feb": "Feb",
    "mar": "Mar",
    "apr": "Apr",
    "may": "May",
    "jun": "Jun",
    "jul": "Jul",
    "aug": "Aug",
    "sep": "Sep",
    "sept": "Sep",
    "oct": "Oct",
    "nov": "Nov",
    "dec": "Dec",
}

#: ``- **12 Dec:** Buy ENL (60 x 1291.33) = NPR 77,795.55 | Sell … = NPR …``
_DAY_BULLET_RE = re.compile(r"^\s*-\s+\*\*(\d{1,2})\s+([A-Za-z]{3,9})\.?:\*\*\s*(.*)$")
_DAY_BUY_RE = re.compile(r"Buy[^=]*=\s*NPR\s+([\d,]+\.\d{2})")
_DAY_SELL_RE = re.compile(r"Sell[^=]*=\s*NPR\s+([\d,]+\.\d{2})")
#: ``16/18/19/22 Dec buy`` — the ``dates`` string on a visually read record.
_DATES_PART_RE = re.compile(r"^([0-9/]+)\s+(\w+)\s+(buy|sell)$")


def _day_trades(md_text: str) -> dict[tuple[str, int], dict[str, Any]]:
    """Day lines keyed by ``(month_abbrev, day)``.

    October–February are written as one bullet per trading day carrying that
    day's buy total and sell total, with no settlement label on the line. That
    is exactly the granularity the visually read records store their
    ``buy_components``/``sell_components`` at, which is what makes a
    component-level cross-check possible where a total-level one is not
    (December carries no settlement totals in the reference at all).
    """
    out: dict[tuple[str, int], dict[str, Any]] = {}
    for raw in md_text.splitlines():
        m = _DAY_BULLET_RE.match(raw)
        if not m:
            continue
        month = _MONTHS.get(m.group(2).lower())
        if month is None:
            continue
        rest = m.group(3)
        entry: dict[str, Any] = {"month": month, "day": int(m.group(1)), "raw": raw.strip()}
        b, s = _DAY_BUY_RE.search(rest), _DAY_SELL_RE.search(rest)
        if b:
            entry["buy"] = _number(b.group(1))
        if s:
            entry["sell"] = _number(s.group(1))
        out[(month, int(m.group(1)))] = entry
    return out


def _parse_dates(dates: str) -> dict[str, list[tuple[str, int]]]:
    """Split a record's ``dates`` string into ``(month, day)`` keys per side."""
    sides: dict[str, list[tuple[str, int]]] = {"buy": [], "sell": []}
    for part in (dates or "").split(","):
        m = _DATES_PART_RE.match(part.strip())
        if not m:
            continue
        month = _MONTHS.get(m.group(2).lower())
        if month is None:
            continue
        for tok in m.group(1).split("/"):
            if tok.strip().isdigit():
                sides[m.group(3)].append((month, int(tok)))
    return sides


def _component_side(
    my_components: list[float],
    my_total: float | None,
    keys: list[tuple[str, int]],
    days: dict[tuple[str, int], dict[str, Any]],
    side: str,
) -> dict[str, Any]:
    """Compare one side (buy or sell) of one settlement against the day lines."""
    found = [days[k][side] for k in keys if k in days and side in days[k]]
    present = [k for k in keys if k in days and side in days[k]]
    row: dict[str, Any] = {
        "days_expected": [f"{d} {m}" for m, d in keys],
        "days_found": [f"{d} {m}" for m, d in present],
        "my_components": list(my_components),
        "my_total": my_total,
        "reference_components": found,
        "reference_sum": round(sum(found), 2) if found else None,
        "components_available": len(found) == len(keys) and bool(keys),
    }
    if row["components_available"] and my_components:
        row["components_match"] = sorted(round(x, 2) for x in found) == sorted(
            round(x, 2) for x in my_components
        )
    elif not my_components:
        # Nothing was read by eye here. Not a disagreement — an absence.
        row["components_match"] = None
        row["note"] = "not read by eye; reference supplies the components"
    else:
        row["components_match"] = None
    if found and my_total is not None:
        row["total_matches_reference_sum"] = round(sum(found), 2) == round(float(my_total), 2)
    else:
        row["total_matches_reference_sum"] = None
    return row


def cross_check_components(md_text: str | None = None) -> list[dict[str, Any]]:
    """Component-level cross-check: every visually read figure vs the reference.

    The total-level check in :func:`cross_check_settlements` can only compare
    August and September, because December is written without settlement
    totals. This compares the *components* instead, using each record's own
    ``dates`` string to find the matching day lines — so it covers 12A–12F,
    where a total-level check would report nothing.

    Nothing is promoted or rewritten here. A record whose components were never
    read (12F's sells) reports ``components_match = None`` with a note, because
    an empty list is an absence of reading, not a disagreement.
    """
    from megatool.written_transcribe import ALL_VISUALLY_READ

    if md_text is None:
        md_text = _read_md()
    days = _day_trades(md_text) if md_text else {}

    out: list[dict[str, Any]] = []
    for rec in ALL_VISUALLY_READ:
        sides = _parse_dates(rec.get("dates", ""))
        if not days or (not any(sides["buy"]) and not any(sides["sell"])):
            continue
        for side in ("buy", "sell"):
            keys = sides[side]
            if not keys:
                continue
            comps = rec.get(f"{side}_components") or []
            total = rec.get(f"{side}_total")
            row = _component_side(comps, total, keys, days, side)
            row.update(
                {
                    "label": rec["label"],
                    "page": rec["page"],
                    "side": side,
                    "provenance": PROVENANCE,
                    "verification": VERIFICATION_UNVERIFIED,
                    "data_vintage": DATA_VINTAGE,
                }
            )
            if row["components_match"] is True or row["total_matches_reference_sum"] is True:
                row["verification"] = "cross_checked"
            out.append(row)
    return out


# --------------------------------------------------------------------------
# cross-check
# --------------------------------------------------------------------------
def cross_check_settlements(md_text: str | None = None) -> list[dict[str, Any]]:
    """Compare the reference file's settlements against the human-read ones.

    This is the one place a reference figure may be promoted to
    ``cross_checked``: not because the reference is authoritative, but because
    two readings of the same page agreeing is evidence about the *page*. Every
    matched figure still reports which side it came from and what the human
    record says, so a disagreement is visible rather than resolved silently.
    """
    from megatool.written_transcribe import ALL_VISUALLY_READ

    if md_text is None:
        md_text = _read_md()
    ref = _settlement_blocks(md_text) if md_text else {}
    ours = {d["label"]: d for d in ALL_VISUALLY_READ}

    out: list[dict[str, Any]] = []
    for label in sorted(set(ref) | set(ours)):
        r = ref.get(label, {})
        o = ours.get(label)
        row: dict[str, Any] = {
            "label": label,
            "in_reference": label in ref,
            "read_by_eye": o is not None,
            "page": o["page"] if o else None,
            "fields_compared": 0,
            "fields_agree": 0,
            "disagreements": [],
            "provenance": PROVENANCE,
            "verification": VERIFICATION_UNVERIFIED,
            "data_vintage": DATA_VINTAGE,
        }
        if o is None:
            # Reference-only: present, but nothing has read the page it came
            # from, so it stays unverified and page-less.
            for k in ("buy_total", "sell_total", "net"):
                row[k] = r.get(k)
            out.append(row)
            continue

        for k in ("buy_total", "sell_total", "net"):
            a, b = o.get(k), r.get(k)
            if a is None or b is None:
                continue
            row["fields_compared"] += 1
            if round(float(a), 2) == round(float(b), 2):
                row["fields_agree"] += 1
            else:
                row["disagreements"].append(f"{k}: read {a} vs reference {b}")
            row[k] = a  # the human reading is what we store

        # The settlement note carries "Paid NPR x on date".
        note = r.get("settlement_note", "")
        if note and o.get("settled") is not None:
            m = re.search(r"(?:Paid|Received)\s+NPR\s+([\d,]+\.\d{2})", note)
            if m:
                ref_settled = _number(m.group(1))
                row["fields_compared"] += 1
                if round(float(o["settled"]), 2) == round(float(ref_settled), 2):
                    row["fields_agree"] += 1
                else:
                    row["disagreements"].append(
                        f"settled: read {o['settled']} vs reference {ref_settled}"
                    )

        if row["fields_compared"] and not row["disagreements"]:
            row["verification"] = "cross_checked"
        out.append(row)
    return out


def _read_md(root: Path | None = None) -> str:
    p = (root or _PROJECT_ROOT) / MD_FILENAME
    return p.read_text(encoding="utf-8") if p.exists() else ""


# --------------------------------------------------------------------------
# public API
# --------------------------------------------------------------------------
def load_reference(root: Path | None = None) -> dict[str, Any]:
    """Parse every available reference file into labelled records.

    Missing files are skipped rather than raising: the module's job is to use
    whatever supplementary material happens to be present, and a workbook the
    owner has not dropped in yet is not an error.
    """
    base = root or _PROJECT_ROOT
    out: dict[str, Any] = {
        "files_found": [],
        "files_missing": [],
        "transactions": [],
        "fundamentals": [],
        "scoreboards": [],
        "strategies": [],
        "watchlists": [],
        "settlements": [],
        "cross_check": [],
        "component_cross_check": [],
        "notes": [],
    }

    md_path = base / MD_FILENAME
    if not md_path.exists():
        out["files_missing"].append(MD_FILENAME)
        return out
    out["files_found"].append(MD_FILENAME)
    md_text = md_path.read_text(encoding="utf-8")
    parsed = parse_markdown(md_text)
    sections = parsed["sections"]

    # --- trade registers (markdown tables) ---------------------------------
    for needle, kind in (("Daily Trade Register", "transaction"),):
        for heading, body in sections.items():
            if needle.lower() not in heading.lower():
                continue
            for table in body["tables"]:
                out["transactions"].extend(
                    _records_from_table(
                        table, source_file=MD_FILENAME, source_section=heading, kind=kind
                    )
                )

    # --- fundamentals ------------------------------------------------------
    for needle, kind in (
        ("Q1 EPS Comparison", "eps_history"),
        ("Commercial Banking Sector Valuation", "sector_valuation"),
        ("Microfinance Sector Master Data", "sector_valuation"),
        ("Multi-Timeframe Indicator Scoreboard", "indicator_scoreboard"),
    ):
        heading = _heading_for(sections, needle)
        if heading is None:
            continue
        for table in sections[heading]["tables"]:
            out["scoreboards" if kind == "indicator_scoreboard" else "fundamentals"].extend(
                _records_from_table(
                    table, source_file=MD_FILENAME, source_section=heading, kind=kind
                )
            )

    # --- prose sections that are lists, not tables -------------------------
    for heading, body in sections.items():
        low = heading.lower()
        target: str | None = None
        if (
            "strategy" in low
            or "indicators & rules" in low
            or ("screening" in low and "framework" in low)
        ):
            target = "strategies"
        elif "screening list" in low or "watchlist" in low:
            target = "watchlists"
        elif "multi-sector valuation" in low:
            target = "fundamentals"
        if target is None:
            continue
        for bullet in body["bullets"]:
            out[target].append(
                {
                    "kind": target[:-1] if target.endswith("s") else target,
                    "source_file": MD_FILENAME,
                    "source_section": heading,
                    "text": bullet,
                    "provenance": PROVENANCE,
                    "verification": VERIFICATION_UNVERIFIED,
                    "data_vintage": DATA_VINTAGE,
                }
            )

    out["settlements"] = [
        {
            "kind": "settlement",
            "source_file": MD_FILENAME,
            "source_section": "Broker Settlements",
            **{k: v for k, v in b.items()},
            "provenance": PROVENANCE,
            "verification": VERIFICATION_UNVERIFIED,
            "data_vintage": DATA_VINTAGE,
        }
        for b in _settlement_blocks(md_text).values()
    ]
    out["cross_check"] = cross_check_settlements(md_text)
    out["component_cross_check"] = cross_check_components(md_text)

    # --- structured workbook ----------------------------------------------
    out.update(_load_workbook(base))

    return out


def _load_workbook(base: Path) -> dict[str, Any]:
    """Read the NotebookLM workbook if openpyxl and the file are available."""
    path = base / XLSX_FILENAME
    if not path.exists():
        return {"files_missing_workbook": [XLSX_FILENAME], "workbook_rows": []}
    try:
        import openpyxl
    except ImportError:  # pragma: no cover - openpyxl is an optional group
        return {
            "files_missing_workbook": [f"{XLSX_FILENAME} (openpyxl not installed)"],
            "workbook_rows": [],
        }

    rows: list[dict[str, Any]] = []
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    try:
        for sheet in wb.sheetnames:
            ws = wb[sheet]
            grid = [list(r) for r in ws.iter_rows(values_only=True)]
            # The first row is a banner, the second the header.
            if len(grid) < 2:
                continue
            header = [str(c).strip() if c is not None else "" for c in grid[1]]
            for n, row in enumerate(grid[2:], start=1):
                if not any(c is not None and str(c).strip() for c in row):
                    continue
                cells = {
                    header[i]: (str(row[i]) if i < len(row) and row[i] is not None else "")
                    for i in range(len(header))
                }
                rows.append(
                    {
                        "sheet": sheet,
                        "source_row": n,
                        **cells,
                        "source_file": XLSX_FILENAME,
                        "source_section": sheet,
                        "provenance": PROVENANCE,
                        "verification": VERIFICATION_UNVERIFIED,
                        "data_vintage": DATA_VINTAGE,
                    }
                )
    finally:
        wb.close()
    return {"files_found_workbook": [XLSX_FILENAME], "workbook_rows": rows}


def reference_summary(ref: dict[str, Any] | None = None) -> dict[str, Any]:
    """Counts for reporting. Computed, never asserted."""
    r = ref if ref is not None else load_reference()
    cross = r.get("cross_check", [])
    compared = [c for c in cross if c["fields_compared"]]
    comps = r.get("component_cross_check", [])
    # ``None`` = one side was never read by eye. Not counted as agreement or
    # disagreement; reported separately so an absence is not mistaken for a pass.
    comp_read = [c for c in comps if c["components_match"] is not None]
    return {
        "files_found": r.get("files_found", []),
        "files_missing": r.get("files_missing", []),
        "workbook_rows": len(r.get("workbook_rows", [])),
        "transactions": len(r.get("transactions", [])),
        "fundamentals": len(r.get("fundamentals", [])),
        "scoreboards": len(r.get("scoreboards", [])),
        "strategies": len(r.get("strategies", [])),
        "watchlists": len(r.get("watchlists", [])),
        "settlements": len(r.get("settlements", [])),
        "settlements_cross_checked": sum(
            1 for c in compared if c["verification"] == "cross_checked"
        ),
        "settlements_with_disagreement": sum(1 for c in compared if c["disagreements"]),
        "settlements_reference_only": sum(1 for c in cross if not c["read_by_eye"]),
        "fields_compared": sum(c["fields_compared"] for c in compared),
        "fields_agree": sum(c["fields_agree"] for c in compared),
        "component_sides_compared": len(comps),
        "component_sides_readable": len(comp_read),
        "component_sides_agreeing": sum(1 for c in comp_read if c["components_match"]),
        "component_sides_disagreeing": sum(1 for c in comp_read if not c["components_match"]),
        "component_sides_not_read_by_eye": sum(
            1 for c in comps if c["components_match"] is None and not c["my_components"]
        ),
        "component_sum_vs_total_agreeing": sum(
            1 for c in comps if c["total_matches_reference_sum"] is True
        ),
    }


def write_reference_csvs(out_dir: Path, ref: dict[str, Any] | None = None) -> dict[str, int]:
    """Emit one CSV per record family. Returns rows written per file.

    Structured cells are JSON so a consumer parsing the file as CSV gets a
    value back rather than a Python ``repr``.
    """
    import json

    r = ref if ref is not None else load_reference()
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    counts: dict[str, int] = {}
    for name, key in (
        ("reference_transactions.csv", "transactions"),
        ("reference_fundamentals.csv", "fundamentals"),
        ("reference_scoreboards.csv", "scoreboards"),
        ("reference_strategies.csv", "strategies"),
        ("reference_watchlists.csv", "watchlists"),
        ("reference_settlements.csv", "settlements"),
        ("reference_cross_check.csv", "cross_check"),
        ("reference_component_cross_check.csv", "component_cross_check"),
        ("reference_workbook.csv", "workbook_rows"),
    ):
        rows = r.get(key, [])
        if not rows:
            counts[name] = 0
            continue
        fields: list[str] = []
        for row in rows:
            for k in row:
                if k not in fields:
                    fields.append(k)
        with (out_dir / name).open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
            w.writeheader()
            for row in rows:
                w.writerow(
                    {
                        k: (
                            json.dumps(v, ensure_ascii=False)
                            if isinstance(v, (list, dict, bool))
                            else ("" if v is None else v)
                        )
                        for k, v in row.items()
                    }
                )
        counts[name] = len(rows)
    return counts
