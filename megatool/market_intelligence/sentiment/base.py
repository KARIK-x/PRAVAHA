"""Sentiment model interface — models are pluggable and versioned.

Any model (lexicon baseline, nepse-sentiment-analyzer, FinBERT, a future
fine-tuned model) implements SentimentModel and is registered in
config/model_registry.json. The pipeline never hard-codes a model.
"""
from __future__ import annotations

from dataclasses import dataclass, field

VALID_GENERAL = {"positive", "negative", "neutral", "mixed", "uncertain"}
VALID_INTENSITY = {"very_negative", "negative", "slightly_negative", "neutral",
                   "slightly_positive", "positive", "very_positive", "uncertain"}


@dataclass
class SentimentOutput:
    general_sentiment: str
    intensity: str
    score: float          # -1..1
    confidence: float     # 0..1
    language: str
    details: dict = field(default_factory=dict)

    def validate(self) -> None:
        if self.general_sentiment not in VALID_GENERAL:
            raise ValueError(f"invalid general_sentiment: {self.general_sentiment}")
        if self.intensity not in VALID_INTENSITY:
            raise ValueError(f"invalid intensity: {self.intensity}")
        if not (-1.0 <= self.score <= 1.0):
            raise ValueError(f"score out of range: {self.score}")
        if not (0.0 <= self.confidence <= 1.0):
            raise ValueError(f"confidence out of range: {self.confidence}")


class SentimentModel:
    model_id = "abstract"
    model_version = "0.0.0"

    def predict(self, text: str, language: str = "unknown") -> SentimentOutput:
        raise NotImplementedError


def route_model(language: str, registry: dict) -> str:
    """Pick the configured model id for a detected language.

    Registry format: {"routes": {"ne": "lexicon-v1", "en": "lexicon-v1",
    "default": "lexicon-v1"}, ...}
    """
    routes = registry.get("routes", {})
    return routes.get(language, routes.get("default", "lexicon-v1"))
