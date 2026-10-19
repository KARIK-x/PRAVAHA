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

import re
import threading
from collections.abc import Iterable, Sequence
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import duckdb
import pandas as pd

from megatool.config import PATHS, ensure_dirs

#: Canonical listing-status vocabulary (R5 / B-4). The store keeps the status
#: distinct from the legacy ``delisted`` flag so that ``MERGED`` and
#: ``SUSPENDED`` securities are not silently relabelled ``DELISTED``.
STATUS_ACTIVE = "ACTIVE"
STATUS_SUSPENDED = "SUSPENDED"
STATUS_MERGED = "MERGED"
STATUS_DELISTED = "DELISTED"
STATUS_UNKNOWN = "UNKNOWN"
CANONICAL_STATUSES = frozenset(
    {STATUS_ACTIVE, STATUS_SUSPENDED, STATUS_MERGED, STATUS_DELISTED, STATUS_UNKNOWN}
)

#: YONEPSE quote timestamps are Nepal local time, UTC+05:45. Kept local so the
#: store never has to import the datasource module just to age a quote.
NPT_OFFSET_MINUTES = 5 * 60 + 45

#: Input aliases found in reviewed CSVs (e.g. binayabaral uses ``listed``).
_STATUS_ALIASES = {"listed": STATUS_ACTIVE, "active": STATUS_ACTIVE}

#: NEPSE symbols are uppercase letters, digits, hyphens and slashes.
#: Equity symbols are normally letters/digits; bonds/debentures use hyphens
#: and slashes (e.g. ``NMBD87-88``, ``GBD80/81``). This rejects empty, lowercase,
#: spaces and other punctuation before it can enter the security master.
_SYMBOL_FORMAT_RE = re.compile(r"^[A-Z0-9][A-Z0-9\-/]*$")


def is_valid_nepse_symbol(symbol: str) -> tuple[bool, str | None]:
    """Return ``(ok, reason)`` for a NEPSE symbol string.

    Accepts uppercase letters, digits, hyphens and slashes. Empty, lowercase,
    spaces and other punctuation are rejected with a reason string.
    """
    s = (symbol or "").strip()
    if not s:
        return False, "symbol is empty"
    if s != s.upper():
        return False, "symbol must be uppercase"
    if not _SYMBOL_FORMAT_RE.match(s):
        return False, "symbol must be uppercase letters, digits, hyphens or slashes"
    return True, None


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
    symbol                VARCHAR PRIMARY KEY,
    name                  VARCHAR,
    sector                VARCHAR,
    sector_source         VARCHAR,
    sector_retrieved_at   TIMESTAMP,
    sector_observed_date  DATE,
    instrument_type       VARCHAR,
    status                VARCHAR DEFAULT 'UNKNOWN',
    delisted              BOOLEAN DEFAULT FALSE,
    successor_symbol      VARCHAR,
    source                VARCHAR NOT NULL,
    first_seen            TIMESTAMP,
    last_updated          TIMESTAMP
);
"""

#: The single upsert shape used by :meth:`MarketStore.upsert_securities`.
#: ``name``/``sector``/``instrument_type`` use ``COALESCE`` (incoming ``NULL``
#: preserves), while ``status``/``delisted``/``successor_symbol`` are resolved
#: to their current or default values in Python before the statement runs.
#: This keeps a partial refresh from reactivating a merged, delisted or
#: suspended security while still allowing an explicit status change.
_UPSERT_SECURITIES = """
                INSERT INTO security_master
                  (symbol, name, sector, instrument_type, status, delisted,
                   successor_symbol, source, first_seen, last_updated)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (symbol) DO UPDATE SET
                   name = COALESCE(excluded.name, security_master.name),
                   sector = COALESCE(excluded.sector, security_master.sector),
                   instrument_type = COALESCE(excluded.instrument_type,
                                              security_master.instrument_type),
                   status = excluded.status,
                   delisted = excluded.delisted,
                   successor_symbol = excluded.successor_symbol,
                   last_updated = excluded.last_updated
                """

#: A published index series (register L3 / B-10). Populated only from an
#: owner-supplied file; there is no live index feed and none is asserted.
_INDEX_DDL = """
CREATE TABLE IF NOT EXISTS index_series (
    index_name   VARCHAR NOT NULL,
    trading_date DATE NOT NULL,
    close        DOUBLE NOT NULL,
    source       VARCHAR NOT NULL,
    retrieved_at TIMESTAMP,
    PRIMARY KEY (index_name, trading_date)
);
CREATE INDEX IF NOT EXISTS idx_index_name_date ON index_series (index_name, trading_date);
"""

#: Near-live per-symbol quotes (YONEPSE ``market/live.json``). Kept separate
#: from ``price_bars`` on purpose: a quote is an evolving intraday snapshot,
#: not a settled end-of-day bar, and merging the two would let a stale or
#: delayed quote masquerade as a close. Keyed ``(symbol, quote_date, source)``
#: so one row per symbol per day per source survives — a re-run overwrites in
#: place instead of appending, and two sources never clobber each other.
_QUOTES_DDL = """
CREATE TABLE IF NOT EXISTS market_quotes (
    symbol             VARCHAR NOT NULL,
    quote_date         DATE NOT NULL,
    ltp                DOUBLE,
    previous_close     DOUBLE,
    high               DOUBLE,
    low                DOUBLE,
    change             DOUBLE,
    percent_change     DOUBLE,
    volume             BIGINT,
    turnover           DOUBLE,
    trades             BIGINT,
    market_cap         DOUBLE,
    name               VARCHAR,
    source             VARCHAR NOT NULL,
    source_updated_at  TIMESTAMP,
    retrieved_at       TIMESTAMP NOT NULL,
    validation_status  VARCHAR NOT NULL DEFAULT 'valid',
    PRIMARY KEY (symbol, quote_date, source)
);
CREATE INDEX IF NOT EXISTS idx_quotes_date ON market_quotes (quote_date);
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


