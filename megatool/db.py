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

SCHEMA_VERSION = 11

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
-- ``created_at`` is the LAST firing time; ``fire_count`` counts firings.
CREATE TABLE IF NOT EXISTS alert_history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    alert_key   TEXT NOT NULL,              -- stable hash of condition+symbol
    symbol      TEXT,
    message     TEXT NOT NULL,
    created_at  TEXT NOT NULL,
    severity    TEXT NOT NULL DEFAULT 'warning',   -- info | warning | critical
    fire_count  INTEGER NOT NULL DEFAULT 1,
    acknowledged_at TEXT,
    UNIQUE (alert_key, symbol)
);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_tx_symbol ON portfolio_transactions (symbol);
CREATE INDEX IF NOT EXISTS idx_journal_symbol ON journal_entries (symbol);

-- ---------------------------------------------------------------------------
-- Written Data.pdf extraction (schema v3)
--
-- Every record extracted from the handwritten journal carries its source page,
-- extraction confidence, and review status. Nothing is treated as verified
-- until a human has reviewed it. The original PDF is never modified and is
-- git-ignored as private.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS pdf_imports (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    source_file  TEXT NOT NULL,               -- e.g. "WRITTENdata.pdf"
    content_hash TEXT NOT NULL,               -- sha256 of the PDF file
    page_count   INTEGER NOT NULL,
    imported_at  TEXT NOT NULL,
    UNIQUE (source_file, content_hash)
);

-- One row per extracted record. The unique key is the record's identity in the
-- source (page + source_ref + field), so re-importing the same extraction
-- cannot create duplicates.
CREATE TABLE IF NOT EXISTS pdf_records (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    import_id     INTEGER NOT NULL REFERENCES pdf_imports(id),
    record_type   TEXT NOT NULL,              -- fundamental | price | trade | settlement | ...
    page          INTEGER NOT NULL,           -- 1-indexed page in the PDF
    source_ref    TEXT NOT NULL DEFAULT '',  -- table name, row/column if identifiable
    raw_text      TEXT NOT NULL DEFAULT '',  -- original transcription
    value         TEXT,                       -- JSON-encoded extracted value
    field_name    TEXT NOT NULL DEFAULT '',  -- eps | net_worth | price | quantity | ...
    symbol        TEXT,                       -- NEPSE symbol if applicable
    record_date   TEXT,                       -- ISO date if applicable
    unit          TEXT,                       -- NPR | shares | crore | lakh | ratio | ...
    confidence    TEXT NOT NULL DEFAULT 'uncertain',  -- high | medium | low | uncertain
    review_status TEXT NOT NULL DEFAULT 'unreviewed', -- unreviewed | reviewed | corrected | rejected
    note          TEXT NOT NULL DEFAULT '',
    -- --- provenance (schema v5) -------------------------------------------------
    extraction_method   TEXT NOT NULL DEFAULT '',   -- apple_vision_ocr | manual_visual | ...
    verification_status TEXT NOT NULL DEFAULT 'ocr_only',
                                                    -- ocr_only | transcribed_unverified |
                                                    -- needs_review | verified |
                                                    -- corrected_verified | unresolvable
    original_reading    TEXT NOT NULL DEFAULT '',   -- machine reading BEFORE any correction
    corrected_value     TEXT,                       -- JSON-encoded, only set when corrected
    correction_history  TEXT NOT NULL DEFAULT '[]', -- append-only JSON list
    reconciliation      TEXT NOT NULL DEFAULT 'not_applicable',
                                                    -- reconciled | discrepancy | unreconcilable | not_applicable
    page_sha256         TEXT NOT NULL DEFAULT '',   -- hash of the rendered source page
    verification_note   TEXT NOT NULL DEFAULT '',
    UNIQUE (import_id, page, source_ref, field_name, symbol)
);

CREATE INDEX IF NOT EXISTS idx_pdf_records_symbol ON pdf_records (symbol);
CREATE INDEX IF NOT EXISTS idx_pdf_records_page ON pdf_records (page);
CREATE INDEX IF NOT EXISTS idx_pdf_records_review ON pdf_records (review_status);

