"""Unicode and text normalization for Nepali/English/mixed financial text.

The original text is NEVER overwritten. Normalization always produces a new
string so the pipeline can store original + normalized representations
side by side (Part 9 of the project specification).
"""
from __future__ import annotations

import re
import unicodedata

# Devanagari digits -> ASCII digits mapping table
_DEVANAGARI_DIGITS = str.maketrans("०१२३४५६७८९", "0123456789")

_ZERO_WIDTH = re.compile(r"[​‌‍﻿]")
_MULTI_WS = re.compile(r"[ \t\u00a0]+")
_MULTI_NL = re.compile(r"\n{3,}")

# Characters that frequently appear as mojibake / legacy encodings in Nepali news
_REPLACEMENTS = {
    "à¤": "",  # stripped later by NFC pass; placeholder for explicit review
}


def normalize_unicode(text: str) -> str:
    """Apply NFC normalization and remove zero-width joiners/invisible chars."""
    if not text:
        return ""
    text = unicodedata.normalize("NFC", text)
    text = _ZERO_WIDTH.sub("", text)
    return text


def normalize_whitespace(text: str) -> str:
    """Collapse runs of spaces/tabs, trim lines, cap blank lines at two."""
    if not text:
        return ""
    text = _MULTI_WS.sub(" ", text)
    text = "\n".join(line.strip() for line in text.splitlines())
    text = _MULTI_NL.sub("\n\n", text)
    return text.strip()


def normalize_digits(text: str) -> str:
    """Convert Devanagari digits to ASCII digits (0-9).

    This is lossy-ish but reversible in meaning; the original is preserved
    separately by the pipeline.
    """
    return (text or "").translate(_DEVANAGARI_DIGITS)


def normalize_text(text: str, *, digits: bool = True) -> str:
    """Full default normalization chain: unicode -> digits -> whitespace."""
    text = normalize_unicode(text)
    if digits:
        text = normalize_digits(text)
    text = normalize_whitespace(text)
    return text


def devanagari_ratio(text: str) -> float:
    """Fraction of script-bearing characters that are Devanagari (U+0900-U+097F).
    Combining vowel signs count toward the Devanagari side, not as Latin."""
    if not text:
        return 0.0
    deva = sum(1 for c in text if "ऀ" <= c <= "ॿ")
    latin = sum(1 for c in text if c in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ")
    total = deva + latin
    return deva / total if total else 0.0
