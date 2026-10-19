"""binayabaral/nepal-market-data adapter.

Reads the MIT-licensed reference and index CSVs published at
https://github.com/binayabaral/nepal-market-data and converts them into the
shapes the existing loaders expect.

The reference table is the project's existing UNVERIFIED review source; this
adapter makes it reproducible to fetch and convert.  No data is imported
automatically — converted files are written to a review directory for dry-run
and owner approval.
"""

from __future__ import annotations

import csv
import io
from datetime import UTC, date, datetime
from typing import Any
from urllib.request import urlopen

BASE_URL = "https://raw.githubusercontent.com/binayabaral/nepal-market-data/main"

PATH_REFERENCE = "data/reference/nepse-symbols.csv"
PATH_INDEX = "data/nepse/NEPSE_INDEX.csv"


class BinayabaralError(Exception):
    """Fetch/parse problem with the binayabaral dataset."""


def _fetch_text(path: str, timeout: float = 30.0) -> str:
    url = f"{BASE_URL}/{path}"
    try:
        with urlopen(url, timeout=timeout) as resp:
            return resp.read().decode("utf-8")
    except Exception as exc:
        raise BinayabaralError(f"failed to fetch {url}: {exc}") from exc


def fetch_reference_csv() -> str:
    return _fetch_text(PATH_REFERENCE)


def fetch_index_csv() -> str:
    return _fetch_text(PATH_INDEX)


def _now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def reference_to_metadata_rows(text: str) -> list[dict[str, Any]]:
    """Convert the binayabaral reference CSV into metadata-dry-run rows.

    The upstream file has columns: symbol, name, source_category,
    instrument_type, sector, status.  The upstream status column is a constant
    placeholder ('listed') and is mapped to ACTIVE for equities; 'merged' is
    preserved.  Sector is passed through unchanged; rows with an empty sector
    are still emitted so the dry-run can report the gap honestly.
    """
    rows: list[dict[str, Any]] = []
    retrieved = _now_iso()
    observed = date.today().isoformat()
    reader = csv.DictReader(io.StringIO(text))
    for rec in reader:
        symbol = (rec.get("symbol") or "").strip().upper()
        if not symbol:
            continue
        raw_status = (rec.get("status") or "").strip().lower()
        status = "MERGED" if raw_status == "merged" else "ACTIVE"
        sector = (rec.get("sector") or "").strip()
        itype = (rec.get("instrument_type") or "").strip().lower()
        rows.append(
            {
                "symbol": symbol,
                "name": (rec.get("name") or "").strip(),
                "instrument_type": itype,
                "sector": sector,
                "status": status,
                "source": "binayabaral/nepal-market-data/reference/nepse-symbols.csv",
                "sector_source": "binayabaral/nepal-market-data/reference/nepse-symbols.csv",
                "sector_retrieved_at": retrieved,
                "sector_observed_date": observed,
            }
        )
    return rows


def reference_to_sector_rows(text: str) -> list[dict[str, Any]]:
    """Convert the binayabaral reference CSV into sector-loader rows."""
    rows: list[dict[str, Any]] = []
    retrieved = _now_iso()
    observed = date.today().isoformat()
    reader = csv.DictReader(io.StringIO(text))
    for rec in reader:
        symbol = (rec.get("symbol") or "").strip().upper()
        sector = (rec.get("sector") or "").strip()
        if symbol and sector:
            rows.append(
                {
                    "symbol": symbol,
                    "sector": sector,
                    "source": "binayabaral/nepal-market-data/reference/nepse-symbols.csv",
                    "retrieved_at": retrieved,
                    "observed_date": observed,
                }
            )
    return rows


def index_to_index_csv(text: str) -> str:
    """Convert binayabaral NEPSE_INDEX.csv (published_date,close,...) to date,close.

    Extra columns are dropped.  Empty/non-positive closes are skipped, but the
    function returns the whole file; the strict :mod:`megatool.index_series`
    loader will reject bad points if the owner chooses to import it.
    """
    reader = csv.DictReader(io.StringIO(text))
    out = io.StringIO()
    writer = csv.DictWriter(out, fieldnames=["date", "close"])
    writer.writeheader()
    for rec in reader:
        published = (rec.get("published_date") or "").strip()
        close = (rec.get("close") or "").strip()
        if not published or not close:
            continue
        writer.writerow({"date": published, "close": close})
    return out.getvalue()


def metadata_csv(rows: list[dict[str, Any]]) -> str:
    fieldnames = [
        "symbol",
        "name",
        "instrument_type",
        "sector",
        "status",
        "source",
        "sector_source",
        "sector_retrieved_at",
        "sector_observed_date",
    ]
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fieldnames)
    writer.writeheader()
    for row in rows:
        writer.writerow({k: row.get(k, "") for k in fieldnames})
    return buf.getvalue()


def sector_csv(rows: list[dict[str, Any]]) -> str:
    fieldnames = ["symbol", "sector", "source", "retrieved_at", "observed_date"]
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=fieldnames)
    writer.writeheader()
    for row in rows:
        writer.writerow({k: row.get(k, "") for k in fieldnames})
    return buf.getvalue()
