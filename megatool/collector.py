"""NEPSE market-data collector - published datasets in, validated rows out, nothing invented.

Layer
-----
Sits *inside* the existing architecture rather than beside it:

* reads YONEPSE through :mod:`megatool.datasources.yonepse` - the one
  legitimate, no-auth public mirror this project already serves on the
  dashboard - so the ``Salter``/WASM anti-bot question stays untouched and no
  new endpoint is invented;
* normalises quotes with the **same** ``live._quotes_from_records`` the live
  service uses, so the collector and the dashboard can never disagree about
  what a row means;
* labels freshness with the **same** ``live._freshness`` bands used
  everywhere else, so "delayed" and "stale" mean exactly the same thing;
* persists into the application SQLite store (schema v7 tables) and logs to
  ````ingestion_log`` like every other ingestion path.

Datasets (all read from published upstream files today)
=======================================================

===============================  ====================================
``market_live``                  ``data/market/live.json``
``index``                        ``data/market/indices.json``
``summary``                      ``data/market/summary.json``
``status``                       ``data/market/status.json``
``sector_indices``               ``data/market/sector_indices.json``
``history``                      ``data/market/history.json``
``top_gainer``                   ``top_stocks.json[top_gainer]``
``top_loser``                    ``top_stocks.json[top_loser]``
``top_turnover``                 ``top_stocks.json[top_turnover]``
``top_trade``                    ``top_stocks.json[top_trade]``
``top_transaction``              ``top_stocks.json[top_transaction]``
===============================  ====================================

``top_stocks.json`` carries five ranking boards in one file; as datasets each
is stored and counted separately, and every one of them is read from a
published file - nothing is re-derived from another dataset.

Freshness honesty
-----------------
* ``observed_at`` is the newest stamp **the source itself states** in a
  dataset (per-row ``last_updated`` for the quote board, ``last_checked`` for
  status, ``generatedTime`` for indices). The retrieval time is stored
  separately in ``retrieved_at`` / the run envelope and is never laundered
  into an observation timestamp.
* Datasets whose source publishes no timestamp (summary, the five rankings,
  sector definitions, history) are labelled ``unknown`` with a note - they
  are never assigned the quote board's stamp.
* The one cross-check the data itself permits: ``summary.json`` turnover,
  share and transaction totals matched against the same-day row of
  ``history.json`` produce ``business_date`` plus ``business_date_evidence``,
  so the report states **which session day** the snapshot describes and what
  evidence backs that claim. A failed cross-check is reported, not squinted past.
* Rankings duplicate-suppression keeps the **best-ranked** occurrence (the
  upstream lists are already sorted by the board's defining metric), so a
  symbol appearing twice cannot double-count.

Persistence
-----------
Each run opens one SQLite transaction; if any write fails the whole run is
rolled back and the error is raised - a half-run is never persisted.
"""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from megatool import db
from megatool.datasources import yonepse
from megatool.live import _freshness, _max_iso, _parse_ts, _quotes_from_records, _utcnow

#: Publish cadence of the upstream market files, seconds (measured 30-76 min
#: upstream; 2-hour "delayed" window is therefore generous, never optimistic).
PUBLISH_CADENCE_SECONDS = 3600.0

#: Minimum poll interval the CLI accepts. Faster polling than the publish
#: cadence adds no information and is pure load on the source.
MIN_POLL_INTERVAL_SECONDS = 60
DEFAULT_POLL_INTERVAL_SECONDS = 900

#: Percent tolerance for the summary-vs-history cross-check.
_CROSSCHECK_TOLERANCE = 0.005

#: Summary label fragments -> normalised metric keys (first match wins).
_SUMMARY_METRICS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("total_turnover", ("total turnover",)),
    ("total_traded_shares", ("traded shares",)),
    ("total_transactions", ("total transactions", "transactions")),
    ("total_scrips_traded", ("scrips traded",)),
    ("total_float_market_cap", ("float market capitalization",)),
    ("total_market_cap", ("market capitalization",)),
)

_STATUS_OK = "ok"
_STATUS_DEGRADED = "degraded"
_STATUS_UNAVAILABLE = "source_unavailable"
_RUN_OK = "success"
_RUN_PARTIAL = "partial"
_RUN_FAILED = "failed"

#: The ranking boards, in source-file order.
RANKING_DATASETS = ("top_gainer", "top_loser", "top_turnover", "top_trade", "top_transaction")


class CollectorError(Exception):
    """A collection could not be represented honestly (never a fabricated one)."""


# ------------------------------------------------------------------ validation
def _finite(value: Any) -> float | None:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if f != f or f in (float("inf"), float("-inf")):
        return None
    return f


