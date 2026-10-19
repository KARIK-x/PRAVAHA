"""RSS collection adapter."""
from __future__ import annotations

from ..common.adapter import CollectionReport, RawItem, SourceAdapter
from .parser import parse_feed


class RSSAdapter(SourceAdapter):
    collection_method = "rss"

    def collect(self, *, max_items: int = 50) -> CollectionReport:
        rss_url = self.source.get("rss_url")
        if not rss_url:
            return CollectionReport(self.source_id, False, error="no_rss_url")
        res = self.fetcher.fetch(rss_url, rate_key=self.source.get("primary_domain"))
        if not res.ok:
            return CollectionReport(self.source_id, False, error=res.error,
                                    http_status=res.status, latency_ms=res.latency_ms)
        if not res.body:
            # dry-run mode: no network performed
            return CollectionReport(self.source_id, True, [], http_status=res.status)
        try:
            feed_items = parse_feed(res.body)
        except ValueError as e:
            return CollectionReport(self.source_id, False, error=str(e),
                                    http_status=res.status, latency_ms=res.latency_ms)
        items = [
            RawItem(
                external_id=fi.guid,
                url=fi.link,
                title=fi.title,
                body=fi.content or fi.summary,
                author=fi.author,
                published_at=fi.published,
            )
            for fi in feed_items[:max_items]
        ]
        return CollectionReport(self.source_id, True, items,
                                http_status=res.status, latency_ms=res.latency_ms)
