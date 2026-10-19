"""Fundamentals storage, import, and guarded ratio calculation.

Priority 4 of ``MEGA_TOOL_RESEARCH_REPORT.md`` (section 7).

Ground rules this module enforces
---------------------------------
* **Provenance travels with the value.** A fundamental is never stored without
  its source, its reporting period, its unit, and a verification status.
* **Historical observations are not current fundamentals.** Records imported
  from the handwritten journal carry ``verification="extracted"`` and, when the
  page does not state a period, ``period_end=None``. Neither may be used as if
  it were today's figure.
* **Ratios refuse incompatible inputs.** ``pe``/``pb``/``dividend_yield``
  require a price and a fundamental whose reporting periods are known and not
  stale relative to each other. Unverified inputs are refused rather than
  quietly divided.
* **No source is assumed to permit collection.** Import is explicit and
  file-based (CSV/Excel). Nothing here fetches from the network.
"""

from __future__ import annotations

import csv
import io
import math
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

__all__ = [
    "FundamentalError",
    "FundamentalRecord",
    "KNOWN_FIELDS",
    "VERIFICATION_LEVELS",
    "ratio_pe",
    "ratio_pb",
    "ratio_dividend_yield",
    "records_from_rows",
    "records_to_rows",
    "import_records",
    "query_symbol",
    "query_revisions",
    "revision_monitor",
    "query_symbol_as_of",
    "point_in_time_coverage",
    "fundamentals_summary",
    "review_source",
]


class FundamentalError(ValueError):
    """A fundamental could not be accepted as presented."""


#: Field -> (unit, human label). Units are stored explicitly so a ratio can
#: refuse to divide mismatched quantities.
KNOWN_FIELDS: dict[str, dict[str, str]] = {
    "eps": {"unit": "NPR", "label": "Earnings per share"},
    "net_worth_per_share": {"unit": "NPR", "label": "Net worth per share"},
    "book_value_per_share": {"unit": "NPR", "label": "Book value per share"},
    "dps": {"unit": "NPR", "label": "Dividend per share"},
    "paid_up_capital": {"unit": "NPR", "label": "Paid-up capital"},
    "reserve": {"unit": "NPR", "label": "Reserve fund"},
    "profit": {"unit": "NPR", "label": "Net profit"},
    "revenue": {"unit": "NPR", "label": "Revenue"},
    "total_shares": {"unit": "shares", "label": "Total shares outstanding"},
    "market_cap": {"unit": "NPR", "label": "Market capitalisation"},
    "promoter_holding": {"unit": "percent", "label": "Promoter holding"},
    "public_holding": {"unit": "percent", "label": "Public holding"},
    "price": {"unit": "NPR", "label": "Price"},
}

#: Ordered least to most trustworthy. A higher level implies the lower ones
#: were satisfied by whoever assigned it.
VERIFICATION_LEVELS = ("extracted", "reviewed", "verified")

#: Reporting periods closer together than this are treated as the same period
#: for ratio purposes (one quarter is ~91 days).
PERIOD_TOLERANCE_DAYS = 120

#: A fundamental older than this relative to the price is "stale".
STALE_AFTER_DAYS = 400


@dataclass(slots=True)
class FundamentalRecord:
    """One fundamental value, with everything needed to audit it."""

    symbol: str
    field: str
    value: float
    unit: str
    source: str
    source_ref: str = ""
    period_end: date | None = None
    period_label: str = ""
    retrieved_at: str = ""
    verification: str = "extracted"
    notes: str = ""

    # ---------------------------------------------------------------- checks
    def validate(self) -> None:
        if not self.symbol or not self.symbol.isascii():
            raise FundamentalError(f"symbol must be non-empty ASCII, got {self.symbol!r}")
        if not self.symbol.replace(".", "").replace("-", "").isalnum():
            raise FundamentalError(f"symbol {self.symbol!r} is not a valid NEPSE symbol")
        if not self.field or not self.field.replace("_", "").isalnum():
            raise FundamentalError(f"field {self.field!r} is not a valid field name")
        # A known field must carry its declared unit. An unrecognised field is
        # allowed (organisations publish their own metrics) but must state its
        # unit explicitly - records_from_rows enforces that at parse time.
        if self.field in KNOWN_FIELDS and self.unit != KNOWN_FIELDS[self.field]["unit"]:
            raise FundamentalError(
                f"unit for {self.field} must be {KNOWN_FIELDS[self.field]['unit']!r}, "
                f"got {self.unit!r}"
            )
        if not self.unit.strip():
            raise FundamentalError(
                f"unit is required for {self.field}; a bare number is meaningless"
            )
        if not isinstance(self.value, (int, float)) or isinstance(self.value, bool):
            raise FundamentalError(f"value for {self.field} must be numeric")
        if not math.isfinite(float(self.value)):
            raise FundamentalError(f"value for {self.field} must be finite")
        if self.verification not in VERIFICATION_LEVELS:
            raise FundamentalError(
                f"verification must be one of {VERIFICATION_LEVELS}, got {self.verification!r}"
            )
        if not self.source.strip():
            raise FundamentalError("source is required; a value without a source cannot be used")

    @property
    def known_field(self) -> bool:
        return self.field in KNOWN_FIELDS

    @property
    def period_known(self) -> bool:
        return self.period_end is not None

    def to_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "field": self.field,
            "value": self.value,
            "unit": self.unit,
            "source": self.source,
            "source_ref": self.source_ref,
            "period_end": self.period_end.isoformat() if self.period_end else None,
            "period_label": self.period_label,
            "retrieved_at": self.retrieved_at,
            "verification": self.verification,
            "notes": self.notes,
            "period_known": self.period_known,
        }