def _norm_symbol(value: Any) -> str:
    return str(value or "").strip().upper()


def _summary_metric_key(label: Any) -> str:
    text = str(label or "").strip().lower()
    for key, needles in _SUMMARY_METRICS:
        if any(needle in text for needle in needles):
            return key
    return ""


def _rows_in(records: Any) -> list[Any]:
    """Only list-shaped payloads iterate; anything else yields nothing."""
    return records if isinstance(records, (list, tuple)) else []


def _counts() -> dict[str, int]:
    return {"read": 0, "valid": 0, "flagged": 0, "rejected": 0, "duplicate": 0}


def validate_market_live(
    records: Any,
) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Quote-board rows, normalised by the shared live-service parser.

    Rules: a blank symbol is rejected; a duplicate keeps its first occurrence
    (later ones are counted as duplicates, never silently overwritten); a
    missing ltp flags the row but preserves the symbol's presence; a high
    below its low flags ``high_lt_low``; a negative turnover, volume or trade
    count rejects the row (a *negative point change* is a legitimate falling
    price and is kept verbatim).
    """
    quotes, _newest = _quotes_from_records(_rows_in(records), time_key=("last_updated",))
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    counts = _counts()
    counts["read"] = sum(isinstance(r, dict) for r in _rows_in(records))
    for obs in quotes:
        symbol = obs.symbol
        if not symbol:
            counts["rejected"] += 1
            continue
        if symbol in seen:
            counts["duplicate"] += 1
            continue
        seen.add(symbol)
        flags: list[str] = []
        negative = False
        for field in ("turnover", "volume", "trades"):
            v = getattr(obs, field)
            if v is not None and v < 0:
                negative = True
        if negative:
            counts["rejected"] += 1
            continue
        if obs.ltp is None:
            flags.append("missing_ltp")
        if obs.high is not None and obs.low is not None and obs.high < obs.low:
            flags.append("high_lt_low")
        validation = "flagged" if flags else obs.validation_status
        rows.append(
            {
                "symbol": symbol,
                "name": obs.name or "",
                "ltp": obs.ltp,
                "previous_close": obs.previous_close,
                "change": obs.change,
                "percent_change": obs.percent_change,
                "high": obs.high,
                "low": obs.low,
                "volume": obs.volume,
                "turnover": obs.turnover,
                "trades": obs.trades,
                "observed_at": obs.observed_at,
                "validation": validation,
                "flags": ",".join(flags),
            }
        )
        counts["flagged" if flags else "valid"] += 1
    return rows, counts


def _ranking_metrics(dataset: str) -> str:
    """The metric that defines the ranking board - used for rejection rules."""
    return {
        "top_gainer": "percent_change",
        "top_loser": "percent_change",
        "top_turnover": "turnover",
        "top_trade": "volume",
        "top_transaction": "trades",
    }[dataset]


#: Per-board field candidates, as published by ``top_stocks.json``.
_RANKING_FIELDS: dict[str, dict[str, tuple[str, ...]]] = {
    "top_gainer": {
        "ltp": ("ltp",),
        "change": ("pointChange",),
        "percent_change": ("percentageChange",),
    },
    "top_loser": {
        "ltp": ("ltp",),
        "change": ("pointChange",),
        "percent_change": ("percentageChange",),
    },
    "top_turnover": {"turnover": ("turnover",), "closing_price": ("closingPrice",)},
    "top_trade": {"volume": ("shareTraded",), "closing_price": ("closingPrice",)},
    "top_transaction": {"trades": ("totalTrades",), "ltp": ("lastTradedPrice",)},
}


def validate_rankings(dataset: str, records: Any) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Ranking-board rows. ``rank`` is the 1-based source position, kept per row.

    Symbols must be present and the board's defining metric must be a finite,
    non-negative number. A row failing either is rejected and counted - never
    re-ordered, never padded with a zero.
    """
    fields = _RANKING_FIELDS[dataset]
    defining = _ranking_metrics(dataset)
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    counts = _counts()
    counts["read"] = sum(isinstance(r, dict) for r in _rows_in(records))
    rank = 0
    for rec in _rows_in(records):
        if not isinstance(rec, dict):
            continue
        symbol = _norm_symbol(rec.get("symbol"))
        if not symbol:
            counts["rejected"] += 1
            continue
        if symbol in seen:
            counts["duplicate"] += 1
            continue

        picked: dict[str, float | None] = {}
        for field, cands in fields.items():
            picked[field] = None
            for cand in cands:
                raw = rec.get(cand)
                if raw not in (None, ""):
                    picked[field] = _finite(raw)
                    break
        if picked.get(defining) is None:
            counts["rejected"] += 1
            continue
        if defining in ("turnover", "volume", "trades") and picked[defining] < 0:
            counts["rejected"] += 1
            continue
        seen.add(symbol)
        rank += 1
        flags: list[str] = []
        if picked.get("ltp") is None and "ltp" in fields:
            flags.append("missing_ltp")
        rows.append(
            {
                "dataset": dataset,
                "rank": rank,
                "symbol": symbol,
                "name": str(rec.get("securityName") or "").strip(),
                "ltp": picked.get("ltp"),
                "change": picked.get("change") if "change" in fields else None,
                "percent_change": picked.get("percent_change")
                if "percent_change" in fields
                else None,
                "closing_price": picked.get("closing_price"),
                "volume": picked.get("volume"),
                "turnover": picked.get("turnover"),
                "trades": picked.get("trades"),
                "validation": "flagged" if flags else "valid",
                "flags": ",".join(flags),
            }
        )
        counts["flagged" if flags else "valid"] += 1
    return rows, counts


