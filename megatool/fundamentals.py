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
    "fundamentals_summary",
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
        missing = [c for c in REQUIRED_COLUMNS if not str(row.get(c, "") or "").strip()]
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
    """
    inserted = updated = 0
    for rec in records:
        cur = conn.execute(
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
                rec.period_end.isoformat() if rec.period_end else "",
                rec.period_label,
                rec.source,
                rec.source_ref,
                rec.retrieved_at or _now(),
                rec.verification,
                rec.notes,
            ),
        )
        if cur.rowcount:
            inserted += 1
        else:
            updated += 1
    return {"inserted": inserted, "updated": updated, "total": len(records)}


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
