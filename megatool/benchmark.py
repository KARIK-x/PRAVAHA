"""Pure logic for the market-hours benchmark harness.

This module contains **no I/O and no network code** so it can be unit-tested
with fixtures. ``scripts/benchmark_market_hours.py`` owns the sampling loop,
the authorization gate and the file writes, and calls into here.

The point of the benchmark is to measure the one quantity the 2026-10-15 probe
could *not* measure because the market was closed: the source's **intraday
update cadence** (how often new data actually appears), as distinct from how
fast a request returns.

Quantities are kept strictly separate:

1. **request duration** — request start → response received (``duration_ms``);
2. **source-data age** — observation time − the source's own timestamp, when the
   timestamp's meaning is known (``source_ts_utc``);
3. **snapshot-change interval** — elapsed time between *distinct* observed
   snapshots (``estimate_cadence``);
4. **ingestion latency** — source timestamp → local ingest (measured elsewhere,
   in the ingest script; not here);
5. **end-to-end freshness** — age of data delivered to the app (the store's
   ``freshness_class``; not here);
6. **true event latency** — event → receipt. There is no trustworthy *event*
   timestamp on this API, so it is **UNMEASURABLE** and never invented.

Nepal Time is UTC+05:45 (no DST). NEPSE trades Sunday–Thursday, 11:00–15:00 NPT
in the continuous session.
"""

from __future__ import annotations

import hashlib
import json
import statistics
from datetime import UTC, datetime, time, timedelta, timezone
from typing import Any

#: Nepal Time — a fixed UTC+05:45 offset (no daylight saving).
NPT = timezone(timedelta(hours=5, minutes=45), name="NPT")

#: Continuous-session boundaries, in Nepal local time.
MARKET_OPEN_NPT = time(11, 0)
MARKET_CLOSE_NPT = time(15, 0)

#: ``datetime.weekday()`` values on which NEPSE trades (Mon=0 … Sun=6).
TRADING_WEEKDAYS = frozenset({6, 0, 1, 2, 3})  # Sun, Mon, Tue, Wed, Thu

#: The headline endpoints the benchmark samples, in display order.
BENCHMARK_ENDPOINTS = ("market-open", "nepse-index", "market-summary", "lives-market")

#: True event latency cannot be derived from this source: mark, never invent.
TRUE_EVENT_LATENCY = "UNMEASURABLE"


# ------------------------------------------------------------------- timezone
def to_npt(dt: datetime) -> datetime:
    """Convert an aware datetime to Nepal Time. Naive input is assumed UTC."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(NPT)


def to_utc(dt: datetime) -> datetime:
    """Convert an aware datetime to UTC. Naive input is assumed Nepal Time."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=NPT)
    return dt.astimezone(UTC)


def iso_npt(dt: datetime) -> str:
    """Render an aware datetime as an ISO-8601 string in Nepal Time."""
    return to_npt(dt).isoformat()


def parse_iso(value: str) -> datetime:
    """Parse an ISO-8601 string, assuming Nepal Time when it carries no offset."""
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=NPT)
    return dt


def in_market_hours(dt: datetime) -> bool:
    """True when ``dt`` falls in NEPSE's Sun–Thu, 11:00–15:00 NPT session."""
    local = to_npt(dt)
    if local.weekday() not in TRADING_WEEKDAYS:
        return False
    return MARKET_OPEN_NPT <= local.time() < MARKET_CLOSE_NPT


def next_session_open(after: datetime) -> datetime:
    """The next 11:00 NPT session open strictly after ``after`` (aware, in NPT)."""
    local = to_npt(after)
    candidate = datetime.combine(local.date(), MARKET_OPEN_NPT, tzinfo=NPT)
    if candidate <= local:
        candidate += timedelta(days=1)
    for _ in range(8):  # bounded: a trading day always occurs within a week
        if candidate.weekday() in TRADING_WEEKDAYS:
            return candidate
        candidate += timedelta(days=1)
    return candidate  # pragma: no cover - unreachable with TRADING_WEEKDAYS set


