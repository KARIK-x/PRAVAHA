"""Language identification for English / Nepali (Devanagari) /
Romanized Nepali / code-switched text (Part 9).

A deliberately transparent, dependency-free classifier. Devanagari detection
is near-deterministic (script range). Romanized Nepali uses a curated
function-word and market-slang lexicon; it is heuristic and its confidence
is reported honestly rather than hidden.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from ..normalization.text import devanagari_ratio

_LANG_EN = "en"
_LANG_NE = "ne"
_LANG_NE_ROMAN = "ne_roman"
_LANG_MIXED = "mixed"
_LANG_UNKNOWN = "unknown"

# Common Nepali function words written in Latin script. Kept deliberately
# conservative: these rarely appear in standard English financial text.
_ROMANIZED_NE_WORDS = {
    "ko", "ka", "ki", "ma", "le", "lai", "ra", "bhane", "pani", "garne",
    "gareko", "gareka", "bhayo", "bhayeko", "chha", "cha", "chh", "hunchha",
    "hune", "bhannu", "bhanne", "gari", "diyo", "liyo", "gayeko", "aayeko",
    "sang", "sanga", "bata", "tira", "mathi", "muni", "yasto", "testo",
    "kasto", "kina", "kahile", "kahan", "tyahi", "yaha", "tyaha", "sabai",
    "dherai", "thorai", "naya", "nayaa", "purano", "ramro", "naramro",
    "thulo", "sano", "aaja", "bholi", "hijo", "ahile", "pachi", "agadi",
    "sarkar", "sarkaar", "bajet", "byaj", "byaaj", "byajdar", "karza",
    "nafa", "ghaata", "ghatayo", "badhayo", "badhyo", "ghatyo", "badheko",
    "ghateko", "bhanyo", "bhanyo", "garyo", "diyena", "liyena", "khulyo",
    "khula", "banda", "gayena", "aayena", "bhayo",
    "sewar", "seya", "bajar", "bazaar", "lagani", "lagaani", "kitta",
    "hissa", "bonas", "bonus", "lamsam", "kharid", "bikri", "utpadan",
    "aayojana", "aayojanaa", "bidhyut", "jalabidhyut", "jalbidhyut",
    "suchak", "ankha", "karobar", "dainik", "xaina", "xainan", "ho",
    "hoina", "hunu", "le", "haru", "haruko",
}

_EN_STOPWORDS = {
    "the", "is", "are", "was", "were", "has", "have", "had", "will", "would",
    "of", "in", "on", "at", "to", "for", "and", "or", "with", "from", "by",
    "an", "a", "it", "its", "this", "that", "as", "be", "been", "said",
    "according", "announced", "reported", "company", "shares", "stock",
    "market", "price", "per", "cent", "percent",
}

_TOKEN = re.compile(r"[A-Za-z']+")
_DEVANAGARI = re.compile(r"[ऀ-ॿ]+")


@dataclass
class LanguageResult:
    language: str
    confidence: float
    devanagari_ratio: float
    romanized_nepali_hits: int = 0
    english_hits: int = 0
    details: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "language": self.language,
            "confidence": round(self.confidence, 4),
            "devanagari_ratio": round(self.devanagari_ratio, 4),
            "romanized_nepali_hits": self.romanized_nepali_hits,
            "english_hits": self.english_hits,
            "details": self.details,
        }


def detect_language(text: str) -> LanguageResult:
    """Classify text as en / ne / ne_roman / mixed / unknown with confidence."""
    if not text or not text.strip():
        return LanguageResult(_LANG_UNKNOWN, 0.0, 0.0)

    dr = devanagari_ratio(text)
    latin_tokens = [t.lower() for t in _TOKEN.findall(text)]
    roman_hits = sum(1 for t in latin_tokens if t in _ROMANIZED_NE_WORDS)
    en_hits = sum(1 for t in latin_tokens if t in _EN_STOPWORDS)
    n_latin = len(latin_tokens)

    # Strong script evidence dominates.
    if dr >= 0.9:
        return LanguageResult(_LANG_NE, min(0.99, 0.7 + dr * 0.3), dr)
    if dr >= 0.05 and n_latin >= 3:
        # Real code-switching: both scripts materially present.
        conf = 0.6 + min(dr, 1 - dr)
        return LanguageResult(_LANG_MIXED, min(0.95, conf), dr,
                              roman_hits, en_hits)
    if n_latin == 0:
        return LanguageResult(_LANG_UNKNOWN, 0.2, dr)

    roman_ratio = roman_hits / n_latin
    en_ratio = en_hits / n_latin
    if roman_hits >= 2 and roman_ratio >= 0.15:
        conf = min(0.9, 0.45 + roman_ratio + min(roman_hits, 8) * 0.03)
        if en_ratio >= 0.25 and roman_ratio >= 0.15:
            return LanguageResult(_LANG_MIXED, conf, dr, roman_hits, en_hits)
        return LanguageResult(_LANG_NE_ROMAN, conf, dr, roman_hits, en_hits)
    if en_ratio >= 0.15 or en_hits >= 3:
        return LanguageResult(_LANG_EN, min(0.95, 0.55 + en_ratio), dr,
                              roman_hits, en_hits)
    # Latin script but neither lexicon matched: default English with low
    # confidence rather than guessing Nepali.
    return LanguageResult(_LANG_EN, 0.35, dr, roman_hits, en_hits,
                          details={"fallback": "latin_default"})
