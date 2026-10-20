"""Sector classification import: a validated loader awaiting an owner CSV.

HONEST LABELLING
----------------
No sector data ships with this project and none is fabricated here. This module
is the *pipeline*: it reads a sector CSV, validates every row, and assigns the
result to ``security_master.sector`` (the column ``ranking.py`` reads for
``sector_percentile``). Until the owner supplies an authoritative CSV, every
symbol's sector stays NULL and the downstream factor stays unavailable.

What the loader guarantees:

* **Required columns** ``symbol,sector`` — a file missing either is refused
  with an explanation rather than imported partially.
* **No fabricated rows.** A symbol absent from the security master is reported
  as *unknown*, never created: the master is built from successfully ingested
  symbols, not from a classification file.
* **Ambiguity is surfaced, not silently resolved.** A symbol that appears twice
  with two different sectors is reported and skipped, because guessing which is
  right would corrupt a classification.
* **Provenance is stored, not just echoed.** Every sector assignment records
  ``sector_source``, ``sector_retrieved_at`` and ``sector_observed_date`` in
  ``security_master`` so an unverified mapping can never be mistaken for an
  authoritative one.

Expected CSV: header ``symbol,sector`` (required). Optional provenance columns
``source``, ``retrieved_at`` (ISO timestamp) and ``observed_date`` (ISO date)
may appear per row; missing per-row values fall back to the ``source`` argument
and the current UTC time. Values are trimmed; symbols are upper-cased.
"""

from __future__ import annotations

import csv
import io
from datetime import UTC, date, datetime
from typing import Any

from megatool.market_store import is_valid_nepse_symbol

__all__ = [
    "REQUIRED_COLUMNS",
    "SECTOR_ALIASES",
    "SectorError",
    "canonical_sector",
    "classify_sectors",
    "import_sectors",
    "read_sectors_csv",
]

#: Source files use both singular and plural spellings for the same industry
#: (``Commercial Bank`` and ``Commercial Banks``), and a few legacy labels that
#: predate the canonical names. They describe the same classification, so report
#: and sector views group them under one label. This is a display/aggregation
#: alias only: the stored rows are never rewritten.
SECTOR_ALIASES: dict[str, str] = {
    "commercial bank": "Commercial Banks",
    "commercial banks": "Commercial Banks",
    "development bank": "Development Banks",
    "development banks": "Development Banks",
    "finance": "Finance Companies",
    "finance companies": "Finance Companies",
    "hotel & tourism": "Hotels",
    "hotels": "Hotels",
    "hydro power": "Hydropower",
    "hydropower": "Hydropower",
    "investment": "Investment Companies",
    "investment companies": "Investment Companies",
    "life insurance": "Life Insurance",
    "microfinance": "Microfinance",
    "manufacturing and processing": "Manufacturing and Processing",
    "mutual fund": "Mutual Fund",
    "non-life insurance": "Non-Life Insurance",
    "others": "Others",
    "trading": "Trading",
}


def canonical_sector(name: str | None) -> str:
    """Return the canonical display name for a stored sector, never a guess.

    Unknown labels are preserved verbatim (trimmed). Aliasing only merges
    spellings that unambiguously name the same classification; it does not
    invent a sector for an unclassified company.
    """
    clean = (name or "").strip()
    if not clean:
        return ""
    return SECTOR_ALIASES.get(clean.lower(), clean)

#: Columns that must be present in a sector CSV.
REQUIRED_COLUMNS = ("symbol", "sector")

#: Optional provenance columns recognised by the loader.
PROVENANCE_COLUMNS = ("source", "retrieved_at", "observed_date")


class SectorError(ValueError):
    """Raised for a file that cannot be imported (missing columns, no rows)."""


