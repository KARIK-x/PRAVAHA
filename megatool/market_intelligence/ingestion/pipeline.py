"""End-to-end ingestion pipeline: RawItem -> stored Article with
normalization, language detection, deduplication, entity resolution,
sentiment, and event classification. Idempotent: re-ingesting the same
feed never creates duplicate rows (stable article_id + INSERT OR IGNORE).
"""
from __future__ import annotations

from ..deduplication.dedup import DuplicateIndex, normalized_text_hash, sha256_hex
from ..entities.registry import EntityRegistry
from ..event_detection.classifier import EventClassifier
from ..language.detect import detect_language
from ..models.schemas import Article
from ..normalization.text import normalize_text
from ..normalization.timestamps import now_utc_iso
from ..normalization.urls import normalize_url
from ..sentiment.base import SentimentModel

PARSER_VERSION = "1.0.0"


class Pipeline:
    def __init__(self, conn, *, entity_registry: EntityRegistry | None,
                 sentiment_model: SentimentModel, event_classifier: EventClassifier,
                 near_threshold: float = 0.8):
        self.conn = conn
        self.entities = entity_registry
        self.sentiment = sentiment_model
        self.events = event_classifier
        self.dedup = DuplicateIndex(near_threshold=near_threshold)
        if entity_registry is not None:
            self._sync_entities(entity_registry)
        self._load_existing_dedup_state()

    def _sync_entities(self, registry) -> None:
        """Upsert registry entities + aliases so mention FKs hold."""
        for e in registry.entities.values():
            self.conn.execute(
                """INSERT INTO entities (entity_id, official_name, ticker, exchange,
                   sector, nepali_name, verification_status)
                   VALUES (?,?,?,?,?,?,?)
                   ON CONFLICT(entity_id) DO UPDATE SET official_name=excluded.official_name,
                   ticker=excluded.ticker, sector=excluded.sector""",
                (e.entity_id, e.official_name, e.ticker, e.exchange, e.sector,
                 e.nepali_name, e.verification_status))
            alias_rows = ([(a, "english") for a in e.aliases]
                          + [(a, "devanagari") for a in e.devanagari_aliases]
                          + [(a, "romanized") for a in e.romanized_aliases]
                          + [(a, "former") for a in e.former_names])
            for alias, atype in alias_rows:
                self.conn.execute(
                    """INSERT OR IGNORE INTO entity_aliases (alias_id, entity_id, alias, alias_type)
                       VALUES (?,?,?,?)""",
                    (f"{e.entity_id}:{alias[:40]}", e.entity_id, alias, atype))

    def _load_existing_dedup_state(self) -> None:
        for row in self.conn.execute(
                "SELECT article_id, canonical_url, normalized_text FROM articles"):
            self.dedup.add(row["article_id"], row["canonical_url"],
                           row["normalized_text"] or "")

    def process(self, source_id: str, raw, collection_method: str = "rss") -> dict:
        """Process one raw item. Returns a per-item outcome record."""
        from ..database import db

        title = getattr(raw, "title", "") or ""
        # RawItem.body OR FeedItem.content/summary — accept both shapes
        body = (getattr(raw, "body", None) or getattr(raw, "content", None)
                or getattr(raw, "summary", None) or "")
        raw_url = getattr(raw, "url", None) or getattr(raw, "link", "") or ""
        text = f"{title}\n{body}".strip()
        if not text or len(text) < 10:
            return {"status": "skipped", "reason": "empty_or_too_short", "url": raw_url}

        canonical = normalize_url(raw_url)
        if not canonical:
            canonical = "nourl:" + sha256_hex(text)[:32]
        article_id = sha256_hex(f"{source_id}|{canonical}")
        normalized = normalize_text(text)

        lang = detect_language(normalized)
        article = Article(
            article_id=article_id, source_id=source_id, url=raw_url,
            canonical_url=canonical, title=title, body=text,
            normalized_text=normalized, language=lang.language,
            language_confidence=lang.confidence, author=getattr(raw, "author", None),
            published_at=getattr(raw, "published_at", None) or getattr(raw, "published", None), retrieved_at=now_utc_iso(),
            collection_method=collection_method,
            content_hash=normalized_text_hash(normalized),
            parser_version=PARSER_VERSION,
        )
        created = db.insert_article(self.conn, {
            **{k: v for k, v in article.__dict__.items()},
        })
        if not created:
            return {"status": "duplicate", "article_id": article_id, "reason": "already_stored"}

        verdict = self.dedup.check(canonical, normalized)
        if verdict.matched_id and verdict.matched_id != article_id:
            db.insert_duplicate(self.conn, article_id, verdict.matched_id,
                                verdict.similarity, verdict.method)
        self.dedup.add(article_id, canonical, normalized)

        mentions = []
        if self.entities is not None:
            for m in self.entities.resolve(title + "\n" + (body[:2000])):
                mentions.append({"entity_id": m.entity_id, "matched_alias": m.matched_alias,
                                 "confidence": m.confidence, "status": m.status,
                                 "candidates": m.candidates})
                db.insert_mention(self.conn, "article_entity_mentions",
                                  "article_id", article_id, mentions[-1])

        sent = self.sentiment.predict(normalized[:4000], language=lang.language)
        sent.validate()
        db.insert_sentiment(self.conn, {
            "result_id": f"sent_{article_id}_{sent_model_id(self.sentiment)}",
            "target_type": "article", "target_id": article_id,
            "model_id": self.sentiment.model_id,
            "model_version": self.sentiment.model_version,
            "general_sentiment": sent.general_sentiment,
            "intensity": sent.intensity, "score": sent.score,
            "confidence": sent.confidence, "language": lang.language,
            "details": sent.details,
        })

        event_types = self.events.classify(normalized[:4000])
        return {"status": "stored", "article_id": article_id, "language": lang.language,
                "mentions": len(mentions), "sentiment": sent.general_sentiment,
                "event_types": [e.event_type for e in event_types],
                "near_duplicate_of": verdict.matched_id if verdict.is_near_duplicate else None}


def sent_model_id(model) -> str:
    return f"{model.model_id}:{model.model_version}"