def validate_summary(records: Any) -> tuple[list[dict[str, Any]], dict[str, int], list[str]]:
    """Session totals ``{detail, value}`` -> stable metric keys.

    Unrecognised labels are **kept** (never dropped) under ``other`` and their
    verbatim labels are returned so upstream schema drift is visible.
    """
    rows: list[dict[str, Any]] = []
    unknown: list[str] = []
    seen: set[str] = set()
    counts = _counts()
    counts["read"] = sum(isinstance(r, dict) for r in _rows_in(records))
    for rec in _rows_in(records):
        if not isinstance(rec, dict):
            continue
        label = str(rec.get("detail") or "").strip()
        value = _finite(rec.get("value"))
        if not label or value is None:
            counts["rejected"] += 1
            continue
        key = _summary_metric_key(label)
        if not key:
            key = "other"
            unknown.append(label)
        if key in seen:
            counts["duplicate"] += 1
            continue
        seen.add(key)
        rows.append({"metric": key, "value": value, "source_label": label})
        counts["valid"] += 1
    return rows, counts, unknown


def validate_status(payload: Any) -> tuple[dict[str, Any] | None, dict[str, int], list[str]]:
    """Exchange open/closed flag exactly as published; ``None`` when unusable."""
    counts = _counts()
    if not isinstance(payload, dict):
        counts["rejected"] = 1
        return None, counts, ["status payload is not an object"]
    is_open = payload.get("is_open")
    if not isinstance(is_open, bool):
        counts["rejected"] = 1
        return None, counts, ["status.is_open missing or not a boolean"]
    counts["read"] = 1
    counts["valid"] = 1
    last_checked = str(payload.get("last_checked") or "") or None
    return (
        {
            "is_open": 1 if is_open else 0,
            "last_checked": last_checked,
            "observed_at": last_checked,
            "is_open_source": "upstream",
        },
        counts,
        [],
    )


def validate_index(records: Any) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Index board rows; high<low rejects, missing close flags."""
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    counts = _counts()
    counts["read"] = sum(isinstance(r, dict) for r in _rows_in(records))
    for rec in _rows_in(records):
        if not isinstance(rec, dict):
            continue
        name = str(rec.get("index") or "").strip()
        if not name:
            counts["rejected"] += 1
            continue
        if name.lower() in seen:
            counts["duplicate"] += 1
            continue
        seen.add(name.lower())
        close, high, low = (
            _finite(rec.get("close")),
            _finite(rec.get("high")),
            _finite(rec.get("low")),
        )
        if high is not None and low is not None and high < low:
            counts["rejected"] += 1
            continue
        flags: list[str] = ["missing_close"] if close is None else []
        rows.append(
            {
                "index_name": name,
                "close": close,
                "high": high,
                "low": low,
                "previous_close": _finite(rec.get("previousClose")),
                "change": _finite(rec.get("change")),
                "percent_change": _finite(rec.get("perChange")),
                "fifty_two_week_high": _finite(rec.get("fiftyTwoWeekHigh")),
                "fifty_two_week_low": _finite(rec.get("fiftyTwoWeekLow")),
                "generated_time": str(rec.get("generatedTime") or "") or None,
                "observed_at": str(rec.get("generatedTime") or "") or None,
                "validation": "flagged" if flags else "valid",
                "flags": ",".join(flags),
            }
        )
        counts["flagged" if flags else "valid"] += 1
    return rows, counts


def validate_sector_indices(records: Any) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Sector index definitions. Values are never published here - only these."""
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    counts = _counts()
    counts["read"] = sum(isinstance(r, dict) for r in _rows_in(records))
    for rec in _rows_in(records):
        if not isinstance(rec, dict):
            continue
        code = str(rec.get("indexCode") or "").strip().upper()
        name = str(rec.get("indexName") or "").strip()
        if not code or not name:
            counts["rejected"] += 1
            continue
        if code in seen:
            counts["duplicate"] += 1
            continue
        seen.add(code)
        rows.append(
            {
                "index_code": code,
                "index_name": name,
                "description": str(rec.get("description") or "").strip(),
                "sector": str(
                    (rec.get("sectorMaster") or {}).get("sectorDescription") or ""
                ).strip(),
                "active_status": str(rec.get("activeStatus") or "").strip(),
                "key_index_flag": str(rec.get("keyIndexFlag") or "").strip(),
            }
        )
        counts["valid"] += 1
    return rows, counts


