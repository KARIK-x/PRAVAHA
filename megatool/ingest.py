"""Ingestion pipeline: adapter -> normalise -> validate -> store -> log.

Responsibilities kept here (and nowhere else):
* duplicate detection (handled idempotently by the store's unique key),
* data-quality annotation,
* provenance stamping on every row,
* an immutable record of every run, successful or not.

A failure on one symbol must never abort the whole run (Section 5.5:
"a failed import does not corrupt the entire dataset").
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable, Sequence
from datetime import date
from pathlib import Path

import pandas as pd

from megatool.datasources.base import BaseAdapter, SourceError, utcnow
from megatool.datasources.local_file import LocalFileAdapter
from megatool.db import init_app_db, log_ingestion
from megatool.market_store import MarketStore
from megatool.models import DataSource, IngestResult
from megatool.quality import validate_series

ProgressFn = Callable[[str, int, int], None]


def _status_counts(report) -> dict[str, int]:
    return {"suspect": report.suspect, "invalid": report.invalid}


def ingest_symbol(
    store: MarketStore,
    adapter: BaseAdapter,
    symbol: str,
    reference_date: pd.Timestamp | None = None,
) -> dict[str, object]:
    """Fetch, validate and store one symbol. Returns a small result dict."""
    raw = adapter.fetch_history(symbol)
    if raw.empty:
        raise SourceError(f"{symbol}: source returned no rows")

    annotated, report = validate_series(raw, reference_date=reference_date)
    retrieved = utcnow().replace(tzinfo=None)
    source_url = (
        adapter.csv_url(symbol)
        if hasattr(adapter, "csv_url")
        else adapter.config.base_url
    )

    annotated = annotated.assign(
        source=adapter.config.source_id.value,
        source_url=source_url,
        retrieved_at=retrieved,
        adjustment_status="unadjusted",
    )
    # Local imports keep their filename in the URL slot for traceability.
    if isinstance(adapter, LocalFileAdapter):
        annotated["source_url"] = adapter.path.name

    counts = store.upsert_bars(annotated)
    return {
        "symbol": symbol,
        "rows": len(annotated),
        "inserted": counts["inserted"],
        "updated": counts["updated"],
        "report": report.as_dict(),
        "first_date": str(annotated["trading_date"].min().date()),
        "last_date": str(annotated["trading_date"].max().date()),
    }


def ingest(
    adapter: BaseAdapter,
    symbols: Sequence[str] | None = None,
    store: MarketStore | None = None,
    db_path: Path | None = None,
    progress: ProgressFn | None = None,
    update_securities: bool = True,
) -> IngestResult:
    """Run a full ingestion for an adapter.

    Parameters
    ----------
    symbols:
        Subset to fetch. Defaults to everything the adapter lists.
    progress:
        Optional callback ``(symbol, index, total)`` for UI feedback.
    """
    init_app_db(db_path)
    started = utcnow()
    own_store = store is None
    store = store or MarketStore()

    result = IngestResult(
        source=adapter.config.source_id,
        started_at=started,
        dataset_label=adapter.config.label,
        synthetic=adapter.config.source_id is DataSource.SYNTHETIC_TEST,
    )

    try:
        wanted = list(symbols) if symbols else adapter.list_symbols()
    except SourceError as exc:
        result.finished_at = utcnow()
        result.errors.append(str(exc))
        _persist(result, db_path)
        return result

    result.symbols_requested = len(wanted)
    if not wanted:
        result.finished_at = utcnow()
        result.errors.append("no symbols to ingest")
        _persist(result, db_path)
        return result

    all_first: list[str] = []
    all_last: list[str] = []

    for i, symbol in enumerate(wanted, start=1):
        if progress is not None:
            progress(symbol, i, len(wanted))
        try:
            r = ingest_symbol(store, adapter, symbol)
        except SourceError as exc:
            result.symbols_failed += 1
            result.errors.append(f"{symbol}: {exc}")
            continue
        except Exception as exc:  # defensive: one bad symbol must not abort
            result.symbols_failed += 1
            result.errors.append(f"{symbol}: unexpected {type(exc).__name__}: {exc}")
            continue

        result.symbols_succeeded += 1
        result.rows_read += int(r["rows"])
        result.rows_inserted += int(r["inserted"])
        result.rows_updated += int(r["updated"])
        rep = r["report"]
        result.rows_flagged += int(rep["suspect"]) + int(rep["invalid"])
        all_first.append(str(r["first_date"]))
        all_last.append(str(r["last_date"]))

    if update_securities and result.symbols_succeeded:
        rows = [
            {
                "symbol": s,
                "name": None,
                "sector": None,
                "source": adapter.config.source_id.value,
                "first_seen": started.replace(tzinfo=None),
                "last_updated": utcnow().replace(tzinfo=None),
            }
            for s in wanted
        ]
        try:
            store.upsert_securities(rows)
        except Exception as exc:  # pragma: no cover - non-fatal
            result.warnings.append(f"security master update failed: {exc}")

    if all_first:
        result.coverage_start = date.fromisoformat(min(all_first))
    if all_last:
        result.coverage_end = date.fromisoformat(max(all_last))

    result.finished_at = utcnow()
    if result.symbols_failed and result.symbols_succeeded:
        result.warnings.append("partial success: some symbols failed to ingest")
    elif result.symbols_failed and not result.symbols_succeeded:
        result.errors.append("every symbol failed")

    _persist(result, db_path)
    if own_store:
        store.close()
    return result


def _persist(result: IngestResult, db_path: Path | None) -> None:
    """Write an immutable ingestion-log row. Never raises into the caller."""
    import json

    ok = result.symbols_succeeded > 0
    failed_all = result.symbols_failed > 0 and result.symbols_succeeded == 0
    status = "failed" if failed_all else ("partial" if result.symbols_failed else "success")
    # Losing the log must not lose the data.
    with contextlib.suppress(Exception):
        log_ingestion(
            {
                "source": result.source.value,
                "started_at": result.started_at.isoformat(),
                "finished_at": result.finished_at.isoformat(),
                "status": status,
                "symbols_requested": result.symbols_requested,
                "symbols_succeeded": result.symbols_succeeded,
                "symbols_failed": result.symbols_failed,
                "rows_read": result.rows_read,
                "rows_inserted": result.rows_inserted,
                "rows_updated": result.rows_updated,
                "rows_flagged": result.rows_flagged,
                "coverage_start": result.coverage_start.isoformat() if result.coverage_start else None,
                "coverage_end": result.coverage_end.isoformat() if result.coverage_end else None,
                "synthetic": result.synthetic,
                "detail": json.dumps(
                    {"errors": result.errors[:200], "warnings": result.warnings},
                    default=str,
                ),
            },
            db_path,
        )
    _ = ok


def ingest_local_csv(
    path: Path | str,
    symbol: str | None = None,
    store: MarketStore | None = None,
    db_path: Path | None = None,
) -> IngestResult:
    """Convenience wrapper: import one local file into the store."""
    adapter = LocalFileAdapter(path, symbol=symbol)
    syms = None
    try:
        syms = adapter.list_symbols()
    except SourceError:
        syms = None
    return ingest(adapter, symbols=syms, store=store, db_path=db_path)