def _normalize_status(value: Any) -> str:
    """Return a canonical status or raise for an unrecognised value."""
    if value is None:
        return STATUS_UNKNOWN
    v = str(value).strip().upper()
    if v in CANONICAL_STATUSES:
        return v
    low = v.lower()
    if low in _STATUS_ALIASES:
        return _STATUS_ALIASES[low]
    raise ValueError(
        f"invalid status {value!r}; expected one of "
        f"{', '.join(sorted(CANONICAL_STATUSES | set(_STATUS_ALIASES)))}"
    )


def _resolve_successor(value: Any) -> str | None:
    if value is None:
        return None
    v = str(value).strip().upper()
    return v if v else None


def _status_from_meta(meta: dict[str, Any] | None) -> str:
    """Resolve the canonical status from stored metadata.

    * If the row is missing or the status column is NULL, fall back to the
      legacy ``delisted`` flag: ``True`` → ``DELISTED``, otherwise ``UNKNOWN``.
    * A stored status always wins; the legacy flag is only a fallback so that
      pre-existing rows remain honest without a data migration.
    """
    if meta is None:
        return STATUS_UNKNOWN
    status = meta.get("status")
    if status in CANONICAL_STATUSES and status != STATUS_UNKNOWN:
        return status
    if status == STATUS_UNKNOWN or status is None:
        if meta.get("delisted") is True:
            return STATUS_DELISTED
        return STATUS_UNKNOWN
    # Defensive: any unexpected stored value is treated as unknown, not guessed.
    return STATUS_UNKNOWN


def _freshness_class(age_minutes: float | None) -> str:
    """Classify a quote's age so a consumer can distinguish fresh/delayed/stale.

    The boundaries are Mega Tool *policy*, not an exchange claim: a quote no
    older than 15 minutes is ``fresh``, up to 24 hours is ``delayed``, older is
    ``stale``, and a quote with no source timestamp is ``unknown`` (never
    silently treated as fresh). ``disconnected``/``unavailable`` are reported by
    the source-health surface, not per quote.
    """
    if age_minutes is None:
        return "unknown"
    if age_minutes <= 15:
        return "fresh"
    if age_minutes <= 24 * 60:
        return "delayed"
    return "stale"