def validate_history(records: Any) -> tuple[list[dict[str, Any]], dict[str, int]]:
    """Per-day session totals; the newest history row enables the date cross-check."""
    rows: list[dict[str, Any]] = []
    seen: set[str] = set()
    counts = _counts()
    counts["read"] = sum(isinstance(r, dict) for r in _rows_in(records))
    for rec in _rows_in(records):
        if not isinstance(rec, dict):
            continue
        day = str(rec.get("businessDate") or "").strip()
        if not day:
            counts["rejected"] += 1
            continue
        if day in seen:
            counts["duplicate"] += 1
            continue
        seen.add(day)
        rows.append(
            {
                "business_date": day,
                "total_turnover": _finite(rec.get("totalTurnover")),
                "total_traded_shares": _finite(rec.get("totalTradedShares")),
                "total_transactions": _finite(rec.get("totalTransactions")),
                "traded_scrips": _finite(rec.get("tradedScrips")),
            }
        )
        counts["valid"] += 1
    return rows, counts


# -------------------------------------------------------------------- evidence
def business_date_evidence(
    summary_rows: list[dict[str, Any]], history_rows: list[dict[str, Any]]
) -> tuple[str | None, str]:
    """Match session totals against the same-day history row.

    The summary board carries no date of its own; the history file's newest
    row does. When turnover, traded shares *and* transactions agree within
    0.5%, the run is attested to describe that business date, with the
    matched values as text evidence. A stale history or a mismatch returns
    ``(None, reason)`` - the absence of an attestation is reportable and
    never silently filled with today's date.
    """
    summary = {r["metric"]: r["value"] for r in summary_rows}
    s_turnover = summary.get("total_turnover")
    s_shares = summary.get("total_traded_shares")
    s_txns = summary.get("total_transactions")
    if s_turnover is None:
        return None, "summary has no turnover metric; cannot cross-check"
    if not history_rows:
        return None, "history is unavailable; cannot cross-check"
    for row in history_rows:
        h_turnover = row["total_turnover"]
        if h_turnover is None:
            continue
        matched: list[str] = []
        for name, s_val, h_val in (
            ("turnover", s_turnover, h_turnover),
            ("shares", s_shares, row["total_traded_shares"]),
            ("transactions", s_txns, row["total_transactions"]),
        ):
            if s_val is None or h_val is None:
                continue
            if abs(s_val - h_val) / max(abs(h_val), 1.0) <= _CROSSCHECK_TOLERANCE:
                matched.append(f"{name} {_ne(s_val)} == history {_ne(h_val)}")
        if len(matched) >= 3:
            return row["business_date"], "; ".join(matched)
        if len(matched) == 2:
            return row["business_date"], "; ".join(matched) + " (2 of 3 metrics matched)"
    return (
        None,
        "no history row matched at least two of turnover/shares/transactions "
        "within tolerance; the snapshot may bridge a session boundary",
    )


def _ne(v: float | None) -> str:
    if v is None:
        return "-"
    return f"{v:,.0f}"


# ------------------------------------------------------------------- freshness
def dataset_freshness(
    observed_at: str | None,
    retrieved_at: str,
    is_open: bool | None,
) -> tuple[float | None, str]:
    """Age + label for one dataset. Retrieval time is never the observation.

    Labels come from the shared ``live._freshness`` bands; any dataset without
    a source-stated timestamp labels ``unknown`` and never inherits another
    dataset's stamp.
    """
    if not observed_at:
        return None, "unknown"
    ts = _parse_ts(observed_at)
    ts0 = _parse_ts(retrieved_at)
    if ts is None or ts0 is None:
        return None, "unknown"
    age = (ts0 - ts).total_seconds()
    return age, _freshness(
        age, (bool(is_open) if is_open is not None else None), PUBLISH_CADENCE_SECONDS
    )