# ------------------------------------------------------------------- payloads
def snapshot_hash(payload: Any) -> str:
    """A stable hash of a parsed payload, used to detect *new* data.

    Canonical JSON (sorted keys, compact separators) so incidental key order or
    whitespace never looks like a change. Only genuine content differences do.
    """
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return "sha256:" + hashlib.sha256(blob.encode("utf-8")).hexdigest()


def record_count(payload: Any) -> int | None:
    """Number of records in a list payload, or the length of the first list field."""
    if isinstance(payload, list):
        return len(payload)
    if isinstance(payload, dict):
        for value in payload.values():
            if isinstance(value, list):
                return len(value)
        return len(payload)
    return None


def _max_timestamp(records: Any, field: str) -> datetime | None:
    best: datetime | None = None
    if not isinstance(records, list):
        return None
    for rec in records:
        if not isinstance(rec, dict):
            continue
        raw = rec.get(field)
        if not isinstance(raw, str) or not raw.strip():
            continue
        try:
            ts = parse_iso(raw.strip().replace("Z", "+00:00"))
        except ValueError:
            continue
        ts = to_utc(ts)
        if best is None or ts > best:
            best = ts
    return best


def extract_source_ts(endpoint: str, payload: Any) -> tuple[str | None, datetime | None]:
    """Return ``(field_name, timestamp_utc)`` for a payload, when one exists.

    * ``market-open`` → ``asOf`` (the exchange's session observation time);
    * ``nepse-index`` → the newest ``generatedTime`` across index rows;
    * ``lives-market`` → the newest ``lastUpdatedDateTime`` across quotes;
    * ``market-summary`` → ``None`` (it carries no timestamp at all).

    Naive source strings are Nepal local time. A missing timestamp is reported
    as ``None`` — never substituted with "now".
    """
    if endpoint == "market-open" and isinstance(payload, dict):
        raw = payload.get("asOf")
        if isinstance(raw, str) and raw.strip():
            try:
                return "asOf", to_utc(parse_iso(raw.strip().replace("Z", "+00:00")))
            except ValueError:
                return None, None
        return None, None
    if endpoint == "nepse-index":
        ts = _max_timestamp(payload, "generatedTime")
        return ("generatedTime", ts) if ts else (None, None)
    if endpoint == "lives-market":
        ts = _max_timestamp(payload, "lastUpdatedDateTime")
        return ("lastUpdatedDateTime", ts) if ts else (None, None)
    if endpoint == "yonepse-live":
        ts = _max_timestamp(payload, "last_updated")
        return ("last_updated", ts) if ts else (None, None)
    if endpoint == "yonepse-status" and isinstance(payload, dict):
        raw = payload.get("last_checked")
        if isinstance(raw, str) and raw.strip():
            try:
                return "last_checked", to_utc(parse_iso(raw.strip().replace("Z", "+00:00")))
            except ValueError:
                return None, None
        return None, None
    return None, None