def eligibility_from_meta(
    meta: dict[str, Any] | None,
    *,
    exclude_delisted: bool = False,
    instrument_types: Sequence[str] | None = None,
) -> tuple[bool, str]:
    """Apply the eligibility filters to one symbol's stored metadata.

    Pure function — no database access — so the scanner, the ranking universe
    and the API layers make the identical decision for identical inputs.
    Returns ``(allowed, reason)``; ``reason`` is empty when allowed unless
    the allowed status is uncertain (see below).

    R5 / B-4 policy:

    * No filter active (``exclude_delisted=False`` and no
      ``instrument_types``) → everything is allowed, including securities
      with no metadata. This preserves historical/research access.
    * When ``exclude_delisted=True`` (the scanner/rank default), verified
      non-tradable securities are excluded: ``DELISTED``, ``SUSPENDED`` and
      ``MERGED``. ``ACTIVE`` is allowed. ``UNKNOWN`` is allowed so that
      missing metadata does not silently erase valid securities from the
      active universe, but the reason string notes the uncertainty so it
      is observable.
    * ``MERGED`` is **never** silently converted to ``DELISTED``; the two
      statuses are stored and reported distinctly.
    * ``instrument_types`` matches case-insensitively against the stored
      value; an empty sequence is an active filter that matches nothing.
    * A missing instrument type only excludes when an ``instrument_types``
      filter is active — it is unrelated to listing status.
    """
    if not exclude_delisted and instrument_types is None:
        return True, ""

    status = _status_from_meta(meta)
    allowed = True
    reason = ""

    if exclude_delisted:
        if status in {STATUS_DELISTED, STATUS_SUSPENDED, STATUS_MERGED}:
            allowed = False
            reason = f"status={status}; not currently tradable"
        elif status == STATUS_UNKNOWN:
            reason = "status unknown; eligibility uncertain"

    if allowed and instrument_types is not None:
        wanted = {t.strip().lower() for t in instrument_types}
        stored = meta.get("instrument_type") if meta is not None else None
        if stored is None:
            allowed = False
            reason = "instrument type unknown; excluded by instrument_types filter"
        elif str(stored).strip().lower() not in wanted:
            allowed = False
            reason = f"instrument_type={stored!r} is not in the requested instrument_types"

    return allowed, reason


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
                self._conn.execute(_INDEX_DDL)
                self._conn.execute(_QUOTES_DDL)
                # R5 / B-4: idempotent, non-destructive schema migration. The
                # status column is required to store ACTIVE/SUSPENDED/MERGED/
                # DELISTED/UNKNOWN distinctly from the legacy delisted flag;
                # successor_symbol is required to retain evidence-based
                # successor relationships without inventing them. No data is
                # rewritten; existing rows simply acquire the column default.
                self._conn.execute(
                    "ALTER TABLE security_master ADD COLUMN IF NOT EXISTS status VARCHAR DEFAULT 'UNKNOWN'"
                )
                self._conn.execute(
                    "ALTER TABLE security_master ADD COLUMN IF NOT EXISTS successor_symbol VARCHAR"
                )
                # Sector provenance (T-11 follow-up): every sector assignment
                # must carry source, retrieval time and observed date so an
                # unverified mapping can never be mistaken for an authoritative
                # one. Idempotent ADD COLUMN keeps existing rows intact.
                self._conn.execute(
                    "ALTER TABLE security_master ADD COLUMN IF NOT EXISTS sector_source VARCHAR"
                )
                self._conn.execute(
                    "ALTER TABLE security_master ADD COLUMN IF NOT EXISTS sector_retrieved_at TIMESTAMP"
                )
                self._conn.execute(
                    "ALTER TABLE security_master ADD COLUMN IF NOT EXISTS sector_observed_date DATE"
                )
        return self._conn

    def execute(self, query: str, params: Sequence[Any] | None = None) -> Any:
        """Run one statement while holding the store lock."""
        with self._lock:
            conn = self.conn  # property: connects (and creates schema) once
            if params is None:
                return conn.execute(query)
            return conn.execute(query, params)

    # -- locked read helpers ------------------------------------------------
    # ``execute()`` releases the lock as soon as the statement runs, but DuckDB
    # stores the result on the *connection*: fetching afterwards meant another
    # thread's ``execute()`` could replace the pending result first. That showed
    # up as ``ValueError: zip() argument 2 is longer than argument 1`` in
    # ``global_coverage`` (a row from some other query), and it could equally
    # have handed one request another request's bars. These helpers hold the
    # lock across execute *and* fetch so a reader always gets its own result.
    def _cursor(self, query: str, params: Sequence[Any] | None = None) -> Any:
        conn = self.conn
        if params is None:
            return conn.execute(query)
        return conn.execute(query, params)

    def query_one(self, query: str, params: Sequence[Any] | None = None) -> tuple[Any, ...] | None:
        """Execute and fetch exactly one row, atomically."""
        with self._lock:
            row = self._cursor(query, params).fetchone()
            return tuple(row) if row is not None else None

    def query_rows(self, query: str, params: Sequence[Any] | None = None) -> list[tuple[Any, ...]]:
        """Execute and fetch all rows, atomically."""
        with self._lock:
            return [tuple(r) for r in self._cursor(query, params).fetchall()]

    def query_df(self, query: str, params: Sequence[Any] | None = None) -> pd.DataFrame:
        """Execute and materialise a DataFrame, atomically."""
        with self._lock:
            return self._cursor(query, params).df()

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
        """Insert or update security-master rows.

        Field contract on update (``ON CONFLICT``):

        * ``name`` / ``sector`` / ``instrument_type``: an incoming value
          replaces the stored one; ``None`` preserves it (``COALESCE``).
        * ``status`` / ``delisted`` / ``successor_symbol``: an omitted key or
          an explicit ``None`` preserves the stored value, so a partial
          refresh cannot reactivate a merged/delisted/suspended security or
          erase a recorded successor. When ``status`` is supplied it is the
          primary source of truth and ``delisted`` is derived from it
          (``DELISTED`` → ``True``). When only ``delisted`` is supplied, the
          status is derived (``True`` → ``DELISTED``, ``False`` → ``UNKNOWN``).
        * ``source`` and ``first_seen`` are insert-only: the first writer wins.

        Each row needs ``symbol`` and ``source`` (``source`` is ``NOT NULL``
        on insert). Supplied ``delisted`` values are coerced with ``bool()``.
        Supplied ``status`` values are normalised to the canonical vocabulary.
        """
        n = 0
        with self._lock:
            for r in rows:
                symbol = str(r["symbol"]).upper()

                # Resolve the current stored values so omitted fields are
                # preserved exactly (not reset to defaults).
                current = self.query_one(
                    "SELECT status, delisted, successor_symbol FROM security_master WHERE symbol = ?",
                    (symbol,),
                )
                cur_status, cur_delisted, cur_successor = (
                    (current[0], current[1], current[2])
                    if current is not None
                    else (STATUS_UNKNOWN, False, None)
                )
                if cur_status is None or cur_status not in CANONICAL_STATUSES:
                    cur_status = STATUS_UNKNOWN

                # Explicit ``None`` for status/delisted means "preserve",
                # exactly like an omitted key. Empty string for successor_symbol
                # means "clear"; ``None`` means preserve.
                raw_status = r.get("status")
                raw_delisted = r.get("delisted")
                raw_successor = r.get("successor_symbol")

                has_status = "status" in r and raw_status is not None
                has_delisted = "delisted" in r and raw_delisted is not None
                has_successor = "successor_symbol" in r

                status = _normalize_status(raw_status) if has_status else cur_status

                if has_delisted:
                    delisted = bool(raw_delisted)
                else:
                    delisted = bool(cur_delisted) if cur_delisted is not None else False

                # Derive the missing side when only one of status/delisted is
                # supplied, and reject an explicit contradiction.
                if has_status and not has_delisted:
                    delisted = status == STATUS_DELISTED
                elif has_delisted and not has_status:
                    status = STATUS_DELISTED if delisted else STATUS_UNKNOWN
                elif has_status and has_delisted:
                    expected_delisted = status == STATUS_DELISTED
                    if delisted != expected_delisted:
                        raise ValueError(
                            f"{symbol}: status={status!r} and delisted={delisted!r} "
                            "are contradictory"
                        )

                if has_successor:
                    successor_symbol = _resolve_successor(raw_successor)
                else:
                    successor_symbol = cur_successor

                stamp = r.get("last_updated") or datetime.now(UTC).replace(tzinfo=None)
                self.execute(
                    _UPSERT_SECURITIES,
                    (
                        symbol,
                        r.get("name"),
                        r.get("sector"),
                        r.get("instrument_type"),
                        status,
                        delisted,
                        successor_symbol,
                        r.get("source"),
                        r.get("first_seen"),
                        stamp,
                    ),
                )
                n += 1
        return n

    def set_sectors(
        self,
        sectors: dict[str, str],
        *,
        updated_at: datetime | None = None,
        provenance: dict[str, dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Assign a sector to symbols that already exist in the master.

        Only the sector-related columns are touched, so ``name``, ``delisted``
        and ``instrument_type`` are never clobbered (a full upsert preserves
        ``delisted`` too unless a value is supplied — see
        :meth:`upsert_securities`). Symbols absent from the master are reported,
        never created — the master is built from successfully ingested symbols,
        not from a classification file.

        ``provenance`` maps symbol -> {"source": str, "retrieved_at": datetime|str,
        "observed_date": date|str}. Missing provenance for a classified symbol
        leaves the existing provenance columns unchanged; this lets a caller
        refresh a sector value without erasing its source history.
        """
        stamp = updated_at or datetime.now(UTC).replace(tzinfo=None)
        provenance = provenance or {}
        updated = 0
        unknown: list[str] = []
        with self._lock:
            for raw_symbol, sector in sectors.items():
                symbol = str(raw_symbol).upper().strip()
                exists = self.execute(
                    "SELECT 1 FROM security_master WHERE symbol = ?", (symbol,)
                ).fetchone()
                if exists is None:
                    unknown.append(symbol)
                    continue
                meta = provenance.get(symbol, {})
                sector_source = meta.get("source")
                sector_retrieved_at = meta.get("retrieved_at")
                sector_observed_date = meta.get("observed_date")
                if isinstance(sector_retrieved_at, str):
                    sector_retrieved_at = datetime.fromisoformat(sector_retrieved_at)
                if (
                    isinstance(sector_retrieved_at, datetime)
                    and sector_retrieved_at.tzinfo is not None
                ):
                    sector_retrieved_at = sector_retrieved_at.astimezone(UTC).replace(tzinfo=None)
                if isinstance(sector_observed_date, str):
                    sector_observed_date = date.fromisoformat(sector_observed_date)
                self.execute(
                    """UPDATE security_master SET
                        sector = ?,
                        sector_source = COALESCE(?, sector_source),
                        sector_retrieved_at = COALESCE(?, sector_retrieved_at),
                        sector_observed_date = COALESCE(?, sector_observed_date),
                        last_updated = ?
                       WHERE symbol = ?""",
                    (
                        sector,
                        sector_source,
                        sector_retrieved_at,
                        sector_observed_date,
                        stamp,
                        symbol,
                    ),
                )
                updated += 1
        return {"updated": updated, "unknown": unknown, "total": len(sectors)}

    def upsert_index_rows(self, rows: Iterable[dict[str, Any]]) -> int:
        """Insert/update index closes. Re-importing a date overwrites it in place.

        Each row needs ``index_name``, ``trading_date`` (date/datetime/ISO str),
        ``close`` and ``source``. Rows are keyed ``(index_name, trading_date)``
        so a refreshed series replaces older points for the same day.
        """
        n = 0
        with self._lock:
            for r in rows:
                raw_date = r["trading_date"]
                if isinstance(raw_date, str):
                    raw_date = date.fromisoformat(raw_date[:10])
                elif isinstance(raw_date, datetime):
                    raw_date = raw_date.date()
                self.execute(
                    """
                    INSERT INTO index_series
                      (index_name, trading_date, close, source, retrieved_at)
                    VALUES (?, ?, ?, ?, ?)
                    ON CONFLICT (index_name, trading_date) DO UPDATE SET
                      close = excluded.close,
                      source = excluded.source,
                      retrieved_at = excluded.retrieved_at
                    """,
                    (
                        str(r["index_name"]),
                        raw_date,
                        float(r["close"]),
                        r.get("source", "unknown"),
                        r.get("retrieved_at"),
                    ),
                )
                n += 1
        return n

    # -------------------------------------------------------------- quotes
    def upsert_quotes(self, rows: Iterable[dict[str, Any]]) -> int:
        """Insert/update near-live quotes, keyed ``(symbol, quote_date, source)``.

        Re-running over the same snapshot overwrites the day's row in place —
        it never appends a duplicate and never touches ``price_bars``. Each row
        needs ``symbol``, ``quote_date``, ``source`` and ``retrieved_at``.
        """
        n = 0
        with self._lock:
            for r in rows:
                raw_date = r["quote_date"]
                if isinstance(raw_date, str):
                    raw_date = date.fromisoformat(raw_date[:10])
                elif isinstance(raw_date, datetime):
                    raw_date = raw_date.date()
                self.execute(
                    """
                    INSERT INTO market_quotes
                      (symbol, quote_date, ltp, previous_close, high, low, change,
                       percent_change, volume, turnover, trades, market_cap, name,
                       source, source_updated_at, retrieved_at, validation_status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT (symbol, quote_date, source) DO UPDATE SET
                      ltp = excluded.ltp,
                      previous_close = excluded.previous_close,
                      high = excluded.high,
                      low = excluded.low,
                      change = excluded.change,
                      percent_change = excluded.percent_change,
                      volume = excluded.volume,
                      turnover = excluded.turnover,
                      trades = excluded.trades,
                      market_cap = excluded.market_cap,
                      name = excluded.name,
                      source_updated_at = excluded.source_updated_at,
                      retrieved_at = excluded.retrieved_at,
                      validation_status = excluded.validation_status
                    """,
                    (
                        str(r["symbol"]).upper(),
                        raw_date,
                        r.get("ltp"),
                        r.get("previous_close"),
                        r.get("high"),
                        r.get("low"),
                        r.get("change"),
                        r.get("percent_change"),
                        r.get("volume"),
                        r.get("turnover"),
                        r.get("trades"),
                        r.get("market_cap"),
                        r.get("name"),
                        str(r["source"]),
                        r.get("source_updated_at"),
                        r.get("retrieved_at"),
                        r.get("validation_status", "valid"),
                    ),
                )
                n += 1
        return n

    def latest_quotes(
        self,
        *,
        source: str | None = None,
        now: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """Latest stored quote per symbol, with honest freshness.

        ``age_minutes`` is measured from the source's own ``source_updated_at``
        (converted from Nepal local time, UTC+05:45, to UTC) — never from the
        wall clock at read time.  ``is_stale`` is ``True`` when the quote is
        older than one calendar day, so a symbol that simply did not trade is
        not silently presented as current.
        """
        where = "WHERE source = ?" if source else ""
        params: tuple[Any, ...] = (source,) if source else ()
        try:
            rows = self.query_rows(
                f"""
                SELECT symbol, quote_date, ltp, previous_close, high, low, change,
                       percent_change, volume, turnover, trades, market_cap, name,
                       source, source_updated_at, retrieved_at, validation_status
                FROM (
                    SELECT *, ROW_NUMBER() OVER (
                        PARTITION BY symbol ORDER BY quote_date DESC, source_updated_at DESC
                    ) AS _rn
                    FROM market_quotes {where}
                )
                WHERE _rn = 1
                ORDER BY symbol
                """,
                params,
            )
        except Exception:
            # Table absent (a read-only DB that has not received the quotes
            # migration): report no quotes rather than raising a 500.
            return []
        now_utc = (now or datetime.now(UTC)).replace(tzinfo=None)
        out = []
        for r in rows:
            updated = r[14]
            age_minutes = None
            is_stale = None
            if updated is not None:
                utc_dt = updated - timedelta(minutes=NPT_OFFSET_MINUTES)
                age_minutes = round((now_utc - utc_dt).total_seconds() / 60.0, 1)
                is_stale = age_minutes > 24 * 60
            out.append(
                {
                    "symbol": r[0],
                    "quote_date": str(r[1]),
                    "ltp": r[2],
                    "previous_close": r[3],
                    "high": r[4],
                    "low": r[5],
                    "change": r[6],
                    "percent_change": r[7],
                    "volume": r[8],
                    "turnover": r[9],
                    "trades": r[10],
                    "market_cap": r[11],
                    "name": r[12],
                    "source": r[13],
                    "source_updated_at": updated.isoformat(timespec="seconds")
                    if updated is not None
                    else None,
                    "retrieved_at": r[15].isoformat(timespec="seconds")
                    if r[15] is not None
                    else None,
                    "validation_status": r[16],
                    "age_minutes": age_minutes,
                    "is_stale": is_stale,
                    "freshness_class": _freshness_class(age_minutes),
                }
            )
        return out

    def quote_freshness(self, *, now: datetime | None = None) -> dict[str, Any]:
        """Summarise stored quotes so freshness is observable, not assumed."""
        try:
            total = self.query_one("SELECT COUNT(*) FROM market_quotes")
            row = self.query_one(
                "SELECT COUNT(DISTINCT symbol), MIN(quote_date), MAX(quote_date), "
                "MAX(source_updated_at) FROM market_quotes"
            )
        except Exception:
            # Table absent (pre-migration read-only DB): nothing stored.
            total, row = (0,), (0, None, None, None)
        symbols, first_d, last_d, latest = row if row else (0, None, None, None)
        now_utc = (now or datetime.now(UTC)).replace(tzinfo=None)
        age_minutes = None
        if latest is not None:
            age_minutes = round(
                (now_utc - (latest - timedelta(minutes=NPT_OFFSET_MINUTES))).total_seconds() / 60.0,
                1,
            )
        return {
            "rows": int(total[0]) if total else 0,
            "distinct_symbols": int(symbols or 0),
            "first_quote_date": str(first_d) if first_d else None,
            "latest_quote_date": str(last_d) if last_d else None,
            "latest_source_updated_at": latest.isoformat(timespec="seconds")
            if latest is not None
            else None,
            "age_minutes": age_minutes,
            "is_stale": None if age_minutes is None else age_minutes > 24 * 60,
            "freshness_class": _freshness_class(age_minutes),
            "timestamp_basis": "source last_updated interpreted as Nepal time (UTC+05:45)",
        }

    def index_closes(self, index_name: str) -> Any:
        """A date-ordered ``close`` series for one index (empty frame if absent)."""
        df = self.query_df(
            """
            SELECT trading_date, close
            FROM index_series
            WHERE index_name = ?
            ORDER BY trading_date
            """,
            (index_name,),
        )
        return df

    def index_names(self) -> list[str]:
        """Which indices have a stored series."""
        rows = self.query_rows("SELECT DISTINCT index_name FROM index_series ORDER BY index_name")
        return [r[0] for r in rows]

    # ------------------------------------------------------------------- read
    def symbols(self, min_bars: int = 1) -> list[str]:
        rows = self.query_rows(
            """
            SELECT symbol FROM price_bars GROUP BY symbol
            HAVING COUNT(*) >= ? ORDER BY symbol
            """,
            (min_bars,),
        )
        return [r[0] for r in rows]

    def securities_meta(self, symbols: Iterable[str] | None = None) -> dict[str, dict[str, Any]]:
        """Read security-master metadata in a single query.

        Returns ``symbol -> {"name", "sector", "sector_source",
        "sector_retrieved_at", "sector_observed_date", "instrument_type",
        "status", "delisted", "successor_symbol"}``. Requested symbols are
        normalised to upper case; ``delisted`` is ``True``/``False``, or
        ``None`` only for a legacy row that actually stores NULL.

        ``status`` is always returned as a canonical value. If the stored
        column is NULL or ``UNKNOWN`` and the legacy ``delisted`` flag is
        ``True``, the returned status is ``DELISTED``; otherwise it is
        ``UNKNOWN``. This makes uncertainty observable without fabricating a
        more specific classification.

        A symbol absent from the result has **no** metadata row. A ``None``
        field other than ``delisted`` means **unknown**. Callers must decide
        explicitly (see :func:`eligibility_from_meta`). Pass ``symbols=None``
        for every row, or an iterable to fetch just those symbols; an empty
        iterable returns ``{}`` without touching the database.
        """
        if symbols is not None:
            wanted = list(dict.fromkeys(str(s).upper().strip() for s in symbols))
            if not wanted:
                return {}
            marks = ", ".join("?" for _ in wanted)
            rows = self.query_rows(
                "SELECT symbol, name, sector, sector_source, sector_retrieved_at, "
                "sector_observed_date, instrument_type, status, delisted, successor_symbol "
                f"FROM security_master WHERE symbol IN ({marks})",
                tuple(wanted),
            )
        else:
            rows = self.query_rows(
                "SELECT symbol, name, sector, sector_source, sector_retrieved_at, "
                "sector_observed_date, instrument_type, status, delisted, "
                "successor_symbol FROM security_master"
            )

        def _row_status(status: Any, delisted: Any) -> str:
            if status in CANONICAL_STATUSES and status != STATUS_UNKNOWN:
                return status
            if status == STATUS_UNKNOWN or status is None:
                if delisted is True:
                    return STATUS_DELISTED
                return STATUS_UNKNOWN
            return STATUS_UNKNOWN

        return {
            r[0]: {
                "name": r[1],
                "sector": r[2],
                "sector_source": r[3],
                "sector_retrieved_at": r[4],
                "sector_observed_date": r[5],
                "instrument_type": r[6],
                "status": _row_status(r[7], r[8]),
                "delisted": None if r[8] is None else bool(r[8]),
                "successor_symbol": r[9],
            }
            for r in rows
        }

    def coverage(self) -> pd.DataFrame:
        """Per-symbol coverage report: bar count, date span, latest source."""
        return self.query_df(
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
        )

    def global_coverage(self) -> dict[str, Any]:
        row = self.query_one(
            """
            SELECT COUNT(*) AS bars,
                   COUNT(DISTINCT symbol) AS symbols,
                   MIN(trading_date) AS first_date,
                   MAX(trading_date) AS last_date,
                   MAX(retrieved_at) AS last_retrieved
            FROM price_bars
            """
        )
        cols = ["bars", "symbols", "first_date", "last_date", "last_retrieved"]
        out = dict(zip(cols, row or (), strict=True))
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
        return self.query_df(sql, params)

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
            return self.query_df(
                f"""
                SELECT * EXCLUDE (rn) FROM (
                    SELECT *, ROW_NUMBER() OVER (
                        PARTITION BY symbol ORDER BY trading_date DESC) AS rn
                    FROM price_bars WHERE {where}
                ) WHERE rn = 1 ORDER BY symbol
                """,
                [s.upper() for s in symbols],
            )
        where = "1=1" if include_invalid else _NOT_INVALID
        return self.query_df(
            f"""
            SELECT * EXCLUDE (rn) FROM (
                SELECT *, ROW_NUMBER() OVER (
                    PARTITION BY symbol ORDER BY trading_date DESC) AS rn
                FROM price_bars WHERE {where}
            ) WHERE rn = 1 ORDER BY symbol
            """
        )

    def all_closes(self, include_invalid: bool = False) -> pd.DataFrame:
        """Wide close-price matrix (dates x symbols) for cross-sectional work.

        Invalid rows are excluded: an impossible close would enter every
        percentile and cross-sectional rank built from this matrix (B-17).
        """
        where = "close IS NOT NULL"
        if not include_invalid:
            where = f"{_NOT_INVALID} AND {where}"
        return self.query_df(
            f"""
            PIVOT (
                SELECT trading_date, symbol, close FROM price_bars WHERE {where}
                GROUP BY trading_date, symbol, close
            )
            ON symbol USING MAX(close)
            ORDER BY trading_date
            """
        )

    def all_volumes(self, include_invalid: bool = False) -> pd.DataFrame:
        """Wide volume matrix (dates x symbols) for market-breadth work.

        Same exclusions as :meth:`all_closes`: impossible rows are dropped, and
        rows without a volume are omitted entirely (absence stays a gap — it is
        never filled with zero, which would silently count as "no up-volume").
        """
        where = "volume IS NOT NULL"
        if not include_invalid:
            where = f"{_NOT_INVALID} AND {where}"
        return self.query_df(
            f"""
            PIVOT (
                SELECT trading_date, symbol, volume FROM price_bars WHERE {where}
                GROUP BY trading_date, symbol, volume
            )
            ON symbol USING MAX(volume)
            ORDER BY trading_date
            """
        )

    def bar_count(self) -> int:
        row = self.query_one("SELECT COUNT(*) FROM price_bars")
        return int(row[0]) if row else 0

    def purge_symbol(self, symbol: str) -> int:
        """Delete all bars for a symbol. Returns the number of rows removed."""
        sym = symbol.upper()
        # Count and delete are held together: releasing the lock between them
        # would let another writer change the count this method reports.
        with self._lock:
            row = self.query_one("SELECT COUNT(*) FROM price_bars WHERE symbol = ?", (sym,))
            n = int(row[0]) if row else 0
            self.execute("DELETE FROM price_bars WHERE symbol = ?", (sym,))
        return n


def to_iso(d: date | datetime | None) -> str | None:
    return None if d is None else d.isoformat()
