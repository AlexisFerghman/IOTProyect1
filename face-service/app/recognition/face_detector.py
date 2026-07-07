from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import cv2
import numpy as np


@dataclass(frozen=True)
class FaceBox:
    x: int
    y: int
    w: int
    h: int

    @property
    def area(self) -> int:
        return self.w * self.h


class FaceDetector:
    def __init__(self, scale_factor: float = 1.1, min_neighbors: int = 5, min_size: int = 60) -> None:
        cascade_path = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        self._cascade = cv2.CascadeClassifier(cascade_path)
        if self._cascade.empty():
            raise RuntimeError(f"No se pudo cargar el clasificador Haar desde {cascade_path}")
        self._scale_factor = scale_factor
        self._min_neighbors = min_neighbors
        self._min_size = min_size

    def detect_faces(self, frame: np.ndarray) -> list[FaceBox]:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        gray = cv2.equalizeHist(gray)
        faces = self._cascade.detectMultiScale(
            gray,
            scaleFactor=self._scale_factor,
            minNeighbors=self._min_neighbors,
            minSize=(self._min_size, self._min_size),
        )
        return [FaceBox(int(x), int(y), int(w), int(h)) for x, y, w, h in faces]

    def detect_largest_face(self, frame: np.ndarray) -> FaceBox | None:
        faces = self.detect_faces(frame)
        if not faces:
            return None
        return max(faces, key=lambda face: face.area)

    def crop_face(self, frame: np.ndarray, face: FaceBox, padding_ratio: float = 0.15) -> np.ndarray:
        height, width = frame.shape[:2]
        padding_x = int(face.w * padding_ratio)
        padding_y = int(face.h * padding_ratio)
        x1 = max(face.x - padding_x, 0)
        y1 = max(face.y - padding_y, 0)
        x2 = min(face.x + face.w + padding_x, width)
        y2 = min(face.y + face.h + padding_y, height)
        return frame[y1:y2, x1:x2].copy()

    def detect_face_in_image(self, image_path: Path) -> FaceBox | None:
        image = cv2.imread(str(image_path))
        if image is None:
            return None
        return self.detect_largest_face(image)
