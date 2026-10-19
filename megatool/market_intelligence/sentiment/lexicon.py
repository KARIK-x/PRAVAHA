"""Lexicon-based financial sentiment baseline (Part 10/11).

This is the always-available, dependency-free baseline model. It is
intentionally simple and auditable: curated English, Devanagari Nepali and
romanized-Nepali financial lexicons with negation and intensifier handling.

The structured output follows the specification:
  - general_sentiment: positive|negative|neutral|mixed|uncertain
  - intensity: very_negative..very_positive|uncertain
  - score: -1.0 .. 1.0
  - confidence: 0..1

Model upgrades (FinBERT, nepse-sentiment-analyzer) plug in through
SentimentModel interface in base.py without touching the pipeline.
"""
from __future__ import annotations

import re

from .base import SentimentModel, SentimentOutput

_EN_POS = {
    "surge", "surges", "surged", "soar", "soared", "gain", "gains", "gained",
    "rise", "rises", "rose", "risen", "rally", "rallied", "jump", "jumped",
    "record", "growth", "grew", "expand", "expansion", "profit", "profitable",
    "boost", "boosted", "upgrade", "upgraded", "outperform", "beat", "beats",
    "strong", "stronger", "improve", "improved", "improvement", "recovery",
    "recover", "recovers", "optimistic", "bullish", "dividend", "bonus",
    "approval", "approved", "profitability", "robust", "resilient", "climb",
    "climbed", "high", "higher", "highest", "positive", "success", "win",
    "liquidity improved", "all-time high",
}
_EN_NEG = {
    "fall", "falls", "fell", "fallen", "drop", "drops", "dropped", "decline",
    "declined", "plunge", "plunged", "crash", "crashed", "loss", "losses",
    "lose", "losing", "deficit", "downgrade", "downgraded", "default",
    "defaulted", "fraud", "scam", "penalty", "fined", "fine", "sanction",
    "crisis", "recession", "inflation", "bearish", "weak", "weaker",
    "worst", "low", "lower", "lowest", "negative", "concern", "concerns",
    "worried", "risk", "risks", "risky", "halt", "halted", "suspend",
    "suspended", "liquidity crunch", "non-performing", "npl", "strike",
    "bandh", "protest", "corruption", "embezzlement", "collapse", "failed",
    "failure", "shortfall", "underperform",
}
_NE_POS = {
    "वृद्धि", "बढ्यो", "बढेको", "बढ्न", "उकालो", "नाफा", "मुनाफा", "सुधार",
    "सकारात्मक", "राम्रो", "उत्कृष्ट", "सफल", "सफलता", "लाभांश", "बोनस",
    "स्वीकृत", "स्वीकृति", "उच्च", "रेकर्ड", "विस्तार", "प्रगति", "बलियो",
    "आशावादी", "उत्साहजनक", "घट्यो नाफामा", "सुदृढ",
}
_NE_NEG = {
    "गिरावट", "घट्यो", "घटेको", "घट्न", "ओरालो", "घाटा", "नोक्सान",
    "नकारात्मक", "नराम्रो", "असफल", "जरिवाना", "कारबाही", "कमजोर",
    "संकट", "महँगी", "ऋण", "चुकिएको", "भ्रष्टाचार", "कुःख्यात", "धराप",
    "हडताल", "बन्द", "आन्दोलन", "खराब", "न्यून", "जोखिम", "डर", "चिन्ता",
    "तरलता संकट", "कुजो", "दिवालिया",
}
_ROMAN_POS = {
    "badhyo", "badheko", "briddhi", "wirdi", "ukalo", "nafa", "munafa",
    "sudhar", "sakaratmak", "ramro", "safal", "labhansh", "labangsa",
    "bonus", "swikrit", "swikriti", "uchha", "bistar", "pragati",
    "baliyo", "utsahajanak",
}
_ROMAN_NEG = {
    "ghatyo", "ghateko", "girabat", "girawat", "oralo", "ghata", "noksan",
    "nakaratmak", "naramro", "asafal", "jaribana", "karbahi", "kamjor",
    "sankat", "mahangi", "rin", "bhrastachar", "hadtal", "andaolan",
    "kharab", "jokhim", "chinta", "diwaliya", "bandha",
}

