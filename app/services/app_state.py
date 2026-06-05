from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from threading import Lock
from typing import Any


@dataclass(frozen=True)
class DetectionSnapshot:
    timestamp: str
    person_detected: bool
    known_person: bool
    person_name: str | None
    confidence: float

    @classmethod
    def empty(cls) -> "DetectionSnapshot":
        return cls(
            timestamp=datetime.now(timezone.utc).isoformat(),
            person_detected=False,
            known_person=False,
            person_name=None,
            confidence=0.0,
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class AppState:
    def __init__(self) -> None:
        self._lock = Lock()
        self._last_detection = DetectionSnapshot.empty()
        self._last_published_signature: str | None = None
        self._last_published_at: float = 0.0

    def update_detection(self, snapshot: DetectionSnapshot) -> None:
        with self._lock:
            self._last_detection = snapshot

    def get_last_detection(self) -> DetectionSnapshot:
        with self._lock:
            return self._last_detection

    def can_publish(self, signature: str, now_seconds: float, cooldown_seconds: int) -> bool:
        with self._lock:
            if self._last_published_signature != signature:
                self._last_published_signature = signature
                self._last_published_at = now_seconds
                return True
            if now_seconds - self._last_published_at >= cooldown_seconds:
                self._last_published_at = now_seconds
                return True
            return False
