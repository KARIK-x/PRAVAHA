"""Source adapter contract (Part 15).

Every collector (RSS, official API, social) implements SourceAdapter. The
pipeline depends only on this interface, so new sources rarely need new
code — usually only a registry entry.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class RawItem:
    """A single collected item before normalization."""
    external_id: str | None
    url: str
    title: str
    body: str
    author: str | None = None
    published_at: str | None = None     # UTC ISO or None
    extra: dict = field(default_factory=dict)


@dataclass
class CollectionReport:
    source_id: str
    ok: bool
    items: list = field(default_factory=list)
    error: str | None = None
    http_status: int | None = None
    latency_ms: int = 0


class SourceAdapter(ABC):
    """Contract: identify, fetch, parse, report. Never raises on source
    failure — returns CollectionReport(ok=False, error=...)."""

    collection_method: str = "abstract"

    def __init__(self, source: dict, fetcher):
        self.source = source
        self.fetcher = fetcher

    @property
    def source_id(self) -> str:
        return self.source["source_id"]

    @abstractmethod
    def collect(self) -> CollectionReport:
        ...

    def health(self) -> dict:
        return {"source_id": self.source_id, "method": self.collection_method}