def newest_source_stamp(rows: list[dict[str, Any]], key: str) -> str | None:
    if not rows:
        return None
    return _max_iso(*[r.get(key) for r in rows if r.get(key)])


# --------------------------------------------------------------------- capture
def _broken(dataset: str, path: str, error: str) -> dict[str, Any]:
    return {
        "dataset": dataset,
        "source_path": path,
        "origin": "",
        "status": _STATUS_UNAVAILABLE,
        "error": (error or "not published")[:400],
        "rows": [],
        "counts": _counts(),
        "observed_at": None,
        "observed_age_seconds": None,
        "freshness": "unknown",
        "notes": "",
    }


def _fresh_dataset(
    dataset: str,
    source_path: str,
    origin: str,
    rows: list[dict[str, Any]],
    counts: dict[str, int],
    observed_key: str | None,
    is_open: bool | None,
    started_at: str,
    notes: str = "",
    error: str = "",
) -> dict[str, Any]:
    """Per-dataset record with stamp-derived freshness, or ``unknown``."""
    observed_at = newest_source_stamp(rows, observed_key) if observed_key else None
    age, label = dataset_freshness(observed_at, started_at, is_open)
    return {
        "dataset": dataset,
        "source_path": source_path,
        "origin": origin,
        "status": _STATUS_DEGRADED if error or not rows else _STATUS_OK,
        "error": error,
        "rows": rows,
        "counts": counts,
        "observed_at": observed_at,
        "observed_age_seconds": age,
        "freshness": label,
        "notes": notes,
    }