_NEGATIONS_EN = {"no", "not", "never", "without", "denies", "denied", "deny", "fails", "fail", "avoid", "avoided", "unlikely"}
_NEGATIONS_NE = {"छैन", "होइन", "भएन", "गरेन", "नहुने", "नभएको", "नभई", "बिना"}
_NEGATIONS_ROMAN = {"chhaina", "xaina", "hoina", "bhayena", "garena", "bina", "nahune", "nabhayeko"}
_INTENSIFIERS = {"very", "sharply", "significantly", "massive", "huge", "steep",
                 "धेरै", "अत्यन्त", "धेरैले", "onektai", "dherai", "atyanta", "nikkai"}

_INTENSITY_BANDS = [
    (-1.01, -0.6, "very_negative"), (-0.6, -0.25, "negative"),
    (-0.25, -0.08, "slightly_negative"), (-0.08, 0.08, "neutral"),
    (0.08, 0.25, "slightly_positive"), (0.25, 0.6, "positive"),
    (0.6, 1.01, "very_positive"),
]

_TOKEN = re.compile(r"[ऀ-ॿ]+|[A-Za-z']+")


def _band(score: float) -> str:
    for lo, hi, name in _INTENSITY_BANDS:
        if lo < score <= hi:
            return name
    return "neutral"


class LexiconSentimentModel(SentimentModel):
    """Transparent lexicon baseline. model_id: lexicon-v1."""

    model_id = "lexicon-v1"
    model_version = "1.0.0"

    def predict(self, text: str, language: str = "unknown") -> SentimentOutput:
        toks = [t.lower() for t in _TOKEN.findall(text or "")]
        pos = neg = 0
        hits_pos: list[str] = []
        hits_neg: list[str] = []
        intensity_boost = 1.0
        all_negations = _NEGATIONS_EN | _NEGATIONS_NE | _NEGATIONS_ROMAN

        def negated(i: int) -> bool:
            # a sentiment word is negated if a negation appears within the
            # preceding 3 tokens ("did not report any profit")
            return any(t in all_negations for t in toks[max(0, i - 3):i])

        for i, t in enumerate(toks):
            if t in _INTENSIFIERS:
                intensity_boost = min(1.6, intensity_boost + 0.3)
                continue
            is_pos = t in _EN_POS or t in _NE_POS or t in _ROMAN_POS
            is_neg = t in _EN_NEG or t in _NE_NEG or t in _ROMAN_NEG
            if not (is_pos or is_neg):
                continue
            if negated(i):
                is_pos, is_neg = is_neg, is_pos  # flip under negation
            if is_pos:
                pos += 1
                hits_pos.append(t)
            else:
                neg += 1
                hits_neg.append(t)
        # multiword phrase pass
        low = " ".join(toks)
        for ph in _EN_POS | _EN_NEG:
            if " " in ph and ph in low:
                if ph in _EN_POS:
                    pos += 1; hits_pos.append(ph)
                else:
                    neg += 1; hits_neg.append(ph)

        total = pos + neg
        if total == 0:
            return SentimentOutput("neutral", "neutral", 0.0, 0.25, language,
                                   {"reason": "no_lexicon_hits"})
        raw = (pos - neg) / total
        score = max(-1.0, min(1.0, raw * intensity_boost))
        if pos and neg:
            general = "mixed" if abs(raw) < 0.34 else ("positive" if raw > 0 else "negative")
        else:
            general = "positive" if pos else "negative"
        conf = min(0.85, 0.3 + 0.1 * total) * (0.8 if general == "mixed" else 1.0)
        return SentimentOutput(general, _band(score), round(score, 4),
                               round(conf, 4), language,
                               {"pos_hits": hits_pos[:10], "neg_hits": hits_neg[:10],
                                "pos_count": pos, "neg_count": neg})
