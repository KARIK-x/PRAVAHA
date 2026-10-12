"""Analytical market-history storage (DuckDB).

Why DuckDB for prices and SQLite for app state:
* Price history is read-heavy, columnar, and scanned in date ranges - exactly
  what a columnar OLAP store is good at.
* It is embedded and in-process: no server to run on an 8 GB machine.
* A few million daily bars compress into a few tens of MB.

Guarantees:
* ``(symbol, trading_date)`` is unique; re-ingesting the same bar updates it in
  place rather than creating a duplicate (tested).
* Every row keeps its ``source`` and ``retrieved_at`` provenance.
"""

from __future__ import annotations

import threading
from collections.abc import Iterable, Sequence
from datetime import date, datetime
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

from megatool.config import PATHS, ensure_dirs

#: Predicate matching rows that are safe to use in arithmetic.
#:
#: ``invalid`` is the ``hard`` severity from :mod:`megatool.quality` — rows
#: that are physically impossible (``high < low``, negative or zero price,
#: missing OHLC). Every read path that feeds indicator, screening, ranking,
#: backtest or forecast arithmetic applies this.
#:
#: ``COALESCE`` rather than a bare ``<> 'invalid'``: in SQL ``NULL <> 'invalid'``
#: is ``NULL``, which is not true, so a stray ``NULL`` status would silently
#: drop *every* bar for a symbol and look like "this symbol has no data". The
#: schema says ``NOT NULL DEFAULT 'valid'``, but the cost of being defensive
#: here is nothing and the cost of being wrong is a whole universe vanishing.
#: The same COALESCE is already used on the insert path.
_NOT_INVALID = "COALESCE(validation_status, 'valid') <> 'invalid'"

_BARS_DDL = """
CREATE SEQUENCE IF NOT EXISTS seq_price_bars START 1;
CREATE TABLE IF NOT EXISTS price_bars (
    id                 BIGINT DEFAULT nextval('seq_price_bars'),
    symbol             VARCHAR NOT NULL,
    trading_date       DATE NOT NULL,
    open               DOUBLE,
    high               DOUBLE,
    low                DOUBLE,
    close              DOUBLE,
    volume             BIGINT,
    turnover           DOUBLE,
    percent_change     DOUBLE,
    transactions       BIGINT,
    source             VARCHAR NOT NULL,
    source_url         VARCHAR,
    retrieved_at       TIMESTAMP NOT NULL,
    validation_status  VARCHAR NOT NULL DEFAULT 'valid',
    adjustment_status  VARCHAR NOT NULL DEFAULT 'unadjusted',
    flags              VARCHAR,
    PRIMARY KEY (symbol, trading_date)
);
CREATE INDEX IF NOT EXISTS idx_bars_date ON price_bars (trading_date);
"""

_SECURITIES_DDL = """
CREATE TABLE IF NOT EXISTS security_master (
    symbol          VARCHAR PRIMARY KEY,
    name            VARCHAR,
    sector          VARCHAR,
    instrument_type VARCHAR,
    delisted        BOOLEAN DEFAULT FALSE,
    source          VARCHAR NOT NULL,
    first_seen      TIMESTAMP,
    last_updated    TIMESTAMP
);
"""

#: Exact column order used when staging a frame for upsert. Keeping this
#: explicit (rather than relying on ``df.columns`` order) means an importer can
#: pass columns in any order.
_BARS_COLUMNS: tuple[str, ...] = (
    "symbol",
    "trading_date",
    "open",
    "high",
    "low",
    "close",
    "volume",
    "turnover",
    "percent_change",
    "transactions",
    "source",
    "source_url",
    "retrieved_at",
    "validation_status",
    "adjustment_status",
    "flags",
)


