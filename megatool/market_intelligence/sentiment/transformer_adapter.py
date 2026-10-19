"""Optional Hugging Face transformer adapter (nepse-sentiment-analyzer,
FinBERT family, etc.).

Deliberately NOT a hard dependency: transformers/tensorflow are heavy for
the 8 GB M1 target. The adapter is import-guarded, model loading is lazy,
and the class is exercised in tests via a mock backend (no weight
download). See docs/MODEL_EVALUATION.md for the evaluation protocol —
self-reported accuracy on a model card is never treated as verified.
"""
from __future__ import annotations

from .base import SentimentModel, SentimentOutput

# nepse-sentiment-analyzer (robinGiri2024): 5-class BiLSTM-CNN, Keras.
_NEPSE_LABELS = {0: "very_negative", 1: "negative", 2: "neutral",
                 3: "positive", 4: "very_positive"}
_LABEL_TO_GENERAL = {
    "very_negative": "negative", "negative": "negative", "neutral": "neutral",
    "positive": "positive", "very_positive": "positive",
}
_LABEL_TO_SCORE = {"very_negative": -1.0, "negative": -0.5, "neutral": 0.0,
                   "positive": 0.5, "very_positive": 1.0}


class HFTransformerSentiment(SentimentModel):
    """Generic adapter around a local HF/Keras text classifier.

    backend: callable(text) -> list[float] (class probabilities). Injected so
    tests can run without downloading weights; production wiring lives in
    load_from_hub().
    """

    def __init__(self, model_id: str, model_version: str, backend,
                 label_map: dict[int, str] | None = None):
        self.model_id = model_id
        self.model_version = model_version
        self._backend = backend
        self._label_map = label_map or _NEPSE_LABELS

    def predict(self, text: str, language: str = "unknown") -> SentimentOutput:
        probs = list(self._backend(text or ""))
        if not probs or abs(sum(probs) - 1.0) > 0.25:
            return SentimentOutput("uncertain", "uncertain", 0.0, 0.0, language,
                                   {"error": "invalid_model_output"})
        idx = max(range(len(probs)), key=lambda i: probs[i])
        label = self._label_map.get(idx, "neutral")
        return SentimentOutput(
            _LABEL_TO_GENERAL.get(label, "neutral"), label,
            round(_LABEL_TO_SCORE.get(label, 0.0) * float(probs[idx]), 4),
            round(float(probs[idx]), 4), language,
            {"probabilities": [round(p, 4) for p in probs]},
        )

    @classmethod
    def load_from_hub(cls, model_id: str, path: str | None = None):
        """Load a Keras/transformers model. Raises ImportError with guidance
        instead of failing cryptically when heavy deps are absent."""
        try:
            from tensorflow.keras.models import load_model  # noqa
        except ImportError as e:
            raise ImportError(
                "tensorflow is required for Keras .keras models "
                "(e.g. nepse-sentiment-analyzer). Install the 'ml' extra "
                "only on hardware with sufficient RAM."
            ) from e
        raise NotImplementedError(
            "Weight loading requires the preprocessing spec of the specific "
            "model; wire it here after reviewing the model card."
        )