-- Fundamentals, each with its reporting period, unit and source.
-- period_end stores '' when the vintage is unknown (SQLite treats NULLs as
-- distinct in UNIQUE constraints, which would let unknown-period rows
-- duplicate on re-import). Python maps '' back to None.
CREATE TABLE IF NOT EXISTS fundamentals (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol        TEXT NOT NULL,
    field         TEXT NOT NULL,
    value         REAL NOT NULL,
    unit          TEXT NOT NULL,
    period_end    TEXT NOT NULL DEFAULT '',  -- ISO date, or '' = unknown vintage
    period_label  TEXT NOT NULL DEFAULT '',  -- as reported, e.g. 'FY2081/82 Q3'
    source        TEXT NOT NULL,             -- provenance, required
    source_ref    TEXT NOT NULL DEFAULT '',  -- file / URL / page
    retrieved_at  TEXT NOT NULL,
    verification  TEXT NOT NULL DEFAULT 'extracted', -- extracted | reviewed | verified
    notes         TEXT NOT NULL DEFAULT '',
    UNIQUE (symbol, field, period_end, source)
);

CREATE INDEX IF NOT EXISTS idx_fundamentals_symbol ON fundamentals (symbol);
CREATE INDEX IF NOT EXISTS idx_fundamentals_field ON fundamentals (field);

-- News / Events (spec Section 22). OWNER-IMPORTED records only: no live
-- source is connected (register item 7 / L4), so these tables store exactly
-- what the owner imports and nothing is fetched, scraped or fabricated.
CREATE TABLE IF NOT EXISTS news_items (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    uid          TEXT NOT NULL UNIQUE,  -- dedup key: url, else title+published hash
    published_at TEXT NOT NULL,         -- ISO date or datetime as normalised on import
    title        TEXT NOT NULL,
    summary      TEXT NOT NULL DEFAULT '',
    url          TEXT NOT NULL DEFAULT '',
    publisher    TEXT NOT NULL DEFAULT '',
    source_file  TEXT NOT NULL DEFAULT '',  -- provenance: the file it came from
    imported_at  TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_news_published ON news_items (published_at);

CREATE TABLE IF NOT EXISTS news_item_symbols (
    news_id INTEGER NOT NULL REFERENCES news_items (id) ON DELETE CASCADE,
    symbol  TEXT NOT NULL,
    UNIQUE (news_id, symbol)
);

CREATE INDEX IF NOT EXISTS idx_news_symbols ON news_item_symbols (symbol);

-- ---------------------------------------------------------------------------
-- NEPSE market-data collector (schema v7)
--
-- Each run of ``megatool collector snapshot`` reads the published YONEPSE
-- market files, validates every row, and stores what the source actually
-- stated - never a derived or fabricated value - with per-dataset provenance,
-- the source's own observation timestamps, and a freshness label computed by
-- age against the source's publish cadence. Records whose source timestamp is
-- absent are stored with freshness ``unknown``; nothing is ever back-dated.
-- ---------------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS collector_runs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at      TEXT NOT NULL UNIQUE,   -- run start, UTC ISO
    finished_at     TEXT,                   -- run end (NULL while in-flight)
    status          TEXT NOT NULL,          -- success | partial | failed
    origin          TEXT NOT NULL DEFAULT '',   -- URL that actually answered
    source_sha      TEXT NOT NULL DEFAULT '',   -- data commit ref when known
    datasets_ok     INTEGER NOT NULL DEFAULT 0,
    datasets_degraded INTEGER NOT NULL DEFAULT 0,
    datasets_failed INTEGER NOT NULL DEFAULT 0,
    rows_read       INTEGER NOT NULL DEFAULT 0,
    rows_inserted   INTEGER NOT NULL DEFAULT 0,
    rows_duplicate  INTEGER NOT NULL DEFAULT 0,
    rows_flagged    INTEGER NOT NULL DEFAULT 0,
    rows_rejected   INTEGER NOT NULL DEFAULT 0,
    is_open         INTEGER,                -- 1 open, 0 closed, NULL unknown
    is_open_source  TEXT NOT NULL DEFAULT '',
    observed_at     TEXT,                   -- newest stamp the source states
    observed_age_seconds REAL,              -- age of that stamp at retrieval
    freshness       TEXT NOT NULL DEFAULT 'unknown',
    business_date   TEXT,                   -- session day the snapshot describes
    business_date_evidence TEXT NOT NULL DEFAULT '',
    detail          TEXT                    -- JSON: per-dataset report
);