# ------------------------------------------------------------------ CSV / Excel
REQUIRED_COLUMNS = ("symbol", "field", "value", "source")
OPTIONAL_COLUMNS = (
    "unit",
    "period_end",
    "period_label",
    "source_ref",
    "verification",
    "notes",
)


def _parse_date(raw: Any) -> date | None:
    if raw is None:
        return None
    text = str(raw).strip()
    if not text or text.lower() in {"", "nan", "none", "null", "?"}:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%Y/%m/%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise FundamentalError(f"unrecognised date {raw!r}; use YYYY-MM-DD")
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        try:
            v = float(value)
            return v if math.isfinite(v) else None
        except (TypeError, ValueError):
            return None
    try:
        return float(str(value).strip().replace(",", ""))
    except (TypeError, ValueError):
        return None
    if raw is None:
        return None
    text = str(raw).strip()
    if not text or text.lower() in {"", "nan", "none", "null", "?"}:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%Y/%m/%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    raise FundamentalError(f"unrecognised date {raw!r}; use YYYY-MM-DD")


def _parse_value(raw: Any) -> float:
    if raw is None:
        raise FundamentalError("value is empty")
    if isinstance(raw, bool):
        raise FundamentalError("value must be numeric")
    if isinstance(raw, (int, float)):
        return float(raw)
    text = str(raw).strip().replace(",", "")
    if text.endswith("%"):
        text = text[:-1]
    try:
        return float(text)
    except ValueError as exc:
        raise FundamentalError(f"value {raw!r} is not numeric") from exc


def _is_blank(value: Any) -> bool:
    """Blank means ``None`` or an empty/whitespace string — never a real 0.

    ``row.get(c, "") or ""`` is tempting but wrong: ``0 or ""`` is ``""``, so a
    genuine ``0.0`` (a P/E of exactly zero, a nil dividend) would be reported as
    a *missing* column and the whole file refused. Missing and zero are
    different facts and are kept different here.
    """
    return value is None or str(value).strip() == ""


def records_from_rows(rows: Iterable[dict[str, Any]]) -> list[FundamentalRecord]:
    """Build and validate records from parsed CSV/Excel rows.

    Rows missing a required column are rejected with a message naming the
    column, rather than being skipped silently.
    """
    records: list[FundamentalRecord] = []
    seen: set[tuple[str, str, str | None]] = set()
    for idx, row in enumerate(rows, start=2):  # row 1 is the header
        if row is None:
            continue
        missing = [c for c in REQUIRED_COLUMNS if _is_blank(row.get(c))]
        if missing:
            raise FundamentalError(f"row {idx}: missing required column(s): {', '.join(missing)}")

        symbol = str(row["symbol"]).strip().upper()
        field_name = str(row["field"]).strip().lower()
        value = _parse_value(row["value"])
        source = str(row["source"]).strip()

        unit = str(row.get("unit", "") or "").strip()
        if not unit:
            if field_name not in KNOWN_FIELDS:
                raise FundamentalError(
                    f"row {idx}: field {field_name!r} needs an explicit unit "
                    f"because it is not a known field"
                )
            unit = KNOWN_FIELDS[field_name]["unit"]

        rec = FundamentalRecord(
            symbol=symbol,
            field=field_name,
            value=value,
            unit=unit,
            source=source,
            source_ref=str(row.get("source_ref", "") or "").strip(),
            period_end=_parse_date(row.get("period_end")),
            period_label=str(row.get("period_label", "") or "").strip(),
            verification=str(row.get("verification", "") or "extracted").strip().lower()
            or "extracted",
            notes=str(row.get("notes", "") or "").strip(),
        )
        try:
            rec.validate()
        except FundamentalError as exc:
            raise FundamentalError(f"row {idx}: {exc}") from exc

        key = (rec.symbol, rec.field, rec.period_end.isoformat() if rec.period_end else None)
        if key in seen:
            raise FundamentalError(
                f"row {idx}: duplicate {rec.field} for {rec.symbol} at {key[2]} - "
                "resolve the conflict explicitly instead of letting one overwrite the other"
            )
        seen.add(key)
        records.append(rec)
    if not records:
        raise FundamentalError("no rows found in the file")
    return records


def read_csv(text: str) -> list[dict[str, Any]]:
    """Parse a CSV payload (the API accepts text, so Excel is converted first)."""
    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        raise FundamentalError("file has no header row")
    return list(reader)


