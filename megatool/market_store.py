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

from collections.abc import Iterable, Sequence
from datetime import date, datetime
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

from megatool.config import PATHS, ensure_dirs

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

    @property
    def conn(self) -> duckdb.DuckDBPyConnection:
        if self._conn is None:
            self._conn = duckdb.connect(str(self.path), read_only=self.read_only)
            if not self.read_only:
                self._conn.execute(_BARS_DDL)
                self._conn.execute(_SECURITIES_DDL)
        return self._conn

    def close(self) -> None:
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

        before = int(self.conn.execute("SELECT COUNT(*) FROM price_bars").fetchone()[0])

        # Register the frame under a stable name, then merge.
        self.conn.unregister("staging_bars")
        self.conn.register("staging_bars", work)

        self.conn.execute(
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
        after = int(self.conn.execute("SELECT COUNT(*) FROM price_bars").fetchone()[0])
        total = len(work)
        inserted = max(0, after - before)
        updated = total - inserted
        return {"inserted": inserted, "updated": updated, "total": total}

    def upsert_securities(self, rows: Iterable[dict[str, Any]]) -> int:
        n = 0
        for r in rows:
            self.conn.execute(
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
        rows = self.conn.execute(
            """
            SELECT symbol FROM price_bars GROUP BY symbol
            HAVING COUNT(*) >= ? ORDER BY symbol
            """,
            (min_bars,),
        ).fetchall()
        return [r[0] for r in rows]

    def coverage(self) -> pd.DataFrame:
        """Per-symbol coverage report: bar count, date span, latest source."""
        return self.conn.execute(
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
        row = self.conn.execute(
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
    ) -> pd.DataFrame:
        """Return one symbol's bars ascending by date, as a DataFrame."""
        sql = "SELECT * FROM price_bars WHERE symbol = ?"
        params: list[Any] = [symbol.upper()]
        if start is not None:
            sql += " AND trading_date >= ?"
            params.append(start)
        if end is not None:
            sql += " AND trading_date <= ?"
            params.append(end)
        sql += " ORDER BY trading_date ASC"
        if limit is not None:
            sql += f" LIMIT {int(limit)}"
        return self.conn.execute(sql, params).df()

    def latest_bars(self, symbols: Sequence[str] | None = None) -> pd.DataFrame:
        """Most recent bar per symbol - the dashboard's snapshot view."""
        if symbols:
            ph = ",".join("?" for _ in symbols)
            return self.conn.execute(
                f"""
                SELECT * EXCLUDE (rn) FROM (
                    SELECT *, ROW_NUMBER() OVER (
                        PARTITION BY symbol ORDER BY trading_date DESC) AS rn
                    FROM price_bars WHERE symbol IN ({ph})
                ) WHERE rn = 1 ORDER BY symbol
                """,
                [s.upper() for s in symbols],
            ).df()
        return self.conn.execute(
            """
            SELECT * EXCLUDE (rn) FROM (
                SELECT *, ROW_NUMBER() OVER (
                    PARTITION BY symbol ORDER BY trading_date DESC) AS rn
                FROM price_bars
            ) WHERE rn = 1 ORDER BY symbol
            """
        ).df()

    def all_closes(self) -> pd.DataFrame:
        """Wide close-price matrix (dates x symbols) for cross-sectional work."""
        return self.conn.execute(
            """
            PIVOT (
                SELECT trading_date, symbol, close FROM price_bars WHERE close IS NOT NULL
                GROUP BY trading_date, symbol, close
            )
            ON symbol USING MAX(close)
            ORDER BY trading_date
            """
        ).df()

    def bar_count(self) -> int:
        return int(self.conn.execute("SELECT COUNT(*) FROM price_bars").fetchone()[0])

    def purge_symbol(self, symbol: str) -> int:
        """Delete all bars for a symbol. Returns the number of rows removed."""
        sym = symbol.upper()
        n = int(
            self.conn.execute(
                "SELECT COUNT(*) FROM price_bars WHERE symbol = ?", (sym,)
            ).fetchone()[0]
        )
        self.conn.execute("DELETE FROM price_bars WHERE symbol = ?", (sym,))
        return n


def to_iso(d: date | datetime | None) -> str | None:
    return None if d is None else d.isoformat()
