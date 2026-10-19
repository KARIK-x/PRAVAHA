"""Event clustering (Part 14): group articles that report the same
underlying event, so syndicated copies are not counted as independent
confirmations.

Approach: union-find over candidate pairs blocked by (primary entity OR
event_type) and a rolling time window, merged when headline/text shingle
similarity >= threshold. Distinct-source counts are computed per cluster
from unique source_ids — never from raw article counts.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from ..deduplication.dedup import jaccard, shingles
from ..normalization.timestamps import parse_timestamp


class _UnionFind:
    def __init__(self):
        self.parent: dict[str, str] = {}

    def find(self, x: str) -> str:
        self.parent.setdefault(x, x)
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, a: str, b: str) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.parent[rb] = ra


@dataclass
class ClusterMember:
    article_id: str
    source_id: str
    title: str
    published_at: str | None
    event_types: list[str] = field(default_factory=list)
    entity_ids: list[str] = field(default_factory=list)
    shingle_set: frozenset = frozenset()


@dataclass
class EventCluster:
    cluster_key: str
    members: list[ClusterMember]
    distinct_sources: int
    earliest_publication: str | None
    dominant_event_type: str | None


def cluster_articles(members: list[ClusterMember], *,
                     window_hours: float = 72.0,
                     similarity_threshold: float = 0.45) -> list[EventCluster]:
    uf = _UnionFind()
    for m in members:
        uf.find(m.article_id)
    # candidate blocking by shared event type or shared entity
    for i, a in enumerate(members):
        ta = parse_timestamp(a.published_at) if a.published_at else None
        for b in members[i + 1:]:
            shared_type = bool(set(a.event_types) & set(b.event_types))
            shared_entity = bool(set(a.entity_ids) & set(b.entity_ids))
            if not (shared_type and (shared_entity or len(a.event_types) == 0)):
                continue
            tb = parse_timestamp(b.published_at) if b.published_at else None
            if ta and tb and abs((ta - tb).total_seconds()) > window_hours * 3600:
                continue
            sim = jaccard(a.shingle_set, b.shingle_set)
            if sim >= similarity_threshold:
                uf.union(a.article_id, b.article_id)
    groups: dict[str, list[ClusterMember]] = {}
    for m in members:
        groups.setdefault(uf.find(m.article_id), []).append(m)

    clusters = []
    for root, ms in groups.items():
        times = [parse_timestamp(m.published_at) for m in ms if m.published_at]
        times = [t for t in times if t]
        type_counts: dict[str, int] = {}
        for m in ms:
            for t in m.event_types:
                type_counts[t] = type_counts.get(t, 0) + 1
        clusters.append(EventCluster(
            cluster_key=root,
            members=ms,
            distinct_sources=len({m.source_id for m in ms}),
            earliest_publication=min(times).isoformat() if times else None,
            dominant_event_type=max(type_counts, key=type_counts.get) if type_counts else None,
        ))
    return clusters


def member_from_row(article_row, mentions, event_types) -> ClusterMember:
    return ClusterMember(
        article_id=article_row["article_id"],
        source_id=article_row["source_id"],
        title=article_row["title"],
        published_at=article_row["published_at"],
        event_types=event_types,
        entity_ids=mentions,
        shingle_set=shingles((article_row["title"] or "") + "\n" +
                             (article_row["normalized_text"] or "")[:1500]),
    )