def records_to_rows(records: list[FundamentalRecord]) -> list[dict[str, Any]]:
    return [r.to_dict() for r in records]


# ------------------------------------------------------------- ratio guards
def _refuse_unverified(rec: FundamentalRecord, name: str) -> None:
    if rec.verification == "extracted":
        raise FundamentalError(
            f"{name} for {rec.symbol} is only 'extracted' (not reviewed); "
            "an unreviewed value must not drive a ratio"
        )


def _refuse_unknown_period(rec: FundamentalRecord, name: str) -> None:
    if not rec.period_known:
        raise FundamentalError(
            f"{name} for {rec.symbol} has no reporting period; a value of unknown "
            "vintage cannot be combined with a current price"
        )


def _refuse_wrong_field(rec: FundamentalRecord, allowed: tuple[str, ...], name: str) -> None:
    """Refuse an operand that is not the field the ratio actually needs.

    Without this, ``ratio_pe(500.0, revenue_record)`` returned ``0.1`` and was
    presented as a P/E - a plausible-looking number with no meaning. Python
    does not enforce the ``eps: FundamentalRecord`` annotation, so the check
    has to be real.
    """
    if rec.field not in allowed:
        need = " or ".join(allowed)
        raise FundamentalError(
            f"{name}: {rec.symbol} supplied field {rec.field!r}, but this ratio requires {need}"
        )


def _refuse_wrong_unit(rec: FundamentalRecord, unit: str, name: str) -> None:
    """Refuse a value measured in something other than the expected unit.

    ``KNOWN_FIELDS`` stores a unit per field precisely so a ratio can refuse to
    divide mismatched quantities; that promise is only kept if it is enforced.
    """
    if rec.unit != unit:
        raise FundamentalError(
            f"{name}: {rec.symbol} field {rec.field!r} is in {rec.unit!r}, "
            f"but this ratio requires {unit!r}"
        )


def _period_gap_days(a: FundamentalRecord, b: FundamentalRecord) -> int:
    assert a.period_end is not None and b.period_end is not None
    return abs((a.period_end - b.period_end).days)


def _refuse_stale(rec: FundamentalRecord, price_as_of: date, name: str) -> None:
    """Refuse a figure whose reporting period is too old for ``price_as_of``.

    ``price_as_of`` is a *required* argument of every ratio in this module so
    the check cannot be skipped by omission: leaving it out previously defaulted
    to ``None``, which silently disabled this guard and let an EPS from 2015 be
    divided into a current price. Nothing in the app computes a ratio yet, so
    making it mandatory costs no caller anything.
    """
    if rec.period_end is None:
        return  # already refused by _refuse_unknown_period upstream
    age = (price_as_of - rec.period_end).days
    if age > STALE_AFTER_DAYS:
        raise FundamentalError(
            f"{name}: the reporting period ended {age} days before the price "
            f"date; refusing a stale figure (limit {STALE_AFTER_DAYS} days)"
        )


def _as_record(x: FundamentalRecord | float, name: str) -> FundamentalRecord | None:
    if isinstance(x, FundamentalRecord):
        return x
    if isinstance(x, bool) or not isinstance(x, (int, float)) or not math.isfinite(float(x)):
        raise FundamentalError(f"{name} must be a finite number or a FundamentalRecord")
    return None


def _combine(
    numerator: FundamentalRecord | float,
    denominator: FundamentalRecord | float,
    label: str,
    price_as_of: date,
) -> float:
    """Shared guard: every operand must be usable and periods compatible.

    Either operand may be a plain number (a price taken from the market store,
    which carries its own date) or a stored :class:`FundamentalRecord`. Any
    record operand must be reviewed, carry a reporting period, and not be stale
    relative to ``price_as_of``.

    ``price_as_of`` is mandatory: without a price date there is no way to know
    whether a vintage is current, and an omitted date must not mean "skip the
    freshness check".
    """
    top_rec = _as_record(numerator, "numerator")
    bot_rec = _as_record(denominator, "denominator")

    for rec, name in ((top_rec, "numerator"), (bot_rec, "denominator")):
        if rec is None:
            continue
        _refuse_unverified(rec, label)
        _refuse_unknown_period(rec, f"{label} ({name})")

    if top_rec is not None and bot_rec is not None:
        gap = _period_gap_days(top_rec, bot_rec)
        if gap > PERIOD_TOLERANCE_DAYS:
            raise FundamentalError(
                f"{label}: reporting periods differ by {gap} days "
                f"({top_rec.period_end} vs {bot_rec.period_end}); values from "
                f"periods more than {PERIOD_TOLERANCE_DAYS} days apart must not "
                "be combined"
            )

    # Staleness is always checked; price_as_of is mandatory (see _refuse_stale).
    for rec, name in ((top_rec, "numerator"), (bot_rec, "denominator")):
        if rec is not None:
            _refuse_stale(rec, price_as_of, f"{label} ({name})")

    top = float(numerator.value) if top_rec is not None else float(numerator)
    bottom = float(denominator.value) if bot_rec is not None else float(denominator)

    if math.isclose(bottom, 0.0):
        raise FundamentalError(f"{label}: denominator is zero")
    result = top / bottom
    if not math.isfinite(result):
        raise FundamentalError(f"{label}: result is not finite")
    return result


