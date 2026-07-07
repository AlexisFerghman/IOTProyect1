from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from app.config.settings import Settings
from app.recognition.embedding_service import EmbeddingIndex


@dataclass(frozen=True)
class RecognitionResult:
    known_person: bool
    person_name: str | None
    confidence: float


class FaceRecognizer:
    def __init__(self, settings: Settings, index: EmbeddingIndex) -> None:
        self._settings = settings
        self._index = index

    def recognize(self, embedding: np.ndarray) -> RecognitionResult:
        if self._index.prototypes.size == 0 or len(self._index.person_names) == 0:
            return RecognitionResult(known_person=False, person_name=None, confidence=0.0)
        normalized_embedding = self._normalize_embedding(embedding)
        similarities = self._index.prototypes @ normalized_embedding
        best_position = int(np.argmax(similarities))
        best_similarity = float(similarities[best_position])
        if best_similarity < self._settings.confidence_threshold:
            return RecognitionResult(known_person=False, person_name=None, confidence=round(best_similarity, 4))
        return RecognitionResult(
            known_person=True,
            person_name=self._index.person_names[best_position],
            confidence=round(best_similarity, 4),
        )

    @staticmethod
    def _normalize_embedding(embedding: np.ndarray) -> np.ndarray:
        vector = embedding.astype(np.float32)
        norm = np.linalg.norm(vector)
        if norm == 0:
            return vector
        return vector / norm