def read_sectors_csv(text: str) -> list[dict[str, str]]:
    """Parse a sector CSV into stripped row dicts.

    Raises :class:`SectorError` if the required columns are absent, so a wrong
    file is refused before any row is interpreted.
    """
    # utf-8-sig strips a BOM that Excel often adds; without it the first header
    # would read "\ufeffsymbol" and every required-column check would fail.
    sample = text.lstrip("\ufeff")
    reader = csv.DictReader(io.StringIO(sample))
    if not reader.fieldnames:
        raise SectorError("sector CSV is empty (no header row)")
    # Normalise header keys once (trim whitespace + any BOM) so both the
    # required-column check and the per-row lookups agree on the key spelling.
    fieldnames = [(h or "").strip().lstrip("\ufeff") for h in reader.fieldnames]
    missing = [c for c in REQUIRED_COLUMNS if c not in set(fieldnames)]
    if missing:
        raise SectorError(
            f"sector CSV is missing required column(s): {', '.join(missing)}. "
            f"Expected a header with {', '.join(REQUIRED_COLUMNS)}."
        )
    rows: list[dict[str, str]] = []
    for raw in reader:
        norm: dict[str, str] = {}
        for key, value in raw.items():  # DictReader keys are the raw header cells
            clean = (key or "").strip().lstrip("\ufeff")
            if clean:
                norm[clean] = (value or "").strip()
        rows.append(norm)
    return rows


def classify_sectors(
    rows: list[dict[str, str]],
) -> tuple[dict[str, str], dict[str, Any]]:
    """Validate rows into a ``{symbol: sector}`` map plus a report of rejects.

    Returns ``(mapping, report)`` where ``report`` has ``skipped`` (per-row
    reasons), ``ambiguous`` (symbols with conflicting sectors), ``duplicates``
    (identical repeats collapsed) and ``counts``.
    """
    mapping: dict[str, str] = {}
    seen: dict[str, set[str]] = {}
    skipped: list[dict[str, Any]] = []
    duplicates = 0

    for idx, row in enumerate(rows, start=2):  # line 1 is the header
        raw_symbol = (row.get("symbol") or "").strip()
        symbol = raw_symbol.upper()
        sector = (row.get("sector") or "").strip()
        ok, reason = is_valid_nepse_symbol(raw_symbol)
        if not ok:
            skipped.append({"line": idx, "symbol": raw_symbol, "reason": reason})
            continue
        if not sector:
            skipped.append({"line": idx, "symbol": symbol, "reason": "empty sector"})
            continue
        prior = seen.setdefault(symbol, set())
        if sector in prior:
            duplicates += 1
            continue
        prior.add(sector)
        if len(prior) > 1:
            # Conflicting classification for one symbol: do not pick a winner.
            skipped.append(
                {
                    "line": idx,
                    "symbol": symbol,
                    "reason": f"conflicting sector {sector!r} (already {sorted(prior - {sector})})",
                }
            )
            continue
        mapping[symbol] = sector

    # Symbols that ended up ambiguous contribute nothing to the mapping.
    ambiguous = sorted(s for s, vals in seen.items() if len(vals) > 1)
    for sym in ambiguous:
        mapping.pop(sym, None)

    report: dict[str, Any] = {
        "rows_in_file": len(rows),
        "classified": len(mapping),
        "duplicates": duplicates,
        "skipped": skipped,
        "ambiguous": ambiguous,
        "counts": {
            "rows": len(rows),
            "classified": len(mapping),
            "skipped": len(skipped),
            "ambiguous": len(ambiguous),
            "duplicates": duplicates,
        },
    }
    return mapping, report


def _parse_iso_timestamp(value: str, line: int) -> datetime:
    """Parse an ISO timestamp, raising SectorError with line context on failure."""
    try:
        dt = datetime.fromisoformat(value)
        # Normalise a trailing "Z" to +00:00 so fromisoformat succeeds on
        # common export formats.
        if value.endswith("Z") and dt.tzinfo is None:
            dt = datetime.fromisoformat(value[:-1] + "+00:00")
        # Store naive UTC to match the rest of the market store timestamps.
        if dt.tzinfo is not None:
            dt = dt.astimezone(UTC).replace(tzinfo=None)
        return dt
    except ValueError as exc:
        raise SectorError(f"line {line}: invalid retrieved_at timestamp {value!r}: {exc}") from exc


def _parse_iso_date(value: str, line: int) -> date:
    """Parse an ISO date, raising SectorError with line context on failure."""
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise SectorError(f"line {line}: invalid observed_date {value!r}: {exc}") from exc