def ratio_pe(
    price: FundamentalRecord | float,
    eps: FundamentalRecord,
    *,
    price_as_of: date,
) -> float:
    """Price-to-earnings = price / EPS.

    Requires a reviewed/verified EPS with a known reporting period. A
    non-positive EPS makes the ratio meaningless rather than merely negative,
    so it is refused with the actual value in the message.

    ``price_as_of`` is required so the staleness check below cannot be
    bypassed by omitting it.
    """
    _refuse_wrong_field(eps, ("eps",), "P/E")
    _refuse_wrong_unit(eps, "NPR", "P/E (EPS)")
    if eps.value <= 0:
        raise FundamentalError(f"P/E refused: EPS is {eps.value}, which is not positive")
    return _combine(price, eps, "P/E", price_as_of)


def eps_available_as_of(
    conn: Any,
    symbol: str,
    as_of: date,
) -> FundamentalRecord | None:
    """Return the most recent EPS record available as of ``as_of``.

    Prevents lookahead: only EPS records whose period_end is on or before
    ``as_of`` are considered. Returns None if no such record exists.
    """
    sym = symbol.upper()
    rows = conn.execute(
        "SELECT value, period_end, period_label, verification, source, unit "
        "FROM fundamentals WHERE symbol = ? AND field = 'eps' AND period_end <= ? "
        "ORDER BY period_end DESC LIMIT 1",
        (sym, as_of.isoformat()),
    ).fetchall()
    if not rows:
        return None
    r = rows[0]
    rec = FundamentalRecord(
        symbol=sym,
        field="eps",
        value=r["value"],
        period_end=date.fromisoformat(r["period_end"]),
        period_label=r["period_label"],
        unit=r["unit"],
        source=r["source"],
        verification=r["verification"],
    )
    return rec


def historical_pe(
    conn: Any,
    symbol: str,
    price: float,
    price_date: date,
) -> dict[str, Any]:
    """Compute point-in-time P/E using only EPS available as of price_date.

    Prevents lookahead: uses eps_available_as_of() to find the most recent
    EPS reported on or before price_date.
    """
    eps_rec = eps_available_as_of(conn, symbol, price_date)
    if eps_rec is None:
        return {
            "symbol": symbol.upper(),
            "price": price,
            "price_date": price_date.isoformat(),
            "pe": None,
            "eps_used": None,
            "eps_period_end": None,
            "reason": "no EPS record available as of this date (lookahead prevention)",
            "method": "point-in-time",
        }
    try:
        pe = ratio_pe(price, eps_rec, price_as_of=price_date)
    except FundamentalError as exc:
        return {
            "symbol": symbol.upper(),
            "price": price,
            "price_date": price_date.isoformat(),
            "pe": None,
            "eps_used": eps_rec.value,
            "eps_period_end": eps_rec.period_end.isoformat(),
            "reason": str(exc),
            "method": "point-in-time",
        }
    return {
        "symbol": symbol.upper(),
        "price": price,
        "price_date": price_date.isoformat(),
        "pe": round(pe, 4),
        "eps_used": eps_rec.value,
        "eps_period_end": eps_rec.period_end.isoformat(),
        "reason": None,
        "method": "point-in-time",
    }


def ratio_pb(
    price: FundamentalRecord | float,
    net_worth: FundamentalRecord,
    *,
    price_as_of: date,
) -> float:
    """Price-to-book = price / net worth per share. Same guards as P/E."""
    _refuse_wrong_field(net_worth, ("net_worth_per_share", "book_value_per_share"), "P/B")
    _refuse_wrong_unit(net_worth, "NPR", "P/B (book value per share)")
    if net_worth.value <= 0:
        raise FundamentalError(
            f"P/B refused: net worth per share is {net_worth.value}, which is not positive"
        )
    return _combine(price, net_worth, "P/B", price_as_of)


def ratio_dividend_yield(
    dps: FundamentalRecord,
    price: float,
    *,
    price_as_of: date,
) -> float:
    """Dividend yield as a percentage. DPS must be non-negative and reviewed.

    ``price_as_of`` is required here too: a DPS of unknown vintage, or one too
    old for the price date, would otherwise produce a yield that looks current.
    """
    _refuse_wrong_field(dps, ("dps",), "dividend yield")
    _refuse_wrong_unit(dps, "NPR", "dividend yield (DPS)")
    if dps.value < 0:
        raise FundamentalError(f"yield refused: DPS is {dps.value}, which is negative")
    if price <= 0:
        raise FundamentalError(f"yield refused: price is {price}, which is not positive")
    _refuse_unverified(dps, "dividend yield")
    _refuse_unknown_period(dps, "dividend yield")
    _refuse_stale(dps, price_as_of, "dividend yield")
    return float(dps.value) / float(price) * 100.0


