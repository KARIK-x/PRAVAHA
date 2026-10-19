"""Core data schemas (stdlib dataclasses — no pydantic dependency in core).

Timestamps are UTC ISO-8601 strings or None. Missing values stay None;
zero is never substituted for missing data.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any


@dataclass
class Article:
    article_id: str                      # stable id: sha256(source_id + canonical_url)
    source_id: str
    url: str                             # original URL as collected
    canonical_url: str
    title: str
    body: str                            # original text, never overwritten
    normalized_text: str = ""
    language: str = "unknown"
    language_confidence: float = 0.0
    author: str | None = None
    published_at: str | None = None      # UTC ISO, None when unknown
    retrieved_at: str = ""               # UTC ISO, always set at collection
    collection_method: str = "rss"
    content_hash: str = ""               # sha256 of normalized text
    parser_version: str = "1.0"
    extra: dict = field(default_factory=dict)


@dataclass
class SocialPost:
    post_id: str
    account_id: str
    platform: str
    text: str
    normalized_text: str = ""
    language: str = "unknown"
    published_at: str | None = None
    retrieved_at: str = ""
    url: str | None = None
    reply_to: str | None = None
    content_hash: str = ""
    extra: dict = field(default_factory=dict)


@dataclass
class EntityMention:
    entity_id: str
    ticker: str | None
    matched_alias: str
    confidence: float                    # 1.0 exact ticker, lower for fuzzy
    role: str = "mentioned"              # subject | mentioned
    status: str = "resolved"             # resolved | ambiguous | unresolved


@dataclass
class SentimentResult:
    target_id: str                       # article_id or post_id
    model_id: str
    model_version: str
    general_sentiment: str               # positive|negative|neutral|mixed|uncertain
    intensity: str                       # very_negative ... very_positive|uncertain
    score: float                         # -1..1
    confidence: float
    language: str
    details: dict = field(default_factory=dict)


@dataclass
class Event:
    event_id: str
    event_type: str
    title: str
    summary: str
    primary_entities: list = field(default_factory=list)
    affected_sectors: list = field(default_factory=list)
    publication_time: str | None = None
    first_observed_time: str = ""
    confirmation_status: str = "unverified_claim"
    sentiment_by_entity: dict = field(default_factory=dict)
    source_ids: list = field(default_factory=list)
    distinct_source_count: int = 0
    uncertainty: str = ""
    extra: dict = field(default_factory=dict)


def to_dict(obj: Any) -> dict:
    return asdict(obj)
