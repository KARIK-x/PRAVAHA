"""Runtime deployment seeding for hosts with an ephemeral filesystem.

WHY THIS EXISTS
---------------
On Render Free there is no persistent disk, and a manually-created service may
not run a seed step at build time. The market database is therefore empty at
boot and every chart is empty. This module fills it from the SAME public sources
the CLI uses (``megatool fetch`` / ``fetch-index`` / ``fetch-sectors``), in a
background thread, so:

* the app serves immediately (the health check never waits on a download);
* charts populate as the data lands;
* nothing is fabricated — only the source's own rows are stored;
* user records are never touched — it writes only the derived market tables and
  only when the seed has not already completed.

SAFETY
------
* Runs at most once per deploy (a marker in the app DB records completion, and a
  partial run is retried because every write is an idempotent upsert).
* Enabled only for a **non-loopback bind** (a hosted deployment). Local
  development and the test client never trigger a download. Override with
  ``MEGATOOL_AUTO_SEED=1`` / ``=0``.
* Uses the application's single, lock-guarded ``MarketStore`` — DuckDB allows one
  writer, and ``ingest`` does not close a caller-owned store.
"""

from __future__ import annotations

import os
import threading
from collections.abc import Callable
from typing import Any

#: ``1`` force on, ``0`` force off, unset → on only for a non-loopback bind.
AUTO_SEED_ENV = "MEGATOOL_AUTO_SEED"

#: Optional cap on how many symbols to fetch (useful on a slow host).
SEED_LIMIT_ENV = "MEGATOOL_SEED_LIMIT"

#: App-DB marker: set once a full seed has completed for this database.
SEED_MARKER_KEY = "deploy_seed_complete_v1"

_LOOPBACK = ("127.0.0.1", "localhost", "::1")


def _is_loopback(host: str | None) -> bool:
    h = (host or "").strip().lower()
    return h in _LOOPBACK or h.startswith("127.")


def auto_seed_enabled(host: str | None = None) -> bool:
    """True when the app should seed itself at startup.

    ``MEGATOOL_AUTO_SEED=0`` disables it; ``=1`` forces it. Otherwise it is on
    only when the process is bound to a non-loopback address, so local
    development and the test client never start a long download.
    """
    flag = os.environ.get(AUTO_SEED_ENV, "").strip()
    if flag == "0":
        return False
    if flag == "1":
        return True
    return not _is_loopback(host or os.environ.get("MEGATOOL_HOST", "127.0.0.1"))


def _seed_limit() -> int | None:
    raw = os.environ.get(SEED_LIMIT_ENV, "").strip()
    if not raw:
        return None
    try:
        n = int(raw)
    except ValueError:
        return None
    return n if n > 0 else None


# --------------------------------------------------------------------- steps
def seed_price_bars(
    store: Any,
    *,
    symbols: list[str] | None = None,
    limit: int | None = None,
    progress: Callable[[str, int, int], None] | None = None,
) -> dict[str, Any]:
    """Fetch the public per-symbol daily OHLCV dataset into ``price_bars``.

    Source: ``Aabishkar2/nepse-data`` (community GitHub CSV collection), via the
    project's existing adapter. Real rows only; a failed symbol is reported, not
    silently skipped.
    """
    from megatool.datasources.nepse_data_repo import NepseDataRepoAdapter
    from megatool.ingest import ingest

    adapter = NepseDataRepoAdapter()
    wanted = list(symbols) if symbols else None
    if wanted is None and limit:
        wanted = sorted(adapter.list_symbols())[:limit]
    res = ingest(adapter, symbols=wanted, store=store, progress=progress)
    return {
        "requested": res.symbols_requested,
        "succeeded": res.symbols_succeeded,
        "failed": res.symbols_failed,
        "rows_read": res.rows_read,
        "rows_inserted": res.rows_inserted,
        "coverage_start": str(res.coverage_start) if res.coverage_start else None,
        "coverage_end": str(res.coverage_end) if res.coverage_end else None,
        "errors": list(res.errors[:5]),
    }


