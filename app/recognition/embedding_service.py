from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any

import cv2
import numpy as np
from deepface import DeepFace

from app.config.settings import Settings
from app.recognition.face_detector import FaceDetector


IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


@dataclass(frozen=True)
class EmbeddingIndex:
    person_names: list[str]
    prototypes: np.ndarray
    created_at: str
    model_name: str


class EmbeddingService:
    def __init__(self, settings: Settings, detector: FaceDetector) -> None:
        self._settings = settings
        self._detector = detector
        self._model = None

    def load_or_build_index(self) -> EmbeddingIndex:
        self._settings.embeddings_dir.mkdir(parents=True, exist_ok=True)
        if self._cache_is_valid():
            return self._load_index()
        return self._build_and_store_index()

    def _cache_is_valid(self) -> bool:
        if not self._settings.embeddings_file.exists() or not self._settings.embeddings_metadata_file.exists():
            return False
        try:
            metadata = json.loads(self._settings.embeddings_metadata_file.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return False
        current_signature = self._dataset_signature()
        return metadata.get("dataset_signature") == current_signature and metadata.get("model_name") == self._settings.recognition_model_name

    def _dataset_signature(self) -> list[dict[str, Any]]:
        signature: list[dict[str, Any]] = []
        if not self._settings.dataset_dir.exists():
            return signature
        for image_path in sorted(self._settings.dataset_dir.rglob("*")):
            if image_path.is_file() and image_path.suffix.lower() in IMAGE_EXTENSIONS:
                stat = image_path.stat()
                signature.append(
                    {
                        "path": str(image_path.relative_to(self._settings.dataset_dir)),
                        "mtime_ns": stat.st_mtime_ns,
                        "size": stat.st_size,
                    }
                )
        return signature

    def _load_index(self) -> EmbeddingIndex:
        cached = np.load(self._settings.embeddings_file, allow_pickle=True)
        person_names = cached["person_names"].tolist()
        prototypes = cached["prototypes"].astype(np.float32)
        metadata = json.loads(self._settings.embeddings_metadata_file.read_text(encoding="utf-8"))
        return EmbeddingIndex(
            person_names=[str(name) for name in person_names],
            prototypes=prototypes,
            created_at=metadata.get("created_at", ""),
            model_name=metadata.get("model_name", self._settings.recognition_model_name),
        )

    def _build_and_store_index(self) -> EmbeddingIndex:
        if not self._settings.dataset_dir.exists():
            raise FileNotFoundError(f"No existe el directorio del dataset: {self._settings.dataset_dir}")

        self._settings.embeddings_dir.mkdir(parents=True, exist_ok=True)
        grouped_embeddings: dict[str, list[np.ndarray]] = defaultdict(list)
        processed_images = 0
        skipped_images = 0

        for person_dir in sorted(path for path in self._settings.dataset_dir.iterdir() if path.is_dir()):
            person_name = person_dir.name.strip()
            for image_path in sorted(person_dir.iterdir()):
                if not image_path.is_file() or image_path.suffix.lower() not in IMAGE_EXTENSIONS:
                    continue
                processed_images += 1
                face_box = self._detector.detect_face_in_image(image_path)
                if face_box is None:
                    skipped_images += 1
                    print(f"[FACE_DETECT] {image_path.name}: sin rostro valido, imagen omitida")
                    continue
                image = cv2.imread(str(image_path))
                if image is None:
                    skipped_images += 1
                    continue
                face_crop = self._detector.crop_face(image, face_box)
                embedding = self.extract_embedding(face_crop)
                grouped_embeddings[person_name].append(self._normalize_embedding(embedding))
                print(f"[FACE_RECOGNITION] Embedding generado para {person_name}/{image_path.name}")

        person_names: list[str] = []
        prototypes: list[np.ndarray] = []
        if grouped_embeddings:
            for person_name in sorted(grouped_embeddings):
                embeddings = np.stack(grouped_embeddings[person_name], axis=0)
                prototype = self._normalize_embedding(np.mean(embeddings, axis=0))
                person_names.append(person_name)
                prototypes.append(prototype)

        index = EmbeddingIndex(
            person_names=person_names,
            prototypes=(np.stack(prototypes, axis=0).astype(np.float32) if prototypes else np.empty((0, 0), dtype=np.float32)),
            created_at=datetime.now(timezone.utc).isoformat(),
            model_name=self._settings.recognition_model_name,
        )
        np.savez_compressed(
            self._settings.embeddings_file,
            person_names=np.array(index.person_names, dtype=object),
            prototypes=index.prototypes,
        )
        metadata = {
            "created_at": index.created_at,
            "model_name": index.model_name,
            "dataset_signature": self._dataset_signature(),
            "processed_images": processed_images,
            "skipped_images": skipped_images,
            "persons": len(index.person_names),
        }
        self._settings.embeddings_metadata_file.write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")
        print(
            f"[FACE_RECOGNITION] Embeddings preparados: personas={len(index.person_names)} "
            f"imagenes_procesadas={processed_images} omitidas={skipped_images}"
        )
        return index

    def extract_embedding(self, face_image: np.ndarray) -> np.ndarray:
        if self._model is None:
            self._model = DeepFace.build_model(self._settings.recognition_model_name)
        representations = DeepFace.represent(
            img_path=face_image,
            model_name=self._settings.recognition_model_name,
            detector_backend="skip",
            enforce_detection=True,
            align=True,
        )
        if isinstance(representations, list) and representations:
            embedding = np.array(representations[0]["embedding"], dtype=np.float32)
            return embedding
        raise RuntimeError("DeepFace no devolvio un embedding valido")

    @staticmethod
    def _normalize_embedding(embedding: np.ndarray) -> np.ndarray:
        vector = embedding.astype(np.float32)
        norm = np.linalg.norm(vector)
        if norm == 0:
            return vector
        return vector / norm