CREATE INDEX IF NOT EXISTS idx_collector_runs_started ON collector_runs (started_at);

-- One row per dataset in the run: ``market_live``, ``index``, ``summary``,
-- ``status``, ``sector_indices``, ``history`` and the five ``top_*`` boards.
CREATE TABLE IF NOT EXISTS collector_datasets (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id          INTEGER NOT NULL REFERENCES collector_runs (id),
    dataset         TEXT NOT NULL,
    source_path     TEXT NOT NULL,
    origin          TEXT NOT NULL DEFAULT '',
    status          TEXT NOT NULL,          -- ok | degraded | source_unavailable
    error           TEXT NOT NULL DEFAULT '',
    observed_at     TEXT,                   -- newest stamp in this dataset
    observed_age_seconds REAL,
    freshness       TEXT NOT NULL DEFAULT 'unknown',
    rows_read       INTEGER NOT NULL DEFAULT 0,
    rows_valid      INTEGER NOT NULL DEFAULT 0,
    rows_flagged    INTEGER NOT NULL DEFAULT 0,
    rows_rejected   INTEGER NOT NULL DEFAULT 0,
    rows_duplicate  INTEGER NOT NULL DEFAULT 0,
    notes           TEXT NOT NULL DEFAULT ''
);

CREATE INDEX IF NOT EXISTS idx_collector_datasets_run ON collector_datasets (run_id);

-- All-stock board rows (typed projection of ``collector_rows.style`` payload).
CREATE TABLE IF NOT EXISTS collector_quotes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id          INTEGER NOT NULL REFERENCES collector_runs (id),
    symbol          TEXT NOT NULL,
    name            TEXT NOT NULL DEFAULT '',
    ltp             REAL,
    previous_close  REAL,
    change          REAL,
    percent_change  REAL,
    high            REAL,
    low             REAL,
    volume          REAL,
    turnover        REAL,
    trades          REAL,
    observed_at     TEXT,
    validation      TEXT NOT NULL DEFAULT 'valid',
    flags           TEXT NOT NULL DEFAULT '',
    UNIQUE (run_id, symbol)
);

CREATE INDEX IF NOT EXISTS idx_collector_quotes_symbol ON collector_quotes (symbol, run_id);

-- Index board rows: NEPSE, Sensitive, Float, Sensitive Float.
CREATE TABLE IF NOT EXISTS collector_index (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id          INTEGER NOT NULL REFERENCES collector_runs (id),
    index_name      TEXT NOT NULL,
    close           REAL,
    high            REAL,
    low             REAL,
    previous_close  REAL,
    change          REAL,
    percent_change  REAL,
    fifty_two_week_high REAL,
    fifty_two_week_low  REAL,
    generated_time  TEXT,
    UNIQUE (run_id, index_name)
);

-- Session totals board, normalised metric keys (source label kept verbatim).
CREATE TABLE IF NOT EXISTS collector_summary (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id          INTEGER NOT NULL REFERENCES collector_runs (id),
    metric          TEXT NOT NULL,
    value           REAL NOT NULL,
    source_label    TEXT NOT NULL DEFAULT '',
    UNIQUE (run_id, metric)
);

-- Top-mover boards. ``rank`` is the source's ordering (1 = best mover).
CREATE TABLE IF NOT EXISTS collector_rankings (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id          INTEGER NOT NULL REFERENCES collector_runs (id),
    dataset         TEXT NOT NULL,
    rank            INTEGER NOT NULL,
    symbol          TEXT NOT NULL,
    name            TEXT NOT NULL DEFAULT '',
    ltp             REAL,
    change          REAL,
    percent_change  REAL,
    closing_price   REAL,
    volume          REAL,
    turnover        REAL,
    trades          REAL,
    validation      TEXT NOT NULL DEFAULT 'valid',
    flags           TEXT NOT NULL DEFAULT '',
    UNIQUE (run_id, dataset, rank)
);

CREATE INDEX IF NOT EXISTS idx_collector_rankings_symbol ON collector_rankings (dataset, symbol);

-- Exchange open/closed state exactly as the source published it.
CREATE TABLE IF NOT EXISTS collector_status (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id          INTEGER NOT NULL REFERENCES collector_runs (id),
    is_open         INTEGER,                -- 1 open, 0 closed, NULL unknown
    last_checked    TEXT,
    source          TEXT NOT NULL DEFAULT '',
    UNIQUE (run_id)
);

