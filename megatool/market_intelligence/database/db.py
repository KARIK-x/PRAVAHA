"""Database layer: connection management, migrations, idempotent writes.

SQLite with WAL mode. Migrations are plain .sql files applied in filename
order and recorded in schema_migrations; re-running migrations is a no-op.
All writes use INSERT OR IGNORE / upserts keyed on stable IDs so retries
never create duplicates (Part 15 acceptance criteria).
"""
from __future__ import annotations

import json
import sqlite3
import uuid
from pathlib import Path

DEFAULT_DB = "data/market_intelligence.db"


def connect(db_path: str | Path = DEFAULT_DB, *, shared_thread: bool = False) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path), check_same_thread=not shared_thread)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def run_migrations(conn: sqlite3.Connection, migrations_dir: str | Path) -> list[int]:
    applied = {r[0] for r in conn.execute(
        "SELECT version FROM schema_migrations"
    )} if _table_exists(conn, "schema_migrations") else set()
    done = []
    for f in sorted(Path(migrations_dir).glob("*.sql")):
        version = int(f.name.split("_")[0])
        if version in applied:
            continue
        conn.executescript(f.read_text(encoding="utf-8"))
        conn.execute("INSERT INTO schema_migrations(version, applied_at) VALUES (?, ?)",
                     (version, _now()))
        done.append(version)
    conn.commit()
    return done


def _table_exists(conn, name) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def _now() -> str:
    from ..normalization.timestamps import now_utc_iso
    return now_utc_iso()


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


def upsert_source(conn, rec: dict) -> None:
    cols = list(rec.keys())
    conn.execute(
        f"INSERT INTO sources ({','.join(cols)}) VALUES ({','.join('?' * len(cols))}) "
        f"ON CONFLICT(source_id) DO UPDATE SET "
        + ", ".join(f"{c}=excluded.{c}" for c in cols if c != "source_id"),
        [json.dumps(v, ensure_ascii=False) if isinstance(v, (list, dict)) else v for v in rec.values()],
    )


def insert_article(conn, a: dict) -> bool:
    """Idempotent insert. Returns True if a new row was created."""
    cur = conn.execute(
        """INSERT OR IGNORE INTO articles
           (article_id, source_id, url, canonical_url, title, body,
            normalized_text, content_hash, language, language_confidence,
            author, published_at, retrieved_at, collection_method, parser_version)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (a["article_id"], a["source_id"], a["url"], a["canonical_url"], a["title"],
         a["body"], a.get("normalized_text"), a["content_hash"], a.get("language"),
         a.get("language_confidence"), a.get("author"), a.get("published_at"),
         a["retrieved_at"], a["collection_method"], a["parser_version"]),
    )
    return cur.rowcount == 1


def insert_duplicate(conn, article_id: str, duplicate_of: str, similarity: float, method: str) -> None:
    conn.execute(
        """INSERT OR IGNORE INTO article_duplicates
           (duplicate_id, article_id, duplicate_of, similarity, method, detected_at)
           VALUES (?,?,?,?,?,?)""",
        (new_id("dup"), article_id, duplicate_of, similarity, method, _now()),
    )


def insert_mention(conn, table: str, id_col: str, target_id: str, m: dict) -> None:
    conn.execute(
        f"""INSERT OR REPLACE INTO {table}
            ({id_col}, entity_id, matched_alias, confidence, role, status, candidates)
            VALUES (?,?,?,?,?,?,?)""",
        (target_id, m.get("entity_id"), m["matched_alias"], m["confidence"],
         m.get("role", "mentioned"), m["status"],
         json.dumps(m.get("candidates")) if m.get("candidates") else None),
    )


def insert_sentiment(conn, s: dict) -> bool:
    cur = conn.execute(
        """INSERT OR IGNORE INTO sentiment_results
           (result_id, target_type, target_id, model_id, model_version,
            general_sentiment, intensity, score, confidence, language, details, processed_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (s["result_id"], s["target_type"], s["target_id"], s["model_id"],
         s["model_version"], s["general_sentiment"], s["intensity"], s["score"],
         s["confidence"], s.get("language"),
         json.dumps(s.get("details", {}), ensure_ascii=False), _now()),
    )
    return cur.rowcount == 1


def insert_event(conn, e: dict) -> None:
    conn.execute(
        """INSERT OR REPLACE INTO events
           (event_id, event_type, event_title, event_summary, primary_entities,
            affected_sectors, publication_time, detection_time, first_observed_time,
            confirmation_status, sentiment_by_entity, distinct_source_count,
            taxonomy_version)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (e["event_id"], e["event_type"], e["event_title"], e.get("event_summary"),
         json.dumps(e.get("primary_entities", []), ensure_ascii=False),
         json.dumps(e.get("affected_sectors", []), ensure_ascii=False),
         e.get("publication_time"), e["detection_time"], e.get("first_observed_time"),
         e.get("confirmation_status", "unverified_claim"),
         json.dumps(e.get("sentiment_by_entity", {}), ensure_ascii=False),
         e.get("distinct_source_count", 0), e.get("taxonomy_version")),
    )


def link_event_article(conn, event_id: str, article_id: str) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO event_sources (event_id, article_id, added_at) VALUES (?,?,?)",
        (event_id, article_id, _now()),
    )


def audit(conn, actor: str, action: str, target: str = "", details: dict | None = None) -> None:
    conn.execute(
        "INSERT INTO audit_log (log_id, occurred_at, actor, action, target, details) VALUES (?,?,?,?,?,?)",
        (new_id("log"), _now(), actor, action, target,
         json.dumps(details or {}, ensure_ascii=False)),
    )
