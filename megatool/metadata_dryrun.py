"""Dry-run harness for reviewed security metadata (T-M2).

**This module cannot write to any database.** It opens the store read-only
(see :class:`~megatool.market_store.MarketStore`), validates a reviewed CSV,
reconciles it against the *current* ``security_master`` values via the T-M1
reader :meth:`~megatool.market_store.MarketStore.securities_meta`, and reports
what an import *would* change. No import command exists; a future import is a
separate, owner-approved operation.

INPUT SCHEMA (one record per row)::

    symbol                 required, normalised upper/strip
    name                   optional
    instrument_type        optional, must be in ALLOWED_INSTRUMENT_TYPES
    sector                 optional, free text (never guessed when blank)
    status                 optional, must be in ALLOWED_STATUSES
    delisted               optional, TRUE/FALSE/1/0/yes/no (blank = unknown)
    source                 optional provenance string
    requires_manual_review optional TRUE/FALSE flag carried through to output

At least one metadata column (``name``, ``instrument_type``, ``sector``,
``status``, ``delisted``) must be present; other columns are ignored and
listed. Blank cells stay blank — the harness never fills a sector, instrument
type, listing status or delisting flag that the file does not state.

POLICY (decisions D-s and D-u…D-w in ``DECISIONS.md``):

* Every proposed value is **source-provided-unverified**; current store values
  are the only verified facts. Nothing about the file upgrades it to verified.
* ``status=merged`` is never converted to ``delisted=True`` — there is no such
  mapping in this build, and inventing one would fabricate a listing status.
* Symbols absent from the store are reported as additions for manual review,
  never created.
* Where the file and the store disagree on a non-NULL stored value, the record
  is a conflict: the stored value is preserved and reported, both sides shown.
* Output is deterministic: identical input bytes + identical store state give
  byte-identical JSON and Markdown (no timestamps, sorted keys, sorted symbols).
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from megatool.market_store import (
    STATUS_ACTIVE,
    STATUS_DELISTED,
    STATUS_MERGED,
    STATUS_SUSPENDED,
    STATUS_UNKNOWN,
    MarketStore,
    is_valid_nepse_symbol,
)


class MetadataDryRunError(ValueError):
    """The input file as a whole is unusable (schema-level problem)."""


#: Columns this harness understands, in canonical order.
RECOGNIZED_COLUMNS: tuple[str, ...] = (
    "symbol",
    "name",
    "instrument_type",
    "sector",
    "status",
    "delisted",
    "successor_symbol",
)

#: At least one of these must be present or there is nothing to reconcile.
METADATA_COLUMNS: tuple[str, ...] = (
    "name",
    "instrument_type",
    "sector",
    "status",
    "delisted",
    "successor_symbol",
)

#: Optional provenance / workflow columns (honoured, not required).
OPTIONAL_COLUMNS: tuple[str, ...] = (
    "source",
    "requires_manual_review",
    "sector_source",
    "sector_retrieved_at",
    "sector_observed_date",
)

#: The vocabulary this build understands — the instrument types and input
#: status aliases carried by the reviewed dataset. **Not** an authoritative
#: NEPSE classification: anything outside these sets is rejected for manual
#: review, never guessed or coerced into a neighbouring value.
ALLOWED_INSTRUMENT_TYPES = frozenset(
    {"ordinary", "mutual_fund", "debenture", "promoter_share", "government_bond", "preference"}
)
# ``listed`` is accepted as an alias for the canonical stored status ``ACTIVE``.
ALLOWED_STATUSES = frozenset({"active", "listed", "merged", "delisted", "suspended"})

_TRUE = frozenset({"true", "1", "yes", "y"})
_FALSE = frozenset({"false", "0", "no", "n"})

#: Proposed fields that have a stored counterpart in ``security_master`` and
#: therefore participate in update/conflict detection. ``status`` is now
#: stored distinctly from ``delisted`` (R5 / B-4), so both are reconciled.
RECONCILED_FIELDS: tuple[str, ...] = (
    "name",
    "sector",
    "instrument_type",
    "status",
    "delisted",
    "successor_symbol",
)

#: Confidence label for every value that comes from the input file.
UNVERIFIED = "source-provided-unverified"
NO_PROVENANCE = "unverified-no-provenance"

MAX_TABLE_ROWS = 30  # human-readable report cap; the JSON always has everything


def read_metadata_csv(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    """Parse the input file. Returns ``(rows, ignored_columns)``.

    Raises :class:`MetadataDryRunError` for a file-level problem: missing,
    empty, no header, no ``symbol`` column, or no recognised metadata column.
    """
    if not path.exists():
        raise MetadataDryRunError(f"no such file: {path}")
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    reader = csv.DictReader(io.StringIO(text))
    if reader.fieldnames is None:
        raise MetadataDryRunError("input CSV is empty (no header row)")
    columns = [c.strip() for c in reader.fieldnames]
    if "symbol" not in columns:
        raise MetadataDryRunError(
            "input CSV needs a 'symbol' column; "
            f"found: {', '.join(columns) if columns else '(nothing)'}"
        )
    present_metadata = [c for c in METADATA_COLUMNS if c in columns]
    if not present_metadata:
        raise MetadataDryRunError(
            "input CSV carries no metadata to reconcile: it needs at least one of "
            f"{', '.join(METADATA_COLUMNS)} (one value per symbol; no 'proposed_*' "
            "or 'current_*' prefixes)"
        )
    ignored = [c for c in columns if c not in RECOGNIZED_COLUMNS and c not in OPTIONAL_COLUMNS]
    rows: list[dict[str, str]] = []
    for raw in reader:
        rows.append({(k.strip() if k else k): (v or "").strip() for k, v in raw.items() if k})
    if not rows:
        raise MetadataDryRunError("input CSV contained no data rows")
    return rows, ignored


def _parse_bool(value: str) -> tuple[bool | None, str | None]:
    """Parse an explicit TRUE/FALSE cell. Blank means unknown (never guessed)."""
    if value == "":
        return None, None
    low = value.strip().lower()
    if low in _TRUE:
        return True, None
    if low in _FALSE:
        return False, None
    return (
        None,
        f"delisted value {value!r} is not TRUE/FALSE/1/0/yes/no (left unknown, row rejected)",
    )


def _parse_flag(value: str) -> bool:
    return value.strip().lower() in _TRUE


def _parse_iso_timestamp(value: str, line: int) -> datetime:
    """Parse an ISO timestamp, raising MetadataDryRunError on failure."""
    try:
        dt = datetime.fromisoformat(value)
        if value.endswith("Z") and dt.tzinfo is None:
            dt = datetime.fromisoformat(value[:-1] + "+00:00")
        if dt.tzinfo is not None:
            dt = dt.astimezone(UTC).replace(tzinfo=None)
        return dt
    except ValueError as exc:
        raise MetadataDryRunError(
            f"line {line}: invalid sector_retrieved_at timestamp {value!r}: {exc}"
        ) from exc


def _parse_iso_date(value: str, line: int) -> date:
    """Parse an ISO date, raising MetadataDryRunError on failure."""
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise MetadataDryRunError(
            f"line {line}: invalid sector_observed_date {value!r}: {exc}"
        ) from exc


def build_dry_run(input_path: Path, store: MarketStore) -> dict[str, Any]:
    """Validate the input, reconcile it against the store, return the result.

    Pure with respect to the database: only
    :meth:`~megatool.market_store.MarketStore.securities_meta` is read. The
    returned dict contains no timestamps and is sorted, so identical input
    bytes plus identical store state produce identical output.
    """
    raw_bytes = input_path.read_bytes()
    rows, ignored = read_metadata_csv(input_path)

    # ---- group by symbol: duplicates collapse or become ambiguous ----------
    by_symbol: dict[str, list[tuple[int, dict[str, str]]]] = {}
    rejected: list[dict[str, Any]] = []
    for i, row in enumerate(rows, start=2):  # line 1 is the header
        raw_symbol = row.get("symbol", "").strip()
        ok, reason = is_valid_nepse_symbol(raw_symbol)
        if not ok:
            rejected.append({"line": i, "symbol": raw_symbol, "reasons": [reason]})
            continue
        symbol = raw_symbol.upper()
        by_symbol.setdefault(symbol, []).append((i, row))

    collapsed = 0
    candidates: dict[str, tuple[int, dict[str, str]]] = {}
    ambiguous: dict[str, list[dict[str, str]]] = {}
    for symbol, entries in by_symbol.items():
        # Blank/invalid symbols were rejected above; this guard stays defensive.
        if symbol == "":
            for line, _ in entries:
                rejected.append({"line": line, "symbol": "", "reasons": ["blank symbol"]})
            continue
        distinct = {
            json.dumps({k: v for k, v in r.items() if k}, sort_keys=True) for _, r in entries
        }
        if len(distinct) > 1:
            ambiguous[symbol] = [r for _, r in entries]
            continue
        collapsed += len(entries) - 1
        candidates[symbol] = entries[0]

    # ---- per-record validation --------------------------------------------
    valid: dict[str, dict[str, Any]] = {}
    for symbol in sorted(candidates):
        line, row = candidates[symbol]
        reasons: list[str] = []
        proposed: dict[str, Any] = {}
        itype = row.get("instrument_type", "")
        if itype:
            norm = itype.strip().lower()
            if norm not in ALLOWED_INSTRUMENT_TYPES:
                reasons.append(
                    f"instrument_type {itype!r} is not in the understood vocabulary "
                    f"({', '.join(sorted(ALLOWED_INSTRUMENT_TYPES))})"
                )
            else:
                proposed["instrument_type"] = norm
        status = row.get("status", "")
        if status:
            norm = status.strip().lower()
            if norm not in ALLOWED_STATUSES:
                reasons.append(
                    f"status {status!r} is not in the understood vocabulary "
                    f"({', '.join(sorted(ALLOWED_STATUSES))})"
                )
            else:
                # Store the canonical value; "listed" becomes "ACTIVE".
                proposed["status"] = STATUS_ACTIVE if norm in {"active", "listed"} else norm.upper()
        delisted, err = _parse_bool(row.get("delisted", ""))
        if err:
            reasons.append(err)
        elif delisted is not None:
            proposed["delisted"] = delisted
        name = row.get("name", "")
        if name:
            proposed["name"] = name
        sector = row.get("sector", "")
        provenance_notes: list[str] = []
        if sector:
            proposed["sector"] = sector
            sector_source = row.get("sector_source", "").strip()
            if not sector_source:
                # Fall back to the generic source column if no per-field source is given.
                sector_source = row.get("source", "").strip()
            if sector_source:
                proposed["sector_source"] = sector_source
            else:
                provenance_notes.append("sector proposed without sector_source")
            sector_retrieved_at = row.get("sector_retrieved_at", "").strip()
            if sector_retrieved_at:
                proposed["sector_retrieved_at"] = _parse_iso_timestamp(
                    sector_retrieved_at, line
                ).isoformat()
            sector_observed_date = row.get("sector_observed_date", "").strip()
            if sector_observed_date:
                proposed["sector_observed_date"] = _parse_iso_date(
                    sector_observed_date, line
                ).isoformat()
        successor = row.get("successor_symbol", "")
        if successor:
            proposed["successor_symbol"] = successor.strip().upper()
        if reasons:
            rejected.append({"line": line, "symbol": symbol, "reasons": reasons})
            continue
        valid[symbol] = {
            "proposed": proposed,
            "provenance": row.get("source", "").strip() or None,
            "manual_flag": _parse_flag(row.get("requires_manual_review", "")),
            "provenance_notes": provenance_notes,
        }

    # ---- ambiguous duplicates are conflicts, reported not guessed ----------
    conflicting: dict[str, list[dict[str, Any]]] = {}
    for symbol in sorted(ambiguous):
        conflicting[symbol] = [
            {
                "line": line,
                "values": {k: v for k, v in r.items() if k in RECOGNIZED_COLUMNS},
            }
            for line, r in by_symbol[symbol]
        ]

    # ---- reconcile against the current store (T-M1 reader) -----------------
    current = store.securities_meta()
    records: list[dict[str, Any]] = []
    summary = {
        "records_examined": len(rows),
        "rows_rejected": len(rejected),
        "rows_collapsed_duplicates": collapsed,
        "symbols_validated": len(valid),
        "symbols_ambiguous": len(ambiguous),
        "additions": 0,
        "updates": 0,
        "unchanged": 0,
        "advisory": 0,
        "no_proposal": 0,
        "conflicting": 0,
        "requires_manual_review": 0,
        "unknown_values_left_blank": 0,
    }

    for symbol in sorted(valid):
        entry = valid[symbol]
        proposed = entry["proposed"]
        cur = current.get(symbol)
        review_reasons: list[str] = []
        conflict_reasons: list[str] = []
        confidence = UNVERIFIED if entry["provenance"] else NO_PROVENANCE

        for field_name in RECONCILED_FIELDS:
            if field_name not in proposed:
                if (cur or {}).get(field_name) is None:
                    summary["unknown_values_left_blank"] += 1
                continue
            stored = (cur or {}).get(field_name)
            # Compare canonical statuses/text verbatim; None stored = unknown.
            if stored is not None and str(stored) != str(proposed[field_name]):
                conflict_reasons.append(
                    f"{field_name}: stored {stored!r} vs proposed {proposed[field_name]!r}"
                )

        # Sector-provenance reconciliation: the loader stores these columns, so
        # the dry-run must preview what would change. Timestamps/dates are parsed
        # and compared as values; stored datetimes are normalised to ISO strings
        # for deterministic JSON output.
        for prov_field in ("sector_source", "sector_retrieved_at", "sector_observed_date"):
            if prov_field not in proposed:
                continue
            stored_raw = (cur or {}).get(prov_field)
            stored_val = (
                stored_raw.isoformat() if isinstance(stored_raw, (datetime, date)) else stored_raw
            )
            if stored_val != proposed[prov_field]:
                conflict_reasons.append(
                    f"{prov_field}: stored {stored_val!r} vs proposed {proposed[prov_field]!r}"
                )

        # Carry forward any provenance notes collected during parsing.
        review_reasons.extend(entry.get("provenance_notes", []))

        if "delisted" in proposed and cur is not None and cur.get("delisted") is not None:
            if bool(cur["delisted"]) and not proposed["delisted"]:
                conflict_reasons.append(
                    "delisted: stored True vs proposed False — reactivation risk; "
                    "stored value wins until an owner decision"
                )
            elif not bool(cur["delisted"]) and proposed["delisted"]:
                conflict_reasons.append("delisted: stored False vs proposed True")

        if proposed.get("status") == STATUS_MERGED:
            # Decision D-s / B-4: merged is stored as-is, never converted to delisted.
            review_reasons.append(
                "status=MERGED: stored as a non-tradable status; not converted to DELISTED"
            )
        if proposed.get("status") == STATUS_ACTIVE and proposed.get("delisted") is True:
            review_reasons.append("status=ACTIVE but delisted=TRUE: internal tension in the file")
        if (
            proposed.get("status") in {STATUS_DELISTED, STATUS_SUSPENDED}
            and proposed.get("delisted") is False
        ):
            review_reasons.append(
                f"status={proposed['status']} but delisted=FALSE: internal tension in the file"
            )
        if proposed.get("status") == STATUS_MERGED and proposed.get("delisted") is True:
            review_reasons.append(
                "status=MERGED but delisted=TRUE: MERGED is not DELISTED (decision D-s / B-4)"
            )
        if "successor_symbol" in proposed and not proposed.get("successor_symbol"):
            review_reasons.append(
                "successor_symbol is blank: clear only if the symbol truly has no successor"
            )

        if cur is None:
            action = "addition"
            review_reasons.append(
                "symbol has no security_master row; additions require an "
                "authoritative source and an owner decision (never auto-created)"
            )
        elif conflict_reasons:
            action = "conflict"
        elif any(
            f in proposed and proposed[f] != (cur or {}).get(f)
            for f in (
                *RECONCILED_FIELDS,
                "sector_source",
                "sector_retrieved_at",
                "sector_observed_date",
            )
        ):
            # ``delisted`` compares as bool against the stored bool (or None);
            # text/status fields compare against the stored VARCHAR (None = unknown).
            action = "update"
        elif not proposed:
            action = "no-proposal"
        elif not (set(proposed) & set(RECONCILED_FIELDS)):
            # Proposed values exist but none are stored fields (should not
            # happen in normal use); reported as advisory, not reconciled.
            action = "advisory"
        else:
            action = "unchanged"

        if entry["manual_flag"]:
            review_reasons.append("input file flagged requires_manual_review=TRUE")
        if not proposed:
            review_reasons.append("row proposes no metadata values (all metadata cells blank)")
        needs_review = bool(review_reasons or conflict_reasons or action == "addition")

        if action == "addition":
            summary["additions"] += 1
        elif action == "conflict":
            summary["conflicting"] += 1
        elif action == "update":
            summary["updates"] += 1
        elif action == "unchanged":
            summary["unchanged"] += 1
        elif action == "advisory":
            summary["advisory"] += 1
        elif action == "no-proposal":
            summary["no_proposal"] += 1
        if needs_review:
            summary["requires_manual_review"] += 1

        records.append(
            {
                "symbol": symbol,
                "action": action,
                "proposed": proposed,
                "current": cur,  # None = no row; fields None = unknown in store
                "confidence": confidence,
                "provenance": entry["provenance"],
                "conflicts": conflict_reasons,
                "review_reasons": review_reasons,
                "requires_manual_review": needs_review,
            }
        )

    for symbol in sorted(conflicting):
        summary["conflicting"] += 1
        summary["requires_manual_review"] += 1
        records.append(
            {
                "symbol": symbol,
                "action": "conflict",
                "proposed": {},
                "current": current.get(symbol),
                "confidence": NO_PROVENANCE,
                "provenance": None,
                "conflicts": ["duplicate symbol rows disagree with each other (ambiguous)"],
                "review_reasons": [
                    f"row values: {json.dumps(conflicting[symbol], sort_keys=True)}"
                ],
                "requires_manual_review": True,
            }
        )

    result = {
        "tool": "metadata-dry-run",
        "version": 1,
        "input": {
            "path": str(input_path),
            "sha256": hashlib.sha256(raw_bytes).hexdigest(),
            "rows": len(rows),
        },
        "store_symbols": len(current),
        "ignored_columns": sorted(ignored),
        "summary": summary,
        "records": records,
        "rejected_records": sorted(rejected, key=lambda r: (r["symbol"], r["reasons"][0])),
        "policy": {
            "proposed_values": UNVERIFIED,
            "verified_values": "current security_master fields only",
            "blank_fields": "left unknown; never filled, never inferred",
            "merged_status": "stored as-is (MERGED); never converted to DELISTED",
            "status_column": "ACTIVE/SUSPENDED/MERGED/DELISTED/UNKNOWN stored distinctly from delisted",
            "successor_symbol": "retained only when the input supplies it; never invented",
            "production_writes": "none; this tool is read-only and imports nothing",
        },
        "vocabulary": {
            "instrument_types": sorted(ALLOWED_INSTRUMENT_TYPES),
            "input_statuses": sorted(ALLOWED_STATUSES),
            "canonical_statuses": [
                STATUS_ACTIVE,
                STATUS_SUSPENDED,
                STATUS_MERGED,
                STATUS_DELISTED,
                STATUS_UNKNOWN,
            ],
        },
    }
    return result


def render_markdown(result: dict[str, Any]) -> str:
    """Concise human-readable report; the JSON carries the complete detail."""
    s = result["summary"]
    lines = [
        "# Security-metadata dry run (no import performed)",
        "",
        f"- Input: `{result['input']['path']}` "
        f"(sha256 `{result['input']['sha256'][:16]}…`, {result['input']['rows']} rows)",
        f"- Store: {result['store_symbols']} symbols in `security_master` (read-only)",
        f"- Ignored columns: {', '.join(result['ignored_columns']) or '(none)'}",
        "",
        "Every proposed value below is **unverified source data**; only the",
        "current store values are verified. Nothing was written, no value was",
        "invented, `MERGED` was never converted to `DELISTED`, and no",
        "successor symbol was invented.",
        "",
        "## Summary",
        "",
        "| Measure | Count |",
        "|---|---|",
        f"| records examined | {s['records_examined']} |",
        f"| rows rejected (invalid) | {s['rows_rejected']} |",
        f"| duplicate rows collapsed | {s['rows_collapsed_duplicates']} |",
        f"| symbols validated | {s['symbols_validated']} |",
        f"| ambiguous symbols (conflicting duplicates) | {s['symbols_ambiguous']} |",
        f"| additions (not in store) | {s['additions']} |",
        f"| updates | {s['updates']} |",
        f"| unchanged | {s['unchanged']} |",
        f"| advisory (no stored counterpart, e.g. status only) | {s['advisory']} |",
        f"| rows proposing nothing | {s['no_proposal']} |",
        f"| conflicting | {s['conflicting']} |",
        f"| requires manual review | {s['requires_manual_review']} |",
        f"| unknown values left blank | {s['unknown_values_left_blank']} |",
        "",
    ]

    def table(title: str, rows: list[list[str]], header: list[str]) -> None:
        if not rows:
            return
        lines.append(f"## {title}")
        lines.append("")
        lines.append("| " + " | ".join(header) + " |")
        lines.append("|" + "|".join("---" for _ in header) + "|")
        for row in rows[:MAX_TABLE_ROWS]:
            clean = [str(c).replace("|", "/").replace("\n", " ") for c in row]
            lines.append("| " + " | ".join(clean) + " |")
        if len(rows) > MAX_TABLE_ROWS:
            lines.append(f"| … ({len(rows) - MAX_TABLE_ROWS} more — see the JSON) |")
        lines.append("")

    conflicts = [r for r in result["records"] if r["action"] == "conflict"]
    table(
        "Conflicts (stored value wins; owner decision required)",
        [[r["symbol"], "; ".join(r["conflicts"])[:160]] for r in conflicts],
        ["symbol", "conflict"],
    )
    additions = [r for r in result["records"] if r["action"] == "addition"]
    table(
        "Additions (symbols with no security_master row — never auto-created)",
        [[r["symbol"], ", ".join(sorted(r["proposed"])) or "(none)"] for r in additions],
        ["symbol", "proposed fields"],
    )
    rejected = result["rejected_records"]
    table(
        "Rejected rows",
        [[r["symbol"] or "(blank)", "; ".join(r["reasons"])[:160]] for r in rejected],
        ["symbol", "reason"],
    )
    review = [
        r for r in result["records"] if r["requires_manual_review"] and r["action"] != "conflict"
    ]
    table(
        "Requiring manual review",
        [[r["symbol"], r["action"], "; ".join(r["review_reasons"])[:140]] for r in review],
        ["symbol", "action", "why"],
    )
    lines += [
        "## Next step",
        "",
        "This report is the review artifact. Importing any of it into production",
        "is a separate, owner-approved operation that does not exist yet.",
        "",
    ]
    return "\n".join(lines)


class _DryRunEncoder(json.JSONEncoder):
    """Encode date/datetime as ISO strings so stored provenance survives JSON."""

    def default(self, obj: Any) -> Any:
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, date):
            return obj.isoformat()
        return super().default(obj)


def metadata_gaps(store: MarketStore) -> dict[str, Any]:
    """Report which symbols lack required metadata.

    Read-only: uses :meth:`~megatool.market_store.MarketStore.securities_meta`.
    Returns counts and symbol lists for missing sector, instrument_type, name,
    unknown status, and merged symbols without a successor. The result is sorted
    and deterministic.
    """
    meta = store.securities_meta()
    total = len(meta)

    def _missing(field: str) -> list[str]:
        return sorted(s for s, m in meta.items() if not m.get(field))

    missing_sector = _missing("sector")
    missing_instrument_type = _missing("instrument_type")
    missing_name = _missing("name")
    unknown_status = sorted(s for s, m in meta.items() if m.get("status") == STATUS_UNKNOWN)
    merged_without_successor = sorted(
        s
        for s, m in meta.items()
        if m.get("status") == STATUS_MERGED and not m.get("successor_symbol")
    )
    incomplete = sorted(
        {
            s
            for s, m in meta.items()
            if not m.get("sector")
            or not m.get("instrument_type")
            or not m.get("name")
            or m.get("status") == STATUS_UNKNOWN
        }
    )

    return {
        "tool": "metadata-gaps",
        "version": 1,
        "store_symbols": total,
        "complete_records": total - len(incomplete),
        "incomplete_symbols": incomplete,
        "gaps": {
            "sector": {"count": len(missing_sector), "symbols": missing_sector},
            "instrument_type": {
                "count": len(missing_instrument_type),
                "symbols": missing_instrument_type,
            },
            "name": {"count": len(missing_name), "symbols": missing_name},
            "status_unknown": {
                "count": len(unknown_status),
                "symbols": unknown_status,
            },
            "merged_without_successor": {
                "count": len(merged_without_successor),
                "symbols": merged_without_successor,
            },
        },
    }


def render_gaps_markdown(result: dict[str, Any]) -> str:
    """Human-readable gap report."""
    lines = [
        "# Security-metadata gap report",
        "",
        f"- Symbols in `security_master`: **{result['store_symbols']}**",
        f"- Complete records (sector, instrument_type, name and status all present): "
        f"**{result['complete_records']}**",
        "",
        "## Gap summary",
        "",
        "| Gap | Count |",
        "|---|---|",
    ]
    for key, item in result["gaps"].items():
        label = key.replace("_", " ").title()
        lines.append(f"| {label} | {item['count']} |")
    lines.append("")
    for key, item in result["gaps"].items():
        if not item["symbols"]:
            continue
        label = key.replace("_", " ").title()
        lines.append(f"## {label}")
        lines.append("")
        lines.append(", ".join(item["symbols"][:50]))
        if len(item["symbols"]) > 50:
            lines.append(f"\n… and {len(item['symbols']) - 50} more.")
        lines.append("")
    return "\n".join(lines)


def result_json(result: dict[str, Any]) -> str:
    """Canonical, deterministic serialisation (sorted keys, no timestamps)."""
    return (
        json.dumps(result, sort_keys=True, indent=2, ensure_ascii=False, cls=_DryRunEncoder) + "\n"
    )


def write_outputs(result: dict[str, Any], out_dir: Path) -> dict[str, Path]:
    """Write ``<stem>_dryrun.json`` and ``<stem>_dryrun.md`` into ``out_dir``.

    Refuses to overwrite anything: if either target already exists the write
    aborts with :class:`MetadataDryRunError` (decision D-w). Returns the paths
    that were written.
    """
    stem = Path(result["input"]["path"]).stem
    json_path = out_dir / f"{stem}_dryrun.json"
    md_path = out_dir / f"{stem}_dryrun.md"
    for target in (json_path, md_path):
        if target.exists():
            raise MetadataDryRunError(
                f"refusing to overwrite {target}; previous dry-run artifacts are "
                "kept as evidence — choose a different --out-dir or remove it yourself"
            )
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path.write_text(result_json(result), encoding="utf-8")
    md_path.write_text(render_markdown(result), encoding="utf-8")
    return {"json": json_path, "markdown": md_path}
