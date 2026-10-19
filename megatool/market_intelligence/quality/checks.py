"""Data-quality checks (Part 18). Each check returns structured findings;
nothing is silently discarded — failures become check rows."""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..normalization.timestamps import is_sane_publication_time, parse_timestamp


@dataclass
class QualityFinding:
    check_type: str
    severity: str          # info | warning | error
    message: str
    target_id: str | None = None
    details: dict = field(default_factory=dict)


def check_article(article: dict) -> list[QualityFinding]:
    findings: list[QualityFinding] = []
    aid = article.get("article_id")

    body = (article.get("body") or "").strip()
    if len(body) < 10:
        findings.append(QualityFinding("missing_text", "error",
                                       "article body missing or too short", aid))
    pub = article.get("published_at")
    if not pub:
        findings.append(QualityFinding("missing_timestamp", "warning",
                                       "publication timestamp missing", aid))
    else:
        dt = parse_timestamp(pub)
        if dt is None:
            findings.append(QualityFinding("invalid_timestamp", "error",
                                           f"unparseable timestamp: {pub}", aid))
        elif not is_sane_publication_time(dt):
            findings.append(QualityFinding("invalid_timestamp", "error",
                                           f"implausible publication time: {pub}", aid))
    if article.get("language") == "unknown" and body:
        findings.append(QualityFinding("language_detection_failure", "warning",
                                       "language could not be identified", aid))
    if body:
        words = re.findall(r"\S+", body.lower())
        if words:
            top = max(words.count(w) for w in set(words)) if len(words) < 5000 else 0
            if len(words) > 20 and top / len(words) > 0.3:
                findings.append(QualityFinding("repetitive_content", "warning",
                                               "suspiciously repetitive content", aid,
                                               {"top_word_ratio": round(top / len(words), 3)}))
    url = article.get("url") or ""
    if url and not url.startswith(("http://", "https://")):
        findings.append(QualityFinding("broken_url", "warning",
                                       f"non-http url: {url[:80]}", aid))
    return findings
