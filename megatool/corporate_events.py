"""Corporate-event calendar (NF-004 / NF-020 — the feasible part).

What this module refuses to do
------------------------------
There is no licensed feed for dividend, bonus, rights, IPO, allotment or AGM
notices in this project, and none of those facts can be derived from a price
series. So this module **never invents an event**. It provides:

* an *import surface* — a typed, sourced row can be recorded from a document a
  human supplied (the same ``text``/rows pattern the floorsheet and PDF
  importers already use), and
* a *projection* of the attested retirement/merger registry, which already
  carries real observed dates and is therefore usable today.

Calling :func:`coverage` returns an explicit statement of which event types are
populated and which are absent, so a caller is never left guessing whether an
empty calendar means "no events" or "no data".

A row records its ``source``, ``source_ref``, ``evidence`` and ``grade`` for the
same reason fundamentals do: an unverified notice must be visible as unverified
rather than silently averaged into a decision.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

__all__ = [
    "CorporateEvent",
    "CorporateEventError",
    "EVENT_TYPES",
    "GRADES",
    "calendar",
    "coverage",
    "import_events",
    "list_events",
    "parse_events_csv",
    "registry_events",
    "summary",
]


class CorporateEventError(ValueError):
    """A corporate event could not be accepted as presented."""


#: The event vocabulary. ``retirement`` and ``merger`` come from the registry;
#: the rest require a supplied notice.
EVENT_TYPES: tuple[str, ...] = (
    "dividend",
    "bonus",
    "rights",
    "ipo",
    "allotment",
    "agm",
    "split",
    "merger",
    "retirement",
    "other",
)

#: How firmly the event is known. ``attested`` means a public notice/observation
#: backs it; ``reported`` means someone supplied it and it has not been checked.
GRADES: tuple[str, ...] = ("attested", "reported", "unverified")

_SYMBOL_RE = re.compile(r"^[A-Z0-9][A-Z0-9._-]{0,14}$")
_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

#: Event types that are fundamentally about a *notice* and cannot be inferred.
NOTICE_ONLY_TYPES: frozenset[str] = frozenset(
    {"dividend", "bonus", "rights", "ipo", "allotment", "agm", "split"}
)


@dataclass
class CorporateEvent:
    """One dated corporate notice or attested action involving ``symbol``."""

    symbol: str
    event_type: str
    effective_date: str = ""
    headline: str = ""
    value: float | None = None
    unit: str = ""
    ratio: str = ""
    successor: str = ""
    source: str = ""
    source_ref: str = ""
    evidence: str = ""
    grade: str = "reported"
    notes: str = ""
    retrieved_at: str = ""

    def validate(self) -> None:
        sym = str(self.symbol or "").strip().upper()
        if not _SYMBOL_RE.match(sym):
            raise CorporateEventError(f"invalid symbol {self.symbol!r}")
        self.symbol = sym
        self.event_type = str(self.event_type or "").strip().lower()
        if self.event_type not in EVENT_TYPES:
            raise CorporateEventError(
                f"unknown event_type {self.event_type!r}; choose from {list(EVENT_TYPES)}"
            )
        if not self.source:
            raise CorporateEventError("a corporate event must name its source")
        if self.grade not in GRADES:
            raise CorporateEventError(f"grade must be one of {list(GRADES)}, got {self.grade!r}")
        if self.effective_date and not _DATE_RE.match(self.effective_date):
            raise CorporateEventError(
                f"effective_date must be ISO YYYY-MM-DD or empty, got {self.effective_date!r}"
            )
        if self.event_type in NOTICE_ONLY_TYPES and not self.effective_date:
            # A notice without a date cannot be placed on a calendar, and
            # guessing one would make the calendar wrong. Refuse it.
            raise CorporateEventError(
                f"a {self.event_type} event needs an effective_date; none may be inferred"
            )
        if self.ratio and not re.match(r"^\d+(\.\d+)?\s*:\s*\d+(\.\d+)?$", self.ratio):
            raise CorporateEventError(f"ratio must look like '1:2', got {self.ratio!r}")

    def to_row(self) -> dict[str, Any]:
        self.validate()
        return {
            "symbol": self.symbol,
            "event_type": self.event_type,
            "effective_date": self.effective_date,
            "headline": self.headline,
            "value": self.value,
            "unit": self.unit,
            "ratio": self.ratio,
            "successor": self.successor,
            "source": self.source,
            "source_ref": self.source_ref,
            "evidence": self.evidence,
            "grade": self.grade,
            "notes": self.notes,
            "retrieved_at": self.retrieved_at,
        }


def _now() -> str:
    from megatool.db import now_iso

    return now_iso()


# --------------------------------------------------------------------------- #
# Import
# --------------------------------------------------------------------------- #

def _coerce(row: dict[str, Any]) -> CorporateEvent:
    value = row.get("value")
    if value in ("", None):
        value = None
    else:
        try:
            value = float(value)
        except (TypeError, ValueError) as exc:
            raise CorporateEventError(f"value {row.get('value')!r} is not a number") from exc
    return CorporateEvent(
        symbol=str(row.get("symbol", "")),
        event_type=str(row.get("event_type", row.get("type", ""))),
        effective_date=str(row.get("effective_date", row.get("date", "")) or ""),
        headline=str(row.get("headline", "") or ""),
        value=value,
        unit=str(row.get("unit", "") or ""),
        ratio=str(row.get("ratio", "") or ""),
        successor=str(row.get("successor", "") or ""),
        source=str(row.get("source", "") or ""),
        source_ref=str(row.get("source_ref", "") or ""),
        evidence=str(row.get("evidence", "") or ""),
        grade=str(row.get("grade", "reported") or "reported").lower(),
        notes=str(row.get("notes", "") or ""),
        retrieved_at=str(row.get("retrieved_at", "") or _now()),
    )


def import_events(rows: list[dict[str, Any]], conn: Any) -> dict[str, int]:
    """Persist supplied corporate events; identical rows overwrite in place.

    The identity is ``(symbol, event_type, effective_date, source)`` so two
    sources reporting the same notice are both kept and can later be
    reconciled rather than silently deduplicated.
    """
    inserted = updated = rejected = 0
    for raw in rows:
        try:
            event = _coerce(raw)
            row = event.to_row()
        except CorporateEventError:
            rejected += 1
            continue
        prior = conn.execute(
            "SELECT value FROM corporate_events WHERE symbol = ? AND event_type = ? "
            "AND effective_date = ? AND source = ?",
            (row["symbol"], row["event_type"], row["effective_date"], row["source"]),
        ).fetchone()
        conn.execute(
            """
            INSERT INTO corporate_events
              (symbol, event_type, effective_date, headline, value, unit, ratio,
               successor, source, source_ref, evidence, grade, notes, retrieved_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(symbol, event_type, effective_date, source) DO UPDATE SET
              headline=excluded.headline,
              value=excluded.value,
              unit=excluded.unit,
              ratio=excluded.ratio,
              successor=excluded.successor,
              source_ref=excluded.source_ref,
              evidence=excluded.evidence,
              grade=excluded.grade,
              notes=excluded.notes,
              retrieved_at=excluded.retrieved_at
            """,
            (
                row["symbol"], row["event_type"], row["effective_date"], row["headline"],
                row["value"], row["unit"], row["ratio"], row["successor"], row["source"],
                row["source_ref"], row["evidence"], row["grade"], row["notes"],
                row["retrieved_at"],
            ),
        )
        if prior is None:
            inserted += 1
        else:
            updated += 1
    return {"inserted": inserted, "updated": updated, "rejected": rejected, "total": len(rows)}


def parse_events_csv(text: str, *, source: str = "supplied") -> list[dict[str, Any]]:
    """Parse a CSV of corporate events.

    Recognised headers: ``symbol,event_type,effective_date,value,unit,ratio,
    successor,headline,evidence,grade,source_ref,notes``. An unknown header is
    ignored, but a row missing ``symbol`` or ``event_type`` is dropped by the
    validator rather than guessed at.
    """
    import csv
    import io

    if not text or not text.strip():
        raise CorporateEventError("empty corporate-event document")
    reader = csv.DictReader(io.StringIO(text))
    rows: list[dict[str, Any]] = []
    for raw in reader:
        cleaned = {str(k).strip().lower(): (v.strip() if isinstance(v, str) else v)
                   for k, v in raw.items() if k is not None}
        cleaned.setdefault("source", source)
        rows.append(cleaned)
    if not rows:
        raise CorporateEventError("no data rows found in corporate-event document")
    return rows


# --------------------------------------------------------------------------- #
# Registry projection
# --------------------------------------------------------------------------- #

def registry_events() -> list[dict[str, Any]]:
    """The attested retirement/merger registry, shaped as calendar events.

    These rows carry real observed dates (``last_trade_date`` and, where known,
    ``successor_first_date``) and their evidence strings. They are marked
    ``attested`` because each registry entry states its attestation.
    """
    from megatool.corporate_actions import VERIFIED_CORPORATE_ACTIONS

    out: list[dict[str, Any]] = []
    for action in VERIFIED_CORPORATE_ACTIONS:
        rel = str(action.relationship or "").lower()
        event_type = "merger" if "merg" in rel or "amalgam" in rel else "retirement"
        when = action.last_trade_date or action.successor_first_date or ""
        out.append({
            "symbol": action.symbol,
            "event_type": event_type,
            "effective_date": when,
            "headline": (
                f"{action.company_name} -> {action.successor_name}"
                if action.successor_name else f"{action.company_name} retired"
            ),
            "successor": action.successor or "",
            "source": "corporate_actions:registry",
            "source_ref": action.successor_first_date or "",
            "evidence": "; ".join(action.evidence or ()),
            "grade": "attested",
            "notes": (
                "Projected from the attested corporate-action registry; dates are "
                "observed last-trade / successor-first dates, not notice dates."
            ),
            "retrieved_at": "",
        })
    return out


# --------------------------------------------------------------------------- #
# Query
# --------------------------------------------------------------------------- #

def _row_to_dict(row: Any) -> dict[str, Any]:
    return dict(row)


def list_events(
    conn: Any,
    *,
    symbol: str | None = None,
    event_type: str | None = None,
    since: str | None = None,
    until: str | None = None,
    include_registry: bool = True,
    limit: int = 500,
) -> list[dict[str, Any]]:
    """Stored events, newest first, optionally filtered.

    ``include_registry`` merges the attested registry projection in so a caller
    sees the real dated actions without having to import them.
    """
    limit = max(1, min(int(limit), 5000))
    clauses: list[str] = []
    params: list[Any] = []
    if symbol:
        clauses.append("symbol = ?")
        params.append(str(symbol).upper())
    if event_type:
        clauses.append("event_type = ?")
        params.append(str(event_type).lower())
    if since:
        clauses.append("effective_date >= ?")
        params.append(str(since)[:10])
    if until:
        clauses.append("effective_date <= ?")
        params.append(str(until)[:10])
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    rows = [_row_to_dict(r) for r in conn.execute(
        f"SELECT * FROM corporate_events {where} "  # noqa: S608 - fixed clauses
        "ORDER BY effective_date DESC, id DESC LIMIT ?",
        (*params, limit),
    ).fetchall()]
    if include_registry:
        for ev in registry_events():
            if symbol and ev["symbol"] != str(symbol).upper():
                continue
            if event_type and ev["event_type"] != str(event_type).lower():
                continue
            if since and (ev["effective_date"] or "") < str(since)[:10]:
                continue
            if until and (ev["effective_date"] or "") > str(until)[:10]:
                continue
            rows.append(ev)
    rows.sort(key=lambda r: (str(r.get("effective_date") or ""), str(r.get("symbol") or "")),
              reverse=True)
    return rows[:limit]


def calendar(conn: Any, *, since: str | None = None, until: str | None = None,
             limit: int = 500) -> dict[str, Any]:
    """A dated calendar view over the stored events plus the registry."""
    events = list_events(conn, since=since, until=until, limit=limit)
    return {
        "since": since,
        "until": until,
        "events": events,
        "count": len(events),
        "note": (
            "The calendar lists only recorded events. A notice type with no rows "
            "means no notice has been imported, not that no such event occurred."
        ),
    }


def summary(conn: Any) -> dict[str, Any]:
    """Counts per event type, separating stored rows from registry rows."""
    stored = {str(r["event_type"]): int(r["n"]) for r in conn.execute(
        "SELECT event_type, COUNT(*) AS n FROM corporate_events GROUP BY event_type"
    ).fetchall()}
    registry = registry_events()
    projected: dict[str, int] = {}
    for ev in registry:
        projected[ev["event_type"]] = projected.get(ev["event_type"], 0) + 1
    return {
        "stored": stored,
        "stored_total": sum(stored.values()),
        "registry_projected": projected,
        "registry_total": len(registry),
        "event_types": list(EVENT_TYPES),
    }


def coverage(conn: Any) -> dict[str, Any]:
    """Exactly which event types are populated and which have no data at all."""
    counts = summary(conn)
    populated = set(counts["stored"]) | set(counts["registry_projected"])
    missing = [t for t in NOTICE_ONLY_TYPES if t not in counts["stored"]]
    return {
        **counts,
        "populated_types": sorted(populated),
        "missing_notice_types": missing,
        "status": "ok" if counts["stored_total"] else "no_imported_notices",
        "limitation": (
            "Dividend, bonus, rights, IPO, allotment, AGM and split notices are NOT "
            "available from a licensed feed in this project and are NOT derivable from "
            "prices. Those types stay empty until a document is supplied; an empty list "
            "means 'no notice imported', never 'no event occurred'. Retirement/merger "
            "rows come from the attested registry (real observed dates) and are marked "
            "grade='attested'; imported rows default to grade='reported' and are "
            "unverified until checked."
        ),
    }
