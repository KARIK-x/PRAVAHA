#!/usr/bin/env python
"""Market-hours benchmark harness for NEPSE data freshness/cadence.

WHY THIS EXISTS
---------------
The 2026-10-15 probe could measure *request duration* but not the source's
intraday **update cadence**, because the market was closed and the intraday
board was empty. This harness samples the probe endpoints during the Sun–Thu
11:00–15:00 NPT session so cadence can be measured from observed snapshot
*changes* — not from request speed.

THE GATE (read carefully)
-------------------------
This script **never** turns the NEPSE authorization on. It only reads
``MEGATOOL_NEPSE_API_AUTHORIZED`` from the environment:

* if it is absent/not ``1``, the script makes **zero** requests to any
  ``nepalstock.com.np`` endpoint and prints schedule-only instructions;
* YONEPSE is an authorised public snapshot and may be sampled ungated.

TLS verification is always on. Intervals are configurable (default 60 s, floor
3 s). A faster poll is a *measurement configuration*, never evidence that the
source produces new data that fast. Requests, retries, timeouts and total
duration are all bounded.

MODES
-----
* live sample   — ``--source nepse --interval 60 --duration-minutes 240``
* schedule-only — automatic when unauthorised or outside market hours
* ``--replay``  — analyse a saved JSONL into a summary, with no network at all
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import re
import sys
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from megatool import benchmark as bench  # noqa: E402
from megatool.datasources import nepse_official_live as ol  # noqa: E402

DEFAULT_INTERVAL_SECONDS = 60.0
MIN_INTERVAL_SECONDS = 3.0
DEFAULT_DURATION_MINUTES = 30.0
DEFAULT_MAX_REQUESTS = 200
DEFAULT_OUT_DIR = ROOT / "data" / "review" / "benchmarks"

_HTTP_RE = re.compile(r"HTTP (\d{3})")


# --------------------------------------------------------------- sample plumbing
def _utcnow() -> datetime:
    return datetime.now(UTC)


def _status_from_error(exc: BaseException) -> int | None:
    code = getattr(exc, "code", None)  # urllib.HTTPError
    if isinstance(code, int):
        return code
    m = _HTTP_RE.search(str(exc))
    return int(m.group(1)) if m else None


def _sample(
    endpoint: str,
    source: str,
    call: Callable[[], Any],
    seq: int,
    run_id: str,
) -> dict[str, Any]:
    start = _utcnow()
    status: int | None = None
    payload: Any = None
    error: str | None = None
    try:
        payload = call()
        status = 200
    except Exception as exc:  # noqa: BLE001 - the harness records, never raises
        status = _status_from_error(exc)
        error = f"{type(exc).__name__}: {exc}"
    end = _utcnow()

    ts_field, ts_utc = (None, None)
    if payload is not None:
        ts_field, ts_utc = bench.extract_source_ts(endpoint, payload)

    return {
        "run_id": run_id,
        "seq": seq,
        "source": source,
        "endpoint": endpoint,
        "request_start_utc": start.isoformat(),
        "request_end_utc": end.isoformat(),
        "request_start_npt": bench.iso_npt(start),
        "status": status,
        "duration_ms": round((end - start).total_seconds() * 1000.0, 1),
        "records": bench.record_count(payload) if payload is not None else None,
        "snapshot_hash": bench.snapshot_hash(payload) if payload is not None else None,
        "source_ts_field": ts_field,
        "source_ts_utc": ts_utc.isoformat() if ts_utc else None,
        "error": error,
    }


def _nepse_calls(client: ol.NepseOfficialLiveClient) -> dict[str, Callable[[], Any]]:
    return {
        "market-open": client.market_status,
        "nepse-index": client.indices,
        "market-summary": client.market_summary,
        "lives-market": client.live_market,
    }


def _yonepse_calls() -> dict[str, Callable[[], Any]]:
    from megatool.datasources import yonepse

    return {
        "yonepse-live": yonepse.fetch_market_live,
        "yonepse-status": yonepse.fetch_market_status,
    }


# ------------------------------------------------------------------- scheduling
def _cron_entry(next_open_npt: datetime, command: str) -> str:
    """A crontab line for the next session open, in the machine's local time."""
    local = next_open_npt.astimezone()  # no-arg → system local timezone
    cron_dow = (local.weekday() + 1) % 7  # cron: 0=Sunday … 6=Saturday
    return f"{local.minute} {local.hour} * * {cron_dow} {command}"


def _launchd_plist(label: str, next_open_npt: datetime, command: str) -> str:
    local = next_open_npt.astimezone()
    cron_dow = (local.weekday() + 1) % 7
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>{label}</string>
  <key>ProgramArguments</key>
  <array><string>/bin/sh</string><string>-lc</string><string>{command}</string></array>
  <!-- Weekday: 0/7=Sunday … 6=Saturday; uses the machine's local time. -->
  <key>StartCalendarInterval</key>
  <dict>
    <key>Weekday</key><integer>{cron_dow}</integer>
    <key>Hour</key><integer>{local.hour}</integer>
    <key>Minute</key><integer>{local.minute}</integer>
  </dict>
  <key>StandardOutPath</key><string>{DEFAULT_OUT_DIR}/launchd.out.log</string>
  <key>StandardErrorPath</key><string>{DEFAULT_OUT_DIR}/launchd.err.log</string>
