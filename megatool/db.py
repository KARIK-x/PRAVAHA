"""Application-state storage (SQLite).

Holds everything the user owns or configures: settings, watchlists, saved
screens, portfolio records, trade journal, ingestion log, alert history.
Market history lives in DuckDB instead - see ``megatool.market_store``.

SQLite is used because it is embedded, transactional, needs no server process,
and is the right tool for small, frequently-written relational records on a
memory-constrained machine.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from megatool.config import PATHS, ensure_dirs

SCHEMA_VERSION = 2

_SCHEMA = """
CREATE TABLE IF NOT EXISTS schema_meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

-- Every ingestion attempt, successful or not (Rule 6: honest data accounting).
CREATE TABLE IF NOT EXISTS ingestion_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    source          TEXT NOT NULL,
    started_at      TEXT NOT NULL,
    finished_at     TEXT,
    status          TEXT NOT NULL,          -- success | partial | failed
    symbols_requested INTEGER DEFAULT 0,
    symbols_succeeded INTEGER DEFAULT 0,
    symbols_failed  INTEGER DEFAULT 0,
    rows_read       INTEGER DEFAULT 0,
    rows_inserted   INTEGER DEFAULT 0,
    rows_updated    INTEGER DEFAULT 0,
    rows_duplicate  INTEGER DEFAULT 0,
    rows_flagged    INTEGER DEFAULT 0,
    rows_rejected   INTEGER DEFAULT 0,
    coverage_start  TEXT,
    coverage_end    TEXT,
    synthetic       INTEGER DEFAULT 0,
    detail          TEXT                    -- JSON: errors/warnings
);

-- Security master. Deliberately not a hard-coded universe (Rule: updateable).
CREATE TABLE IF NOT EXISTS securities (
    symbol          TEXT PRIMARY KEY,
    name            TEXT,
    sector          TEXT,
    instrument_type TEXT,
    delisted        INTEGER DEFAULT 0,
    source          TEXT NOT NULL,
    first_seen      TEXT,
    last_updated    TEXT
);

CREATE TABLE IF NOT EXISTS watchlists (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL UNIQUE,
    symbols    TEXT NOT NULL,               -- comma separated
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS saved_screens (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    name       TEXT NOT NULL UNIQUE,
    definition TEXT NOT NULL,               -- JSON filter tree
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS portfolio_positions (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol       TEXT NOT NULL,
    quantity     INTEGER NOT NULL,          -- positive = long
    avg_cost     REAL NOT NULL,             -- NPR per share, incl. costs
    opened_at    TEXT,
    notes        TEXT,
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS portfolio_transactions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol      TEXT NOT NULL,
    side        TEXT NOT NULL,              -- buy | sell
    quantity    INTEGER NOT NULL,
    price       REAL NOT NULL,
    fees        REAL DEFAULT 0,
    traded_at   TEXT NOT NULL,
    notes       TEXT,
    created_at  TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS journal_entries (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol        TEXT,
    strategy      TEXT,
    thesis        TEXT,
    entry_price   REAL,
    exit_price    REAL,
    quantity      INTEGER,
    fees          REAL DEFAULT 0,
    planned_target REAL,
    planned_invalidation REAL,
    confidence    TEXT,                     -- low | medium | high (user's own)
    followed_plan INTEGER,                  -- 1 yes, 0 no, NULL unknown
    opened_at     TEXT,
    closed_at     TEXT,
    outcome_notes TEXT,
    created_at    TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);

-- One row per imported floor-sheet file. `content_hash` makes a re-import of the
-- same file a no-op, so the same session cannot be double-counted.
CREATE TABLE IF NOT EXISTS floorsheet_imports (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    source        TEXT NOT NULL,              -- free-text label for where the file came from
    content_hash  TEXT NOT NULL,              -- sha256 of the raw text
    traded_at     TEXT NOT NULL,              -- the session date the sheet describes
    rows_total    INTEGER NOT NULL,
    rows_imported INTEGER NOT NULL,
    rows_skipped  INTEGER NOT NULL,
    imported_at   TEXT NOT NULL,
    UNIQUE (content_hash, traded_at)
);

-- Individual prints. The unique key is the trade itself, so two different files
-- describing the same session cannot inflate the counts.
CREATE TABLE IF NOT EXISTS floorsheet_trades (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    traded_at  TEXT NOT NULL,
    symbol     TEXT NOT NULL,
    buyer      TEXT NOT NULL,
    seller     TEXT NOT NULL,
    quantity   INTEGER NOT NULL,
    rate       REAL NOT NULL,
    amount     REAL NOT NULL,
    source     TEXT NOT NULL,
    UNIQUE (traded_at, symbol, buyer, seller, quantity, rate)
);

CREATE INDEX IF NOT EXISTS idx_floorsheet_trades_symbol
    ON floorsheet_trades (traded_at, symbol);

-- Dedupe key for alerts so a condition cannot fire every poll cycle.
CREATE TABLE IF NOT EXISTS alert_history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    alert_key   TEXT NOT NULL,              -- stable hash of condition+symbol
    symbol      TEXT,
    message     TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    UNIQUE (alert_key, symbol)
);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_tx_symbol ON portfolio_transactions (symbol);
CREATE INDEX IF NOT EXISTS idx_journal_symbol ON journal_entries (symbol);
"""


def _connect(db_path: Path | None = None) -> sqlite3.Connection:
    path = db_path or PATHS.app_db
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


@contextmanager
def get_conn(db_path: Path | None = None) -> Iterator[sqlite3.Connection]:
    conn = _connect(db_path)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_app_db(db_path: Path | None = None) -> int:
    """Create/upgrade the application database. Returns the schema version."""
    ensure_dirs()
    with get_conn(db_path) as conn:
        conn.executescript(_SCHEMA)
        row = conn.execute("SELECT value FROM schema_meta WHERE key='schema_version'").fetchone()
        current = int(row["value"]) if row else 0
        if current < SCHEMA_VERSION:
            conn.execute(
                "INSERT INTO schema_meta (key, value) VALUES ('schema_version', ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (str(SCHEMA_VERSION),),
            )
            current = SCHEMA_VERSION
    return current


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def set_setting(key: str, value: str, db_path: Path | None = None) -> None:
    with get_conn(db_path) as conn:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )


def get_setting(key: str, default: str | None = None, db_path: Path | None = None) -> str | None:
    with get_conn(db_path) as conn:
        row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def log_ingestion(record: dict[str, Any], db_path: Path | None = None) -> int:
    """Persist one ingestion run. Returns the log row id."""
    with get_conn(db_path) as conn:
        cur = conn.execute(
            """
            INSERT INTO ingestion_log
              (source, started_at, finished_at, status, symbols_requested,
               symbols_succeeded, symbols_failed, rows_read, rows_inserted,
               rows_updated, rows_duplicate, rows_flagged, rows_rejected,
               coverage_start, coverage_end, synthetic, detail)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                record.get("source"),
                record.get("started_at"),
                record.get("finished_at"),
                record.get("status", "failed"),
                record.get("symbols_requested", 0),
                record.get("symbols_succeeded", 0),
                record.get("symbols_failed", 0),
                record.get("rows_read", 0),
                record.get("rows_inserted", 0),
                record.get("rows_updated", 0),
                record.get("rows_duplicate", 0),
                record.get("rows_flagged", 0),
                record.get("rows_rejected", 0),
                record.get("coverage_start"),
                record.get("coverage_end"),
                1 if record.get("synthetic") else 0,
                record.get("detail"),
            ),
        )
        return int(cur.lastrowid)
