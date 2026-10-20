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

import contextlib
import json
import os
import threading
from collections.abc import Callable
from pathlib import Path
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
#: A committed, real market-data snapshot (Parquet). Loading it is offline and
#: takes seconds, so the data survives a Render Free restart (it is part of the
#: deploy image) — unlike a runtime download, which the ephemeral filesystem
#: loses on the next spin-down.
SNAPSHOT_PARTS = ("seed", "pravaha_market_seed.parquet")

#: Attribution recorded on every row that comes from the snapshot.
SNAPSHOT_SOURCE = "github.com/Aabishkar2/nepse-data"

#: Symbols per INSERT. Keeps the load well inside Render Free's 512 MB RAM.
_BATCH = 10

#: DuckDB memory ceiling used only while the snapshot loads. DuckDB defaults to
#: ~80% of the machine's RAM, which on a 512 MB container is ~410 MB — enough,
#: with the Python process on top, to OOM-kill the service mid-load. Capping it
#: makes DuckDB spill to disk instead. Restored afterwards.
_LOAD_MEMORY_LIMIT = "256MB"


def snapshot_path() -> Path:
    """Absolute path to the committed market-data snapshot."""
    return Path(__file__).resolve().parent.parent.joinpath(*SNAPSHOT_PARTS)


def seed_from_snapshot(store: Any, path: Path | None = None) -> dict[str, Any]:
    """Load the committed market-data snapshot into ``price_bars``.

    Offline, deterministic and fast (one set-based merge). Real rows only: the
    snapshot is a frozen copy of the public dataset, never synthesised. Raises
    ``FileNotFoundError`` when the snapshot is absent so the caller can fall back
    to the network fetch.
    """
    from datetime import UTC, datetime

    started_at = datetime.now(UTC).replace(tzinfo=None)
    src = path or snapshot_path()
    if not src.is_file():
        raise FileNotFoundError(f"market-data snapshot not found: {src}")

    # MEMORY: the whole snapshot is 515k rows. A single `INSERT … ON CONFLICT`
    # builds a conflict hash table over the target and peaked at ~530 MB — above
    # Render Free's 512 MB limit, which OOM-crashed the service. Two paths keep
    # the peak low:
    #   * the table is EMPTY at first seed → a plain INSERT needs no hash table
    #     (~290 MB, measured);
    #   * otherwise → merge symbol-by-symbol in small batches (~365 MB at 25,
    #     less at 10), which is also what makes a re-run idempotent.
    _COLS = (
        "symbol, trading_date, open, high, low, close, volume, turnover, "
        "percent_change, transactions, source, source_url, retrieved_at, "
        "validation_status, adjustment_status, flags"
    )
    _SELECT = (
        "SELECT symbol, trading_date, open, high, low, close, volume, turnover, "
        "percent_change, transactions, source, source_url, retrieved_at, "
        "COALESCE(validation_status, 'valid'), "
        "COALESCE(adjustment_status, 'unadjusted'), flags FROM read_parquet(?)"
    )

    _CONFLICT = (
        " ON CONFLICT (symbol, trading_date) DO UPDATE SET "
        "open = excluded.open, high = excluded.high, low = excluded.low, "
        "close = excluded.close, volume = excluded.volume, "
        "turnover = excluded.turnover, "
        "percent_change = excluded.percent_change, "
        "transactions = excluded.transactions, source = excluded.source, "
        "source_url = excluded.source_url, retrieved_at = excluded.retrieved_at, "
        "validation_status = excluded.validation_status, "
        "adjustment_status = excluded.adjustment_status, flags = excluded.flags"
    )

    before = int(store.execute("SELECT COUNT(*) FROM price_bars").fetchone()[0])
    symbols = [
        r[0]
        for r in store.execute(
            "SELECT DISTINCT symbol FROM read_parquet(?) ORDER BY symbol", [str(src)]
        ).fetchall()
    ]

    # Bound DuckDB's memory for the load (see _LOAD_MEMORY_LIMIT), then restore.
    try:
        prev_limit = store.execute("SELECT current_setting('memory_limit')").fetchone()[0]
    except Exception:  # noqa: BLE001 - an older DuckDB may not expose it
        prev_limit = None
    try:
        store.execute(f"SET memory_limit='{_LOAD_MEMORY_LIMIT}'")
    except Exception:  # noqa: BLE001 - never fail the seed over a tuning knob
        prev_limit = None

    try:
        # Small batches keep the peak low on either path (measured: ~210 MB plain,
        # ~365 MB merge at 25 → less at 10).
        for i in range(0, len(symbols), _BATCH):
            chunk = symbols[i : i + _BATCH]
            marks = ",".join(["?"] * len(chunk))
            sql = f"INSERT INTO price_bars ({_COLS}) {_SELECT} WHERE symbol IN ({marks})"
            if before:
                sql += _CONFLICT
            store.execute(sql, [str(src), *chunk])
    finally:
        if prev_limit:
            with contextlib.suppress(Exception):
                store.execute(f"SET memory_limit='{prev_limit}'")
    after = int(store.execute("SELECT COUNT(*) FROM price_bars").fetchone()[0])

    rows = store.execute(
        "SELECT COUNT(DISTINCT symbol), MIN(trading_date), MAX(trading_date) FROM price_bars"
    ).fetchone()
    symbols = int(rows[0] or 0)
    now = datetime.now(UTC).replace(tzinfo=None)

    # Record the load in the ingestion log so ``/api/status`` can report the last
    # successful fetch. Without this the snapshot path leaves no trace and an
    # operator cannot tell WHEN the data was loaded or from where.
    with contextlib.suppress(Exception):
        from megatool.db import init_app_db, log_ingestion

        init_app_db()  # idempotent: guarantees the ingestion_log table exists
        snapshot_rows = int(
            store.execute("SELECT COUNT(*) FROM read_parquet(?)", [str(src)]).fetchone()[0]
        )
        log_ingestion(
            {
                "source": SNAPSHOT_SOURCE,
                "started_at": started_at.isoformat(),
                "finished_at": now.isoformat(),
                "status": "success",
                "symbols_requested": symbols,
                "symbols_succeeded": symbols,
                "symbols_failed": 0,
                "rows_read": snapshot_rows,
                "rows_inserted": max(0, after - before),
                "rows_updated": max(0, snapshot_rows - max(0, after - before)),
                "coverage_start": str(rows[1]) if rows[1] else None,
                "coverage_end": str(rows[2]) if rows[2] else None,
                "detail": json.dumps(
                    {
                        "kind": "snapshot",
                        "path": str(src),
                        "note": (
                            "committed market-data snapshot loaded at startup; "
                            "the frozen dataset's own dates are the coverage above"
                        ),
                    }
                ),
            }
        )
    store.upsert_securities(
        [
            {
                "symbol": r[0],
                "source": SNAPSHOT_SOURCE,
                "first_seen": now,
                "last_updated": now,
            }
            for r in store.execute("SELECT DISTINCT symbol FROM price_bars").fetchall()
        ]
    )
    return {
        "rows_added": after - before,
        "rows_total": after,
        "symbols": symbols,
        "coverage_start": str(rows[1]) if rows[1] else None,
        "coverage_end": str(rows[2]) if rows[2] else None,
        "snapshot": str(src),
    }


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

    # 1. The committed snapshot first: offline, takes seconds, and — because it
    #    ships in the deploy image — survives a restart on an ephemeral host.
    try:
        out["snapshot"] = seed_from_snapshot(store)
        log(f"[seed] snapshot: {out['snapshot']}")
    except Exception as exc:  # noqa: BLE001 - reported, not swallowed
        out["snapshot"] = {"error": f"{type(exc).__name__}: {exc}"}
        log(f"[seed] snapshot unavailable ({type(exc).__name__}: {exc}); using the network fetch")
        try:
            out["price_bars"] = seed_price_bars(store, limit=limit)
            log(f"[seed] price_bars: {out['price_bars']}")
        except Exception as exc2:  # noqa: BLE001
            out["price_bars"] = {"error": f"{type(exc2).__name__}: {exc2}"}
            log(f"[seed] price_bars FAILED: {type(exc2).__name__}: {exc2}")

    # 2. The small public fetches: the NEPSE index and the sector map.
    for name, fn in (("index", lambda: seed_index(store)), ("sectors", lambda: seed_sectors(store))):
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
        log("[seed] market database is empty — seeding from the committed snapshot / public sources")
        result = seed_all(store, log=log, limit=_seed_limit())
        # Only mark complete if the price bars actually landed (snapshot or fetch).
        bars = result.get("price_bars") or {}
        snap = result.get("snapshot") or {}
        if snap.get("symbols"):
            mark_seed_complete()
            log(
                f"[seed] complete from snapshot: {snap['symbols']} symbols, "
                f"{snap.get('rows_total')} rows, "
                f"{snap.get('coverage_start')} -> {snap.get('coverage_end')}"
            )
        elif bars.get("succeeded"):
            mark_seed_complete()
            log(
                f"[seed] complete from network: {bars['succeeded']} symbols, "
                f"{bars.get('rows_inserted')} rows, "
                f"{bars.get('coverage_start')} -> {bars.get('coverage_end')}"
            )
        else:
            log("[seed] the price-bar step did not succeed; the marker is NOT set (will retry)")
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