def seed_index(store: Any) -> dict[str, Any]:
    """Fetch the published NEPSE composite into ``index_series`` and the index
    OHLC history used by the charting view. One public CSV, no auth."""
    import csv as _csv
    import io as _io
    import tempfile
    from pathlib import Path as _Path

    from megatool.datasources import binayabaral
    from megatool.index_ohlc_ingest import IngestError, ingest_index_ohlc

    text = binayabaral.fetch_index_csv()

    rows: list[dict[str, Any]] = []
    for rec in _csv.DictReader(_io.StringIO(text)):
        day = (rec.get("published_date") or "").strip()
        close_raw = (rec.get("close") or "").strip()
        if not day or not close_raw:
            continue
        try:
            close = float(close_raw)
        except ValueError:
            continue
        if close <= 0:
            continue
        rows.append(
            {
                "index_name": "NEPSE",
                "trading_date": day,
                "close": close,
                "source": "binayabaral/nepal-market-data",
            }
        )
    if not rows:
        raise ValueError("the NEPSE index file contained no usable rows")
    written = store.upsert_index_rows(rows)

    # The charting view reads `index_ohlc_history` (app DB). Rows where
    # open == high == low == close are stored close-only, never as fake candles.
    buf = _io.StringIO()
    writer = _csv.writer(buf)
    writer.writerow(["date", "open", "high", "low", "close", "volume", "symbol"])
    for rec in _csv.DictReader(_io.StringIO(text)):
        day = (rec.get("published_date") or "").strip()
        close_raw = (rec.get("close") or "").strip()
        if not day or not close_raw:
            continue
        writer.writerow(
            [
                day,
                (rec.get("open") or "").strip(),
                (rec.get("high") or "").strip(),
                (rec.get("low") or "").strip(),
                close_raw,
                (rec.get("traded_amount") or "").strip(),
                "NEPSE_index",
            ]
        )
    tmp = _Path(tempfile.mkdtemp()) / "nepse_index_ohlc.csv"
    tmp.write_text(buf.getvalue(), encoding="utf-8")
    genuine = placeholder = 0
    try:
        res = ingest_index_ohlc(
            str(tmp), source="binayabaral/nepal-market-data", index_name="NEPSE"
        )
        genuine, placeholder = res.genuine, res.placeholder
    except IngestError:
        pass

    return {
        "rows_written": written,
        "coverage_start": rows[0]["trading_date"],
        "coverage_end": rows[-1]["trading_date"],
        "genuine_ohlc": genuine,
        "close_only": placeholder,
    }


def seed_sectors(store: Any) -> dict[str, Any]:
    """Fetch sector classifications from the public YONEPSE securities snapshot
    into ``security_master.sector``."""
    import csv as _csv
    import io as _io

    from megatool.datasources import yonepse
    from megatool.sectors import import_sectors

    records = yonepse.fetch_securities()
    rows = yonepse.securities_to_sector_rows(records)
    if not rows:
        raise ValueError("the securities snapshot contained no sector rows")

    buf = _io.StringIO()
    writer = _csv.DictWriter(
        buf, fieldnames=["symbol", "sector", "source", "retrieved_at", "observed_date"]
    )
    writer.writeheader()
    writer.writerows(rows)
    report = import_sectors(buf.getvalue(), source="yonepse/securities.json", store=store)
    return {"classified": report["classified"], "assigned": report["assigned"]}


# ------------------------------------------------------------------ orchestration
def seed_all(
    store: Any,
    *,
    log: Callable[[str], None] = print,
    limit: int | None = None,
) -> dict[str, Any]:
    """Run every seed step. Each step is independent: one failing does not stop
    the others, and every failure is reported rather than swallowed."""
    out: dict[str, Any] = {}
    for name, fn in (
        ("price_bars", lambda: seed_price_bars(store, limit=limit)),
        ("index", lambda: seed_index(store)),
        ("sectors", lambda: seed_sectors(store)),
    ):
        try:
            out[name] = fn()
            log(f"[seed] {name}: {out[name]}")
        except Exception as exc:  # noqa: BLE001 - reported, not swallowed
            out[name] = {"error": f"{type(exc).__name__}: {exc}"}
            log(f"[seed] {name} FAILED: {type(exc).__name__}: {exc}")
    return out


def seed_needed() -> bool:
    """True when a full seed has not yet completed for this database."""
    from megatool.db import get_setting

    try:
        return get_setting(SEED_MARKER_KEY, None) != "1"
    except Exception:  # noqa: BLE001 - a marker read must never break startup
        return True


def mark_seed_complete() -> None:
    from megatool.db import init_app_db, set_setting

    init_app_db()  # idempotent: guarantees the settings table exists
    set_setting(SEED_MARKER_KEY, "1")


def _run(store: Any, log: Callable[[str], None]) -> None:
    try:
        log("[seed] market database is empty — seeding from public sources")
        result = seed_all(store, log=log, limit=_seed_limit())
        # Only mark complete if the price bars actually landed.
        bars = result.get("price_bars") or {}
        if bars.get("succeeded"):
            mark_seed_complete()
            log(
                f"[seed] complete: {bars['succeeded']} symbols, "
                f"{bars.get('rows_inserted')} rows, "
                f"{bars.get('coverage_start')} -> {bars.get('coverage_end')}"
            )
        else:
            log("[seed] price-bar step did not succeed; the marker is NOT set (will retry)")
    except Exception as exc:  # noqa: BLE001 - a failed seed must not kill the app
        log(f"[seed] aborted: {type(exc).__name__}: {exc}")


def start_background_seed(
    store: Any,
    *,
    log: Callable[[str], None] = print,
    host: str | None = None,
) -> threading.Thread | None:
    """Start the seed in a daemon thread when needed. Returns the thread, or None.

    Never raises: a hosting boot must not fail because a public dataset is down.
    """
    try:
        if not auto_seed_enabled(host):
            return None
        if not seed_needed():
            return None
        t = threading.Thread(target=_run, args=(store, log), name="pravaha-seed", daemon=True)
        t.start()
        return t
    except Exception as exc:  # noqa: BLE001
        log(f"[seed] could not start: {type(exc).__name__}: {exc}")
        return None
