"""Adapter for the socrateai-official/nepse-open-data ``ohlc_index`` dataset.

WHAT THIS IS
------------
The dataset publishes one CSV per trading session containing **every NEPSE
index for that session** — the composite plus the sector indices (Banking,
Development Banks, Finance, Microfinance, Hotels & Tourism, Hydropower, Life
Insurance, Non-Life Insurance, Manufacturing, Investment, Trading, Mutual
Funds, Others) and the Float / Sensitive / Sensitive-Float variants.

This is the only permitted source found that carries **sector index** history,
which is what makes sector-relative work possible rather than only
market-wide. Verified: 5,350 daily files spanning **2003-07-17 → 2026-10-15**,
each file holding 16 index observations.

PROVENANCE AND RIGHTS
---------------------
The repository is published as `NOASSERTION` (a permissive LICENSE exists but
GitHub cannot classify it). Its README's advertised `meta/symbols.csv` and
`meta/sector_map.csv` **do not exist** — the `meta/` directory holds only a
`.gitkeep`, so no sector master is available here. The data is a derived
compilation of NEPSE figures; this module reads it for local research only and
never redistributes it.

DATA-QUALITY NOTES (measured, not assumed)
------------------------------------------
* Older files carry an empty ``volume`` and, pre-split, an ``Insurance_index``
  that later becomes ``Life Insurance_index`` / ``Non Life Insurance_index``.
  Empty fields are reported as missing, never coerced to zero.
* Values are published with mixed rounding (2–3 dp), so a close can sit a
  fraction of a point above the published high. These are recorded as rounding
  artefacts, not as corrupt rows.
"""

from __future__ import annotations

import csv
import io
from typing import Any
from urllib.parse import unquote

BASE_RAW = "https://raw.githubusercontent.com/socrateai-official/nepse-open-data/main"
INDEX_DIR = "ohlc_index"

#: Canonical index names. The source uses URL-encoded symbols such as
#: ``Development%20Bank_index``; keys below are the DECODED forms.
INDEX_NAME_MAP: dict[str, str] = {
    "NEPSE_index": "NEPSE",
    "Banking_index": "Banking",
    "Development Bank_index": "Development Banks",
    "Finance_index": "Finance",
    "Microfinance_index": "Microfinance",
    "Hotels and Tourism_index": "Hotels & Tourism",
    "HydroPower_index": "Hydropower",
    "Life Insurance_index": "Life Insurance",
    "Non Life Insurance_index": "Non-Life Insurance",
    "Others_index": "Others",
    "Investment_index": "Investment",
    "Float_index": "Float",
    "Trading_index": "Trading",
    "Mutual Fund_index": "Mutual Funds",
    "Sen. Float_index": "Sensitive Float",
    "Sensitive_index": "Sensitive",
    # Pre-split legacy series: the insurance sector was one index before it
    # divided into Life and Non-Life.
    "Insurance_index": "Insurance (legacy)",
}

#: Indices whose published volume is structurally zero/unmaintained in some
#: sessions. Volume is stored but never used for ranking.
ZERO_VOLUME_INDICES = frozenset({"Float", "Sensitive Float", "Mutual Funds", "Sensitive"})


class SocrateaiError(Exception):
    """Problem fetching or parsing a socrateai index file."""


def index_csv_url(trading_date: str) -> str:
    return f"{BASE_RAW}/{INDEX_DIR}/adj_{trading_date}.csv"