-- Sector index definitions (17 rows upstream). Values themselves are not
-- published by this source, so only the definitions are stored.
CREATE TABLE IF NOT EXISTS collector_sector_indices (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id          INTEGER NOT NULL REFERENCES collector_runs (id),
    index_code      TEXT NOT NULL,
    index_name      TEXT NOT NULL,
    description     TEXT NOT NULL DEFAULT '',
    sector          TEXT NOT NULL DEFAULT '',
    active_status   TEXT NOT NULL DEFAULT '',
    key_index_flag  TEXT NOT NULL DEFAULT '',
    UNIQUE (run_id, index_code)
);

-- Kronos AI forecaster experiments (schema v8). Every saved run keeps the
-- request parameters, the official model variant, the honest measured result
-- and enough context to re-load or reproduce it later. Forecast rows are
-- stored verbatim (each carries is_predicted=true) - they are never mixed
-- with observed candle tables.
CREATE TABLE IF NOT EXISTS kronos_experiments (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at      TEXT NOT NULL,
    kind            TEXT NOT NULL,            -- 'forecast' | 'evaluate'
    symbol          TEXT NOT NULL,
    variant         TEXT NOT NULL,            -- model variant: mini/small/base
    device          TEXT NOT NULL DEFAULT '',
    context_len     INTEGER,
    pred_len        INTEGER,
    temperature     REAL NOT NULL DEFAULT 1.0,
    sample_count    INTEGER NOT NULL DEFAULT 1,
    params_json     TEXT NOT NULL DEFAULT '{}',
    result_json     TEXT NOT NULL DEFAULT '{}',
    inference_seconds REAL,
    note            TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_kronos_exp_created ON kronos_experiments (created_at);
CREATE INDEX IF NOT EXISTS idx_kronos_exp_symbol  ON kronos_experiments (symbol);

-- ---------------------------------------------------------------------------
-- Data-source reconciliation (schema v10).
--
-- A reconciliation *run* records that a comparison was performed, with the
-- tolerances used and the finding counts. Individual findings are recomputed on
-- demand from the live data (never cached as truth), so a stale copy of a
-- discrepancy can never be mistaken for the current one. A *resolution* is the
-- only durable decision: it names which source was chosen (or that the finding
-- is left open) and why, with an author and timestamp for the audit history.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS reconciliation_runs (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    dataset          TEXT NOT NULL,
    created_at       TEXT NOT NULL,
    tolerances_json  TEXT NOT NULL DEFAULT '{}',
    findings         INTEGER NOT NULL DEFAULT 0,
    detail_json      TEXT NOT NULL DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_recon_runs_created ON reconciliation_runs (created_at);

CREATE TABLE IF NOT EXISTS reconciliation_resolutions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    dataset       TEXT NOT NULL,
    finding_key   TEXT NOT NULL,      -- stable identity of the observation
    classification TEXT NOT NULL,
    chosen_source TEXT NOT NULL DEFAULT '',
    resolution    TEXT NOT NULL,      -- accepted | left_open | needs_review | accepted_both
    note          TEXT NOT NULL DEFAULT '',
    actor         TEXT NOT NULL DEFAULT 'local',
    created_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_recon_res_key ON reconciliation_resolutions (dataset, finding_key);

-- ---------------------------------------------------------------------------
-- Calculation snapshots (NF-014, schema v10).
--
-- One row per captured calculation. `reproducibility` is decided by the
-- capture code - not asserted by callers - and is one of
--   fully_reproducible        inputs, versions and methodology all recoverable
--   partially_reproducible    some required historical inputs are missing
--   unrecoverable             the original inputs cannot be recovered
-- Secrets are never stored: the capture path only accepts named scalar params.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS calculation_snapshots (
    id                  TEXT PRIMARY KEY,
    feature             TEXT NOT NULL,
    created_at          TEXT NOT NULL,
    data_cutoff         TEXT,
    universe            TEXT NOT NULL DEFAULT '',
    date_range          TEXT NOT NULL DEFAULT '',
    source_ids          TEXT NOT NULL DEFAULT '[]',
    input_hash          TEXT NOT NULL,
    params_json         TEXT NOT NULL DEFAULT '{}',
    methodology         TEXT NOT NULL DEFAULT '',
    code_version        TEXT NOT NULL DEFAULT '',
    benchmark           TEXT NOT NULL DEFAULT '',
    cost_assumptions    TEXT NOT NULL DEFAULT '',
    seed                TEXT NOT NULL DEFAULT '',
    results_json        TEXT NOT NULL DEFAULT '{}',
    results_hash        TEXT NOT NULL DEFAULT '',
    warnings_json       TEXT NOT NULL DEFAULT '[]',
    data_quality        TEXT NOT NULL DEFAULT 'unknown',
    references_json     TEXT NOT NULL DEFAULT '[]',
    limitations         TEXT NOT NULL DEFAULT '',
    reproducibility     TEXT NOT NULL,
    missing_inputs_json TEXT NOT NULL DEFAULT '[]'
);
CREATE INDEX IF NOT EXISTS idx_snap_created ON calculation_snapshots (created_at);
CREATE INDEX IF NOT EXISTS idx_snap_feature ON calculation_snapshots (feature);

-- ---------------------------------------------------------------------------
-- Fundamental revisions (NF-028, schema v10).
--
-- `fundamentals` keeps only the current value per identity; re-imports
-- overwrite in place. This table records each change going *forward* (old ->
-- new) so a revision monitor has real history. It deliberately contains no
-- back-filled rows: history before this table exists is genuinely unavailable
-- and is reported as such rather than reconstructed.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS fundamental_revisions (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol        TEXT NOT NULL,
    field         TEXT NOT NULL,
    period_end    TEXT NOT NULL DEFAULT '',
    source        TEXT NOT NULL,
    old_value     REAL,
    new_value     REAL NOT NULL,
    changed_at    TEXT NOT NULL,
    source_ref    TEXT NOT NULL DEFAULT '',
    reason        TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_fund_rev_sym ON fundamental_revisions (symbol, field);

-- ---------------------------------------------------------------------------
-- Research-desk runs and natural-language query audit (NF-015 / NF-016, v10).
--
-- Both store what was asked and what was returned so a user can re-open a past
-- question. NF-015 runs keep the evidence bundle and the model text (never a
-- key); NF-016 runs keep only the *plan* and a summary result -- the plan is the
-- security boundary, so it is persisted for audit rather than the raw output.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS research_runs (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at     TEXT NOT NULL,
    symbol         TEXT NOT NULL DEFAULT '',
    question       TEXT NOT NULL,
    provider       TEXT NOT NULL DEFAULT '',
    model          TEXT NOT NULL DEFAULT '',
    available      INTEGER NOT NULL DEFAULT 0,
    evidence_json  TEXT NOT NULL DEFAULT '[]',
    review_json    TEXT NOT NULL DEFAULT '{}',
    answer         TEXT NOT NULL DEFAULT '',
    error          TEXT NOT NULL DEFAULT '',
    snapshot_id    TEXT NOT NULL DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_research_created ON research_runs (created_at);

CREATE TABLE IF NOT EXISTS nl_query_runs (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at   TEXT NOT NULL,
    question     TEXT NOT NULL,
    plan_json    TEXT NOT NULL DEFAULT '{}',
    status       TEXT NOT NULL,          -- ok | rejected | error
    reason       TEXT NOT NULL DEFAULT '',
    rows         INTEGER NOT NULL DEFAULT 0,
    duration_ms  INTEGER NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_nlq_created ON nl_query_runs (created_at);

-- ---------------------------------------------------------------------------
-- Corporate events (NF-004 / NF-020 partial, v11).
--
-- A typed calendar of corporate notices: dividend, bonus, rights, IPO,
-- allotment, AGM, split, merger, retirement. The project holds no licensed
-- notice feed, so this table starts EMPTY and is only ever filled from a
-- supplied document (CSV/rows) or projected from the attested retirement
-- registry. Nothing here is ever inferred from a price series.
-- ---------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS corporate_events (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol         TEXT NOT NULL,
    event_type     TEXT NOT NULL,
    effective_date TEXT NOT NULL DEFAULT '',
    headline       TEXT NOT NULL DEFAULT '',
    value          REAL,
    unit           TEXT NOT NULL DEFAULT '',
    ratio          TEXT NOT NULL DEFAULT '',
    successor      TEXT NOT NULL DEFAULT '',
    source         TEXT NOT NULL,
    source_ref     TEXT NOT NULL DEFAULT '',
    evidence       TEXT NOT NULL DEFAULT '',
    grade          TEXT NOT NULL DEFAULT 'reported',
    notes          TEXT NOT NULL DEFAULT '',
    retrieved_at   TEXT NOT NULL DEFAULT '',
    UNIQUE (symbol, event_type, effective_date, source)
);
CREATE INDEX IF NOT EXISTS idx_corp_events_date ON corporate_events (effective_date);
CREATE INDEX IF NOT EXISTS idx_corp_events_sym ON corporate_events (symbol, event_type);
"""

# --- index_ohlc_history: historical NEPSE index OHLC from verified sources ---
# Added in schema v9. Created here so fresh databases receive the complete
# schema through the normal init path (megatool init). Idempotent.
_INDEX_OHLC_SCHEMA = """
CREATE TABLE IF NOT EXISTS index_ohlc_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    index_name TEXT NOT NULL,
    trading_date DATE NOT NULL,
    open REAL,
    high REAL,
    low REAL,
    close REAL NOT NULL,
    volume REAL,
    volume_type TEXT,
    ohlc_status TEXT NOT NULL,
    source TEXT NOT NULL,
    source_file TEXT,
    retrieved_at TIMESTAMP,
    close_diff_vs_index_series REAL,
    UNIQUE(index_name, trading_date)
);
CREATE INDEX IF NOT EXISTS idx_ioh_name_date ON index_ohlc_history (index_name, trading_date);
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


# Columns added to ``pdf_records`` in schema v5. Kept as data so the CREATE
# TABLE statement and the migration for older databases cannot drift apart.
_PDF_RECORDS_V5_COLUMNS: dict[str, str] = {
    "extraction_method": "TEXT NOT NULL DEFAULT ''",
    "verification_status": "TEXT NOT NULL DEFAULT 'ocr_only'",
    "original_reading": "TEXT NOT NULL DEFAULT ''",
    "corrected_value": "TEXT",
    "correction_history": "TEXT NOT NULL DEFAULT '[]'",
    "reconciliation": "TEXT NOT NULL DEFAULT 'not_applicable'",
    "page_sha256": "TEXT NOT NULL DEFAULT ''",
    "verification_note": "TEXT NOT NULL DEFAULT ''",
}


def _migrate_pdf_records(conn: Any) -> None:
    """Add the schema-v5 provenance columns to a database created at v4.

    ``CREATE TABLE IF NOT EXISTS`` never alters an existing table, so an
    already-created ``pdf_records`` would otherwise silently lack the
    provenance columns and every import would fail. The migration is
    idempotent: each column is added only if it is not already present.
    """
    existing = {r["name"] for r in conn.execute("PRAGMA table_info(pdf_records)")}
    for name, decl in _PDF_RECORDS_V5_COLUMNS.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE pdf_records ADD COLUMN {name} {decl}")


#: Columns added to ``alert_history`` for severity, cooldown counters and
#: acknowledgement. Same idempotent ADD COLUMN approach as pdf_records.
_ALERT_HISTORY_V6_COLUMNS = {
    "severity": "TEXT NOT NULL DEFAULT 'warning'",
    "fire_count": "INTEGER NOT NULL DEFAULT 1",
    "acknowledged_at": "TEXT",
}


def _migrate_alert_history(conn: Any) -> None:
    """Add severity / fire_count / acknowledged_at to an existing alert table."""
    existing = {r["name"] for r in conn.execute("PRAGMA table_info(alert_history)")}
    for name, decl in _ALERT_HISTORY_V6_COLUMNS.items():
        if name not in existing:
            conn.execute(f"ALTER TABLE alert_history ADD COLUMN {name} {decl}")


def init_app_db(db_path: Path | None = None) -> int:
    """Create/upgrade the application database. Returns the schema version."""
    ensure_dirs()
    with get_conn(db_path) as conn:
        conn.executescript(_SCHEMA)
        conn.executescript(_INDEX_OHLC_SCHEMA)
        _migrate_pdf_records(conn)
        _migrate_alert_history(conn)
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