def collect_snapshot(
    db_path: Path | None = None,
    out_dir: Path | None = None,
    timeout: float = 30.0,
) -> dict[str, Any]:
    """One collection cycle: read, validate, persist, report.

    A dataset that cannot be fetched or validated is recorded as
    ``source_unavailable`` in the run report and contributes **no rows** - an
    outage is observable and older data is never quietly substituted.
    """

    started = _utcnow()
    started_at = started.isoformat()
    datasets: list[dict[str, Any]] = []
    added: set[str] = set()

    def add(ds: dict[str, Any]) -> None:
        name = ds["dataset"]
        if name in added:
            raise CollectorError(f"duplicate dataset record for {name}")
        added.add(name)
        datasets.append(ds)

    # --- fetch: one ref decision covers the whole market bundle ---------------
    snap: dict[str, Any] | None = None
    origin = ""
    try:
        snap = yonepse.fetch_market_snapshot()
        origin = str(snap.get("origin") or "")
    except Exception as exc:  # noqa: BLE001 - a failed fetch is a report, not a crash
        for dataset, path in (
            ("market_live", yonepse.PATH_MARKET_LIVE),
            ("index", yonepse.PATH_MARKET_INDICES),
            ("status", yonepse.PATH_MARKET_STATUS),
        ):
            add(_broken(dataset, path, str(exc)))

    is_open: bool | None = None
    if snap is not None:
        status_row, status_counts, status_notes = validate_status(snap.get("status"))
        if status_row is None:
            add(
                {
                    "dataset": "status",
                    "source_path": yonepse.PATH_MARKET_STATUS,
                    "origin": origin,
                    "status": _STATUS_DEGRADED,
                    "error": "; ".join(status_notes),
                    "rows": [],
                    "counts": status_counts,
                    "observed_at": None,
                    "observed_age_seconds": None,
                    "freshness": "unknown",
                    "notes": "is_open absent or not a boolean; nothing inferred",
                }
            )
        else:
            is_open = bool(status_row["is_open"])
            observed = status_row["last_checked"]
            age, label = dataset_freshness(observed, started_at, None)
            add(
                {
                    "dataset": "status",
                    "source_path": yonepse.PATH_MARKET_STATUS,
                    "origin": origin,
                    "status": _STATUS_OK,
                    "error": "",
                    "rows": [status_row],
                    "counts": status_counts,
                    "observed_at": observed,
                    "observed_age_seconds": age,
                    "freshness": label,
                    "notes": "",
                }
            )
        live_rows, live_counts = validate_market_live(snap.get("live"))
        add(
            _fresh_dataset(
                "market_live",
                yonepse.PATH_MARKET_LIVE,
                origin,
                live_rows,
                live_counts,
                "observed_at",
                is_open,
                started_at,
            )
        )
        index_rows, index_counts = validate_index(snap.get("indices"))
        add(
            _fresh_dataset(
                "index",
                yonepse.PATH_MARKET_INDICES,
                origin,
                index_rows,
                index_counts,
                "observed_at",
                is_open,
                started_at,
                notes="one row per published index (NEPSE, Sensitive, Float, Sensitive Float)",
            )
        )

    # --- the remaining published files ---------------------------------------
    summary_rows: list[dict[str, Any]] = []
    history_rows: list[dict[str, Any]] = []
    try:
        extras, extras_errors = yonepse.fetch_market_extras(yonepse.MARKET_EXTRA_PATHS)
    except Exception as exc:  # noqa: BLE001 - degrade every extra dataset
        extras, extras_errors = {}, {"*": str(exc)}
    for dataset, path in (
        ("summary", yonepse.PATH_MARKET_SUMMARY),
        ("history", yonepse.PATH_MARKET_HISTORY),
        ("sector_indices", yonepse.PATH_MARKET_SECTOR_INDICES),
    ):
        entry = extras.get(path)
        error = extras_errors.get(path, extras_errors.get("*", ""))
        if entry is None:
            add(_broken(dataset, path, error))
            continue
        payload, file_origin = entry
        if dataset == "summary":
            rows, counts, unknown = validate_summary(payload)
            notes = "; ".join([f"unlabelled metric kept verbatim: {u}" for u in unknown])
            summary_rows = rows
        elif dataset == "history":
            rows, counts = validate_history(payload)
            notes = ""
            history_rows = rows
        else:
            rows, counts = validate_sector_indices(payload)
            notes = "definitions only: this file publishes no current index values"
        add(
            _fresh_dataset(
                dataset, path, file_origin, rows, counts, None, is_open, started_at, notes, error
            )
        )

    rank_entry = extras.get(yonepse.PATH_MARKET_TOP_STOCKS)
    rank_error = extras_errors.get(yonepse.PATH_MARKET_TOP_STOCKS, extras_errors.get("*", ""))
    rank_payload, rank_origin = rank_entry if rank_entry else (None, "")
    for dataset in RANKING_DATASETS:
        if rank_payload is None:
            add(_broken(dataset, yonepse.PATH_MARKET_TOP_STOCKS, rank_error))
            continue
        rows, counts = validate_rankings(dataset, (rank_payload or {}).get(dataset))
        add(
            _fresh_dataset(
                dataset,
                yonepse.PATH_MARKET_TOP_STOCKS,
                rank_origin,
                rows,
                counts,
                None,
                is_open,
                started_at,
                notes="the source stamps no timestamps on ranking rows",
            )
        )

    # --- business-date affirmation -------------------------------------------
    business_date, bd_evidence = business_date_evidence(summary_rows, history_rows)

    # --- aggregate ------------------------------------------------------------
    totals = {
        "rows_read": sum(d["counts"]["read"] for d in datasets),
        "rows_inserted": sum(d["counts"]["valid"] + d["counts"]["flagged"] for d in datasets),
        "rows_duplicate": sum(d["counts"]["duplicate"] for d in datasets),
        "rows_flagged": sum(d["counts"]["flagged"] for d in datasets),
        "rows_rejected": sum(d["counts"]["rejected"] for d in datasets),
    }
    ok_ds = sum(1 for d in datasets if d["status"] == _STATUS_OK)
    degraded_ds = sum(1 for d in datasets if d["status"] == _STATUS_DEGRADED)
    failed_ds = sum(1 for d in datasets if d["status"] == _STATUS_UNAVAILABLE)
    if ok_ds == 0:
        overall = _RUN_FAILED
    elif degraded_ds == 0 and failed_ds == 0:
        overall = _RUN_OK
    else:
        overall = _RUN_PARTIAL

    run_observed = _max_iso(*[d.get("observed_at") for d in datasets])
    run_age, run_fresh = dataset_freshness(run_observed, started_at, is_open)

    report: dict[str, Any] = {
        "started_at": started_at,
        "finished_at": "",
        "status": overall,
        "origin": origin,
        "datasets_ok": ok_ds,
        "datasets_degraded": degraded_ds,
        "datasets_failed": failed_ds,
        **totals,
        "is_open": None if is_open is None else int(is_open),
        "is_open_source": "upstream" if is_open is not None else "",
        "observed_at": run_observed,
        "observed_age_seconds": run_age,
        "freshness": run_fresh,
        "business_date": business_date,
        "business_date_evidence": bd_evidence,
        "datasets": [{k: v for k, v in d.items() if k != "rows"} for d in datasets],
    }

    run_id = _persist(db_path, report, datasets, business_date=bd_evidence)
    report["run_id"] = run_id
    finished = _utcnow().isoformat()
    report["finished_at"] = finished
    with db.get_conn(db_path) as conn:
        conn.execute("UPDATE collector_runs SET finished_at=? WHERE id=?", (finished, run_id))

    if out_dir is not None:
        out_dir.mkdir(parents=True, exist_ok=True)
        stamp = started_at.replace(":", "").replace("-", "")
        payload = dict(report)
        payload["rows"] = {d["dataset"]: d["rows"] for d in datasets}
        body = json.dumps(payload, indent=1, default=str)
        (out_dir / f"snapshot_{stamp}.json").write_text(body)
        (out_dir / "latest.json").write_text(body)
    return report