def _build_provenance(
    rows: list[dict[str, str]],
    mapping: dict[str, str],
    *,
    fallback_source: str,
    fallback_retrieved_at: datetime,
) -> dict[str, dict[str, Any]]:
    """Return a provenance entry for every symbol that survived classification.

    Per-row ``source``, ``retrieved_at`` and ``observed_date`` take precedence;
    otherwise the call-level fallback is used. ``observed_date`` has no default.
    """
    provenance: dict[str, dict[str, Any]] = {}
    for idx, row in enumerate(rows, start=2):
        symbol = (row.get("symbol") or "").upper().strip()
        if symbol not in mapping:
            continue
        if symbol in provenance:
            # Already captured from an earlier row for this symbol.
            continue
        entry: dict[str, Any] = {"source": fallback_source, "retrieved_at": fallback_retrieved_at}
        per_source = (row.get("source") or "").strip()
        if per_source:
            entry["source"] = per_source
        per_retrieved = (row.get("retrieved_at") or "").strip()
        if per_retrieved:
            entry["retrieved_at"] = _parse_iso_timestamp(per_retrieved, idx)
        per_observed = (row.get("observed_date") or "").strip()
        if per_observed:
            entry["observed_date"] = _parse_iso_date(per_observed, idx)
        provenance[symbol] = entry
    # Any symbol in the mapping that had no rows with provenance columns still
    # gets the fallback source/retrieved_at.
    for symbol in mapping:
        provenance.setdefault(
            symbol,
            {"source": fallback_source, "retrieved_at": fallback_retrieved_at},
        )
    return provenance


def import_sectors(
    text: str,
    *,
    source: str,
    store: Any = None,
    retrieved_at: datetime | str | None = None,
    observed_date: date | str | None = None,
) -> dict[str, Any]:
    """Parse, validate and persist a sector CSV into ``security_master``.

    ``source`` is required provenance and is stored in ``sector_source`` for
    every assignment. Pass a ``MarketStore`` to target a specific database
    (tests inject an isolated one); the default opens the application's market
    store.

    ``retrieved_at`` and ``observed_date`` are optional call-level fallbacks;
    if omitted, ``retrieved_at`` defaults to the current UTC time and
    ``observed_date`` is left NULL unless supplied by the CSV.
    """
    if not str(source).strip():
        raise SectorError("source is required; a sector import without provenance is not kept")
    rows = read_sectors_csv(text)
    if not rows:
        raise SectorError("sector CSV contained no data rows")
    mapping, report = classify_sectors(rows)

    if store is None:
        from megatool.market_store import MarketStore

        store = MarketStore()

    stamp = datetime.now(UTC).replace(tzinfo=None)
    if isinstance(retrieved_at, str):
        retrieved_at = datetime.fromisoformat(retrieved_at)
    if isinstance(observed_date, str):
        observed_date = date.fromisoformat(observed_date)
    fallback_retrieved = retrieved_at or stamp

    provenance = _build_provenance(
        rows,
        mapping,
        fallback_source=str(source).strip(),
        fallback_retrieved_at=fallback_retrieved,
    )
    # Apply any call-level observed_date fallback to symbols that did not get
    # one from their row.
    if observed_date is not None:
        for entry in provenance.values():
            entry.setdefault("observed_date", observed_date)

    written = (
        store.set_sectors(mapping, provenance=provenance)
        if mapping
        else {"updated": 0, "unknown": [], "total": 0}
    )

    report.update(
        {
            "source": str(source).strip(),
            "assigned": written["updated"],
            "unknown_symbols": written["unknown"],
        }
    )
    return report


def auto_import_from_disk(store: Any = None) -> dict[str, Any]:
    """Auto-import sector CSVs from the project's review sources directory.

    Reuses the existing import_sectors pipeline. Returns a report dict.
    If no CSV files are found, returns an empty report with a reason.
    """
    from pathlib import Path

    if store is None:
        from megatool.market_store import MarketStore
        store = MarketStore()

    csv_candidates = [
        ("data/review/sources/yonepse/yonepse_sectors.csv", "yonepse/securities.json"),
        ("data/review/sources/binayabaral/binayabaral_sectors.csv", "binayabaral/securities.json"),
    ]
    total_classified = 0
    total_skipped = 0
    sources_used = []
    for path, source in csv_candidates:
        p = Path(path)
        if not p.exists():
            continue
        text = p.read_text(encoding="utf-8")
        try:
            report = import_sectors(text, source=source, store=store)
            total_classified += report["classified"]
            total_skipped += len(report["skipped"])
            sources_used.append(path)
        except SectorError:
            continue
    return {
        "classified": total_classified,
        "skipped": total_skipped,
        "sources_used": sources_used,
        "available": total_classified > 0,
    }
