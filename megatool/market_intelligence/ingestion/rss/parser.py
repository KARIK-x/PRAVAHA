"""Dependency-free RSS 2.0 / RDF / Atom parser (stdlib xml.etree).

We deliberately avoid feedparser as a hard dependency: the core engine must
run with the standard library only. The parser extracts title, link,
publication date, author and summary/content from RSS 2.0, RSS 1.0 (RDF)
and Atom feeds. HTML inside descriptions is stripped.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field

from ...normalization.timestamps import parse_timestamp

_ATOM = "{http://www.w3.org/2005/Atom}"
_RDF = "{http://www.w3.org/1999/02/22-rdf-syntax-ns#}"
_DC = "{http://purl.org/dc/elements/1.1/}"
_CONTENT = "{http://purl.org/rss/1.0/modules/content/}"

_TAG_STRIP = re.compile(r"<[^>]+>")


def strip_html(text: str) -> str:
    """Remove HTML tags and collapse whitespace. External content is
    untrusted — this never executes anything, it is pure text surgery."""
    if not text:
        return ""
    text = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", text, flags=re.S | re.I)
    text = _TAG_STRIP.sub(" ", text)
    for ent, ch in (("&amp;", "&"), ("&lt;", "<"), ("&gt;", ">"),
                    ("&quot;", '"'), ("&#39;", "'"), ("&nbsp;", " ")):
        text = text.replace(ent, ch)
    return re.sub(r"\s+", " ", text).strip()


@dataclass
class FeedItem:
    title: str
    link: str
    published: str | None = None   # UTC ISO or None
    author: str | None = None
    summary: str = ""
    content: str = ""
    guid: str | None = None


def _text(el, path) -> str | None:
    node = el.find(path)
    if node is None or node.text is None:
        return None
    return node.text.strip() or None


def parse_feed(data: bytes) -> list[FeedItem]:
    """Parse RSS 2.0 / RDF / Atom bytes into FeedItems.

    Raises ValueError on unparseable XML so callers can record a
    collection_error instead of silently dropping the source.
    """
    try:
        root = ET.fromstring(data)
    except ET.ParseError as e:
        raise ValueError(f"unparseable feed XML: {e}") from e

    items: list[FeedItem] = []
    tag = root.tag.lower()
    if tag.endswith("rss") or tag.endswith("rdf"):
        for item in root.iter("item"):
            pub = (_text(item, "pubDate") or _text(item, f"{_DC}date")
                   or _text(item, "date"))
            content = _text(item, f"{_CONTENT}encoded") or ""
            items.append(FeedItem(
                title=strip_html(_text(item, "title") or ""),
                link=(_text(item, "link") or "").strip(),
                published=(parse_timestamp(pub).isoformat() if parse_timestamp(pub) else None),
                author=_text(item, f"{_DC}creator") or _text(item, "author"),
                summary=strip_html(_text(item, "description") or ""),
                content=strip_html(content),
                guid=_text(item, "guid"),
            ))
    elif tag.endswith("feed"):
        for entry in root.iter(f"{_ATOM}entry"):
            link = ""
            for ln in entry.findall(f"{_ATOM}link"):
                if ln.get("rel", "alternate") == "alternate" and ln.get("href"):
                    link = ln.get("href"); break
            pub = (_text(entry, f"{_ATOM}published") or _text(entry, f"{_ATOM}updated"))
            items.append(FeedItem(
                title=strip_html(_text(entry, f"{_ATOM}title") or ""),
                link=link,
                published=(parse_timestamp(pub).isoformat() if parse_timestamp(pub) else None),
                author=None,
                summary=strip_html(_text(entry, f"{_ATOM}summary") or ""),
                content=strip_html(_text(entry, f"{_ATOM}content") or ""),
                guid=_text(entry, f"{_ATOM}id"),
            ))
    else:
        raise ValueError(f"unrecognized feed root element: {root.tag}")
    return [i for i in items if i.link or i.title]