class MarketStore:
    """Thin, explicit wrapper over the DuckDB price database."""

    def __init__(self, db_path: Path | None = None, read_only: bool = False):
        ensure_dirs()
        self.path = db_path or PATHS.market_db
        self.read_only = read_only
        self._conn: duckdb.DuckDBPyConnection | None = None
        # DuckDB's Python connection is not safe to share across threads: the
        # API serves requests from a threadpool, and a read overlapping another
        # read/write can return a truncated row (observed as a short tuple from
        # ``global_coverage``). Every statement therefore goes through this
        # re-entrant lock, and multi-statement sequences hold it throughout.
        self._lock = threading.RLock()

    @property
    def conn(self) -> duckdb.DuckDBPyConnection:
        if self._conn is None:
            self._conn = duckdb.connect(str(self.path), read_only=self.read_only)
            if not self.read_only:
                self._conn.execute(_BARS_DDL)
                self._conn.execute(_SECURITIES_DDL)
        return self._conn

    def execute(self, query: str, params: Sequence[Any] | None = None) -> Any:
        """Run one statement while holding the store lock."""
        with self._lock:
            conn = self.conn  # property: connects (and creates schema) once
            if params is None:
                return conn.execute(query)
            return conn.execute(query, params)

    def close(self) -> None:
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None

    def __enter__(self) -> MarketStore:
        # Force the connection (and schema creation) before the caller uses it.
        _ = self.conn
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # ------------------------------------------------------------------ write
    def upsert_bars(self, df: pd.DataFrame) -> dict[str, int]:
        """Insert or update bars. Idempotent on ``(symbol, trading_date)``.

        ``df`` must carry the canonical columns. Rows failing a NOT NULL
        constraint (missing symbol/date) are rejected by the caller, not here.

        Returns counts: inserted / updated / total.
        """
        if df.empty:
            return {"inserted": 0, "updated": 0, "total": 0}

        required = {"symbol", "trading_date", "source", "retrieved_at"}
        missing = required - set(df.columns)
        if missing:
            raise ValueError(f"upsert_bars: missing required columns {sorted(missing)}")

        work = df.copy()
        work["symbol"] = work["symbol"].astype(str).str.upper().str.strip()
        work["trading_date"] = pd.to_datetime(work["trading_date"]).dt.date
        work["retrieved_at"] = pd.to_datetime(work["retrieved_at"]).dt.tz_localize(None)

        # Tolerate sources that omit optional fields: fill defaults so the
        # staging frame always matches the table layout exactly.
        _OPTIONAL_DEFAULTS: dict[str, object] = {
            "open": None,
            "high": None,
            "low": None,
            "close": None,
            "volume": None,
            "turnover": None,
            "percent_change": None,
            "transactions": None,
            "source_url": None,
            "validation_status": "valid",
            "adjustment_status": "unadjusted",
            "flags": None,
        }
        for col, default in _OPTIONAL_DEFAULTS.items():
            if col not in work.columns:
                work[col] = default
        work = work[list(_BARS_COLUMNS)]

        with self._lock:
            before = int(self.execute("SELECT COUNT(*) FROM price_bars").fetchone()[0])

            # Register the frame under a stable name, then merge. The name is
            # shared, so this whole sequence must hold the lock.
            self.conn.unregister("staging_bars")
            self.conn.register("staging_bars", work)

            self.execute(
                """
                INSERT INTO price_bars
                  (symbol, trading_date, open, high, low, close, volume, turnover,
                   percent_change, transactions, source, source_url, retrieved_at,
                   validation_status, adjustment_status, flags)
                SELECT symbol, trading_date, open, high, low, close, volume, turnover,
                       percent_change, transactions, source, source_url, retrieved_at,
                       COALESCE(validation_status,'valid'),
                       COALESCE(adjustment_status,'unadjusted'),
                       flags
                FROM staging_bars
                ON CONFLICT (symbol, trading_date) DO UPDATE SET
                   open = excluded.open,
                   high = excluded.high,
                   low = excluded.low,
                   close = excluded.close,
                   volume = excluded.volume,
                   turnover = excluded.turnover,
                   percent_change = excluded.percent_change,
                   transactions = excluded.transactions,
                   source = excluded.source,
                   source_url = excluded.source_url,
                   retrieved_at = excluded.retrieved_at,
                   validation_status = excluded.validation_status,
                   adjustment_status = excluded.adjustment_status,
                   flags = excluded.flags
                """
            )
            after = int(self.execute("SELECT COUNT(*) FROM price_bars").fetchone()[0])
        total = len(work)
        inserted = max(0, after - before)
        updated = total - inserted
        return {"inserted": inserted, "updated": updated, "total": total}

    def upsert_securities(self, rows: Iterable[dict[str, Any]]) -> int:
        n = 0
        with self._lock:
            for r in rows:
                self.execute(
                    """
                INSERT INTO security_master
                  (symbol, name, sector, instrument_type, delisted, source,
                   first_seen, last_updated)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (symbol) DO UPDATE SET
                   name = COALESCE(excluded.name, security_master.name),
                   sector = COALESCE(excluded.sector, security_master.sector),
                   instrument_type = COALESCE(excluded.instrument_type,
                                              security_master.instrument_type),
                   delisted = excluded.delisted,
                   last_updated = excluded.last_updated
                """,
                    (
                        str(r["symbol"]).upper(),
                        r.get("name"),
                        r.get("sector"),
                        r.get("instrument_type"),
                        bool(r.get("delisted", False)),
                        r.get("source"),
                        r.get("first_seen"),
                        r.get("last_updated"),
                    ),
                )
                n += 1
        return n

    # ------------------------------------------------------------------- read
    def symbols(self, min_bars: int = 1) -> list[str]:
        rows = self.execute(
            """
            SELECT symbol FROM price_bars GROUP BY symbol
            HAVING COUNT(*) >= ? ORDER BY symbol
            """,
            (min_bars,),
        ).fetchall()
        return [r[0] for r in rows]

    def coverage(self) -> pd.DataFrame:
        """Per-symbol coverage report: bar count, date span, latest source."""
        return self.execute(
            """
            SELECT symbol,
                   COUNT(*)                          AS bars,
                   MIN(trading_date)                 AS first_date,
                   MAX(trading_date)                 AS last_date,
                   COUNT(DISTINCT source)            AS distinct_sources,
                   MAX(retrieved_at)                 AS last_retrieved,
                   SUM(CASE WHEN validation_status='suspect' THEN 1 ELSE 0 END) AS suspect_rows,
                   SUM(CASE WHEN validation_status='invalid' THEN 1 ELSE 0 END) AS invalid_rows
            FROM price_bars
            GROUP BY symbol
            ORDER BY symbol
            """
        ).df()

    def global_coverage(self) -> dict[str, Any]:
        row = self.execute(
            """
            SELECT COUNT(*) AS bars,
                   COUNT(DISTINCT symbol) AS symbols,
                   MIN(trading_date) AS first_date,
                   MAX(trading_date) AS last_date,
                   MAX(retrieved_at) AS last_retrieved
            FROM price_bars
            """
        ).fetchone()
        cols = ["bars", "symbols", "first_date", "last_date", "last_retrieved"]
        out = dict(zip(cols, row, strict=True))
        for k in ("first_date", "last_date"):
            if out.get(k) is not None:
                out[k] = str(out[k])
        if out.get("last_retrieved") is not None:
            out["last_retrieved"] = str(out["last_retrieved"])
        return out

    def get_bars(
        self,
        symbol: str,
        start: date | None = None,
        end: date | None = None,
        limit: int | None = None,
        include_invalid: bool = False,
    ) -> pd.DataFrame:
        """Return one symbol's bars ascending by date, as a DataFrame.

        ``limit`` keeps the **most recent** N bars (the charting-terminal
        meaning of "last 6 months"), not the oldest N. The ordering is applied
        inside a subquery so the returned frame is still chronological.
        ``limit`` is applied *after* the invalid-row filter, so a caller asking
        for "the last 200 bars" gets 200 usable ones rather than 200 rows of
        which some are unusable.

        **Invalid rows are excluded by default** (B-17). ``invalid`` is the
        ``hard`` severity in :mod:`megatool.quality` — physically impossible
        rows such as ``high < low``, a negative or zero price, or missing OHLC.
        Feeding those into ATR, range, return or drawdown arithmetic produces
        numbers that are not merely noisy but meaningless. ``suspect`` rows
        stay: they are uncertain, not impossible, and dropping ~2.5% of the
        series because a volume spike looked odd would silently smooth away
        the very history being researched.

        Pass ``include_invalid=True`` to inspect flagged rows — the API's raw
        bars endpoint exposes that switch, because a row still carries its
        ``validation_status`` and ``flags`` and should remain diagnosable.
        """
        inner = "SELECT * FROM price_bars WHERE symbol = ?"
        params: list[Any] = [symbol.upper()]
        if not include_invalid:
            inner += f" AND {_NOT_INVALID}"
        if start is not None:
            inner += " AND trading_date >= ?"
            params.append(start)
        if end is not None:
            inner += " AND trading_date <= ?"
            params.append(end)
        if limit is not None:
            inner += f" ORDER BY trading_date DESC LIMIT {int(limit)}"
            sql = f"SELECT * FROM ({inner}) ORDER BY trading_date ASC"
        else:
            sql = f"{inner} ORDER BY trading_date ASC"
        return self.execute(sql, params).df()

    def latest_bars(
        self, symbols: Sequence[str] | None = None, include_invalid: bool = False
    ) -> pd.DataFrame:
        """Most recent bar per symbol - the dashboard's snapshot view.

        With the filter on, this is the most recent **valid** bar, which means
        a symbol whose newest bar is impossible reports the previous usable one
        rather than a fabricated price. Measured on the real store: no symbol's
        newest bar is currently `invalid`, so no snapshot is stale as a result
        today. `/api/quality` reports `stale_days` for any future case where
        this fallback would start to matter (B-17).
        """
        if symbols:
            ph = ",".join("?" for _ in symbols)
            where = f"symbol IN ({ph})"
            if not include_invalid:
                where += f" AND {_NOT_INVALID}"
            return self.execute(
                f"""
                SELECT * EXCLUDE (rn) FROM (
                    SELECT *, ROW_NUMBER() OVER (
                        PARTITION BY symbol ORDER BY trading_date DESC) AS rn
                    FROM price_bars WHERE {where}
                ) WHERE rn = 1 ORDER BY symbol
                """,
                [s.upper() for s in symbols],
            ).df()
        where = "1=1" if include_invalid else _NOT_INVALID
        return self.execute(
            f"""
            SELECT * EXCLUDE (rn) FROM (
                SELECT *, ROW_NUMBER() OVER (
                    PARTITION BY symbol ORDER BY trading_date DESC) AS rn
                FROM price_bars WHERE {where}
            ) WHERE rn = 1 ORDER BY symbol
            """
        ).df()

    def all_closes(self, include_invalid: bool = False) -> pd.DataFrame:
        """Wide close-price matrix (dates x symbols) for cross-sectional work.

        Invalid rows are excluded: an impossible close would enter every
        percentile and cross-sectional rank built from this matrix (B-17).
        """
        where = "close IS NOT NULL"
        if not include_invalid:
            where = f"{_NOT_INVALID} AND {where}"
        return self.execute(
            f"""
            PIVOT (
                SELECT trading_date, symbol, close FROM price_bars WHERE {where}
                GROUP BY trading_date, symbol, close
            )
            ON symbol USING MAX(close)
            ORDER BY trading_date
            """
        ).df()

    def bar_count(self) -> int:
        return int(self.execute("SELECT COUNT(*) FROM price_bars").fetchone()[0])

    def purge_symbol(self, symbol: str) -> int:
        """Delete all bars for a symbol. Returns the number of rows removed."""
        sym = symbol.upper()
        n = int(
            self.execute("SELECT COUNT(*) FROM price_bars WHERE symbol = ?", (sym,)).fetchone()[0]
        )
        self.execute("DELETE FROM price_bars WHERE symbol = ?", (sym,))
        return n


def to_iso(d: date | datetime | None) -> str | None:
    return None if d is None else d.isoformat()