# ------------------------------------------------------------------- storage
def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def import_records(
    records: list[FundamentalRecord],
    conn: Any,
) -> dict[str, int]:
    """Persist records. Re-importing the same identity overwrites in place.

    The identity is ``(symbol, field, period_end, source)`` so two sources
    reporting different values for the same period are both kept.

    When a re-import *changes* an existing value, the previous and new value are
    appended to ``fundamental_revisions``. That history starts when the table is
    introduced: values imported before it existed have no recoverable history and
    the revision monitor reports them as unknown rather than inventing a change.
    """
    inserted = updated = 0
    for rec in records:
        period_end = rec.period_end.isoformat() if rec.period_end else ""
        prior = conn.execute(
            "SELECT value FROM fundamentals WHERE symbol = ? AND field = ? "
            "AND period_end = ? AND source = ?",
            (rec.symbol, rec.field, period_end, rec.source),
        ).fetchone()
        conn.execute(
            """
            INSERT INTO fundamentals
              (symbol, field, value, unit, period_end, period_label,
               source, source_ref, retrieved_at, verification, notes)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(symbol, field, period_end, source) DO UPDATE SET
              value=excluded.value,
              unit=excluded.unit,
              period_label=excluded.period_label,
              source_ref=excluded.source_ref,
              retrieved_at=excluded.retrieved_at,
              verification=excluded.verification,
              notes=excluded.notes
            """,
            (
                rec.symbol,
                rec.field,
                rec.value,
                rec.unit,
                period_end,
                rec.period_label,
                rec.source,
                rec.source_ref,
                rec.retrieved_at or _now(),
                rec.verification,
                rec.notes,
            ),
        )
        if prior is None:
            inserted += 1
        else:
            updated += 1
            old_value = prior[0]
            if old_value is None or float(old_value) != float(rec.value):
                conn.execute(
                    "INSERT INTO fundamental_revisions "
                    "(symbol, field, period_end, source, old_value, new_value, changed_at, "
                    "source_ref, reason) VALUES (?,?,?,?,?,?,?,?,?)",
                    (
                        rec.symbol, rec.field, period_end, rec.source,
                        old_value, rec.value, rec.retrieved_at or _now(),
                        rec.source_ref, "re-import overwrote an existing value",
                    ),
                )
    return {"inserted": inserted, "updated": updated, "total": len(records)}


