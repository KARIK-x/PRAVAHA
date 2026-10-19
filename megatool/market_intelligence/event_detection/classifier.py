"""Financial event classification (Part 11D/12).

Rule-based, multilingual (EN/NE/romanized) keyword classifier over a
configurable taxonomy (config/event_taxonomy.json). Rules are auditable and
versioned; an ML classifier can be added later behind the same interface.
Multiple event types per article are supported, each with a confidence
score; nothing is collapsed into a single opaque label.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_TAXONOMY: dict[str, list[str]] = {
    "earnings_announcement": ["quarterly report", "annual report", "net profit", "eps",
                              "financial result", "q1", "q2", "q3", "q4", "नाफा",
                              "वित्तीय विवरण", "त्रैमासिक", "munafa", "nafa", "quarterly"],
    "dividend": ["dividend", "cash dividend", "लाभांश", "labhansh", "labangsa"],
    "bonus_shares": ["bonus share", "bonus", "बोनस", "bonas"],
    "rights_issue": ["rights share", "right share", "rights issue", "हकप्रद", "hakprad", "hakprada"],
    "ipo": ["ipo", "initial public offering", "आईपीओ", "aipio", "primary issue"],
    "fpo": ["fpo", "further public offering", "एफपीओ"],
    "merger_acquisition": ["merger", "acquisition", "merge", "merged", "acquire",
                           "मर्जर", "एकीकरण", "marjar", "ekikaran", "acquires"],
    "regulatory_action": ["sebon", "directive", "regulator", "penalty", "fine",
                          "निर्देशन", "जरिवाना", "नियामक", "nirdeshan", "jaribana",
                          "sebon", "nrb directive"],
    "interest_rate_change": ["interest rate", "policy rate", "bank rate", "repo rate",
                             "ब्याजदर", "ब्याज दर", "byajdar", "byaj dar", "repo"],
    "monetary_policy": ["monetary policy", "mps", "मौद्रिक नीति", "maudrik niti"],
    "fiscal_policy_budget": ["budget", "fiscal policy", "tax", "customs duty",
                             "बजेट", "कर", "bajet", "kar", "appropriation"],
    "liquidity_event": ["liquidity", "liquidity crunch", "तरलता", "taralta",
                        "interbank", "deposit collection"],
    "hydropower_development": ["hydropower", "hydro", "power purchase agreement",
                               "ppa", "जलविद्युत", "बिजुली", "jalbidhyut", "bidhyut",
                               "bijuli", "megawatt", "mw ", "transmission line"],
    "political_event": ["government", "minister", "parliament", "election", "cabinet",
                        "सरकार", "मन्त्री", "संसद", "निर्वाचन", "sarkar", "mantri",
                        "samsad", "nirbachan", "prime minister", "प्रधानमन्त्री"],
    "natural_disaster": ["earthquake", "flood", "landslide", "drought",
                         "भूकम्प", "बाढी", "पहिरो", "भुकम्प", "badhi", "pahiro",
                         "bhukampa", "bhukampa"],
    "forex_remittance": ["remittance", "foreign exchange", "forex reserve",
                         "रेमिट्यान्स", "विदेशी मुद्रा", "remittance", "remitansa",
                         "exchange rate", "सटही"],
    "inflation_macro": ["inflation", "cpi", "price index", "महँगी", "मुद्रास्फीति",
                        "mahangi", "mudrasfiti", "gdp", "economic growth"],
    "market_microstructure": ["trading halt", "circuit breaker", "settlement",
                              "ट्रेडिङ", "nepse", "नेप्से", "broker", "ब्रोकर"],
    "credit_rating_debt": ["credit rating", "rating downgrade", "rating upgrade",
                           "bond", "debenture", "डिबेन्चर", "debencar", "icra",
                           "care rating", "ऋणपत्र"],
}


@dataclass
class EventClassification:
    event_type: str
    confidence: float
    matched_terms: list[str] = field(default_factory=list)


class EventClassifier:
    def __init__(self, taxonomy: dict[str, list[str]] | None = None,
                 version: str = "1.0.0"):
        self.taxonomy = taxonomy or DEFAULT_TAXONOMY
        self.version = version
        self._patterns: dict[str, list[re.Pattern]] = {
            etype: [re.compile(r"(?<![\wऀ-ॿ])" + re.escape(t.lower()) + r"(?![\wऀ-ॿ])")
                    if re.match(r"^[a-z ]+$", t.lower()) else re.compile(re.escape(t))
                    for t in terms]
            for etype, terms in self.taxonomy.items()
        }

    @classmethod
    def from_file(cls, path: str | Path) -> "EventClassifier":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(data["taxonomy"], version=data.get("version", "1.0.0"))

    def classify(self, text: str, *, max_types: int = 3) -> list[EventClassification]:
        low = (text or "").lower()
        scored: list[EventClassification] = []
        for etype, pats in self._patterns.items():
            matched = [t for t, p in zip(self.taxonomy[etype], pats) if p.search(low)]
            if matched:
                conf = min(0.95, 0.4 + 0.15 * len(matched))
                scored.append(EventClassification(etype, round(conf, 4), matched[:8]))
        scored.sort(key=lambda c: c.confidence, reverse=True)
        return scored[:max_types]