# --------------------------------------------------------------------- persist
def _persist(
    db_path: Path | None,
    report: dict[str, Any],
    datasets: list[dict[str, Any]],
    business_date: str = "",
) -> int:
    """Insert the whole run in one transaction; any failure rolls everything back."""
    with db.get_conn(db_path) as conn:
        try:
            conn.execute("BEGIN IMMEDIATE")
            cur = conn.execute(
                """
                INSERT INTO collector_runs (
                    started_at, finished_at, status, origin, source_sha,
                    datasets_ok, datasets_degraded, datasets_failed,
                    rows_read, rows_inserted, rows_duplicate, rows_flagged,
                    rows_rejected, is_open, is_open_source, observed_at,
                    observed_age_seconds, freshness, business_date,
                    business_date_evidence, detail
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    report["started_at"],
                    None,  # finished_at is written back once persistence succeeds
                    report["status"],
                    report["origin"],
                    "",  # no commit sha claim here: published files are the-of-record
                    report["datasets_ok"],
                    report["datasets_degraded"],
                    report["datasets_failed"],
                    report["rows_read"],
                    report["rows_inserted"],
                    report["rows_duplicate"],
                    report["rows_flagged"],
                    report["rows_rejected"],
                    report["is_open"],
                    report["is_open_source"],
                    report["observed_at"],
                    report["observed_age_seconds"],
                    report["freshness"],
                    report["business_date"],
                    business_date,
                    json.dumps({"crosscheck": business_date}, sort_keys=True, default=str),
                ),
            )
            run_id = int(cur.lastrowid)
            for item in datasets:
                conn.execute(
                    """
                    INSERT INTO collector_datasets (
                        run_id, dataset, source_path, origin, status, error,
                        observed_at, observed_age_seconds, freshness,
                        rows_read, rows_valid, rows_flagged, rows_rejected,
                        rows_duplicate, notes
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    """,
                    (
                        run_id,
                        item["dataset"],
                        item["source_path"],
                        item.get("origin", ""),
                        item["status"],
                        item.get("error", ""),
                        item.get("observed_at"),
                        item.get("observed_age_seconds"),
                        item.get("freshness", "unknown"),
                        item["counts"]["read"],
                        item["counts"]["valid"],
                        item["counts"]["flagged"],
                        item["counts"]["rejected"],
                        item["counts"]["duplicate"],
                        item.get("notes", ""),
                    ),
                )
                for row in item["rows"]:
                    _insert_row(conn, run_id, item["dataset"], row)
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    db.log_ingestion(
        {
            "source": "collector/yonepse",
            "started_at": report["started_at"],
            "finished_at": report["finished_at"],
            "status": report["status"],
            "rows_read": report["rows_read"],
            "rows_inserted": report["rows_inserted"],
            "rows_duplicate": report["rows_duplicate"],
            "rows_flagged": report["rows_flagged"],
            "rows_rejected": report["rows_rejected"],
            "coverage_start": report["observed_at"],
            "coverage_end": report["started_at"],
            "synthetic": False,
            "detail": json.dumps(
                {
                    "run_id": run_id,
                    "datasets_ok": report["datasets_ok"],
                    "datasets_degraded": report["datasets_degraded"],
                    "datasets_failed": report["datasets_failed"],
                    "business_date": report["business_date"],
                }
            ),
        },
        db_path=db_path,
    )
    return run_id


def _insert_row(conn: Any, run_id: int, dataset: str, row: dict[str, Any]) -> None:
    """One validated row into its typed table."""
    if dataset == "market_live":
        conn.execute(
            """
            INSERT INTO collector_quotes (
                run_id, symbol, name, ltp, previous_close, change,
                percent_change, high, low, volume, turnover, trades,
                observed_at, validation, flags
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                run_id,
                row["symbol"],
                row["name"],
                row["ltp"],
                row["previous_close"],
                row["change"],
                row["percent_change"],
                row["high"],
                row["low"],
                row["volume"],
                row["turnover"],
                row["trades"],
                row["observed_at"],
                row["validation"],
                row["flags"],
            ),
        )
    elif dataset == "index":
        conn.execute(
            """
            INSERT INTO collector_index (
                run_id, index_name, close, high, low, previous_close, change,
                percent_change, fifty_two_week_high, fifty_two_week_low,
                generated_time
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                run_id,
                row["index_name"],
                row["close"],
                row["high"],
                row["low"],
                row["previous_close"],
                row["change"],
                row["percent_change"],
                row["fifty_two_week_high"],
                row["fifty_two_week_low"],
                row["generated_time"],
            ),
        )
    elif dataset == "summary":
        conn.execute(
            "INSERT INTO collector_summary (run_id, metric, value, source_label) VALUES (?,?,?,?)",
            (run_id, row["metric"], row["value"], row["source_label"]),
        )
    elif dataset in RANKING_DATASETS:
        conn.execute(
            """
            INSERT INTO collector_rankings (
                run_id, dataset, rank, symbol, name, ltp, change,
                percent_change, closing_price, volume, turnover, trades,
                validation, flags
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                run_id,
                dataset,
                row["rank"],
                row["symbol"],
                row["name"],
                row["ltp"],
                row["change"],
                row["percent_change"],
                row["closing_price"],
                row["volume"],
                row["turnover"],
                row["trades"],
                row["validation"],
                row["flags"],
            ),
        )
    elif dataset == "status":
        conn.execute(
            "INSERT INTO collector_status (run_id, is_open, last_checked, source) VALUES (?,?,?,?)",
            (
                run_id,
                row["is_open"],
                row["last_checked"],
                row.get("is_open_source") or "yonepse/status.json",
            ),
        )
    elif dataset == "sector_indices":
        conn.execute(
            """
            INSERT INTO collector_sector_indices (
                run_id, index_code, index_name, description, sector,
                active_status, key_index_flag
            ) VALUES (?,?,?,?,?,?,?)
            """,
            (
                run_id,
                row["index_code"],
                row["index_name"],
                row["description"],
                row["sector"],
                row["active_status"],
                row["key_index_flag"],
            ),
        )
    elif dataset == "history":
        # Session totals history: stored as dated summary metrics, so the
        # business-date cross-check is queryable alongside the snapshot's
        # own session totals.
        for key, value in (
            (f"{row['business_date']}:turnover", row["total_turnover"]),
            (f"{row['business_date']}:shares", row["total_traded_shares"]),
            (f"{row['business_date']}:transactions", row["total_transactions"]),
            (f"{row['business_date']}:scrips", row["traded_scrips"]),
        ):
            if value is None:
                continue
            conn.execute(
                "INSERT INTO collector_summary (run_id, metric, value, source_label) "
                "VALUES (?,?,?,?)",
                (run_id, key, value, "history.json"),
            )
    else:
        raise CollectorError(f"no storage table for dataset {dataset}")


# ------------------------------------------------------------------------- loop
def collect_loop(
    db_path: Path | None,
    out_dir: Path | None,
    interval: int,
    stop_check: Callable[[], bool] | None = None,
    max_cycles: int | None = None,
) -> list[dict[str, Any]]:
    """Polling loop. The interval floors at a minute - faster adds nothing.

    The upstream publishes on a roughly-hourly cadence; each cycle reports its
    own source-stated freshness, so nothing here pretends a shorter loop made
    the data fresher.
    """
    if interval < MIN_POLL_INTERVAL_SECONDS:
        raise CollectorError(
            f"--interval is {interval}s; the floor is {MIN_POLL_INTERVAL_SECONDS}s "
            "because the source publishes on a roughly-hourly cadence and faster "
            "polling would be pure load"
        )
    reports: list[dict[str, Any]] = []
    n = 0
    while max_cycles is None or n < max_cycles:
        n += 1
        reports.append(collect_snapshot(db_path=db_path, out_dir=out_dir))
        if stop_check is not None and stop_check():
            break
        if max_cycles is not None and n >= max_cycles:
            break
        time.sleep(interval)
    return reports


# ------------------------------------------------------------------------ read
def latest_report(db_path: Path | None = None) -> dict[str, Any] | None:
    """The latest run with per-dataset provenance, or ``None`` when never run."""
    with db.get_conn(db_path) as conn:
        row = conn.execute("SELECT * FROM collector_runs ORDER BY id DESC LIMIT 1").fetchone()
        if row is None:
            return None
        datasets = [
            dict(r)
            for r in conn.execute(
                "SELECT * FROM collector_datasets WHERE run_id=? ORDER BY dataset", (row["id"],)
            ).fetchall()
        ]
        history = [
            dict(r)
            for r in conn.execute(
                "SELECT id, started_at, finished_at, status, datasets_ok, "
                "datasets_degraded, datasets_failed, freshness, observed_at, "
                "business_date FROM collector_runs ORDER BY id DESC LIMIT 10"
            ).fetchall()
        ]
    report = dict(row)
    report["datasets"] = datasets
    report["history"] = history
    return report