def query_revisions(
    conn: Any,
    *,
    symbol: str | None = None,
    limit: int = 200,
) -> list[dict[str, Any]]:
    """Recorded fundamental revisions, newest first (NF-028).

    Returns an empty list -- not a fabricated series -- when nothing has been
    revised since the revision table was introduced.
    """
    limit = max(1, min(int(limit), 2000))
    if symbol:
        rows = conn.execute(
            "SELECT * FROM fundamental_revisions WHERE symbol = ? "
            "ORDER BY changed_at DESC, id DESC LIMIT ?",
            (str(symbol).upper(), limit),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM fundamental_revisions ORDER BY changed_at DESC, id DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def revision_monitor(conn: Any, *, symbol: str | None = None,
                     limit: int = 200) -> dict[str, Any]:
    """Summarise what the revision history can and cannot say (NF-028)."""
    where = "WHERE symbol = ?" if symbol else ""
    params: tuple = (str(symbol).upper(),) if symbol else ()
    rows = [dict(r) for r in conn.execute(
        f"SELECT * FROM fundamental_revisions {where} ORDER BY changed_at DESC, id DESC LIMIT ?",  # noqa: S608
        (*params, max(1, min(int(limit), 2000))),
    ).fetchall()]
    total = conn.execute(
        f"SELECT COUNT(*) FROM fundamental_revisions {where}", params  # noqa: S608
    ).fetchone()[0]
    return {
        "symbol": str(symbol).upper() if symbol else None,
        "revisions": rows,
        "revision_count": int(total),
        "coverage": (
            "Revision history is recorded from the moment the revision table was "
            "introduced. Earlier overwrites were not captured and cannot be "
            "reconstructed; those periods are reported as unknown."
        ),
        "status": "ok" if total else "no_revisions_recorded",
        "note": (
            "No revision has been recorded yet; this does not prove the stored values "
            "were never revised before capture began."
            if not total else
            "Each row shows the previous and new value, the source and when the change was observed."
        ),
    }


def query_symbol_as_of(
    conn: Any,
    symbol: str,
    as_of: str,
) -> list[dict[str, Any]]:
    """Point-in-time fundamentals using *ingestion* time (NF-025).

    A row is visible only if ``retrieved_at <= as_of``. This is a knowledge-time
    view: it uses the moment the project stored the value, because the original
    publication date is not recorded for most rows. The distinction is reported
    to the caller rather than hidden.
    """
    rows = conn.execute(
        """
        SELECT symbol, field, value, unit, period_end, period_label, source,
               source_ref, retrieved_at, verification, notes
        FROM fundamentals
        WHERE symbol = ? AND substr(retrieved_at, 1, 10) <= ?
        ORDER BY period_end DESC, retrieved_at DESC
        """,
        (str(symbol).upper(), str(as_of)[:10]),
    ).fetchall()
    return [_row_to_dict(r) for r in rows]


def point_in_time_coverage(conn: Any, symbol: str) -> dict[str, Any]:
    """Explain what the point-in-time view can honestly support (NF-025)."""
    row = conn.execute(
        "SELECT MIN(retrieved_at) AS first_seen, MAX(retrieved_at) AS last_seen, "
        "COUNT(*) AS n FROM fundamentals WHERE symbol = ?",
        (str(symbol).upper(),),
    ).fetchone()
    return {
        "symbol": str(symbol).upper(),
        "records": int(row["n"] or 0),
        "first_ingested": row["first_seen"],
        "last_ingested": row["last_seen"],
        "knowledge_time": "retrieved_at (ingestion timestamp)",
        "limitation": (
            "Original publication dates are not stored for most records, so this view "
            "uses the ingestion timestamp as the knowledge time. A value that was "
            "published earlier but ingested later is invisible before ingestion. "
            "A true publication-time archive is NOT IMPLEMENTED."
        ),
    }


def _row_to_dict(row: Any) -> dict[str, Any]:
    d = dict(row)
    d["period_end"] = d.get("period_end") or None
    d["period_known"] = bool(d.get("period_end"))
    return d


def query_symbol(conn: Any, symbol: str) -> list[dict[str, Any]]:
    """All fundamentals for a symbol, newest period first; '' maps to None."""
    rows = conn.execute(
        """
        SELECT symbol, field, value, unit, period_end, period_label, source,
               source_ref, retrieved_at, verification, notes
        FROM fundamentals
        WHERE symbol = ?
        ORDER BY period_end = '', period_end DESC, field
        """,
        (symbol.upper(),),
    ).fetchall()
    return [_row_to_dict(r) for r in rows]


def review_source(conn: Any, source: str, *, level: str = "reviewed") -> dict[str, Any]:
    """Promote one source's ``extracted`` records to a reviewed level.

    Bulk review is a deliberate operator act: it asserts "values from *this
    named source* are trusted". It is not automatic, because the ratio guard
    refuses ``extracted`` values precisely so no unreviewed figure can silently
    drive a P/E. The caller names the source, so the trust is scoped and
    auditable rather than global.
    """
    if level not in ("reviewed", "verified"):
        raise FundamentalError("review level must be 'reviewed' or 'verified'")
    if not (source or "").strip():
        raise FundamentalError("a source name is required (review is scoped to a source)")
    cur = conn.execute(
        "UPDATE fundamentals SET verification=? WHERE source=? AND verification='extracted'",
        (level, source.strip()),
    )
    return {"source": source.strip(), "level": level, "promoted": int(cur.rowcount or 0)}


def fundamentals_summary(conn: Any) -> dict[str, Any]:
    """Counts by verification level and period coverage - for the UI header."""
    total = conn.execute("SELECT COUNT(*) AS n FROM fundamentals").fetchone()["n"]
    by_verification = {
        r["verification"]: r["n"]
        for r in conn.execute(
            "SELECT verification, COUNT(*) AS n FROM fundamentals "
            "GROUP BY verification ORDER BY n DESC"
        ).fetchall()
    }
    by_field = {
        r["field"]: r["n"]
        for r in conn.execute(
            "SELECT field, COUNT(*) AS n FROM fundamentals GROUP BY field ORDER BY n DESC"
        ).fetchall()
    }
    symbols = conn.execute("SELECT COUNT(DISTINCT symbol) AS n FROM fundamentals").fetchone()["n"]
    no_period = conn.execute(
        "SELECT COUNT(*) AS n FROM fundamentals WHERE period_end = ''"
    ).fetchone()["n"]
    return {
        "total": total,
        "symbols": symbols,
        "by_verification": by_verification,
        "by_field": by_field,
        "without_period": no_period,
        "known_fields": sorted(KNOWN_FIELDS),
        "verification_levels": list(VERIFICATION_LEVELS),
        "note": (
            "Values are only as trustworthy as their verification level. "
            "'extracted' means read from a document but not yet checked."
        ),
    }


# ------------------------------------------------------- ratio assistant (F10)
def _record_from_row(row: dict[str, Any]) -> FundamentalRecord:
    """Rebuild a FundamentalRecord from a stored query row."""
    period = row.get("period_end")
    if isinstance(period, str) and period:
        period = date.fromisoformat(period[:10])
    elif not isinstance(period, date):
        period = None
    return FundamentalRecord(
        symbol=row["symbol"],
        field=row["field"],
        value=float(row["value"]),
        unit=row["unit"],
        source=row["source"],
        source_ref=row.get("source_ref") or "",
        period_end=period,
        period_label=row.get("period_label") or "",
        retrieved_at=row.get("retrieved_at") or "",
        verification=row.get("verification") or "extracted",
        notes=row.get("notes") or "",
    )


def _unavailable(reason: str) -> dict[str, Any]:
    return {"value": None, "kind": "derived", "unavailable_reason": reason}


def _attempt(fn: Any) -> dict[str, Any]:
    """Run one ratio computation; refusals become reasons, never numbers."""
    try:
        return {"value": round(float(fn()), 4), "kind": "derived"}
    except FundamentalError as exc:
        return _unavailable(str(exc))
    except Exception as exc:  # a malformed stored row must not 500 the report
        return _unavailable(f"computation failed: {type(exc).__name__}: {exc}")


def compute_symbol_ratios(conn: Any, store: Any, symbol: str) -> dict[str, Any]:
    """Deterministic P/E, P/B and dividend yield for one symbol.

    Contract:
    * the price always comes from **stored market data** and carries its
      trading date; with no stored close, every ratio is unavailable with that
      stated reason — no price is ever invented;
    * inputs are *reported* figures, each shown with its period, source and
      verification level; the ratios are *derived* and marked as such;
    * every unavailable ratio carries the exact refusal reason from the ratio
      guards (unreviewed input, unknown period, stale vintage, non-positive
      EPS, ...) instead of a silently omitted or estimated number.
    """
    sym = symbol.upper()
    rows = query_symbol(conn, sym)

    latest: dict[str, FundamentalRecord] = {}
    malformed: list[str] = []
    for row in rows:
        field_name = row["field"]
        if field_name in latest:
            continue  # query is newest-period-first: the first row wins
        try:
            latest[field_name] = _record_from_row(row)
        except Exception:
            malformed.append(field_name)

    price_value: float | None = None
    price_date: str | None = None
    try:
        bars = store.get_bars(sym)
    except Exception:
        bars = None
    if bars is not None and not getattr(bars, "empty", True):
        last = bars.sort_values("trading_date").iloc[-1]
        try:
            candidate = float(last["close"])
            if math.isfinite(candidate) and candidate > 0:
                price_value = candidate
                price_date = str(last["trading_date"])[:10]
        except (TypeError, ValueError):
            price_value = None

    def _input_of(rec: FundamentalRecord) -> dict[str, Any]:
        return {
            "field": rec.field,
            "value": rec.value,
            "period_end": rec.period_end.isoformat() if rec.period_end else None,
            "period_label": rec.period_label,
            "verification": rec.verification,
            "source": rec.source,
            "kind": "reported",
        }

    no_price = f"no usable stored close for {sym}; a price must not be invented"
    as_of = date.fromisoformat(price_date) if price_date else None

    def _ratio(name: str, fields: tuple[str, ...], runner: Any) -> dict[str, Any]:
        rec = next((latest[f] for f in fields if f in latest), None)
        if rec is None:
            out = _unavailable(f"no {' or '.join(fields)} record stored for {sym}")
            out["inputs"] = []
            return out
        if as_of is None:
            out = _unavailable(no_price)
            out["inputs"] = [_input_of(rec)]
            return out
        out = _attempt(lambda: runner(price_value, rec, price_as_of=as_of))
        out["inputs"] = [_input_of(rec)]
        return out

    if price_value is None:
        ratios = {
            "pe": _unavailable(no_price),
            "pb": _unavailable(no_price),
            "dividend_yield_pct": _unavailable(no_price),
        }
        for r in ratios.values():
            r["inputs"] = []
    else:
        ratios = {
            "pe": _ratio(
                "pe", ("eps",), lambda p, r, price_as_of: ratio_pe(p, r, price_as_of=price_as_of)
            ),
            "pb": _ratio(
                "pb",
                ("net_worth_per_share", "book_value_per_share"),
                lambda p, r, price_as_of: ratio_pb(p, r, price_as_of=price_as_of),
            ),
            "dividend_yield_pct": _ratio(
                "dividend_yield_pct",
                ("dps",),
                lambda p, r, price_as_of: ratio_dividend_yield(
                    r, float(p), price_as_of=price_as_of
                ),
            ),
        }

    reported = [
        {
            "field": f,
            "value": rec.value,
            "unit": rec.unit,
            "period_end": rec.period_end.isoformat() if rec.period_end else None,
            "verification": rec.verification,
            "source": rec.source,
            "kind": "reported",
        }
        for f, rec in sorted(latest.items())
    ]

    return {
        "symbol": sym,
        "status": "ok" if rows else "no_data",
        "price": (
            {
                "value": price_value,
                "date": price_date,
                "kind": "market",
                "source": "stored price bars",
            }
            if price_value is not None
            else {
                "value": None,
                "date": None,
                "kind": "market",
                "source": None,
                "unavailable_reason": no_price,
            }
        ),
        "ratios": ratios,
        "reported_fields": reported,
        "malformed_fields": sorted(set(malformed)),
        "notes": [
            "Ratios are derived calculations; every input under "
            "ratios.*.inputs is a reported figure with its own period, source "
            "and verification level.",
            "A ratio with value=null states its reason; nothing was estimated to fill a gap.",
            "'extracted' inputs are refused by the ratio guards by design - "
            "review them before a ratio can be produced.",
        ],
    }


def compute_ttm_eps(conn: Any, symbol: str) -> dict[str, Any]:
    """Report TTM EPS availability for *symbol*.

    The source (yonepse/financials.json) labels reports as "First/Second/Third/
    Fourth Quarter (Nepali FY YYYY-YYYY)" and "Annual Report (Nepali FY
    YYYY-YYYY)" but does NOT document whether a quarterly EPS figure is
    per-quarter, cumulative (year-to-date), or trailing-12-month.

    Empirical check over the stored data: summing the four most recent quarterly
    EPS records does not reconcile with the annual report EPS in 99.1% of cases
    (321/324), the quarterly values are not consistently cumulative
    (Q4 < Q3 in 43.4% of cases) and not consistently trailing-12-month
    (Q1(FY X)/Annual(FY X-1) median 0.70, not 1.0). Deriving per-quarter EPS
    by subtraction is therefore unreliable.

    Because the reporting basis cannot be established from the available
    evidence, this function does NOT compute a TTM EPS value. It returns the
    available EPS records (with their period labels) for transparency, and an
    explicit reason. A TTM EPS value is returned only when a documented source
    makes the quarterly basis verifiable.
    """
    sym = symbol.upper()
    rows = conn.execute(
        "SELECT value, period_end, period_label, verification, source FROM fundamentals WHERE symbol = ? AND field = 'eps' ORDER BY period_end DESC",
        (sym,),
    ).fetchall()
    if not rows:
        return {"symbol": sym, "ttm_eps": None, "reason": "no EPS records stored", "quarters_used": 0, "quarters": []}
    seen_periods: set[str] = set()
    quarters: list[dict] = []
    for r in rows:
        pe = r["period_end"]
        if pe in seen_periods:
            continue
        seen_periods.add(pe)
        v = _num(r["value"])
        if v is None:
            continue
        quarters.append({"value": v, "period_end": pe, "label": r["period_label"], "verification": r["verification"], "source": r["source"]})
    quarters_sorted = sorted(quarters, key=lambda q: q["period_end"])
    reason = (
        "quarterly EPS basis is not documented by the source "
        "(yonepse/financials.json): the reported quarterly figures do not "
        "reconcile with the annual report (sum of four quarters != annual EPS "
        "in 99.1% of cases), so per-quarter, cumulative and trailing-12-month "
        "interpretations cannot be distinguished. TTM EPS is not computed to "
        "avoid a misleading result; the available records are returned for "
        "transparency."
    )
    return {
        "symbol": sym,
        "ttm_eps": None,
        "reason": reason,
        "quarters_used": len(quarters_sorted),
        "quarters": quarters_sorted,
    }


def compute_eps_growth(conn: Any, symbol: str) -> dict[str, Any]:
    """Compute EPS growth between the two most recent compatible periods.

    Only compares periods of the same type (quarterly vs quarterly, or
    annual vs annual). Never compares quarterly EPS with annual EPS.
    Handles negative prior EPS and zero denominators gracefully.
    """
    sym = symbol.upper()
    rows = conn.execute(
        "SELECT value, period_end, period_label FROM fundamentals WHERE symbol = ? AND field = 'eps' ORDER BY period_end DESC",
        (sym,),
    ).fetchall()

    def _period_type(label: str) -> str:
        l = (label or "").lower()
        if "annual" in l:
            return "annual"
        if "quarter" in l:
            return "quarterly"
        return "unknown"

    distinct: list[dict] = []
    seen: set[str] = set()
    for r in rows:
        pe = r["period_end"]
        if pe in seen:
            continue
        seen.add(pe)
        v = _num(r["value"])
        if v is None:
            continue
        pt = _period_type(r["period_label"] or "")
        if distinct and distinct[0].get("_type") != pt:
            continue
        distinct.append({"value": v, "period_end": pe, "label": r["period_label"], "_type": pt})
        if len(distinct) >= 2:
            break
    if len(distinct) < 2:
        return {"symbol": sym, "growth_pct": None,
                "reason": "fewer than 2 comparable EPS periods (same type)",
                "current": distinct[0] if distinct else None, "previous": None}
    cur, prev = distinct[0], distinct[1]
    if prev["value"] == 0:
        if cur["value"] > 0:
            return {"symbol": sym, "growth_pct": None, "reason": "prior EPS is zero; growth not meaningful",
                    "current": cur, "previous": prev}
        elif cur["value"] < 0:
            return {"symbol": sym, "growth_pct": None, "reason": "prior EPS is zero and current is negative; growth not meaningful",
                    "current": cur, "previous": prev}
        else:
            return {"symbol": sym, "growth_pct": 0.0, "reason": "both periods zero",
                    "current": cur, "previous": prev}
    growth = (cur["value"] - prev["value"]) / abs(prev["value"]) * 100.0
    for d in (cur, prev):
        d.pop("_type", None)
    return {
        "symbol": sym,
        "growth_pct": round(growth, 2),
        "current": cur,
        "previous": prev,
        "reason": None,
    }


def _num(value: Any) -> float | None:
    """Parse a value to float, returning None on failure (never raising)."""
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        try:
            v = float(value)
            return v if math.isfinite(v) else None
        except (TypeError, ValueError):
            return None
    try:
        return float(str(value).strip().replace(",", ""))
    except (TypeError, ValueError):
        return None
