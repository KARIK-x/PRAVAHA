"""Read-only FastAPI layer over the intelligence database (Part 25).

The API is a thin shell: no business logic beyond query assembly, input
validation and pagination. The core package has no FastAPI dependency, so
the engine runs without the API entirely.
"""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import HTMLResponse

MAX_LIMIT = 200


def _rows(conn: sqlite3.Connection, sql: str, params=(), limit: int = 50, offset: int = 0):
    limit = min(max(1, limit), MAX_LIMIT)
    offset = max(0, offset)
    cur = conn.execute(f"{sql} LIMIT ? OFFSET ?", (*params, limit, offset))
    return [dict(r) for r in cur.fetchall()]


def _row(conn, sql, params=()):
    r = conn.execute(sql, params).fetchone()
    return dict(r) if r else None


def create_app(db_path: str) -> FastAPI:
    from ..database.db import connect
    conn = connect(db_path, shared_thread=True)  # ASGI workers run in threads
    app = FastAPI(title="NEPSE Market Intelligence Engine", version="0.1.0")
    dashboard_path = Path(__file__).resolve().parents[1] / "dashboard" / "index.html"

    @app.get("/health")
    def health():
        counts = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
                  for t in ("sources", "articles", "events", "social_accounts")}
        return {"status": "ok", "counts": counts}

    @app.get("/", response_class=HTMLResponse)
    def dashboard():
        if dashboard_path.exists():
            return dashboard_path.read_text(encoding="utf-8")
        return HTMLResponse("<h1>Dashboard not built</h1>", status_code=404)

    @app.get("/sources")
    def sources(status: str | None = None, group: str | None = None,
                limit: int = 50, offset: int = 0):
        sql = "SELECT source_id, source_name, primary_domain, source_group, automated_access_status, rss_url, last_successful_fetch_at FROM sources WHERE 1=1"
        params: list = []
        if status:
            sql += " AND automated_access_status = ?"; params.append(status)
        if group:
            sql += " AND source_group = ?"; params.append(group)
        sql += " ORDER BY source_group, source_name"
        return {"items": _rows(conn, sql, params, limit, offset)}

    @app.get("/sources/{source_id}")
    def source_detail(source_id: str):
        row = _row(conn, "SELECT * FROM sources WHERE source_id = ?", (source_id,))
        if not row:
            raise HTTPException(404, "source not found")
        return row

    @app.get("/source-health")
    def source_health(limit: int = 50, offset: int = 0):
        return {"items": _rows(conn, "SELECT * FROM source_health ORDER BY checked_at DESC",
                               (), limit, offset)}

    @app.get("/articles")
    def articles(q: str | None = None, source_id: str | None = None,
                 language: str | None = None, date_from: str | None = None,
                 date_to: str | None = None, limit: int = 50, offset: int = 0):
        sql = "SELECT article_id, source_id, title, url, language, published_at, retrieved_at FROM articles WHERE 1=1"
        params: list = []
        if q:
            sql += " AND (title LIKE ? OR body LIKE ?)"
            params += [f"%{q}%", f"%{q}%"]
        if source_id:
            sql += " AND source_id = ?"; params.append(source_id)
        if language:
            sql += " AND language = ?"; params.append(language)
        if date_from:
            sql += " AND published_at >= ?"; params.append(date_from)
        if date_to:
            sql += " AND published_at <= ?"; params.append(date_to)
        sql += " ORDER BY published_at DESC"
        return {"items": _rows(conn, sql, params, limit, offset)}

    @app.get("/articles/{article_id}")
    def article_detail(article_id: str):
        row = _row(conn, "SELECT * FROM articles WHERE article_id = ?", (article_id,))
        if not row:
            raise HTTPException(404, "article not found")
        row["mentions"] = _rows(conn, "SELECT * FROM article_entity_mentions WHERE article_id = ?",
                                (article_id,))
        row["sentiment"] = _rows(conn, "SELECT * FROM sentiment_results WHERE target_id = ? AND target_type='article'",
                                 (article_id,))
        row["duplicates"] = _rows(conn, "SELECT * FROM article_duplicates WHERE article_id = ? OR duplicate_of = ?",
                                  (article_id, article_id))
        return row

    @app.get("/entities")
    def entities(limit: int = 50, offset: int = 0):
        return {"items": _rows(conn, "SELECT * FROM entities ORDER BY official_name",
                               (), limit, offset)}

    @app.get("/entities/{entity_id}")
    def entity_detail(entity_id: str):
        row = _row(conn, "SELECT * FROM entities WHERE entity_id = ?", (entity_id,))
        if not row:
            raise HTTPException(404, "entity not found")
        return row

    @app.get("/entities/{entity_id}/news")
    def entity_news(entity_id: str, limit: int = 50, offset: int = 0):
        return {"items": _rows(conn, """
            SELECT a.article_id, a.title, a.url, a.published_at, m.confidence, m.status
            FROM article_entity_mentions m JOIN articles a ON a.article_id = m.article_id
            WHERE m.entity_id = ? ORDER BY a.published_at DESC""", (entity_id,), limit, offset)}

    @app.get("/entities/{entity_id}/sentiment")
    def entity_sentiment(entity_id: str, limit: int = 100, offset: int = 0):
        return {"items": _rows(conn, """
            SELECT a.published_at, s.general_sentiment, s.intensity, s.score, s.confidence
            FROM article_entity_mentions m
            JOIN articles a ON a.article_id = m.article_id
            JOIN sentiment_results s ON s.target_id = a.article_id AND s.target_type='article'
            WHERE m.entity_id = ? AND m.status='resolved'
            ORDER BY a.published_at""", (entity_id,), limit, offset)}

    @app.get("/events")
    def events(event_type: str | None = None, limit: int = 50, offset: int = 0):
        sql = "SELECT event_id, event_type, event_title, first_observed_time, confirmation_status, distinct_source_count FROM events"
        params: list = []
        if event_type:
            sql += " WHERE event_type = ?"; params.append(event_type)
        sql += " ORDER BY first_observed_time DESC"
        return {"items": _rows(conn, sql, params, limit, offset)}

    @app.get("/events/{event_id}")
    def event_detail(event_id: str):
        row = _row(conn, "SELECT * FROM events WHERE event_id = ?", (event_id,))
        if not row:
            raise HTTPException(404, "event not found")
        for k in ("primary_entities", "affected_sectors", "sentiment_by_entity"):
            if row.get(k):
                row[k] = json.loads(row[k])
        row["articles"] = _rows(conn, """
            SELECT a.article_id, a.title, a.url, a.source_id, a.published_at
            FROM event_sources es JOIN articles a ON a.article_id = es.article_id
            WHERE es.event_id = ?""", (event_id,))
        return row

    @app.get("/accounts")
    def accounts(limit: int = 50, offset: int = 0):
        return {"items": _rows(conn, """
            SELECT account_id, platform, handle, display_name, account_category,
                   public_verification_status, nepse_relevance
            FROM social_accounts ORDER BY account_category""", (), limit, offset)}

    @app.get("/social-posts")
    def social_posts(account_id: str | None = None, limit: int = 50, offset: int = 0):
        sql = "SELECT post_id, account_id, text, language, published_at, url FROM social_posts"
        params: list = []
        if account_id:
            sql += " WHERE account_id = ?"; params.append(account_id)
        sql += " ORDER BY published_at DESC"
        return {"items": _rows(conn, sql, params, limit, offset)}

    @app.get("/analysis/event-studies")
    def event_studies(limit: int = 50, offset: int = 0):
        return {"items": _rows(conn, "SELECT * FROM event_studies ORDER BY rowid DESC",
                               (), limit, offset)}

    @app.get("/analysis/model-evaluations")
    def model_evaluations(limit: int = 50, offset: int = 0):
        return {"items": _rows(conn, "SELECT * FROM model_evaluations ORDER BY evaluated_at DESC",
                               (), limit, offset)}

    @app.get("/jobs")
    def jobs(limit: int = 50, offset: int = 0):
        return {"items": _rows(conn, "SELECT * FROM collection_jobs ORDER BY started_at DESC",
                               (), limit, offset)}

    @app.get("/models")
    def models():
        return {"items": _rows(conn, "SELECT * FROM sentiment_model_registry", (), 100)}

    return app