</dict></plist>"""


def _print_schedule_only(reason: str, args: argparse.Namespace, now: datetime) -> None:
    nxt = bench.next_session_open(now)
    cmd = (
        "cd "
        + f'"{ROOT}"'
        + " && "
        + f"{ol.AUTH_ENV}=1 .venv/bin/python scripts/benchmark_market_hours.py "
        + f"--source nepse --interval {args.interval:g} "
        + f"--duration-minutes {args.duration_minutes:g} "
        + f"--max-requests {args.max_requests}"
    )
    print("=" * 72)
    print("SCHEDULE-ONLY MODE — no NEPSE requests were made.")
    print("=" * 72)
    print(f"reason            : {reason}")
    print(f"now (NPT)         : {bench.iso_npt(now)}")
    print(f"next session open : {nxt.isoformat()}  ({nxt.astimezone()})")
    print("session window    : Sun–Thu 11:00–15:00 NPT (05:15–09:15 UTC)")
    print()
    print("Run this during the session (requires an explicit owner ruling):")
    print(f"    {cmd}")
    print()
    print("Or schedule it. crontab -e  →  add:")
    print(f"    {_cron_entry(nxt, cmd)}")
    print()
    print("macOS launchd — save as ~/Library/LaunchAgents/com.megatool.benchmark.plist,")
    print("then `launchctl load` it:")
    print(_launchd_plist("com.megatool.benchmark", nxt, cmd))
    print("=" * 72)


# ---------------------------------------------------------------------- replay
def load_jsonl(path: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(rec, dict) and "endpoint" in rec:
            records.append(rec)
    return records


def _replay(path: Path, json_out: Path | None) -> int:
    if not path.is_file():
        print(f"replay: no such file: {path}", file=sys.stderr)
        return 2
    records = load_jsonl(path)
    summary = bench.summarize(records)
    summary["replay_of"] = str(path)
    summary["records_read"] = len(records)
    text = json.dumps(summary, indent=2)
    print(text)
    if json_out:
        json_out.parent.mkdir(parents=True, exist_ok=True)
        json_out.write_text(text, encoding="utf-8")
        print(f"\nsummary written to {json_out}")
    return 0


# ---------------------------------------------------------------------- main
def _lock_guard(out_dir: Path) -> Path | None:
    """Refuse to start a second concurrent collector. Returns the lock path."""
    out_dir.mkdir(parents=True, exist_ok=True)
    lock = out_dir / ".benchmark.lock"
    if lock.exists():
        try:
            pid = int(lock.read_text(encoding="utf-8").strip() or "0")
        except ValueError:
            pid = 0
        if pid > 0 and _pid_alive(pid):
            raise SystemExit(
                f"another benchmark is already running (pid {pid}); refusing to "
                "start a second concurrent collector for the same source"
            )
    lock.write_text(str(os.getpid()), encoding="utf-8")
    return lock


def _pid_alive(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    p.add_argument("--source", choices=["nepse", "yonepse", "all"], default="nepse")
    p.add_argument(
        "--interval",
        type=float,
        default=DEFAULT_INTERVAL_SECONDS,
        help=f"seconds between samples (default {DEFAULT_INTERVAL_SECONDS:g}, floor {MIN_INTERVAL_SECONDS:g})",
    )
    p.add_argument(
        "--duration-minutes",
        type=float,
        default=DEFAULT_DURATION_MINUTES,
        help=f"maximum run length (default {DEFAULT_DURATION_MINUTES:g})",
    )
    p.add_argument(
        "--max-requests",
        type=int,
        default=DEFAULT_MAX_REQUESTS,
        help=f"hard cap on total samples (default {DEFAULT_MAX_REQUESTS})",
    )
    p.add_argument("--timeout", type=float, default=20.0, help="per-request timeout seconds")
    p.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    p.add_argument("--replay", type=Path, help="summarise a saved JSONL; no network")
    p.add_argument("--json-out", type=Path, help="also write the summary JSON here")
    p.add_argument(
        "--allow-off-hours",
        action="store_true",
        help="probe even outside the Sun–Thu 11:00–15:00 NPT window (smoke tests)",
    )
    p.add_argument(
        "--require-market-hours",
        action="store_true",
        default=True,
        help="only sample inside the session window (default)",
    )
    p.add_argument("--once", action="store_true", help="take a single sample then stop")
    args = p.parse_args(argv)

    if args.replay is not None:
        return _replay(args.replay, args.json_out)

    if args.interval < MIN_INTERVAL_SECONDS:
        print(
            f"--interval must be >= {MIN_INTERVAL_SECONDS:g}s (source-respect floor)",
            file=sys.stderr,
        )
        return 2

    now = _utcnow()
    nepse_authorized = os.environ.get(ol.AUTH_ENV) == "1"
    want_nepse = args.source in ("nepse", "all")
    want_yonepse = args.source in ("yonepse", "all")

    # Decide what may actually be probed. NEPSE requires the owner ruling.
    probe_nepse = want_nepse and nepse_authorized
    probe_yonepse = want_yonepse

    if want_nepse and not nepse_authorized and not want_yonepse:
        _print_schedule_only(
            f"{ol.AUTH_ENV} is not set to 1 — the NEPSE collector stays off "
            "pending the owner's authorization ruling",
            args,
            now,
        )
        return 0

    if (
        probe_nepse
        and args.require_market_hours
        and not args.allow_off_hours
        and not bench.in_market_hours(now)
    ):
        _print_schedule_only("outside the Sun–Thu 11:00–15:00 NPT session window", args, now)
        return 0

    if not probe_nepse and not probe_yonepse:
        _print_schedule_only("no probeable source requested", args, now)
        return 0

    # -- build the sample plan (sequential; never concurrent) ----------------
    run_id = now.strftime("%Y%m%dT%H%M%SZ")
    plan: list[tuple[str, str, Callable[[], Any]]] = []
    nepse_client: ol.NepseOfficialLiveClient | None = None
    if probe_nepse:
        nepse_client = ol.NepseOfficialLiveClient(timeout=args.timeout)
        if not nepse_client._authorized:  # defensive: the gate must be on
            print("internal error: NEPSE client not authorized", file=sys.stderr)
            return 2
        for endpoint, call in _nepse_calls(nepse_client).items():
            plan.append(("nepse", endpoint, call))
    if probe_yonepse:
        for endpoint, call in _yonepse_calls().items():
            plan.append(("yonepse", endpoint, call))

    lock = _lock_guard(args.out_dir)
    started = _utcnow()
    date_npt = bench.to_npt(started).date().isoformat()
    jsonl_path = args.out_dir / f"{date_npt}.jsonl"
    manifest_path = args.out_dir / f"{date_npt}.{run_id}.manifest.json"

    market_status: dict[str, Any] = {}
    if probe_nepse and nepse_client is not None:
        try:
            market_status = ol.market_status_summary(nepse_client.market_status())
        except Exception as exc:  # noqa: BLE001
            market_status = {"error": f"{type(exc).__name__}: {exc}"}

    manifest = {
        "run_id": run_id,
        "started_utc": started.isoformat(),
        "started_npt": bench.iso_npt(started),
        "config": {
            "source": args.source,
            "interval_seconds": args.interval,
            "duration_minutes": args.duration_minutes,
            "max_requests": args.max_requests,
            "timeout_seconds": args.timeout,
            "require_market_hours": args.require_market_hours and not args.allow_off_hours,
            "in_market_hours": bench.in_market_hours(started),
        },
        "env": {ol.AUTH_ENV: "1" if nepse_authorized else "unset"},
        "sources_probed": sorted({s for s, _, _ in plan}),
        "market_status": market_status,
        "endpoints": [e for _, e, _ in plan],
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    deadline = started.timestamp() + args.duration_minutes * 60.0
    records: list[dict[str, Any]] = []
    seq = 0
    try:
        print(
            f"run {run_id}: {len(plan)} endpoints, every {args.interval:g}s "
            f"for up to {args.duration_minutes:g} min (cap {args.max_requests} samples)"
        )
        while len(records) < args.max_requests and _utcnow().timestamp() < deadline:
            for source, endpoint, call in plan:
                rec = _sample(endpoint, source, call, seq, run_id)
                records.append(rec)
                with jsonl_path.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(rec, separators=(",", ":")) + "\n")
                seq += 1
                print(
                    f"  [{rec['request_start_npt']}] {endpoint:<14} "
                    f"status={rec['status']} {rec['duration_ms']}ms "
                    f"records={rec['records']}"
                )
                if len(records) >= args.max_requests or _utcnow().timestamp() >= deadline:
                    break
            if args.once or len(records) >= args.max_requests or _utcnow().timestamp() >= deadline:
                break
            time.sleep(args.interval)
    finally:
        if nepse_client is not None:
            nepse_client.close()
        with contextlib.suppress(OSError):
            lock.unlink()

    finished = _utcnow()
    summary = bench.summarize(records)
    summary["run_id"] = run_id
    summary["started_utc"] = started.isoformat()
    summary["finished_utc"] = finished.isoformat()
    summary["jsonl"] = str(jsonl_path)
    manifest["finished_utc"] = finished.isoformat()
    manifest["samples"] = len(records)
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")

    print("\n" + "=" * 72)
    print("SUMMARY")
    print("=" * 72)
    print(json.dumps(summary, indent=2))
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
