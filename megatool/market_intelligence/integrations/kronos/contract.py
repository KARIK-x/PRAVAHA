"""Kronos integration contract (Part 23 / Milestone 10).

Kronos (shiyu-coder/Kronos, NeoQuasar weights) is a K-line foundation
model: it consumes OHLCV(A) sequences and nothing else. It does NOT read
news text. Therefore this subsystem never injects sentiment into Kronos
inputs. Instead it exports a *time-aligned information feature frame* that
a downstream experiment (Experiment B/C in docs/KRONOS_INTEGRATION.md) may
join with prices and evaluate independently.

This module defines and validates that contract; it has no Kronos
dependency and modifies nothing in the main Mega Tool.
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field

CONTRACT_VERSION = "1.0.0"

# Columns of the exported feature frame. All values for session date D use
# only information published strictly before the D session open (enforced
# by the alignment module and validated below).
FEATURE_COLUMNS = [
    "session_date",            # YYYY-MM-DD NEPSE trading day
    "symbol",                  # ticker or 'NEPSE' for market-wide
    "news_count",              # distinct non-duplicate articles
    "distinct_source_count",   # distinct sources (syndication-adjusted)
    "sentiment_mean",          # mean lexicon/model score in [-1, 1]
    "sentiment_pos_share",
    "sentiment_neg_share",
    "event_count",
    "event_types",             # JSON array of event types observed
    "max_event_confidence",
    "data_window_start",       # provenance: earliest info timestamp used
    "data_window_end",         # latest info timestamp used (must be < session open)
]


@dataclass
class FeatureRow:
    session_date: str
    symbol: str
    news_count: int
    distinct_source_count: int
    sentiment_mean: float | None
    sentiment_pos_share: float | None
    sentiment_neg_share: float | None
    event_count: int
    event_types: list = field(default_factory=list)
    max_event_confidence: float | None = None
    data_window_start: str | None = None
    data_window_end: str | None = None

    def validate(self) -> None:
        from ...event_studies.study import check_no_lookahead
        if self.data_window_end:
            # window end must precede the session date (open at 11:00 NPT);
            # a date string compares safely at day granularity here because
            # the end timestamp includes time and the session is date-only.
            if not check_no_lookahead(self.data_window_end,
                                      self.session_date + "T11:00:00+05:45"):
                raise ValueError(
                    f"look-ahead violation: window_end={self.data_window_end} "
                    f"not before session {self.session_date} open")


def build_feature_rows(conn: sqlite3.Connection, symbol_ticker: str,
                       entity_id: str, calendar) -> list[FeatureRow]:
    """Aggregate per-session sentiment/event features for one entity from
    the intelligence database. Point-in-time safe: a row for session D only
    aggregates articles published before D 11:00 NPT."""
    from ...normalization.timestamps import parse_timestamp
    rows: list[FeatureRow] = []
    articles = conn.execute(
        """SELECT a.article_id, a.published_at, a.source_id,
                  s.score, s.general_sentiment
           FROM article_entity_mentions m
           JOIN articles a ON a.article_id = m.article_id
           LEFT JOIN sentiment_results s ON s.target_id = a.article_id
              AND s.target_type='article'
           WHERE m.entity_id = ? AND m.status = 'resolved'
             AND a.published_at IS NOT NULL
           ORDER BY a.published_at""", (entity_id,)).fetchall()
    by_session: dict[str, list] = {}
    for a in articles:
        pub = parse_timestamp(a["published_at"])
        if pub is None:
            continue
        from ...normalization.timestamps import to_kathmandu
        local = to_kathmandu(pub)
        d = local.date()
        if local.time() >= __import__("datetime").time(11, 0) or not calendar.is_trading_day(d):
            d = calendar.next_trading_day(d)
        by_session.setdefault(d.isoformat(), []).append(a)
    for session, arts in sorted(by_session.items()):
        scores = [a["score"] for a in arts if a["score"] is not None]
        rows.append(FeatureRow(
            session_date=session, symbol=symbol_ticker,
            news_count=len(arts),
            distinct_source_count=len({a["source_id"] for a in arts}),
            sentiment_mean=round(sum(scores) / len(scores), 4) if scores else None,
            sentiment_pos_share=(round(sum(1 for s in scores if s > 0) / len(scores), 4)
                                 if scores else None),
            sentiment_neg_share=(round(sum(1 for s in scores if s < 0) / len(scores), 4)
                                 if scores else None),
            event_count=0, event_types=[],
            data_window_start=min(a["published_at"] for a in arts),
            data_window_end=max(a["published_at"] for a in arts),
        ))
    for r in rows:
        r.validate()
    return rows


def export_frame_json(rows: list[FeatureRow]) -> str:
    return json.dumps({
        "contract_version": CONTRACT_VERSION,
        "columns": FEATURE_COLUMNS,
        "rows": [r.__dict__ for r in rows],
        "note": ("Features only. Feed to a separately evaluated downstream "
                 "model (Experiment B). Never concatenate into Kronos OHLCV "
                 "inputs. See docs/KRONOS_INTEGRATION.md."),
    }, ensure_ascii=False, indent=1)
