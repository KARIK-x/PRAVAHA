"""Historical NEPSE index loader: a validated pipeline awaiting an owner file.

HONEST LABELLING
----------------
No index series ships with this project and none is synthesised here. Stock
price history is *not* a substitute for index history, and this module never
derives one from the other. It reads a ``date,close`` CSV the owner supplies,
validates every point strictly, and stores it in ``index_series`` so that the
currently-disabled ``relative_strength`` factor has real data to consume once a
published series is obtained (register L3 / B-10).

Validation is deliberately strict — an index series with a bad point is worse
than no series:

* **Required columns** ``date,close`` — a wrong file is refused up front.
* **Unparseable dates fail loudly** (no silent coercion to a wrong day).
* **Closes must be finite and > 0** — NaN, inf, zero and negatives are rejected.
* **Duplicate dates are rejected**, never silently deduped.
* Any such problem aborts the whole import with a per-line report; nothing is
  written partially.

Expected CSV: header ``date,close`` (extra columns ignored). Dates are ISO
``YYYY-MM-DD``; provenance (``source``) is required.
"""

from __future__ import annotations

import csv
import io
import math
from datetime import date, datetime
from typing import Any

__all__ = [
    "REQUIRED_COLUMNS",
    "IndexSeriesError",
    "import_index_series",
    "read_index_csv",
]

#: Columns that must be present in an index CSV.
REQUIRED_COLUMNS = ("date", "close")


class IndexSeriesError(ValueError):
    """Raised for a file that cannot be imported (bad columns, bad points)."""


def _parse_date(raw: str) -> date | None:
    """ISO date, else a pandas-parseable date; ``None`` if neither works."""
    value = (raw or "").strip()
    if not value:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        pass
    try:
        import pandas as pd

        ts = pd.to_datetime(value, errors="coerce")
        if ts is None or (isinstance(ts, float) and math.isnan(ts)) or pd.isna(ts):
            return None
        return pd.Timestamp(ts).date()
    except Exception:
        return None


def read_index_csv(text: str) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Parse a ``date,close`` CSV into ``(points, errors)``.

    Each point is ``{"date": date, "close": float}``. Each error is
    ``{"line", "reason", ...}`` for a rejected row. Duplicate dates and
    non-positive/non-finite closes are errors, not warnings.
    """
    sample = text.lstrip("\ufeff")
    reader = csv.DictReader(io.StringIO(sample))
    if not reader.fieldnames:
        raise IndexSeriesError("index CSV is empty (no header row)")
    fieldnames = [(h or "").strip().lstrip("\ufeff") for h in reader.fieldnames]
    missing = [c for c in REQUIRED_COLUMNS if c not in set(fieldnames)]
    if missing:
        raise IndexSeriesError(
            f"index CSV is missing required column(s): {', '.join(missing)}. "
            f"Expected a header with {', '.join(REQUIRED_COLUMNS)}."
        )

    points: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    seen: set[date] = set()

    for line, raw in enumerate(reader, start=2):  # line 1 is the header
        norm: dict[str, str] = {}
        for key, value in raw.items():
            clean = (key or "").strip().lstrip("\ufeff")
            if clean:
                norm[clean] = (value or "").strip()

        raw_date = norm.get("date", "")
        raw_close = norm.get("close", "")

        parsed_date = _parse_date(raw_date)
        if parsed_date is None:
            errors.append(
                {"line": line, "reason": f"unparseable date {raw_date!r}", "value": raw_date}
            )
            continue

        try:
            close = float(raw_close)
        except (TypeError, ValueError):
            errors.append(
                {"line": line, "reason": f"non-numeric close {raw_close!r}", "value": raw_close}
            )
            continue
        if not math.isfinite(close):
            errors.append(
                {"line": line, "reason": f"non-finite close {raw_close!r}", "value": raw_close}
            )
            continue
        if close <= 0:
            errors.append(
                {"line": line, "reason": f"close must be > 0, got {close}", "value": raw_close}
            )
            continue

        if parsed_date in seen:
            errors.append({"line": line, "reason": f"duplicate date {parsed_date.isoformat()}"})
            continue
        seen.add(parsed_date)
        points.append({"date": parsed_date, "close": close})

    return points, errors


def import_index_series(
    text: str,
    *,
    index_name: str,
    source: str,
    store: Any = None,
) -> dict[str, Any]:
    """Validate and persist an index series. Refuses a file with any bad point.

    ``index_name`` labels the series (e.g. ``"NEPSE"``) and ``source`` is
    required provenance. Nothing is written if any point fails validation.
    """
    if not str(index_name).strip():
        raise IndexSeriesError("index_name is required")
    if not str(source).strip():
        raise IndexSeriesError("source is required; an index import without provenance is not kept")

    points, errors = read_index_csv(text)
    if errors:
        shown = "; ".join(f"line {e['line']}: {e['reason']}" for e in errors[:5])
        more = f" (+{len(errors) - 5} more)" if len(errors) > 5 else ""
        raise IndexSeriesError(
            f"index CSV has {len(errors)} invalid point(s); nothing was written: {shown}{more}"
        )
    if not points:
        raise IndexSeriesError("index CSV contained no data rows")
    # Chronological order so first_date/last_date are the true span, not the
    # file's line order.
    points.sort(key=lambda p: p["date"])

    if store is None:
        from megatool.market_store import MarketStore

        store = MarketStore()

    rows = [
        {
            "index_name": str(index_name).strip(),
            "trading_date": p["date"],
            "close": p["close"],
            "source": str(source).strip(),
            "retrieved_at": datetime.now().astimezone(),
        }
        for p in points
    ]
    written = store.upsert_index_rows(rows)
    return {
        "index_name": str(index_name).strip(),
        "source": str(source).strip(),
        "rows_in_file": len(points),
        "points_written": written,
        "first_date": points[0]["date"].isoformat(),
        "last_date": points[-1]["date"].isoformat(),
    }