def parse_index_csv(text: str, trading_date: str | None = None) -> dict[str, Any]:
    """Parse one ``adj_<date>.csv`` into normalised observations.

    Returns ``{"observations": [...], "missing": [...], "date_mismatch": bool}``.
    A row with an empty numeric field is reported in ``missing`` and dropped
    from ``observations`` — an empty field is never treated as zero.
    """
    sample = text.lstrip("﻿")
    reader = csv.DictReader(io.StringIO(sample))
    if not reader.fieldnames:
        raise SocrateaiError("index CSV has no header row")

    observations: list[dict[str, Any]] = []
    missing: list[dict[str, Any]] = []
    mismatches: list[str] = []
    seen: set[tuple[str, str]] = set()

    for line, raw in enumerate(reader, start=2):
        symbol_raw = (raw.get("symbol") or "").strip()
        if not symbol_raw:
            continue
        symbol = unquote(symbol_raw)
        file_date = (raw.get("date") or "").strip()[:10]
        if trading_date and file_date and file_date != trading_date:
            mismatches.append(file_date)

        values: dict[str, float] = {}
        blanks: list[str] = []
        for field in ("open", "high", "low", "close", "volume"):
            raw_value = (raw.get(field) or "").strip()
            if raw_value == "":
                blanks.append(field)
                continue
            try:
                values[field] = float(raw_value)
            except ValueError:
                blanks.append(field)
        if blanks:
            missing.append({"line": line, "symbol": symbol, "fields": blanks, "date": file_date})
            continue

        name = INDEX_NAME_MAP.get(symbol, symbol)
        key = (file_date or (trading_date or ""), name)
        if key in seen:
            continue
        seen.add(key)
        observations.append(
            {
                "date": file_date or trading_date or "",
                "index_name": name,
                "open": values["open"],
                "high": values["high"],
                "low": values["low"],
                "close": values["close"],
                "volume": values["volume"],
            }
        )

    return {
        "observations": observations,
        "missing": missing,
        "date_mismatch": bool(mismatches),
        "unmapped_symbols": sorted(
            {o["index_name"] for o in observations} - set(INDEX_NAME_MAP.values())
        ),
    }


def validate_observations(
    observations: list[dict[str, Any]], tolerance: float = 0.01
) -> dict[str, Any]:
    """Check OHLC ordering, tolerating the source's mixed rounding.

    A close/high/low/open ordering that is violated by no more than
    ``tolerance`` is a **rounding artefact** of publishing 2–3 decimals; a
    larger inversion is a genuine problem. The two are reported separately and
    never silently merged.
    """
    inverted: list[dict[str, Any]] = []
    rounding: list[dict[str, Any]] = []
    for o in observations:
        problems: list[str] = []
        if o["high"] < o["low"]:
            problems.append("high < low")
        if o["close"] > o["high"]:
            problems.append("close > high")
        if o["close"] < o["low"]:
            problems.append("close < low")
        if o["open"] > o["high"]:
            problems.append("open > high")
        if o["open"] < o["low"]:
            problems.append("open < low")
        if not problems:
            continue
        excess = max(
            max(0.0, o["close"] - o["high"]),
            max(0.0, o["low"] - o["close"]),
            max(0.0, o["open"] - o["high"]),
            max(0.0, o["low"] - o["open"]),
            max(0.0, o["low"] - o["high"]),
        )
        entry = {
            "date": o["date"],
            "index_name": o["index_name"],
            "problems": problems,
            "excess": round(excess, 6),
        }
        if excess <= tolerance:
            rounding.append(entry)
        else:
            inverted.append(entry)

    return {
        "checked": len(observations),
        "inverted": inverted,
        "rounding_artefacts": rounding,
        "non_positive_close": [
            {"date": o["date"], "index_name": o["index_name"], "close": o["close"]}
            for o in observations
            if o["close"] <= 0
        ],
    }


def to_index_rows(observations: list[dict[str, Any]], source: str) -> list[dict[str, Any]]:
    """Shape observations for :meth:`MarketStore.upsert_index_rows`."""
    rows: list[dict[str, Any]] = []
    for o in observations:
        rows.append(
            {
                "index_name": o["index_name"],
                "trading_date": o["date"],
                "close": o["close"],
                "source": source,
            }
        )
    return rows


def fetch_index_csv(trading_date: str, timeout: float = 30.0) -> str:
    """Fetch one session's index file (public raw.githubusercontent.com)."""
    from urllib.request import urlopen

    url = index_csv_url(trading_date)
    try:
        with urlopen(url, timeout=timeout) as resp:
            return resp.read().decode("utf-8")
    except Exception as exc:
        raise SocrateaiError(f"failed to fetch {url}: {exc}") from exc


def index_name_canonical(symbol: str) -> str:
    """Canonical index name for a source symbol (already URL-decoded)."""
    return INDEX_NAME_MAP.get(unquote(symbol).strip(), unquote(symbol).strip())