# -------------------------------------------------------------------- summary
def _percentile(values: list[float], q: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    idx = max(0, min(len(ordered) - 1, int(round(q * (len(ordered) - 1)))))
    return ordered[idx]


def estimate_cadence(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Estimate the snapshot-change interval for one endpoint from its samples.

    A "change" is the first sample whose ``snapshot_hash`` differs from the
    previously seen hash. Identical consecutive snapshots are *not* evidence of
    staleness on their own — they may simply mean the benchmark polled faster
    than the source updates — so this reports change *intervals*, never a claim
    that the source updates at the polling rate.
    """
    ordered = sorted(records, key=lambda r: r["request_start_utc"])
    changes: list[dict[str, Any]] = []
    if not ordered:
        return {
            "distinct_snapshots": 0,
            "changes_observed": 0,
            "cadence_seconds": None,
            "first_snapshot_utc": None,
            "change_times_utc": [],
        }

    current_hash = ordered[0].get("snapshot_hash")
    first_time = ordered[0]["request_start_utc"]
    for rec in ordered[1:]:
        h = rec.get("snapshot_hash")
        if h is not None and h != current_hash:
            changes.append({"at_utc": rec["request_start_utc"], "hash": h})
            current_hash = h

    distinct = len({r.get("snapshot_hash") for r in ordered if r.get("snapshot_hash")})
    cadence = None
    if len(changes) >= 1:
        times = [parse_iso(first_time)] + [parse_iso(c["at_utc"]) for c in changes]
        deltas = [(times[i + 1] - times[i]).total_seconds() for i in range(len(times) - 1)]
        deltas = [d for d in deltas if d > 0]
        if deltas:
            cadence = round(statistics.median(deltas), 1)
    return {
        "distinct_snapshots": distinct,
        "changes_observed": len(changes),
        "cadence_seconds": cadence,
        "first_snapshot_utc": first_time,
        "change_times_utc": [c["at_utc"] for c in changes],
    }


def _freshness(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Source-data age statistics for records that carry a source timestamp."""
    ages: list[float] = []
    for rec in records:
        ts = rec.get("source_ts_utc")
        if not ts:
            continue
        try:
            delta = (parse_iso(rec["request_start_utc"]) - parse_iso(ts)).total_seconds()
        except ValueError:
            continue
        ages.append(delta)
    if not ages:
        return {
            "samples_with_source_ts": 0,
            "age_seconds_median": None,
            "age_seconds_max": None,
            "pct_le_5s": None,
            "pct_le_20s": None,
            "note": "no source timestamp on this endpoint — freshness % is not computable",
        }
    return {
        "samples_with_source_ts": len(ages),
        "age_seconds_median": round(statistics.median(ages), 1),
        "age_seconds_max": round(max(ages), 1),
        "pct_le_5s": round(100.0 * sum(1 for a in ages if a <= 5) / len(ages), 1),
        "pct_le_20s": round(100.0 * sum(1 for a in ages if a <= 20) / len(ages), 1),
        "note": "age = observation time − source timestamp (NPT→UTC); "
        "assumes the source timestamp is the exchange's own observation time",
    }


def summarize(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Roll a list of JSONL sample records into a per-endpoint summary.

    Separates request latency from data freshness from update cadence, and marks
    true event latency as UNMEASURABLE rather than inferring it.
    """
    by_endpoint: dict[str, list[dict[str, Any]]] = {}
    for rec in records:
        by_endpoint.setdefault(str(rec.get("endpoint", "?")), []).append(rec)

    endpoints: dict[str, Any] = {}
    for name in sorted(by_endpoint):
        rows = by_endpoint[name]
        durations = [float(r["duration_ms"]) for r in rows if r.get("duration_ms") is not None]
        ok = [r for r in rows if r.get("status") == 200]
        bad = [r for r in rows if r.get("status") != 200]
        src_ts = {r["source_ts_utc"] for r in rows if r.get("source_ts_utc")}
        endpoints[name] = {
            "requests": len(rows),
            "successes": len(ok),
            "failures": len(bad),
            "status_codes": sorted({r.get("status") for r in rows}),
            "request_duration_ms": {
                "n": len(durations),
                "avg": round(statistics.mean(durations), 1) if durations else None,
                "median": round(statistics.median(durations), 1) if durations else None,
                "p95": _percentile(durations, 0.95),
                "max": round(max(durations), 1) if durations else None,
            },
            "record_counts": sorted({r.get("records") for r in rows}),
            "distinct_source_timestamps": sorted(src_ts),
            "freshness": _freshness(rows),
            "cadence": estimate_cadence(rows),
        }

    total = len(records)
    ok_total = sum(1 for r in records if r.get("status") == 200)
    return {
        "samples": total,
        "successes": ok_total,
        "failures": total - ok_total,
        "endpoints": endpoints,
        "true_event_latency": TRUE_EVENT_LATENCY,
        "notes": [
            "Request duration is NOT data freshness.",
            "Cadence is estimated from observed snapshot *changes*, not request "
            "speed; identical snapshots alone do not prove staleness.",
            "True event latency is UNMEASURABLE: the API exposes no trustworthy event timestamp.",
        ],
    }
