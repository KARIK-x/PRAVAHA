"""Historical NEPSE index OHLC ingestion pipeline."""

from __future__ import annotations

import csv
import math
import sqlite3
from datetime import date, datetime
from pathlib import Path
from typing import Any

__all__ = ["ingest_index_ohlc", "read_index_ohlc_csv", "IngestResult"]

REQUIRED_COLUMNS = ("date", "close")


class IngestError(ValueError):
    """Raised when the input file cannot be imported."""


class IngestResult:
    def __init__(self):
        self.discovered = 0
        self.inserted = 0
        self.updated = 0
        self.skipped = 0
        self.rejected = 0
        self.rejected_details = []
        self.genuine = 0
        self.placeholder = 0
        self.invalid = 0
        self.with_turnover = 0
        self.first_date = None
        self.last_date = None
        self.source = ""
        self.dry_run = False

    def as_dict(self):
        return {
            "discovered": self.discovered,
            "inserted": self.inserted,
            "updated": self.updated,
            "skipped": self.skipped,
            "rejected": self.rejected,
            "genuine": self.genuine,
            "placeholder": self.placeholder,
            "invalid": self.invalid,
            "with_turnover": self.with_turnover,
            "first_date": self.first_date,
            "last_date": self.last_date,
            "source": self.source,
            "dry_run": self.dry_run,
        }


def _parse_date(raw):
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


def read_index_ohlc_csv(path):
    records = []
    errors = []
    seen = set()

    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise IngestError("CSV is empty (no header row)")
        fieldnames = [(h or "").strip() for h in reader.fieldnames]
        missing = [c for c in REQUIRED_COLUMNS if c not in set(fieldnames)]
        if missing:
            raise IngestError(
                "CSV is missing required column(s): " + ", ".join(missing)
            )

        for line, raw in enumerate(reader, start=2):
            norm = {}
            for key, value in raw.items():
                clean = (key or "").strip()
                if clean:
                    norm[clean] = (value or "").strip()

            raw_date = norm.get("date", "")
            parsed_date = _parse_date(raw_date)
            if parsed_date is None:
                errors.append({"line": line, "reason": "unparseable date " + repr(raw_date)})
                continue

            raw_close = norm.get("close", "")
            try:
                close = float(raw_close)
            except (TypeError, ValueError):
                errors.append({"line": line, "reason": "non-numeric close " + repr(raw_close)})
                continue
            if not math.isfinite(close) or close <= 0:
                errors.append({"line": line, "reason": "invalid close " + repr(raw_close)})
                continue

            def _float_or_none(key):
                val = norm.get(key, "")
                if not val:
                    return None
                try:
                    v = float(val)
                    return v if math.isfinite(v) else None
                except (TypeError, ValueError):
                    return None

            open_val = _float_or_none("open")
            high_val = _float_or_none("high")
            low_val = _float_or_none("low")
            volume_val = _float_or_none("volume")

            if open_val is None and high_val is None and low_val is None:
                ohlc_status = "placeholder"
                # Store NULL for OHLC (not close) - close-only data
                open_val = None
                high_val = None
                low_val = None
            elif high_val == close and low_val == close and open_val == close:
                ohlc_status = "placeholder"
                open_val = None
                high_val = None
                low_val = None
            elif (high_val is not None and low_val is not None and open_val is not None
                  and high_val >= max(open_val, close) and low_val <= min(open_val, close)
                  and high_val >= low_val):
                ohlc_status = "genuine"
            else:
                ohlc_status = "invalid"

            if parsed_date in seen:
                errors.append({"line": line, "reason": "duplicate date " + parsed_date.isoformat()})
                continue
            seen.add(parsed_date)

            symbol = norm.get("symbol", "NEPSE").replace("_index", "").strip() or "NEPSE"

            records.append({
                "date": parsed_date,
                "open": open_val,
                "high": high_val,
                "low": low_val,
                "close": close,
                "volume": volume_val,
                "ohlc_status": ohlc_status,
                "index_name": symbol,
            })

    return records, errors


def ingest_index_ohlc(csv_path, db_path=None, source="socrateai-official/nepse-open-data",
                      dry_run=False, index_name="NEPSE"):
    from megatool.config import PATHS, ensure_dirs
    from megatool.db import init_app_db, get_conn

    ensure_dirs()
    csv_path = Path(csv_path)
    if not csv_path.is_file():
        raise IngestError("Source file not found: " + str(csv_path))

    if db_path is None:
        db_path = PATHS.app_db
    db_path = Path(db_path)

    result = IngestResult()
    result.source = source
    result.dry_run = dry_run

    records, errors = read_index_ohlc_csv(csv_path)
    result.discovered = len(records) + len(errors)
    result.rejected = len(errors)
    result.rejected_details = errors

    if index_name == "NEPSE":
        filtered = records
    else:
        filtered = [r for r in records if r["index_name"] == index_name]

    for r in filtered:
        if r["ohlc_status"] == "genuine":
            result.genuine += 1
        elif r["ohlc_status"] == "placeholder":
            result.placeholder += 1
        elif r["ohlc_status"] == "invalid":
            result.invalid += 1
        if r["volume"] is not None:
            result.with_turnover += 1

    if filtered:
        result.first_date = min(r["date"] for r in filtered).isoformat()
        result.last_date = max(r["date"] for r in filtered).isoformat()

    if dry_run:
        return result

    init_app_db(db_path)

    with get_conn(db_path) as conn:
        for r in filtered:
            try:
                existing = conn.execute(
                    "SELECT open, high, low, close, volume, ohlc_status FROM index_ohlc_history WHERE index_name = ? AND trading_date = ?",
                    (index_name, r["date"].isoformat()),
                ).fetchone()

                if existing:
                    old_vals = (existing[0], existing[1], existing[2], existing[3], existing[4], existing[5])
                    new_vals = (r["open"], r["high"], r["low"], r["close"], r["volume"], r["ohlc_status"])
                    if old_vals == new_vals:
                        result.skipped += 1
                        continue
                    else:
                        result.updated += 1
                else:
                    result.inserted += 1

                sql = "INSERT OR REPLACE INTO index_ohlc_history (index_name, trading_date, open, high, low, close, volume, volume_type, ohlc_status, source, source_file, retrieved_at, close_diff_vs_index_series) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
                params = (
                    index_name,
                    r["date"].isoformat(),
                    r["open"],
                    r["high"],
                    r["low"],
                    r["close"],
                    r["volume"],
                    "turnover_npr" if r["volume"] is not None else None,
                    r["ohlc_status"],
                    source,
                    csv_path.name,
                    datetime.now().isoformat(),
                    None,
                )
                conn.execute(sql, params)
            except sqlite3.IntegrityError:
                result.skipped += 1

    return result
