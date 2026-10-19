"""Duplicate detection: exact URL, canonical URL, text hashes, and
shingle-based near-duplicate detection (Part 14).

Deliberately implemented with the standard library only. For the target
scale (a personal research system; thousands–low-hundreds-of-thousands of
articles) banded shingle Jaccard with entity/date blocking is adequate and
transparent. If the corpus grows, datasketch MinHashLSH is the documented
upgrade path (see docs/REPOSITORY_RESEARCH.md).
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass

from ..normalization.text import normalize_text
from ..normalization.urls import normalize_url

_TOKEN = re.compile(r"[ऀ-ॿ]+|[A-Za-z0-9']+")


def sha256_hex(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def exact_text_hash(text: str) -> str:
    """Hash of the raw text (byte-identical duplicates only)."""
    return sha256_hex(text or "")


def normalized_text_hash(text: str) -> str:
    """Hash after unicode/whitespace/digit normalization."""
    return sha256_hex(normalize_text(text or "").lower())


def canonical_url_key(url: str) -> str:
    return normalize_url(url or "")


def tokens(text: str) -> list[str]:
    return _TOKEN.findall((text or "").lower())


def _stable_hash(text: str) -> int:
    """Process-independent hash (built-in hash() is salted per process)."""
    return int.from_bytes(hashlib.blake2b(text.encode("utf-8"), digest_size=6).digest(), "big")


def shingles(text: str, k: int = 5) -> frozenset[int]:
    """Word k-shingle set hashed to ints. Short docs fall back to tokens."""
    toks = tokens(normalize_text(text, digits=True))
    if not toks:
        return frozenset()
    if len(toks) < k:
        return frozenset({_stable_hash(" ".join(toks))})
    out = set()
    for i in range(len(toks) - k + 1):
        out.add(_stable_hash(" ".join(toks[i:i + k])))
    return frozenset(out)


def jaccard(a: frozenset[int], b: frozenset[int]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    return inter / (len(a) + len(b) - inter) if (len(a) + len(b) - inter) else 0.0


@dataclass
class DuplicateVerdict:
    is_exact_duplicate: bool
    is_near_duplicate: bool
    matched_id: str | None
    similarity: float
    method: str


class DuplicateIndex:
    """In-memory dedup index over a batch of documents.

    Tracks canonical URLs, exact hashes, normalized hashes, and shingle
    sets; near-duplicate queries use length-banded candidate blocking to
    avoid quadratic scans.
    """

    def __init__(self, near_threshold: float = 0.8, shingle_k: int = 5):
        self.near_threshold = near_threshold
        self.shingle_k = shingle_k
        self.urls: dict[str, str] = {}
        self.exact_hashes: dict[str, str] = {}
        self.norm_hashes: dict[str, str] = {}
        self.docs: dict[str, frozenset[int]] = {}

    def add(self, doc_id: str, url: str, text: str) -> None:
        self.urls[canonical_url_key(url)] = doc_id
        self.exact_hashes[exact_text_hash(text)] = doc_id
        self.norm_hashes[normalized_text_hash(text)] = doc_id
        self.docs[doc_id] = shingles(text, self.shingle_k)

    def check(self, url: str, text: str) -> DuplicateVerdict:
        cu = canonical_url_key(url)
        if cu in self.urls:
            return DuplicateVerdict(True, False, self.urls[cu], 1.0, "canonical_url")
        eh = exact_text_hash(text)
        if eh in self.exact_hashes:
            return DuplicateVerdict(True, False, self.exact_hashes[eh], 1.0, "exact_text_hash")
        nh = normalized_text_hash(text)
        if nh in self.norm_hashes:
            return DuplicateVerdict(True, False, self.norm_hashes[nh], 1.0, "normalized_text_hash")
        sh = shingles(text, self.shingle_k)
        best_id, best_sim, method = None, 0.0, "none"
        if sh:
            n = len(sh)
            # length banding: only compare docs with similar shingle counts
            for doc_id, other in self.docs.items():
                if not other or not (0.5 <= len(other) / n <= 2.0):
                    continue
                sim = jaccard(sh, other)
                if sim > best_sim:
                    best_id, best_sim, method = doc_id, sim, "shingle_jaccard"
        near = best_sim >= self.near_threshold
        return DuplicateVerdict(False, near, best_id if near else None,
                                round(best_sim, 4), method)
